# Task 02: reconcile — aggregation layer

> Revised after Phase 3 cycles 1 and 2. Cycle 1: every day key is pinned to `YYYY-MM-DD` and
> the org-wide truth side must truncate `usage_report`'s raw `starting_at`; the Analytics
> mocking seam is pinned (the old criteria named one that cannot work); all
> `reconcile.py:NN` citations are replaced with symbol references; Σdaily == period
> invariants added; `otel_daily`'s `tagged` rule pinned; `(none)` coalescing generalized.
> Cycle 2: `dedupe_drop_report` gained `counts_outside_measurement` so a real drop count
> is never suppressed by the measurement state (requirement 4), and the seam preamble's
> criterion range was corrected.

## Objective

`billing/reconcile.py` exposes importable, independently unit-testable functions that
return every number the diagnostic output needs: unmapped token types surfaced rather
than discarded, captured tokens broken down by surface, per-day truth and captured
totals for both modes, and the dedupe-drop report with its counting-start epoch. This
task adds **no printing** — task 03 renders what these functions return.

## Dependencies

- 01-store-dedupe-counter (imports its frozen read interface and meta-key constant)

```yaml
# --- task ownership contract ---
writes:
  - billing/reconcile.py
reads:
  - billing/otel/otel_store.py
  - billing/otel/attribute.py
  - billing/store.py
  - billing/analytics_client.py
  - README.md
depends_on:
  - "01-store-dedupe-counter"
owner: implementer
rewrite_semantics: targeted-insertion
eval_depth: full
# full because task 03 consumes every return shape defined here, and because
# reconcile.py is the rollout acceptance test that invoices are built on -- a wrong
# aggregate here is a wrong number on a client invoice.
```

## Requirements (exhaustive — the evaluator verifies every item)

> **Reference convention.** This task cites code by **symbol**, not line number. Tasks
> 02 and 03 both mutate `billing/reconcile.py` in sequence, so any line number written
> here is wrong by the time task 03 runs. Locate code by the names given.

### 0. The day-key contract (read this first — it is the highest-risk item)

- [ ] **Every day key produced by any function in this feature is exactly `YYYY-MM-DD`.**
      Three sources feed the per-day union and they do not natively agree:
      - `otel_daily` — derives days from `substr(ts,1,10)`. Already correct.
      - `analytics_user_daily` — reads `user_cc_usage.day`, which `billing/store.py`'s
        `_day()` helper already truncated on write. Already correct.
      - `analytics_claude_code_daily` — **not** correct by default. `AnalyticsClient`'s
        `usage_report` yields `bucket.get("starting_at")` **verbatim from the API
        payload**, which is an RFC3339 timestamp (e.g. `2026-07-14T00:00:00Z`). The
        codebase's own `_to_dt` helper in `analytics_client.py` truncates with `[:10]`
        for exactly this reason, and `billing/ingest.py` routes every write through
        `store._day()`.
- [ ] `analytics_claude_code_daily` must therefore normalize the yielded value with the
      `[:10]` truncation (reuse `billing.store._day` or restate the same one-liner) before
      using it as a key.
- [ ] **Why this is not cosmetic**: if truth days are `2026-07-14T00:00:00Z` and captured
      days are `2026-07-14`, the union task 03 renders is disjoint, so every day prints
      twice — once with truth and zero captured, once with captured and zero truth. The
      first of those is indistinguishable from the receiver-outage signal this whole
      feature exists to create.

### 1. Unmapped token types (no new query)

- [ ] `otel_totals(store, start, end, emails=None)` keeps its exact current signature and
      its `"captured"` / `"tagged"` keys keep their exact current shape
      (`{CANON bucket: int}`) and meaning. The return is extended **additively**.
- [ ] Add a `"unmapped"` key: `{token_type: tokens}` for every `token_type` present in
      the window that is **not** in `CANON`. Build it by replacing the silent `continue`
      in `otel_totals`' row loop with accumulation — the existing
      `GROUP BY resolved_repo, token_type` query already returns these rows, so do **not**
      add a second query.
- [ ] Token types with no tokens are absent from `"unmapped"`; an empty dict means
      nothing was unmapped.
- [ ] A `NULL`/empty `token_type` is reported under the stable literal key `"(none)"`
      rather than crashing or being dropped. Use `"(none)"` — the same literal as the
      dimension coalescing in requirement 2 — not `"(null)"`, so the output has one
      spelling for "this field was absent".

