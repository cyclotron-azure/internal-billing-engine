You are the evaluator subagent (RESUMED, task 02 re-evaluation after fix cycle 1). Read: .claude/agents/evaluator.md

CURRENT_DATETIME: 2026-10-02T14:30:00-10:00

## Task
Re-evaluate task 02 (`_goals/unknown-parent-child-inheritance/02-tests.md`) after fix cycle 1.
Test-writer report: `_goals/unknown-parent-child-inheritance/spawns/17-report.md`. Verify your Issue 1
(three non-equivalent surviving blocklist mutants) and your recommended items are fixed, and that the
changes introduced no new problem. Re-run; do not trust the report.

## Requirements - delta
- Re-run YOUR OWN mutants on a scratchpad COPY (never mutate the repo; `attribute.py` is UNCOMMITTED
  task-01 work, hash 38d2db20fe79911ed9c9c6e49f714958ee527021; never git checkout/restore/stash/reset):
  bl_mount_k2, bl_gitbash_seg, z1 (`_HOME_PARENTS` dropped), the combined empty-guard mutant, plus
  a few NEW non-equivalent blocklist mutants of your own that probe the same families (e.g. UNC
  top-level `//host/share/seg` rule, `/volumes/<x>/seg` or `/media/<x>/seg` separately, home parents
  `…/users` vs `…/home` each separately, `onedrive*`/`visual studio *` prefix rules, each container
  name in the vocabulary removed one at a time - report any NOT caught and whether equivalent).
- Check the moved case (`/mnt/c/dev` -> containers) and that the new top-level cases use
  non-container names (`Cyclotron`) so the top-level rule is what blocks them; check each new case has a
  real descendant row and a positive control exists for the same shape.
- Check `test_export_build_bills_nate_session_to_the_real_repo` now passes `allowed_domains`
  (environment-independent) and the NULL-repo test asserts `attribution_source`.
- Rungs yourself: `python -m pytest tests/test_attribute_inheritance.py -q` and
  `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_export_unattributed.py tests/test_invoice.py tests/test_reconcile.py -q`. Not the full suite. Run the new file twice.
- Write fence: final tree = ` M billing/otel/attribute.py` (hash above), `?? tests/test_attribute_inheritance.py`,
  `?? _goals/unknown-parent-child-inheritance/`, nothing else.

## Files to Read
- _goals/unknown-parent-child-inheritance/spawns/17-report.md, 16-report.md (your earlier report), 02-tests.md
- tests/test_attribute_inheritance.py, billing/otel/attribute.py
- your scratchpad drivers `ev16_mut.py`, `ev16b_mut.py`, `ev16_probe.py`

## Write fence
none (never edit repo files; scratch copy only)

## Model
requested: claude-opus-5 · tier: frontier · rotation: n/a (resumed)

## Rules
- Do not fix anything. Cite file:line. Separate blocking defects from notes.
- Known non-blocking: AC5 wording in task 01; `/media/<u>/<disk>/proj`; deny-list residuals; the
  z5 NULL-first-row mutant is unreachable by ingest.

## Output
Verdict first: PASS | PASS (with notes) | NEEDS FIXES | REJECT, score out of 5, fixed/not-fixed
line per prior issue, your mutation table (mutant -> red tests / NOT caught), blocking defects, notes,
`### Footprint`.
