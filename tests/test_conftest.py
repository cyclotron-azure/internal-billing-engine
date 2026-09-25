"""Pin the fixture invariants task 00's fixtures exist to guarantee.

These are not tests of production code -- there is none yet in this goal's
scope. They pin the SHAPE of the fixtures in `tests/conftest.py` itself, so a
later edit to conftest.py cannot silently drift the legacy schema, the
cumulative-block/duplicate-pair shapes, or the nested projects tree out from
under the tasks (01, 02, 03, 06, 07) that build targeted tests on top of them.
Task 06's anti-fixture criterion in particular depends on this tree being
genuinely nested -- if nothing here pins that, it can regress unnoticed and
take that regression test down with it.
"""

from __future__ import annotations

import glob
import json
import sqlite3
from pathlib import Path

import pytest

from billing.otel.otel_store import OtelStore
from billing.otel.receiver import _attrs, _datapoints

from tests.conftest import (
    AGENT_1_ID,
    COWORK_COST_USD,
    COWORK_INPUT_TOKENS,
    COWORK_LOOKUP_SESSION_ID,
    COWORK_OUTPUT_TOKENS,
    COWORK_SERVICE_NAME,
    COWORK_TERMINAL_TYPE,
    COWORK_USER_EMAIL,
    DUPLICATE_CACHE_CREATION,
    DUPLICATE_CACHE_READ,
    DUPLICATE_INPUT,
    DUPLICATE_OUTPUT,
    ENTRYPOINT_MIX_ENTRYPOINTS,
    EXPECTED_COMBINED_TOTAL_TOKENS,
    EXPECTED_MAIN_ONLY_TOTAL_TOKENS,
    EXPECTED_MAIN_ONLY_TOTALS,
    EXPECTED_SIDECHAIN_ONLY_TOTAL_TOKENS,
    EXPECTED_SIDECHAIN_ONLY_TOTALS,
    INFLIGHT_OUTPUT_PARTIAL,
    INFLIGHT_OUTPUT_TERMINAL,
    INFLIGHT_REQUEST_ID,
    INFLIGHT_SESSION_ID,
    MULTI_BLOCK_CACHE_CREATION,
    MULTI_BLOCK_CACHE_READ,
    MULTI_BLOCK_INPUT,
    MULTI_BLOCK_OUTPUT_PARTIAL,
    MULTI_BLOCK_OUTPUT_TERMINAL,
    MULTI_BLOCK_REQUEST_ID,
    DUPLICATE_REQUEST_ID,
    SESSION_A_ID,
    build_cowork_metrics_payload,
    capture_cowork_isolation_baseline,
)

GOLDEN_DIR = Path(__file__).parent / "golden"
COWORK_BASELINE_PATH = GOLDEN_DIR / "cowork_isolation_baseline.txt"

# The 8 tables the pre-change schema defines, per otel_store.py lines 19-122.
LEGACY_TABLES = {
    "token_usage",
    "cost_usage",
    "session_repo_timeline",
    "repo_name_map",
    "invoices",
    "invoice_line_items",
    "fabric_outbox",
    "meta",
}


def _read_jsonl_lines(path) -> list[str]:
    return path.read_text(encoding="utf-8").split("\n")


def _parse_valid_rows(lines: list[str]) -> tuple[list[dict], list[str]]:
    """Split JSONL lines into (parsed rows, lines that failed to parse)."""
    rows, bad = [], []
    for line in lines:
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            bad.append(line)
    return rows, bad


_TOKEN_CATEGORIES = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def _group_by_request_and_message(rows: list[dict]) -> dict:
    """Group usage-bearing rows by (requestId, message.id), preserving file
    order within each group -- exactly the grouping key task 06's hook uses."""
    groups: dict = {}
    for row in rows:
        key = (row["requestId"], row["message"]["id"])
        groups.setdefault(key, []).append(row)
    return groups


