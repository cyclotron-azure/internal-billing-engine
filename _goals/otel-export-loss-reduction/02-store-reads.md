# Task 02: two frozen read methods on OtelStore

## Objective

`OtelStore` exposes exactly two new read-only methods — an ingest-freshness reader and a
batched "does this session already have OTLP rows" membership test. These are the contract
that task 03's health route and its CLI-ingest guard both build against. No schema change,
no write path change, no new table.

## Dependencies

- none

```yaml
# --- task ownership contract ---
writes:
  - billing/otel/otel_store.py
reads:
  - billing/otel/receiver.py         # how the receiver holds its single connection
depends_on: []
owner: implementer
rewrite_semantics: targeted-insertion
eval_depth: full
# full: contract task. Two downstream consumers (task 03's route and its ingest guard)
# build against these signatures, and the membership test gates whether a row is billed.
# A wrong answer from it either double-bills a client or silently discards recoverable
# usage.
```

## Requirements (exhaustive — the evaluator verifies every item)

### `last_ingest_at(usage_source=None) -> str | None`

- [ ] Returns the greatest `MAX(ingested_at)` across **both** `token_usage` and
      `cost_usage`, as the stored UTC ISO8601 string. Both tables carry `usage_source` and
      `ingested_at`, and the receiver inserts into them from two **independent** branches
      (`receiver.py:163` for `claude_code.token.usage`, `:176` for
      `claude_code.cost.usage`), so a payload can carry cost datapoints and no token
      datapoints. A `token_usage`-only reader would report a live receiver as stale.
- [ ] `usage_source=None` (default) considers all rows. A non-`None` value filters to that
      `usage_source` exactly, with no `LIKE`, no case folding, and no normalization.
- [ ] Returns `None` — not `""`, not `0`, not a sentinel date — when no row matches. An
      empty table and a stalled receiver are different conditions and the caller must be
      able to tell them apart.
- [ ] Reads `ingested_at` (when the receiver stored it), **not** `ts` (when the datapoint
      was recorded). A replayed export has old `ts` values and proves the receiver is
      alive; using `ts` would report a live receiver as stale.
- [ ] Uses the existing `self.db` connection. No new `sqlite3.connect`, no
      `check_same_thread`, no WAL pragma, no pool.
- [ ] Read-only: issues no `INSERT`/`UPDATE`/`DELETE`/`CREATE` and no `commit()`.

### `sessions_with_otlp_rows(session_ids) -> set`

- [ ] Accepts any iterable of session id strings and returns the subset that has at least
      one `usage_source = 'otlp'` row in **`token_usage` OR `cost_usage`**.
      **Both tables, and this is the safety-critical part of the contract.** A transcript
      record inserts a cost row as well as its token rows, and `invoice.py:215`/`:224-225`
      sum `actual_cost + estimated_cost` into `total_billed` — so the cost side is billed.
      Because the receiver's token and cost branches are independent
      (`receiver.py:163`/`:176`), a partial flush can leave a session with OTLP rows in
      `cost_usage` and **none** in `token_usage`. A `token_usage`-only guard would pass
      that session, accept its transcript, and land a `cost_source='rate_card'` row beside
      the existing `cost_source='actual'` row — billing the client twice.
      `transcript_key` cannot stop it: it and `dp_key` are *designed* never to collide
      (`otel_store.py:217-220`).
- [ ] An empty or falsy input returns an empty `set()` **without issuing a query**. A bare
      `IN ()` is a syntax error in SQLite, and a query that builds `IN (NULL)` instead
      would silently return nothing and be read as "safe to insert" — the double-billing
      direction.