### 2. Surface breakdown (share of captured)

- [ ] Add `otel_by_surface(store, start, end, emails=None) -> dict` returning:
      ```python
      {
        "usage_source":  {value: tokens, ...},   # 'otlp' | 'transcript'
        "entrypoint":    {value: tokens, ...},   # claude-desktop | ... | '(none)'
        "query_source":  {value: tokens, ...},   # main | subagent | auxiliary | '(none)'
        "captured_total": int,                   # == sum(otel_totals(...)["captured"].values())
      }
      ```
- [ ] Restricted to `CANON` token types only, with the **identical** date window and
      email filter as `otel_totals`, so each dimension sums to `captured_total`. Unmapped
      types are reported by requirement 1 and never mixed in here.
- [ ] **Every dimension coalesces `NULL` and empty-string to the literal `"(none)"`** —
      not just `entrypoint`. `entrypoint` is `NULL` for every OTLP row (the column is
      transcript-only), and `query_source` is nullable in the schema even though both
      current writers coalesce it, so a legacy row can carry `NULL`. Dropping any of them
      makes the dimension stop summing to `captured_total` and the share percentages
      silently stop adding to 100%.
- [ ] This function reads no repo column, so it **may** query `token_usage` directly
      rather than through `resolved_view("token_usage")`, which would pay for
      `attribute.py`'s correlated subqueries for nothing. If you take that option, add a
      comment saying the function must never grow a repo dimension without switching to
      `resolved_view`. `otel_totals` and `otel_daily` do **not** have this latitude —
      they compute `tagged`, which depends on resolved attribution.

### 3. Per-day aggregation, both modes

- [ ] Add `otel_daily(store, start, end, emails=None) -> dict[str, dict]` returning
      `{day: {"captured": {CANON: int}, "tagged": {CANON: int}}}` for each UTC day with
      rows. Same half-open `[start, end)` window and same email filter.
- [ ] `otel_daily`'s `"tagged"` must apply the **identical** rule `otel_totals` uses —
      a row counts as tagged when its resolved repo is truthy and not the literal
      `"unknown"`. Do not reimplement or vary it; factor the predicate out if that helps,
      but the two must not be able to diverge.
- [ ] Must read `resolved_repo` via `resolved_view("token_usage")`, exactly as
      `otel_totals` does — never the raw `repo` column.
- [ ] Add `analytics_claude_code_daily(start, end) -> dict[str, dict]` returning
      `{day: {CANON: int}}` from the Analytics API, using the `(day, row)` pairs
      `usage_report` yields, with the day key normalized per requirement 0. Accumulate —
      do not assume one row per day.
- [ ] **It must return a fully materialized `dict`** — never a generator, never a lazy
      mapping. `run()` wraps the truth call in `try/except AnalyticsError`; a lazy return
      would move the HTTP call (and its `AnalyticsError`) outside that `try` and break
      the existing error path.
- [ ] **`analytics_claude_code_totals(start, end)` keeps its exact signature and return
      shape, and the org-wide path must make exactly ONE `usage_report` pass.**
      `AnalyticsClient` does 31-day windowing and pagination; a second pass doubles calls
      against a rate-limited endpoint. Implement it as: `analytics_claude_code_daily`
      performs the single pass, `analytics_claude_code_totals` becomes a thin public
      wrapper that sums it, and **`run()` calls `analytics_claude_code_daily` and sums it
      locally — `run()` must no longer call `analytics_claude_code_totals` at all.**
      Keep the wrapper: it is public API and may have external callers.
- [ ] `AnalyticsError` must still propagate out of the org-wide truth call so `run()`'s
      existing `except AnalyticsError` branch still prints its "Could not reach Analytics
      API" message. Do not swallow it, and do not move the API call outside that `try`.
- [ ] Add `analytics_user_daily(emails, start, end, analytics_db=None) -> dict[str, dict]`
      returning `{day: {CANON: int}}` from `user_cc_usage`, with the same
      `LOWER(TRIM(email)) IN (...)` matching `analytics_user_totals` uses. Returns a
      possibly-empty dict; the `None`-means-"run ingest first" signal stays with
      `analytics_user_totals` and must not be duplicated here.