def _terminal_row(group: list[dict]) -> dict:
    """The terminal row of a (requestId, message.id) group: highest
    apiBlockIndex, tie-break last-in-file-order wins. Absent apiBlockIndex is
    treated as lower than every present value (mirrors task 06's rule)."""
    best = None
    best_idx = None
    for row in group:
        idx = row.get("apiBlockIndex", -1)
        if best is None or idx >= best_idx:
            best, best_idx = row, idx
    return best


def _first_row(group: list[dict]) -> dict:
    """The first (lowest-apiBlockIndex, earliest-in-file) row of a group --
    the wrong selection an INSERT-OR-IGNORE-only implementation would keep."""
    best = None
    best_idx = None
    for row in group:
        idx = row.get("apiBlockIndex", -1)
        if best is None or idx < best_idx:
            best, best_idx = row, idx
    return best


def _recompute_totals_from_rows(rows: list[dict]) -> dict:
    """Recompute the billable totals a correct collapser would produce: group
    by (requestId, message.id), select each group's terminal row, sum the four
    token categories across groups. This is independent of, and does not
    reference, the EXPECTED_* constants -- it derives the numbers fresh from
    the fixture file's own bytes."""
    groups = _group_by_request_and_message(rows)
    totals = {c: 0 for c in _TOKEN_CATEGORIES}
    for group in groups.values():
        terminal = _terminal_row(group)
        usage = terminal["message"]["usage"]
        for c in _TOKEN_CATEGORIES:
            totals[c] += usage[c]
    return totals


def _naive_sum_totals_from_rows(rows: list[dict]) -> dict:
    """The over-billing failure mode: sum every row's usage with no grouping
    at all (as blindly summing cumulative snapshots would)."""
    totals = {c: 0 for c in _TOKEN_CATEGORIES}
    for row in rows:
        usage = row["message"]["usage"]
        for c in _TOKEN_CATEGORIES:
            totals[c] += usage[c]
    return totals


def _first_block_totals_from_rows(rows: list[dict]) -> dict:
    """The under-billing failure mode: keep only each group's FIRST
    (lowest-apiBlockIndex) row, as a naive INSERT-OR-IGNORE dedupe would."""
    groups = _group_by_request_and_message(rows)
    totals = {c: 0 for c in _TOKEN_CATEGORIES}
    for group in groups.values():
        first = _first_row(group)
        usage = first["message"]["usage"]
        for c in _TOKEN_CATEGORIES:
            totals[c] += usage[c]
    return totals


# ---------------------------------------------------------------------------
# AC2 -- legacy-schema fixture lacks usage_source / entrypoint / cost_source,
# and has exactly the 8 tables the pre-change schema defines.
# ---------------------------------------------------------------------------

