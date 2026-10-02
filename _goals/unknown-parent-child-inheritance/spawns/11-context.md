You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-10-01T18:30:00-10:00

## Task
FIX CYCLE 3 of 3 (final) for task 01 (`_goals/unknown-parent-child-inheritance/01-attribute-inheritance.md`),
fresh context. `billing/otel/attribute.py` (uncommitted; hash 3a2a637fa5804abe008ebc7aa787a42ff535ebc8)
already implements the full feature and the evaluator verified in cycle 2: every functional AC,
the amended performance gate, view-vs-standalone equivalence on ~35k randomized datapoints,
strictness, and every alias EXCEPT one. Do NOT redesign anything. Fix exactly ONE defect with
minimal edits, but fix its WHOLE CLASS so we stop playing whack-a-mole with aliases.
Project root: C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine

## Requirements
1. **Defect:** `resolved_view(table, alias='_i')` returns two extra columns (`rid`, `v`) because the
   view LEFT JOINs the `_inherit_table()` derived table under the FIXED alias `_i` and selects
   `{alias}.*`, so `_i.*` expands over both `{table} _i` and the derived table `_i`.
   (attribute.py ~lines 296 and 304; `_inherit_table()` docstring ~line 163.) Values are correct;
   the COLUMN LIST breaks the frozen-interface requirement ("added columns unchanged") and alias
   safety.
2. **Fix the whole class.** Every alias the generated SQL introduces OUTSIDE a closed derived-table
   scope must be derived from the caller's alias with a suffix (like the existing
   `{alias}__ar`), so it can never equal the caller's alias or each other: at minimum the join
   alias of the `_inherit_table()` derived table (e.g. `{alias}__i`) in BOTH `resolved_view` and
   the standalone `resolved_repo`/`attribution_source`. Also derived-table-internal aliases
   (`_u`, `_m`, `_q`, `_ru`, `_rx`, `_x`, `r`, ...) are in a closed scope today and the evaluator
   found them safe for every caller alias; do not churn them unless a column-list or
   correlation problem can be shown. Audit the generated SQL once and write down in the report
   the full list of aliases the SQL introduces and why each is collision-proof.
3. **Acceptance for this fix:** the evaluator's `eval06/alias_chk3.py` must report `problems: 0`
   (30 aliases x 2 tables x 3 forms: bare view, `WITH r AS (...)`, standalone; values AND
   `SELECT *` column list == table columns + `resolved_repo` + `attribution_source`), including
   `_i`, `_ar`, `t__i`, `t__ar`, `t__i__ar`, `rid`, `v`. Also extend a check of your own to the
   new derived names (`<alias>__i`, `__ar`, nested).
4. Re-verify nothing else moved: `func2.py` 124/124; `regress2.py`, `regress2_noties.py`,
   `regress4.py`, `regress4_nullheavy.py` (view == standalone 0 diffs, no new vs original
   differences, 0 vs the updated model); `newrisk3.py` sections 1-4; rung 2 (below); and the
   7-statement per-process perf check (absolute limit <= 1.0 s per 100k datapoints; the edit only
   renames an alias, so expect noise-level change; report real numbers for export token and
   bill token at least, on `eval06/perf_eval.db`).

## Files to Read
- _goals/unknown-parent-child-inheritance/01-attribute-inheritance.md
- _goals/unknown-parent-child-inheritance/spawns/10-report.md (evaluator findings; the one issue)
- billing/otel/attribute.py (whole file; the working-tree version to edit)
- scratchpad `eval06/`: alias_chk3.py, func2.py, regress2.py, regress2_noties.py, regress4.py,
  regress4_nullheavy.py, newrisk3.py, perf_drive.py, perf_one.py
- CLAUDE.md

## Write fence
ONLY: `billing/otel/attribute.py` (scratchpad for everything else; scratchpad dir:
C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\efecdfb4-de1b-4a6f-9f68-641f5525f749\scratchpad\)

## Model
requested: claude-opus-5 · tier: frontier (fix cycle 3 pins frontier per the rotation rule) · rotation: fix cycle 3

## Rules
- Test ladder rungs 1-2 only. Rung 2 = `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_invoice.py tests/test_reconcile.py tests/test_export.py tests/test_export_unattributed.py tests/test_integration_desktop.py -q`. NEVER the full suite.
- Stdlib only; no new imports; no tests/README/consumer edits; no new table/column/index; no
  registered SQLite functions; path text never used as a LIKE/GLOB pattern.
- NEVER run `git checkout`, `git restore`, `git stash` or `git reset` on any repo path: the work is
  uncommitted. FIRST copy the current `billing/otel/attribute.py` into the scratchpad
  (`attribute_v5_3a2a637.py`). To compare with the original use `scratchpad/attribute_orig.py`.
- Do not commit. Do not touch the VM, deploy/, client-package/.
- If a clean fix is not possible, STOP and report; do not weaken behavior.

## Output
Report: exact edits (before/after snippets), the alias audit table (every alias the SQL introduces,
scope, why collision-proof), `alias_chk3.py` output (`problems: 0`), results of the other scripts,
rung-2 result, perf numbers (export token, bill token, ideally all 7) on perf_eval.db,
`git status --short`, new `git hash-object billing/otel/attribute.py`, anything you could not do,
and a `### Footprint` block (`files_read: <N> (~<C> chars)`).