- [ ] `analytics_user_totals` keeps its exact current signature and
      `(totals, matched_emails) | None` return shape.
- [ ] Column mapping is identical everywhere and must match `analytics_user_totals`
      exactly: `input` ← `uncached_input`, `output` ← `output`,
      `cacheRead` ← `cache_read`, `cacheCreation` ← `cache_creation_1h +
      cache_creation_5m`. Never `total_tokens`.
- [ ] Days present in truth but absent from captured (and vice versa) must both be
      representable — task 03 prints the union, so a day with truth and zero captured is
      a receiver-outage signal that must not vanish.

### 4. Dedupe-drop report

- [ ] Add `dedupe_drop_report(store, start, end) -> dict` returning:
      ```python
      {
        "epoch": str | None,       # OtelStore.dedupe_epoch() -- UTC ISO8601 timestamp
        "epoch_day": str | None,   # epoch[:10], or None
        "measurement": str,        # "none" | "partial" | "full"
        "counts_outside_measurement": bool,      # see below
        "by_type": {token_type: drops},          # OtelStore.dedupe_drops(...)
        "by_day":  {day: {token_type: drops}},   # OtelStore.dedupe_drops_by_day(...)
      }
      ```
- [ ] `"counts_outside_measurement"` is `True` when `by_type` is non-empty **and**
      `measurement != "full"`. It exists so the inconsistency is a value in the return
      rather than something task 03 has to infer, and so task 03 can qualify a real count
      instead of suppressing it.
- [ ] **This state is reachable by two independent routes, both legitimate** (found in
      Phase 3 cycle 2):
      - *By design*: a drop's `day` comes from the dropped datapoint's own timestamp
        (task 01 §Schema), so a replayed old export counted today records drops dated
        inside a window that entirely precedes the epoch → `measurement == "none"` with a
        non-empty `by_type`.
      - *By interruption*: if the process's first epoch write is rolled back, the epoch
        stays absent while drops from later committed requests persist → `epoch is None`
        with a non-empty `by_type`. Task 01's confirm-then-latch rule makes this
        self-healing on the next insert, but a reconcile run in between still sees it.
- [ ] A non-empty `by_type` must therefore **never** be suppressed on account of
      `measurement`. `dedupe_drop_report` always returns the real counts; task 03 renders
      them with the measurement as a qualifier.
- [ ] `"measurement"` is derived exactly as follows — these cases are mutually exclusive
      and exhaustive, and task 03 renders one message per case:
      - `"none"` when `epoch is None` (counting never ran against this database), **or**
        when `epoch_day >= end` (counting began after the window entirely).
      - `"full"` when `epoch_day < start` (counting covered the whole window).
      - `"partial"` otherwise, i.e. `start <= epoch_day < end` — counting began
        mid-window, so any count is real but understated. Note this deliberately
        includes `epoch_day == start`: the epoch is a timestamp, so counting began
        partway through the first day.
- [ ] String comparison on `YYYY-MM-DD` is correct and intended for these tests.
- [ ] Import the epoch meta-key constant from `billing.otel.otel_store` rather than
      re-declaring the string.
- [ ] Call only task 01's three frozen read methods. Do not query `dedupe_drops`
      directly from `reconcile.py`.

### 5. Shape and placement

- [ ] Every function above is a module-level function in `billing/reconcile.py`,
      importable and callable without `argparse` or `main()`. A future dashboard calls
      these directly.
- [ ] No printing, no `sys.exit`, no `argparse` in any function added by this task.
      `run()` may be *wired* to the new functions, but all rendering changes belong to
      task 03 — if you find yourself formatting a string for display, stop.
- [ ] Follow the file's existing style: plain functions returning dicts keyed by `CANON`;
      leave `ftok`/`pct` untouched.
- [ ] All DB access goes through `OtelStore` / `Store`. No new `sqlite3.connect` call.

## Acceptance Criteria

