"""Tests for deploy/claude-transcript-usage.py -- task 06a of
desktop-usage-capture (the standalone client hook only; rollout/packaging
is task 06b's scope).

The hook is standalone and stdlib-only, so it is imported BY FILE PATH here,
never as a package import. Tests never POST to a real receiver or bind a
port -- network is replaced by an injected `post_batch` callable except for
one subprocess-level smoke test of the always-exit-0 guarantee, which points
CLAUDE_BILLING_RECEIVER at a closed port so the connection is refused fast.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from billing.otel.transcript import MAX_BATCH_SIZE as SERVER_MAX_BATCH_SIZE
from billing.otel.transcript import validate_batch

from tests.conftest import (
    DUPLICATE_CACHE_CREATION,
    DUPLICATE_CACHE_READ,
    DUPLICATE_INPUT,
    DUPLICATE_OUTPUT,
    DUPLICATE_REQUEST_ID,
    MULTI_BLOCK_CACHE_CREATION,
    MULTI_BLOCK_CACHE_READ,
    MULTI_BLOCK_INPUT,
    MULTI_BLOCK_OUTPUT_PARTIAL,
    MULTI_BLOCK_OUTPUT_TERMINAL,
    MULTI_BLOCK_REQUEST_ID,
    SECOND_PROJECT_REQUEST_ID,
    SESSION_A_ID,
    SESSION_B_ID,
    SIDECHAIN_CACHE_CREATION,
    SIDECHAIN_CACHE_READ,
    SIDECHAIN_INPUT,
    SIDECHAIN_OUTPUT,
    SIDECHAIN_REQUEST_ID,
    _usage_row,
)

_HOOK_PATH = Path(__file__).resolve().parents[1] / "deploy" / "claude-transcript-usage.py"
_HOOK_SOURCE = _HOOK_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def hook():
    spec = importlib.util.spec_from_file_location("claude_transcript_usage_hook", _HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _capturing_post(outcome="ok", status=200, body=None, sequence=None):
    """A fake post_batch. `sequence`, if given, is a list of
    (outcome, status, body) tuples consumed one per call (last one repeats
    once exhausted) -- used to simulate N failures then a success."""
    calls = []

    def _post(records):
        calls.append([dict(r) for r in records])
        if sequence:
            step = sequence[min(len(calls) - 1, len(sequence) - 1)]
            return step
        return outcome, status, dict(body or {})

    _post.calls = calls
    return _post


def _seed_epoch_install(state_path: Path) -> None:
    """Pre-seed state so the forward-only install watermark (which, on a
    genuinely first run, is set from real wall-clock time) doesn't filter
    out these tests' synthetic fixture timestamps -- most of which sit in
    the past relative to the actual clock. test_ac7e exercises the
    install-watermark itself and deliberately skips this helper."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        "install_ts": "1970-01-01T00:00:00.000000Z",
        "files": {}, "envelope_retries": {}, "drops": [],
    }), encoding="utf-8")


def _now():
    return datetime.now(timezone.utc)


def _soon():
    """`now` a couple of seconds after the current wall clock -- used with
    idle_threshold_seconds=0 so idle_elapsed is unambiguously true regardless
    of filesystem mtime resolution / clock-read timing (a bare `_now()` can
    land within the same tick as a file just written, making `now - mtime`
    zero or even negative on some filesystems)."""
    return datetime.now(timezone.utc) + timedelta(seconds=2)


# ---------------------------------------------------------------------------
# AC1 / AC1b / AC1c: entrypoint filter + terminal-block collapse
# ---------------------------------------------------------------------------

def test_ac1_desktop_and_cli_entrypoints_ship_claude_vscode_withheld_trailing(
    hook, entrypoint_mix_transcript
):
    """Inverted for otel-export-loss-reduction task 04 Part A: the hook now
    ships `cli`/`claude-vscode` too, not only `claude-desktop`. Under correct
    behavior 2 of the fixture's 3 rows ship here -- the third
    (claude-vscode, the file's LAST-appearing group) is still withheld by the
    pre-existing 30s trailing-group rule (unrelated to entrypoint), since
    `hook_event_name`/`transcript_path_hint` are None here and the file's
    real mtime is not >30s stale relative to `_now()`.
    """
    _seed_epoch_install(entrypoint_mix_transcript.parent / "state.json")
    post = _capturing_post()
    hook.run(
        projects_root=entrypoint_mix_transcript.parent,
        state_path=entrypoint_mix_transcript.parent / "state.json",
        claude_json_path=entrypoint_mix_transcript.parent / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None,
        now=_now(), post_batch=post,
    )
    shipped = [r for chunk in post.calls for r in chunk]
    assert len(shipped) == 2
    assert {r["entrypoint"] for r in shipped} == {"claude-desktop", "cli"}
    assert "sess-claude-vscode" not in {r["session_id"] for r in shipped}


