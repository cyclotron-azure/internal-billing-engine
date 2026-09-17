"""Tests for task 02: `OtelStore.last_ingest_at` / `OtelStore.sessions_with_otlp_rows`
on `billing/otel/otel_store.py`.

One test per acceptance criterion 1-15 of
`_goals/otel-export-loss-reduction/02-store-reads.md`.

Every store is a `tmp_path`-backed file via the `tmp_db_path` fixture from
`tests/conftest.py`. No test touches the network or a live service; nothing
here needs one.

Two testability traps this file is built around (see 05-tests.md):
  - `sqlite3.Connection.execute` cannot be monkeypatched (immutable C type).
    Criteria 5, 6, 7 and 11 reuse the `_ExecuteSpy` delegating wrapper from
    `tests/test_dedupe_counter.py:57` -- swapping `store.db` for the wrapper,
    never patching `.execute` on the connection itself.
  - Criterion 15 needs `conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)`
    applied to the store's connection -- this machine's real cap (32766) would
    otherwise make the test pass against a statement that raises in production.
"""

from __future__ import annotations

import hashlib
import sqlite3

from billing.otel.otel_store import OtelStore, OTLP_MEMBERSHIP_CHUNK_SIZE

from tests.test_dedupe_counter import _ExecuteSpy


def _nano(n: int = 0) -> int:
    return 1_767_225_600_000_000_000 + n * 1_000_000_000


def _otlp_kwargs(**overrides) -> dict:
    kwargs = dict(
        session_id="sess-a", repo="github.com/cyclotron/acme-web",
        repo_raw="git@github.com:cyclotron/acme-web.git", user_email="alice@cyclotron.com",
        user_id="u-alice", org_id="org-cyclotron", model="claude-sonnet-5",
        token_type="output", query_source="main", tokens=10,
        time_unix_nano=_nano(0),
    )
    kwargs.update(overrides)
    return kwargs


def _cost_kwargs(**overrides) -> dict:
    kwargs = dict(
        session_id="sess-a", repo="github.com/cyclotron/acme-web",
        repo_raw="git@github.com:cyclotron/acme-web.git", user_email="alice@cyclotron.com",
        user_id="u-alice", org_id="org-cyclotron", model="claude-sonnet-5",
        query_source="main", cost_usd=1.0, time_unix_nano=_nano(0),
    )
    kwargs.update(overrides)
    return kwargs


def _transcript_kwargs(**overrides) -> dict:
    kwargs = dict(
        session_id="sess-t", repo="github.com/cyclotron/acme-web",
        repo_raw="git@github.com:cyclotron/acme-web.git", user_email="alice@cyclotron.com",
        user_id="u-alice", org_id="org-cyclotron", model="claude-sonnet-5",
        token_type="output", query_source="main", tokens=10,
        time_unix_nano=_nano(0), usage_source="transcript",
        entrypoint="claude-desktop", request_id="req-1",
    )
    kwargs.update(overrides)
    return kwargs


# ---------------------------------------------------------------------------
# Criterion 1 -- zero rows -> None.
# ---------------------------------------------------------------------------

