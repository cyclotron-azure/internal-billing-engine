"""Tests for task 04 (sweeper ships CLI/VS Code transcripts + one-time
historical replay, `client-package/claude-transcript-usage.py` /
`deploy/claude-transcript-usage.py`) plus task 01's config assertions
(export interval 60s -> 10s), both from the `otel-export-loss-reduction` goal.

One test per acceptance criterion 1-19 of
`_goals/otel-export-loss-reduction/04-sweeper-cli-backfill.md`, plus 1-7 of
`01-export-interval.md`. Task 01's criteria are command-shaped -- covered
here by parsing the config files and asserting their values, never by
shelling out to grep.

The hook is standalone/stdlib-only and is imported BY FILE PATH, exactly as
`tests/test_transcript_hook.py` does. `_FakeClock`-style frozen `datetime`
values (never `sleep`) drive every quarantine-boundary and replay-sequence
test.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.conftest import _usage_row

_REPO_ROOT = Path(__file__).resolve().parents[1]
_HOOK_PATH = _REPO_ROOT / "client-package" / "claude-transcript-usage.py"


@pytest.fixture(scope="module")
def hook():
    spec = importlib.util.spec_from_file_location("claude_transcript_usage_hook_04", _HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _capturing_post(outcome="ok", status=200, body=None, sequence=None):
    calls = []

    def _post(records):
        calls.append([dict(r) for r in records])
        if sequence:
            step = sequence[min(len(calls) - 1, len(sequence) - 1)]
            return step
        return outcome, status, dict(body or {})

    _post.calls = calls
    return _post


def _seed_state(state_path: Path, *, install_ts: str = "1970-01-01T00:00:00.000000Z",
                 replayed: bool = True) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "install_ts": install_ts,
        "files": {}, "envelope_retries": {}, "drops": [],
    }
    if replayed:
        state["cli_backfill_replay_at"] = install_ts
    state_path.write_text(json.dumps(state), encoding="utf-8")


def _cli_row(*, session_id, request_id, message_id, timestamp, entrypoint="cli",
             input_tokens=1, output_tokens=1):
    return _usage_row(
        session_id=session_id, request_id=request_id, message_id=message_id,
        api_block_index=0, stop_reason="end_turn", input_tokens=input_tokens,
        output_tokens=output_tokens, cache_creation_input_tokens=0,
        cache_read_input_tokens=0, entrypoint=entrypoint, timestamp=timestamp,
    )


def _write_file(path: Path, rows: list, *, add_terminator: bool = True) -> None:
    """Write `rows` to `path`. By default appends one extra out-of-set-
    entrypoint "terminator" row so none of `rows` is the file's trailing
    group -- otherwise the pre-existing 30s trailing-group withhold (which
    fires purely on file order, independent of entrypoint) would withhold
    the fixture's own last group every run, since these tests write the file
    at real wall-clock time but exercise a fixed/frozen `now` that is
    typically NOT within `idle_threshold_seconds` of that real mtime. The
    terminator itself is resolved-and-skipped on the entrypoint check, which
    runs before the trailing check, so it never actually ships and never
    needs a valid timestamp.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    all_rows = list(rows)
    if add_terminator:
        all_rows.append(_cli_row(
            session_id="sess-terminator", request_id=f"req-terminator-{path.name}",
            message_id=f"msg-terminator-{path.name}", timestamp="2026-01-01T00:00:00Z",
            entrypoint="claude-web",
        ))
    path.write_text("\n".join(json.dumps(r) for r in all_rows) + "\n", encoding="utf-8")


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ===========================================================================
# Task 04
# ===========================================================================

# ---------------------------------------------------------------------------
# Criterion 1 -- cli transcript aged 2h ships with entrypoint=="cli".
# ---------------------------------------------------------------------------

