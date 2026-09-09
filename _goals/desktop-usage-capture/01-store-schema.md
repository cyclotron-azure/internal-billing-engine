# Task 01: Store schema — transcript-sourced usage columns

## Objective

`billing/otel/otel_store.py` carries an additive, idempotent migration adding `usage_source` +
`entrypoint` to `token_usage` and `usage_source` + `cost_source` to `cost_usage`, a collision-free
`dp_key` derivation for transcript rows, and insert support for them. Existing databases migrate in
place with no data loss and no change to how existing rows bill. This is the CONTRACT task — tasks
02–07 build against the column names, defaults, and method signatures frozen here.

## Dependencies

- 00 (test scaffold; the legacy-schema fixture this task's migration test needs)

```yaml
# --- task ownership contract ---
writes:
  - billing/otel/otel_store.py
  - tests/test_otel_store.py
reads:
  - billing/otel/receiver.py
  - billing/otel/attribute.py
  - billing/otel/bill.py
  - billing/otel/export.py
  - tests/conftest.py
depends_on:
  - "00-test-scaffold"
owner: implementer
rewrite_semantics: targeted-insertion
eval_depth: full
```

## Requirements (exhaustive — the evaluator verifies every item)

**Columns**

- [ ] `token_usage` gains `usage_source TEXT NOT NULL DEFAULT 'otlp'` and `entrypoint TEXT`.
- [ ] `cost_usage` gains `usage_source TEXT NOT NULL DEFAULT 'otlp'` **and** `cost_source TEXT NOT NULL
      DEFAULT 'actual'`.
      **`usage_source` on `cost_usage` is mandatory and is not symmetry for its own sake.**
      `attribute.py`'s `resolved_view` is applied to `cost_usage` at `bill.py:57` and `export.py:78`.
      Task 04 adds an `attribution_source` branch that references `usage_source`; if the column is
      missing from `cost_usage`, that SQL fails to prepare and `python -m billing.otel.bill` and the
      lake export both die outright — for the existing OTLP-only fleet, not just for desktop rows.
- [ ] The migration runs on store open, is **idempotent**, and is **additive only** — no column dropped,
      renamed, or retyped; no existing row rewritten.
- [ ] The migration inspects existing columns via `PRAGMA table_info` before each `ALTER TABLE`, so an
      already-migrated database is a no-op rather than an error.
- [ ] A fresh database created from `SCHEMA` and a migrated legacy database converge on identical
      columns, types, and defaults. Drift between the two paths is a silent, long-lived bug.
- [ ] Every pre-existing row reads back as `usage_source='otlp'` / `cost_source='actual'`.

**Dedupe key — the silent under-billing defect**

- [ ] Add a **separate** transcript key function; do NOT overload the existing `dp_key`. The existing
      `dp_key(session_id, model, token_type, query_source, time_unix_nano)` at `otel_store.py:138`
      contains no request identifier. Task 02 emits second-granularity timestamps, so two desktop
      assistant messages in the same session, model, and second produce an IDENTICAL key, and
      `INSERT OR IGNORE` silently drops the second — under-billing a paying client with no error
      anywhere. This is the exact failure the goal exists to prevent, reintroduced by the key.
- [ ] The transcript key is derived from `(session_id, request_id, token_type)` and is independent of
      timestamp granularity.
- [ ] Document in the same comment why `query_source` is **excluded** from the transcript key, unlike
      the OTLP `dp_key` which includes it. The reason: a `request_id` is unique to one API request,
      which belongs to exactly one file and therefore to exactly one `query_source` — measured at 0
      collisions across 314 real request groups. If that ever ceases to be true, a main and a sidechain
      row for one `request_id` would silently collide and the subagent row would be dropped, so the
      asymmetry must be a recorded decision rather than an oversight a future reader has to reconstruct.
- [ ] **`request_id` is NOT unique per assistant message — do not assume it is.** Measured against real
      transcripts: 402 usage-bearing rows carry only 187 distinct `requestId`s, and 149 of those repeat
      up to 5 times. Rows sharing a `(requestId, message.id)` are **cumulative streaming snapshots of a
      single API request**: `input_tokens`, `cache_creation_input_tokens`, and
      `cache_read_input_tokens` hold constant while `output_tokens` grows. The terminal block is the
      one with the highest `apiBlockIndex` — not the one with a non-null `stop_reason`, which is
      multi-valued for 108 of 230 real groups.
- [ ] Task 02 and task 06 collapse each request to its terminal block and emit ONE record per request.
      This key's job is therefore to be a **replay guard**, not a semantic collapse — by the time a
      record reaches the store there is exactly one per `(session_id, request_id, token_type)`.
      **Do not rely on `INSERT OR IGNORE` to do the collapsing.** It keeps the FIRST insert, which is
      `apiBlockIndex=0` — the snapshot with the smallest `output_tokens` — and would discard 34% of
      output tokens, under-billing by ~8.6% overall. The correct total is the LAST block, not the first
      and not the sum.
- [ ] The cost row's key uses the same function with a distinct sentinel token type, so a record's cost
      row never collides with any of its four token rows.
- [ ] The exact key composition is documented verbatim in a comment, since tasks 02, 03, and 07 depend on it.
- [ ] `dp_key` for OTLP rows is unchanged, and a transcript key can never equal an OTLP key.

**Insert signatures**

- [ ] `insert_datapoint` and `insert_cost_datapoint` keep working unchanged for existing OTLP callers —
      every new parameter is keyword-only with a default matching current OTLP behavior.
- [ ] `insert_datapoint` accepts `usage_source`, `entrypoint`, and `request_id`.
- [ ] `insert_cost_datapoint` accepts `usage_source`, `cost_source`, and `request_id`.
- [ ] `user_email`, `user_id`, and `org_id` remain first-class parameters on both, and the task must not
      make them optional — identity must be storable for transcript rows exactly as it is for OTLP rows.
- [ ] No third-party import is added.

## Acceptance Criteria

1. Opening a store against the task-00 legacy-schema fixture adds all four columns and leaves every
   existing row's billed value identical — verification: unit test in `tests/test_otel_store.py` using
   the legacy fixture, asserting column presence and unchanged row values.
2. Opening an already-migrated store a second time raises nothing and changes nothing — verification:
   unit test invoking the migration twice.
3. A fresh DB and a migrated DB agree on columns for BOTH `token_usage` and `cost_usage`, compared as
   **set-equality over `(name, type, notnull, dflt_value)`** — deliberately NOT including `cid`, because
   `ALTER TABLE` can only append while a fresh `SCHEMA` may declare the column mid-table, so an
   order-sensitive comparison would fail a perfectly correct implementation — verification: unit test.
4. Inserting the same transcript datapoint twice yields exactly one row — verification: unit test.
5. **Two records differing ONLY in `request_id`, with identical session, model, token_type and
   timestamp, produce TWO rows** — verification: unit test. This is the regression test for the silent
   under-billing defect; criterion 4 alone would pass while the bug is present.
5b. **The converse — a replayed record with the same `(session_id, request_id, token_type)` but a
   LARGER token count does NOT overwrite and does NOT add.** Insert `output=5`, then insert `output=209`
   for the same key; assert exactly one row survives and state which value it holds. This pins the
   `INSERT OR IGNORE` first-writer-wins semantics explicitly, so tasks 02 and 06 cannot quietly depend
   on the store to pick the right snapshot — it cannot, and this test proves it — verification: unit test.
6. A transcript row's cost key never equals any of its four token keys, and no transcript key equals an
   OTLP `dp_key` for the same session and timestamp — verification: unit test asserting inequality.
7. `cost_usage` carries `usage_source`, proven by a query filtering on it — verification: unit test
   selecting `WHERE usage_source = 'otlp'` against `cost_usage` and getting the seeded rows back.

## Files to Read

- `billing/otel/otel_store.py` — the file being changed: `SCHEMA`, `dp_key` at line 138, `OtelStore.__init__`'s
  `executescript(SCHEMA)`, and both insert methods.
- `billing/otel/receiver.py` — how the insert methods are called today, so signatures stay compatible.
- `billing/otel/attribute.py` — `resolved_view` applies `attribution_source` to whichever table it is given.
- `billing/otel/bill.py` line 57 and `billing/otel/export.py` line 78 — the two `resolved_view('cost_usage')`
  call sites that make `usage_source` on `cost_usage` mandatory.
- `tests/conftest.py` — the legacy-schema and seeding fixtures from task 00.
- `README.md` — "The constraint that shapes everything" (SQLite single-host, single-connection).
- `.claude/skills/test-ladder/SKILL.md`

## Files to Create / Change

- `billing/otel/otel_store.py` — add columns to `SCHEMA`; add a guarded idempotent migration invoked on
  open; add the transcript key function; extend both insert methods with keyword-only parameters.
- `tests/test_otel_store.py` — the seven acceptance criteria above.

## Constraints

- Must: keep the store single-connection; preserve `INSERT OR IGNORE` dedupe; keep existing signatures working.
- Must: guard each `ALTER TABLE` with `PRAGMA table_info` — a live billing database is in use, and a
  migration that raises on open takes the receiver down.
- Must NOT: add a third-party import; drop, rename, or retype any column; rewrite existing rows; change
  `dp_key` for OTLP rows; introduce threading or a second connection.
- Must NOT: create a new table — the agreed storage decision is existing tables plus columns.
- Must NOT: modify `attribute.py`, `bill.py`, or `export.py` — other tasks own them.

## Verification

- Targeted test command: `python -m pytest tests/test_otel_store.py -v`
- Per the test-ladder convention map, a change here impacts every test that opens a store; at rung 2 run
  the impacted set that exists at the time.
