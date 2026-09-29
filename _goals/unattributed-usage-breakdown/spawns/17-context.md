You are the evaluator subagent, in AUDIT MODE. Read: .claude/agents/evaluator.md

CURRENT_DATETIME: 2026-09-29T00:45:00Z

## Task
Phase 5 final audit of goal `unattributed-usage-breakdown`. All four tasks have passed
their task evaluations (01, 02 and 03 after fix cycles; 02 after a user decision to
accept the collision correction). Audit the goal as a whole: every task's requirements,
cross-task integration, the goal's Success Criteria and Constraints, and regressions.

## Requirements
- Check every goal.md Success Criterion against the delivered code, tests and docs.
  Interpret "no cell contains `Users`" as a whole `Users` path segment (ruling carried
  from task 01/04 evaluations).
- Check the hard constraints (CLAUDE.md): stdlib-only runtime under billing/; single
  connection SQLite; attribution resolved at query time and nothing persisted; no
  secrets; README is ground truth (README must match the code).
- Integration: project_label ↔ export ↔ README ↔ tests are consistent (field names,
  special labels, class names, walk-up rule, collision correction).
- Regressions: run `python -m pytest tests/test_project_label.py tests/test_export_unattributed.py tests/test_export.py tests/test_attribute.py tests/test_invoice.py tests/test_bill.py tests/test_reconcile.py -q`.
  Do NOT run the full suite; the orchestrator runs it after your verdict.
- Confirm out-of-scope items were not touched (hooks, client-package/, deploy/,
  invoice.py, bill.py, normalize.py, attribute.py, fabric notebook) and nothing was
  committed (`git status`, `git log -1`, `git diff --stat`).
- Review the orchestration log for skipped evaluations or unlogged spawns.
- Carried-forward minor notes (decide if any should block): export.py docstring lines
  6–7 grain wording; README `local:(other)` bullet omits `-Users-` slug and control
  characters; project_label.py has two comment lines vs one allowed; DEL/C1 control
  chars pass the guard; test-name overclaim on the network test.

## Files to Read
- CLAUDE.md
- _goals/unattributed-usage-breakdown/goal.md and 01–04 task files
- _goals/unattributed-usage-breakdown/orchestration-log.md
- billing/otel/project_label.py, billing/otel/export.py (and git diff), billing/otel/attribute.py,
  billing/otel/invoice.py
- README.md and fabric/README.md (git diff)
- tests/test_project_label.py, tests/test_export_unattributed.py, tests/COVERAGE_MAP.md (new section)
- .claude/skills/task-criteria/SKILL.md

## Write fence
None. Audit only; scratch in the session scratchpad only.

## Model
requested: claude-opus-5 · tier: frontier · rotation: n/a

## Output
`VERDICT: APPROVED` | `VERDICT: ISSUES FOUND`, a per-Success-Criterion table
(✅/❌ with evidence), findings with severity and exact fix, `### Footprint`.
