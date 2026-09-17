#!/usr/bin/env python3
"""Claude Code hook: ship desktop usage metadata from local transcripts to
the billing receiver.

Registered on `SessionEnd` (see managed-settings.json). Claude Code passes a
JSON object on stdin carrying `session_id`, `transcript_path`, and
`hook_event_name`. Unlike `claude-repo-tag.py` (one small POST per hook
firing), this hook does real work: it walks the on-disk transcript tree,
collapses cumulative streaming rows to one record per API request, and POSTs
batches of the frozen wire payload (`billing/otel/transcript.py`) to
`POST /v1/transcript-usage`.

Why a full recursive sweep and not just `transcript_path`: `transcript_path`
names the session that is ending -- it is a PRIORITY HINT for which file to
look at first, never the complete set of files to parse and never a source
of directory structure. Subagent (sidechain) transcripts live one level
below their parent session's directory
(`<project_dir>/<sessionId>/subagents/agent-<agentId>.jsonl`), and every
crashed or force-quit desktop session -- one whose OWN `SessionEnd` never
fires -- leaves an unshipped transcript in some OTHER project directory
that only a later session's hook run can ever reach. A flat,
`transcript_path`-relative glob misses both shapes silently. See
`_goals/desktop-usage-capture/06-client-hook.md` for the measured cost of
getting this wrong (30% of spend, from missed sidechain files alone).

Why client-side collapse: rows sharing `(sessionId, requestId,
message.id)` are cumulative streaming snapshots of ONE API request --
input/cache counts hold constant while `output_tokens` grows across them,
and only the TERMINAL block (highest `apiBlockIndex`) carries the correct
total. Summing them over-bills; taking the first under-bills. `stop_reason`
is NOT a reliable selector (observed: multi-valued or absent across real
groups). See `_select_terminal_block` below.

DESIGN RULE -- inherited verbatim from `claude-repo-tag.py`, this hook must
never break a developer's session:
  * always exits 0. Never exit 2 (that would BLOCK the tool call).
  * short network timeout, failures swallowed.
  * a lost or delayed billing record degrades one interval's invoice; a
    blocked tool call breaks someone's work. The tradeoff is not close.

Retry policy (the permanent-stall trap, and its mirror-image data-loss
trap):
  * A transport failure (connection refused, DNS failure, timeout, TLS
    error -- no HTTP response at all) NEVER advances per-file state and
    NEVER counts against the envelope drop bound. The transcripts are
    durable on disk and this hook's state is a per-file WATERMARK, not a
    queue, so nothing is lost by trying again on the next hook run (the
    next `SessionEnd`, or the next sweep) -- that natural cadence IS the
    backoff; there is deliberately no in-process sleep-and-retry loop,
    because a hook that sleeps is a hook that can be seen to hang a
    session.
  * An envelope-level rejection -- HTTP 400, and ONLY 400; every other
    non-200 status (401/403/408/429/5xx/anything else) is treated as a
    transport failure, per the point above -- is a client/schema defect
    that will never self-heal by retrying. Each RECORD's own attempt count
    (not a hash of the whole batch, which changes as new candidates join
    an active machine's batch run over run) is retried up to
    `MAX_ENVELOPE_RETRIES` times *across* hook runs; once a given record's
    count is exhausted, that record alone is dropped, its state advances
    past it, and the drop is logged locally (session + batch size, never
    message content) -- so one poison record cannot block every later
    record forever, and does not take newer, still-retryable records down
    with it.
  * A 200 response is PERMANENT even when it carries per-record
    `rejections` -- state advances for every record in the batch,
    accepted or rejected, and rejections are logged locally. Retrying a
    200-with-rejections would just get the same rejections again.

State (a JSON watermark file, keyed by absolute transcript path, holding
per-file resolved-request-id sets plus a light "examined" marker so a
machine with a long transcript history isn't re-parsed on every
`SessionEnd`) lives under `CLAUDE_CONFIG_DIR` (default `~/.claude`),
never inside this repo.

    Receiver URL:    CLAUDE_BILLING_RECEIVER  (default http://127.0.0.1:4318)
    Auth token:      CLAUDE_BILLING_TOKEN
    Projects root:   $CLAUDE_CONFIG_DIR/projects  (CLAUDE_CONFIG_DIR default ~/.claude)
    Identity source: ~/.claude.json (oauthAccount.emailAddress/.accountUuid/
                     .organizationUuid) -- NEVER ~/.claude/.credentials.json.

Standalone and stdlib-only: this file is copied to developer machines and
CANNOT import anything from `billing/`. `MAX_BATCH_SIZE` below is therefore
a DUPLICATE of the frozen value in `billing/otel/transcript.py`, not an
import of it -- keep the two in sync by hand; a test in
`tests/test_transcript_hook.py` cross-checks them.

Claude Code does NOT pass `OTEL_*` environment variables to hook
subprocesses -- this file never reads them.

Entrypoints shipped: `claude-desktop`, `cli`, and `claude-vscode` -- matching
`billing/otel/transcript.py`'s `ALLOWED_ENTRYPOINTS` exactly (duplicated
below, not imported: this file cannot import `billing/`). `cli` and
`claude-vscode` sessions ALSO emit OTLP metrics via the exporter, so this
hook is a BACKFILL path for gaps in that OTLP capture (a crash, a
force-quit, or an exporter flush that never lands before the process dies)
-- not a duplicate of it. The receiver-side guards that make this safe
(`sessions_with_otlp_rows` exclusion, `BACKFILL_MIN_AGE_SECONDS`) live in
`billing/otel/receiver.py` / `transcript.py`; this file additionally
quarantines a `cli`/`claude-vscode` record client-side (see
`BACKFILL_MIN_AGE_SECONDS` below) before ever attempting to ship it.

One-time historical replay (2026-09-16): the first run of this version of
the hook -- detected by the absence of the `cli_backfill_replay_at` state
key -- clears every file's `resolved` list and `examined_mtime`, then
performs an ordinary scan/ship pass so that previously-unshippable
`cli`/`claude-vscode` history (discarded forever by every earlier version of
this hook, which resolved those rows without ever shipping them) becomes
eligible instead of only sessions from here forward. It deliberately does
NOT touch the `install_ts` watermark: `install_ts` is set to the real
install time on a machine's first-ever run, so every transcript written
after installation already passes the forward-only watermark check on its
own -- what actually blocked recovery was `resolved`/`examined_mtime`, not
the watermark. Resetting `install_ts` would add nothing to this goal's
target and would instead make PRE-installation history shippable too (for
`claude-desktop` as well as CLI); that usage was never captured by OTLP
either, because the tool was not installed yet, so billing it now would
expand a client's invoices retroactively rather than recover lost
telemetry. Do not "fix" this by reintroducing a watermark reset -- it was
tried and deliberately removed for exactly this reason.
This is a STATE RESET, not a second code path -- it flows through the exact
same `_build_candidates` / shipping loop as any other run, and is subject to
the same quarantine, entrypoint filter, and install watermark. It runs at
most once per machine (the flag, once written, is never cleared by this
code -- deleting it by hand is the intentional escape hatch). Expect
`reconcile --detail`'s `DEDUPE DROPS` section to show a one-day cliff around
2026-09-16 on machines that pick up this version: the replay re-POSTs
already-known `claude-desktop`
records too, and the store's `INSERT OR IGNORE` correctly no-ops them --
that is the replay working as designed, not a `dp_key` collision.
"""

