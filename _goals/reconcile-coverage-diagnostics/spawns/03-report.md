VERDICT: PASS
MODEL: claude-opus-5 (harness-reported: Opus 5 / `claude-opus-5`)

## Summary

Both cycle-2 majors are resolved in the task files an implementer actually reads, and the latch-on-confirmation rule is correct — I traced it against `receiver.py`'s rollback path and it is self-healing under exactly the failure I flagged. Your off-by-one correction to criterion 01.10 is right: "exactly one" is what a correct implementation produces, and asserting zero would indeed be unsatisfiable. Task 03's `DEDUPE DROPS` restructure now cleanly separates counts from qualifier and its criteria partition all eight state cells with no gap; `goal.md` no longer contradicts any task requirement. Two minor wording residues remain — a seam list that omits one criterion, and one stale "once-per-process" phrase — neither of which can mislead an implementer, because in both cases the authoritative instruction sits in the same file and a criterion mechanically fails the wrong reading. Baseline re-verified: no source drift since cycle 1 (`git status --porcelain -- billing/ tests/` empty) and `python -m pytest tests/test_otel_store.py -q` → `27 passed in 2.32s`.

## Fix verification

**Major A — counts-vs-measurement contradiction**: RESOLVED, and the safer option was the right pick. Settled by `01` §"Counting-start epoch" bullets 4–5 (latch-on-confirmation plus the "Why (a defect found in Phase 3 cycle 2 — do not 'optimize' this back to latch-on-attempt)" block, which records the `rollback()` mechanism and the cost honestly), criteria 01.10 and the new 01.11; `02` requirement 4's `counts_outside_measurement` with both routes documented and the explicit "a non-empty `by_type` must therefore **never** be suppressed"; new criterion 02.16; `03` §"Always-printed defect sections" — the `DEDUPE DROPS` bullet now leads with "**The measurement state selects the wording; it never decides whether counts are shown**", splits the two things being reported, scopes "print no drop *figure*" to "only when `by_type` is genuinely empty", and extends the `--daily` sub-table "under **every** measurement state"; criteria 03.5 (rescoped), 03.7b, 03.7c, 03.11 (two tests, states 4 and 2).

**Major B — `goal.md` Constraints**: RESOLVED. All four stale statements corrected in `goal.md` §Constraints: the attribution bullet now names `otel_totals` and `otel_daily` only and grants `otel_by_surface` the direct query with the comment requirement, the `billing/reconcile.py:76-86` citation is gone, the counter bullet carries the bursty-not-rare wording, and §"Contract first" says **three** read helpers and names them. Zero `.py:NN` citations remain in any of the four task files (verified by grep); the two left in `goal.md` are `receiver.py:167`/`:358`, both of which I verified accurate in cycle 1.

**Minor C — four-state success criterion**: RESOLVED. `goal.md` §Success Criteria now enumerates task 03's four states verbatim with the zero/non-zero split as a sub-clause of state 4, plus the added "A non-empty drop count is **never suppressed** by the measurement state" criterion naming both routes.

**Minor D — dangling cross-references**: PARTIAL. `04` §"`tests/test_dedupe_counter.py`" is fixed correctly ("One test per acceptance criterion **1–14** ... Criterion 15 is a command-output criterion ... do not write a test for it and do not list it as a GAP"), the criterion-10/11 bullet is aligned including the "Do not assert zero" warning, the stale duplicate bullet is gone, the success-path comparison is now scoped to "after the epoch is committed and the latch has closed", and the task-02/03 references read (1–16) and (1–16, including 7b and 7c). The seam preamble in `02` still omits one criterion — see finding F.

**Minor E — canonical `rewrite_semantics` key**: RESOLVED. `04`'s ownership block now uses `rewrite_semantics:` holding the three `path: mode` entries with a `# per owned path` comment.

