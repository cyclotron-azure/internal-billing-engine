# Task 01: store — dedupe-drop counter + counting-start epoch

> Revised after Phase 3 cycles 1 and 2. Cycle 1: the epoch is written by the **insert
> path**, not by `_migrate()`, and it is a **UTC ISO8601 timestamp**, not a date. Cycle 2:
> the in-memory guard latches **only on a `SELECT`-confirmed epoch**, never on a write
> attempt — a rolled-back first request would otherwise leave `dedupe_epoch()` permanently
> `None`. All three changes are load-bearing; see the two Rationale notes under
> "Counting-start epoch" and do not optimize either away.

## Objective

`billing/otel/otel_store.py` persists a per-`(day, token_type, usage_source)` count of
datapoints rejected as duplicates by `INSERT OR IGNORE`, records the instant at which
that counting actually began, and exposes both to callers through a frozen read
interface. After this task a `dp_key` collision is distinguishable from telemetry that
never arrived, and a window that was never counted is distinguishable from a window with
genuinely zero collisions.

## Dependencies

- none

```yaml
# --- task ownership contract ---
writes:
  - billing/otel/otel_store.py
reads:
  - billing/otel/receiver.py
  - billing/store.py
  - README.md
depends_on: []
owner: implementer
rewrite_semantics: targeted-insertion
eval_depth: full
# full because this is the goal's contract task: it freezes a schema, a meta key, and
# three read helpers that task 02 consumes, and it adds code to the receiver's serial
# write path where a raising or slow statement degrades live billing ingest.
```

## Requirements (exhaustive — the evaluator verifies every item)

### Schema

- [ ] Add to `SCHEMA` (so a fresh database declares it) exactly this table — **six
      columns**, three of which form the primary key:
      ```sql
      CREATE TABLE IF NOT EXISTS dedupe_drops (
        day TEXT NOT NULL,            -- UTC YYYY-MM-DD, from the dropped datapoint's own ts
        token_type TEXT NOT NULL,     -- input|output|cacheRead|cacheCreation|__cost__
        usage_source TEXT NOT NULL,   -- 'otlp' | 'transcript'
        drops INTEGER NOT NULL DEFAULT 0,
        first_seen TEXT,              -- UTC ISO8601 when this bucket's first drop was counted
        last_seen TEXT,               -- UTC ISO8601 when its most recent drop was counted
        PRIMARY KEY (day, token_type, usage_source)
      );
      ```
- [ ] Cost-row drops use the literal `token_type` sentinel `__cost__`, matching the
      sentinel `dp_key` already uses for cost rows in `insert_cost_datapoint`. Do not
      invent a second spelling.
- [ ] `day` is derived from the **dropped datapoint's own timestamp** (the same
      `_ns_to_iso(...)[:10]` value the row would have carried), NOT from wall-clock
      "now", and is exactly `YYYY-MM-DD`. A replayed old export must count against the
      day it describes, because that is the day `reconcile.py` queries for.

### Migration

- [ ] Extend `_migrate()` so a pre-existing database gains the table. Additive and
      idempotent: never drop, rename, or retype a column; never rewrite an existing row;
      a second open is a no-op rather than an error.
- [ ] Note, so you do not conclude the two mechanisms disagree: `__init__` runs
      `executescript(SCHEMA)` *before* `_migrate()`, so on both fresh and existing
      databases the `CREATE TABLE IF NOT EXISTS` above already creates the table. The
      `_migrate()` entry is deliberate belt-and-braces consistent with how the existing
      columns are handled; keep it, guarded by the existing `PRAGMA`-style check pattern.
- [ ] `_migrate()` must not raise on an already-migrated or freshly-created database — a
      migration that raises on open takes the receiver down, per its own docstring.
- [ ] `_migrate()` must **not** write the epoch. See below.

### Counting-start epoch

**Rationale — do not "simplify" this back into `_migrate()`.** `_migrate()` runs on
every `OtelStore` construction, and ten call sites open the store (`reconcile.py`,
`bill.py`, `export.py`, `invoice.py`, `fabric_sync.py`, `records.py`, `repos.py` ×2,
`scheduler.py`, `receiver.py`). If an operator runs `python -m billing.reconcile` on the
new code on day X while the receiver is still running the old code, an epoch written
from `_migrate()` would be stamped X even though nothing is counted until the receiver
restarts days later — and reconcile would then report "no duplicates in this window" for
a window that was never counted. That is the exact misleading `0` this mechanism exists
to prevent. Writing the epoch from the insert path makes it mean "the counting code has
run at least once", which is the only claim it can honestly support.