def test_ac1_out_of_set_entrypoint_never_ships(hook, tmp_path):
    """Kept alive: an entrypoint genuinely outside the allowed set must still
    never ship, regardless of the cli/claude-vscode widening above."""
    root = tmp_path / "claude_projects" / "proj"
    root.mkdir(parents=True)
    row = _usage_row(
        session_id="sess-web", request_id="req-web", message_id="msg-web",
        api_block_index=0, stop_reason="end_turn", input_tokens=1, output_tokens=1,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        entrypoint="claude-web", timestamp="2026-01-01T00:00:00Z",
    )
    (root / "sess-web.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    state_path = tmp_path / "state.json"
    _seed_epoch_install(state_path)
    post = _capturing_post()
    hook.run(
        projects_root=root.parent, state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None, now=_now(), post_batch=post,
    )
    assert [r for chunk in post.calls for r in chunk] == []


def test_build_payload_record_carries_entrypoint_not_stamps_it(hook):
    """Direct unit test of build_payload_record itself -- run()'s own
    entrypoint filter makes stamping vs carrying behaviourally identical
    through that path (a row missing/mismatching entrypoint never reaches
    build_payload_record at all), so this must be asserted directly against
    the function, not only observed end-to-end through run()."""
    terminal_row = {
        "sessionId": "sess-carry", "requestId": "req-carry", "cwd": "",
        "entrypoint": "cli",  # deliberately NOT "claude-desktop"
        "timestamp": "2026-01-01T00:00:00Z",
        "message": {
            "id": "msg-carry", "model": "claude-sonnet-5",
            "usage": {"input_tokens": 1, "output_tokens": 1,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        },
    }
    rec = hook.build_payload_record(
        terminal_row, is_sidechain=False, identity={}, remote_cache={})
    assert rec["entrypoint"] == "cli"  # carried from the row, not stamped


def test_ac1b_exact_amount_terminal_block_not_sum_not_first(hook, projects_tree):
    _seed_epoch_install(projects_tree["projects_root"].parent / "state.json")
    post = _capturing_post()
    hook.run(
        projects_root=projects_tree["projects_root"],
        state_path=projects_tree["projects_root"].parent / "state.json",
        claude_json_path=projects_tree["projects_root"].parent / "missing.claude.json",
        transcript_path_hint=str(projects_tree["main_path"]),
        hook_event_name="SessionEnd", now=_now(), post_batch=post,
    )
    shipped = [r for chunk in post.calls for r in chunk]
    multi = next(r for r in shipped if r["request_id"] == MULTI_BLOCK_REQUEST_ID)
    assert multi["input_tokens"] == MULTI_BLOCK_INPUT
    assert multi["output_tokens"] == MULTI_BLOCK_OUTPUT_TERMINAL
    assert multi["cache_creation_input_tokens"] == MULTI_BLOCK_CACHE_CREATION
    assert multi["cache_read_input_tokens"] == MULTI_BLOCK_CACHE_READ
    # Not the sum (5 + 209 = 214) and not the first block (5).
    assert multi["output_tokens"] != MULTI_BLOCK_OUTPUT_PARTIAL + MULTI_BLOCK_OUTPUT_TERMINAL
    assert multi["output_tokens"] != MULTI_BLOCK_OUTPUT_PARTIAL


def test_ac1c_duplicate_pair_both_nonnull_stop_reason_collapses_to_one(hook, projects_tree):
    _seed_epoch_install(projects_tree["projects_root"].parent / "state.json")
    post = _capturing_post()
    hook.run(
        projects_root=projects_tree["projects_root"],
        state_path=projects_tree["projects_root"].parent / "state.json",
        claude_json_path=projects_tree["projects_root"].parent / "missing.claude.json",
        transcript_path_hint=str(projects_tree["main_path"]),
        hook_event_name="SessionEnd", now=_now(), post_batch=post,
    )
    shipped = [r for chunk in post.calls for r in chunk]
    dup_records = [r for r in shipped if r["request_id"] == DUPLICATE_REQUEST_ID]
    assert len(dup_records) == 1
    assert dup_records[0]["input_tokens"] == DUPLICATE_INPUT
    assert dup_records[0]["output_tokens"] == DUPLICATE_OUTPUT
    assert dup_records[0]["cache_creation_input_tokens"] == DUPLICATE_CACHE_CREATION
    assert dup_records[0]["cache_read_input_tokens"] == DUPLICATE_CACHE_READ


# ---------------------------------------------------------------------------
# AC1d / AC1d-bis: subagent capture, against the real nested layout
# ---------------------------------------------------------------------------

def test_ac1d_and_1d_bis_subagent_capture_and_anti_fixture(hook, projects_tree, transcript_expected_totals):
    _seed_epoch_install(projects_tree["projects_root"].parent / "state.json")
    post = _capturing_post()
    hook.run(
        projects_root=projects_tree["projects_root"],
        state_path=projects_tree["projects_root"].parent / "state.json",
        claude_json_path=projects_tree["projects_root"].parent / "missing.claude.json",
        transcript_path_hint=str(projects_tree["main_path"]),
        hook_event_name="SessionEnd", now=_soon(), post_batch=post,
        idle_threshold_seconds=0,  # let the sidechain file's own trailing group ship too
    )
    shipped = [r for chunk in post.calls for r in chunk]
    session_a_records = [r for r in shipped if r["session_id"] == SESSION_A_ID]

    def _sum(records):
        return sum(
            r["input_tokens"] + r["output_tokens"]
            + r["cache_creation_input_tokens"] + r["cache_read_input_tokens"]
            for r in records
        )

    hook_total = _sum(session_a_records)
    assert hook_total == transcript_expected_totals["combined_total"]
    # not the main-file-only value
    assert hook_total != transcript_expected_totals["main_only"]["total"]

    # Anti-fixture check: a FLAT enumeration of project_dir_a only must miss
    # the sidechain file and equal the published MAIN-ONLY total.
    flat_files = sorted(projects_tree["project_dir_a"].glob("*.jsonl"))
    assert flat_files == [projects_tree["main_path"]]
    flat_rows = hook._usage_rows(hook.read_jsonl_rows(flat_files[0]))
    order, groups = hook.build_groups(flat_rows)
    flat_total = 0
    for key in order:
        terminal = hook.select_terminal_block(groups[key])
        u = terminal["message"]["usage"]
        flat_total += (u["input_tokens"] + u["output_tokens"]
                       + u["cache_creation_input_tokens"] + u["cache_read_input_tokens"])
    assert flat_total == transcript_expected_totals["main_only"]["total"]
    assert flat_total != hook_total


def test_ac1e_query_source_and_shared_repo(hook, projects_tree):
    _seed_epoch_install(projects_tree["projects_root"].parent / "state.json")
    post = _capturing_post()
    hook.run(
        projects_root=projects_tree["projects_root"],
        state_path=projects_tree["projects_root"].parent / "state.json",
        claude_json_path=projects_tree["projects_root"].parent / "missing.claude.json",
        transcript_path_hint=str(projects_tree["main_path"]),
        hook_event_name="SessionEnd", now=_soon(), post_batch=post,
        idle_threshold_seconds=0,
    )
    shipped = [r for chunk in post.calls for r in chunk]
    main_rec = next(r for r in shipped if r["request_id"] == MULTI_BLOCK_REQUEST_ID)
    side_rec = next(r for r in shipped if r["request_id"] == SIDECHAIN_REQUEST_ID)
    assert main_rec["query_source"] == "main"
    assert side_rec["query_source"] == "subagent"
    assert main_rec["repo_raw"] == side_rec["repo_raw"]


def test_ac1e_classifies_by_isSidechain_flag_not_by_subagents_path(hook, tmp_path):
    """A filename/path-based classifier (`"subagents" in file_key`) would
    pass every OTHER test in this file, because no other fixture separates
    the flag from the directory shape. Here they deliberately DISAGREE:
    an isSidechain=true row living OUTSIDE any subagents/ directory, and an
    isSidechain=false row living INSIDE one. query_source must follow the
    flag in both cases."""
    root = tmp_path / "claude_projects" / "proj"
    root.mkdir(parents=True)

    flagged_outside_row = _usage_row(
        session_id="sess-flagout", request_id="req-flagout", message_id="msg-flagout",
        api_block_index=0, stop_reason="end_turn", input_tokens=1, output_tokens=1,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        is_sidechain=True, timestamp="2026-01-01T00:00:00Z",
    )
    (root / "sess-flagout.jsonl").write_text(json.dumps(flagged_outside_row) + "\n", encoding="utf-8")

    unflagged_inside_dir = root / "sess-unflagged" / "subagents"
    unflagged_inside_dir.mkdir(parents=True)
    unflagged_inside_row = _usage_row(
        session_id="sess-unflagged", request_id="req-unflagged", message_id="msg-unflagged",
        api_block_index=0, stop_reason="end_turn", input_tokens=1, output_tokens=1,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        is_sidechain=False, timestamp="2026-01-01T00:00:00Z",
    )
    (unflagged_inside_dir / "agent-x.jsonl").write_text(
        json.dumps(unflagged_inside_row) + "\n", encoding="utf-8")

    state_path = tmp_path / "state.json"
    _seed_epoch_install(state_path)
    post = _capturing_post()
    hook.run(
        projects_root=root.parent, state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None,
        now=_soon(), post_batch=post, idle_threshold_seconds=0,
    )
    shipped = [r for chunk in post.calls for r in chunk]
    flagged_rec = next(r for r in shipped if r["request_id"] == "req-flagout")
    unflagged_rec = next(r for r in shipped if r["request_id"] == "req-unflagged")
    assert flagged_rec["query_source"] == "subagent", (
        "isSidechain=true OUTSIDE a subagents/ directory must still classify "
        "as subagent -- the flag decides, not the path"
    )
    assert unflagged_rec["query_source"] == "main", (
        "isSidechain=false INSIDE a subagents/ directory must still "
        "classify as main -- the flag decides, not the path"
    )


def test_ac1f_missing_apiblockindex_selects_by_file_order_without_raising(hook):
    entries = [
        (0, {"apiBlockIndex": None, "message": {"usage": {}}}),
        (1, {"apiBlockIndex": 0, "message": {"usage": {}}}),
    ]
    terminal = hook.select_terminal_block(entries)
    assert terminal["apiBlockIndex"] == 0  # present beats absent regardless of ordinal

    entries_all_none = [
        (0, {"apiBlockIndex": None, "message": {"usage": {}}, "tag": "first"}),
        (1, {"apiBlockIndex": None, "message": {"usage": {}}, "tag": "last"}),
    ]
    terminal2 = hook.select_terminal_block(entries_all_none)
    assert terminal2["tag"] == "last"  # all absent -> file order, last wins


def test_ac1f_apiblockindex_wins_over_file_order_when_they_disagree(hook):
    # File order and apiBlockIndex DISAGREE here: the row with the HIGHER
    # apiBlockIndex (1) appears FIRST in file order (ordinal 0), and the
    # lower one (0) appears LAST (ordinal 1). A selector that used pure file
    # order (ignoring apiBlockIndex entirely) would pick the ordinal-1 row
    # (apiBlockIndex=0) here -- the wrong one. The normative selector is
    # apiBlockIndex, not file order; file order is only the tie-breaker.
    entries = [
        (0, {"apiBlockIndex": 1, "message": {"usage": {}}, "tag": "higher-index-first"}),
        (1, {"apiBlockIndex": 0, "message": {"usage": {}}, "tag": "lower-index-last"}),
    ]
    terminal = hook.select_terminal_block(entries)
    assert terminal["apiBlockIndex"] == 1
    assert terminal["tag"] == "higher-index-first"


# ---------------------------------------------------------------------------
# AC2 / AC3: privacy and schema-drift
# ---------------------------------------------------------------------------

def test_ac2_no_message_content_in_payload(hook, tmp_path):
    _seed_epoch_install(tmp_path / "state.json")
    root = tmp_path / "claude_projects" / "proj"
    root.mkdir(parents=True)
    secret = "SECRET_PROMPT_TEXT_DO_NOT_SHIP"
    row = _usage_row(
        session_id="sess-priv", request_id="req-priv", message_id="msg-priv",
        api_block_index=0, stop_reason="end_turn", input_tokens=1, output_tokens=1,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        timestamp="2026-01-01T00:00:00Z",
    )
    row["message"]["content"] = secret
    row["some_future_field_with_prompt_text"] = secret
    (root / "sess-priv.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    post = _capturing_post()
    hook.run(
        projects_root=root.parent, state_path=tmp_path / "state.json",
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None, now=_soon(), post_batch=post,
        idle_threshold_seconds=0,
    )
    shipped = [r for chunk in post.calls for r in chunk]
    assert len(shipped) == 1
    assert secret not in json.dumps(shipped[0])


def test_ac3_payload_validates_against_server_validator(hook, projects_tree):
    _seed_epoch_install(projects_tree["projects_root"].parent / "state.json")
    post = _capturing_post()
    hook.run(
        projects_root=projects_tree["projects_root"],
        state_path=projects_tree["projects_root"].parent / "state.json",
        claude_json_path=projects_tree["projects_root"].parent / "missing.claude.json",
        transcript_path_hint=str(projects_tree["main_path"]),
        hook_event_name="SessionEnd", now=_soon(), post_batch=post,
        idle_threshold_seconds=0,
    )
    shipped = [r for chunk in post.calls for r in chunk]
    assert shipped
    accepted, rejected = validate_batch(shipped)
    assert rejected == []
    assert len(accepted) == len(shipped)


def test_max_batch_size_matches_server_contract(hook):
    assert hook.MAX_BATCH_SIZE == SERVER_MAX_BATCH_SIZE


# ---------------------------------------------------------------------------
# AC4: always exits 0
# ---------------------------------------------------------------------------

def test_ac4_exits_zero_missing_transcript_missing_claude_json_empty_stdin(tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    config_dir = fake_home / ".claude"  # does not exist -> zero-files path
    env = dict(os.environ)
    env["HOME"] = str(fake_home)
    env["USERPROFILE"] = str(fake_home)
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    env["CLAUDE_BILLING_RECEIVER"] = "http://127.0.0.1:1"
    env["CLAUDE_BILLING_TIMEOUT"] = "0.3"
    for stdin_data in ("", "not-json{{{", json.dumps({"hook_event_name": "SessionEnd"})):
        result = subprocess.run(
            [sys.executable, str(_HOOK_PATH)],
            input=stdin_data, capture_output=True, text=True, timeout=30, env=env,
        )
        assert result.returncode == 0, result.stderr


def test_ac4_exits_zero_receiver_unreachable_with_real_transcript(tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    config_dir = fake_home / ".claude"
    project_dir = config_dir / "projects" / "proj"
    project_dir.mkdir(parents=True)
    row = _usage_row(
        session_id="sess-unreach", request_id="req-unreach", message_id="msg-unreach",
        api_block_index=0, stop_reason="end_turn", input_tokens=1, output_tokens=1,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        timestamp="2026-01-01T00:00:00Z",
    )
    transcript_path = project_dir / "sess-unreach.jsonl"
    transcript_path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    env = dict(os.environ)
    env["HOME"] = str(fake_home)
    env["USERPROFILE"] = str(fake_home)
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    env["CLAUDE_BILLING_RECEIVER"] = "http://127.0.0.1:1"
    env["CLAUDE_BILLING_TIMEOUT"] = "0.3"
    stdin_data = json.dumps({
        "hook_event_name": "SessionEnd",
        "transcript_path": str(transcript_path),
        "session_id": "sess-unreach",
    })
    result = subprocess.run(
        [sys.executable, str(_HOOK_PATH)],
        input=stdin_data, capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("garbage_timeout", ["", "not-a-float", "2s", "   "])
def test_ac4_exits_zero_with_garbage_billing_timeout(tmp_path, garbage_timeout):
    """CLAUDE_BILLING_TIMEOUT parsing is module-scope, outside any function's
    try/except -- a garbage or empty value must never crash the module at
    import time. The empty-string case is the realistic trigger: a shell
    exporting an unset variable, or an MDM profile writing an empty value."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    env = dict(os.environ)
    env["HOME"] = str(fake_home)
    env["USERPROFILE"] = str(fake_home)
    env["CLAUDE_CONFIG_DIR"] = str(fake_home / ".claude")
    env["CLAUDE_BILLING_RECEIVER"] = "http://127.0.0.1:1"
    env["CLAUDE_BILLING_TIMEOUT"] = garbage_timeout
    result = subprocess.run(
        [sys.executable, str(_HOOK_PATH)],
        input="", capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# AC5: malformed trailing line skipped
# ---------------------------------------------------------------------------

def test_ac5_malformed_trailing_line_skipped_preceding_records_ship(hook, projects_tree):
    _seed_epoch_install(projects_tree["projects_root"].parent / "state.json")
    rows = hook.read_jsonl_rows(projects_tree["main_path"])
    # 4 well-formed rows in the fixture, plus one deliberately truncated line.
    assert len(rows) == 4

    post = _capturing_post()
    hook.run(
        projects_root=projects_tree["projects_root"],
        state_path=projects_tree["projects_root"].parent / "state.json",
        claude_json_path=projects_tree["projects_root"].parent / "missing.claude.json",
        transcript_path_hint=str(projects_tree["main_path"]),
        hook_event_name="SessionEnd", now=_now(), post_batch=post,
    )
    shipped = [r for chunk in post.calls for r in chunk]
    assert len(shipped) >= 1  # preceding well-formed records still ship


# ---------------------------------------------------------------------------
# AC6: running twice ships each record once
# ---------------------------------------------------------------------------

def test_ac6_running_twice_ships_each_record_once(hook, entrypoint_mix_transcript):
    """Inverted for otel-export-loss-reduction task 04 Part A, same fixture
    and root cause as test_ac1 above: 2 of the 3 rows ship (claude-desktop +
    cli; claude-vscode stays withheld as the trailing group both runs), and
    running the hook twice must not ship either of those two more than
    once."""
    state_path = entrypoint_mix_transcript.parent / "state.json"
    _seed_epoch_install(state_path)
    post = _capturing_post()
    kwargs = dict(
        projects_root=entrypoint_mix_transcript.parent, state_path=state_path,
        claude_json_path=entrypoint_mix_transcript.parent / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None,
    )
    hook.run(now=_now(), post_batch=post, **kwargs)
    hook.run(now=_now(), post_batch=post, **kwargs)
    shipped = [r for chunk in post.calls for r in chunk]
    assert len(shipped) == 2
    assert {r["entrypoint"] for r in shipped} == {"claude-desktop", "cli"}
    request_ids = [r["request_id"] for r in shipped]
    assert len(request_ids) == len(set(request_ids))  # no record shipped twice


# ---------------------------------------------------------------------------
# AC7 / AC7c: envelope 400 retry bound, and 200-with-rejections is permanent
# ---------------------------------------------------------------------------

def test_ac7_persistent_400_dropped_after_bound_state_advances(hook, tmp_path):
    root = tmp_path / "claude_projects" / "proj"
    root.mkdir(parents=True)
    row = _usage_row(
        session_id="sess-poison", request_id="req-poison", message_id="msg-poison",
        api_block_index=0, stop_reason="end_turn", input_tokens=1, output_tokens=1,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        timestamp="2026-01-01T00:00:00Z",
    )
    (root / "sess-poison.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    state_path = tmp_path / "state.json"
    _seed_epoch_install(state_path)
    kwargs = dict(
        projects_root=root.parent, state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None,
        idle_threshold_seconds=0,
    )

    bad_post = _capturing_post(outcome="envelope_reject", status=400)
    for _ in range(hook.MAX_ENVELOPE_RETRIES + 1):
        hook.run(now=_soon(), post_batch=bad_post, **kwargs)
    assert len(bad_post.calls) == hook.MAX_ENVELOPE_RETRIES + 1

    state = json.loads(state_path.read_text())
    assert any(d["kind"] == "dropped_after_retries" for d in state["drops"])

    # A further run must NOT resend the dropped record.
    good_post = _capturing_post()
    hook.run(now=_soon(), post_batch=good_post, **kwargs)
    assert good_post.calls == [] or all(len(c) == 0 for c in good_post.calls)


def test_ac7_growing_batch_poison_record_eventually_drops_others_still_ship(hook, tmp_path):
    """Regression for keying the envelope-retry counter to a hash of the
    WHOLE batch's content: on an active machine, new candidates join the
    retryable batch on every run (a newly-idle group, a fresh SessionEnd),
    so batch composition genuinely GROWS run over run. If the retry counter
    is keyed to that composition, it resets to 1 every time something new
    joins and the poison record's own count never crosses the bound --
    every later record stalls behind it forever. Keying per-record (this
    hook's actual behaviour) must let the poison record's count accumulate
    independently of whatever else rides alongside it, so it eventually
    drops while genuinely-new records -- which haven't individually
    accumulated enough attempts yet -- remain pending and ship once the
    receiver recovers."""
    root = tmp_path / "claude_projects" / "proj"
    root.mkdir(parents=True)
    poison_row = _usage_row(
        session_id="sess-poison", request_id="req-poison-0", message_id="msg-poison-0",
        api_block_index=0, stop_reason="end_turn", input_tokens=1, output_tokens=1,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        timestamp="2026-01-01T00:00:00Z",
    )
    path = root / "sess-growing.jsonl"
    path.write_text(json.dumps(poison_row) + "\n", encoding="utf-8")

    state_path = tmp_path / "state.json"
    _seed_epoch_install(state_path)
    kwargs = dict(
        projects_root=root.parent, state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None,
        idle_threshold_seconds=0,
    )

    bad_post = _capturing_post(outcome="envelope_reject", status=400)
    n_runs = hook.MAX_ENVELOPE_RETRIES + 1  # attempts needed for req-poison-0 to drop
    for i in range(n_runs):
        if i > 0:
            # A genuinely NEW record joins the batch before this run -- it
            # will have accumulated (n_runs - i) attempts by the end of the
            # loop, always <= MAX_ENVELOPE_RETRIES, so it must NOT drop.
            new_row = _usage_row(
                session_id="sess-poison", request_id=f"req-new-{i}", message_id=f"msg-new-{i}",
                api_block_index=0, stop_reason="end_turn", input_tokens=1, output_tokens=1,
                cache_creation_input_tokens=0, cache_read_input_tokens=0,
                timestamp=f"2026-01-01T00:0{i}:00Z",
            )
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(new_row) + "\n")
        hook.run(now=_soon(), post_batch=bad_post, **kwargs)

    state = json.loads(state_path.read_text())
    file_key = str(path)
    resolved = set(state["files"][file_key]["resolved"])
    assert "req-poison-0" in resolved, "the poison record must eventually drop"
    for i in range(1, n_runs):
        assert f"req-new-{i}" not in resolved, (
            f"req-new-{i} accumulated only {n_runs - i} attempt(s) and must "
            f"still be pending, not dropped alongside the poison record"
        )
    assert any(d["kind"] == "dropped_after_retries" for d in state["drops"])

    # The receiver recovers: every still-pending (non-poison) record ships.
    good_post = _capturing_post()
    hook.run(now=_soon(), post_batch=good_post, **kwargs)
    shipped_ids = {r["request_id"] for chunk in good_post.calls for r in chunk}
    assert "req-poison-0" not in shipped_ids
    assert shipped_ids == {f"req-new-{i}" for i in range(1, n_runs)}


def test_ac7c_200_with_rejections_advances_state_no_retry(hook, tmp_path):
    root = tmp_path / "claude_projects" / "proj"
    root.mkdir(parents=True)
    row = _usage_row(
        session_id="sess-rej", request_id="req-rej", message_id="msg-rej",
        api_block_index=0, stop_reason="end_turn", input_tokens=1, output_tokens=1,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        timestamp="2026-01-01T00:00:00Z",
    )
    (root / "sess-rej.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    state_path = tmp_path / "state.json"
    _seed_epoch_install(state_path)
    kwargs = dict(
        projects_root=root.parent, state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None,
        idle_threshold_seconds=0,
    )
    rejecting_post = _capturing_post(
        outcome="ok", status=200,
        body={"rejections": [{"index": 0, "request_id": "req-rej", "reason": "invalid_entrypoint"}]},
    )
    hook.run(now=_soon(), post_batch=rejecting_post, **kwargs)
    assert len(rejecting_post.calls) == 1
    state = json.loads(state_path.read_text())
    assert any(d["kind"] == "rejected_200" for d in state["drops"])

    # A second run must not resend -- the 200 was permanent.
    second_post = _capturing_post()
    hook.run(now=_soon(), post_batch=second_post, **kwargs)
    assert all(len(c) == 0 for c in second_post.calls)


# ---------------------------------------------------------------------------
# AC7b: overlapping sessions -- no global watermark
# ---------------------------------------------------------------------------

def test_ac7b_overlapping_sessions_older_ends_last_both_ship(hook, tmp_path):
    root = tmp_path / "claude_projects"
    dir_a, dir_b = root / "proj-a", root / "proj-b"
    dir_a.mkdir(parents=True)
    dir_b.mkdir(parents=True)

    row_a = _usage_row(
        session_id="sess-A", request_id="req-A", message_id="msg-A",
        api_block_index=0, stop_reason="end_turn", input_tokens=1, output_tokens=9,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        timestamp="2026-01-01T09:30:00Z",
    )
    row_b = _usage_row(
        session_id="sess-B", request_id="req-B", message_id="msg-B",
        api_block_index=0, stop_reason="end_turn", input_tokens=1, output_tokens=9,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        timestamp="2026-01-01T10:00:00Z",
    )
    path_a = dir_a / "sess-A.jsonl"
    path_b = dir_b / "sess-B.jsonl"
    path_a.write_text(json.dumps(row_a) + "\n", encoding="utf-8")
    path_b.write_text(json.dumps(row_b) + "\n", encoding="utf-8")

    state_path = tmp_path / "state.json"
    _seed_epoch_install(state_path)
    base_now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    # Session B ends first, at 10:05.
    post_b = _capturing_post()
    hook.run(
        projects_root=root, state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=str(path_b), hook_event_name="SessionEnd",
        now=base_now + timedelta(hours=10, minutes=5), post_batch=post_b,
    )
    b_shipped = [r for chunk in post_b.calls for r in chunk]
    assert any(r["request_id"] == "req-B" for r in b_shipped)

    # Session A (older records) ends LAST, at 11:00.
    post_a = _capturing_post()
    hook.run(
        projects_root=root, state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=str(path_a), hook_event_name="SessionEnd",
        now=base_now + timedelta(hours=11), post_batch=post_a,
    )
    a_shipped = [r for chunk in post_a.calls for r in chunk]
    assert any(r["request_id"] == "req-A" for r in a_shipped)


# ---------------------------------------------------------------------------
# AC7d: never-fired SessionEnd, across project directories
# ---------------------------------------------------------------------------

def test_ac7d_never_fired_session_end_across_project_dirs(hook, projects_tree):
    _seed_epoch_install(projects_tree["projects_root"].parent / "state.json")
    # Session B (project_dir_b) never had its own SessionEnd fire. Session A's
    # SessionEnd fires from a DIFFERENT project directory.
    post = _capturing_post()
    hook.run(
        projects_root=projects_tree["projects_root"],
        state_path=projects_tree["projects_root"].parent / "state.json",
        claude_json_path=projects_tree["projects_root"].parent / "missing.claude.json",
        transcript_path_hint=str(projects_tree["main_path"]),
        hook_event_name="SessionEnd", now=_soon(), post_batch=post,
        idle_threshold_seconds=0,
    )
    shipped = [r for chunk in post.calls for r in chunk]
    assert any(r["request_id"] == SECOND_PROJECT_REQUEST_ID for r in shipped)
    b_records = [r for r in shipped if r["session_id"] == SESSION_B_ID]
    assert len(b_records) == 1


# ---------------------------------------------------------------------------
# AC7f / AC7g: in-flight completeness
# ---------------------------------------------------------------------------

def test_ac7f_inflight_group_not_shipped_partially_then_ships_at_terminal(hook, inflight_transcript):
    root = inflight_transcript["path"].parent
    state_path = root / "state.json"
    _seed_epoch_install(state_path)
    t0 = _now()

    # Run 1: only the partial block exists, file just written -- withheld.
    post1 = _capturing_post()
    hook.run(
        projects_root=root, state_path=state_path,
        claude_json_path=root / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None,
        now=t0, post_batch=post1,
    )
    assert all(len(c) == 0 for c in post1.calls)

    # The terminal block arrives.
    with open(inflight_transcript["path"], "a", encoding="utf-8") as fh:
        fh.write(inflight_transcript["terminal_row_json"])

    # Run 2: idle threshold has now elapsed.
    post2 = _capturing_post()
    hook.run(
        projects_root=root, state_path=state_path,
        claude_json_path=root / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None,
        now=t0 + timedelta(seconds=hook.IDLE_THRESHOLD_SECONDS + 5), post_batch=post2,
    )
    shipped = [r for chunk in post2.calls for r in chunk]
    assert len(shipped) == 1
    assert shipped[0]["output_tokens"] == 209
    assert shipped[0]["output_tokens"] != 5


def test_ac7g_abandoned_inflight_group_still_ships(hook, inflight_transcript):
    root = inflight_transcript["path"].parent
    state_path = root / "state.json"
    _seed_epoch_install(state_path)
    t0 = _now()

    post1 = _capturing_post()
    hook.run(
        projects_root=root, state_path=state_path,
        claude_json_path=root / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None,
        now=t0, post_batch=post1,
    )
    assert all(len(c) == 0 for c in post1.calls)

    # Nothing further is EVER appended -- only the clock advances.
    post2 = _capturing_post()
    hook.run(
        projects_root=root, state_path=state_path,
        claude_json_path=root / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None,
        now=t0 + timedelta(seconds=hook.IDLE_THRESHOLD_SECONDS + 5), post_batch=post2,
    )
    shipped = [r for chunk in post2.calls for r in chunk]
    assert len(shipped) == 1
    assert shipped[0]["output_tokens"] == 5  # whatever was actually on disk


# ---------------------------------------------------------------------------
# AC7h: transport failure never drops
# ---------------------------------------------------------------------------

def test_ac7h_transport_failure_never_drops_eventually_ships(hook, tmp_path):
    root = tmp_path / "claude_projects" / "proj"
    root.mkdir(parents=True)
    row = _usage_row(
        session_id="sess-flaky", request_id="req-flaky", message_id="msg-flaky",
        api_block_index=0, stop_reason="end_turn", input_tokens=1, output_tokens=1,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        timestamp="2026-01-01T00:00:00Z",
    )
    (root / "sess-flaky.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    state_path = tmp_path / "state.json"
    _seed_epoch_install(state_path)
    kwargs = dict(
        projects_root=root.parent, state_path=state_path,
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None,
        idle_threshold_seconds=0,
    )

    n_failures = hook.MAX_ENVELOPE_RETRIES + 1
    sequence = [("transport_fail", 0, {})] * n_failures + [("ok", 200, {})]
    flaky_post = _capturing_post(sequence=sequence)

    for _ in range(n_failures):
        hook.run(now=_soon(), post_batch=flaky_post, **kwargs)
    state = json.loads(state_path.read_text())
    assert state["drops"] == []
    assert state["envelope_retries"] == {}

    # Receiver finally comes back.
    hook.run(now=_soon(), post_batch=flaky_post, **kwargs)
    shipped = [r for chunk in flaky_post.calls for r in chunk]
    assert any(r["request_id"] == "req-flaky" for r in shipped)
    state = json.loads(state_path.read_text())
    assert state["drops"] == []


# ---------------------------------------------------------------------------
# _default_post_batch itself -- driving the REAL classification logic, not
# an injected outcome. Every other test in this file replaces post_batch
# with a fake, which means _default_post_batch's own try/except and status-
# code branching is never exercised anywhere else. Mutation M13 (making
# _default_post_batch classify connection-refused/DNS/timeout/TLS as
# 'envelope_reject' instead of 'transport_fail') survived the full suite
# without these tests -- that is the offline-laptop data-loss bug AC7h
# exists to prevent, invisible to the test named for it.
# ---------------------------------------------------------------------------

def test_default_post_batch_transport_fail_on_real_connection_refused(hook, monkeypatch):
    # No listener on this port -- a real connection attempt, refused by the
    # OS. Not binding a port ourselves; just attempting an outbound connect.
    monkeypatch.setattr(hook, "RECEIVER", "http://127.0.0.1:1")
    monkeypatch.setattr(hook, "TIMEOUT", 0.5)
    outcome, status, body = hook._default_post_batch([{"session_id": "s", "request_id": "r"}])
    assert outcome == "transport_fail"


def test_default_post_batch_classifies_400_as_envelope_reject(hook, monkeypatch):
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, None)

    monkeypatch.setattr(hook.urllib.request, "urlopen", fake_urlopen)
    outcome, status, body = hook._default_post_batch([{"session_id": "s", "request_id": "r"}])
    assert outcome == "envelope_reject"
    assert status == 400


@pytest.mark.parametrize("code", [401, 403, 408, 429, 500, 503])
def test_default_post_batch_classifies_401_and_5xx_as_transport_fail_retryable(hook, monkeypatch, code):
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, code, "error", {}, None)

    monkeypatch.setattr(hook.urllib.request, "urlopen", fake_urlopen)
    outcome, status, body = hook._default_post_batch([{"session_id": "s", "request_id": "r"}])
    assert outcome == "transport_fail", (
        f"HTTP {code} must classify as transport_fail (retry-forever), never "
        f"envelope_reject -- a 401 from a mis-substituted fleet token must "
        f"self-heal once the token is fixed, not permanently drop billing "
        f"after MAX_ENVELOPE_RETRIES."
    )


def test_default_post_batch_classifies_200_as_ok(hook, monkeypatch):
    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"inserted": 1, "rejections": []}'

        def getcode(self):
            return 200

    monkeypatch.setattr(hook.urllib.request, "urlopen", lambda req, timeout=None: _FakeResp())
    outcome, status, body = hook._default_post_batch([{"session_id": "s", "request_id": "r"}])
    assert outcome == "ok"
    assert status == 200
    assert body["inserted"] == 1


def test_default_post_batch_http_client_exception_is_transport_fail(hook, monkeypatch):
    import http.client

    def fake_urlopen(req, timeout=None):
        raise http.client.BadStatusLine("garbage")

    monkeypatch.setattr(hook.urllib.request, "urlopen", fake_urlopen)
    outcome, status, body = hook._default_post_batch([{"session_id": "s", "request_id": "r"}])
    assert outcome == "transport_fail"


def test_default_post_batch_incomplete_read_is_transport_fail(hook, monkeypatch):
    import http.client

    def fake_urlopen(req, timeout=None):
        raise http.client.IncompleteRead(b"partial")

    monkeypatch.setattr(hook.urllib.request, "urlopen", fake_urlopen)
    outcome, status, body = hook._default_post_batch([{"session_id": "s", "request_id": "r"}])
    assert outcome == "transport_fail"


# ---------------------------------------------------------------------------
# AC7e: forward-only install watermark
# ---------------------------------------------------------------------------

def test_ac7e_forward_only_install_watermark(hook, tmp_path):
    root = tmp_path / "claude_projects" / "proj"
    root.mkdir(parents=True)
    old_row = _usage_row(
        session_id="sess-fwd", request_id="req-old", message_id="msg-old",
        api_block_index=0, stop_reason="end_turn", input_tokens=1, output_tokens=1,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        timestamp="2020-01-01T00:00:00Z",
    )
    new_row = _usage_row(
        session_id="sess-fwd", request_id="req-new", message_id="msg-new",
        api_block_index=0, stop_reason="end_turn", input_tokens=1, output_tokens=1,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        timestamp="2026-06-01T00:00:00Z",
    )
    path = root / "sess-fwd.jsonl"
    path.write_text(json.dumps(old_row) + "\n" + json.dumps(new_row) + "\n", encoding="utf-8")

    install_now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    post = _capturing_post()
    hook.run(
        projects_root=root.parent, state_path=tmp_path / "state.json",
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=str(path), hook_event_name="SessionEnd",
        now=install_now, post_batch=post,
    )
    shipped = [r for chunk in post.calls for r in chunk]
    ids = {r["request_id"] for r in shipped}
    assert "req-new" in ids
    assert "req-old" not in ids


# ---------------------------------------------------------------------------
# AC8: never opens ~/.claude/.credentials.json
# ---------------------------------------------------------------------------

def test_ac8_never_reads_credentials_json_static(hook):
    # Comments/docstrings are allowed to MENTION the filename as a design
    # note (explaining what this hook deliberately does NOT read); what must
    # never appear is a QUOTED STRING LITERAL of that name, which is what
    # constructing/opening such a path would require.
    assert '".credentials.json"' not in _HOOK_SOURCE
    assert "'.credentials.json'" not in _HOOK_SOURCE
    assert hook._claude_json_path().name == ".claude.json"


def test_ac8_never_reads_credentials_json_dynamic(hook, tmp_path):
    fake_home = tmp_path / "home"
    claude_dir = fake_home / ".claude"
    claude_dir.mkdir(parents=True)
    poison = "POISON_CREDENTIAL_VALUE_MUST_NEVER_SHIP"
    (claude_dir / ".credentials.json").write_text(
        json.dumps({"secret": poison}), encoding="utf-8")
    (fake_home / ".claude.json").write_text(
        json.dumps({"oauthAccount": {"emailAddress": "dev@cyclotron.com",
                                       "accountUuid": "u-1", "organizationUuid": "org-1"}}),
        encoding="utf-8")
    root = claude_dir / "projects" / "proj"
    root.mkdir(parents=True)
    row = _usage_row(
        session_id="sess-cred", request_id="req-cred", message_id="msg-cred",
        api_block_index=0, stop_reason="end_turn", input_tokens=1, output_tokens=1,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        timestamp="2026-01-01T00:00:00Z",
    )
    (root / "sess-cred.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    state_path = tmp_path / "state.json"
    _seed_epoch_install(state_path)
    post = _capturing_post()
    hook.run(
        projects_root=root.parent, state_path=state_path,
        claude_json_path=fake_home / ".claude.json",
        transcript_path_hint=None, hook_event_name=None, now=_soon(), post_batch=post,
        idle_threshold_seconds=0,
    )
    shipped = [r for chunk in post.calls for r in chunk]
    assert shipped and shipped[0]["user_email"] == "dev@cyclotron.com"
    assert poison not in json.dumps(shipped)
    state_text = (tmp_path / "state.json").read_text(encoding="utf-8")
    assert poison not in state_text


# ---------------------------------------------------------------------------
# Structural: CLAUDE_CONFIG_DIR honored; zero-files-under-root is logged
# ---------------------------------------------------------------------------

def test_config_dir_honors_env_var(hook, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/custom/config/dir")
    assert hook._config_dir() == Path("/custom/config/dir")
    assert hook._projects_root(hook._config_dir()) == Path("/custom/config/dir/projects")


def test_config_dir_defaults_to_home_claude(hook, monkeypatch):
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    assert hook._config_dir() == Path(os.path.expanduser("~/.claude"))


def test_zero_files_sweep_logs_locally(hook, tmp_path):
    missing_root = tmp_path / "does-not-exist"
    log_path = tmp_path / "hook.log"
    post = _capturing_post()
    hook.run(
        projects_root=missing_root, state_path=tmp_path / "state.json",
        claude_json_path=tmp_path / "missing.claude.json",
        transcript_path_hint=None, hook_event_name=None,
        now=_now(), post_batch=post, log_path=log_path,
    )
    assert log_path.exists()
    assert "zero transcript files" in log_path.read_text(encoding="utf-8")
    assert post.calls == []


# ---------------------------------------------------------------------------
# Enumeration: recursive from the root, never derived from transcript_path
# ---------------------------------------------------------------------------

def test_recursive_enumeration_finds_sidechain_file_flat_glob_does_not(hook, projects_tree):
    recursive = hook.find_transcript_files(projects_tree["projects_root"])
    assert projects_tree["sidechain_path"] in recursive
    assert projects_tree["second_project_path"] in recursive

    flat = sorted(projects_tree["project_dir_a"].glob("*.jsonl"))
    assert projects_tree["sidechain_path"] not in flat


# ---------------------------------------------------------------------------
# _save_state's replace retry -- regression for a real, reproduced flake.
#
# Root cause (captured directly, not inferred): `Path.replace()` on the
# state file can raise a transient `PermissionError(13, 'Access is denied')`
# on Windows -- most plausibly real-time antivirus briefly holding the
# freshly-written temp file open at the exact moment of rename. Reproduced
# via a tight loop of `hook.run()` calls against a real filesystem: roughly
# 1 in 50-150 runs hit it. Under the OLD save path (a single un-retried
# `tmp.replace(state_path)`), that single lost save silently drops one
# run's worth of envelope-retry increments -- not a correctness bug in the
# retry logic itself (which is exercised elsewhere and is correct), but
# enough to make a test asserting an EXACT attempt count intermittently
# fail. `_replace_with_retry` makes the transient-lock case retry a few
# times with a short delay before giving up, which is what these tests
# pin directly rather than relying solely on "the flake went away".
# ---------------------------------------------------------------------------

def test_replace_with_retry_recovers_from_transient_permission_error(hook, tmp_path, monkeypatch):
    tmp = tmp_path / "state.json.tmp"
    dest = tmp_path / "state.json"
    tmp.write_text("{}", encoding="utf-8")

    real_replace = Path.replace
    calls = {"n": 0}

    def flaky_replace(self, target):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(13, "Access is denied")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)
    monkeypatch.setattr(hook, "_REPLACE_RETRY_DELAY_SECONDS", 0.0)  # don't slow the test down
    hook._replace_with_retry(tmp, dest)  # must not raise -- recovers on the 3rd attempt
    assert calls["n"] == 3
    assert dest.exists()


def test_replace_with_retry_gives_up_after_exhausting_attempts(hook, tmp_path, monkeypatch):
    tmp = tmp_path / "state.json.tmp"
    dest = tmp_path / "state.json"
    tmp.write_text("{}", encoding="utf-8")

    def always_locked(self, target):
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(Path, "replace", always_locked)
    monkeypatch.setattr(hook, "_REPLACE_RETRY_DELAY_SECONDS", 0.0)
    with pytest.raises(PermissionError):
        hook._replace_with_retry(tmp, dest)


def test_save_state_still_never_raises_when_replace_permanently_locked(hook, tmp_path, monkeypatch):
    """The always-exit-0 guarantee: even if every retry is exhausted,
    `_save_state`'s own `except OSError` still swallows it -- the retry
    helper does not weaken that contract."""
    state_path = tmp_path / "state.json"

    def always_locked(self, target):
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(Path, "replace", always_locked)
    monkeypatch.setattr(hook, "_REPLACE_RETRY_DELAY_SECONDS", 0.0)
    hook._save_state(state_path, {"hello": "world"})  # must not raise