- [ ] Covers both tables in **one** statement per chunk, and **binds each chunk exactly
      once**. Use a `VALUES` CTE, not two `IN` lists:

      ```sql
      WITH ids(x) AS (VALUES (?),(?),...)      -- N placeholders, bound ONCE
      SELECT session_id FROM token_usage
        WHERE usage_source='otlp' AND session_id IN (SELECT x FROM ids)
      UNION
      SELECT session_id FROM cost_usage
        WHERE usage_source='otlp' AND session_id IN (SELECT x FROM ids)
      ```

      **Why this shape and not the obvious one.** A two-arm `UNION` that repeats the `IN`
      list binds every id twice: for a 500-id chunk that is 500 x 2 arms + 2
      `usage_source` binds = **1002 parameters**, which exceeds the 999
      `SQLITE_MAX_VARIABLE_NUMBER` cap on older sqlite3 builds and raises
      `OperationalError: too many SQL variables`. The Phase 3 evaluator reproduced this at
      `conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)` and confirmed the
      single-bind form above succeeds with 500 parameters. **This fault is invisible in
      development** — this machine's cap is 32766 — and appears only on the unpinned
      production host. Its consequence is not a wrong bill but a silent permanent failure:
      the guard raises, this task forbids swallowing `sqlite3.Error`, the receiver rolls
      back and re-raises, the sweeper reads `transport_fail` and never advances state, so
      CLI backfill retries forever and the always-exit-0 hook shows nobody.
- [ ] The invariant to preserve is **`ids_per_chunk x arms_binding_them + literal_binds
      <= 999`**. With the single-bind CTE that is `500 x 1 + 2 = 502`. If anyone ever
      reverts to two `IN` lists, the chunk must drop to **498** (`498 x 2 + 2 = 998`);
      499 does not fit (`1000`). Stating the arithmetic here is what stops the constant and
      the statement shape from drifting apart again.
- [ ] Chunks the `IN` list at **500 ids per statement** and unions the results. The
      production host's sqlite3 build is unpinned and older builds cap
      `SQLITE_MAX_VARIABLE_NUMBER` at 999. The constant is justified by this method's
      **public contract accepting an unbounded iterable** -- not by the sweeper exceeding
      it: `MAX_BATCH_SIZE = 500` caps a POST at 500 records, so the receiver can never hand
      the guard more than 500 distinct session ids and production sees exactly one chunk.
      The chunking still has to be correct and tested, because the method is public and
      criterion 6 exercises it directly.
- [ ] Deduplicates the input before chunking, so a caller passing 600 copies of one id
      issues one statement rather than two.
- [ ] Uses parameter binding (`?`) for every id. No string interpolation of ids into SQL,
      ever — session ids arrive from a client-posted payload.
- [ ] Filters on `usage_source = 'otlp'` and nothing else. It must **not** additionally
      filter on `entrypoint`: OTLP rows carry a NULL `entrypoint` (the column is
      transcript-rows-only per the schema comment), so an `entrypoint` predicate would
      match zero rows and make the guard a no-op.
- [ ] Read-only, same connection, same prohibitions as above.

### Both

- [ ] Standard library only. No new import beyond what `otel_store.py` already imports.
- [ ] Neither method reads or returns the raw `repo` column, and neither introduces a
      persisted repo attribution. Repo resolution stays a query-time concern elsewhere.
- [ ] `dp_key`, `transcript_key`, `SCHEMA`, `_migrate`, `insert_datapoint`,
      `insert_cost_datapoint`, the transcript insert path, and the `dedupe_drops` counter
      from the previous goal are all **byte-unmodified**.
- [ ] Docstrings state the freshness/`ts` distinction and the `IN ()` hazard, because both
      are the kind of thing a later reader will "simplify" away.

## Acceptance Criteria

1. `last_ingest_at()` on a store with zero rows returns `None` — verification: unit test
2. `last_ingest_at()` returns the maximum `ingested_at` across rows inserted out of
   chronological order (insert a later `ingested_at` first, then an earlier one), and
   does so across **both** tables, not just whichever one was written last —
   verification: unit test
3. `last_ingest_at(usage_source="otlp")` ignores a transcript row that is the newest row
   in either table, and `last_ingest_at()` returns that transcript row's value — one
   fixture, both assertions, so the filter is proven to actually filter —
   verification: unit test
4. A row whose `ts` is far in the past but whose `ingested_at` is now reports as fresh —
   this is the assertion that fails if someone swaps the column — verification: unit test
5. `sessions_with_otlp_rows([])` returns `set()` and issues **zero** queries, proven by an
   execute-counting spy on the connection rather than by inspecting SQL text —
   verification: unit test
6. `sessions_with_otlp_rows` over 1200 distinct ids, 3 of which exist, returns exactly
   those 3 and issues exactly 3 statements (1200/500 rounded up) — verification: unit test