> **Analytics mocking seam — pinned. Seam B is required by criteria 7, 8, 9, 10, 11 and 12;
> Seam A covers the rest.** `run()`'s org-wide
> truth path constructs its own client inside `analytics_claude_code_daily`, and
> `AnalyticsClient.__init__` raises `AnalyticsError` when no token is in the environment.
> So a test that patches `AnalyticsClient.usage_report` alone never reaches it, and a
> test asserting `AnalyticsError` passes whether or not the code is correct — the
> constructor raises on its own. Every criterion below names which of the two permitted
> seams it uses:
> - **Seam A (function-level)**: `monkeypatch.setattr` on the module-level
>   `billing.reconcile.analytics_claude_code_daily`. Use for output/behavior tests.
> - **Seam B (client-level)**: `monkeypatch.setenv("ANTHROPIC_ANALYTICS_TOKEN",
>   "test-token")` **plus** `monkeypatch.setattr(AnalyticsClient, "usage_report", fake)`.
>   Required whenever the assertion is about the client itself (call counts, raise
>   origin). The `setenv` is mandatory — without it the constructor raises first.
>
> No test may reach the live Analytics API under either seam.

1. `otel_totals(...)["captured"]` and `["tagged"]` match a **pre-change baseline** for a
   seeded fixture — verification: unit test pinning both dicts against expected literals.
   The implementer must capture that baseline by running the aggregation on the fixture
   **before** making changes and paste it in the completion report; a criterion that
   compares post-change code to itself proves nothing.
2. A fixture containing a `token_type` of `cacheCreation5m` reports it under
   `["unmapped"]["cacheCreation5m"]` with the correct total, and that value appears in no
   `["captured"]` bucket — verification: unit test.
3. A fixture with a `NULL` `token_type` reports it under `["unmapped"]["(none)"]` without
   raising — verification: unit test.
4. For any fixture, each of `otel_by_surface(...)`'s three dimension dicts sums to
   `captured_total`, and `captured_total == sum(otel_totals(...)["captured"].values())` —
   verification: unit test asserting all four equalities on a fixture mixing
   `otlp`+`transcript`, at least two `query_source` values, **one row with NULL
   `query_source`**, and at least two `entrypoint` values.
5. OTLP rows (NULL `entrypoint`) appear under `entrypoint["(none)"]`, and the NULL
   `query_source` row under `query_source["(none)"]` — verification: unit test.
6. **Σdaily == period, captured side**: for a fixture spanning three days,
   `sum(otel_daily[day]["captured"][k] for day in ...) == otel_totals(...)["captured"][k]`
   for every `k` in `CANON`, and the same identity for `"tagged"` — verification: unit
   test. This is the invariant that catches a day-key slip, a half-open-window error, and
   a `GROUP BY` that drops NULL-grouped rows.
7. **Σdaily == period, truth side**: the same identity for `analytics_claude_code_daily`
   vs `analytics_claude_code_totals` (Seam B) and for `analytics_user_daily` vs
   `analytics_user_totals` (no Analytics touch — pure SQLite) — verification: two unit
   tests.
8. **Day-key literal**: a fake `usage_report` yielding `starting_at` of
   `"2026-07-14T00:00:00Z"` produces the key `"2026-07-14"` in
   `analytics_claude_code_daily`, and that key compares equal to the key `otel_daily`
   produces for the same day — verification: unit test, Seam B.
9. The org-wide path makes exactly **one** `usage_report` call across a `run()` that needs
   both daily and period figures — verification: unit test with a call-counting fake,
   Seam B, asserting the count is exactly 1.
10. `analytics_claude_code_totals(start, end)` returns the same summed `CANON` dict as
    before the change for a fixed fake payload — verification: unit test, Seam B.
11. An `AnalyticsError` raised **from `usage_report`** still produces the existing "Could
    not reach Analytics API" output and no funnel — verification: unit test, Seam B, with
    a valid fake token set so the raise provably originates in `usage_report` and not in
    the constructor.
12. `analytics_claude_code_daily` returns a `dict` (not a generator or lazy mapping) —
    verification: unit test asserting `isinstance(result, dict)` and that the fake's call
    counter has already advanced on return, proving the pass completed eagerly.
13. `dedupe_drop_report` returns `measurement == "none"` when the epoch is `None` and when
    `epoch_day >= end`; `"full"` when `epoch_day < start`; `"partial"` when
    `epoch_day == start` and when `start < epoch_day < end` — verification: unit test
    covering all five placements.
14. `otel_daily`'s `"tagged"` for a fixture whose raw `repo` is `unknown` but whose
    `session_repo_timeline` resolves it reflects the **resolved** repo — verification:
    unit test. This is the query-time-attribution invariant.
