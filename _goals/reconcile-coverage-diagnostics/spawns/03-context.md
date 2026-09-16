You are the evaluator subagent, RESUMED for Phase 3 cycle 3 — the final allowed cycle.
Your cycle-1 report is at `spawns/01-report.md`, your cycle-2 report at
`spawns/02-report.md`, both under `_goals/reconcile-coverage-diagnostics/`.

CURRENT_DATETIME: 2026-09-16T10:16-04:00

## Task

Re-evaluate. Both cycle-2 majors and all three minors were applied. Delta prompt —
verify the fixes and check for new contradictions. Do not re-derive earlier findings.

## Fixes applied

**Major A — the counts-vs-measurement contradiction.** Applied all three of your
suggested edits, taking the *safer* of the two options you offered for (1):

- `01` §"Counting-start epoch" — the in-memory flag now **latches on confirmation, not
  on attempt**: "on each insert attempt: if the flag is unset, `SELECT` the key; if
  present, latch the flag and do nothing else; if absent, write it and leave the flag
  **unset** so the next insert re-checks." A new "Why (a defect found in Phase 3 cycle 2
  — do not 'optimize' this back to latch-on-attempt)" block records your
  `receiver.py:379-387` rollback finding and the docstring's treatment of
  `OperationalError` as an ordinary condition, and states the cost explicitly (one PK
  lookup on a one-row table per insert until committed, zero forever after).
- Criterion 01.10 rewritten to the post-commit form, then corrected for an off-by-one the
  orchestrator caught while preparing this spawn: insert once, `commit()`, then ten more
  inserts on the same instance issue **exactly one** `meta` lookup — the first, which
  finds the key and closes the latch; the remaining nine issue zero. The criterion carries
  a parenthetical warning that asserting zero is unsatisfiable by a correct
  implementation, and `04`'s matching test instruction was aligned. It no longer forbids
  the recovery re-check.
- **New criterion 01.11** pins the recovery: insert, `rollback()`, assert
  `dedupe_epoch()` is `None`, insert again on the *same* instance, `commit()`, assert the
  epoch is now set — written so a latch-on-attempt implementation fails it. Old criteria
  11–14 renumbered to 12–15 (task 01 now has 15).
- `02` requirement 4 — `dedupe_drop_report` gained
  `"counts_outside_measurement": bool`, `True` when `by_type` is non-empty and
  `measurement != "full"`, with both reachable routes documented in-task (replayed export
  dated pre-epoch by design; interrupted first epoch write) and an explicit "a non-empty
  `by_type` must never be suppressed on account of `measurement`".
- **New criterion 02.16** covers both routes plus the `False` case (task 02 now has 16).
- `03` §"Always-printed defect sections" — the `DEDUPE DROPS` bullet is restructured so
  **the measurement state selects the wording and never decides whether counts are
  shown**: counts are always printed when `by_type` is non-empty, under every state; the
  four states are now explicitly a *qualifier*; a new bullet handles
  `counts_outside_measurement is True` with your suggested wording; "print no drop
  *figure*" is now scoped to "only when `by_type` is genuinely empty"; and the `--daily`
  sub-table bullet now says "whenever `by_day` is non-empty, **including** when
  `measurement != "full"`, for the same reason".
- Criterion 03.5 rescoped to the empty-`by_type` case; **new criteria 03.7b and 03.7c**
  pin a non-empty `by_type` printed under each of states 1–3 and the
  `counts_outside_measurement` reconciling sentence; criterion 03.11 now requires two
  tests, one in state 4 and one in state 2.

**Major B — `goal.md` Constraints.** All four stale statements fixed: the `resolved_view`
constraint now reads "`otel_totals` and `otel_daily` must read `resolved_repo` via
`resolved_view()` ... `otel_by_surface` reads no repo column and may query `token_usage`
directly (see task 02 requirement 2)" and additionally records your empirical 1:1
projection finding and that criterion 02.4 remains the guard; the
`billing/reconcile.py:76-86` citation is deleted; "which is by definition rare" is
replaced with the bursty-but-bounded wording; §"Contract first" now says **three** read
helpers and names them.

