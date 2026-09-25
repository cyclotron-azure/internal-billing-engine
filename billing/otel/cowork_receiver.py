"""Standalone OTLP/JSON receiver for Claude Cowork telemetry.

A brand-new, SEPARATE HTTP server process -- structurally parallel to
`billing/otel/receiver.py` but sharing no port, token, database file, or log
file with it. This is a deliberate, user-approved exception to this repo's
"one receiver process" hard constraint (see
`_goals/cowork-telemetry-ingest/goal.md`): the exception is scoped narrowly
to "one receiver process per SQLite store" -- it does NOT relax SQLite's
single-connection safety within EITHER store. This process still runs as one
single-threaded `http.server.HTTPServer` against one `CoworkStore` connection,
exactly like `receiver.py` does for `OtelStore`.

This module MUST NEVER `import billing.otel.receiver` -- that module runs
`load_env()` and populates a module-level `AUTH_TOKEN` global (read from
`RECEIVER_AUTH_TOKEN`) at IMPORT TIME, which would silently couple this
process's behavior to the existing pipeline's environment/secrets handling.
Instead, this module DUPLICATES the small amount of body-reading logic it
needs (`_read_body`'s chunked/gzip handling) as a local, independent copy --
same rule `cowork_ingest.py` already follows for its own parsing helpers.

Auth: a NEW, distinct environment variable, `COWORK_RECEIVER_AUTH_TOKEN` --
never `RECEIVER_AUTH_TOKEN` (that name does not appear anywhere in this
file). Loaded via `billing.config.load_env()` -- a small, generic, shared
`.env` reader used by several modules in this repo (not
`billing.otel.receiver`), so calling it does not violate the
never-import-receiver rule above. `load_env()` does write every `.env` key
(including `RECEIVER_AUTH_TOKEN`, if present) into `os.environ` via
`setdefault` -- that is `load_env`'s ordinary, shared, repo-wide behavior,
and every other module that calls it already accepts it. What matters for
THIS file's isolation is narrower: it reads ONLY
`os.environ.get("COWORK_RECEIVER_AUTH_TOKEN", "")`, so the existing
receiver's token value is never consulted or compared against here.

Point a Cowork client at it with its own port (default 4319, distinct from
receiver.py's 4318):
    OTEL_EXPORTER_OTLP_PROTOCOL=http/json
    OTEL_EXPORTER_OTLP_ENDPOINT=http://<host>:4319
"""

from __future__ import annotations

import argparse
import gzip
import hmac
import json
import os
import sqlite3
import time
import zlib
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

from ..config import load_env
from . import cowork_ingest
from . import cowork_store
from .cowork_store import CoworkStore

load_env()

# Fix-cycle-1: an env value that is PRESENT but EMPTY (e.g. a `.env` copied
# from `.env.example` with `COWORK_RECEIVER_LOG=` left blank) must be treated
# as unset, not as "log to the empty path". `os.environ.get(key, default)`
# only supplies `default` when the key is ABSENT -- an empty string is a
# perfectly good value as far as `.get` is concerned, and `open("")` then
# raises `FileNotFoundError`, which `_log`'s `except OSError` silently
# swallows: every rejection/401 log line would vanish with zero indication
# anything was wrong. `or` (not `.get(..., default)`) is required here so an
# empty-but-present value still falls through to the real default.
LOG_PATH = os.environ.get("COWORK_RECEIVER_LOG") or "data/cowork_receiver.log"
AUTH_TOKEN = (os.environ.get("COWORK_RECEIVER_AUTH_TOKEN") or "").strip()

_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

#: Log-line safety bounds (fix-cycle 1, security finding): a rejection's
#: `reason`/`detail` strings, and metric names in `metrics_seen`, come
#: straight from attacker-controlled payload content by way of
#: `cowork_ingest.py` -- this receiver is documented to run OPEN (no auth)
#: until a token is configured, so this needs no authentication to trigger.
#: Two distinct risks, both closed by `_sanitize_log_field`/the rejection-
#: line cap below:
#:   1. Log injection: an embedded "\r"/"\n" in a field would forge what
#:      looks like a separate, fake log line.
#:   2. Disk-fill amplification: an unbounded field length, times an
#:      unbounded NUMBER of rejections in one payload (one per malformed
#:      metric/datapoint), can turn a modest request into a massive log
#:      write (confirmed by evaluator probing: ~592x amplification from an
#:      ~85KB request).
_MAX_LOG_FIELD_LEN = 200
_MAX_REJECTION_LOG_LINES = 20