**Coordinator's question — is criterion 01.10's "exactly one" correct?** Yes, confirmed by tracing the mandated rule. Insert #1: flag unset → `SELECT` (key absent) → write, flag left unset. `commit()`. Insert #2 (first of the ten): flag unset → `SELECT` → key **found** → latch. That is the one lookup. Inserts #3–#11: flag set → zero lookups. Total across the ten = 1. Asserting zero would require the flag to have latched on the pre-commit attempt, which is precisely the behavior criterion 01.11 exists to fail, so the parenthetical warning is accurate. The count is also cleanly attributable: `_migrate()` no longer touches `meta`, `__init__` only runs `executescript(SCHEMA)`, and the increment statements hit `dedupe_drops` — so the only `SELECT ... FROM meta` in that window is the epoch check.

**Coordinator's question — 01.10 vs 01.11 contradiction?** None. They exercise disjoint sequences: 01.10 is the post-commit steady state (latch closes, stays closed), 01.11 is the pre-commit rollback path (flag never latched, so the next insert retries). One implementation satisfies both. The `sqlite3.Error` guard composes correctly with the rule as well — a swallowed failure of either the `SELECT` or the epoch write leaves the flag unset, so the next insert retries, which is the recovery 01.11 pins; and criterion 01.14 (a failed epoch write must not raise) is satisfied independently of the flag state.

**Coordinator's question — does `03` partition the state space?** Yes, over all eight cells of (qualifier state 1–4) × (`by_type` empty / non-empty): criterion 5 covers the four empty cells, criterion 7 covers state 4 empty and non-empty, criterion 7b covers states 1–3 non-empty, criterion 7c adds the reconciling-sentence assertion on the `counts_outside_measurement` subset, criterion 6 pins state 3's wording, criterion 11 pins the sub-table in states 4 and 2. The only overlap is (state 4, empty) between criteria 5 and 7, which is deliberate and benign — 5 asserts distinctness, 7 asserts the specific "no duplicate datapoints" wording.

**Also verified as applied, though not on your list**: the width-constant point from my cycle-2 acceptance-criteria commentary is now in `03` §"Exact-integer column" bullets 3–5 — the constant is specified as "the **global maximum across every flag combination**" with the six-column `--daily` row named as the widest line, and "Every prose line must wrap to that width too", which is what makes criterion 03.16 satisfiable rather than accidentally failing on an unwrapped sentence.

## New findings

### [MINOR] F. `02`'s seam preamble omits criterion 8 from the Seam B list
- **Where**: `02-reconcile-aggregation.md` §Acceptance Criteria, preamble line: "Seam B is required by criteria 7, 9, 10, 11 and 12; Seam A covers the rest."
- **Problem**: Criterion 02.8 (the day-key literal) ends "verification: unit test, **Seam B**" and requires a fake `usage_report` yielding `starting_at`, which is only reachable through Seam B. The preamble's enumeration skips it, so "Seam A covers the rest" is false for criterion 8. This is the same over-narrow-enumeration shape as cycle-2 finding D, with a different omission.
- **Consequence**: Non-blocking. A test-writer reading criterion 8 gets "Seam B" from the criterion itself, and `04` §"`tests/test_reconcile.py`" independently states "Criterion 02.8 pins the day-key literal ... Seam B." Both authoritative statements are correct; only the summary line is incomplete. Worst case is a moment's confusion, not a wrong test.
- **Fix**: one character — "criteria 7, **8**, 9, 10, 11 and 12".

### [MINOR] G. `01` §Increment still says the epoch check is "at-most-once-per-process"
- **Where**: `01-store-dedupe-counter.md` §Increment, bullet 4: "An inserting call must issue no extra statement beyond the at-most-once-per-process epoch check."
- **Problem**: Under latch-on-confirmation the epoch check is once per process only *after* the epoch is committed; before that it is one primary-key lookup per insert, exactly as §"Counting-start epoch" bullet 5 states ("costs one primary-key lookup on a one-row table per insert until the epoch is committed, and exactly zero forever after"). The two bullets describe the same mechanism with incompatible cost language.
- **Consequence**: Non-blocking. An implementer optimizing toward the literal "at most once per process" would land on latch-on-attempt — but that reading is blocked three ways in the same file: the explicit rule four bullets earlier, the "do not 'optimize' this back to latch-on-attempt" block, and criterion 01.11, which a latch-on-attempt implementation fails deterministically. `04`'s success-path bullet already handles the measurement correctly ("taken **after** the epoch is committed and the latch has closed").
- **Fix**: replace with "beyond the epoch check, which is one primary-key lookup per insert until the epoch is committed and zero thereafter".