15. No function added by this task prints anything when called against a fixture that has
    rows — verification: unit test asserting `capsys` captured output is empty for a
    direct call to each new aggregation function.
16. `counts_outside_measurement` is `True` with a non-empty `by_type` for both reachable
    routes, and `False` when `measurement == "full"` — verification: three unit tests —
    one seeding drops dated before an epoch that starts after the window (the
    replayed-export route), one seeding drops with the epoch meta key absent entirely
    (the interrupted-write route), and one asserting `False` on a fully-counted window.

## Files to Read

- `billing/reconcile.py` — the whole file before writing anything. Note `CANON`,
  `otel_totals`, `analytics_claude_code_totals`, `analytics_user_totals`, `run`,
  `_print_funnel`, and the `_normalize_emails` helper you must reuse.
- `billing/otel/otel_store.py` — task 01's frozen interface (`dedupe_drops`,
  `dedupe_drops_by_day`, `dedupe_epoch`, the epoch meta-key constant) and the
  `token_usage` schema for exact column names and nullability.
- `billing/otel/attribute.py` — `resolved_view()`'s contract and the
  resolve-at-query-time invariant. **Non-negotiable**: this feature must never persist an
  attribution decision, so a late or corrected `session_repo_timeline` still
  retroactively fixes past bills.
- `billing/store.py` — the `user_cc_usage` schema and the `_day()` truncation helper
  (requirement 0).
- `billing/analytics_client.py` — `usage_report`'s yield shape (note it yields
  `bucket.get("starting_at")` raw), the `_to_dt` helper's own `[:10]` truncation,
  `__init__`'s no-token raise, the 31-day windowing and pagination, and `AnalyticsError`.
- `README.md` — the "Typical OTEL flow" section. Ground truth. The rate card in
  `rating.py` is a placeholder, not real pricing — irrelevant here, do not "fix" it.
- `.claude/skills/test-ladder/SKILL.md` — rungs 1–2 only; never run `python -m pytest -q`.
- `.claude/skills/python-performance-optimization/SKILL.md` — consult only if the per-day
  or per-surface aggregation tempts you toward a per-day query in a loop. Prefer one
  grouped query per shape over N queries.

## Files to Create / Change

- `billing/reconcile.py` — `otel_totals` extended with `"unmapped"`; new
  `otel_by_surface`, `otel_daily`, `analytics_claude_code_daily`, `analytics_user_daily`,
  `dedupe_drop_report`; `analytics_claude_code_totals` restructured into a wrapper over
  the single pass; `run()` rewired to call the daily function.

## Constraints

- Must: keep `otel_totals`, `analytics_claude_code_totals`, and `analytics_user_totals`
  signature- and shape-compatible; extend additively only.
- Must: pin every day key to `YYYY-MM-DD`, including the truncation of `starting_at`.
- Must: use `resolved_view("token_usage")` / `resolved_repo` in `otel_totals` and
  `otel_daily`; `otel_by_surface` may query directly per requirement 2.
- Must: reuse `_normalize_emails`; email matching stays case/whitespace-insensitive via
  `LOWER(TRIM(...))`.
- Must: make exactly one `usage_report` pass on the org-wide path, returning a
  materialized dict, inside the existing `try`/`except AnalyticsError`.
- Must NOT: print, format for display, add CLI flags, or change `_print_funnel`'s
  rendering — that is task 03.
- Must NOT: modify `billing/otel/otel_store.py` (task 01's fence),
  `billing/otel/receiver.py`, any test file, or anything outside the write fence.
- Must NOT: import outside the standard library.
- Must NOT: query the `dedupe_drops` table directly — go through task 01's methods.

## Verification

- Targeted test command: `python -m pytest tests/test_otel_store.py -q`
  (task 04 writes `tests/test_reconcile.py`; this confirms you broke nothing upstream)
- **Required in the completion report**: (a) the pre-change baseline for criterion 1;
  (b) the output of a scratchpad script (session scratchpad directory, never the repo)
  that builds a tmp OTEL store with a mixed otlp+transcript+unmapped+NULL-dimension
  fixture spanning three days and prints the full return value of `otel_totals`,
  `otel_by_surface`, `otel_daily`, and `dedupe_drop_report`, plus an explicit check that
  Σdaily == period for every `CANON` bucket.
