You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-10-01T17:00:00-10:00

## Task
FIX CYCLE 2 of 3 for task 01 (`_goals/unknown-parent-child-inheritance/01-attribute-inheritance.md`),
fresh context. `billing/otel/attribute.py` (uncommitted; hash 903cdd549895384908c91d45c5dba2ac913179f8)
already implements the full feature and the evaluator verified: all functional ACs, the amended
performance gate, view-vs-standalone equivalence on ~22k randomized datapoints, and strictness (no
unrelated folder inherits). Do NOT redesign anything. Fix exactly TWO narrow defects, with minimal
edits. Project root: C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine

## Requirements
1. **Alias collision (`alias='_ar'`).** The correlated inner alias `_ar` used in the `_AS_OF`/
   `_FIRST` templates (attribute.py ~lines 101-111) equals a legal caller alias, so with
   `alias='_ar'` the correlation `_ar.session_id = _ar.session_id` is always true and EVERY row
   misattributes (view and standalone). Make the inner alias collision-proof by DERIVING it from
   the caller's alias (e.g. `f"{alias}__ar"`), which can never equal `alias`. Check the other
   internal aliases the generated SQL uses (`_i`, `_u`, `_m`, `_q`, `_ru`, `_rx`, `_x`, `r`, and
   any new derived one) cannot collide with the caller alias either: the evaluator already
   confirmed these caller aliases work today and they MUST keep working: `r`, `R`, `x1`, `q`,
   `token_usage`, `_i`, `_r`, `_m`, `_x`, `_q`, `_ru`, `_rx`, `_w`. Add `_ar`, the new derived name
   itself (e.g. `t__ar`), and `t` to your checks. Every one must return the same rows as the
   default alias, in BOTH `resolved_view` and the standalone `resolved_repo`/`attribution_source`.
2. **View vs standalone divergence on a NULL-repo as-of row.** Seeded case (evaluator's
   `eval06/newrisk.py` section 1): timeline rows = an unknown row at `C:\dev\proj`, then a row with
   a NULL repo, then a real row R at `C:\dev\proj\x`; the datapoint comes after the NULL-repo row.
   `resolved_view` returns `('unknown','timeline')` (same as the ORIGINAL attribute.py);
   standalone `resolved_repo()` returns `('R','timeline')`. The view falls back to the first row's
   RAW repo; the standalone falls back to the first row's `_i` value. Make the STANDALONE agree
   with the view and the original: its second COALESCE term must be the first row's raw repo
   (e.g. `_FIRST.format(..., col='repo')`), keeping every other behavior. (The docstring at
   ~line 270 says they are identical; keep it true.) This cannot occur through ingest
   (`normalize_remote` never returns NULL), so this is purely a consistency fix.
3. Update docstring/comment text only where needed to stay accurate. No other behavior change.
4. Re-verify (see Output): the full rung-2 command; the evaluator's scripts in
   `scratchpad/eval06/` (`func2.py` must stay 124/124; `regress2.py`, `regress2_noties.py`,
   `alias_chk.py`, `newrisk.py` section 1 must now show view == standalone and no new
   differences vs the original model); the 7-statement perf check must still be <= 1.0 s per
   100k datapoints per statement, each in its own process (`eval06/perf_drive.py`,
   `perf_one.py`) on `eval06/perf_eval.db` and `perf.db` (the edit is tiny; a quick
   confirmation is enough, but report real numbers).

## Files to Read
- _goals/unknown-parent-child-inheritance/01-attribute-inheritance.md
- _goals/unknown-parent-child-inheritance/spawns/08-report.md (the evaluator's findings; issues 1 and 2)
- billing/otel/attribute.py (whole file; it is the working-tree version to edit)
- scratchpad `eval06/` scripts listed above; `ac.py` (AC1-9 ad-hoc evidence)
- CLAUDE.md

## Write fence
ONLY: `billing/otel/attribute.py` (scratchpad for everything else; scratchpad dir:
C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\efecdfb4-de1b-4a6f-9f68-641f5525f749\scratchpad\)

## Model
requested: claude-fable-5-1 · tier: light role, rotated to a different model line · rotation: fix cycle 2

## Rules
- Test ladder rungs 1-2 only. Rung 2 = `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_invoice.py tests/test_reconcile.py tests/test_export.py tests/test_export_unattributed.py tests/test_integration_desktop.py -q`. NEVER the full suite.
- Stdlib only; no new imports; no tests/README/consumer edits; no new table/column/index; no
  registered SQLite functions; path text never used as a LIKE/GLOB pattern.
- NEVER run `git checkout`, `git restore`, `git stash` or `git reset` on any repo path: the work is
  uncommitted. FIRST copy the current `billing/otel/attribute.py` into the scratchpad
  (`attribute_v4_903cdd5.py`). To compare with the original use `scratchpad/attribute_orig.py`.
- Do not commit. Do not touch the VM, deploy/, client-package/.

## Output
Report: the exact edits (before/after snippets), evidence that every listed alias (including
`_ar`, the derived name and `t`) matches the default alias in view AND standalone, the NULL-repo
seeded case result for view and standalone (must be equal and equal to the original's), results of
`func2.py` / `regress2.py` / `regress2_noties.py` / `newrisk.py`, the rung-2 result, the
7-statement per-process perf table (s per 100k) on both stores, `git status --short`, the new
`git hash-object billing/otel/attribute.py`, anything you could not do, and a `### Footprint`
block (`files_read: <N> (~<C> chars)`).