## Non-blocking notes

- **`03` carries 18 criteria under 16 numbers.** The 7b/7c letter suffixes were the right call — renumbering 8–16 would have dangled `04`'s references — but a counted audit finds 18 items where the plan says 16. Worth one line in `03`'s Acceptance Criteria preamble ("16 numbered criteria; 7b and 7c are additional, so 18 in total") so the COVERAGE_MAP sub-table and any later criterion-count check agree.
- **Criterion 02.16's `False` case tests one of two routes.** `counts_outside_measurement` is `False` both when `measurement == "full"` (tested) and when `by_type` is empty under any state (not tested). The latter is the ordinary default and is covered indirectly by criteria 02.13 and 03.5, so this is completeness, not a gap.
- **A persistently failing epoch write costs two swallowed statements per insert indefinitely**, since the flag can never latch. That requires a broken `meta` table, and the alternative (latching after N failures) is complexity for a case that means the database is already unusable. Accepting it is correct; I note it only because it is the honest completion of "does the guard interact correctly" — it does, and the pathological case is bounded and strictly preferable to the correctness bug it replaced.
- **`goal.md` §Problem Statement still cites `reconcile.py:91`.** Verified accurate enough in cycle 1 (line 91 is the `if tt is None:` guard, 92 the `continue`), it is narrative rather than an instruction, and every task file now uses symbol references. Left as-is deliberately.

## Acceptance-criteria validation

Only the changed or added criteria, all of which are verifiable by their named method:

- **01.10** (rewritten): correct and satisfiable — "exactly one" matches the mandated rule as traced above, the count is attributable solely to the epoch check, and the parenthetical warning against asserting zero is accurate. The method (wrapping `db.execute` and counting `SELECT ... FROM meta`) does not require guessing at internals.
- **01.11** (new): the strongest criterion added this cycle — insert / `rollback()` / assert `None` / insert / `commit()` / assert set is exactly the sequence a latch-on-attempt implementation fails, so it pins the fix mechanically rather than by instruction. Verifiable; no conflict with 01.8, whose epoch read happens on the same connection before any rollback, and whose reopen commits via `OtelStore.close()`.
- **01.12–01.15** (renumbered from 11–14): content unchanged, all four references in `04` (criteria 7, 8–9, 10/11, 13–14, 15) land on the right items post-renumbering. No dangling reference remains in `04`.
- **02.16** (new): three named tests, each with a concrete seeding recipe that distinguishes the two `True` routes. Verifiable. See the note above on the untested second `False` route.
- **03.5** (rescoped): now correctly conditions the no-bare-count assertion on an empty `by_type`, which is what makes it compatible with 7b. Verifiable.
- **03.7b** (new): three unit tests asserting the exact count *and* the qualifier wording appear together — the right shape, since asserting only the count would pass an implementation that dropped the qualifier.
- **03.7c** (new): asserts count, epoch and reconciling sentence all present. Verifiable; the requirement supplies example wording so the test can pin a string without the test-writer inventing one.
- **03.11** (expanded): two tests, states 4 and 2, which is the minimum that proves the sub-table is not gated on `measurement == "full"`. Verifiable.

No auto-fail trigger fired across any cycle: stdlib-only stated in all four tasks, single-host/single-connection SQLite restated in `01` with WAL/pool/threading/`check_same_thread` named, query-time attribution preserved and now correctly scoped, no secret handling, no receiver modification, no persisted invoice mutation, no test path reaching a live external service under either pinned seam, and no `request_id` column. Write fences remain disjoint-or-ordered with `billing/reconcile.py` serialized 02 → 03. A fresh executor can run task 01 from its file alone.

### Footprint
files_read: 6 (~46000 chars)
commands_run: 6