from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

RECEIVER = os.environ.get("CLAUDE_BILLING_RECEIVER", "http://127.0.0.1:4318")
ENDPOINT = "/v1/transcript-usage"


def _parse_timeout(raw: str | None) -> float:
    """A garbage/empty CLAUDE_BILLING_TIMEOUT must never crash the module at
    import time -- an MDM profile writing an empty value, or a shell
    exporting an unset variable, are both realistic. Falls back to 2.0."""
    try:
        return float(raw) if raw else 2.0
    except (TypeError, ValueError):
        return 2.0


TIMEOUT = _parse_timeout(os.environ.get("CLAUDE_BILLING_TIMEOUT"))
TOKEN = os.environ.get("CLAUDE_BILLING_TOKEN", "").strip()

#: DUPLICATE of billing/otel/transcript.py's MAX_BATCH_SIZE -- this file
#: cannot import billing/. Keep in sync by hand; cross-checked by test.
MAX_BATCH_SIZE = 500

#: The entrypoints this hook ships. DUPLICATE of billing/otel/transcript.py's
#: ALLOWED_ENTRYPOINTS -- this file cannot import billing/, keep the two
#: values in sync by hand. CLI and VS Code do NOT already bill by themselves
#: -- their OTLP exporter can miss a session entirely (crash, force-quit, a
#: shutdown flush that never lands); this hook is the backfill path for
#: exactly that gap. The receiver's own guards (session-already-has-OTLP-rows
#: exclusion, and the age quarantine below) are what prevent double-billing,
#: not this filter.
ENTRYPOINT = frozenset({"claude-desktop", "cli", "claude-vscode"})

#: DUPLICATE of billing/otel/transcript.py's DESKTOP_ENTRYPOINT. The desktop
#: app has no OTLP exporter, so it is exempt from the age quarantine below --
#: quarantining it would only delay/regress capture that carries no
#: double-billing risk in the first place.
DESKTOP_ENTRYPOINT = "claude-desktop"

#: How old (in seconds) a cli/claude-vscode record's terminal-row timestamp
#: must be before this hook will attempt to ship it. Deliberately TWICE
#: billing/otel/transcript.py's server-side BACKFILL_MIN_AGE_SECONDS (900s)
#: -- duplicated, not imported. A record that clears this looser client-side
#: gate but still fails the server's tighter 900s check (clock skew between
#: machines, or latency between candidate-building here and the POST landing
#: on the receiver) is PERMANENTLY BURNED: the resolve-on-200 path in run()
#: marks every record in an HTTP-200 chunk resolved regardless of its own
#: per-record rejection. A client window strictly larger than the server's
#: makes that boundary unreachable in practice -- belt and braces, in the
#: safe direction. Does NOT apply to claude-desktop (see DESKTOP_ENTRYPOINT).
BACKFILL_MIN_AGE_SECONDS = 1800

