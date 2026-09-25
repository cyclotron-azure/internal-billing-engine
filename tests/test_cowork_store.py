"""Tests for billing/otel/cowork_store.py -- the fully separate Cowork
usage store (task 01 of the cowork-telemetry-ingest goal).

Uses `cowork_db_path` from tests/conftest.py (task 00's fixture) rather than
hand-rolling an equivalent path fixture.
"""

from __future__ import annotations

from billing.otel.cowork_store import CoworkStore


def test_schema_creates_both_tables_with_documented_columns(cowork_db_path):
    store = CoworkStore(cowork_db_path)
    try:
        token_cols = {row[1] for row in
                      store.db.execute("PRAGMA table_info(cowork_token_usage)").fetchall()}
        cost_cols = {row[1] for row in
                     store.db.execute("PRAGMA table_info(cowork_cost_usage)").fetchall()}
    finally:
        store.close()

    assert token_cols == {
        "dp_key", "ts", "session_id", "repo", "repo_raw", "user_email",
        "user_id", "org_id", "model", "token_type", "query_source",
        "tokens", "ingested_at",
    }
    assert cost_cols == {
        "dp_key", "ts", "session_id", "repo", "repo_raw", "user_email",
        "user_id", "org_id", "model", "query_source", "cost_usd",
        "ingested_at",
    }


