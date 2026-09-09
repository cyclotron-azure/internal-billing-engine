"""Tests for task 01: transcript-sourced usage columns on `otel_store.py`.

This is the CONTRACT task's own test file -- tasks 02-07 build against the
column names, defaults, key composition, and insert signatures pinned here.
"""

from __future__ import annotations

import sqlite3

import pytest

from billing.otel.otel_store import (
    OtelStore,
    dp_key,
    transcript_key,
)
from tests.conftest import LEGACY_SCHEMA, seed_otlp_rows


def _table_info_set(db, table: str) -> set:
    """Set of (name, type, notnull, dflt_value) for `table`, deliberately
    EXCLUDING `cid` -- ALTER TABLE can only append, while a fresh SCHEMA may
    declare a column mid-table, so an order-sensitive comparison would fail a
    perfectly correct implementation."""
    return {
        (row[1], row[2], row[3], row[4])
        for row in db.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _column_names(db, table: str) -> set:
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}


# ---------------------------------------------------------------------------
# AC1 -- migration adds all four columns and leaves existing rows' billed
# values identical. Rows are seeded via RAW sqlite3 against LEGACY_SCHEMA, NOT
# via seed_otlp_rows (which takes an OtelStore and would auto-migrate on
# open, destroying the pre-migration state this test needs).
# ---------------------------------------------------------------------------

def test_migration_adds_columns_and_preserves_existing_rows(tmp_path):
    path = str(tmp_path / "legacy_seeded.db")
    conn = sqlite3.connect(path)
    try:
        conn.executescript(LEGACY_SCHEMA)
        conn.execute(
            """INSERT INTO token_usage
               (dp_key, ts, session_id, repo, repo_raw, user_email, user_id,
                org_id, model, token_type, query_source, tokens, ingested_at)
               VALUES ('legacy-tok-1', '2026-01-01T00:00:00Z', 'sess-legacy',
                       'github.com/cyclotron/acme-web', 'git@github.com:x/y.git',
                       'alice@cyclotron.com', 'u-alice', 'org-cyclotron',
                       'claude-sonnet-5', 'input', 'main', 12345,
                       '2026-01-01T00:00:00Z')""")
        conn.execute(
            """INSERT INTO cost_usage
               (dp_key, ts, session_id, repo, repo_raw, user_email, user_id,
                org_id, model, query_source, cost_usd, ingested_at)
               VALUES ('legacy-cost-1', '2026-01-01T00:00:00Z', 'sess-legacy',
                       'github.com/cyclotron/acme-web', 'git@github.com:x/y.git',
                       'alice@cyclotron.com', 'u-alice', 'org-cyclotron',
                       'claude-sonnet-5', 'main', 3.5,
                       '2026-01-01T00:00:00Z')""")
        conn.commit()
    finally:
        conn.close()

    # Pre-migration billed values, read with a fresh raw connection (not
    # OtelStore -- opening OtelStore is the act under test).
    pre = sqlite3.connect(path)
    try:
        pre_tok = pre.execute(
            "SELECT tokens FROM token_usage WHERE dp_key='legacy-tok-1'").fetchone()[0]
        pre_cost = pre.execute(
            "SELECT cost_usd FROM cost_usage WHERE dp_key='legacy-cost-1'").fetchone()[0]
        assert "usage_source" not in _column_names(pre, "token_usage")
        assert "entrypoint" not in _column_names(pre, "token_usage")
        assert "usage_source" not in _column_names(pre, "cost_usage")
        assert "cost_source" not in _column_names(pre, "cost_usage")
    finally:
        pre.close()

    store = OtelStore(path)
    try:
        tok_cols = _column_names(store.db, "token_usage")
        cost_cols = _column_names(store.db, "cost_usage")
        assert {"usage_source", "entrypoint"} <= tok_cols
        assert {"usage_source", "cost_source"} <= cost_cols

        tok_row = store.db.execute(
            "SELECT tokens, usage_source FROM token_usage WHERE dp_key='legacy-tok-1'"
        ).fetchone()
        cost_row = store.db.execute(
            "SELECT cost_usd, usage_source, cost_source FROM cost_usage "
            "WHERE dp_key='legacy-cost-1'").fetchone()

        assert tok_row["tokens"] == pre_tok == 12345
        assert tok_row["usage_source"] == "otlp"
        assert cost_row["cost_usd"] == pre_cost == 3.5
        assert cost_row["usage_source"] == "otlp"
        assert cost_row["cost_source"] == "actual"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# AC2 -- opening an already-migrated store a second time raises nothing and