#: Observed real streaming window for a cumulative block group: ~6 seconds
#: (21:19:53.999 -> 21:20:00.187). 30s is a wide safety margin -- long
#: enough that a genuinely in-flight group is never mistaken for idle, far
#: shorter than any realistic gap between a live session's writes.
IDLE_THRESHOLD_SECONDS = 30.0

#: An envelope-level (400) rejection is retried across hook runs up to this
#: many times before the batch is dropped and state advances past it. Does
#: NOT apply to a transport failure -- see module docstring.
MAX_ENVELOPE_RETRIES = 5


def _config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"))


def _projects_root(config_dir: Path) -> Path:
    return config_dir / "projects"


def _state_path(config_dir: Path) -> Path:
    return config_dir / "billing-hook-state.json"


def _log_path(config_dir: Path) -> Path:
    return config_dir / "billing-hook.log"


def _claude_json_path() -> Path:
    # ~/.claude.json is a fixed, home-relative location on every real Claude
    # Code install -- independent of CLAUDE_CONFIG_DIR, which only affects
    # ~/.claude's own contents (projects/, settings, this hook's state).
    return Path(os.path.expanduser("~/.claude.json"))


# ---------------------------------------------------------------------------
# Identity -- ~/.claude.json ONLY. Never ~/.claude/.credentials.json (that
# file holds live OAuth tokens, not the profile fields this hook needs).
# ---------------------------------------------------------------------------

def load_identity(claude_json_path: Path) -> dict:
    """Best-effort identity. Missing file, unreadable file, malformed JSON,
    or a non-dict `oauthAccount` all degrade to empty strings -- the usage
    record still ships; it just carries no identity."""
    try:
        data = json.loads(claude_json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"user_email": "", "user_id": "", "org_id": ""}
    if not isinstance(data, dict):
        return {"user_email": "", "user_id": "", "org_id": ""}
    oauth = data.get("oauthAccount")
    if not isinstance(oauth, dict):
        oauth = {}
    return {
        "user_email": oauth.get("emailAddress") or "",
        "user_id": oauth.get("accountUuid") or "",
        "org_id": oauth.get("organizationUuid") or "",
    }


# ---------------------------------------------------------------------------
# Git remote resolution -- same shape as claude-repo-tag.py, cached per
# distinct cwd so a 215-record transcript spawns at most a handful of `git`
# subprocesses, not 215.
# ---------------------------------------------------------------------------

def git_remote(cwd: str, cache: dict) -> str:
    if cwd in cache:
        return cache[cwd]
    try:
        out = subprocess.run(
            ["git", "-C", cwd, "config", "--get", "remote.origin.url"],
            capture_output=True, text=True, timeout=TIMEOUT, check=False)
        remote = out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError, ValueError):
        remote = ""
    cache[cwd] = remote
    return remote


# ---------------------------------------------------------------------------
# Timestamp parsing -- same round trip as transcript.py's _ts_to_unix_nano,
# duplicated (stdlib-only, no import) so install-watermark and sort-order
# comparisons are numeric, never a fragile lexicographic string compare
# (which breaks across differing millisecond precision).
# ---------------------------------------------------------------------------

def _parse_ts(ts) -> float | None:
    if not isinstance(ts, str):
        return None
    try:
        s = ts.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, OverflowError, OSError):
        return None


# ---------------------------------------------------------------------------
# Transcript enumeration -- RECURSIVE from the projects root. Never derive a
# directory from transcript_path and glob inside it.
# ---------------------------------------------------------------------------

def find_transcript_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    try:
        return sorted(p for p in root.rglob("*.jsonl") if p.is_file())
    except OSError:
        return []


def _same_file(hint: str, path: Path) -> bool:
    try:
        return Path(hint).resolve() == path.resolve()
    except OSError:
        return str(Path(hint)) == str(path)


