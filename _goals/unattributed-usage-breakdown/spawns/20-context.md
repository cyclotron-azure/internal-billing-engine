You are the evaluator subagent, running Phase 6.5 (align-docs final audit). Read:
.claude/agents/evaluator.md and .claude/skills/align-docs/SKILL.md.

CURRENT_DATETIME: 2026-09-29T01:20:00Z

## Task
Final doc audit for goal `unattributed-usage-breakdown`. The small-change fold applied
(edit list had 1 doc), so this audit ALSO verifies the Phase 6.3 edit-list criteria.

## Requirements
- **Edit-list criteria (6.3, folded):**
  - Coverage: grep every in-scope markdown file (everything except `_research/` and
    `_goals/`) for this feature's identifiers (`claudeusagesummary`,
    `claudeusagelineitems`, `attribution_source`, `unattributed_project`,
    `project_label`, `export.py`, `bill_name`, `one row per`, `unknown`, `local:(`).
    Was any stale doc missed? The orchestrator excluded `deploy/README.md:254`,
    `tests/golden/README.md:53-55`, `.claude/ORCHESTRATION.md`, `.claude/skills/*`,
    `.claude/agents/qa-evaluator.md` as unaffected; confirm or refute each.
  - Scope: no code, test, config, `_goals/`, `_research/` or `client-package.zip` edits
    in this phase.
  - Anti-invention: every claim in the Phase 6.4 edits traces to code.
- **Accuracy and consistency:** README.md and fabric/README.md are accurate against
  `billing/otel/project_label.py` and `billing/otel/export.py`, and mutually consistent
  (column lists, class meanings, special labels, the walk-up rule, collision
  correction, Power BI note). Links/anchors resolve.
- Phase 6.4 report: `_goals/unattributed-usage-breakdown/spawns/19-report.md`.
- `git status --short`: beyond the goal's code/test files already audited in Phase 5
  (billing/otel/project_label.py, billing/otel/export.py, tests/test_project_label.py,
  tests/test_export_unattributed.py, tests/COVERAGE_MAP.md) and the pre-existing
  `client-package.zip` + `_goals/`, only documentation files changed.
- If a doc change implies `client-package.zip` is stale, say so (not expected: no
  client-package change in this goal).

## Files to Read
- .claude/skills/align-docs/SKILL.md
- _goals/unattributed-usage-breakdown/goal.md (read only)
- _goals/unattributed-usage-breakdown/spawns/19-report.md
- README.md, fabric/README.md and `git diff` of both
- billing/otel/project_label.py, billing/otel/export.py, billing/otel/attribute.py

## Write fence
None. Audit only.

## Model
requested: claude-opus-5 · tier: frontier · rotation: n/a

## Output
`VERDICT: APPROVED` | `VERDICT: ISSUES FOUND`, the edit-list criteria results, findings
with exact fixes, the list of docs changed, `### Footprint`.