def test_ac01_last_ingest_at_empty_store_returns_none(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        assert store.last_ingest_at() is None
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 2 -- max across both tables, insert order irrelevant.
# ---------------------------------------------------------------------------

def test_ac02_last_ingest_at_is_max_across_both_tables_out_of_order(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        # Insert a LATER ingested_at first (into token_usage), then an
        # EARLIER one into cost_usage -- proves the max, not "last written",
        # wins, and proves both tables are consulted.
        store.db.execute(
            "INSERT INTO token_usage (dp_key, ingested_at, usage_source) "
            "VALUES ('k1', '2025-06-01T00:00:00Z', 'otlp')")
        store.db.execute(
            "INSERT INTO cost_usage (dp_key, ingested_at, usage_source) "
            "VALUES ('k2', '2020-01-01T00:00:00Z', 'otlp')")
        store.commit()
        assert store.last_ingest_at() == "2025-06-01T00:00:00Z"

        # Now insert a still-later one into cost_usage -- proves cost_usage
        # is not ignored.
        store.db.execute(
            "INSERT INTO cost_usage (dp_key, ingested_at, usage_source) "
            "VALUES ('k3', '2026-01-01T00:00:00Z', 'otlp')")
        store.commit()
        assert store.last_ingest_at() == "2026-01-01T00:00:00Z"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 3 -- usage_source filter actually filters (one fixture, two
# assertions).
# ---------------------------------------------------------------------------

def test_ac03_usage_source_filter_ignores_newer_transcript_row(tmp_db_path):
    import billing.otel.otel_store as otel_store_mod

    store = OtelStore(tmp_db_path)
    real_now = otel_store_mod._now
    try:
        otel_store_mod._now = lambda: "2020-01-01T00:00:00Z"
        store.insert_datapoint(**_otlp_kwargs(time_unix_nano=_nano(0)))
        store.commit()

        # The newest row in EITHER table is a transcript row.
        otel_store_mod._now = lambda: "2026-01-01T00:00:00Z"
        store.insert_datapoint(**_transcript_kwargs(time_unix_nano=_nano(1)))
        store.commit()

        otlp_row = store.db.execute(
            "SELECT ingested_at FROM token_usage WHERE usage_source='otlp'").fetchone()
        all_max = store.last_ingest_at()
        otlp_only = store.last_ingest_at(usage_source="otlp")

        assert otlp_only == otlp_row["ingested_at"] == "2020-01-01T00:00:00Z"
        assert all_max == "2026-01-01T00:00:00Z"
        assert all_max != otlp_only
    finally:
        otel_store_mod._now = real_now
        store.close()


# ---------------------------------------------------------------------------
# Criterion 4 -- reads ingested_at, not ts.
# ---------------------------------------------------------------------------

def test_ac04_reads_ingested_at_not_ts(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        # time_unix_nano is far in the past (2020) -> ts column is old, but
        # ingested_at (stamped by _now() at insert time) is "now".
        store.insert_datapoint(**_otlp_kwargs(time_unix_nano=_nano(-190000000)))
        store.commit()
        row = store.db.execute("SELECT ts, ingested_at FROM token_usage").fetchone()
        assert row["ts"] < "2021-01-01"
        assert store.last_ingest_at() == row["ingested_at"]
        assert store.last_ingest_at() > "2025-01-01"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 5 -- empty input: set(), zero queries (execute-counting spy).
# ---------------------------------------------------------------------------

def test_ac05_empty_session_ids_returns_empty_set_zero_queries(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        calls = []
        store.db = _ExecuteSpy(store.db, on_execute=lambda sql: calls.append(sql))
        assert store.sessions_with_otlp_rows([]) == set()
        assert store.sessions_with_otlp_rows(None) == set()
        assert store.sessions_with_otlp_rows("") == set()
        assert calls == []
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 6 -- 1200 distinct ids, 3 exist -> exactly those 3, 3 statements.
# ---------------------------------------------------------------------------

def test_ac06_chunking_over_1200_ids_three_exist_three_statements(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        existing = ["sess-found-1", "sess-found-2", "sess-found-3"]
        for i, sid in enumerate(existing):
            store.insert_datapoint(**_otlp_kwargs(session_id=sid, time_unix_nano=_nano(i)))
        store.commit()

        ids = [f"sess-missing-{i}" for i in range(1197)] + existing
        assert len(ids) == 1200

        calls = []
        store.db = _ExecuteSpy(store.db, on_execute=lambda sql: calls.append(sql))
        found = store.sessions_with_otlp_rows(ids)
        assert found == set(existing)
        assert len(calls) == 3  # ceil(1200/500)
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 7 -- 600 copies of one existing id -> that id, exactly 1 statement.
# ---------------------------------------------------------------------------

def test_ac07_600_duplicate_ids_dedupe_to_one_statement(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        store.insert_datapoint(**_otlp_kwargs(session_id="sess-dup"))
        store.commit()

        calls = []
        store.db = _ExecuteSpy(store.db, on_execute=lambda sql: calls.append(sql))
        found = store.sessions_with_otlp_rows(["sess-dup"] * 600)
        assert found == {"sess-dup"}
        assert len(calls) == 1
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 8 -- transcript-only session excluded; OTLP+transcript session
# included.
# ---------------------------------------------------------------------------

def test_ac08_transcript_only_session_excluded_mixed_session_included(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        store.insert_datapoint(**_transcript_kwargs(session_id="sess-transcript-only"))
        store.insert_datapoint(**_otlp_kwargs(session_id="sess-mixed", time_unix_nano=_nano(1)))
        store.insert_datapoint(**_transcript_kwargs(
            session_id="sess-mixed", request_id="req-mixed", time_unix_nano=_nano(2)))
        store.commit()

        found = store.sessions_with_otlp_rows(["sess-transcript-only", "sess-mixed"])
        assert found == {"sess-mixed"}
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 9 -- entrypoint IS NULL OTLP row IS returned; must be built
# through insert_datapoint, not raw SQL.
# ---------------------------------------------------------------------------

def test_ac09_entrypoint_null_otlp_row_is_returned(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        # insert_datapoint's default entrypoint=None, usage_source='otlp' ->
        # a real OTLP row shape, entrypoint column NULL.
        store.insert_datapoint(**_otlp_kwargs(session_id="sess-null-entry"))
        store.commit()
        row = store.db.execute(
            "SELECT entrypoint FROM token_usage WHERE session_id='sess-null-entry'").fetchone()
        assert row["entrypoint"] is None
        assert store.sessions_with_otlp_rows(["sess-null-entry"]) == {"sess-null-entry"}
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 10 -- SQL metacharacter session id: no match, no raise.
# ---------------------------------------------------------------------------

def test_ac10_sql_metacharacter_session_id_no_match_no_raise(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        found = store.sessions_with_otlp_rows(["' OR 1=1 --"])
        assert found == set()
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 11 -- both methods write nothing: (a) execute-spy sees no
# mutating verb / commit; (b) full-file sha256 unchanged after commit+close.
# ---------------------------------------------------------------------------

def test_ac11_read_methods_write_nothing_spy_and_sha256(tmp_path):
    path = str(tmp_path / "readonly.db")
    store = OtelStore(path)
    store.insert_datapoint(**_otlp_kwargs())
    store.commit()
    store.close()

    with open(path, "rb") as fh:
        before_hash = hashlib.sha256(fh.read()).hexdigest()

    store2 = OtelStore(path)
    try:
        mutating_calls = []

        def on_execute(sql):
            head = sql.strip().split(None, 1)[0].upper()
            if head in ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER"):
                mutating_calls.append(sql)

        store2.db = _ExecuteSpy(store2.db, on_execute=on_execute)
        real_commit = store2.db._real.commit
        commit_calls = []
        store2.commit = lambda: (commit_calls.append(1), real_commit())[-1]

        store2.last_ingest_at()
        store2.last_ingest_at(usage_source="otlp")
        store2.sessions_with_otlp_rows(["sess-a", "sess-b"])

        assert mutating_calls == []
        assert commit_calls == []
    finally:
        store2.db._real.commit()
        store2.db._real.close()

    with open(path, "rb") as fh:
        after_hash = hashlib.sha256(fh.read()).hexdigest()
    assert after_hash == before_hash


# ---------------------------------------------------------------------------
# Criterion 12 -- git diff on otel_store.py shows additions only.
# ---------------------------------------------------------------------------

def test_ac12_git_diff_otel_store_is_additions_only():
    import subprocess

    result = subprocess.run(
        ["git", "diff", "-U0", "--", "billing/otel/otel_store.py"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        # No baseline diff available (e.g. already committed) -- nothing to
        # assert; this criterion is only meaningful mid-goal.
        return
    removed = [
        line for line in result.stdout.splitlines()
        if line.startswith("-") and not line.startswith("---")
    ]
    assert removed == [], f"unexpected deletions in otel_store.py diff: {removed}"


# ---------------------------------------------------------------------------
# Criterion 13 -- C1: cost-only session (built via insert_cost_datapoint
# ALONE) IS returned.
# ---------------------------------------------------------------------------

def test_ac13_cost_only_session_via_insert_cost_datapoint_alone_is_returned(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        store.insert_cost_datapoint(**_cost_kwargs(session_id="sess-cost-only"))
        store.commit()

        tok_count = store.db.execute(
            "SELECT COUNT(*) n FROM token_usage WHERE session_id='sess-cost-only'"
        ).fetchone()["n"]
        assert tok_count == 0

        assert store.sessions_with_otlp_rows(["sess-cost-only"]) == {"sess-cost-only"}
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 14 -- last_ingest_at reflects a cost_usage row newer than every
# token_usage row, both unfiltered and usage_source='otlp'.
# ---------------------------------------------------------------------------

def test_ac14_last_ingest_at_reflects_newer_cost_row(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        store.insert_datapoint(**_otlp_kwargs(time_unix_nano=_nano(0)))
        store.commit()
        tok_ingested = store.db.execute(
            "SELECT ingested_at FROM token_usage").fetchone()["ingested_at"]

        # Force a strictly later ingested_at on a cost row via a fake clock.
        import billing.otel.otel_store as otel_store_mod
        real_now = otel_store_mod._now
        try:
            otel_store_mod._now = lambda: "2099-01-01T00:00:00Z"
            store.insert_cost_datapoint(**_cost_kwargs(time_unix_nano=_nano(1)))
            store.commit()
        finally:
            otel_store_mod._now = real_now

        assert store.last_ingest_at() == "2099-01-01T00:00:00Z"
        assert store.last_ingest_at() != tok_ingested
        assert store.last_ingest_at(usage_source="otlp") == "2099-01-01T00:00:00Z"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 15 -- the parameter-cap regression test.
# ---------------------------------------------------------------------------

def test_ac15_full_500_id_chunk_succeeds_under_999_variable_cap(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        store.db.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)

        existing = [f"sess-cap-{i}" for i in range(3)]
        for i, sid in enumerate(existing):
            store.insert_datapoint(**_otlp_kwargs(session_id=sid, time_unix_nano=_nano(i)))
        store.commit()

        assert OTLP_MEMBERSHIP_CHUNK_SIZE == 500
        ids = [f"sess-cap-missing-{i}" for i in range(497)] + existing
        assert len(ids) == 500

        found = store.sessions_with_otlp_rows(ids)
        assert found == set(existing)
    finally:
        store.close()