7. 600 copies of a single existing id returns that one id and issues exactly 1 statement —
   verification: unit test
8. A session with only `usage_source='transcript'` rows is **not** returned; a session with
   both an OTLP and a transcript row **is** returned — verification: unit test
9. A session whose only OTLP row has `entrypoint IS NULL` **is** returned. This is the
   criterion that fails if an `entrypoint` predicate is added — verification: unit test
10. A session id containing a SQL metacharacter (`' OR 1=1 --`) returns no match and does
    not raise — verification: unit test
11. Calling both methods writes nothing. Assert it **two** ways: (a) an execute-counting
    spy shows no statement beginning with `INSERT`/`UPDATE`/`DELETE`/`CREATE`/`DROP`/
    `ALTER` and no `commit()`; and (b) a full-file SHA-256 taken after committing and
    closing the connection is identical before and after.
    **Do not use `PRAGMA data_version` or file size for this** — the Phase 3 evaluator
    demonstrated both are unchanged across a same-connection `INSERT` + `commit()`
    (size 8192 -> 8192, `data_version` 1 -> 1), which would make this criterion pass
    against a method that writes — verification: unit test
12. `git diff billing/otel/otel_store.py` shows additions only within the class plus
    imports; no deletion or modification of any pre-existing line — verification: command
    output
13. **The C1 criterion.** A session whose only OTLP row is in `cost_usage` — zero
    `token_usage` rows — **is** returned by `sessions_with_otlp_rows`. Build it through
    `insert_cost_datapoint` alone, exactly as the receiver's cost branch would on a
    partial flush. This is the criterion that fails if the guard is narrowed to one table,
    and the failure mode it prevents is double-billing a client — verification: unit test
14. `last_ingest_at()` reflects a `cost_usage` row that is newer than every `token_usage`
    row, and `last_ingest_at(usage_source="otlp")` does too. Fails if the reader is
    narrowed to one table — verification: unit test
15. **The parameter-cap regression test.** With
    `conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)` applied to the store's
    connection, `sessions_with_otlp_rows` over a full 500-id chunk succeeds and returns
    the right ids. Without this, criteria 6, 7 and mutation (f) all pass on a modern
    build (cap 32766) while production fails — it is the only way this class of defect
    is catchable in CI — verification: unit test

16. **Added after Phase 5 final audit.** `sessions_with_otlp_rows` propagates
    `sqlite3.Error` rather than swallowing it. Force the connection to raise (e.g. close it,
    or corrupt the query via a monkeypatched `execute`) and assert the exception propagates
    out of the call rather than being caught and turned into `set()`. Before this test
    existed, a mutation adding `try/except sqlite3.Error: return set()` escaped all 421
    tests -- `set()` reads downstream as "no OTLP rows, safe to insert", the double-billing
    direction -- verification: unit test

## Files to Read

- `billing/otel/otel_store.py` — the whole module; in particular the `token_usage` schema
  comment establishing that `entrypoint` is transcript-rows-only, and the `dedupe_drops`
  reader methods added by the previous goal as the pattern for a read interface
- `billing/otel/receiver.py` — confirm the receiver's single-connection model so the new
  methods fit it
- `tests/test_otel_store.py` — the existing fixture and assertion style (read-only; task
  05 writes tests)

## Files to Create / Change

- `billing/otel/otel_store.py` — two read methods plus their docstrings

## Constraints

- Must: reuse `self.db`; follow the read-interface shape the `dedupe_drops` readers
  established.
- Must: bind every id as a parameter.
- Must NOT: change any existing line, add a table, add a column, add an index, or write
  anything.
- Must NOT: add a caching layer or memoize results. The membership test is consulted
  during ingest and a stale cached "no OTLP rows" answer double-bills.
- Must NOT: swallow `sqlite3.Error`. Unlike the `dedupe_drops` counter — where a failed
  diagnostic count must never become a billing rejection — a failed membership test must
  propagate, because the caller's only safe fallback is to refuse the insert.
- Must NOT: touch `tests/`, `receiver.py`, or `transcript.py`.

## Verification

- `python -m pytest tests/test_otel_store.py -q` -> passing, unchanged count
- Report the two final signatures verbatim, plus the chunk constant.