def test_schema_has_no_otel_only_tables(cowork_db_path):
    store = CoworkStore(cowork_db_path)
    try:
        names = {row[0] for row in
                 store.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    finally:
        store.close()
    assert "session_repo_timeline" not in names
    assert "repo_name_map" not in names
    assert "invoices" not in names
    assert "fabric_outbox" not in names


def test_insert_datapoint_dedupes_on_replay(cowork_db_path):
    store = CoworkStore(cowork_db_path)
    try:
        kwargs = dict(
            session_id="sess-cowork-1", repo="", repo_raw="",
            user_email="dev@cyclotron.com", user_id="u-1", org_id="org-1",
            model="claude-sonnet-5", token_type="input", query_source="main",
            tokens=100, time_unix_nano=1_767_312_000_000_000_000,
        )
        first = store.insert_datapoint(**kwargs)
        second = store.insert_datapoint(**kwargs)
        store.commit()

        rows = store.db.execute("SELECT * FROM cowork_token_usage").fetchall()
    finally:
        store.close()

    assert first is True
    assert second is False
    assert len(rows) == 1


def test_insert_datapoint_coalesces_none_repo_to_empty_string(cowork_db_path):
    store = CoworkStore(cowork_db_path)
    try:
        store.insert_datapoint(
            session_id="sess-cowork-2", repo=None, repo_raw=None,
            user_email="dev@cyclotron.com", user_id="u-1", org_id="org-1",
            model="claude-sonnet-5", token_type="output", query_source="main",
            tokens=42, time_unix_nano=1_767_312_000_000_000_001,
        )
        store.commit()
        row = store.db.execute(
            "SELECT repo, repo_raw FROM cowork_token_usage").fetchone()
    finally:
        store.close()

    assert row["repo"] == ""
    assert row["repo_raw"] == ""


def test_insert_cost_datapoint_dedupes_on_replay(cowork_db_path):
    store = CoworkStore(cowork_db_path)
    try:
        kwargs = dict(
            session_id="sess-cowork-1", repo="", repo_raw="",
            user_email="dev@cyclotron.com", user_id="u-1", org_id="org-1",
            model="claude-sonnet-5", query_source="main", cost_usd=1.5,
            time_unix_nano=1_767_312_000_000_000_003,
        )
        first = store.insert_cost_datapoint(**kwargs)
        second = store.insert_cost_datapoint(**kwargs)
        store.commit()

        rows = store.db.execute("SELECT * FROM cowork_cost_usage").fetchall()
    finally:
        store.close()

    assert first is True
    assert second is False
    assert len(rows) == 1


def test_token_and_cost_dp_keys_never_collide(cowork_db_path):
    """Same session/model/query_source/timestamp, token vs cost insert --
    the "__cost__" sentinel token_type must keep the two dp_keys distinct."""
    store = CoworkStore(cowork_db_path)
    try:
        store.insert_datapoint(
            session_id="sess-x", repo="", repo_raw="",
            user_email="", user_id="", org_id="",
            model="claude-sonnet-5", token_type="input", query_source="main",
            tokens=10, time_unix_nano=1_767_312_000_000_000_010,
        )
        store.insert_cost_datapoint(
            session_id="sess-x", repo="", repo_raw="",
            user_email="", user_id="", org_id="",
            model="claude-sonnet-5", query_source="main", cost_usd=0.5,
            time_unix_nano=1_767_312_000_000_000_010,
        )
        store.commit()
        token_rows = store.db.execute("SELECT dp_key FROM cowork_token_usage").fetchall()
        cost_rows = store.db.execute("SELECT dp_key FROM cowork_cost_usage").fetchall()
    finally:
        store.close()

    assert len(token_rows) == 1
    assert len(cost_rows) == 1
    assert token_rows[0]["dp_key"] != cost_rows[0]["dp_key"]


def test_last_ingest_at_none_for_fresh_store(cowork_db_path):
    store = CoworkStore(cowork_db_path)
    try:
        result = store.last_ingest_at()
    finally:
        store.close()
    assert result is None


def test_last_ingest_at_reflects_max_when_cost_table_is_latest(cowork_db_path, monkeypatch):
    import billing.otel.cowork_store as cowork_store_mod

    times = iter([
        "2026-01-01T00:00:00Z",  # token insert's ingested_at
        "2026-01-02T00:00:00Z",  # cost insert's ingested_at (later -> should win)
    ])
    monkeypatch.setattr(cowork_store_mod, "_now", lambda: next(times))

    store = CoworkStore(cowork_db_path)
    try:
        store.insert_datapoint(
            session_id="sess-y", repo="", repo_raw="",
            user_email="", user_id="", org_id="",
            model="claude-sonnet-5", token_type="input", query_source="main",
            tokens=1, time_unix_nano=1_767_312_000_000_000_020,
        )
        store.insert_cost_datapoint(
            session_id="sess-y", repo="", repo_raw="",
            user_email="", user_id="", org_id="",
            model="claude-sonnet-5", query_source="main", cost_usd=1.0,
            time_unix_nano=1_767_312_000_000_000_021,
        )
        store.commit()
        result = store.last_ingest_at()
    finally:
        store.close()

    assert result == "2026-01-02T00:00:00Z"


def test_last_ingest_at_reflects_max_when_token_table_alone_has_rows(cowork_db_path, monkeypatch):
    """Mirror of the case above with the tables reversed: cowork_cost_usage
    stays EMPTY and only cowork_token_usage has rows. A last_ingest_at()
    implementation that only reads cowork_cost_usage (e.g. a copy-paste that
    dropped the token_usage arm of the UNION) would return None here instead
    of the token row's ingested_at -- this test fails against that mistake."""
    import billing.otel.cowork_store as cowork_store_mod
    monkeypatch.setattr(cowork_store_mod, "_now", lambda: "2026-03-01T00:00:00Z")

    store = CoworkStore(cowork_db_path)
    try:
        store.insert_datapoint(
            session_id="sess-token-only", repo="", repo_raw="",
            user_email="", user_id="", org_id="",
            model="claude-sonnet-5", token_type="input", query_source="main",
            tokens=1, time_unix_nano=1_767_312_000_000_000_030,
        )
        store.commit()

        cost_rows = store.db.execute("SELECT COUNT(*) AS n FROM cowork_cost_usage").fetchone()
        result = store.last_ingest_at()
    finally:
        store.close()

    assert cost_rows["n"] == 0
    assert result == "2026-03-01T00:00:00Z"


def test_last_ingest_at_token_row_more_recent_than_cost_row(cowork_db_path, monkeypatch):
    """Both tables have rows, but the TOKEN row is the more recent one -- the
    inverse ordering of the existing cost-is-latest test. Catches a query
    that only reads cowork_cost_usage (which would return the older cost
    timestamp instead of the newer token one)."""
    import billing.otel.cowork_store as cowork_store_mod

    times = iter([
        "2026-01-01T00:00:00Z",  # cost insert's ingested_at (earlier)
        "2026-01-02T00:00:00Z",  # token insert's ingested_at (later -> should win)
    ])
    monkeypatch.setattr(cowork_store_mod, "_now", lambda: next(times))

    store = CoworkStore(cowork_db_path)
    try:
        store.insert_cost_datapoint(
            session_id="sess-z", repo="", repo_raw="",
            user_email="", user_id="", org_id="",
            model="claude-sonnet-5", query_source="main", cost_usd=1.0,
            time_unix_nano=1_767_312_000_000_000_040,
        )
        store.insert_datapoint(
            session_id="sess-z", repo="", repo_raw="",
            user_email="", user_id="", org_id="",
            model="claude-sonnet-5", token_type="output", query_source="main",
            tokens=2, time_unix_nano=1_767_312_000_000_000_041,
        )
        store.commit()
        result = store.last_ingest_at()
    finally:
        store.close()

    assert result == "2026-01-02T00:00:00Z"