- [ ] Define a module-level constant for the `meta` key name — e.g.
      `DEDUPE_EPOCH_META_KEY = "dedupe_counting_since"`. Task 02 imports this constant
      rather than hardcoding the string. (The `meta` table is already declared in
      `SCHEMA`.)
- [ ] The epoch value is a **UTC ISO8601 timestamp**, not a date. Reuse the module's
      existing `_now()` helper so the format matches the rest of the file
      (`%Y-%m-%dT%H:%M:%SZ`). Day-granularity is insufficient: a window starting on the
      epoch day is only partially counted, and task 02 must be able to say so.
- [ ] Written **once, ever**, from `insert_datapoint` and `insert_cost_datapoint` — on
      any insert *attempt*, whether it inserts or is a duplicate. Not only on a
      collision: a store that has served inserts for a week with zero collisions is
      genuinely measured, and must not read as "never counted".
- [ ] **Latch on confirmation, not on attempt.** Guard the check with an in-memory
      per-instance flag, but set that flag **only when a `SELECT` has confirmed the epoch
      is actually present in the database** — never merely because this instance issued
      the `INSERT`. Concretely, on each insert attempt: if the flag is unset, `SELECT` the
      key; if present, latch the flag and do nothing else; if absent, write it and leave
      the flag **unset** so the next insert re-checks.
- [ ] **Why (a defect found in Phase 3 cycle 2 — do not "optimize" this back to
      latch-on-attempt).** The epoch write deliberately does not `commit()`; it rides the
      caller's transaction. `receiver.py`'s transcript path calls `store.db.rollback()`
      and re-raises on any exception outside its per-record data-error set, and its own
      docstring treats `sqlite3.OperationalError` ("database is locked", "disk I/O error")
      as an *ordinary* condition on a single-host SQLite deployment. The receiver holds
      one long-lived `OtelStore`. So if the first request of the process is rolled back,
      a latch-on-attempt flag would discard the epoch write and never retry it for the
      process lifetime: `dedupe_epoch()` returns `None` forever while drops from later
      successful requests commit normally — and reconcile would then report "counting has
      never run" alongside a real drop count. Latching on confirmation costs one
      primary-key lookup on a one-row table per insert until the epoch is committed, and
      exactly zero forever after.
- [ ] Writing the epoch must never raise into the caller — same `sqlite3.Error` guard as
      the increment below.
