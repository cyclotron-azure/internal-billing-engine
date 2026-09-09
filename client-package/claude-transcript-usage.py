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

#: The only entrypoint this hook ever ships. CLI and VS Code already bill
#: via OTLP; shipping them here would double-bill.
ENTRYPOINT = "claude-desktop"

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
        # Carried from the row, not stamped -- the caller has already
        # filtered to ENTRYPOINT before reaching here (this value will
        # always equal it today), but reading it back off the row means the
        # entrypoint filter and the payload's claimed entrypoint can never
        # drift apart under a future refactor -- a second, structural
        # defense on top of the filter itself.
        "entrypoint": terminal_row.get("entrypoint") or ENTRYPOINT,
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
# call: non-desktop groups, groups predating the install watermark, and
# groups with an unparseable ts. Everything else either ships this run
# (non-trailing groups, and trailing groups that are complete/idle) or is
# withheld (an in-flight trailing group).
# ---------------------------------------------------------------------------

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

            if entrypoint != ENTRYPOINT:
                _mark_resolved(state, file_key, request_id)
                continue
            if ts_epoch is None:
                _mark_resolved(state, file_key, request_id)  # malformed, unshippable
                continue
            if ts_epoch < install_epoch:
                _mark_resolved(state, file_key, request_id)  # forward-only watermark
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

    idx = 0
    stop_due_to_transport = False
    while idx < len(candidates) and not stop_due_to_transport:
        chunk = candidates[idx: idx + MAX_BATCH_SIZE]
        idx += len(chunk)
        records = [c[0] for c in chunk]
        outcome, status, body = post_batch(records)

        if outcome == "ok":
            for _record, file_key, request_id, _ts in chunk:
                _mark_resolved(state, file_key, request_id)
                pending_by_file[file_key].discard(request_id)
                state["envelope_retries"].pop(_record_retry_key(file_key, request_id), None)
            rejections = body.get("rejections") or []
            if rejections:
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