# changes nothing.
# ---------------------------------------------------------------------------

def test_migration_is_idempotent_on_second_open(legacy_schema_db_path):
    store1 = OtelStore(legacy_schema_db_path)
    tok_cols_1 = _table_info_set(store1.db, "token_usage")
    cost_cols_1 = _table_info_set(store1.db, "cost_usage")
    store1.close()

    # Second open against the now-migrated database must not raise.
    store2 = OtelStore(legacy_schema_db_path)
    try:
        tok_cols_2 = _table_info_set(store2.db, "token_usage")
        cost_cols_2 = _table_info_set(store2.db, "cost_usage")
        assert tok_cols_1 == tok_cols_2
        assert cost_cols_1 == cost_cols_2
    finally:
        store2.close()


# ---------------------------------------------------------------------------
# AC3 -- a fresh DB and a migrated DB agree on columns for BOTH tables,
# compared as set-equality over (name, type, notnull, dflt_value) -- NOT cid.
# ---------------------------------------------------------------------------

def test_fresh_and_migrated_schemas_converge(tmp_path, legacy_schema_db_path):
    fresh = OtelStore(str(tmp_path / "fresh.db"))
    migrated = OtelStore(legacy_schema_db_path)
    try:
        assert _table_info_set(fresh.db, "token_usage") == _table_info_set(
            migrated.db, "token_usage")
        assert _table_info_set(fresh.db, "cost_usage") == _table_info_set(
            migrated.db, "cost_usage")
    finally:
        fresh.close()
        migrated.close()


# ---------------------------------------------------------------------------
# AC4 -- inserting the same transcript datapoint twice yields exactly one row.
# ---------------------------------------------------------------------------

