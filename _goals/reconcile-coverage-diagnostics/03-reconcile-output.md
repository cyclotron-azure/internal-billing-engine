# Task 03: reconcile — output rendering + CLI flags

> Revised after Phase 3 cycles 1 and 2. Cycle 1: all `reconcile.py:NN` citations replaced with
> symbol references (one of the old ones protected the wrong code block); the dedupe
> section now renders four states from task 02's `measurement` enum, not three from a
> bool; each `--by-surface` sub-block prints a `TOTAL` reading `100.00%`; `--daily`
> renders the `tagged` figures and the per-day drops that task 01/02 already produce;
> the manual width criterion is now automated; the tautological default-equivalence
> criterion is removed. Cycle 2: the `DEDUPE DROPS` section no longer lets the
> measurement state suppress a real count (the two were contradictory — states 1-2 said
> "print no count" while the `--daily` bullet required the sub-table "when drops
> exist"); the width constant is now specified as the global maximum across all flag
> combinations, with prose required to wrap to it.

## Objective

`python -m billing.reconcile` prints an auditable diagnostic: exact integers beside every
abbreviated figure, unmapped token types and dedupe drops always surfaced, and per-day
and per-surface breakdowns available behind flags. The default invocation still opens
with the same three sections a reader compares against an invoice today.

## Dependencies

- 02-reconcile-aggregation (renders exactly the return shapes that task froze)

```yaml
# --- task ownership contract ---
writes:
  - billing/reconcile.py
reads:
  - billing/otel/otel_store.py
  - billing/store.py
  - README.md
depends_on:
  - "02-reconcile-aggregation"
owner: implementer
rewrite_semantics: targeted-insertion
eval_depth: light
```

## Requirements (exhaustive — the evaluator verifies every item)

> **Reference convention.** Cite code by **symbol**, never line number — task 02 has
> already shifted every line in this file.

### CLI flags

- [ ] Add three `argparse` flags in `main()`: `--by-surface`, `--daily`, `--detail`, all
      `action="store_true"`.
- [ ] `--detail` implies both `--by-surface` and `--daily`.
- [ ] Extend `run()` **additively and keyword-only**:
      `run(start, end, db=None, emails=None, analytics_db=None, *, by_surface=False,
      daily=False)`. Keyword-only so no existing positional call site can bind a flag to
      the wrong parameter. Every existing call shape keeps working unchanged.
- [ ] The existing `--start`, `--end`, `--db`, `--email`, `--analytics-db` flags keep
      their exact current meaning. `--db` is the OTEL database; `--analytics-db` is the
      analytics database. Never overload the two.

### Exact-integer column

- [ ] Every table that prints a token count prints an **exact integer column beside** the
      `ftok()` column — not instead of it, not behind a flag. Format with thousands
      separators (`f"{n:,}"`), right-aligned.
- [ ] Applies to: the `BY TOKEN TYPE` table (truth and captured, including `TOTAL`), the
      `COVERAGE FUNNEL` rows (including both `gap` figures), and every new section below.
- [ ] Introduce a module-level width constant and use it for every `"=" * N` / `"-" * N`
      rule, so rules match the widest table instead of the current hardcoded `70` that
      the new columns overflow. Do not leave a mix of widths.
- [ ] The constant is the **global maximum across every flag combination**, not the widest
      table in the default output. The widest line in the feature is the six-column
      `--daily` row (day + three `ftok`/exact pairs + two `pct`), so size it for that;
      the default invocation then prints wider rules around a narrower table, which is
      correct and expected.
- [ ] Every prose line must wrap to that width too — the `UNMAPPED TOKEN TYPES`
      explanatory text, the `DEDUPE DROPS` qualifiers, the `--by-surface` header, and the
      preserved synthetic-data note. Criterion 16 asserts over **all** output lines, not
      just table rows, so an unwrapped sentence fails it.
- [ ] `ftok()` and `pct()` keep their current behavior and signatures. `pct()` already
      returns `"n/a"` when the denominator is zero — rely on it; do not reimplement
      division anywhere.

### Always-printed defect sections

These print whenever a funnel prints, regardless of `--by-surface` / `--daily` /
`--detail`. A silent failure is what this goal exists to eliminate.

- [ ] `UNMAPPED TOKEN TYPES` — printed only when `otel_totals(...)["unmapped"]` is
      non-empty. One row per token type with `ftok()` + exact integer. Must state plainly
      that these tokens are **excluded** from the captured figures above and therefore
      **understate** coverage by that amount, and name a token-type vocabulary change as
      the likely cause. A reader who does not know the codebase must be able to act on it.
- [ ] Use the file's existing `!!` prefix convention for this section — the same marker
      `run()` already uses for its "No analytics rows" and "Could not reach Analytics API"
      messages.
- [ ] `DEDUPE DROPS` — driven by `dedupe_drop_report(...)`. **The measurement state
      selects the wording; it never decides whether counts are shown.** Two independent
      things are being reported and they must not be conflated:
      - **The counts.** If `by_type` is non-empty, its rows are **always** printed — one
        row per token type with `ftok()` + exact integer — under *every* measurement
        state. A real recorded duplicate count is never suppressed.
      - **The measurement qualifier**, one of four mutually exclusive states:
        1. `measurement == "none"` and `epoch is None` → counting has never run against
           this database.
        2. `measurement == "none"` and `epoch` is set → counting began **after** this
           window (`{epoch}`).
        3. `measurement == "partial"` → counting began **during** this window, at
           `{epoch}`, so the counts are a **lower bound**.
        4. `measurement == "full"` → the window is fully counted, epoch shown.
- [ ] `counts_outside_measurement is True` (task 02 gives you this flag) means the two
      disagree: real counts exist in a window the epoch says was not counted. Say so
      plainly rather than printing one and hiding the other — e.g. "counting began after
      this window, yet N drops dated inside it were recorded (a replayed export, or an
      interrupted first write)". **This state is legitimate and reachable** by two routes
      task 02 documents; it is not an error to swallow.
- [ ] Print no drop *figure* only when `by_type` is genuinely empty. In states 1–3 with an
      empty `by_type`, print the qualifier alone and no `0`. In state 4 with an empty
      `by_type`, state explicitly that there were **no duplicate datapoints in this
      window** — a measured zero and an unmeasured window must be textually unmistakable
      for one another.
- [ ] When `--daily` is also passed and `by_day` is non-empty, `DEDUPE DROPS`
      additionally renders `dedupe_drop_report(...)["by_day"]` as a per-day sub-table —
      again under **every** measurement state, for the same reason. This is the only
      consumer of that frozen interface; if you do not render it, task 01 froze an
      interface for nothing.

### `--daily`

- [ ] One row per UTC day over the **union** of days present in truth and in captured,
      sorted ascending. A day with truth but zero captured must appear with its coverage
      percentage — that is the receiver-outage signal and it must not vanish. A day with
      captured but zero truth must also appear.
- [ ] Columns: day, truth (`ftok` + exact), captured (`ftok` + exact), coverage `pct`,
      tagged (`ftok` + exact), billable `pct` (tagged / truth). The `tagged` figures come
      from `otel_daily`'s `"tagged"`, which task 02 produces — render them; per-day
      billable coverage is the actionable number.
- [ ] Works in **both** modes: org-wide via `analytics_claude_code_daily`, `--email` via
      `analytics_user_daily`.
- [ ] Every day key is `YYYY-MM-DD` (task 02 requirement 0 guarantees this). Do not
      reformat, re-parse, or re-derive day keys here.
- [ ] Days in the window with no rows on either side are omitted rather than printed as
      zero rows — an absent day and a zero day are different facts and only the latter is
      evidence.

### `--by-surface`

- [ ] The header must state it is a **share of captured, NOT coverage**, and say why in
      one short line: truth has no surface dimension. This label is a hard requirement —
      an unlabeled percentage here reads as coverage and would be actively misleading on
      an invoice review.
- [ ] Three sub-blocks in this order: `usage_source`, `entrypoint`, `query_source`. Each
      row: value, `ftok()`, exact integer, share of `captured_total` via `pct()`.
- [ ] Rows sorted by tokens descending within each sub-block.
- [ ] **Each sub-block ends with its own `TOTAL` row**: the summed tokens (`ftok` + exact)
      and `pct(block_total, captured_total)`. That percentage must read `100.00%`. This
      makes a dimension that silently stops summing to the captured total visible in the
      output itself rather than only in a fixture test — a unit test cannot catch a data
      shape the fixture does not contain.
- [ ] The `"(none)"` rows (OTLP rows' NULL `entrypoint`, any NULL `query_source`) are
      printed like any other row, never suppressed.

### Carried-over cleanups from task 02's evaluation (required, small)

Task 02 shipped and PASSED with two non-blocking findings in `billing/reconcile.py`. You
own that file, so fix both here rather than leaving them for a separate cycle.

- [ ] **Drop the unused `DEDUPE_EPOCH_META_KEY` import.** It is imported at the top of
      `reconcile.py` but referenced only in a docstring. `OtelStore.dedupe_epoch()`
      resolves the meta key internally, so `reconcile.py` never handles the string and
      there is no executable use available. The task-02 evaluator ruled: drop the import,
      keep the prose reference. Do not invent a use for it to justify keeping it.
- [ ] **Fix the falsy-epoch guard in `dedupe_drop_report`.** It currently reads
      `epoch_day = epoch[:10] if epoch else None` and then guards with
      `if epoch is None or epoch_day >= end`. For `epoch == ""` the first line yields
      `epoch_day = None` while the guard's `epoch is None` is `False`, so it evaluates
      `None >= end` and raises `TypeError`. Change the guard to
      `if not epoch or epoch_day >= end` so the two lines agree on what falsy means.
      Unreachable today (`_ensure_dedupe_epoch` only ever writes `_now()`), so this is
      defensive consistency, not a live bug — do not change `measurement`'s semantics for
      any reachable input while fixing it.

### What task 02 actually returns (build against this, not the prose)

Verified by the task-02 evaluator by calling each function, with no drift from its report:

- `otel_totals(...)` → `{"captured": {CANON: int}, "tagged": {CANON: int}, "unmapped": {token_type: int}}`.
  `captured`/`tagged` **always** carry all four CANON keys including zeros; `unmapped`
  omits zero-token types and is `{}` when nothing was unmapped.
- `otel_by_surface(...)` → the three dimension dicts plus `captured_total`. NULL **and
  empty-string** values both coalesce to `"(none)"`.
- `otel_daily(...)` → `{"YYYY-MM-DD": {"captured": {CANON: int}, "tagged": {CANON: int}}}`.
  Only days with rows appear; both inner dicts always carry all four CANON keys.
- `analytics_claude_code_daily(start, end)` → `{"YYYY-MM-DD": {CANON: int}}`, materialized.
- `analytics_user_daily(...)` → `{"YYYY-MM-DD": {CANON: int}}`, possibly `{}`, never `None`.
- `dedupe_drop_report(...)` → exactly six keys: `epoch`, `epoch_day`, `measurement`,
  `counts_outside_measurement`, `by_type`, `by_day`.

- [ ] **Do not render `"(none)"` as though it can only mean "the field was absent".** In
      `otel_totals["unmapped"]`, a NULL `token_type`, an empty-string `token_type`, and a
      literal `token_type` of `"(none)"` all collapse into the one `"(none)"` key (the
      evaluator observed 3 + 5 + 7 = 15). That collapse is what task 02 requirement 1
      specifies by choosing a stable literal, so it is intended — but your wording must
      not assert a cause the key cannot distinguish.
- [ ] For the `--email` period totals you may sum `analytics_user_daily`'s output locally
      rather than calling `analytics_user_totals` a second time, exactly as `run()` now
      does on the org path. The two functions each open and close their own `Store`, so
      calling both means two sequential opens of `analytics.db`. Keep the `analytics_user_totals`
      call where the `None`-means-"run ingest first" signal is needed — that sentinel lives
      only there.

### Preserved behavior

- [ ] With no new flags, the output still contains the `BY TOKEN TYPE` table, the
      `COVERAGE FUNNEL` section, and the `BILLABLE COVERAGE` line, with the same funnel
      arithmetic and the same `pct` values as today.
- [ ] The `--email` banner line (`emails=...`) and the `!! no analytics rows matched:`
      line are unchanged.
- [ ] **The no-analytics-rows early-return path stays exactly as it is today** — the
      branch in `run()` guarded by `if result is None:`, which prints
      `!! No analytics rows for ...`, prints the `billing.ingest` hint, closes the store,
      and returns without a funnel. Do **not** add the new sections to that path: it is an
      error path telling the user data was never pulled, and a funnel-adjacent section
      there would imply a measurement happened. (Do not confuse this with the *success*
      branch immediately after it, which unpacks `truth, matched_emails` and calls
      `_print_funnel` — that one you **do** modify.)
- [ ] The `except AnalyticsError` branch in `run()` stays unchanged.
- [ ] The synthetic-data note and its `suppress_synthetic_note` / `C < A * 0.99`
      condition stay unchanged.
- [ ] `store.close()` is still called on every return path, including the new ones.

## Acceptance Criteria

> **18 criteria under 16 numbers**: 7b and 7c are additional items, not sub-clauses of 7.
> Any criterion count or COVERAGE_MAP sub-table must show 18 rows.
>
> Analytics is mocked at **Seam A** (module-level `monkeypatch.setattr` on
> `billing.reconcile.analytics_claude_code_daily`) for every criterion here. Patching
> `AnalyticsClient.usage_report` alone does not work — see task 02's seam note.

1. `run(start, end, db=<seeded tmp>)` with the truth function patched prints
   `BY TOKEN TYPE`, `COVERAGE FUNNEL`, and `BILLABLE COVERAGE`, and prints neither a
   surface nor a daily section — verification: unit test on `capsys`.
2. For a known fixture, the default output's `BY TOKEN TYPE` rows and `TOTAL` row match
   **pinned expected lines** exactly (whitespace included), and the `TOTAL` row's exact
   integers equal the sum of the per-type exact integers — verification: unit test
   comparing against literal expected strings, not a substring search.
3. A fixture containing an unmapped token type prints an `UNMAPPED TOKEN TYPES` section
   with that type and its exact count, in the **default** invocation with no flags —
   verification: unit test on `capsys`.
4. A fixture with no unmapped token types prints no `UNMAPPED TOKEN TYPES` section —
   verification: unit test asserting absence.
5. Each of the four `DEDUPE DROPS` measurement qualifiers produces distinct output, and
   with an **empty** `by_type` states 1–3 contain no bare drop count — verification: four
   unit tests plus one asserting all four captured outputs are pairwise different.
6. State 3 (`partial`) **with a non-empty `by_type`** names the epoch instant and says the
   counts are a lower bound. With an **empty** `by_type` it must instead say that nothing
   was recorded from that instant onward and anything earlier was never counted — a
   "lower bound" on an empty set is meaningless. Disambiguated after the Phase 4/6 cleanup
   found a test asserting `LOWER BOUND` against the empty fixture —
   verification: unit test.
7. State 4 with zero drops says there were no duplicate datapoints in the window;
   state 4 with seeded drops prints each token type's exact count — verification: two
   unit tests.
7b. **A non-empty `by_type` is printed under each of states 1, 2 and 3**, together with
   that state's qualifier — verification: three unit tests, each seeding real drops and
   asserting both the exact count and the qualifier wording appear. These are the
   criteria that pin the cycle-2 fix; an implementation that suppresses counts outside
   `"full"` fails all three.
7c. When `counts_outside_measurement` is `True`, the output says the counts and the
   measurement state disagree and names both — verification: unit test asserting the
   count, the epoch, and the reconciling sentence are all present.
8. `--daily` prints a row for a day that has truth but zero captured, with a coverage
   percentage — verification: unit test with a truth fixture covering three days and a
   captured fixture covering two.
9. `--daily` rows sum to the period `TOTAL` printed in the same output, for both the
   truth and the captured column — verification: unit test parsing the exact-integer
   columns out of the captured output and summing. This is the rendered counterpart of
   task 02's Σdaily invariant.
10. `--daily` works in `--email` mode against `user_cc_usage`, and renders the `tagged`
    and billable columns — verification: unit test.
11. `--daily` additionally renders the per-day dedupe sub-table whenever `by_day` is
    non-empty, **including** when `measurement != "full"` — verification: two unit
    tests, one in state 4 and one in state 2.
12. `--by-surface` output contains the literal strings "share of captured" and
    "NOT coverage", lists all three dimensions, and includes an `(none)` entrypoint row
    for an OTLP-containing fixture — verification: unit test.
13. Each `--by-surface` sub-block prints a `TOTAL` row whose share reads exactly
    `100.00%` — verification: unit test asserting three occurrences of `100.00%` in the
    surface section.
14. `--detail` produces output containing both the daily and the surface section headers
    — verification: unit test.
15. The no-analytics-rows path and the `except AnalyticsError` path produce the same
    output as before this task — verification: unit tests on `capsys` pinning both
    messages and asserting no `COVERAGE FUNNEL` is printed.
16. All rule lines (`===` / `---`) in a full `--detail` run have **equal length**, and no
    output line exceeds that length — verification: unit test that captures the output,
    collects every line consisting solely of `=` or `-`, asserts they are all the same
    length, and asserts `max(len(line) for line in all_lines)` is not greater.

## Files to Read

- `billing/reconcile.py` — the whole file, post-task-02, especially `run`,
  `_print_funnel`, and task 02's new aggregation functions and their exact return shapes.
- `billing/otel/otel_store.py` — task 01's `dedupe_epoch` semantics (an ISO8601 timestamp
  written by the insert path), for the wording of the unmeasured and partial cases.
- `README.md` — the `reconcile.py` bullet and the pilot "Coverage" bullet, which describe
  this output. Ground truth; Phase 6 syncs it, so do **not** edit it here, but read it so
  your section names and wording do not contradict it.
- `.claude/skills/test-ladder/SKILL.md` — rungs 1–2 only; never run `python -m pytest -q`.

## Files to Create / Change

- `billing/reconcile.py` — `main()` gains three flags; `run()` gains two keyword-only
  parameters; `_print_funnel` (or new sibling print helpers) gains the exact-integer
  column and the four new sections.

## Constraints

- Must: keep the default output's three existing sections and their arithmetic intact.
- Must: label the surface breakdown as share-of-captured and never as coverage, and print
  a `100.00%` `TOTAL` per sub-block.
- Must: print the unmapped and dedupe sections regardless of flags, whenever a funnel
  prints.
- Must: keep all rendering in print helpers; do not recompute any aggregate here —
  consume task 02's functions. If a number you need is not in their return value, report
  that rather than querying the database from a print helper.
- Must NOT: add `--json`, an exit-code threshold, or any machine-readable mode (out of
  scope by explicit decision).
- Must NOT: modify `billing/otel/otel_store.py`, `billing/otel/receiver.py`, `README.md`,
  any test file, or anything outside the write fence.
- Must NOT: import outside the standard library.
- Must NOT: change `ftok()` or `pct()` behavior.

## Verification

- Targeted test command: `python -m pytest tests/test_otel_store.py -q`
- **Required evidence, pasted verbatim in the completion report** (task 04 has not
  written the reconcile tests yet, and this output is the deliverable): build a tmp
  fixture under the session scratchpad directory containing OTLP + transcript rows, at
  least one unmapped token type, at least one dedupe drop, a NULL `entrypoint` and a NULL
  `query_source`, and three distinct days, then capture and paste the full stdout of:
  1. default (no flags)
  2. `--daily`
  3. `--by-surface`
  4. `--detail`
  5. one run per `DEDUPE DROPS` state 1, 2 and 3 (vary the epoch meta value)
  Never write fixtures into the repo's `data/` directory.
