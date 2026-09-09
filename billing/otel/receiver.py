"""Minimal OTLP/JSON receiver for Claude Code telemetry.

Accepts OTLP/HTTP JSON on /v1/metrics (and acks /v1/logs, /v1/traces), extracts
`claude_code.token.usage` data points, resolves the repo (from the injected
`repo` resource attribute) + user + model + token type, and writes deduped rows
to the OTEL store.

Also accepts POST /v1/session-repo — NOT an OTLP endpoint. That's the
session->repo timeline fed by the CwdChanged hook (deploy/claude-repo-tag.py),
which is how mid-session repo switches get attributed; the frozen `repo=`
resource attribute can't see them. See billing.otel.attribute.

Point Claude Code at it with:
    OTEL_EXPORTER_OTLP_PROTOCOL=http/json
    OTEL_EXPORTER_OTLP_ENDPOINT=http://<host>:4318

Authentication (shared fleet token):
    Set RECEIVER_AUTH_TOKEN and every write (POST) must present it, either as
        X-Billing-Token: <token>          (preferred — no spaces to encode)
        Authorization: Bearer <token>
    Clients: Claude Code sends it via OTEL_EXPORTER_OTLP_HEADERS, the CwdChanged
    hook via CLAUDE_BILLING_TOKEN (see deploy/). The token authenticates a fleet
    machine, not an individual user — it stops unauthorized injection from
    anything that can merely reach the port, not forgery by a holder of the
    token. If RECEIVER_AUTH_TOKEN is unset the receiver stays open (with a loud
    warning) so the token can be rolled out to machines before enforcement is
    turned on; pass --require-auth to refuse to start without one.

Dependency-free (stdlib http.server). For production durability you'd normally
front this with an OpenTelemetry Collector; this is the lean direct path.
"""

from __future__ import annotations

import argparse
import gzip
import hmac
import json
import os
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from ..config import load_env
from .normalize import normalize_remote
from .otel_store import OtelStore
from .rating import RatingService
from .transcript import map_record, validate_batch

load_env()

TOKEN_METRIC = "claude_code.token.usage"
COST_METRIC = "claude_code.cost.usage"
LOG_PATH = os.environ.get("RECEIVER_LOG", "data/receiver.log")
AUTH_TOKEN = os.environ.get("RECEIVER_AUTH_TOKEN", "").strip()


def _presented_token(headers) -> str:
    """The credential a request presents, from X-Billing-Token or a Bearer
    Authorization header ('' if neither is present)."""
    tok = headers.get("X-Billing-Token")
    if tok:
        return tok.strip()
    auth = headers.get("Authorization", "")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    return ""


