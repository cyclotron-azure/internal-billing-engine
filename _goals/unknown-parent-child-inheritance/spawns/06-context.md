You are the evaluator subagent. Read: .claude/agents/evaluator.md

CURRENT_DATETIME: 2026-10-01T14:10:00-10:00

## Task
Phase 4 evaluation of TASK 01 (cycle 1): `_goals/unknown-parent-child-inheritance/01-attribute-inheritance.md`
(project root: C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine).
Evaluate the implementation in `billing/otel/attribute.py` (uncommitted working-tree change;
`git diff` vs HEAD) against every Requirement and Acceptance Criterion, using
`.claude/skills/task-criteria/SKILL.md`. eval_depth: FULL.
Be skeptical and verify independently - do NOT trust the implementer's evidence; re-run it.

## Requirements
- Verify every bullet of the task's Requirements and every Acceptance Criterion 1-12.
- ACCEPTED DEVIATION on AC11 (decided by the user, recorded here; not a defect): the original
  gate "bare view <= 3.0x" measured 3.52x and the user chose to keep the pure-SQL design and
  replace the gate with an absolute limit on the REAL consumer statements: each must stay
  <= 3.0x the original AND <= 1.0 s per 100,000 datapoints. Measured by the implementer
  (spawns/05-report.md): 2.35-2.78x and a worst case of 0.70 s per 100k (export _scan). Re-measure
  yourself on a synthetic store (scratchpad only) at least for export `_scan` token_usage
  and bill token aggregation; flag it if you cannot reproduce within ~25%.
- Independently re-verify: the 22 BLOCKED / 5 ALLOWED examples (plus `/mnt/c/dev/wealthspire`,
  `/c/dev/wealthspire`, `C:\u\OneDrive - Cyclotron Inc\Code\Dashnoard`), ancestor-only direction,
  Preservation (non-unknown effective row unchanged, including M-at-`C:\dev\mono` with S below),
  same-row repo+cwd, rowid tie-breaks, DirectoryAdded exclusion, session_id 'unknown',
  NULL repo/cwd/event handling, `attribution_source` ordering (desktop-scratch first; inherited
  -> `timeline`), wrapper fall-through, alias safety (alias='x' and a subquery without CTE as in
  reconcile), frozen public interface (names/params/return types), the single-backslash literal
  in the generated SQL, and that path text is never a LIKE/GLOB pattern.
- Check for behavior regressions: compare `resolved_repo`/`attribution_source` outputs of the
  ORIGINAL attribute.py (scratchpad/attribute_orig.py) vs the new one on a randomized store
  where NO timeline row is 'unknown' - they must be identical; and where unknown rows exist but
  no qualifying real row exists - identical too.
- Look hard for any case where an UNRELATED folder inherits (the user's priority is strictly no
  misattribution). Try adversarial paths: trailing dots/spaces, `..` segments, `C:` vs `c:/`,
  mixed UNC forms, `C:\dev\wealthspire` vs `C:\dev\wealthspire-old\x`, unicode case, a real
  row equal to an ancestor's name prefix.
- Check the docstrings describe the new rule (ancestor-only, blocklist, same-folder,
  DirectoryAdded and session-id exclusions, ASCII-only lower(), query-time only).
- Write-fence: only `billing/otel/attribute.py` changed in the repo; hand-off hash
  `56e3526d8aa251c99017a0a783aa718a202189ab`.
- Rung 2 (run it yourself): `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_invoice.py tests/test_reconcile.py tests/test_export.py tests/test_export_unattributed.py tests/test_integration_desktop.py -q`
  Do NOT run the full suite.

## Files to Read
- _goals/unknown-parent-child-inheritance/01-attribute-inheritance.md, goal.md
- _goals/unknown-parent-child-inheritance/spawns/04-report.md and 05-report.md (implementer reports)
- billing/otel/attribute.py (+ `git diff`), tests/test_attribute.py, billing/otel/otel_store.py
- .claude/skills/task-criteria/SKILL.md
- scratchpad (read-only reuse): attribute_orig.py, perf.py, perf.db, ac.py, consumers.py

## Write fence
none (evaluator never edits repo files; scratch work in the scratchpad only; never use
git checkout/restore/stash on any repo path - task 01's work is uncommitted).

## Model
requested: claude-opus-5 · tier: frontier · rotation: n/a (cycle 1)

## Rules
- Do not fix anything. Cite file:line. Separate blocking defects from notes.
- Known, non-blocking note from Phase 3: 01 AC5 wording uses `C:\mono` while task 02 uses
  `C:\dev\mono`; /media/<u>/<disk>/proj is allowed (deny-list residual).
- The implementer observed `resolved_view` rebuilds the inherited-repo lookup (`_i`) up to 8 times
  per export statement and described an unapplied optimisation (compute `resolved_repo` once).
  Judge whether the CURRENT code is acceptable under the amended AC11; do not require the
  optimisation unless the numbers or correctness demand it.

## Output
Verdict first: PASS | PASS (with notes) | NEEDS FIXES | REJECT (tag destructive/security/infra if
applicable), score out of 5, per-AC table (1-12), your re-measured numbers, blocking defects,
notes, and a `### Footprint` block.