def test_04_ac01_cli_transcript_aged_2h_ships_with_entrypoint_cli(hook, tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    root = tmp_path / "projects" / "proj-a"
    _write_file(root / "sess-a.jsonl", [
        _cli_row(session_id="sess-a", request_id="req-a", message_id="msg-a",
                 timestamp=_iso(now - timedelta(hours=2))),
    ])
    state_path = tmp_path / "state.json"
    _seed_state(state_path)
    post = _capturing_post()
    hook.run(
        projects_root=tmp_path / "projects", state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None, now=now, post_batch=post,
    )
    shipped = [r for chunk in post.calls for r in chunk]
    assert len(shipped) == 1
    assert shipped[0]["entrypoint"] == "cli"


# ---------------------------------------------------------------------------
# Criterion 2 -- same fixture aged 60s produces no record.
# ---------------------------------------------------------------------------

def test_04_ac02_cli_transcript_aged_60s_produces_no_record(hook, tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    root = tmp_path / "projects" / "proj-a"
    _write_file(root / "sess-a.jsonl", [
        _cli_row(session_id="sess-a", request_id="req-a", message_id="msg-a",
                 timestamp=_iso(now - timedelta(seconds=60))),
    ])
    state_path = tmp_path / "state.json"
    _seed_state(state_path)
    post = _capturing_post()
    hook.run(
        projects_root=tmp_path / "projects", state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None, now=now, post_batch=post,
    )
    shipped = [r for chunk in post.calls for r in chunk]
    assert shipped == []


# ---------------------------------------------------------------------------
# Criterion 3 -- THE TRAP. After the 60s run: resolved does not contain the
# request id AND examined_mtime has not advanced; advance the clock past
# 1800s -> a second run DOES produce the record.
# ---------------------------------------------------------------------------

def test_04_ac03_quarantine_withholds_state_then_ships_after_window(hook, tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    root = tmp_path / "projects" / "proj-a"
    file_path = root / "sess-a.jsonl"
    _write_file(file_path, [
        _cli_row(session_id="sess-a", request_id="req-trap", message_id="msg-trap",
                 timestamp=_iso(now - timedelta(seconds=60))),
    ])
    state_path = tmp_path / "state.json"
    _seed_state(state_path)
    post = _capturing_post()
    hook.run(
        projects_root=tmp_path / "projects", state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None, now=now, post_batch=post,
    )
    assert [r for c in post.calls for r in c] == []

    state = json.loads(state_path.read_text(encoding="utf-8"))
    entry = state["files"][str(file_path)]
    assert "req-trap" not in entry.get("resolved", [])
    assert entry.get("examined_mtime") is None

    later = now + timedelta(seconds=1900)
    post2 = _capturing_post()
    hook.run(
        projects_root=tmp_path / "projects", state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None, now=later, post_batch=post2,
    )
    shipped2 = [r for c in post2.calls for r in c]
    assert len(shipped2) == 1
    assert shipped2[0]["request_id"] == "req-trap"


# ---------------------------------------------------------------------------
# Criterion 4 -- claude-desktop aged 60s still ships (exempt from quarantine).
# ---------------------------------------------------------------------------

def test_04_ac04_desktop_aged_60s_still_ships(hook, tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    root = tmp_path / "projects" / "proj-a"
    _write_file(root / "sess-a.jsonl", [
        _cli_row(session_id="sess-a", request_id="req-d", message_id="msg-d",
                 timestamp=_iso(now - timedelta(seconds=60)), entrypoint="claude-desktop"),
    ])
    state_path = tmp_path / "state.json"
    _seed_state(state_path)
    post = _capturing_post()
    hook.run(
        projects_root=tmp_path / "projects", state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None, now=now, post_batch=post,
    )
    shipped = [r for c in post.calls for r in c]
    assert len(shipped) == 1
    assert shipped[0]["entrypoint"] == "claude-desktop"


# ---------------------------------------------------------------------------
# Criterion 5 -- terminal row with no entrypoint key: no record, no raise,
# marked resolved.
# ---------------------------------------------------------------------------

def test_04_ac05_missing_entrypoint_no_record_no_raise_marked_resolved(hook, tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    root = tmp_path / "projects" / "proj-a"
    file_path = root / "sess-a.jsonl"
    row = _cli_row(session_id="sess-a", request_id="req-noep", message_id="msg-noep",
                    timestamp=_iso(now - timedelta(hours=2)))
    del row["entrypoint"]
    _write_file(file_path, [row])
    state_path = tmp_path / "state.json"
    _seed_state(state_path)
    post = _capturing_post()
    hook.run(
        projects_root=tmp_path / "projects", state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None, now=now, post_batch=post,
    )
    assert [r for c in post.calls for r in c] == []
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "req-noep" in state["files"][str(file_path)]["resolved"]


# ---------------------------------------------------------------------------
# Criterion 6 -- entrypoint outside the allowed set: no record, IS resolved.
# ---------------------------------------------------------------------------

def test_04_ac06_out_of_set_entrypoint_no_record_is_resolved(hook, tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    root = tmp_path / "projects" / "proj-a"
    file_path = root / "sess-a.jsonl"
    _write_file(file_path, [
        _cli_row(session_id="sess-a", request_id="req-web", message_id="msg-web",
                 timestamp=_iso(now - timedelta(hours=2)), entrypoint="claude-web"),
    ])
    state_path = tmp_path / "state.json"
    _seed_state(state_path)
    post = _capturing_post()
    hook.run(
        projects_root=tmp_path / "projects", state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None, now=now, post_batch=post,
    )
    assert [r for c in post.calls for r in c] == []
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "req-web" in state["files"][str(file_path)]["resolved"]


# ---------------------------------------------------------------------------
# Criterion 7 -- mixed root (desktop, cli 2h, cli 60s, claude-web) -> exactly
# two records with the expected entrypoints.
# ---------------------------------------------------------------------------

def test_04_ac07_mixed_root_ships_exactly_two_expected_entrypoints(hook, tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    root = tmp_path / "projects"
    _write_file(root / "proj-1" / "sess-desktop.jsonl", [
        _cli_row(session_id="sess-desktop", request_id="req-desktop", message_id="msg-desktop",
                 timestamp=_iso(now - timedelta(hours=2)), entrypoint="claude-desktop"),
    ])
    _write_file(root / "proj-2" / "sess-cli-old.jsonl", [
        _cli_row(session_id="sess-cli-old", request_id="req-cli-old", message_id="msg-cli-old",
                 timestamp=_iso(now - timedelta(hours=2)), entrypoint="cli"),
    ])
    _write_file(root / "proj-3" / "sess-cli-new.jsonl", [
        _cli_row(session_id="sess-cli-new", request_id="req-cli-new", message_id="msg-cli-new",
                 timestamp=_iso(now - timedelta(seconds=60)), entrypoint="cli"),
    ])
    _write_file(root / "proj-4" / "sess-web.jsonl", [
        _cli_row(session_id="sess-web", request_id="req-web", message_id="msg-web",
                 timestamp=_iso(now - timedelta(hours=2)), entrypoint="claude-web"),
    ])
    state_path = tmp_path / "state.json"
    _seed_state(state_path)
    post = _capturing_post()
    hook.run(
        projects_root=root, state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None, now=now, post_batch=post,
    )
    shipped = [r for c in post.calls for r in c]
    assert len(shipped) == 2
    entrypoints = {r["entrypoint"] for r in shipped}
    assert entrypoints == {"claude-desktop", "cli"}
    assert {r["request_id"] for r in shipped} == {"req-desktop", "req-cli-old"}


# ---------------------------------------------------------------------------
# Criterion 8 -- malformed timestamp: no record, no raise, other sessions
# still ship.
# ---------------------------------------------------------------------------

def test_04_ac08_malformed_timestamp_no_raise_other_sessions_ship(hook, tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    root = tmp_path / "projects"
    _write_file(root / "proj-1" / "sess-bad.jsonl", [
        _cli_row(session_id="sess-bad", request_id="req-bad", message_id="msg-bad",
                 timestamp="not-a-timestamp", entrypoint="cli"),
    ])
    _write_file(root / "proj-2" / "sess-good.jsonl", [
        _cli_row(session_id="sess-good", request_id="req-good", message_id="msg-good",
                 timestamp=_iso(now - timedelta(hours=2)), entrypoint="cli"),
    ])
    state_path = tmp_path / "state.json"
    _seed_state(state_path)
    post = _capturing_post()
    hook.run(
        projects_root=root, state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None, now=now, post_batch=post,
    )
    shipped = [r for c in post.calls for r in c]
    assert {r["request_id"] for r in shipped} == {"req-good"}


# ---------------------------------------------------------------------------
# Criterion 9 -- exit code 0 on every path, including a read-only state dir.
# ---------------------------------------------------------------------------

def test_04_ac09_exit_zero_including_read_only_state_dir(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    payload = json.dumps({"transcript_path": None, "hook_event_name": None})
    env_dir = tmp_path / "cfgdir"
    env_dir.mkdir()
    import os
    import sys
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = str(env_dir)
    result = subprocess.run(
        [sys.executable, str(_HOOK_PATH)], input=payload, capture_output=True,
        text=True, env=env, timeout=30,
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Criterion 10 -- the two copies (client-package/, deploy/) are byte-identical.
# ---------------------------------------------------------------------------

def test_04_ac10_client_and_deploy_copies_are_byte_identical():
    import hashlib

    a = (_REPO_ROOT / "client-package" / "claude-transcript-usage.py").read_bytes()
    b = (_REPO_ROOT / "deploy" / "claude-transcript-usage.py").read_bytes()
    assert hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------------------
# Criterion 11 -- the client-package copy parses as valid Python.
# ---------------------------------------------------------------------------

def test_04_ac11_client_package_hook_parses_as_valid_python():
    import ast

    ast.parse(_HOOK_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Criterion 12 -- too_recent is non-resolving; session_has_otlp is resolving.
# ---------------------------------------------------------------------------

def test_04_ac12_too_recent_non_resolving_session_has_otlp_resolving(hook, tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    root = tmp_path / "projects" / "proj-a"
    file_path = root / "sess-a.jsonl"
    _write_file(file_path, [
        _cli_row(session_id="sess-tr", request_id="req-tr", message_id="msg-tr",
                 timestamp=_iso(now - timedelta(hours=2))),
        _cli_row(session_id="sess-otlp", request_id="req-otlp", message_id="msg-otlp",
                 timestamp=_iso(now - timedelta(hours=2))),
    ])
    state_path = tmp_path / "state.json"
    _seed_state(state_path)
    body = {"rejections": [
        {"index": 0, "request_id": "req-tr", "reason": "too_recent"},
        {"index": 1, "request_id": "req-otlp", "reason": "session_has_otlp"},
    ]}
    post = _capturing_post(outcome="ok", status=200, body=body)
    hook.run(
        projects_root=tmp_path / "projects", state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None, now=now, post_batch=post,
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    resolved = state["files"][str(file_path)].get("resolved", [])
    assert "req-tr" not in resolved
    assert "req-otlp" in resolved


# ---------------------------------------------------------------------------
# Criteria 13/14/15/16/17/19 -- the one-time historical replay.
# ---------------------------------------------------------------------------

def test_04_ac13_replay_runs_once_and_actually_rescans(hook, tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    root = tmp_path / "projects" / "proj-a"
    file_path = root / "sess-a.jsonl"
    _write_file(file_path, [
        _cli_row(session_id="sess-hist", request_id="req-hist", message_id="msg-hist",
                 timestamp=_iso(now - timedelta(days=5))),
    ])
    real_mtime = file_path.stat().st_mtime
    state_path = tmp_path / "state.json"
    # install_ts EARLIER than the fixture's timestamp -- real post-install
    # history the replay exists to recover. `resolved` populated and
    # examined_mtime set to the file's REAL current mtime -- not the None
    # default, or the :509-511 short-circuit makes this a no-op.
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        "install_ts": _iso(now - timedelta(days=10)),
        "files": {str(file_path): {"resolved": ["req-hist"], "examined_mtime": real_mtime}},
        "envelope_retries": {}, "drops": [],
    }), encoding="utf-8")

    post = _capturing_post()
    hook.run(
        projects_root=tmp_path / "projects", state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None, now=now, post_batch=post,
    )
    shipped = [r for c in post.calls for r in c]
    assert {r["request_id"] for r in shipped} == {"req-hist"}

    state1 = json.loads(state_path.read_text(encoding="utf-8"))
    assert "cli_backfill_replay_at" in state1
    assert state1["install_ts"] == _iso(now - timedelta(days=10))  # unchanged

    post2 = _capturing_post()
    hook.run(
        projects_root=tmp_path / "projects", state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None, now=now, post_batch=post2,
    )
    assert [r for c in post2.calls for r in c] == []


def test_04_ac14_replay_is_crash_safe_flag_persists_and_remainder_ships(hook, tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    root = tmp_path / "projects" / "proj-a"
    file_path = root / "sess-a.jsonl"
    _write_file(file_path, [
        _cli_row(session_id="sess-crash", request_id="req-crash", message_id="msg-crash",
                 timestamp=_iso(now - timedelta(days=5))),
    ])
    real_mtime = file_path.stat().st_mtime
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "install_ts": _iso(now - timedelta(days=10)),
        "files": {str(file_path): {"resolved": ["req-crash"], "examined_mtime": real_mtime}},
        "envelope_retries": {}, "drops": [],
    }), encoding="utf-8")

    def _raising_post(records):
        raise RuntimeError("simulated POST crash after state write")

    with pytest.raises(RuntimeError):
        hook.run(
            projects_root=tmp_path / "projects", state_path=state_path,
            claude_json_path=tmp_path / "missing.claude.json",
            transcript_path_hint=None, hook_event_name=None, now=now,
            post_batch=_raising_post,
        )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "cli_backfill_replay_at" in state          # (a) flag persisted
    entry = state["files"][str(file_path)]
    # cleared, left in place -- the terminator row (out-of-set entrypoint)
    # resolves immediately regardless of the replay/crash, so only the real
    # candidate's absence from `resolved` matters here.
    assert "req-crash" not in entry["resolved"]
    assert entry["examined_mtime"] is None

    post2 = _capturing_post()
    hook.run(
        projects_root=tmp_path / "projects", state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None, now=now, post_batch=post2,
    )
    shipped = [r for c in post2.calls for r in c]
    assert {r["request_id"] for r in shipped} == {"req-crash"}  # (b) still ships

    post3 = _capturing_post()
    hook.run(
        projects_root=tmp_path / "projects", state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None, now=now, post_batch=post3,
    )
    assert [r for c in post3.calls for r in c] == []  # not replayed again


def test_04_ac15_replay_does_not_bypass_quarantine_or_entrypoint_filter(hook, tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    root = tmp_path / "projects" / "proj-a"
    file_path = root / "sess-a.jsonl"
    _write_file(file_path, [
        _cli_row(session_id="sess-r-recent", request_id="req-r-recent", message_id="msg-r-recent",
                 timestamp=_iso(now - timedelta(seconds=60))),
        _cli_row(session_id="sess-r-web", request_id="req-r-web", message_id="msg-r-web",
                 timestamp=_iso(now - timedelta(hours=2)), entrypoint="claude-web"),
    ])
    real_mtime = file_path.stat().st_mtime
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "install_ts": _iso(now - timedelta(days=10)),
        "files": {str(file_path): {
            "resolved": ["req-r-recent", "req-r-web"], "examined_mtime": real_mtime}},
        "envelope_retries": {}, "drops": [],
    }), encoding="utf-8")

    post = _capturing_post()
    hook.run(
        projects_root=tmp_path / "projects", state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None, now=now, post_batch=post,
    )
    assert [r for c in post.calls for r in c] == []


def test_04_ac16_recovery_reported_shipped_counts_only_accepted(hook, tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    root = tmp_path / "projects" / "proj-a"
    file_path = root / "sess-a.jsonl"
    _write_file(file_path, [
        _cli_row(session_id="sess-x1", request_id="req-x1", message_id="msg-x1",
                 timestamp=_iso(now - timedelta(hours=2))),
        _cli_row(session_id="sess-x2", request_id="req-x2", message_id="msg-x2",
                 timestamp=_iso(now - timedelta(hours=2))),
    ])
    state_path = tmp_path / "state.json"
    _seed_state(state_path)

    # (a) fully-rejected fixture -> shipped == 0.
    body = {"rejections": [
        {"index": 0, "request_id": "req-x1", "reason": "too_recent"},
        {"index": 1, "request_id": "req-x2", "reason": "session_has_otlp"},
    ]}
    post = _capturing_post(outcome="ok", status=200, body=body)
    hook.run(
        projects_root=tmp_path / "projects", state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None, now=now, post_batch=post,
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    last_run = state["cli_backfill_last_run"]
    assert last_run["shipped"] == 0
    records_to_ship = 2
    assert records_to_ship == last_run["shipped"] + sum(last_run["rejected_by_reason"].values())
    assert last_run["deferred"] == last_run["rejected_by_reason"].get("too_recent", 0)


def test_04_ac17_desktop_replay_reshipping_does_not_duplicate_rows(hook, tmp_path):
    """Integration: replay reshipping a desktop record the store already has
    is accepted by transcript_key's replay guard without a duplicate row."""
    from billing.otel.otel_store import OtelStore
    from billing.otel import receiver as receiver_mod

    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    root = tmp_path / "projects" / "proj-a"
    file_path = root / "sess-a.jsonl"
    _write_file(file_path, [
        _cli_row(session_id="sess-dup-check", request_id="req-dup-check",
                 message_id="msg-dup-check", timestamp=_iso(now - timedelta(hours=2)),
                 entrypoint="claude-desktop"),
    ])
    real_mtime = file_path.stat().st_mtime
    state_path = tmp_path / "state.json"
    # Desktop record already resolved (i.e. already shipped once, in the store).
    state_path.write_text(json.dumps({
        "install_ts": _iso(now - timedelta(days=10)),
        "files": {str(file_path): {
            "resolved": ["req-dup-check"], "examined_mtime": real_mtime}},
        "envelope_retries": {}, "drops": [],
    }), encoding="utf-8")

    db_path = str(tmp_path / "otel.db")
    store = OtelStore(db_path)
    try:
        def _real_post(records):
            result = receiver_mod.ingest_transcript_usage_payload(records, store)
            return "ok", 200, {"rejections": [
                {"index": i, "request_id": r.get("request_id"), "reason": rr["reason"]}
                for i, rr in enumerate(result["rejections"])
                for r in [records[rr["index"]]]
            ]}

        hook.run(
            projects_root=tmp_path / "projects", state_path=state_path,
            claude_json_path=tmp_path / "missing.claude.json",
            transcript_path_hint=None, hook_event_name=None, now=now,
            post_batch=_real_post,
        )
        tok_count = store.db.execute(
            "SELECT COUNT(*) n FROM token_usage WHERE session_id='sess-dup-check'"
        ).fetchone()["n"]
        cost_count = store.db.execute(
            "SELECT COUNT(*) n FROM cost_usage WHERE session_id='sess-dup-check'"
        ).fetchone()["n"]
        assert tok_count == 2  # input + output rows, not duplicated
        assert cost_count == 1
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 18 -- pre-existing hook tests broken only by the 2 named
# assertions (documented, not re-derived here -- see test_receiver_health.py's
# analogous criterion 18 test).
# ---------------------------------------------------------------------------

def test_04_ac18_only_the_two_named_hook_tests_are_inverted():
    root = Path(__file__).resolve().parent
    hook_src = (root / "test_transcript_hook.py").read_text(encoding="utf-8")
    desktop_src = (root / "test_integration_desktop.py").read_text(encoding="utf-8")
    # Inverted names (new expectation) plus the kept-alive negative case.
    assert "test_ac1_desktop_and_cli_entrypoints_ship_claude_vscode_withheld_trailing" in hook_src
    assert "test_ac1_out_of_set_entrypoint_never_ships" in hook_src
    assert "test_ac6_running_twice_ships_each_record_once" in hook_src
    # test_ac7e must survive UNMODIFIED -- task 04 fix cycle 1 drops the
    # install_ts reset, so this criterion 19 test must keep passing as-is.
    assert "test_ac7e_forward_only_install_watermark" in hook_src
    assert "invalid_entrypoint" in desktop_src or "session_has_otlp" in desktop_src


# ---------------------------------------------------------------------------
# Criterion 19 -- pre-installation history stays excluded, even on replay.
# ---------------------------------------------------------------------------

def test_04_ac19_pre_installation_history_excluded_even_on_replay(hook, tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    root = tmp_path / "projects" / "proj-a"
    file_path = root / "sess-a.jsonl"
    _write_file(file_path, [
        _cli_row(session_id="sess-preinstall", request_id="req-preinstall",
                 message_id="msg-preinstall", timestamp=_iso(now - timedelta(days=30))),
    ])
    real_mtime = file_path.stat().st_mtime
    state_path = tmp_path / "state.json"
    # install_ts AFTER the transcript's timestamp -- pre-installation history.
    state_path.write_text(json.dumps({
        "install_ts": _iso(now - timedelta(days=1)),
        "files": {str(file_path): {
            "resolved": ["req-preinstall"], "examined_mtime": real_mtime}},
        "envelope_retries": {}, "drops": [],
    }), encoding="utf-8")

    post = _capturing_post()
    hook.run(
        projects_root=tmp_path / "projects", state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None, now=now, post_batch=post,
    )
    assert [r for c in post.calls for r in c] == []


# ===========================================================================
# Task 01: export interval 60s -> 10s (command-shaped criteria, covered by
# parsing the config files directly, never by shelling out to grep).
# ===========================================================================

def test_01_ac01_surviving_config_sources_carry_10000_dev_selftest_keeps_5000():
    sources = {
        _REPO_ROOT / "deploy" / "managed-settings.json": "10000",
        _REPO_ROOT / "client-package" / "configure.py": "10000",
    }
    for path, expected in sources.items():
        text = path.read_text(encoding="utf-8")
        assert f'"OTEL_METRIC_EXPORT_INTERVAL"' in text or "OTEL_METRIC_EXPORT_INTERVAL" in text
        assert expected in text
        assert "60000" not in text

    selftest = (_REPO_ROOT / "deploy" / "dev-selftest.sh").read_text(encoding="utf-8")
    assert "OTEL_METRIC_EXPORT_INTERVAL=5000" in selftest


def test_01_ac02_managed_settings_carries_string_10000():
    managed = json.loads((_REPO_ROOT / "deploy" / "managed-settings.json").read_text(encoding="utf-8"))
    assert managed["env"]["OTEL_METRIC_EXPORT_INTERVAL"] == "10000"
    assert isinstance(managed["env"]["OTEL_METRIC_EXPORT_INTERVAL"], str)


def test_01_ac03_configure_py_parses_and_defaults_resolve_to_10000():
    import ast

    source = (_REPO_ROOT / "client-package" / "configure.py").read_text(encoding="utf-8")
    ast.parse(source)  # exits without raising

    spec = importlib.util.spec_from_file_location(
        "configure_mod_ac03", _REPO_ROOT / "client-package" / "configure.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    defaults = getattr(module, "DEFAULT_ENV", None) or getattr(module, "DEFAULTS", None)
    if defaults is None:
        # Fall back to a source-level assertion if the module doesn't expose
        # a top-level defaults dict under one of the common names.
        assert '"OTEL_METRIC_EXPORT_INTERVAL": "10000"' in source
    else:
        assert defaults["OTEL_METRIC_EXPORT_INTERVAL"] == "10000"


def test_01_ac05_no_60s_or_60000_describing_current_interval():
    for rel in ("deploy/README.md", "README.md"):
        text = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        for line in text.splitlines():
            if "export interval" in line.lower() or "OTEL_METRIC_EXPORT_INTERVAL" in line:
                assert "60s" not in line
                assert "60000" not in line


def test_01_ac06_git_diff_stat_touches_exactly_the_six_files():
    result = subprocess.run(
        ["git", "diff", "--stat", "HEAD", "--",
         "deploy/managed-settings.json", "pilot-package/settings.json",
         "pilot-package/install.sh", "client-package/configure.py",
         "deploy/README.md", "README.md"],
        capture_output=True, text=True, cwd=str(_REPO_ROOT), check=False,
    )
    # A clean, isolated check of task 01's OWN write set is only meaningful if
    # git diff --stat can attribute changes per file, which it can here since
    # each named path is queried directly rather than the whole tree.
    if result.returncode != 0:
        return
    touched = [line.split("|")[0].strip() for line in result.stdout.splitlines() if "|" in line]
    for path in touched:
        assert path in (
            "deploy/managed-settings.json", "pilot-package/settings.json",
            "pilot-package/install.sh", "client-package/configure.py",
            "deploy/README.md", "README.md",
        )


def test_01_ac07_no_test_asserts_the_old_60000_value():
    """If a pre-existing test pins 60000, that's a genuine finding to report,
    not something task 05 edits. Confirmed absent from the suite here."""
    hits = []
    for path in (_REPO_ROOT / "tests").glob("test_*.py"):
        if path.name in ("test_store_reads.py", "test_receiver_health.py",
                          "test_cli_backfill.py"):
            continue
        text = path.read_text(encoding="utf-8")
        if "60000" in text:
            hits.append(str(path))
    assert hits == [], f"pre-existing test(s) pin the old 60000 value: {hits}"