def test_duplicate_transcript_insert_dedupes(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        kwargs = dict(
            session_id="sess-desktop-a", repo="github.com/cyclotron/acme-web",
            repo_raw="git@github.com:x/y.git", user_email="alice@cyclotron.com",
            user_id="u-alice", org_id="org-cyclotron", model="claude-sonnet-5",
            token_type="output", query_source="main", tokens=209,
            time_unix_nano=1_767_225_600_000_000_000,
            usage_source="transcript", entrypoint="claude-desktop",
            request_id="req-multiblock-001",
        )
        first = store.insert_datapoint(**kwargs)
        second = store.insert_datapoint(**kwargs)
        store.commit()
        assert first is True
        assert second is False
        row = store.db.execute(
            "SELECT COUNT(*) n, entrypoint FROM token_usage WHERE usage_source='transcript'"
        ).fetchone()
        assert row["n"] == 1
        # entrypoint is frozen-contract (task 05 filters on it) -- assert the
        # round trip, not just that a row exists. Forcing entrypoint to None
        # in the insert must fail this.
        assert row["entrypoint"] == "claude-desktop"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# The "__cost__" sentinel insert_cost_datapoint actually uses is pinned here
# at the CALL SITE. AC6 above only tests transcript_key() directly -- it
# would stay green even if insert_cost_datapoint passed a different sentinel
# (e.g. "output") to transcript_key internally.
# ---------------------------------------------------------------------------

def test_insert_cost_datapoint_uses_the_cost_sentinel_key(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        store.insert_cost_datapoint(
            session_id="sess-desktop-a", repo="github.com/cyclotron/acme-web",
            repo_raw="git@github.com:x/y.git", user_email="alice@cyclotron.com",
            user_id="u-alice", org_id="org-cyclotron", model="claude-sonnet-5",
            query_source="main", cost_usd=1.23,
            time_unix_nano=1_767_225_600_000_000_000,
            usage_source="transcript", cost_source="rate_card",
            request_id="req-multiblock-001",
        )
        store.commit()
        row = store.db.execute(
            "SELECT dp_key FROM cost_usage WHERE usage_source='transcript'"
        ).fetchone()
        expected = transcript_key("sess-desktop-a", "req-multiblock-001", "__cost__")
        assert row["dp_key"] == expected
    finally:
        store.close()


# ---------------------------------------------------------------------------
# AC5 -- two records differing ONLY in request_id (same session, model,
# token_type, timestamp) produce TWO rows. Regression test for the silent
# under-billing defect; AC4 alone would pass while the bug is present.
# ---------------------------------------------------------------------------

def test_differing_request_id_alone_produces_two_rows(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        common = dict(
            session_id="sess-desktop-a", repo="github.com/cyclotron/acme-web",
            repo_raw="git@github.com:x/y.git", user_email="alice@cyclotron.com",
            user_id="u-alice", org_id="org-cyclotron", model="claude-sonnet-5",
            token_type="output", query_source="main", tokens=100,
            time_unix_nano=1_767_225_600_000_000_000,  # SAME second for both
            usage_source="transcript", entrypoint="claude-desktop",
        )
        r1 = store.insert_datapoint(**common, request_id="req-aaa")
        r2 = store.insert_datapoint(**common, request_id="req-bbb")
        store.commit()
        assert r1 is True
        assert r2 is True
        rows = store.db.execute(
            "SELECT COUNT(*) n FROM token_usage WHERE usage_source='transcript'"
        ).fetchone()["n"]
        assert rows == 2
    finally:
        store.close()


# ---------------------------------------------------------------------------
# AC5b -- the converse: a replayed record with the same (session_id,
# request_id, token_type) but a LARGER token count does NOT overwrite and
# does NOT add. Pins INSERT OR IGNORE first-writer-wins semantics explicitly.
# ---------------------------------------------------------------------------

def test_replay_with_larger_tokens_does_not_overwrite_or_add(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        base = dict(
            session_id="sess-desktop-a", repo="github.com/cyclotron/acme-web",
            repo_raw="git@github.com:x/y.git", user_email="alice@cyclotron.com",
            user_id="u-alice", org_id="org-cyclotron", model="claude-sonnet-5",
            token_type="output", query_source="main",
            time_unix_nano=1_767_225_600_000_000_000,
            usage_source="transcript", entrypoint="claude-desktop",
            request_id="req-multiblock-001",
        )
        first = store.insert_datapoint(tokens=5, **base)
        second = store.insert_datapoint(tokens=209, **base)
        store.commit()
        assert first is True
        assert second is False

        rows = store.db.execute(
            "SELECT tokens FROM token_usage WHERE usage_source='transcript'"
        ).fetchall()
        assert len(rows) == 1
        # First-writer-wins: the surviving row holds the FIRST inserted value
        # (5), not the second (209) and not their sum (214). This is exactly
        # why tasks 02/06 must collapse to the terminal block themselves --
        # the store cannot and does not pick the right snapshot.
        assert rows[0]["tokens"] == 5
    finally:
        store.close()


# ---------------------------------------------------------------------------
# AC6 -- a transcript row's cost key never equals any of its four token keys,
# and no transcript key equals an OTLP dp_key for the same session/timestamp.
# ---------------------------------------------------------------------------

def test_transcript_cost_key_never_collides_with_token_keys_or_otlp_dp_key():
    session_id = "sess-desktop-a"
    request_id = "req-multiblock-001"
    model = "claude-sonnet-5"
    query_source = "main"
    time_unix_nano = 1_767_225_600_000_000_000

    token_types = ["input", "output", "cacheRead", "cacheCreation"]
    token_keys = {tt: transcript_key(session_id, request_id, tt) for tt in token_types}
    cost_key = transcript_key(session_id, request_id, "__cost__")

    # Cost key distinct from every one of the four token keys, and all four
    # token keys distinct from each other.
    assert cost_key not in token_keys.values()
    assert len(set(token_keys.values())) == len(token_types)

    # No transcript key (for any token_type, including the cost sentinel)
    # equals an OTLP dp_key built from the same session_id/model/query_source/
    # timestamp fields.
    otlp_keys = {
        dp_key(session_id, model, tt, query_source, time_unix_nano)
        for tt in token_types
    }
    otlp_keys.add(dp_key(session_id, model, "__cost__", query_source, time_unix_nano))
    transcript_keys = set(token_keys.values()) | {cost_key}
    assert otlp_keys.isdisjoint(transcript_keys)


# ---------------------------------------------------------------------------
# AC7 -- cost_usage carries usage_source, proven by a query filtering on it.
# ---------------------------------------------------------------------------

def test_cost_usage_usage_source_is_queryable(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        seed_otlp_rows(store)  # 3 otlp cost rows, usage_source defaults to 'otlp'

        store.insert_cost_datapoint(
            session_id="sess-desktop-a", repo="github.com/cyclotron/acme-web",
            repo_raw="git@github.com:x/y.git", user_email="alice@cyclotron.com",
            user_id="u-alice", org_id="org-cyclotron", model="claude-sonnet-5",
            query_source="main", cost_usd=1.23,
            time_unix_nano=1_767_225_600_000_000_000,
            usage_source="transcript", cost_source="rate_card",
            request_id="req-multiblock-001",
        )
        store.commit()

        otlp_rows = store.db.execute(
            "SELECT session_id FROM cost_usage WHERE usage_source='otlp'").fetchall()
        transcript_rows = store.db.execute(
            "SELECT session_id, cost_source FROM cost_usage WHERE usage_source='transcript'"
        ).fetchall()

        assert {r["session_id"] for r in otlp_rows} == {
            "sess-otlp-001", "sess-otlp-002", "sess-otlp-003"}
        assert len(transcript_rows) == 1
        assert transcript_rows[0]["session_id"] == "sess-desktop-a"
        # 'rate_card' -- NOT 'estimated'. goal.md / 02-transcript-payload.md /
        # 05-billing-basis.md all pin this literal; task 05 derives the
        # invoice's actual-vs-estimated split from it, so a mismatched
        # literal here would make desktop cost silently vanish from the
        # estimated bucket of a client invoice.
        assert transcript_rows[0]["cost_source"] == "rate_card"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# request_id guard -- both directions, both insert methods.
#
# Direction 1: usage_source != 'otlp' with a missing/None/"" /"None" request_id
# must RAISE, not silently collapse every request in the session onto one row
# per token_type. `request_id=None` is the parameter's own default, so this is
# not an exotic input -- it's what a caller gets from forgetting one keyword.
#
# Direction 2 (mirror): usage_source == 'otlp' with a non-None request_id must
# RAISE too -- otherwise a caller that forgets to also pass
# usage_source='transcript' is silently routed onto the timestamp-based
# dp_key, reintroducing the exact second-granularity collision this task
# exists to prevent.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_request_id", [None, "", "None", "  ", " None "])
def test_insert_datapoint_transcript_without_request_id_raises(tmp_db_path, bad_request_id):
    store = OtelStore(tmp_db_path)
    try:
        with pytest.raises(ValueError):
            store.insert_datapoint(
                session_id="sess-desktop-a", repo="github.com/cyclotron/acme-web",
                repo_raw="git@github.com:x/y.git", user_email="alice@cyclotron.com",
                user_id="u-alice", org_id="org-cyclotron", model="claude-sonnet-5",
                token_type="output", query_source="main", tokens=100,
                time_unix_nano=1_767_225_600_000_000_000,
                usage_source="transcript", entrypoint="claude-desktop",
                request_id=bad_request_id,
            )
        # No row was left behind by the failed insert.
        n = store.db.execute(
            "SELECT COUNT(*) n FROM token_usage WHERE usage_source='transcript'"
        ).fetchone()["n"]
        assert n == 0
    finally:
        store.close()


@pytest.mark.parametrize("bad_request_id", [None, "", "None", "  ", " None "])
def test_insert_cost_datapoint_transcript_without_request_id_raises(tmp_db_path, bad_request_id):
    store = OtelStore(tmp_db_path)
    try:
        with pytest.raises(ValueError):
            store.insert_cost_datapoint(
                session_id="sess-desktop-a", repo="github.com/cyclotron/acme-web",
                repo_raw="git@github.com:x/y.git", user_email="alice@cyclotron.com",
                user_id="u-alice", org_id="org-cyclotron", model="claude-sonnet-5",
                query_source="main", cost_usd=1.23,
                time_unix_nano=1_767_225_600_000_000_000,
                usage_source="transcript", cost_source="rate_card",
                request_id=bad_request_id,
            )
        n = store.db.execute(
            "SELECT COUNT(*) n FROM cost_usage WHERE usage_source='transcript'"
        ).fetchone()["n"]
        assert n == 0
    finally:
        store.close()


def test_none_string_and_none_hash_identically_which_is_why_the_guard_rejects_both():
    """Direct proof, independent of the store, of the defect the guard closes:
    transcript_key("s1", "None", "input") == transcript_key("s1", None, "input").
    A client that stringifies a missing id collides exactly like a true None
    -- an `is None` check alone is insufficient; the guard must reject the
    literal string "None" too. (This test is NOT itself the guard test -- it
    stays green even with the guard deleted; the parametrized
    ...transcript_without_request_id_raises tests above cover the guard.)"""
    assert (transcript_key("sess-x", "None", "input")
            == transcript_key("sess-x", None, "input"))


def test_padded_and_unpadded_request_id_key_identically(tmp_db_path):
    """Hardening 2: " req-1 " and "req-1" must produce the SAME stored key --
    otherwise inconsistent padding across re-sends of the same request
    double-inserts (the over-count direction; still wrong). The stripping
    happens in the insert methods (transcript_key itself does not strip),
    so this is asserted at the insert level, not against transcript_key
    directly."""
    store = OtelStore(tmp_db_path)
    try:
        common = dict(
            session_id="sess-desktop-a", repo="github.com/cyclotron/acme-web",
            repo_raw="git@github.com:x/y.git", user_email="alice@cyclotron.com",
            user_id="u-alice", org_id="org-cyclotron", model="claude-sonnet-5",
            token_type="output", query_source="main", tokens=100,
            time_unix_nano=1_767_225_600_000_000_000,
            usage_source="transcript", entrypoint="claude-desktop",
        )
        first = store.insert_datapoint(**common, request_id="req-1")
        second = store.insert_datapoint(**common, request_id=" req-1 ")
        store.commit()
        assert first is True
        assert second is False  # treated as the SAME request, not a new one
        n = store.db.execute(
            "SELECT COUNT(*) n FROM token_usage WHERE usage_source='transcript'"
        ).fetchone()["n"]
        assert n == 1
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Hardening 1: pin that an OTLP row's STORED key equals dp_key(...) directly.
# This is the mirror of test_insert_cost_datapoint_uses_the_cost_sentinel_key
# above, but for the OTLP branch -- nothing else in the suite pins this, and
# re-keying the OTLP branch onto transcript_key(...) leaves every other test
# (including the golden baseline, since re-keying without collision leaves
# bill.py's SUMs identical) green.
# ---------------------------------------------------------------------------

def test_insert_datapoint_otlp_uses_dp_key(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        store.insert_datapoint(
            session_id="sess-otlp-x", repo="github.com/cyclotron/acme-web",
            repo_raw="git@github.com:x/y.git", user_email="alice@cyclotron.com",
            user_id="u-alice", org_id="org-cyclotron", model="claude-sonnet-5",
            token_type="output", query_source="main", tokens=100,
            time_unix_nano=1_767_225_600_000_000_000,
        )
        store.commit()
        row = store.db.execute(
            "SELECT dp_key FROM token_usage WHERE usage_source='otlp'").fetchone()
        expected = dp_key("sess-otlp-x", "claude-sonnet-5", "output", "main",
                           1_767_225_600_000_000_000)
        assert row["dp_key"] == expected
    finally:
        store.close()


def test_insert_cost_datapoint_otlp_uses_dp_key(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        store.insert_cost_datapoint(
            session_id="sess-otlp-x", repo="github.com/cyclotron/acme-web",
            repo_raw="git@github.com:x/y.git", user_email="alice@cyclotron.com",
            user_id="u-alice", org_id="org-cyclotron", model="claude-sonnet-5",
            query_source="main", cost_usd=1.5,
            time_unix_nano=1_767_225_600_000_000_000,
        )
        store.commit()
        row = store.db.execute(
            "SELECT dp_key FROM cost_usage WHERE usage_source='otlp'").fetchone()
        expected = dp_key("sess-otlp-x", "claude-sonnet-5", "__cost__", "main",
                           1_767_225_600_000_000_000)
        assert row["dp_key"] == expected
    finally:
        store.close()


def test_insert_datapoint_otlp_with_request_id_raises(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        with pytest.raises(ValueError):
            store.insert_datapoint(
                session_id="sess-otlp-x", repo="github.com/cyclotron/acme-web",
                repo_raw="git@github.com:x/y.git", user_email="alice@cyclotron.com",
                user_id="u-alice", org_id="org-cyclotron", model="claude-sonnet-5",
                token_type="output", query_source="main", tokens=100,
                time_unix_nano=1_767_225_600_000_000_000,
                request_id="req-should-not-be-here",
            )
    finally:
        store.close()


def test_insert_cost_datapoint_otlp_with_request_id_raises(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        with pytest.raises(ValueError):
            store.insert_cost_datapoint(
                session_id="sess-otlp-x", repo="github.com/cyclotron/acme-web",
                repo_raw="git@github.com:x/y.git", user_email="alice@cyclotron.com",
                user_id="u-alice", org_id="org-cyclotron", model="claude-sonnet-5",
                query_source="main", cost_usd=1.23,
                time_unix_nano=1_767_225_600_000_000_000,
                request_id="req-should-not-be-here",
            )
    finally:
        store.close()


def test_two_otlp_request_ids_would_have_silently_collapsed_without_the_guard(tmp_db_path):
    """Orchestrator-confirmed defect this guard prevents: two distinct
    request_ids at usage_source='otlp' with the same timestamp used to
    collapse to 1 row / 100 tokens instead of 2 rows / 300, because
    request_id was silently ignored by dp_key. Now both calls raise instead
    of silently mis-keying."""
    store = OtelStore(tmp_db_path)
    try:
        common = dict(
            session_id="sess-otlp-y", repo="github.com/cyclotron/acme-web",
            repo_raw="git@github.com:x/y.git", user_email="alice@cyclotron.com",
            user_id="u-alice", org_id="org-cyclotron", model="claude-sonnet-5",
            token_type="output", query_source="main", tokens=100,
            time_unix_nano=1_767_225_600_000_000_000,
        )
        with pytest.raises(ValueError):
            store.insert_datapoint(**common, request_id="req-aaa")
        with pytest.raises(ValueError):
            store.insert_datapoint(**common, request_id="req-bbb")
        n = store.db.execute("SELECT COUNT(*) n FROM token_usage").fetchone()["n"]
        assert n == 0
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Backward compatibility -- existing OTLP callers (receiver.py's call shape,
# reproduced via conftest's seed_otlp_rows) keep working unchanged, with
# usage_source defaulting to 'otlp' and cost_source defaulting to 'actual'.
# ---------------------------------------------------------------------------

def test_existing_otlp_callers_unaffected(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        seed_otlp_rows(store)
        tok_sources = {r["usage_source"] for r in store.db.execute(
            "SELECT DISTINCT usage_source FROM token_usage")}
        cost_sources = {r["usage_source"] for r in store.db.execute(
            "SELECT DISTINCT usage_source FROM cost_usage")}
        cost_kinds = {r["cost_source"] for r in store.db.execute(
            "SELECT DISTINCT cost_source FROM cost_usage")}
        assert tok_sources == {"otlp"}
        assert cost_sources == {"otlp"}
        assert cost_kinds == {"actual"}
    finally:
        store.close()