def test_legacy_schema_lacks_new_token_usage_columns(legacy_schema_db_path):
    conn = sqlite3.connect(legacy_schema_db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(token_usage)")}
    finally:
        conn.close()
    assert "usage_source" not in cols
    assert "entrypoint" not in cols


def test_legacy_schema_lacks_new_cost_usage_columns(legacy_schema_db_path):
    conn = sqlite3.connect(legacy_schema_db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(cost_usage)")}
    finally:
        conn.close()
    assert "usage_source" not in cols
    assert "cost_source" not in cols


def test_legacy_schema_has_the_pre_change_tables(legacy_schema_db_path):
    conn = sqlite3.connect(legacy_schema_db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        conn.close()
    assert LEGACY_TABLES <= tables


# ---------------------------------------------------------------------------
# AC3 -- entrypoint-mix transcript: all three entrypoints, plus a malformed
# trailing line that is genuinely unparseable as JSON.
# ---------------------------------------------------------------------------

def test_entrypoint_mix_contains_all_three_entrypoints(entrypoint_mix_transcript):
    lines = _read_jsonl_lines(entrypoint_mix_transcript)
    rows, _bad = _parse_valid_rows(lines)
    seen = {row["entrypoint"] for row in rows}
    assert seen == set(ENTRYPOINT_MIX_ENTRYPOINTS)


def test_entrypoint_mix_trailing_line_is_malformed(entrypoint_mix_transcript):
    lines = _read_jsonl_lines(entrypoint_mix_transcript)
    trailing = lines[-1]
    assert trailing.strip() != ""
    with pytest.raises(json.JSONDecodeError):
        json.loads(trailing)


# ---------------------------------------------------------------------------
# AC3b -- cumulative multi-block group + exact-duplicate pair.
# ---------------------------------------------------------------------------

def test_multiblock_group_terminal_is_highest_api_block_index(projects_tree):
    rows, _bad = _parse_valid_rows(_read_jsonl_lines(projects_tree["main_path"]))
    group = [r for r in rows if r["requestId"] == MULTI_BLOCK_REQUEST_ID]
    assert len(group) == 2

    terminal = max(group, key=lambda r: r["apiBlockIndex"])
    terminal_output = terminal["message"]["usage"]["output_tokens"]

    assert terminal_output == MULTI_BLOCK_OUTPUT_TERMINAL == 209
    # Ground the other three terminal-row values against both the constant and
    # the hard literal too -- these four numbers are duplicated on purpose in
    # task 06's criterion 1b, so a coordinated fixture+constant drift here
    # would otherwise slip through unnoticed. Do not "de-duplicate" this into
    # a shared constant; that would reopen the coordinated-drift hole.
    assert terminal["message"]["usage"]["input_tokens"] == MULTI_BLOCK_INPUT == 2
    assert terminal["message"]["usage"]["cache_creation_input_tokens"] == MULTI_BLOCK_CACHE_CREATION == 13984
    assert terminal["message"]["usage"]["cache_read_input_tokens"] == MULTI_BLOCK_CACHE_READ == 35774
    # Neither the sum over the group nor the first (lowest-index) block.
    summed = sum(r["message"]["usage"]["output_tokens"] for r in group)
    first_block = min(group, key=lambda r: r["apiBlockIndex"])
    assert summed == 214
    assert terminal_output != summed
    assert terminal_output != first_block["message"]["usage"]["output_tokens"] == MULTI_BLOCK_OUTPUT_PARTIAL == 5


def test_multiblock_group_input_and_cache_constant_output_grows(projects_tree):
    rows, _bad = _parse_valid_rows(_read_jsonl_lines(projects_tree["main_path"]))
    group = [r for r in rows if r["requestId"] == MULTI_BLOCK_REQUEST_ID]
    usages = [r["message"]["usage"] for r in group]

    assert len({u["input_tokens"] for u in usages}) == 1
    assert len({u["cache_creation_input_tokens"] for u in usages}) == 1
    assert len({u["cache_read_input_tokens"] for u in usages}) == 1
    outputs = sorted(u["output_tokens"] for u in usages)
    assert outputs == sorted([MULTI_BLOCK_OUTPUT_PARTIAL, MULTI_BLOCK_OUTPUT_TERMINAL])
    assert outputs[0] < outputs[1]


def test_duplicate_pair_both_rows_carry_non_null_stop_reason(projects_tree):
    rows, _bad = _parse_valid_rows(_read_jsonl_lines(projects_tree["main_path"]))
    group = [r for r in rows if r["requestId"] == DUPLICATE_REQUEST_ID]
    assert len(group) == 2

    # This is the fact that proves stop_reason ALONE cannot identify the
    # terminal block: both rows are non-null, so a non-null check can't
    # distinguish them -- only highest apiBlockIndex can.
    assert all(r["message"]["stop_reason"] is not None for r in group)
    assert {r["message"]["stop_reason"] for r in group} == {"end_turn"}

    usages = [r["message"]["usage"] for r in group]
    assert usages[0] == usages[1]
    assert usages[0]["output_tokens"] == DUPLICATE_OUTPUT
    assert usages[0]["input_tokens"] == DUPLICATE_INPUT
    assert usages[0]["cache_creation_input_tokens"] == DUPLICATE_CACHE_CREATION
    assert usages[0]["cache_read_input_tokens"] == DUPLICATE_CACHE_READ


# ---------------------------------------------------------------------------
# AC3c -- sidechain at the exact relative path; second project directory;
# combined strictly greater than main-only.
# ---------------------------------------------------------------------------

def test_sidechain_file_at_exact_relative_path(projects_tree):
    expected = (
        projects_tree["project_dir_a"]
        / SESSION_A_ID
        / "subagents"
        / f"agent-{AGENT_1_ID}.jsonl"
    )
    assert projects_tree["sidechain_path"] == expected
    assert projects_tree["sidechain_path"].is_file()
    # single-prefixed, not agent-agent-...
    assert projects_tree["sidechain_path"].name == f"agent-{AGENT_1_ID}.jsonl"
    assert not projects_tree["sidechain_path"].name.startswith("agent-agent-")


def test_sidechain_rows_are_flagged_and_carry_parent_identity(projects_tree):
    rows, _bad = _parse_valid_rows(_read_jsonl_lines(projects_tree["sidechain_path"]))
    assert rows
    assert all(r["isSidechain"] is True for r in rows)
    assert all(r["sessionId"] == SESSION_A_ID for r in rows)
    assert all(r["entrypoint"] == "claude-desktop" for r in rows)


def test_second_project_directory_exists_and_is_distinct(projects_tree):
    dir_a = projects_tree["project_dir_a"]
    dir_b = projects_tree["project_dir_b"]
    assert dir_b.is_dir()
    assert dir_b != dir_a
    assert projects_tree["second_project_path"].is_file()
    assert projects_tree["second_project_path"].parent == dir_b


def test_published_totals_combined_strictly_greater_than_main_only(transcript_expected_totals):
    main_total = transcript_expected_totals["main_only"]["total"]
    combined_total = transcript_expected_totals["combined_total"]
    assert combined_total > main_total


# ---------------------------------------------------------------------------
# AC3d -- flat glob of the first project directory finds strictly fewer files
# than a recursive walk of it.
# ---------------------------------------------------------------------------

def test_flat_glob_finds_fewer_files_than_recursive_walk(projects_tree):
    dir_a = projects_tree["project_dir_a"]
    flat = glob.glob(str(dir_a / "*.jsonl"))
    recursive = glob.glob(str(dir_a / "**" / "*.jsonl"), recursive=True)

    assert len(flat) == 1
    assert len(recursive) == 2  # main + sidechain, one level deeper
    assert len(flat) < len(recursive)


def test_flat_glob_of_projects_root_misses_sidechain_and_is_fewer_than_full_recursive_walk(
    projects_tree,
):
    root = projects_tree["projects_root"]
    flat_per_dir = glob.glob(str(root / "*" / "*.jsonl"))
    recursive_root = glob.glob(str(root / "**" / "*.jsonl"), recursive=True)

    assert len(flat_per_dir) == 2  # main_path + second_project_path only
    assert len(recursive_root) == 3  # + sidechain_path
    assert len(flat_per_dir) < len(recursive_root)


# ---------------------------------------------------------------------------
# Published totals are recomputed FROM THE FIXTURE FILES (not compared against
# the same constants used to build them), and match EXPECTED_*. This is the
# test that actually exercises the fixture bytes: it opens main_path and
# sidechain_path, groups rows by (requestId, message.id), selects each group's
# terminal row by highest apiBlockIndex, and only THEN compares the recomputed
# sums to the published constants. A published total with no relation to the
# fixture (e.g. mutated to the naive over-billing sum) fails here.
# ---------------------------------------------------------------------------

def test_recomputed_main_only_totals_match_published(projects_tree):
    main_rows, _bad = _parse_valid_rows(_read_jsonl_lines(projects_tree["main_path"]))

    recomputed = _recompute_totals_from_rows(main_rows)
    assert recomputed == EXPECTED_MAIN_ONLY_TOTALS
    assert sum(recomputed.values()) == EXPECTED_MAIN_ONLY_TOTAL_TOKENS

    # AC 3b: the published output total is neither the naive sum over every
    # row nor the sum of each group's first (lowest-apiBlockIndex) block.
    naive_sum = _naive_sum_totals_from_rows(main_rows)
    first_block = _first_block_totals_from_rows(main_rows)
    assert EXPECTED_MAIN_ONLY_TOTALS["output_tokens"] != naive_sum["output_tokens"]
    assert EXPECTED_MAIN_ONLY_TOTALS["output_tokens"] != first_block["output_tokens"]
    # Ground the failure modes in concrete numbers so this can't quietly pass
    # if the fixture's shape ever collapses to a single row per group.
    assert naive_sum["output_tokens"] == (
        MULTI_BLOCK_OUTPUT_PARTIAL + MULTI_BLOCK_OUTPUT_TERMINAL + DUPLICATE_OUTPUT * 2
    )
    assert first_block["output_tokens"] == MULTI_BLOCK_OUTPUT_PARTIAL + DUPLICATE_OUTPUT


def test_recomputed_sidechain_only_totals_match_published(projects_tree):
    sidechain_rows, _bad = _parse_valid_rows(
        _read_jsonl_lines(projects_tree["sidechain_path"])
    )

    recomputed = _recompute_totals_from_rows(sidechain_rows)
    assert recomputed == EXPECTED_SIDECHAIN_ONLY_TOTALS
    assert sum(recomputed.values()) == EXPECTED_SIDECHAIN_ONLY_TOTAL_TOKENS


def test_recomputed_combined_totals_match_published_and_exceed_main_only(projects_tree):
    main_rows, _bad_a = _parse_valid_rows(_read_jsonl_lines(projects_tree["main_path"]))
    sidechain_rows, _bad_b = _parse_valid_rows(
        _read_jsonl_lines(projects_tree["sidechain_path"])
    )

    main_recomputed = _recompute_totals_from_rows(main_rows)
    sidechain_recomputed = _recompute_totals_from_rows(sidechain_rows)

    main_total = sum(main_recomputed.values())
    sidechain_total = sum(sidechain_recomputed.values())
    combined_total = main_total + sidechain_total

    assert main_total == EXPECTED_MAIN_ONLY_TOTAL_TOKENS
    assert sidechain_total == EXPECTED_SIDECHAIN_ONLY_TOTAL_TOKENS
    assert combined_total == EXPECTED_COMBINED_TOTAL_TOKENS
    assert combined_total > main_total


# ---------------------------------------------------------------------------
# inflight_transcript -- trailing group holds only apiBlockIndex=0; the
# terminal row is supplied separately for a test to append. Task 06's
# in-flight completeness rule (criteria 7f/7g) is built entirely on this
# fixture, so pin its shape here.
# ---------------------------------------------------------------------------

def test_inflight_transcript_trailing_group_holds_only_partial_block(inflight_transcript):
    rows, bad = _parse_valid_rows(_read_jsonl_lines(inflight_transcript["path"]))
    assert not bad
    assert len(rows) == 1

    row = rows[0]
    assert row["sessionId"] == INFLIGHT_SESSION_ID
    assert row["requestId"] == INFLIGHT_REQUEST_ID
    assert row["apiBlockIndex"] == 0
    assert row["message"]["usage"]["output_tokens"] == INFLIGHT_OUTPUT_PARTIAL == 5


def test_inflight_transcript_terminal_row_supplied_separately(inflight_transcript):
    terminal = inflight_transcript["terminal_row"]
    assert terminal["sessionId"] == INFLIGHT_SESSION_ID
    assert terminal["requestId"] == INFLIGHT_REQUEST_ID
    assert terminal["apiBlockIndex"] == 1
    assert terminal["message"]["usage"]["output_tokens"] == INFLIGHT_OUTPUT_TERMINAL == 209

    # The terminal row is not yet on disk -- the file still holds only the
    # partial block until a test appends terminal_row_json itself.
    on_disk, _bad = _parse_valid_rows(_read_jsonl_lines(inflight_transcript["path"]))
    assert all(r["apiBlockIndex"] == 0 for r in on_disk)

    # Appending it and re-parsing produces the complete, terminal-selected group.
    with open(inflight_transcript["path"], "a", encoding="utf-8", newline="") as f:
        f.write(inflight_transcript["terminal_row_json"])
    rows_after, bad_after = _parse_valid_rows(_read_jsonl_lines(inflight_transcript["path"]))
    assert not bad_after
    assert len(rows_after) == 2
    group = _group_by_request_and_message(rows_after)[(INFLIGHT_REQUEST_ID, terminal["message"]["id"])]
    assert _terminal_row(group)["message"]["usage"]["output_tokens"] == INFLIGHT_OUTPUT_TERMINAL


# ---------------------------------------------------------------------------
# seeded_otlp_db_path / tmp_db_path -- basic shape pins so a conftest.py edit
# to these fixtures cannot silently drift unnoticed either.
# ---------------------------------------------------------------------------

def test_tmp_db_path_is_under_tmp_path_and_not_yet_created(tmp_db_path, tmp_path):
    from pathlib import Path

    p = Path(tmp_db_path)
    # Under tmp_path, never data/otel.db or any shared path.
    assert p.parent == tmp_path
    assert not p.exists()
    assert "data" not in p.parts


def test_seeded_otlp_db_path_has_expected_row_counts(seeded_otlp_db_path):
    conn = sqlite3.connect(seeded_otlp_db_path)
    try:
        token_rows = conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0]
        cost_rows = conn.execute("SELECT COUNT(*) FROM cost_usage").fetchone()[0]
        timeline_rows = conn.execute(
            "SELECT COUNT(*) FROM session_repo_timeline"
        ).fetchone()[0]
        distinct_sessions = conn.execute(
            "SELECT COUNT(DISTINCT session_id) FROM token_usage"
        ).fetchone()[0]
    finally:
        conn.close()

    # 3 seeded sessions x 4 token types each = 12 token_usage rows.
    assert token_rows == 12
    assert cost_rows == 3
    assert distinct_sessions == 3
    # Exactly one seeded session carries a session_repo_timeline entry.
    assert timeline_rows == 1


# ---------------------------------------------------------------------------
# Task 00 (cowork-telemetry-ingest goal) -- fixtures for the new Cowork
# ingestion pipeline, and the pre-goal golden isolation baseline capture.
# ---------------------------------------------------------------------------

def test_cowork_db_path_is_under_tmp_path_and_distinct_from_other_db_fixtures(
    cowork_db_path, tmp_path, tmp_db_path,
):
    p = Path(cowork_db_path)
    assert p.parent == tmp_path
    assert not p.exists()
    assert "data" not in p.parts
    assert cowork_db_path != tmp_db_path


def test_seeded_otlp_db_path_doubles_as_the_cowork_lookup_fixture(seeded_otlp_db_path):
    """Task 00's 'read-only-lookup fixture' requirement: a session that
    carries BOTH a session_repo_timeline row and a matching
    token_usage/cost_usage row for the SAME session_id. seeded_otlp_db_path
    already satisfies this (SEEDED_SESSIONS[0], re-exported as
    COWORK_LOOKUP_SESSION_ID) -- no parallel fixture is built for it."""
    conn = sqlite3.connect(seeded_otlp_db_path)
    try:
        timeline_rows = conn.execute(
            "SELECT COUNT(*) FROM session_repo_timeline WHERE session_id=?",
            (COWORK_LOOKUP_SESSION_ID,),
        ).fetchone()[0]
        token_rows = conn.execute(
            "SELECT COUNT(*) FROM token_usage WHERE session_id=?",
            (COWORK_LOOKUP_SESSION_ID,),
        ).fetchone()[0]
        cost_rows = conn.execute(
            "SELECT COUNT(*) FROM cost_usage WHERE session_id=?",
            (COWORK_LOOKUP_SESSION_ID,),
        ).fetchone()[0]
    finally:
        conn.close()
    assert timeline_rows >= 1
    assert token_rows >= 1
    assert cost_rows >= 1


def test_seeded_otlp_db_path_schema_matches_current_otel_store_schema_exactly(
    seeded_otlp_db_path, tmp_path,
):
    """AC2: the existing-otel.db fixture's schema matches otel_store.py's
    real SCHEMA exactly -- built by importing/executing it (OtelStore(path)
    runs the real, current SCHEMA), never hand-copied. Verified by comparing
    PRAGMA table_info across every table against an INDEPENDENTLY built
    fresh OtelStore, not merely asserting the fixture is internally
    consistent with itself."""
    fresh = OtelStore(str(tmp_path / "fresh_for_schema_check.db"))
    try:
        conn = sqlite3.connect(seeded_otlp_db_path)
        try:
            fixture_tables = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")
            }
            fresh_tables = {
                row[0] for row in fresh.db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")
            }
            assert fixture_tables == fresh_tables
            assert fixture_tables  # sanity: not comparing two empty sets
            for table in sorted(fixture_tables):
                # `conn` is a plain sqlite3 connection (tuples); `fresh.db` is
                # an OtelStore connection with row_factory=sqlite3.Row --
                # normalize both to plain tuples before comparing, since
                # sqlite3.Row does not compare equal to a plain tuple.
                fixture_cols = [
                    tuple(row) for row in
                    conn.execute(f"PRAGMA table_info({table})").fetchall()
                ]
                fresh_cols = [
                    tuple(row) for row in
                    fresh.db.execute(f"PRAGMA table_info({table})").fetchall()
                ]
                assert fixture_cols == fresh_cols, (
                    f"table_info({table}) diverged between the fixture db "
                    f"and a freshly-built OtelStore")
        finally:
            conn.close()
    finally:
        fresh.close()


def test_cowork_metrics_payload_attrs_and_datapoints_are_exact(cowork_metrics_payload):
    """AC3: run the fixture through receiver.py's OWN _attrs/_datapoints
    helpers and assert EXACT values -- proving this is a realistic,
    correctly-shaped OTLP payload, not merely that parsing didn't crash."""
    rm = cowork_metrics_payload["resourceMetrics"][0]
    resource_attrs = _attrs(rm["resource"]["attributes"])
    assert resource_attrs == {
        "service.name": COWORK_SERVICE_NAME,
        "terminal.type": COWORK_TERMINAL_TYPE,
        "session.id": COWORK_LOOKUP_SESSION_ID,
        "user.email": COWORK_USER_EMAIL,
    }

    metrics = rm["scopeMetrics"][0]["metrics"]
    token_metric = next(m for m in metrics if m["name"] == "claude_code.token.usage")
    cost_metric = next(m for m in metrics if m["name"] == "claude_code.cost.usage")

    token_dps = _datapoints(token_metric)
    assert len(token_dps) == 2
    by_type = {
        _attrs(dp["attributes"])["type"]: int(dp["asInt"]) for dp in token_dps
    }
    assert by_type == {"input": COWORK_INPUT_TOKENS, "output": COWORK_OUTPUT_TOKENS}

    cost_dps = _datapoints(cost_metric)
    assert len(cost_dps) == 1
    assert cost_dps[0]["asDouble"] == COWORK_COST_USD


@pytest.mark.parametrize("service_name", ["claude-code", None, "some-unrecognized-value"])
def test_cowork_payload_service_name_is_swappable(service_name):
    payload = build_cowork_metrics_payload(service_name=service_name)
    resource_attrs = _attrs(payload["resourceMetrics"][0]["resource"]["attributes"])
    if service_name is None:
        assert "service.name" not in resource_attrs
    else:
        assert resource_attrs["service.name"] == service_name
    # Swapping service_name never disturbs the rest of the payload's shape.
    assert resource_attrs["session.id"] == COWORK_LOOKUP_SESSION_ID
    assert resource_attrs["user.email"] == COWORK_USER_EMAIL


def test_cowork_payload_unrecognized_metric_name_is_swappable():
    payload = build_cowork_metrics_payload(
        token_metric_name="claude_code.some.unknown.metric")
    names = {
        m["name"] for m in payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
    }
    assert "claude_code.some.unknown.metric" in names
    assert "claude_code.token.usage" not in names
    # The cost metric is untouched by this swap.
    assert "claude_code.cost.usage" in names


# ---------------------------------------------------------------------------
# AC4/AC5/AC6 -- the golden isolation baseline itself.
# ---------------------------------------------------------------------------

def test_golden_baseline_file_is_non_empty_lf_only_and_has_all_three_pieces():
    raw = COWORK_BASELINE_PATH.read_bytes()
    assert raw, "cowork_isolation_baseline.txt must not be empty"
    assert b"\r\n" not in raw, "cowork_isolation_baseline.txt must be LF-only"

    text = raw.decode("utf-8")
    assert "billing.otel.bill.run()" in text
    assert "billing.reconcile.run()" in text
    assert "AnalyticsClient mocked" in text
    assert "ingest_metrics_payload" in text
    assert 'service.name="claude-code"' in text
    assert "service.name absent" in text
    assert 'service.name="cowork"' in text
    # AC6: every one of the three ingest captures shows a genuine insert on
    # both counts, never a duplicate.
    assert text.count('"duplicate": 0') == 3
    assert text.count('"token_inserted": 2') == 3
    assert text.count('"cost_inserted": 1') == 3


def test_golden_baseline_shows_cowork_payload_accepted_as_ordinary_usage():
    """The specific fact piece 3 exists to record: the existing receiver has
    no service.name filter, so a 'cowork'-tagged payload is stored exactly
    like the 'claude-code' and absent-service.name variants -- all three
    lines carry an identical result body."""
    with open(COWORK_BASELINE_PATH, encoding="utf-8", newline="") as f:
        text = f.read()
    lines = text.splitlines()

    def _result_after(marker: str) -> str:
        for i, line in enumerate(lines):
            if marker in line:
                return lines[i + 1]
        raise AssertionError(f"marker not found: {marker}")

    claude_code_result = _result_after('service.name="claude-code"')
    absent_result = _result_after("service.name absent")
    cowork_result = _result_after('service.name="cowork"')

    assert claude_code_result == absent_result == cowork_result
    assert '"token_inserted": 2' in cowork_result
    assert '"cost_inserted": 1' in cowork_result
    assert '"duplicate": 0' in cowork_result


def test_golden_baseline_capture_is_deterministic_across_two_fresh_runs(tmp_path):
    """AC5: re-running the entire capture twice, in two separate temp
    directories (two separate fresh db builds from the same fixtures,
    otel_store._now frozen the same way both times), produces byte-identical
    output.

    Both calls happen in THIS interpreter process, back to back -- this test
    pins same-process determinism only. It does not by itself guard against
    cross-process or cross-run drift (e.g. a hidden dependency on process
    startup state, import order, or hash randomization seeds); that guarantee
    comes from test_golden_baseline_capture_matches_the_committed_file below,
    which regenerates the capture in a fresh call and diffs it against the
    file committed from a prior, separate run.

    Each call gets its OWN MonkeyPatch instance, fully undone before the
    next call starts (not both undone together at the end) -- undoing mp1
    only after mp2 has already run would make mp2's setattr capture mp1's
    still-patched value as "the original", and undoing mp2 afterwards would
    then re-apply that patched value permanently, leaking a fake
    AnalyticsClient/_now into every later test in the session."""
    mp1 = pytest.MonkeyPatch()
    try:
        run1 = capture_cowork_isolation_baseline(tmp_path / "run1", mp1)
    finally:
        mp1.undo()

    mp2 = pytest.MonkeyPatch()
    try:
        run2 = capture_cowork_isolation_baseline(tmp_path / "run2", mp2)
    finally:
        mp2.undo()

    assert run1 == run2


def test_golden_baseline_capture_matches_the_committed_file(tmp_path):
    """The committed golden file is exactly what capture_cowork_isolation_baseline
    produces today -- i.e. it was captured with this exact function, not
    hand-edited or produced by a diverged one-off script."""
    mp = pytest.MonkeyPatch()
    try:
        regenerated = capture_cowork_isolation_baseline(tmp_path / "regen", mp)
    finally:
        mp.undo()
    with open(COWORK_BASELINE_PATH, encoding="utf-8", newline="") as f:
        committed = f.read()
    assert regenerated == committed