- [ ] Do NOT add a general `get_meta`/`set_meta` API to `OtelStore` (unlike
      `billing/store.py`'s `Store`). Add only what this task needs, so the public surface
      stays the frozen interface below.

### Increment

- [ ] Increment at the single choke point where a duplicate is already detected: the
      `cur.rowcount > 0` returns in `insert_datapoint` and `insert_cost_datapoint`. When
      `rowcount == 0`, count a drop; when it inserted, do not.
- [ ] Use the **portable two-statement form**, not `ON CONFLICT ... DO UPDATE`:
      `INSERT OR IGNORE` the bucket row (setting `drops = 0` and `first_seen`), then
      `UPDATE ... SET drops = drops + 1, last_seen = ?`. Upsert syntax needs SQLite
      3.24+ and the production host's sqlite3 version is not pinned anywhere in this
      repo — do not add a version dependency on a path that must not fail.
- [ ] The increment must **never raise into the caller.** Wrap it so a failure to record
      a drop still returns the correct `False` from the insert method. Losing a
      diagnostic count is acceptable; breaking billing ingest is not. Catch
      `sqlite3.Error` specifically, not bare `Exception`. (This matters beyond
      robustness: `receiver.py`'s per-record error handling would otherwise turn a
      counter failure into a per-record *billing* rejection.)
- [ ] The increment touches the database **only on the collision path.** An inserting
      call must issue no extra statement beyond the epoch check, which is one
      primary-key lookup per insert until the epoch is committed and zero thereafter.
- [ ] Do not `commit()` inside the increment or the epoch write. Both participate in the
      caller's transaction, which `receiver.py` already commits per request on both the
      OTLP and transcript paths.
- [ ] **Cost note, corrected from the first draft**: collisions are *not* uniformly rare.
      A retried OTLP export re-sends the whole batch, so every datapoint in it collides
      at once — the path is bursty. What keeps this bounded is that both statements are
      primary-key-targeted against a table holding at most a few rows per day, not the
      rarity of the path. Do not add an index, a scan, or a read-modify-write in Python
      on this path.

### Frozen read interface (task 02 consumes exactly these)

- [ ] `OtelStore.dedupe_drops(self, start: str, end: str) -> dict[str, int]`
      — total drops per `token_type` for `day >= start AND day < end` (half-open, the
      same convention `reconcile.otel_totals` uses). Summed across `usage_source`. Token
      types with no drops are **absent** from the dict, never present with `0`.
- [ ] `OtelStore.dedupe_drops_by_day(self, start: str, end: str) -> dict[str, dict[str, int]]`
      — `{day: {token_type: drops}}` over the same half-open window. Day keys are exactly
      `YYYY-MM-DD`. Days with no drops are absent.
- [ ] `OtelStore.dedupe_epoch(self) -> str | None`
      — the UTC ISO8601 counting-start timestamp, or `None` if no insert has ever been
      attempted against this database by counter-aware code. Task 02 renders `None` as
      "never counted", never as `0`.
- [ ] All three are methods on `OtelStore` using `self.db`. No new `sqlite3.connect`
      call anywhere.

### Constraints restated in-task

- [ ] **Stdlib only.** No third-party import may enter `billing/`. This is the single
      easiest way to break this codebase.
- [ ] **Single-host, single-connection SQLite.** Do not enable WAL, do not pass
      `check_same_thread=False`, do not add a pool, do not thread anything.
- [ ] Do NOT modify `billing/otel/receiver.py`. Both ingest paths already route through
      `store.insert_datapoint` / `insert_cost_datapoint`, so the choke points above cover
      both surfaces with zero receiver changes — and moving the epoch to the insert path
      is specifically what keeps that true. If you believe a receiver change is required,
      stop and report that instead of making it.
- [ ] Do NOT change any existing column, key function (`dp_key`, `transcript_key`), or
      the `request_id` validation behavior in either insert method. Those carry extensive
      recorded rationale in their docstrings; leave them alone.
- [ ] Do NOT add a `request_id` column (explicitly out of scope for this goal).

## Acceptance Criteria

1. A fresh `OtelStore(tmp_path)` has a `dedupe_drops` table with exactly the six columns
   named above and a three-column primary key — verification: unit test asserting
   `PRAGMA table_info(dedupe_drops)` column names and the PK via `PRAGMA index_list` /
   `index_info`.
2. Inserting the same OTLP datapoint twice returns `True` then `False`, and leaves
   `dedupe_drops` holding exactly one row with `drops = 1`, whose `day` equals the
   datapoint's own `ts[:10]` and **not** today's date — verification: unit test using a
   `time_unix_nano` for a deliberately past day.
3. A third identical insert raises `drops` to 2 and advances `last_seen` while leaving
   `first_seen` unchanged — verification: unit test.
4. A successful (non-duplicate) insert adds no `dedupe_drops` row — verification: unit
   test asserting the table is empty after one clean insert.
5. A duplicate **transcript** insert counts a drop with `usage_source = 'transcript'`,
   and a duplicate **cost** insert counts one with `token_type = '__cost__'` —
   verification: unit test covering both.
6. Opening the `legacy_schema_db_path` fixture migrates it: `dedupe_drops` exists, every
   pre-existing row is preserved byte-for-byte, and a second open changes nothing —
   verification: unit test against the existing `tests/conftest.py` fixture.
7. **A store that is opened (and migrated) but never inserted into has
   `dedupe_epoch() is None`** — verification: unit test that constructs `OtelStore`,
   calls only read methods, closes, reopens, and asserts `None`. This is the criterion
   that pins the cycle-1 fix; an epoch written from `_migrate()` fails it.
8. The first insert attempt sets the epoch to an ISO8601 timestamp, and a later insert
   on a subsequent reopen leaves that value **unchanged** — verification: unit test that
   inserts, records the epoch, reopens, inserts again, and asserts equality.
9. The epoch is set by a *successful* first insert and equally by a *duplicate-only*
   first insert — verification: unit test covering both entry paths.
10. The latch closes on the first lookup that finds a committed epoch, and never reopens.
    Insert once, `commit()`, then perform ten more inserts on the same instance: **exactly
    one** `SELECT ... FROM meta` occurs across those ten — the first one, which finds the
    key and latches; the remaining nine issue zero — verification: unit test wrapping
    `db.execute` and counting. (Note the count is one, not zero: the flag is only set by a
    `SELECT` that *found* the key, so the insert immediately after the commit is the one
    that closes the latch. A test asserting zero here is unsatisfiable by a correct
    implementation.)
11. **A rolled-back first epoch write is recovered on the next insert.** Insert once, then
    `rollback()`; assert `dedupe_epoch()` is `None`; insert again on the *same* store
    instance and `commit()`; assert the epoch is now set — verification: unit test. This
    is the criterion that pins the cycle-2 fix; a latch-on-attempt implementation returns
    `None` forever and fails it.
12. `dedupe_drops(start, end)` and `dedupe_drops_by_day(start, end)` honor the half-open
    window: a drop dated `end` is excluded, one dated `start` included — verification:
    unit test seeding drops dated `start - 1`, `start`, and `end`.
13. When the counter's `UPDATE` fails, `insert_datapoint` still returns `False` and does
    not raise — verification: unit test monkeypatching `execute` to raise `sqlite3.Error`
    on the counter statement **only**, not on the main insert.
14. When the epoch write fails, the insert still returns its correct value and does not
    raise — verification: unit test with a narrowly targeted `sqlite3.Error`.
15. `python -m pytest tests/test_otel_store.py -q` still exits 0 — verification: command
    output. No existing store test may be modified to accommodate this change; if one
    fails, that is a regression to fix in the implementation.

## Files to Read

- `billing/otel/otel_store.py` — the module you are editing. Read `SCHEMA`,
  `_existing_columns`, `_migrate`, `_now`, `_ns_to_iso`, `dp_key`, `transcript_key`,
  `insert_datapoint`, and `insert_cost_datapoint` in full before writing anything. The
  docstrings carry recorded decisions you must not undo.
- `billing/otel/receiver.py` — the OTLP datapoint loop in `ingest_metrics_payload` and
  the transcript loop that calls `store.insert_datapoint(**row)`, read-only, to confirm
  both duplicate paths flow through the two insert methods and that the per-request
  `store.commit()` makes an in-increment commit unnecessary. Also read the module's
  per-record error-handling constant to see why the counter must not raise.
- `billing/store.py` — the `set_meta`/`get_meta` pattern on the *other* store, as a
  style reference only. Do not copy the whole API over.
- `README.md` — the single-host/single-connection SQLite constraint and the
  `otel_store.py` bullet. Ground truth.
- `tests/conftest.py` — the `tmp_db_path` and `legacy_schema_db_path` fixtures, and
  `seed_otlp_rows` (a plain module-level function, **not** a pytest fixture), so you know
  what task 04 will test against.
- `.claude/skills/test-ladder/SKILL.md` — climb rungs 1–2 only. Do NOT run
  `python -m pytest -q` (rung 3); that is the orchestrator's call at cycle end.

## Files to Create / Change

- `billing/otel/otel_store.py` — `SCHEMA` gains `dedupe_drops`; `_migrate()` gains the
  table migration (and must **not** write the epoch); `insert_datapoint` and
  `insert_cost_datapoint` gain the guarded increment on their duplicate path and the
  at-most-once-per-process epoch write on any insert attempt; three new read methods and
  one new module constant.

## Constraints

- Must: reuse `self.db` and `_now()`; keep every change additive; keep the increment off
  the success path; catch `sqlite3.Error` around both the counter write and the epoch
  write and swallow it.
- Must: use the portable `INSERT OR IGNORE` + `UPDATE` pair, not `ON CONFLICT`.
- Must: write the epoch from the insert path only, never from `_migrate()`.
- Must NOT: modify `billing/otel/receiver.py`, `billing/reconcile.py`, any test file, or
  anything outside the write fence.
- Must NOT: import outside the standard library.
- Must NOT: enable WAL, thread the receiver, add a connection pool, or pass
  `check_same_thread=False`.
- Must NOT: alter `dp_key`, `transcript_key`, the `request_id` validation, or any
  existing column.

## Verification

- Targeted test command: `python -m pytest tests/test_otel_store.py -q`
- Also capture: a short scratchpad script (write it under the session scratchpad
  directory, never in the repo) that (a) opens a tmp store and calls only a read method,
  printing `dedupe_epoch()` — must be `None`; (b) inserts one datapoint twice, printing
  the resulting `dedupe_drops` rows and `dedupe_epoch()`. Paste its output in the
  completion report — task 04 has not written the new tests yet, so this is the evidence
  that both the increment and the epoch semantics actually behave as specified.