#: Request-body size bound (fix-cycle 2, issue 4). `Content-Length` is a
#: client-supplied integer: a syntactically valid but absurd value
#: (99999999999999) made `rfile.read(length)` attempt that allocation and
#: die with an uncaught `MemoryError` (connection dropped, no HTTP response);
#: a merely large one (2GB) would attempt that allocation per request; a
#: NEGATIVE one read until the client closed the connection (a hang on a slow
#: or malicious client). Why 8 MiB: a Cowork OTLP/JSON metric export is a
#: handful of resourceMetrics/scopeMetrics records with a few datapoints
#: each -- tens of kilobytes at most, and well under one megabyte even for a
#: very busy client batching aggressively -- so 8 MiB is roughly two orders
#: of magnitude of headroom over legitimate traffic while still being a size
#: a single-threaded receiver can allocate and JSON-parse without noticeable
#: harm. The same bound applies to the chunked path's cumulative size, and
#: to a gzip body AFTER decompression (a compressed payload under the bound
#: can inflate far past it).
MAX_BODY_BYTES = 8 * 1024 * 1024


class BodyTooLargeError(Exception):
    """Raised by `_read_body` when a request body exceeds `MAX_BODY_BYTES`
    (declared, cumulative, or post-decompression) -- or when the platform
    refuses the allocation outright. `do_POST` maps it to HTTP 413. Not a
    `ValueError` subclass on purpose: a body that is merely TOO BIG is a
    different failure from one that is MALFORMED (400), and callers/clients
    should be able to tell them apart."""


#: The two most common line breakers keep their familiar, readable escape
#: (\\r, \\n) -- everything else non-printable is hex-escaped as \\xNN.
_READABLE_ESCAPES = {"\r": "\\r", "\n": "\\n"}


def _escape_char(c: str) -> str:
    if c.isprintable():
        return c
    return _READABLE_ESCAPES.get(c) or f"\\x{ord(c):02x}"


def _sanitize_log_field(value) -> str:
    """Make an attacker-controlled value safe to interpolate into ONE log
    line, and cap its length so one field can't blow up the log file's size.

    Fix-cycle 2 (issue 3): the fix-cycle-1 version escaped only "\\r" and
    "\\n". That left every OTHER line-breaking or terminal-controlling
    character through unescaped -- NEL (U+0085), LINE/PARAGRAPH SEPARATOR
    (U+2028/U+2029), vertical tab, form feed, the ASCII separators
    (\\x1c-\\x1e), and ANSI escape sequences (ESC = \\x1b) -- each of which
    forges an apparent new line for `str.splitlines()` or a live `tail -f`
    viewer, and ESC sequences can rewrite/hide earlier terminal output. Now
    EVERY non-printable character is hex-escaped: `str.isprintable()` is
    False for all Unicode control (Cc), format (Cf), separator (Zl/Zp/Zs
    other than ASCII space), surrogate, and unassigned code points -- which
    is exactly the set that misbehaves in a single-line text log. Legitimate
    log content here is metric names, service names, header values, error
    messages, and request paths -- none of which needs any of those
    characters, so no exception is carved out. Backslash is escaped first so
    the output is unambiguous (a literal "\\x85" in input stays
    distinguishable from an escaped NEL).
    """
    s = str(value)
    s = s.replace("\\", "\\\\")
    s = "".join(_escape_char(c) for c in s)
    if len(s) > _MAX_LOG_FIELD_LEN:
        s = s[:_MAX_LOG_FIELD_LEN] + "...(truncated)"
    return s


def _now() -> datetime:
    """The single source of "now" for /healthz -- a module-level helper (not
    an inline `datetime.now()`) so it can be monkeypatched in tests."""
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime(_TS_FORMAT)


def _presented_token(headers) -> str:
    """The credential a request presents, from X-Billing-Token or a Bearer
    Authorization header ('' if neither is present). Same convention as
    receiver.py, reproduced locally -- never imported from it."""
    tok = headers.get("X-Billing-Token")
    if tok:
        return tok.strip()
    auth = headers.get("Authorization", "")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    return ""


