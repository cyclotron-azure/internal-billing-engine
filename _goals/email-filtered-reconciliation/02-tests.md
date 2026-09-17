# Task 02: tests

## Objective

`tests/test_reconcile.py` exists and covers the new email-filtering behavior added in
task 01: `analytics_user_totals`, the extended `otel_totals(..., emails=...)`, and
`run(..., emails=...)`'s branching (empty-analytics-side message vs. valid-zero-OTEL
funnel vs. unfiltered/no-`--email` regression).

## Dependencies

- 01-reconcile-email-filter

```yaml
# --- task ownership contract ---
writes:
  - tests/test_reconcile.py
reads:
  - billing/reconcile.py
  - billing/store.py
  - billing/otel/otel_store.py
  - tests/conftest.py
depends_on:
  - "01-reconcile-email-filter"
owner: test-writer
rewrite_semantics: whole-file
eval_depth: light
```

## Requirements (exhaustive — the evaluator verifies every item)

**Parameter names** (matches task 01's resolved contract): `run()`'s `db` argument is
the **OTEL** database path; the analytics database path is the separate `analytics_db`
argument. Never pass an analytics fixture path as `db`, and never pass an OTEL fixture
path as `analytics_db`. **Every single `run()` call in this file — filtered or not —
passes an explicit `db=<tmp_path fixture>`.** `run()` called with no `db=` opens
`OtelStore()`'s real default `./data/otel.db` (verified: creates the file and its
schema on first use) — that would write into the repo's actual data directory during
a test run and must never happen.

- [ ] Create `tests/test_reconcile.py` using `pytest`, following the fixture
      conventions in `tests/conftest.py` (use `tmp_path` for every database — never
      touch `data/otel.db` or `data/analytics.db`, and never rely on execution order
      between tests).
- [ ] Test: `analytics_user_totals` returns `None` when a temp analytics db's
      `user_cc_usage` table has zero rows for the given emails/date range.
- [ ] Test: `analytics_user_totals` returns `(totals, matched_emails)` where `totals`
      is a pure `CANON`-shaped dict (only the four keys, sums matching task 01's exact
      column mapping — `input`←`uncached_input`, `output`←`output`,
      `cacheRead`←`cache_read`, `cacheCreation`←`cache_creation_1h +
      cache_creation_5m`; never `total_tokens`, never a `matched_emails` key mixed
      into `totals`) when `user_cc_usage` has matching rows, and that rows for OTHER
      emails or outside the date range are excluded from the sum.
- [ ] Test: `analytics_user_totals` matches emails case/whitespace-insensitively (seed
      a row with `"a@x.com"`, query with `"A@X.com "`) — `"a@x.com"` appears in the
      returned `matched_emails`; `"b@x.com"` (seeded with zero matching rows) does
      NOT appear in `matched_emails`, so the caller can derive it as unmatched.
- [ ] Test: `otel_totals(store, start, end, emails=[...])` sums `captured`/`tagged`
      only over `token_usage` rows whose (normalized) `user_email` is in the given
      list, excluding rows for other emails in the same date range.
- [ ] Test: `otel_totals(store, start, end)` (no `emails` argument) — seed a fixed,
      known set of `token_usage` rows and assert the returned `captured`/`tagged`
      dicts equal a pinned expected dict. This is the regression check for the
      unfiltered path and does not touch the Analytics API at all (pure SQLite).
- [ ] Test: `run(start, end, emails=[...], analytics_db=<tmp analytics path>,
      db=<tmp otel path>)` against a fixture where the analytics side is empty for
      those emails prints the "run `billing.ingest` first" message and does **not**
      print a `COVERAGE FUNNEL` section (capture via `capsys`).
- [ ] Test: same call shape, but the analytics side has data and the OTEL side has
      zero matching rows — prints a normal funnel with `captured`/`tagged` = 0 and
      does **not** print the "SYNTHETIC" heuristic line (capture via `capsys`).
- [ ] Test: `run(start, end, db=<tmp otel path>)` with no `emails` argument, with
      `billing.reconcile.analytics_claude_code_totals` **monkeypatched** to a fixed
      dict and `db` pointed at a seeded tmp OTEL fixture (so this test makes no live
      network call and never touches the real `./data/otel.db`), asserts the printed
      output contains the specific pre-task-01 section headers (`"BY TOKEN TYPE"`,
      `"COVERAGE FUNNEL"`, `"BILLABLE COVERAGE"`) and the correct computed percentage
      for the patched fixed input — a concrete assertion, not a "looks similar" check.
      Also assert `run(start, end, db=<same path>)` and
      `run(start, end, db=<same path>, emails=None)` produce byte-identical stdout
      (the declared-default equivalence).
- [ ] The only test in this file that touches `billing.reconcile.AnalyticsClient` /
      `analytics_claude_code_totals` is the one immediately above, and it does so via
      `monkeypatch`, never a real HTTP call. Every other test in this file exercises
      only `analytics_user_totals`, `otel_totals`, or the filtered `run()` path, all of
      which touch nothing but local SQLite fixtures — so no test in this file makes a
      live network call, full stop.
- [ ] Tests are runnable via the exact command in Verification below and pass.

## Acceptance Criteria

1. `tests/test_reconcile.py` exists and every requirement above has a corresponding
   test — verification: code review against this checklist.
2. `pytest tests/test_reconcile.py -q` exits 0 — verification: command output.
3. No test in this file touches `data/otel.db`, `data/analytics.db`, or makes a live
   network call — verification: code review (grep for `AnalyticsClient(` and confirm
   every use of `analytics_claude_code_totals`/`AnalyticsClient` in the file is behind
   `monkeypatch`, and that every DB path used is under `tmp_path`).

## Files to Read

- `billing/reconcile.py` — the functions under test, post-task-01.
- `billing/store.py` — `Store` schema for `user_cc_usage`, to seed fixtures correctly.
- `billing/otel/otel_store.py` — `OtelStore` schema for `token_usage`.
- `tests/conftest.py` — existing fixture conventions (`tmp_path` usage, synthetic data
  patterns) to follow; add new fixtures locally in `test_reconcile.py` if nothing
  existing fits rather than editing `conftest.py`.
- `python-testing-patterns` skill — fixtures, mocking, TDD shape.

## Files to Create / Change

- `tests/test_reconcile.py` — new file, all tests for this goal.

## Constraints

- Must: use `tmp_path`-backed SQLite databases for every fixture; never read/write the
  real `data/otel.db` / `data/analytics.db`.
- Must: the one test that exercises the unfiltered `run()` path monkeypatches
  `billing.reconcile.analytics_claude_code_totals` to a fixed dict; every other test
  must not import or invoke `AnalyticsClient`/`analytics_claude_code_totals` at all.
  No test may make a real HTTP call.
- Must NOT: modify `tests/conftest.py` or any file outside `tests/test_reconcile.py`.
- Must NOT: modify `billing/reconcile.py` (that's task 01's write-fence) — if a test
  reveals a bug in task 01's implementation, report it in the test-writer's output
  rather than fixing it directly.

## Verification

- Targeted test command: `pytest tests/test_reconcile.py -q`