def read_jsonl_rows(path: Path) -> list[dict]:
    """Every well-formed JSON object line in `path`. A corrupt or
    partially-written line (transcripts are appended live; the final line
    may be mid-write) is skipped, not fatal."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _usage_rows(rows: list[dict]) -> list[dict]:
    """Rows that carry real usage data -- filters out non-assistant rows,
    rows with no message/usage block, and rows missing an identifier a
    group key needs."""
    out = []
    for row in rows:
        message = row.get("message")
        if not isinstance(message, dict):
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        if not row.get("sessionId") or not row.get("requestId") or not message.get("id"):
            continue
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# Cumulative-block collapse -- the single most important correctness rule.
# ---------------------------------------------------------------------------

def _group_key(row: dict) -> tuple:
    return (row["sessionId"], row["requestId"], row["message"]["id"])


def build_groups(rows: list[dict]):
    """Returns (order, groups): `order` is group keys in first-appearance
    order; `groups[key]` is a list of (ordinal, row) tuples in file order."""
    groups: dict[tuple, list] = {}
    order: list = []
    for ordinal, row in enumerate(rows):
        key = _group_key(row)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((ordinal, row))
    return order, groups


def _block_index(row: dict):
    v = row.get("apiBlockIndex")
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def select_terminal_block(entries: list) -> dict:
    """The terminal block of one (sessionId, requestId, message.id) group.

    Selector: highest `apiBlockIndex`; a row with NO `apiBlockIndex` is
    treated as lower than every row that HAS one (never a raw None/int
    comparison, which raises TypeError); ties (including "all absent")
    break by file order, last wins. Deliberately NOT `stop_reason` --
    measured across real transcripts, `stop_reason` is non-null on more
    than one row for a large fraction of groups and null on every row for
    others; it is not a usable selector.
    """
    def sort_key(item):
        ordinal, row = item
        bi = _block_index(row)
        return (bi is not None, bi if bi is not None else -1, ordinal)
    return max(entries, key=sort_key)[1]


def trailing_group_key(order: list, groups: dict):
    """The group whose last-appearing row sits latest in the file -- i.e.
    the file's trailing (possibly still in-flight) request group. All other
    groups are complete by construction (a later group exists after them)."""
    if not order:
        return None
    return max(order, key=lambda k: max(o for o, _ in groups[k]))


# ---------------------------------------------------------------------------
# Wire payload -- exactly the 14 fields frozen in billing/otel/transcript.py.
# Deliberately never includes `cwd` (a file path -- excluded by the opt-in
# consent notice) and never touches message text/tool output/file contents.
# ---------------------------------------------------------------------------

def _num(v) -> int:
    if isinstance(v, bool):
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    return 0


def build_payload_record(terminal_row: dict, *, is_sidechain: bool, identity: dict,
                          remote_cache: dict) -> dict:
    cwd = terminal_row.get("cwd") or ""
    repo_raw = git_remote(cwd, remote_cache) if cwd else ""
    usage = terminal_row["message"]["usage"]
    return {
        "session_id": terminal_row["sessionId"],
        "ts": terminal_row.get("timestamp"),
        "request_id": terminal_row["requestId"],
        "model": terminal_row["message"].get("model") or "",
        "input_tokens": _num(usage.get("input_tokens")),
        "output_tokens": _num(usage.get("output_tokens")),
        "cache_read_input_tokens": _num(usage.get("cache_read_input_tokens")),
        "cache_creation_input_tokens": _num(usage.get("cache_creation_input_tokens")),
        "repo_raw": repo_raw,
        # Carried from the row, VERBATIM -- never stamped/relabeled. The
        # caller has already validated this value is a member of the
        # ENTRYPOINT set before reaching here, so this simply reads it back
        # off the row rather than re-deriving it, meaning the entrypoint
        # filter and the payload's claimed entrypoint can never drift apart
        # under a future refactor. Do NOT reintroduce an `or ENTRYPOINT`
        # fallback here -- ENTRYPOINT is now a SET (not a single value), and
        # any fallback would relabel a cli/claude-vscode row as
        # claude-desktop, exactly the mislabeling task 03's preserve-
        # entrypoint fix exists to prevent.
        "entrypoint": terminal_row.get("entrypoint"),
        "query_source": "subagent" if is_sidechain else "main",
        "user_email": identity.get("user_email", ""),
        "user_id": identity.get("user_id", ""),
        "org_id": identity.get("org_id", ""),
    }


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def _load_state(state_path: Path) -> dict:
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


#: `tmp.replace(state_path)` below can raise a TRANSIENT PermissionError on
#: Windows: a freshly-written file is occasionally held open for a few
#: milliseconds by another process (most commonly real-time antivirus
#: scanning it) at the exact moment of rename. Observed directly: reproduced
#: under a tight write-every-run loop with `PermissionError(13, 'Access is
#: denied')` on `Path.replace`. A handful of short retries turns this from an
#: intermittently LOST state-persist (this run's progress silently not
#: saved -- tolerable per the "never fatal" rule, but avoidable) into a
#: successful save almost every time, without weakening that rule at all:
#: if every attempt still fails, the caller's own `except OSError` still
#: swallows it exactly as before.
_REPLACE_RETRY_ATTEMPTS = 5
_REPLACE_RETRY_DELAY_SECONDS = 0.02


def _replace_with_retry(tmp: Path, dest: Path) -> None:
    last_err: OSError | None = None
    for attempt in range(_REPLACE_RETRY_ATTEMPTS):
        try:
            tmp.replace(dest)
            return
        except PermissionError as e:
            last_err = e
            if attempt < _REPLACE_RETRY_ATTEMPTS - 1:
                time.sleep(_REPLACE_RETRY_DELAY_SECONDS)
    if last_err is not None:
        raise last_err


def _save_state(state_path: Path, state: dict) -> None:
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = state_path.with_name(state_path.name + ".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        _replace_with_retry(tmp, state_path)
    except OSError:
        pass  # worst case: some work is redone next run -- never fatal


def _mark_resolved(state: dict, file_key: str, request_id: str) -> None:
    entry = state["files"].setdefault(file_key, {"resolved": [], "examined_mtime": None})
    resolved = entry.setdefault("resolved", [])
    if request_id not in resolved:
        resolved.append(request_id)


def _append_log(log_path: Path | None, msg: str) -> None:
    if log_path is None:
        return
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")
    except OSError:
        pass


def _record_retry_key(file_key: str, request_id: str) -> str:
    """A STABLE identity for one record's envelope-retry counter -- stable
    across runs even though batch COMPOSITION is not.

    Earlier this counted whole-batch attempts keyed by a hash of every
    request_id in the batch. On an active machine new candidates join the
    batch on every run (a new group ships, an idle threshold elapses,
    etc.), so that hash changes run over run, the counter for the still-
    poisoned record keeps resetting to 1, and it NEVER crosses
    MAX_ENVELOPE_RETRIES -- the exact permanent stall the bound exists to
    prevent. Keying per-record instead means each record's own attempt
    count is independent of whatever else happens to ride alongside it in
    any given batch.
    """
    return f"{file_key}::{request_id}"


# ---------------------------------------------------------------------------
# Candidate building -- one pass over every transcript file. Resolves
# (marks done, without shipping) whatever can be resolved with no network
# call: groups with an entrypoint outside ENTRYPOINT (or missing/empty/
# non-string), groups predating the install watermark, and groups with an
# unparseable ts -- all permanently unshippable. Everything else either ships
# this run (non-trailing, non-quarantined groups, and trailing groups that
# are complete/idle) or is WITHHELD -- a temporary state that leaves
# `examined_mtime` unadvanced and skips `_mark_resolved`, so the group stays
# eligible on a later run: an in-flight trailing group (any entrypoint), or a
# cli/claude-vscode group younger than BACKFILL_MIN_AGE_SECONDS.
# ---------------------------------------------------------------------------


def _within_backfill_quarantine_window(ts_epoch: float, now_epoch: float) -> bool:
    """True if a cli/claude-vscode record's terminal-row timestamp is not
    yet BACKFILL_MIN_AGE_SECONDS old.

    Takes `now_epoch` as a parameter and never calls `datetime.now()` /
    `time.time()` itself -- `run()` already threads a single `now` through
    to `now_epoch`, so a test (or a future caller) can freeze/advance the
    clock across two `run()` calls and this comparison responds exactly as
    a real clock tick would, with no inline clock read at the comparison
    site to work around.
    """
    return (now_epoch - ts_epoch) < BACKFILL_MIN_AGE_SECONDS


def _build_candidates(files: list[Path], *, state: dict, install_epoch: float,
                       transcript_path_hint: str | None, hook_event_name: str | None,
                       now_epoch: float, identity: dict, remote_cache: dict,
                       idle_threshold_seconds: float):
    candidates = []  # list of (record, file_key, request_id, ts_epoch)
    file_meta = {}
    own_session_end = hook_event_name == "SessionEnd"

    for path in files:
        file_key = str(path)
        try:
            current_mtime = path.stat().st_mtime
        except OSError:
            continue

        entry = state["files"].setdefault(file_key, {"resolved": [], "examined_mtime": None})
        resolved = set(entry.get("resolved", []))
        examined_mtime = entry.get("examined_mtime")

        if examined_mtime is not None and examined_mtime == current_mtime:
            file_meta[file_key] = {"withheld": False, "mtime": current_mtime, "pending": set()}
            continue

        rows = read_jsonl_rows(path)
        usage_rows = _usage_rows(rows)
        order, groups = build_groups(usage_rows)
        trailing_key = trailing_group_key(order, groups)
        is_own_trailing_target = (
            own_session_end
            and transcript_path_hint is not None
            and _same_file(transcript_path_hint, path)
        )
        idle_elapsed = (now_epoch - current_mtime) > idle_threshold_seconds

        withheld = False
        pending: set = set()

        for key in order:
            session_id, request_id, _message_id = key
            if request_id in resolved:
                continue
            entries = groups[key]
            terminal = select_terminal_block(entries)
            is_sidechain = any(bool(r.get("isSidechain")) for _, r in entries)
            entrypoint = terminal.get("entrypoint")
            ts_epoch = _parse_ts(terminal.get("timestamp"))

            if not isinstance(entrypoint, str) or entrypoint not in ENTRYPOINT:
                # Missing, empty, non-string, or outside the allowed set
                # (e.g. "claude-web") -- permanently unshippable either way,
                # so mark resolved now rather than re-parsing this row on
                # every future run forever.
                _mark_resolved(state, file_key, request_id)
                continue
            if ts_epoch is None:
                _mark_resolved(state, file_key, request_id)  # malformed, unshippable
                continue
            if ts_epoch < install_epoch:
                _mark_resolved(state, file_key, request_id)  # forward-only watermark
                continue

            if entrypoint != DESKTOP_ENTRYPOINT and _within_backfill_quarantine_window(
                    ts_epoch, now_epoch):
                # cli/claude-vscode record younger than BACKFILL_MIN_AGE_SECONDS
                # -- the receiver's own OTLP-backfill exclusion check for this
                # session may not be meaningful yet (the exporter's shutdown
                # flush races this hook). WITHHELD, reusing the exact same
                # mechanism as the trailing-group idle withhold below:
                # examined_mtime does not advance and _mark_resolved is not
                # called, so the group stays eligible on a later run instead
                # of being skipped once and never revisited. claude-desktop
                # is exempt -- see DESKTOP_ENTRYPOINT.
                withheld = True
                continue

            is_trailing = key == trailing_key
            if is_trailing and not (is_own_trailing_target or idle_elapsed):
                withheld = True
                continue  # in-flight -- leave pending for a future run

            record = build_payload_record(
                terminal, is_sidechain=is_sidechain, identity=identity,
                remote_cache=remote_cache)
            candidates.append((record, file_key, request_id, ts_epoch))
            pending.add(request_id)

        file_meta[file_key] = {"withheld": withheld, "mtime": current_mtime, "pending": pending}

    return candidates, file_meta


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

def _default_post_batch(records: list[dict]):
    """POST one batch. Returns (outcome, status, body_dict) where outcome is:

      - 'ok'              HTTP 200.
      - 'envelope_reject' HTTP 400 ONLY -- the receiver's own contract
        (billing/otel/receiver.py) returns 400 for exactly one reason: the
        POSTed envelope itself is unusable (not a list, or over
        MAX_BATCH_SIZE). That is a genuine client/schema defect that will
        never self-heal by retrying, which is what the drop bound is for.
      - 'transport_fail'  everything else that is NOT a clean 200: no HTTP
        response at all (connection refused, DNS failure, timeout, TLS
        error, a malformed status line or an incomplete read), AND any
        other non-400 HTTP status (401/403 auth misconfiguration -- e.g. a
        mis-substituted REPLACE_WITH_FLEET_BILLING_TOKEN placeholder --
        408/429, or a 5xx server-side failure). None of these are the
        client poisoning its own request; every one of them "costs nothing
        to retry, and self-heals the moment the receiver/auth is fixed" --
        the exact reasoning that exempts a transport failure from the drop
        bound applies verbatim, so they must NEVER consume it. Getting this
        wrong on 401 in particular is catastrophic: six runs against a
        misconfigured token, followed by the operator fixing it, must still
        recover every withheld record -- treating 401 as poison would
        instead drop them permanently once the bound is hit.
    """
    body = json.dumps(records).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["X-Billing-Token"] = TOKEN
    req = urllib.request.Request(
        RECEIVER.rstrip("/") + ENDPOINT, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            status = resp.getcode()
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            raw = e.read()
        except Exception:
            raw = b"{}"
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException):
        # No HTTP response at all: connection refused, DNS failure, timeout,
        # TLS error, or a transport-level protocol error (BadStatusLine,
        # IncompleteRead, etc. -- http.client.HTTPException is neither a
        # ValueError nor a URLError and would otherwise escape uncaught).
        return "transport_fail", 0, {}

    if status == 200:
        try:
            parsed = json.loads(raw or b"{}")
            if not isinstance(parsed, dict):
                parsed = {}
        except ValueError:
            parsed = {}
        return "ok", status, parsed

    if status == 400:
        return "envelope_reject", status, {}

    # Any other non-200 status (401/403/408/429/5xx/anything unexpected):
    # retry-forever, like a transport failure. See docstring above.
    return "transport_fail", status, {}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run(*, projects_root: Path, state_path: Path, claude_json_path: Path,
        transcript_path_hint: str | None, hook_event_name: str | None,
        now: datetime | None = None, post_batch=_default_post_batch,
        log_path: Path | None = None,
        idle_threshold_seconds: float = IDLE_THRESHOLD_SECONDS) -> None:
    now = now or datetime.now(timezone.utc)
    now_epoch = now.timestamp()

    state = _load_state(state_path)
    state.setdefault("files", {})
    state.setdefault("envelope_retries", {})
    state.setdefault("drops", [])
    if "install_ts" not in state:
        state["install_ts"] = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    # --- one-time historical replay (Part C) ---------------------------
    # Gated on a single flag: while it is absent, this is the first run of
    # this hook version on this machine. Perform the two-part reset -- clear
    # every file's `resolved` list and clear every `examined_mtime` (NOT
    # optional: :509-511's mtime-unchanged short-circuit fires before
    # `resolved` is ever consulted, so skipping this makes the whole replay
    # a no-op against any file whose mtime hasn't changed since it was last
    # examined -- true of every historical transcript, since history is not
    # being appended to). This happens entirely in-memory here; it is
    # written to disk (atomically, together with the flag) below, BEFORE the
    # first POST of this pass, so a crash mid-replay cannot cause a second
    # replay -- see the write further down.
    #
    # Deliberately does NOT reset `install_ts`/`install_epoch` below. This
    # was tried and removed: `install_ts` is set to the real install time on
    # a machine's first-ever run, so every transcript written AFTER
    # installation already passes the :543-545 forward-only watermark check
    # on its own -- `resolved`/`examined_mtime` were what actually blocked
    # recovery, not the watermark. Resetting the watermark would have added
    # nothing to this goal's target (post-install sessions whose OTLP export
    # never flushed) and would instead have made PRE-installation history
    # shippable too, for claude-desktop as well as CLI -- usage that was
    # never captured by OTLP either, because the tool wasn't installed yet,
    # so billing it now would expand a client's invoices retroactively
    # rather than recover lost telemetry. Do not "fix" this by
    # reintroducing a watermark reset here.
    is_replay = "cli_backfill_replay_at" not in state
    if is_replay:
        for entry in state["files"].values():
            entry["resolved"] = []
            entry["examined_mtime"] = None

    install_epoch = _parse_ts(state["install_ts"]) or 0.0

    files = find_transcript_files(projects_root)
    if not files:
        _append_log(
            log_path,
            f"{now.isoformat()} WARNING zero transcript files found under "
            f"{projects_root} -- if Claude Code has run here before, this "
            f"likely means the projects root is wrong (e.g. CLAUDE_CONFIG_DIR "
            f"mismatch), not that there is no usage.",
        )
        if is_replay:
            state["cli_backfill_replay_intended"] = {
                "files_eligible": 0, "groups_eligible": 0, "records_to_ship": 0,
            }
            _append_log(
                log_path,
                f"{now.isoformat()} INFO cli-backfill replay: 0 files eligible, "
                f"0 groups eligible, 0 records to ship (no transcript files found)",
            )
            state["cli_backfill_replay_at"] = now.isoformat()
        state["cli_backfill_last_run"] = {
            "shipped": 0, "rejected_by_reason": {}, "deferred": 0,
            "replay_performed": is_replay,
        }
        _save_state(state_path, state)
        return

    # transcript_path is a PRIORITY HINT -- process it first. It never
    # changes the set of files walked or the directories searched.
    if transcript_path_hint:
        files = sorted(files, key=lambda p: (0 if _same_file(transcript_path_hint, p) else 1, str(p)))

    identity = load_identity(claude_json_path)
    remote_cache: dict = {}

    candidates, file_meta = _build_candidates(
        files, state=state, install_epoch=install_epoch,
        transcript_path_hint=transcript_path_hint, hook_event_name=hook_event_name,
        now_epoch=now_epoch, identity=identity, remote_cache=remote_cache,
        idle_threshold_seconds=idle_threshold_seconds)

    # Non-decreasing ts order globally, so a partial failure cannot strand
    # an earlier record behind a later confirmed one.
    candidates.sort(key=lambda c: c[3])

    pending_by_file = {fk: set(v["pending"]) for fk, v in file_meta.items()}

    if is_replay:
        # Log and persist the intended volume BEFORE the first POST of this
        # pass -- a replay that intends to ship zero records is then visible
        # immediately, at the moment it happens, and `state` (not stdout,
        # which nobody reads on a laptop) is what will actually be inspected
        # after the fact. One record ships per eligible group in this hook,
        # so groups_eligible and records_to_ship are numerically equal here,
        # but are reported separately since they answer different questions
        # (scope of the replay vs. what it will actually send).
        intended_volume = {
            "files_eligible": len(files),
            "groups_eligible": len(candidates),
            "records_to_ship": len(candidates),
        }
        state["cli_backfill_replay_intended"] = intended_volume
        _append_log(
            log_path,
            f"{now.isoformat()} INFO cli-backfill replay: "
            f"{intended_volume['files_eligible']} files eligible, "
            f"{intended_volume['groups_eligible']} groups eligible, "
            f"{intended_volume['records_to_ship']} records to ship",
        )
        # Write the flag now, atomically together with the resets already
        # made above (still in-memory until this save) and the intended-
        # volume numbers -- BEFORE the loop below issues its first POST.
        # This is what makes a crash mid-replay safe: the flag survives so a
        # later run does not replay a second time, and the resets survive
        # (this write is never rolled back) so whatever this run doesn't
        # finish shipping still ships on that later, ordinary run.
        state["cli_backfill_replay_at"] = now.isoformat()
        _save_state(state_path, state)

    shipped_count = 0    # records the server ACCEPTED -- not merely resolved
    deferred_count = 0   # too_recent: left pending, retried on a later run
    rejected_by_reason: dict[str, int] = {}

    idx = 0
    stop_due_to_transport = False
    while idx < len(candidates) and not stop_due_to_transport:
        chunk = candidates[idx: idx + MAX_BATCH_SIZE]
        idx += len(chunk)
        records = [c[0] for c in chunk]
        outcome, status, body = post_batch(records)

        if outcome == "ok":
            rejections = body.get("rejections") or []
            # `too_recent` is the ONE per-record rejection reason that is
            # NOT permanent -- it means the receiver's own quarantine
            # (BACKFILL_MIN_AGE_SECONDS server-side) still finds this record
            # too young, most likely clock skew or latency between
            # candidate-building here and the POST landing. Every other
            # reason (session_has_otlp, invalid_entrypoint, etc.) is a
            # permanent verdict and stays resolving, exactly as today.
            # Getting this backwards would let resolve-on-200 (below) burn a
            # too_recent record forever on its very first attempt.
            rejected_ids = {
                r.get("request_id") for r in rejections if isinstance(r, dict)
            }
            too_recent_ids = {
                r.get("request_id") for r in rejections
                if isinstance(r, dict) and r.get("reason") == "too_recent"
            }
            for _record, file_key, request_id, _ts in chunk:
                if request_id in too_recent_ids:
                    deferred_count += 1
                    continue  # non-resolving -- stays pending for a later run
                _mark_resolved(state, file_key, request_id)
                pending_by_file[file_key].discard(request_id)
                state["envelope_retries"].pop(_record_retry_key(file_key, request_id), None)
                # Resolution and counting are separate concerns: a permanently
                # rejected record is resolved (never retried) but was NOT
                # accepted, so it must not count as shipped. Otherwise a
                # replay that recovers nothing would report recovery.
                if request_id not in rejected_ids:
                    shipped_count += 1
            if rejections:
                for r in rejections:
                    if isinstance(r, dict):
                        reason = r.get("reason") or "unknown"
                        rejected_by_reason[reason] = rejected_by_reason.get(reason, 0) + 1
                state["drops"].append({
                    "ts": now.isoformat(),
                    "kind": "rejected_200",
                    "count": len(rejections),
                    "sessions": sorted({r["session_id"] for r, _, _, _ in chunk}),
                })
        elif outcome == "envelope_reject":
            # Per-RECORD attempt counts, not a whole-batch hash: batch
            # COMPOSITION changes run over run as new candidates join (a
            # freshly-idle group, a new SessionEnd), so a hash of the whole
            # batch would reset every time and the bound would never fire
            # on an active machine -- the permanent-stall trap this bound
            # exists to prevent. Each record's own count survives being
            # re-batched alongside different neighbours.
            dropped_this_batch = []
            for _record, file_key, request_id, _ts in chunk:
                retry_key = _record_retry_key(file_key, request_id)
                attempts = state["envelope_retries"].get(retry_key, 0) + 1
                state["envelope_retries"][retry_key] = attempts
                if attempts > MAX_ENVELOPE_RETRIES:
                    _mark_resolved(state, file_key, request_id)
                    pending_by_file[file_key].discard(request_id)
                    state["envelope_retries"].pop(retry_key, None)
                    dropped_this_batch.append(request_id)
                # else: leave pending/unresolved -- retried on a future run,
                # possibly in a differently-composed batch.
            if dropped_this_batch:
                state["drops"].append({
                    "ts": now.isoformat(),
                    "kind": "dropped_after_retries",
                    "status": status,
                    "batch_size": len(chunk),
                    "dropped_count": len(dropped_this_batch),
                    "sessions": sorted({r["session_id"] for r, _, _, _ in chunk}),
                })
        else:  # transport_fail -- never advances state, never drops, and
               # we stop for this run: the receiver is unreachable, no point
               # attempting further batches now.
            stop_due_to_transport = True

    for file_key, meta in file_meta.items():
        if meta["withheld"]:
            continue
        if pending_by_file.get(file_key):
            continue
        state["files"].setdefault(file_key, {"resolved": [], "examined_mtime": None})
        state["files"][file_key]["examined_mtime"] = meta["mtime"]

    # Recovery must be measurable (Part C): persisted into `state`, not only
    # ever visible via the injected post_batch's own call log, so the
    # outcome is inspectable after the fact on a real machine. The tallies
    # reconcile against the pre-POST intended volume for a run that reached
    # every batch:
    #   records_to_ship == shipped + sum(rejected_by_reason.values())
    #   deferred        == rejected_by_reason.get("too_recent", 0)
    # `rejected_by_reason` lists EVERY server rejection including too_recent
    # (Part C: the breakdown must show it); `deferred` calls out the
    # retryable subset separately so "permanently rejected" and "still
    # pending" are not read as the same thing. A transport_fail stops the
    # run early, so the remainder is simply absent from all tallies and
    # ships on a later run.
    state["cli_backfill_last_run"] = {
        "shipped": shipped_count,
        "rejected_by_reason": rejected_by_reason,
        "deferred": deferred_count,
        "replay_performed": is_replay,
    }

    _save_state(state_path, state)


def main() -> int:
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        raw = ""
    try:
        payload = json.loads(raw or "{}")
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    config_dir = _config_dir()
    try:
        run(
            projects_root=_projects_root(config_dir),
            state_path=_state_path(config_dir),
            claude_json_path=_claude_json_path(),
            transcript_path_hint=payload.get("transcript_path") or None,
            hook_event_name=payload.get("hook_event_name") or None,
            log_path=_log_path(config_dir),
        )
    except Exception:  # noqa: BLE001 - a telemetry hook must never fail loudly
        pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:      # noqa: BLE001
        sys.exit(0)