def _log(msg: str) -> None:
    """Append a line to a log file so inbound requests are visible after the fact."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(LOG_PATH)), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except OSError:
        pass


def _read_body(handler) -> bytes:
    """Read the full request body, handling Content-Length, chunked transfer
    encoding, and gzip — OTLP/HTTP clients (incl. Claude Code) commonly use
    chunked + gzip, which have no Content-Length header."""
    te = (handler.headers.get("Transfer-Encoding") or "").lower()
    if "chunked" in te:
        parts = []
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
            parts.append(handler.rfile.read(size))
            handler.rfile.readline()      # CRLF after each chunk
        body = b"".join(parts)
    else:
        length = int(handler.headers.get("Content-Length", 0) or 0)
        body = handler.rfile.read(length) if length else b""
    if "gzip" in (handler.headers.get("Content-Encoding") or "").lower():
        try:
            body = gzip.decompress(body)
        except OSError:
            pass
    return body


def _attr_value(v: dict):
    if "stringValue" in v:
        return v["stringValue"]
    if "intValue" in v:
        return int(v["intValue"])
    if "doubleValue" in v:
        return v["doubleValue"]
    if "boolValue" in v:
        return v["boolValue"]
    return None


def _attrs(attr_list) -> dict:
    return {a["key"]: _attr_value(a.get("value", {})) for a in (attr_list or [])}


def _datapoints(metric: dict) -> list:
    return (metric.get("sum") or metric.get("gauge") or {}).get("dataPoints", [])


def _common(res: dict, dp: dict) -> dict:
    """Merge resource + datapoint attributes and pull the fields we store."""
    a = dict(res)
    a.update(_attrs(dp.get("attributes")))  # datapoint attrs win
    repo_raw = a.get("repo")
    return {
        "session_id": a.get("session.id") or "unknown",
        "repo": normalize_remote(repo_raw),
        "repo_raw": repo_raw or "",
        "user_email": a.get("user.email") or "",
        "user_id": a.get("user.id") or "",
        "org_id": a.get("organization.id") or "",
        "model": a.get("model") or "unknown",
        "query_source": a.get("query_source") or "main",
        "type": a.get("type") or "unknown",
        "time_unix_nano": dp.get("timeUnixNano") or dp.get("startTimeUnixNano") or 0,
    }


def ingest_metrics_payload(payload: dict, store: OtelStore) -> dict:
    """Parse an OTLP/JSON ExportMetricsServiceRequest, routing the token and
    cost metrics into their tables."""
    tok_ins = tok_dup = cost_ins = cost_dup = 0
    names = set()
    for rm in payload.get("resourceMetrics", []):
        res = _attrs(rm.get("resource", {}).get("attributes"))
        for sm in rm.get("scopeMetrics", []):
            for metric in sm.get("metrics", []):
                name = metric.get("name")
                names.add(name)
                if name == TOKEN_METRIC:
                    for dp in _datapoints(metric):
                        c = _common(res, dp)
                        val = dp.get("asInt", dp.get("asDouble", 0))
                        ok = store.insert_datapoint(
                            session_id=c["session_id"], repo=c["repo"],
                            repo_raw=c["repo_raw"], user_email=c["user_email"],
                            user_id=c["user_id"], org_id=c["org_id"],
                            model=c["model"], token_type=c["type"],
                            query_source=c["query_source"], tokens=int(val or 0),
                            time_unix_nano=c["time_unix_nano"])
                        tok_ins += 1 if ok else 0
                        tok_dup += 0 if ok else 1
                elif name == COST_METRIC:
                    for dp in _datapoints(metric):
                        c = _common(res, dp)
                        val = dp.get("asDouble", dp.get("asInt", 0))
                        ok = store.insert_cost_datapoint(
                            session_id=c["session_id"], repo=c["repo"],
                            repo_raw=c["repo_raw"], user_email=c["user_email"],
                            user_id=c["user_id"], org_id=c["org_id"],
                            model=c["model"], query_source=c["query_source"],
                            cost_usd=float(val or 0),
                            time_unix_nano=c["time_unix_nano"])
                        cost_ins += 1 if ok else 0
                        cost_dup += 0 if ok else 1
    store.commit()
    return {"inserted": tok_ins + cost_ins, "token_inserted": tok_ins,
            "cost_inserted": cost_ins, "duplicate": tok_dup + cost_dup,
            "metrics_seen": sorted(n for n in names if n)}


def ingest_session_repo_payload(payload: dict, store: OtelStore) -> dict:
    """Record one session->repo timeline entry, as POSTed by the CwdChanged hook
    (deploy/claude-repo-tag.py). See billing.otel.attribute for how it's joined
    back onto the usage datapoints at billing time."""
    session_id = (payload.get("session_id") or "").strip()
    ts = (payload.get("ts") or "").strip()
    if not session_id or not ts:
        raise ValueError("session_id and ts are required")
    repo_raw = payload.get("repo_raw") or ""
    inserted = store.insert_session_repo(
        session_id=session_id, ts=ts, seq=payload.get("seq") or 0,
        repo=normalize_remote(repo_raw), repo_raw=repo_raw,
        cwd=payload.get("cwd") or "", event=payload.get("event") or "")
    store.commit()
    return {"inserted": 1 if inserted else 0,
            "duplicate": 0 if inserted else 1,
            "repo": normalize_remote(repo_raw)}


#: Data-shape exceptions caught PER RECORD around both map_record and the
#: store inserts. This is deliberately broader than ValueError alone.
#:
#: `transcript._validate_record` only type-checks 5 of the 15 payload
#: fields (`ts` and the four token-count fields) -- `session_id`,
#: `request_id`, `model`, `repo_raw`, `user_email`, `user_id`, and `org_id`
#: are checked for TRUTHINESS only, never TYPE. A client that sends
#: `"session_id": ["x"]` or `"model": 123` or `"user_email": {"a": 1}`
#: passes validate_batch and then raises downstream of it -- reproduced,
#: per field:
#:     session_id=["x"]   -> sqlite3.ProgrammingError (unhashable/unbindable
#:                            parameter type)
#:     model=123           -> TypeError (RatingService._base does
#:                            `key in (model or "")`, which raises when
#:                            `model or ""` evaluates to the truthy int 123)
#:     repo_raw=123         -> AttributeError (normalize_remote calls
#:                            .strip()/.lower() on what it assumes is a str)
#:     user_email={"a": 1} -> sqlite3.ProgrammingError (same unbindable
#:                            parameter class as session_id)
#: None of these is a ValueError, so a catch typed to ValueError alone lets
#: all four escape -- past this loop AND past do_POST's
#: `except (ValueError, KeyError)` -- leaving the client with a dropped
#: connection and no HTTP response at all, not even a 400. Task 06 then
#: retries a deterministically-failing batch, exhausts its retry bound, and
#: discards every valid billable record behind the one bad one -- the exact
#: batch-poisoning path per-record rejection exists to prevent, just
#: reached via a different exception type than task 02 anticipated. This is
#: the third time in this goal "upstream validation is exhaustive" has been
#: assumed and been wrong; this catch is deliberately typed to the DATA-SHAPE
#: exception family observed from malformed client input, not to what
#: validate_batch happens to check today.
#:
#: `KeyError` has no client-triggerable reproduction, unlike every other
#: member of this tuple: `accepted` records are normalized by
#: `validate_batch`, and every key `map_record` reads off them is guaranteed
#: present by `transcript.REQUIRED_FIELDS`/`_normalize_record` -- no payload
#: shape a client can send provokes it today. It is kept anyway as
#: belt-and-braces against a RECEIVER-SIDE wiring bug: a future change to
#: `map_record`'s returned dict keys (e.g. renaming `"token_rows"`) would
#: raise `KeyError` for the row-shape lookups above, and containing it here
#: means that bug surfaces as every accepted record rejected with
#: `store_error:KeyError` and a 200 -- not a crash, but not silent either.
#: Task 07 adds the integration check that flags "accepted > 0 and every
#: accepted record rejected with a store_error: reason" as systemic rather
#: than ordinary client-data noise, which is what makes that visible.
#:
#: `sqlite3.OperationalError` (disk full, database locked, a genuinely
#: operational failure of the SQLite connection/disk, not of the DATA) is
#: DELIBERATELY EXCLUDED and allowed to keep propagating -- catching it here
#: and returning a cheerful 200 would mask a real outage as success. See
#: `ingest_transcript_usage_payload`'s outer try/except for how that escape
#: is still handled without leaving orphaned uncommitted rows behind.
_RECORD_DATA_ERRORS = (
    ValueError, TypeError, AttributeError, KeyError,
    sqlite3.InterfaceError, sqlite3.ProgrammingError,
)


def ingest_transcript_usage_payload(payload: Any, store: OtelStore) -> dict:
    """Validate + map + store one POST /v1/transcript-usage batch (desktop
    transcript usage, task 06's hook). Follows the ingest_*_payload pattern of
    ingest_metrics_payload / ingest_session_repo_payload above.

    `validate_batch` raises ValueError ONLY for an unusable envelope (not a
    list, or over MAX_BATCH_SIZE) -- that's allowed to propagate and lands on
    the existing 400 path in do_POST, same as the other endpoints. No store
    write has happened yet at that point, so nothing needs rolling back.

    Everything else is per-record: each accepted record is mapped and stored
    inside its OWN try/except catching `_RECORD_DATA_ERRORS` (see that
    tuple's docstring for the full reasoning and the four reproduced
    field-shape failures it exists to contain) so a raise from EITHER
    map_record (a malformed field validate_batch didn't type-check, or an
    edge case it didn't parse) OR the store's insert_datapoint /
    insert_cost_datapoint (the deliberate wiring-bug guard that raises when
    request_id is missing/present incorrectly for the given usage_source)
    becomes a per-record rejection instead of aborting the whole batch.

    Response contract -- the dict this returns becomes the 200 JSON body
    verbatim:
        {
          "inserted": <int>,        # token + cost rows actually inserted
          "token_inserted": <int>,
          "cost_inserted": <int>,
          "duplicate": <int>,       # rows that already existed (replay)
          "rejected": <int>,        # len(rejections)
          "rejections": [
            {"index": <int>, "request_id": <str|None>, "reason": <str>},
            ...
          ],
        }
    Every rejection entry ALWAYS carries an `index` -- the record's position
    in the original POSTed batch -- whether it was rejected by
    `validate_batch` (whose own indices are preserved verbatim) or by this
    function (whose indices are derived below from the batch positions
    `validate_batch` did NOT reject). `reason` is one of two families:
    `transcript.REJECTION_REASONS` (validate_batch's own strings, e.g.
    `invalid_ts`, `unknown_field:<name>`) or, for a rejection raised here,
    the stable `store_error:<ExceptionClassName>` prefix (e.g.
    `store_error:ProgrammingError`, `store_error:ValueError`). The two
    families are deliberately kept distinguishable by that prefix rather
    than folded into transcript.py's frozen tuple (out of this task's write
    fence) -- task 06/07 should match on the `store_error:` prefix, not
    enumerate every exception class name it might carry.

    An escaped raise -- of anything NOT in `_RECORD_DATA_ERRORS`, i.e.
    `sqlite3.OperationalError` or a genuinely unanticipated exception, from
    EITHER the per-record loop OR from `store.commit()` itself (both live
    inside the same guarded region below) -- reaches the outer try/except,
    which rolls back the connection before re-raising: `store.commit()` is
    only ever called once, at the very end of that region, on the single
    long-lived receiver connection, so any record processed earlier in THIS
    batch is still sitting uncommitted at that point -- whether the escape
    came from mid-loop or from the commit call that was meant to durably
    close the batch out. Without the rollback, those rows would survive on
    the connection and get silently committed as a side effect of the NEXT
    unrelated request's `store.commit()` -- the receiver's persisted state
    would then never match any response it had sent for either request.
    Rolling back discards the whole not-yet-committed batch (not just the
    record that raised) -- that's the coherent-failure behavior we want: a
    loud failure that leaves clean state, not one whose writes land later
    unannounced. `commit()` is still called exactly once per request either
    way -- this only changes what happens when that one call fails.
    """
    accepted, rejected = validate_batch(payload)

    # validate_batch preserves accepted's relative order and each rejected
    # entry's own `index`; the complement of the rejected indices, in order,
    # is exactly the original batch position of each accepted record -- so
    # every rejection this function adds below carries a real index, never
    # None, matching validate_batch's own always-defined-index contract.
    rejected_indices = {r["index"] for r in rejected}
    accepted_indices = [i for i in range(len(payload)) if i not in rejected_indices]

    rating = RatingService()
    tok_ins = tok_dup = cost_ins = cost_dup = 0
    try:
        for index, record in zip(accepted_indices, accepted):
            request_id = record.get("request_id")
            if not isinstance(request_id, str):
                request_id = None
            try:
                mapped = map_record(record, rating)
                for row in mapped["token_rows"]:
                    ok = store.insert_datapoint(**row)
                    tok_ins += 1 if ok else 0
                    tok_dup += 0 if ok else 1
                ok = store.insert_cost_datapoint(**mapped["cost_row"])
                cost_ins += 1 if ok else 0
                cost_dup += 0 if ok else 1
            except _RECORD_DATA_ERRORS as e:
                rejected.append({"index": index, "request_id": request_id,
                                  "reason": f"store_error:{e.__class__.__name__}"})

        # commit() itself lives INSIDE this guarded region, not after it: a
        # commit-time failure (sqlite3.OperationalError -- "database is
        # locked", "disk I/O error", both ordinary conditions on a
        # single-host SQLite deployment) is exactly as capable of leaving
        # this batch's writes sitting uncommitted as a mid-loop failure is,
        # and would otherwise escape to do_POST uncaught (no HTTP response)
        # with those rows still staged for a LATER, unrelated request's
        # commit() to silently pick up -- the same orphan-commit-by-side-
        # effect defect the except block below exists to close, just
        # reachable one statement later than the loop it originally guarded.
        store.commit()
    except Exception:
        # Something NOT in _RECORD_DATA_ERRORS escaped (e.g.
        # sqlite3.OperationalError, from either the loop or commit() above)
        # -- leave the connection clean rather than let earlier-in-this-
        # batch writes sit uncommitted for the NEXT request's commit() to
        # silently pick up. Then re-raise: this is a genuine operational
        # failure, not something to mask as a 200.
        store.db.rollback()
        raise

    return {
        "inserted": tok_ins + cost_ins,
        "token_inserted": tok_ins,
        "cost_inserted": cost_ins,
        "duplicate": tok_dup + cost_dup,
        "rejected": len(rejected),
        "rejections": rejected,
    }


class Handler(BaseHTTPRequestHandler):
    store: OtelStore = None  # set by serve()

    def log_message(self, *args):  # quieter
        pass

    def _ok(self, body: bytes = b"{}"):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        """True if auth is disabled, or the request presents the right token.
        Compared in constant time so a wrong token leaks nothing via timing."""
        if not AUTH_TOKEN:
            return True
        presented = _presented_token(self.headers)
        return bool(presented) and hmac.compare_digest(presented, AUTH_TOKEN)

    def _unauthorized(self):
        body = b'{"error":"unauthorized"}'
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("WWW-Authenticate", "Bearer")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        # Reject before reading/parsing the body: an unauthenticated caller
        # never reaches the store, and we don't spend work on junk traffic.
        if not self._authorized():
            _log(f"401 POST {self.path} (missing/invalid token)")
            self._unauthorized()
            return
        raw = _read_body(self)
        path = self.path.rstrip("/")
        ctype = self.headers.get("Content-Type", "?")
        te = self.headers.get("Transfer-Encoding", "-")
        ce = self.headers.get("Content-Encoding", "-")
        _log(f"POST {self.path} bytes={len(raw)} content-type={ctype} te={te} ce={ce}")
        if path.endswith("/v1/metrics"):
            try:
                result = ingest_metrics_payload(json.loads(raw or b"{}"), self.store)
                msg = (f"/v1/metrics tok+={result['token_inserted']} "
                       f"cost+={result['cost_inserted']} dup={result['duplicate']} "
                       f"metrics_seen={result['metrics_seen']}")
                print(f"[receiver] {msg}")
                _log(msg)
            except (ValueError, KeyError) as e:
                print(f"[receiver] bad metrics payload: {e}")
                _log(f"BAD metrics payload ({ctype} te={te} ce={ce}): {e}  first120={raw[:120]!r}")
                self.send_response(400)
                self.end_headers()
                return
        elif path.endswith("/v1/session-repo"):
            try:
                result = ingest_session_repo_payload(json.loads(raw or b"{}"), self.store)
                msg = (f"/v1/session-repo repo={result['repo']} "
                       f"new={result['inserted']} dup={result['duplicate']}")
                print(f"[receiver] {msg}")
                _log(msg)
            except (ValueError, KeyError) as e:
                print(f"[receiver] bad session-repo payload: {e}")
                _log(f"BAD session-repo payload: {e}  first120={raw[:120]!r}")
                self.send_response(400)
                self.end_headers()
                return
        elif path.endswith("/v1/transcript-usage"):
            try:
                result = ingest_transcript_usage_payload(json.loads(raw or b"[]"), self.store)
                msg = (f"/v1/transcript-usage tok+={result['token_inserted']} "
                       f"cost+={result['cost_inserted']} dup={result['duplicate']} "
                       f"rejected={result['rejected']}")
                print(f"[receiver] {msg}")
                _log(msg)
            except (ValueError, KeyError) as e:
                # DELIBERATE DIVERGENCE from the /v1/metrics and /v1/session-repo
                # log lines above: those echo `first120={raw[:120]!r}`, which on
                # this endpoint would write conversation-adjacent transcript
                # content into receiver.log, contrary to the Phase 1 privacy
                # decision (this payload can carry no message content by
                # schema, but the raw bytes on a malformed/oversized envelope
                # are still untrusted and unparsed). Log only the error and
                # counts/identifiers -- never raw request bytes. Do not
                # "restore consistency" with the other endpoints' format.
                print(f"[receiver] bad transcript-usage payload: {e}")
                _log(f"BAD transcript-usage payload ({ctype} te={te} ce={ce}) "
                     f"bytes={len(raw)}: {e}")
                self.send_response(400)
                self.end_headers()
                return
            self._ok(json.dumps({
                "inserted": result["inserted"],
                "token_inserted": result["token_inserted"],
                "cost_inserted": result["cost_inserted"],
                "duplicate": result["duplicate"],
                "rejected": result["rejected"],
                "rejections": result["rejections"],
            }).encode("utf-8"))
            return
        # /v1/logs, /v1/traces, anything else: just acknowledge
        self._ok()


def serve(host: str, port: int, db: str | None = None, require_auth: bool = False):
    if require_auth and not AUTH_TOKEN:
        raise SystemExit(
            "[receiver] --require-auth set but RECEIVER_AUTH_TOKEN is empty — refusing "
            "to start. Set the token, or drop --require-auth to run open.")
    Handler.store = OtelStore(db) if db else OtelStore()
    server = HTTPServer((host, port), Handler)
    auth_state = "ENABLED" if AUTH_TOKEN else "DISABLED"
    print(f"[receiver] listening on http://{host}:{port}  auth={auth_state}  "
          f"(POST /v1/metrics, /v1/session-repo, /v1/transcript-usage)")
    if not AUTH_TOKEN:
        print("[receiver] WARNING: RECEIVER_AUTH_TOKEN is unset — any client that can "
              "reach this port can write billing rows. Set it to require a token.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        Handler.store.close()


def main():
    ap = argparse.ArgumentParser(description="OTLP/JSON receiver for Claude Code.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4318)
    ap.add_argument("--db", default=None)
    ap.add_argument("--require-auth", action="store_true",
                    help="refuse to start unless RECEIVER_AUTH_TOKEN is set")
    args = ap.parse_args()
    serve(args.host, args.port, args.db, require_auth=args.require_auth)


if __name__ == "__main__":
    main()