def _log(msg: str) -> None:
    """Append a line to THIS receiver's own log file -- never receiver.log."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(LOG_PATH)), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except OSError:
        pass


def _read_body(handler) -> bytes:
    """Read the full request body, handling Content-Length, chunked transfer
    encoding, and gzip. DUPLICATED from receiver.py's `_read_body` (never
    imported -- see module docstring) since OTLP/HTTP clients commonly use
    chunked + gzip, which have no Content-Length header."""
    te = (handler.headers.get("Transfer-Encoding") or "").lower()
    if "chunked" in te:
        parts = []
        total = 0
        while True:
            size_line = handler.rfile.readline().strip()
            if not size_line:
                break
            try:
                size = int(size_line.split(b";")[0], 16)
            except ValueError:
                break
            if size == 0:
                handler.rfile.readline()  # consume trailing CRLF
                break
            # Fix-cycle 2 (issue 4): a chunk-size line is exactly as
            # client-controlled as Content-Length, so the same bound applies
            # -- per chunk AND cumulatively.
            if size < 0:
                raise ValueError(f"negative chunk size {size}")
            total += size
            if total > MAX_BODY_BYTES:
                raise BodyTooLargeError(
                    f"chunked body exceeds {MAX_BODY_BYTES} bytes")
            parts.append(_read_exact(handler, size))
            handler.rfile.readline()      # CRLF after each chunk
        body = b"".join(parts)
    else:
        length = int(handler.headers.get("Content-Length", 0) or 0)
        # Fix-cycle 2 (issue 4): validate BEFORE touching rfile. A negative
        # length is malformed (400) -- previously `rfile.read(-1)` read
        # until the client closed the connection. An oversized one is 413
        # -- previously `rfile.read(99999999999999)` raised an uncaught
        # MemoryError and dropped the connection with no response.
        if length < 0:
            raise ValueError(f"negative Content-Length {length}")
        if length > MAX_BODY_BYTES:
            raise BodyTooLargeError(
                f"Content-Length {length} exceeds {MAX_BODY_BYTES} bytes")
        body = _read_exact(handler, length) if length else b""
    if "gzip" in (handler.headers.get("Content-Encoding") or "").lower():
        try:
            body = gzip.decompress(body)
        except OSError:
            pass
        except MemoryError:
            # A gzip bomb: compressed size under the bound, decompressed
            # size beyond what the platform will allocate.
            raise BodyTooLargeError(
                "gzip body too large to decompress") from None
        if len(body) > MAX_BODY_BYTES:
            raise BodyTooLargeError(
                f"decompressed body {len(body)} exceeds {MAX_BODY_BYTES} bytes")
    return body


def _read_exact(handler, n: int) -> bytes:
    """`handler.rfile.read(n)` with a last-resort `MemoryError` safety net
    (fix-cycle 2, issue 4): `_read_body` validates `n` against
    `MAX_BODY_BYTES` before ever calling this, so under normal conditions
    this cannot trip -- but if a value ever slipped past that check on a
    platform where the bound itself has an edge case (or the host is simply
    out of memory), the caller must still get a clean HTTP 413 rather than a
    dropped connection and a traceback on stderr."""
    try:
        return handler.rfile.read(n)
    except MemoryError:
        raise BodyTooLargeError(
            f"could not allocate {n} bytes for request body") from None


#: Data-shape exceptions caught PER RECORD around each store insert, mirroring
#: receiver.py's own `_RECORD_DATA_ERRORS` tuple and its documented reasoning:
#: a record that passes cowork_ingest.py's own validation can still raise at
#: the store-insert boundary (e.g. an unbindable SQLite parameter type slipping
#: through in a field cowork_ingest.py doesn't type-check as strictly as this
#: receiver would like, or a future cowork_ingest.py change that's less
#: defensive than today's). Never `sqlite3.OperationalError` -- a genuine
#: operational failure (disk full, database locked) must still propagate so it
#: is never masked as an ordinary 200; see the outer rollback/re-raise below.
_RECORD_DATA_ERRORS = (
    ValueError, TypeError, AttributeError, KeyError,
    sqlite3.InterfaceError, sqlite3.ProgrammingError,
)


def ingest_cowork_metrics_payload(payload, store: CoworkStore) -> dict:
    """Parse an OTLP/JSON payload via `cowork_ingest.parse_cowork_payload`,
    store every accepted row, and log every rejection (reason + minimal
    identifiers, never raw request bytes).

    Response contract:
        {
          "inserted": <int>, "token_inserted": <int>, "cost_inserted": <int>,
          "duplicate": <int>, "rejected": <int>, "metrics_seen": [<str>, ...],
        }

    Mirrors receiver.py's `ingest_transcript_usage_payload` commit/rollback
    discipline: the per-record loop AND `store.commit()` both live inside one
    guarded region. Any exception NOT in `_RECORD_DATA_ERRORS` (e.g.
    `sqlite3.OperationalError`, a genuine operational failure) rolls back the
    connection before re-raising, so no partial batch is ever left uncommitted
    on the connection for a LATER, unrelated request's commit() to silently
    pick up. `parse_cowork_payload` itself only raises TypeError for an
    unusable (non-dict) envelope -- no store write has happened yet at that
    point, so nothing needs rolling back for that case; it's left to the
    caller (do_POST) to turn into a 400.

    Fix-cycle 1: rejections are now logged in a `finally` block, so a batch
    whose `store.commit()` (or a mid-loop insert) raises still gets every
    rejection identified before the failure logged -- previously the log
    call sat AFTER the guarded try/except, so an exception propagating out
    of that block skipped it entirely, silently losing rejection lines for
    exactly the batches most worth investigating.
    """
    parsed = cowork_ingest.parse_cowork_payload(payload)

    tok_ins = tok_dup = cost_ins = cost_dup = 0
    rejected = list(parsed["rejections"])

    try:
        try:
            for row in parsed["token_rows"]:
                session_id = row.get("session_id")
                try:
                    ok = store.insert_datapoint(**row)
                    tok_ins += 1 if ok else 0
                    tok_dup += 0 if ok else 1
                except _RECORD_DATA_ERRORS as e:
                    rejected.append({
                        "reason": f"store_error:{e.__class__.__name__}",
                        "detail": f"session_id={session_id!r} metric=token",
                    })

            for row in parsed["cost_rows"]:
                session_id = row.get("session_id")
                try:
                    ok = store.insert_cost_datapoint(**row)
                    cost_ins += 1 if ok else 0
                    cost_dup += 0 if ok else 1
                except _RECORD_DATA_ERRORS as e:
                    rejected.append({
                        "reason": f"store_error:{e.__class__.__name__}",
                        "detail": f"session_id={session_id!r} metric=cost",
                    })

            # commit() lives INSIDE this guarded region -- a commit-time
            # failure (sqlite3.OperationalError) is exactly as capable of
            # leaving this batch's writes uncommitted as a mid-loop failure,
            # and must roll back too. See receiver.py's
            # ingest_transcript_usage_payload for the full reasoning this
            # mirrors.
            store.commit()
        except Exception:
            store.db.rollback()
            raise
    finally:
        # Log every rejection identified so far -- reason + minimal
        # identifiers, never raw bytes -- REGARDLESS of whether the guarded
        # region above succeeded or raised (see fix-cycle-1 note above).
        # Capped to _MAX_REJECTION_LOG_LINES real lines plus one summary
        # line, and every field sanitized, so a payload engineered to carry
        # a huge number of oversized rejection reasons (attacker-controlled,
        # reachable with NO auth on an open receiver) can't turn one request
        # into an unbounded log write or forge fake log lines via embedded
        # newlines.
        for r in rejected[:_MAX_REJECTION_LOG_LINES]:
            reason = _sanitize_log_field(r.get("reason", ""))
            detail = _sanitize_log_field(r.get("detail", ""))
            _log(f"REJECTED {reason}: {detail}")
        omitted = len(rejected) - _MAX_REJECTION_LOG_LINES
        if omitted > 0:
            _log(f"REJECTED +{omitted} more rejections omitted")

    return {
        "inserted": tok_ins + cost_ins,
        "token_inserted": tok_ins,
        "cost_inserted": cost_ins,
        "duplicate": tok_dup + cost_dup,
        "rejected": len(rejected),
        "metrics_seen": parsed["metrics_seen"],
    }


class Handler(BaseHTTPRequestHandler):
    store: CoworkStore = None  # set by serve()

    def log_message(self, *args):  # quieter
        pass

    def _ok(self, body: bytes = b"{}"):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        """True if auth is disabled, or the request presents the right
        token. Constant-time compare so a wrong token leaks nothing via
        timing -- same convention as receiver.py, reproduced locally.

        Fix-cycle 1: `hmac.compare_digest` raises `TypeError` for a `str`
        argument containing non-ASCII characters (a deliberate CPython
        security restriction, not a bug) -- a client presenting a non-ASCII
        token must still get a clean 401, not an unhandled exception that
        drops the connection. This is NOT an auth-bypass concern (the
        request is still correctly refused either way); it's purely about
        never crashing on attacker-controlled input.
        """
        if not AUTH_TOKEN:
            return True
        presented = _presented_token(self.headers)
        if not presented:
            return False
        try:
            return hmac.compare_digest(presented, AUTH_TOKEN)
        except TypeError:
            return False

    def _unauthorized(self):
        body = b'{"error":"unauthorized"}'
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("WWW-Authenticate", "Bearer")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj: dict):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _healthz(self):
        """GET /healthz -- liveness to anyone, ingest-freshness detail to an
        authorized caller only, and only when a token is actually configured
        (both conditions required -- mirrors receiver.py's own `_healthz`
        gating logic exactly, so an open receiver never discloses whether a
        token is configured via the body's shape)."""
        now = _now()
        body: dict = {"status": "ok", "now": _iso(now)}
        if AUTH_TOKEN and self._authorized():
            try:
                body["last_ingest_at"] = self.store.last_ingest_at()
            except sqlite3.Error:
                self._json(503, {"status": "degraded"})
                return
        self._json(200, body)

    def do_GET(self):
        path = self.path.rstrip("/")
        if path.endswith("/healthz"):
            self._healthz()
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        # Reject before reading/parsing the body: an unauthenticated caller
        # never reaches the store.
        # Fix-cycle 2 (issue 2): EVERY request-derived value that reaches a
        # `_log(...)` call in this method goes through `_sanitize_log_field`
        # -- the request path (logged on the 401 line with NO auth at all)
        # and the Content-Type / Transfer-Encoding / Content-Encoding header
        # values. Fix-cycle 1 sanitized only payload-derived fields; a CRLF-
        # folded header value ("application/json\r\n 12:00:00 FORGED") then
        # forged a genuinely separate log line, and a multi-megabyte folded
        # header or a 60KB path wrote that many bytes per request. The
        # sanitized copies are what get LOGGED; the raw header values still
        # drive behavior (`_read_body` reads the headers itself).
        safe_path = _sanitize_log_field(self.path)
        if not self._authorized():
            _log(f"401 POST {safe_path} (missing/invalid token)")
            self._unauthorized()
            return
        ctype = _sanitize_log_field(self.headers.get("Content-Type", "?"))
        te = _sanitize_log_field(self.headers.get("Transfer-Encoding", "-"))
        ce = _sanitize_log_field(self.headers.get("Content-Encoding", "-"))
        try:
            # Fix-cycle 1: _read_body (the faithfully-duplicated chunked/
            # gzip parsing logic) can raise ValueError (a non-numeric
            # Content-Length header), EOFError (a truncated gzip body --
            # `gzip.decompress` raises this directly; it is NOT an OSError
            # subclass, so it escapes _read_body's own inner `except
            # OSError`), or zlib.error (a corrupt deflate stream inside an
            # otherwise well-formed gzip header). None of these were
            # previously caught anywhere, so the connection just dropped
            # with a traceback on stderr and no HTTP response at all --
            # fail-closed-and-silent is not fail-closed. Every one of these
            # is untrusted-client input, never a reason to leave the caller
            # without a response.
            raw = _read_body(self)
        except BodyTooLargeError as e:
            # Fix-cycle 2 (issue 4): a declared/cumulative/decompressed body
            # over MAX_BODY_BYTES -- or an allocation the platform refused --
            # is a clean 413, never a MemoryError traceback and a dropped
            # connection.
            print(f"[cowork-receiver] request body too large: {_sanitize_log_field(e)}")
            _log(f"413 POST {safe_path} ({ctype} te={te} ce={ce}): "
                 f"{_sanitize_log_field(e)}")
            self.send_response(413)
            self.end_headers()
            return
        except (ValueError, EOFError, zlib.error) as e:
            print(f"[cowork-receiver] bad request body: {_sanitize_log_field(e)}")
            _log(f"BAD request body ({ctype} te={te} ce={ce}): "
                 f"{_sanitize_log_field(e)}")
            self.send_response(400)
            self.end_headers()
            return
        path = self.path.rstrip("/")
        _log(f"POST {safe_path} bytes={len(raw)} content-type={ctype} te={te} ce={ce}")
        if path.endswith("/v1/metrics"):
            try:
                payload = json.loads(raw or b"{}")
                if not isinstance(payload, dict):
                    raise TypeError(
                        f"cowork payload must be a dict, got {type(payload).__name__}")
                result = ingest_cowork_metrics_payload(payload, self.store)
            except (ValueError, TypeError, RecursionError) as e:
                # Never log raw request bytes/content on a malformed body --
                # mirrors receiver.py's OWN deliberate divergence on its
                # /v1/transcript-usage 400 path: echoing raw bytes here would
                # leak payload content into a log file. RecursionError (fix-
                # cycle 1) is what CPython's json decoder raises for
                # pathologically deeply-nested input (e.g. ~100k levels of
                # "[") -- previously uncaught, dropping the connection.
                print(f"[cowork-receiver] bad metrics payload: {_sanitize_log_field(e)}")
                _log(f"BAD metrics payload ({ctype} te={te} ce={ce}) "
                     f"bytes={len(raw)}: {_sanitize_log_field(e)}")
                self.send_response(400)
                self.end_headers()
                return
            seen = [_sanitize_log_field(n) for n in result["metrics_seen"][:_MAX_REJECTION_LOG_LINES]]
            msg = (f"/v1/metrics tok+={result['token_inserted']} "
                   f"cost+={result['cost_inserted']} dup={result['duplicate']} "
                   f"rejected={result['rejected']} metrics_seen={seen}")
            print(f"[cowork-receiver] {msg}")
            _log(msg)
            self._ok(json.dumps(result).encode("utf-8"))
            return
        # /v1/logs, /v1/traces, anything else: just acknowledge, matching
        # receiver.py's actual catch-all behavior exactly.
        self._ok()


def serve(host: str, port: int, db: str | None = None, require_auth: bool = False):
    if require_auth and not AUTH_TOKEN:
        raise SystemExit(
            "[cowork-receiver] --require-auth set but COWORK_RECEIVER_AUTH_TOKEN is "
            "empty — refusing to start. Set the token, or drop --require-auth to run "
            "open.")
    Handler.store = CoworkStore(db) if db else CoworkStore()
    server = HTTPServer((host, port), Handler)
    auth_state = "ENABLED" if AUTH_TOKEN else "DISABLED"
    print(f"[cowork-receiver] listening on http://{host}:{port}  auth={auth_state}  "
          f"(POST /v1/metrics; GET /healthz)")
    if not AUTH_TOKEN:
        print("[cowork-receiver] WARNING: COWORK_RECEIVER_AUTH_TOKEN is unset — any "
              "client that can reach this port can write billing rows. Set it to "
              "require a token.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        Handler.store.close()


def main():
    # Fix-cycle 1: `DEFAULT_COWORK_DB` (imported above) was FROZEN at
    # cowork_store's own import time, which happens as part of THIS module's
    # `from .cowork_store import ...` line near the top -- i.e. BEFORE this
    # module's own `load_env()` call a few lines later ever runs. A
    # `COWORK_DB` value sitting in `.env` is therefore never visible to
    # `cowork_store.py` at the moment it computes its default, and using
    # `DEFAULT_COWORK_DB` directly as argparse's `--db` default would
    # silently ignore it. Re-reading `os.environ.get("COWORK_DB")` here,
    # after `load_env()` has already populated it, fixes that -- `or`
    # (not `.get(..., default)`) so an empty-but-present `.env` value (e.g.
    # `COWORK_DB=` left blank, same trap as issue 1's log path) still falls
    # through to the real default instead of resolving to "" and making
    # `sqlite3.connect("")` open a throwaway temp database.
    db_default = os.environ.get("COWORK_DB") or cowork_store.DEFAULT_COWORK_DB
    ap = argparse.ArgumentParser(description="OTLP/JSON receiver for Claude Cowork.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4319)
    ap.add_argument("--db", default=db_default)
    ap.add_argument("--require-auth", action="store_true",
                    help="refuse to start unless COWORK_RECEIVER_AUTH_TOKEN is set")
    args = ap.parse_args()
    serve(args.host, args.port, args.db, require_auth=args.require_auth)


if __name__ == "__main__":
    main()
