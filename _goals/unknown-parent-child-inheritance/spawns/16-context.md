You are the evaluator subagent. Read: .claude/agents/evaluator.md

CURRENT_DATETIME: 2026-10-02T12:00:00-10:00

## Task
Phase 4 evaluation of TASK 02 (cycle 1): `_goals/unknown-parent-child-inheritance/02-tests.md`
(project root: C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine). Evaluate
`tests/test_attribute_inheritance.py` (new, untracked) against every Requirement and Acceptance
Criterion, using `.claude/skills/task-criteria/SKILL.md`. eval_depth: LIGHT (requirements walk +
targeted tests + write-fence check, ending in a real verdict) - but the tests guard a strict
no-misattribution billing rule, so be skeptical about assertions that cannot fail.
Test-writer report: `_goals/unknown-parent-child-inheritance/spawns/15-report.md`.

## Requirements
- Walk every bullet of 02-tests.md's Requirements. NOTE the as-built deviations that the orchestrator
  directed in the test-writer's context package (`spawns/15-context.md`; they are NOT defects):
  ancestor-only direction (a real parent with an unknown child stays unknown); the anchor blocklist
  (project-level folders only); repo-based final tie-break (not rowid); quoted/bare alias column-list
  tests; view==standalone; cardinality; no-behavior-change-without-unknown-rows; mutants (g) direction
  alt-form and (h) `_fmt` raw alias were added.
- **Do the mutation check yourself, SAFELY.** `billing/otel/attribute.py` (task 01, hash
  38d2db20fe79911ed9c9c6e49f714958ee527021) is UNCOMMITTED. NEVER edit it in place and NEVER use git
  checkout/restore/stash/reset on any repo path. Instead COPY the working tree (excluding `.git`,
  `_goals`, caches) to a directory in the scratchpad, mutate `billing/otel/attribute.py` THERE, and run the
  tests there (`python -m pytest tests/test_attribute_inheritance.py -q` from that copy; make sure the
  copy's `billing` package is the one imported - check `billing.__file__`). Re-run at least mutants
  (a) widen, (b)/(g) direction, (c) blocklist, (d) distinct (MIN), (e) unknown-only, (f) LIKE wildcard,
  and (h) raw-alias; each must turn a NAMED test red. Also try 3 mutants of your own invention aimed at
  assertions that might be vacuous (e.g. `DirectoryAdded` gate removed; session_id 'unknown' guard removed;
  `ifnull(event,'')` / NULL-cwd handling removed; same-row repo/cwd pairing broken; ASCII case folding
  removed; first-row fallback removed) and report which are NOT caught.
- Check each test for vacuity: it must fail if behavior regresses. Flag tests that assert only
  that something is not raised, that compare a value to itself, that use a path which would be
  `unknown` for a different reason than the one named, or that seed Windows paths with an unescaped
  backslash escape (e.g. `'\d'`, `'\U'`, `'\n'` pitfalls).
- Check determinism: no network, no real clock, nothing outside `tmp_path`, no reliance on dict/set
  ordering or on a shared DB; run the file twice and with `-p no:randomly` if applicable.
- Check both token_usage and cost_usage are really asserted where claimed, and the export smoke test
  really exercises `export.build`.
- Rungs: run `python -m pytest tests/test_attribute_inheritance.py -q` and
  `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_export_unattributed.py tests/test_invoice.py tests/test_reconcile.py -q` yourself. NOT the full suite.
- Write fence: final tree = `M billing/otel/attribute.py` (task 01, hash above, unchanged), `?? tests/test_attribute_inheritance.py`, `?? _goals/unknown-parent-child-inheritance/`, nothing else.

## Files to Read
- _goals/unknown-parent-child-inheritance/02-tests.md, 01-attribute-inheritance.md, goal.md
- _goals/unknown-parent-child-inheritance/spawns/15-context.md and 15-report.md
- tests/test_attribute_inheritance.py (all of it), billing/otel/attribute.py, tests/test_attribute.py (conventions)
- .claude/skills/task-criteria/SKILL.md

## Write fence
none (never edit repo files; scratch copy only)

## Model
requested: claude-opus-5 · tier: frontier · rotation: n/a (cycle 1)

## Rules
- Do not fix anything. Cite file:line. Separate blocking defects from notes.
- Known non-blocking: AC5 wording `C:\mono` vs `C:\dev\mono` in task 01; `/media/<u>/<disk>/proj` allowed;
  deny-list residuals.

## Output
Verdict first: PASS | PASS (with notes) | NEEDS FIXES | REJECT, score out of 5, a per-requirement table,
your mutation table (mutant -> red tests / NOT caught), vacuity findings, blocking defects, notes,
`### Footprint`.