**Minor C** — `goal.md`'s success criterion restated as task 03's four states verbatim
(counting never ran / began after the window / began during the window so counts are a
lower bound / fully counted, with the zero-vs-non-zero split as a sub-clause of the
last). A second success criterion added: "A non-empty drop count is **never suppressed**
by the measurement state", naming both routes.

**Minor D** — `02`'s seam preamble now reads "Seam B is required by criteria 7, 9, 10, 11
and 12; Seam A covers the rest." `04`'s task-01 bullet now reads "One test per acceptance
criterion **1–14** ... Criterion 15 is a command-output criterion ... not a unit test —
do not write a test for it and do not list it as a GAP." `04`'s task-02/03 reference
updated to (1–16) and (1–16, including 7b and 7c).

**Minor E** — `04`'s ownership block uses the canonical `rewrite_semantics:` key holding
the three `path: mode` entries.

Also applied while in `04`: a stale duplicate criterion-10 bullet that the Major-A edit
would have left contradicting its replacement was removed, and the
"increment adds no statement on the success path" bullet now specifies the comparison be
taken **after** the epoch is committed and the latch has closed, so it isolates the
counter rather than the epoch check.

## Your job this cycle

1. Verify each fix in the task file an implementer reads.
2. Look specifically for new contradictions introduced by the latch-on-confirmation rule:
   - Does "leave the flag unset so the next insert re-checks" interact correctly with the
     `sqlite3.Error` guard around the epoch write, and with criterion 01.14 (a failed
     epoch write must not raise)?
   - Criterion 01.10 had exactly this off-by-one and the orchestrator caught and fixed it
     before this spawn: the flag is only set by a `SELECT` that *found* the key, so the
     insert immediately after the commit performs one lookup and closes the latch. The
     criterion now reads "exactly one across those ten — the first one ... the remaining
     nine issue zero", with a parenthetical warning that asserting zero is unsatisfiable,
     and `04`'s matching test instruction was aligned. **Confirm that reading is right
     and that the corrected count is what a correct implementation produces.**
   - Do criteria 01.10 and 01.11 contradict each other on the same instance?
3. Confirm `03`'s restructured `DEDUPE DROPS` bullet is now internally consistent and
   that criteria 03.5, 03.7, 03.7b, 03.7c and 03.11 partition the state space without
   overlap or gap.
4. Confirm `goal.md` no longer contradicts any task requirement.
5. Re-validate only the criteria that changed or were added: 01.10, 01.11 (and the 12–15
   renumbering), 02.16, 03.5, 03.7b, 03.7c, 03.11.

## Files to Read

- `_goals/reconcile-coverage-diagnostics/goal.md` and all four task files (revised).
- Your own cycle-2 report if you need a finding's exact wording.
- Re-read source only where a fix's correctness depends on it.

## Write fence

None. Evaluating only.

## Model

requested: claude-opus-5 · tier: frontier · rotation: n/a

## Rules

- Do NOT write or edit any file.
- **This is the final allowed cycle.** On exhaustion Phase 3 escalates to the user. Do
  not suppress a real defect to avoid that — but distinguish clearly between something
  that genuinely blocks an implementer and something you would merely prefer. If the only
  remaining findings are of the latter kind, PASS and list them as non-blocking notes.
- Anything you flag must name the task file and section an implementer would read.
- Tag any `destructive`, `security`, or `infra` finding explicitly.
- `files_read: <N> (~<C> chars)` with **C digits only, no separators**.

## Output

```
VERDICT: PASS | NEEDS REVISION | REJECT
MODEL: <the model you are actually running as>

## Summary
[2-4 sentences]

## Fix verification
[One line per major A, B and minors C, D, E: RESOLVED / PARTIAL / NOT RESOLVED /
REGRESSED, with the task file section that settles it.]

## New findings (if any)
### [MAJOR|MINOR] <title>
- **Where**: · **Problem**: · **Consequence**: · **Fix**:

## Non-blocking notes (if PASS)
[Anything you would prefer but that does not block execution.]

## Acceptance-criteria validation
[Only the changed/added criteria.]

### Footprint
files_read: <N> (~<C> chars)
```
