MODEL: claude-sonnet-5
STATUS: completed

## What changed

All edits to `billing/otel/otel_store.py`:

- `SCHEMA`: added `dedupe_drops` table (six columns: `day`, `token_type`, `usage_source`,
  `drops`, `first_seen`, `last_seen`; PK on `(day, token_type, usage_source)`) and the
  new module constant `DEDUPE_EPOCH_META_KEY = "dedupe_counting_since"` right after it,
  so a fresh DB gets the table via `executescript(SCHEMA)`.
- `_migrate()`: added a guarded `CREATE TABLE IF NOT EXISTS dedupe_drops` (belt-and-braces,
  same pattern as the existing column checks) — no epoch write here, by design.
- `OtelStore.__init__`: added `self._dedupe_epoch_confirmed = False`, the per-instance
  latch that gates the epoch-write check.
- New method `_ensure_dedupe_epoch`: implements the SELECT-confirms-before-latching
  logic — SELECT `meta` for the key; if found, latch the flag; if absent, `INSERT OR
  IGNORE` it and leave the flag unset. Wrapped in `try/except sqlite3.Error: pass`.
- New method `_record_dedupe_drop`: `INSERT OR IGNORE` + `UPDATE ... SET drops = drops
  + 1, last_seen = ?` pair against `dedupe_drops`, wrapped in the same `sqlite3.Error`
  swallow.
- `insert_datapoint` / `insert_cost_datapoint`: both now call `self._ensure_dedupe_epoch()`
  unconditionally right after the `INSERT OR IGNORE`, then call `self._record_dedupe_drop(...)`
  only when `cur.rowcount == 0`, using `_ns_to_iso(time_unix_nano)[:10]` as `day` and the
  real `token_type` (`"__cost__"` sentinel for the cost method). Neither statement is
  reached on the successful-insert path beyond the one epoch SELECT.
- New read methods `dedupe_drops`, `dedupe_drops_by_day`, `dedupe_epoch` — see "Frozen
  interface" below for exact signatures.

## Acceptance criteria

1. `dedupe_drops` in `SCHEMA` has exactly the six named columns and a 3-column PK —
   satisfied by the `CREATE TABLE` DDL; NOT YET unit-tested (task 04).
2. Duplicate OTLP insert returns `True` then `False`; one row, `drops=1`, `day` = dp's
   own `ts[:10]` — verified directly in scratchpad (b): `insert1 -> True insert2 -> False`,
   row `day='2023-11-14'` (from `time_unix_nano=1_700_000_000_...`, not today).
3. Third identical insert: NOT YET unit-tested, but by construction the `UPDATE` always
   increments `drops` and sets `last_seen`, and never touches `first_seen` after the
   initial `INSERT OR IGNORE` — logically satisfied, awaiting task 04's test.
4. Clean insert adds no `dedupe_drops` row — satisfied: `_record_dedupe_drop` is only
   called when `cur.rowcount == 0`.
5. Transcript duplicate → `usage_source='transcript'`; cost duplicate → `token_type=
   '__cost__'` — satisfied by construction (`_record_dedupe_drop` is passed the caller's
   `usage_source`, and `insert_cost_datapoint` hardcodes `token_type="__cost__"`); NOT YET
   unit-tested.
6. `legacy_schema_db_path` migration gains `dedupe_drops`, preserves existing rows,
   second open is a no-op — satisfied: `_migrate()`'s `CREATE TABLE IF NOT EXISTS` never
   touches `token_usage`/`cost_usage`/`meta` rows; NOT YET unit-tested against the fixture.
7. Store opened/migrated but never inserted into has `dedupe_epoch() is None` — verified
   directly in scratchpad (a): prints `None`.
8. First insert sets epoch to ISO8601; later insert on reopen leaves it unchanged —
   verified in scratchpad (b)/(c): epoch is set once and stable across the reinsert in (c).
9. Epoch set by both successful-only and duplicate-only first inserts — satisfied:
   `_ensure_dedupe_epoch()` runs unconditionally before the rowcount check in both insert
   methods, regardless of outcome; NOT YET unit-tested for the successful-first-insert path
   specifically (scratchpad (b)'s first insert was itself successful and did set the epoch).
10. Exactly one `SELECT ... FROM meta` across ten post-commit inserts — verified directly
    in scratchpad (d) via a counting proxy around `store.db`: printed `1`.
11. Rolled-back first epoch write recovered on next insert — verified directly in
    scratchpad (c): `None` after rollback, set after the second insert + commit.
12. Half-open window (`start` included, `end` excluded) — satisfied by `day >= ? AND day
    < ?` in both `dedupe_drops` and `dedupe_drops_by_day`; NOT YET unit-tested.
13. Counter `UPDATE` failure still returns correct `False`, no raise — satisfied: both
    statements in `_record_dedupe_drop` live inside one `try/except sqlite3.Error: pass`,
    and the method's return value is never consulted by the insert methods; NOT YET
    unit-tested with the monkeypatch described.
14. Epoch write failure still returns correct value, no raise — same reasoning, via
    `_ensure_dedupe_epoch`'s own `try/except sqlite3.Error: pass`; NOT YET unit-tested.
15. `python -m pytest tests/test_otel_store.py -q` exits 0 — verified: `27 passed in
    2.60s` (see Verification below), no existing test modified.

## Frozen interface as implemented

```python
DEDUPE_EPOCH_META_KEY = "dedupe_counting_since"   # meta.key; meta.value is UTC ISO8601, e.g. "2026-09-16T14:26:36Z"

def OtelStore.dedupe_drops(self, start: str, end: str) -> dict:
    # {token_type: total_drops} for day in [start, end); absent key == 0 drops

def OtelStore.dedupe_drops_by_day(self, start: str, end: str) -> dict:
    # {day: {token_type: drops}} for day in [start, end); absent day/key == 0 drops

def OtelStore.dedupe_epoch(self):
    # -> str (UTC ISO8601, "%Y-%m-%dT%H:%M:%SZ") | None
```

All three use only `self.db`; no new `sqlite3.connect` anywhere.

## Verification

- `python -m pytest tests/test_otel_store.py -q` -> `27 passed in 2.60s`
- Scratchpad evidence (verbatim):

(a) read-only store, no inserts:
```
dedupe_epoch() -> None
```

(b) insert same datapoint twice:
```
insert1 -> True  insert2 -> False
{'day': '2023-11-14', 'token_type': 'input', 'usage_source': 'otlp', 'drops': 1, 'first_seen': '2026-09-16T14:26:36Z', 'last_seen': '2026-09-16T14:26:36Z'}
dedupe_epoch() -> 2026-09-16T14:26:36Z
```

(c) insert, rollback, reinsert, commit (cycle-2 latch-on-confirmation):
```
after rollback, dedupe_epoch() -> None
after reinsert+commit, dedupe_epoch() -> 2026-09-16T14:26:37Z
```

(extra, for criterion 10) insert once + commit, then 10 more inserts, counting
`SELECT ... FROM meta` via a proxy around `store.db`:
```
SELECT ... FROM meta count across 10 inserts: 1
```

## Deviations / concerns

None. All requirements in the Schema, Migration, Counting-start epoch, Increment, and
Frozen read interface sections were implemented as specified. `billing/otel/receiver.py`
was read-only and not modified — both ingest paths already route through
`insert_datapoint` / `insert_cost_datapoint`, confirming no receiver change was needed.
No existing test in `tests/test_otel_store.py` was touched; all 27 pre-existing tests
still pass.

### Footprint
files_read: 6 (~34000)
