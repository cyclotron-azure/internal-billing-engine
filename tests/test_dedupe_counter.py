"""Tests for task 01: the `dedupe_drops` counter and counting-start epoch on
`billing/otel/otel_store.py`.

One test per acceptance criterion 1-14 of
`_goals/reconcile-coverage-diagnostics/01-store-dedupe-counter.md`. Criterion 15 is a
command-output criterion (`pytest tests/test_otel_store.py -q` exits 0), not a unit
test, and is intentionally not represented here.

Every store is opened against a `tmp_path`-backed file (via the `tmp_db_path` /
`legacy_schema_db_path` fixtures from `tests/conftest.py`) -- never
`./data/otel.db`. No test touches the network or a live service; nothing here
needs one.

Three testability traps in the shipped (correct) implementation, and how each test
below is written around them:

  1. A failing counter UPDATE leaves a `drops = 0` residue row (the INSERT OR IGNORE
     half of `_record_dedupe_drop` still lands a row before the UPDATE raises). Both
     public readers filter falsy `drops`, so `test_ac13_...` asserts through
     `dedupe_drops()` (must be `{}`), never `SELECT COUNT(*) FROM dedupe_drops`.
  2. `last_seen` is second-granular (`_now()`'s `%Y-%m-%dT%H:%M:%SZ` format), so three
     back-to-back inserts in the same wall-clock second would land on an identical
     timestamp. `test_ac3_...` monkeypatches `billing.otel.otel_store._now` with a
     strictly-increasing fake clock instead of sleeping.
  3. `dedupe_epoch()` issues its own `SELECT ... FROM meta`, sharing the `FROM meta`
     shape with the insert path's latch-closing `SELECT 1 FROM meta WHERE key=?`.
     `test_ac10_...` matches on the exact insert-path SQL string and never calls
     `dedupe_epoch()` inside the counted window.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from billing.otel.otel_store import DEDUPE_EPOCH_META_KEY, OtelStore, dp_key


def _nano(iso_date: str) -> int:
    """Nanoseconds-since-epoch for 00:00:00 UTC on `iso_date` (YYYY-MM-DD)."""
    dt = datetime.strptime(iso_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1_000_000_000)


def _base_kwargs(**overrides) -> dict:
    kwargs = dict(
        session_id="sess-x", repo="github.com/cyclotron/acme-web",
        repo_raw="git@github.com:cyclotron/acme-web.git", user_email="alice@cyclotron.com",
        user_id="u-alice", org_id="org-cyclotron", model="claude-sonnet-5",
        token_type="output", query_source="main", tokens=100,
        time_unix_nano=_nano("2020-06-15"),
    )
    kwargs.update(overrides)
    return kwargs


class _ExecuteSpy:
    """Wraps a real `sqlite3.Connection` and intercepts `.execute()` only.

    `sqlite3.Connection.execute` is a C-level method on an immutable type --
    neither instance nor class assignment works (`AttributeError: read-only`
    / `TypeError: cannot set 'execute' attribute of immutable type`). Since
    `OtelStore.db` is a plain Python attribute, swapping the whole connection
    for this delegating wrapper is the seam that actually works. Everything
    but `execute` forwards straight through via `__getattr__`.
    """

    def __init__(self, real_conn, *, on_execute):
        self._real = real_conn
        self._on_execute = on_execute

    def execute(self, sql, *args, **kwargs):
        self._on_execute(sql)
        return self._real.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _FakeClock:
    """A strictly-increasing fake `_now()` -- avoids sleeping past a real wall-clock
    second (trap 2) while still returning valid `%Y-%m-%dT%H:%M:%SZ` strings."""

    def __init__(self):
        self.n = 0

    def now(self) -> str:
        self.n += 1
        return f"2024-01-01T{self.n // 3600:02d}:{(self.n // 60) % 60:02d}:{self.n % 60:02d}Z"


# ---------------------------------------------------------------------------
# Criterion 1 -- schema: six columns, three-column primary key.
# ---------------------------------------------------------------------------

def test_ac1_dedupe_drops_schema(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        cols = store.db.execute("PRAGMA table_info(dedupe_drops)").fetchall()
        names = {c[1] for c in cols}
        assert names == {"day", "token_type", "usage_source", "drops", "first_seen", "last_seen"}
        pk_cols = {c[1] for c in cols if c[5] > 0}
        assert pk_cols == {"day", "token_type", "usage_source"}
        # PRAGMA index_list / index_info corroborate the same PK membership.
        indexes = store.db.execute("PRAGMA index_list(dedupe_drops)").fetchall()
        pk_indexes = [ix for ix in indexes if ix[3] == "pk"]
        assert len(pk_indexes) == 1
        info = store.db.execute(f"PRAGMA index_info({pk_indexes[0][1]})").fetchall()
        assert {row[2] for row in info} == {"day", "token_type", "usage_source"}
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 2 -- duplicate OTLP insert: True then False; one row, drops=1,
# day == the datapoint's own (past) ts[:10], not today.
# ---------------------------------------------------------------------------

def test_ac2_duplicate_insert_true_then_false_day_from_datapoint_ts(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        kwargs = _base_kwargs(time_unix_nano=_nano("2020-06-15"))
        assert store.insert_datapoint(**kwargs) is True
        assert store.insert_datapoint(**kwargs) is False
        store.commit()
        rows = store.db.execute("SELECT day, drops FROM dedupe_drops").fetchall()
        assert len(rows) == 1
        assert rows[0]["day"] == "2020-06-15"
        assert rows[0]["drops"] == 1
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 3 -- a third identical insert raises drops to 2, advances
# last_seen, leaves first_seen unchanged. Trap 2: fake clock, no sleeping.
# ---------------------------------------------------------------------------

def test_ac3_third_duplicate_advances_last_seen_not_first_seen(tmp_db_path, monkeypatch):
    import billing.otel.otel_store as otel_store_mod
    clock = _FakeClock()
    monkeypatch.setattr(otel_store_mod, "_now", clock.now)

    store = OtelStore(tmp_db_path)
    try:
        kwargs = _base_kwargs()
        assert store.insert_datapoint(**kwargs) is True
        assert store.insert_datapoint(**kwargs) is False  # 1st duplicate: drops=1
        row = store.db.execute(
            "SELECT first_seen, last_seen, drops FROM dedupe_drops").fetchone()
        assert row["drops"] == 1
        first_seen_after_first_drop = row["first_seen"]
        last_seen_after_first_drop = row["last_seen"]

        assert store.insert_datapoint(**kwargs) is False  # 2nd duplicate: drops=2
        row2 = store.db.execute(
            "SELECT first_seen, last_seen, drops FROM dedupe_drops").fetchone()
        assert row2["drops"] == 2
        assert row2["first_seen"] == first_seen_after_first_drop
        assert row2["last_seen"] > last_seen_after_first_drop
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 4 -- a successful (non-duplicate) insert adds no dedupe_drops row.
# ---------------------------------------------------------------------------

def test_ac4_successful_insert_adds_no_dedupe_drops_row(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        assert store.insert_datapoint(**_base_kwargs()) is True
        store.commit()
        n = store.db.execute("SELECT COUNT(*) n FROM dedupe_drops").fetchone()["n"]
        assert n == 0
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 5 -- a duplicate transcript insert counts usage_source='transcript';
# a duplicate cost insert counts token_type='__cost__'.
# ---------------------------------------------------------------------------

def test_ac5_transcript_and_cost_duplicates_counted_correctly(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        t_kwargs = dict(
            session_id="sess-t", repo="github.com/cyclotron/acme-web",
            repo_raw="git@github.com:cyclotron/acme-web.git", user_email="alice@cyclotron.com",
            user_id="u-alice", org_id="org-cyclotron", model="claude-sonnet-5",
            token_type="output", query_source="main", tokens=10,
            time_unix_nano=_nano("2020-06-15"), usage_source="transcript",
            entrypoint="claude-desktop", request_id="req-1",
        )
        assert store.insert_datapoint(**t_kwargs) is True
        assert store.insert_datapoint(**t_kwargs) is False

        c_kwargs = dict(
            session_id="sess-c", repo="github.com/cyclotron/acme-web",
            repo_raw="git@github.com:cyclotron/acme-web.git", user_email="alice@cyclotron.com",
            user_id="u-alice", org_id="org-cyclotron", model="claude-sonnet-5",
            query_source="main", cost_usd=1.0, time_unix_nano=_nano("2020-06-16"),
        )
        assert store.insert_cost_datapoint(**c_kwargs) is True
        assert store.insert_cost_datapoint(**c_kwargs) is False
        store.commit()

        rows = {
            (r["token_type"], r["usage_source"]): r["drops"]
            for r in store.db.execute(
                "SELECT token_type, usage_source, drops FROM dedupe_drops")
        }
        assert rows[("output", "transcript")] == 1
        assert rows[("__cost__", "otlp")] == 1
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 6 -- migrating the legacy_schema_db_path fixture: dedupe_drops
# exists, every pre-existing row is preserved byte-for-byte, second open is a
# no-op.
# ---------------------------------------------------------------------------

def test_ac6_legacy_migration_adds_dedupe_drops_preserves_rows(legacy_schema_db_path):
    conn = sqlite3.connect(legacy_schema_db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            """INSERT INTO token_usage
               (dp_key, ts, session_id, repo, repo_raw, user_email, user_id,
                org_id, model, token_type, query_source, tokens, ingested_at)
               VALUES ('k1','2020-01-01T00:00:00Z','s','r','rr','a@x.com','u1',
                       'org1','m','input','main',5,'2020-01-01T00:00:00Z')""")
        conn.commit()
        # Full row, byte-for-byte, BEFORE migration -- not just `tokens`.
        pre_row = dict(conn.execute(
            "SELECT * FROM token_usage WHERE dp_key='k1'").fetchone())
    finally:
        conn.close()

    dedupe_drops_schema = {"day", "token_type", "usage_source", "drops", "first_seen", "last_seen"}

    store1 = OtelStore(legacy_schema_db_path)
    try:
        cols = {row[1] for row in store1.db.execute(
            "PRAGMA table_info(dedupe_drops)").fetchall()}
        assert cols == dedupe_drops_schema
        # Full (name, type, notnull, dflt_value, pk) tuple set for
        # token_usage -- migration must be additive, never retyping or
        # dropping an existing column.
        post_migration_cols = {
            (r[1], r[2], r[3], r[4], r[5])
            for r in store1.db.execute("PRAGMA table_info(token_usage)").fetchall()
        }
        assert {"usage_source", "entrypoint"} <= {c[0] for c in post_migration_cols}

        post_row = dict(store1.db.execute(
            "SELECT * FROM token_usage WHERE dp_key='k1'").fetchone())
        for key, value in pre_row.items():
            assert post_row[key] == value, f"column {key!r} changed on migration"
        n1 = store1.db.execute("SELECT COUNT(*) n FROM dedupe_drops").fetchone()["n"]
        assert n1 == 0
    finally:
        store1.close()

    # Second open: no-op -- schema (all columns, not just dedupe_drops's
    # names) and the pre-existing row are BOTH still identical.
    store2 = OtelStore(legacy_schema_db_path)
    try:
        cols2 = {
            (r[1], r[2], r[3], r[4], r[5])
            for r in store2.db.execute("PRAGMA table_info(token_usage)").fetchall()
        }
        assert cols2 == post_migration_cols

        post_row2 = dict(store2.db.execute(
            "SELECT * FROM token_usage WHERE dp_key='k1'").fetchone())
        assert post_row2 == post_row
        n2 = store2.db.execute("SELECT COUNT(*) n FROM dedupe_drops").fetchone()["n"]
        assert n2 == 0
    finally:
        store2.close()


# ---------------------------------------------------------------------------
# Criterion 7 -- a store opened (and migrated) but never inserted into has
# dedupe_epoch() is None, even after a close/reopen. Pins the cycle-1 fix: an
# epoch written from _migrate() fails this.
# ---------------------------------------------------------------------------

def test_ac7_never_inserted_store_has_no_epoch(tmp_db_path):
    store = OtelStore(tmp_db_path)
    store.dedupe_drops("2020-01-01", "2020-01-02")
    store.dedupe_drops_by_day("2020-01-01", "2020-01-02")
    assert store.dedupe_epoch() is None
    store.close()

    store2 = OtelStore(tmp_db_path)
    try:
        assert store2.dedupe_epoch() is None
    finally:
        store2.close()


# ---------------------------------------------------------------------------
# Criterion 8 -- the first insert attempt sets the epoch to an ISO8601
# timestamp; a later insert on a subsequent reopen leaves it unchanged.
# ---------------------------------------------------------------------------

def test_ac8_epoch_set_on_first_insert_unchanged_across_reopen(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        store.insert_datapoint(**_base_kwargs())
        store.commit()
        epoch1 = store.dedupe_epoch()
        assert epoch1 is not None
        datetime.strptime(epoch1, "%Y-%m-%dT%H:%M:%SZ")  # raises if not ISO8601
    finally:
        store.close()

    store2 = OtelStore(tmp_db_path)
    try:
        store2.insert_datapoint(
            **_base_kwargs(session_id="sess-y", time_unix_nano=_nano("2020-07-01")))
        store2.commit()
        assert store2.dedupe_epoch() == epoch1
    finally:
        store2.close()


# ---------------------------------------------------------------------------
# Criterion 9 -- the epoch is set equally by a successful first insert and by
# a duplicate-only first insert (two independent entry paths).
# ---------------------------------------------------------------------------

def test_ac9_epoch_set_by_successful_first_insert(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        assert store.dedupe_epoch() is None
        assert store.insert_datapoint(**_base_kwargs()) is True
        store.commit()
        assert store.dedupe_epoch() is not None
    finally:
        store.close()


def test_ac9_epoch_set_by_duplicate_only_first_insert(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        kwargs = _base_kwargs()
        # Pre-seed the exact dp_key directly, bypassing insert_datapoint, so the
        # very FIRST call to insert_datapoint against this store is itself a
        # duplicate -- the "duplicate-only first insert" entry path.
        key = dp_key(kwargs["session_id"], kwargs["model"], kwargs["token_type"],
                      kwargs["query_source"], kwargs["time_unix_nano"])
        store.db.execute(
            "INSERT INTO token_usage (dp_key, ts, tokens, usage_source) VALUES (?,?,?,?)",
            (key, "2020-06-15T00:00:00Z", 999, "otlp"))
        store.commit()
        assert store.dedupe_epoch() is None

        result = store.insert_datapoint(**kwargs)
        store.commit()
        assert result is False
        assert store.dedupe_epoch() is not None
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 10 -- the latch closes on the first SELECT that finds a committed
# epoch, and never reopens: insert once, commit, then ten more inserts on the
# same instance issue EXACTLY ONE "SELECT 1 FROM meta WHERE key=?" across
# those ten (the first, which finds the key and latches). Trap 3: match the
# exact insert-path SQL and never call dedupe_epoch() inside the window.
# ---------------------------------------------------------------------------

def test_ac10_latch_closes_after_exactly_one_meta_select_post_commit(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        store.insert_datapoint(**_base_kwargs())
        store.commit()

        calls: list = []

        def on_execute(sql):
            if sql.strip() == "SELECT 1 FROM meta WHERE key=?":
                calls.append(sql)

        store.db = _ExecuteSpy(store.db, on_execute=on_execute)

        for i in range(10):
            store.insert_datapoint(
                **_base_kwargs(session_id=f"sess-{i}", time_unix_nano=_nano("2020-06-16")))
        store.commit()

        assert len(calls) == 1
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 11 -- a rolled-back first epoch write is recovered on the next
# insert. Pins the cycle-2 fix: a latch-on-attempt implementation returns
# None forever and fails this.
# ---------------------------------------------------------------------------

def test_ac11_rollback_of_first_epoch_write_is_recovered(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        store.insert_datapoint(**_base_kwargs())
        store.db.rollback()
        assert store.dedupe_epoch() is None

        store.insert_datapoint(**_base_kwargs(session_id="sess-recovered"))
        store.commit()
        assert store.dedupe_epoch() is not None
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 12 -- dedupe_drops/dedupe_drops_by_day honor the half-open
# window: a drop dated `end` is excluded, one dated `start` is included.
# ---------------------------------------------------------------------------

def test_ac12_half_open_window_for_dedupe_reads(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        start, end = "2020-06-10", "2020-06-20"
        for day, sess in [("2020-06-09", "s-before"), ("2020-06-10", "s-start"),
                          ("2020-06-20", "s-end")]:
            kwargs = _base_kwargs(session_id=sess, time_unix_nano=_nano(day))
            store.insert_datapoint(**kwargs)
            store.insert_datapoint(**kwargs)  # duplicate -> exactly 1 drop for that day
        store.commit()

        totals = store.dedupe_drops(start, end)
        assert totals.get("output") == 1  # only "2020-06-10" is inside [start, end)

        by_day = store.dedupe_drops_by_day(start, end)
        assert set(by_day.keys()) == {"2020-06-10"}
        assert by_day["2020-06-10"]["output"] == 1
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 13 -- when the counter's UPDATE fails, insert_datapoint still
# returns False and does not raise. Trap 1: assert through the public reader
# (dedupe_drops() == {}), never SELECT COUNT(*) FROM dedupe_drops.
# ---------------------------------------------------------------------------

def test_ac13_counter_update_failure_does_not_raise_or_break_insert(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        kwargs = _base_kwargs()
        assert store.insert_datapoint(**kwargs) is True
        store.commit()

        def on_execute(sql):
            if sql.strip().startswith("UPDATE dedupe_drops"):
                raise sqlite3.Error("boom: counter UPDATE only")

        store.db = _ExecuteSpy(store.db, on_execute=on_execute)
        result = store.insert_datapoint(**kwargs)  # duplicate -> triggers the counter

        assert result is False
        # The bucket row exists with drops=0 (the INSERT OR IGNORE half landed
        # before the UPDATE raised) -- benign, and invisible through the public
        # readers, which filter falsy drops. Asserting COUNT(*)==0 here would
        # fail against this correct behavior.
        assert store.dedupe_drops("2020-06-15", "2020-06-16") == {}
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Criterion 14 -- when the epoch write fails, the insert still returns its
# correct value and does not raise.
# ---------------------------------------------------------------------------

def test_ac14_epoch_write_failure_does_not_raise_or_break_insert(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        def on_execute(sql):
            if sql.strip().startswith("INSERT OR IGNORE INTO meta"):
                raise sqlite3.Error("boom: epoch write only")

        store.db = _ExecuteSpy(store.db, on_execute=on_execute)
        result = store.insert_datapoint(**_base_kwargs())

        assert result is True
        store.commit()
        # The epoch write never succeeded, so dedupe_epoch() is still None --
        # confirming the failure was actually swallowed at the targeted
        # statement, not merely that nothing raised.
        assert store.dedupe_epoch() is None
    finally:
        store.close()
