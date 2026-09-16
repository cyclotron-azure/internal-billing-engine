You are the test-writer subagent. Read: .claude/agents/test-writer.md

CURRENT_DATETIME: 2026-09-16T11:45-04:00

## Task

Execute task 04 of `reconcile-coverage-diagnostics`. Spec:
`_goals/reconcile-coverage-diagnostics/04-tests.md`. **Read it in full first** — it already
contains everything unusual about this job, including a "Testability traps in task 01's
shipped implementation (READ BEFORE WRITING)" section and the verified shipped interface.

Tasks 01, 02 and 03 are complete and PASSED. Nothing they built is covered by a committed
test. Every guarantee three evaluators established by hand-run observation is currently
unpinned against regression. That is what you are fixing.

## Write fence

```
tests/test_reconcile.py          (new, whole-file)
tests/test_dedupe_counter.py     (new, whole-file)
tests/COVERAGE_MAP.md            (append a section; H1/preamble generalization permitted)
```

Nothing under `billing/`. Nothing in `tests/conftest.py` or `tests/test_otel_store.py`.

## Non-negotiables (the spec has the detail; these are the ones that bite)

1. **Every `run()` call passes an explicit `db=<tmp_path>`.** Without it `run()` opens the
   real `./data/otel.db` and creates it. Same for `analytics_db=` — never cross the two.
2. **Analytics seams.** Seam A = `monkeypatch.setattr` on module-level
   `billing.reconcile.analytics_claude_code_daily`. Seam B = `monkeypatch.setenv(
   "ANTHROPIC_ANALYTICS_TOKEN", "test-token")` **plus** `monkeypatch.setattr(AnalyticsClient,
   "usage_report", fake)`. The `setenv` is mandatory — the constructor raises without a token,
   so patching `usage_report` alone never reaches it, and an `AnalyticsError` test without the
   token passes for the wrong reason. Say which seam each test uses, in a comment.
3. **The three testability traps in your spec.** A failed counter `UPDATE` leaves a
   `drops = 0` residue row (assert through the public readers, never
   `SELECT COUNT(*) == 0`); `last_seen` is second-granular (monkeypatch
   `billing.otel.otel_store._now`, don't sleep); `dedupe_epoch()` shares the `FROM meta` SQL
   shape the criterion-10 counting test matches on (match the exact insert-path SQL, or don't
   call `dedupe_epoch()` inside the counted window).
4. **Criterion 01.10 is "exactly one" meta lookup, not zero.** Insert, `commit()`, then ten
   more inserts → the first of those ten performs the `SELECT` that closes the latch.
   Asserting zero fails correct code.

## One deviation from the spec, decided by the orchestrator

Task 03's evaluator left three **non-blocking wording/layout minors** in `reconcile.py` that
Phase 5 will fix — including the `DEDUPE DROPS` sentence for `partial` with an empty
`by_type`, and the `__cost__` label width.

So: **do not pin the verbatim text of the `partial`-with-empty-`by_type` sentence, and do not
pin the column offsets of the `__cost__` row.** For those, assert wording-independent
properties instead:

- the four measurement-state qualifiers are **pairwise distinct**;
- states 1-3 with an empty `by_type` contain **no bare drop count**;
- state 4 with an empty `by_type` says something that cannot be confused with an unmeasured
  window;
- a non-empty `by_type` prints its rows under **every** measurement state.

Everything else — section headers, exact comma-formatted integers, specific coverage
percentages, the literal `100.00%` per surface sub-block, the two required `--by-surface`
label strings — **do** pin verbatim. Those are stable.

## Verification

- `python -m pytest tests/test_reconcile.py tests/test_dedupe_counter.py -q` must exit 0.
- `python -m pytest tests/test_otel_store.py -q` must still exit 0 and that file must be
  unmodified (`git diff --stat tests/test_otel_store.py` empty).
- Rungs 1-2 only. **Do NOT run the full `python -m pytest -q`** — that is the orchestrator's
  call at cycle end.

## If a test fails against the implementation

Report it and leave the failing test in place. **Do not** weaken an assertion to make it pass,
and do not edit anything under `billing/` — that is the signal the orchestrator needs.

## Model

requested: claude-sonnet-5 · tier: light

## Output — terse, the user is token-constrained

```
MODEL: <model>
STATUS: completed | blocked

## Files written
[path -> test count]

## Coverage
[Per task (01/02/03): criteria covered, and any criterion left as a GAP with the reason.
Name GAPs explicitly; do not omit them.]

## Traps
[One line each: how you handled the three testability traps and criterion 01.10's off-by-one.]

## Verification
`python -m pytest tests/test_reconcile.py tests/test_dedupe_counter.py -q` -> [result]
`python -m pytest tests/test_otel_store.py -q` -> [result]
`git diff --stat tests/test_otel_store.py` -> [result]

## Failures found in the implementation
[Any test that fails against billing/ code, with the assertion and what it proves. "None" is
valid and expected.]

### Footprint
files_read: <N> (~<C> chars)
```
