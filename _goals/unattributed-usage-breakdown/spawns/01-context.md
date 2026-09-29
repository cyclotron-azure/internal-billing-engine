You are the evaluator subagent. Read: .claude/agents/evaluator.md

CURRENT_DATETIME: 2026-09-28T21:03:00Z

## Task
Phase 3 goal evaluation for goal `unattributed-usage-breakdown`. Evaluate goal.md and
all four task files against `.claude/skills/goal-criteria/SKILL.md`. Validate every
task's `## Acceptance Criteria` section once (criterion + verification method each).
Check that every decision in goal.md's Discovery Summary (the user's Phase 1 answers) is
reflected in a task, that write sets are disjoint for tasks without a depends_on
ordering, that eval_depth choices are justified, that the contract-first rule holds, and
that the task requirements are correct against the real code (not just internally
consistent).

## Requirements
- Read every file listed below in full.
- Verify claims against the code: e.g. that `attribute.resolved_view()` exposes an
  `attribution_source` column usable by export.py; that appending fields after
  `generated_at` keeps `tests/test_export.py` passing; that the task 01 root algorithm
  actually yields each worked example (trace each one by hand).
- Flag ambiguity a worker could resolve two ways, scope creep against Out of Scope, and
  anything that breaks a CLAUDE.md hard constraint (stdlib only; single-connection
  SQLite; attribution resolved at query time; never commit a secret; README is ground
  truth).
- Flag privacy gaps: any path by which a full path, username, OneDrive org folder, or
  scratchpad slug could still reach an exported cell.

## Files to Read
- CLAUDE.md
- .claude/skills/goal-criteria/SKILL.md
- _goals/unattributed-usage-breakdown/goal.md (includes the Phase 1 Discovery Summary)
- _goals/unattributed-usage-breakdown/01-project-label.md
- _goals/unattributed-usage-breakdown/02-export-breakdown.md
- _goals/unattributed-usage-breakdown/03-readme-columns.md
- _goals/unattributed-usage-breakdown/04-tests.md
- billing/otel/export.py
- billing/otel/attribute.py
- billing/otel/otel_store.py (lines 1-130)
- billing/otel/normalize.py
- tests/test_export.py
- README.md lines 140-170 and 285-335
- fabric/README.md

## Write fence
None. You evaluate only; do not create or modify any file.

## Model
requested: claude-opus-5 · tier: frontier · rotation: n/a

## Rules
- Never fix anything; report only.
- Cite file:line for every finding.
- Real production context for the worked examples: Derek's timeline cwds include
  `C:\Users\DerekMcConnell\OneDrive - Cyclotron Inc\Code\Dashnoard`,
  `...\Code\Dashnoard\OfficeDashboard\backend`, `C:\Users\DerekMcConnell\src\orbit`,
  `C:\Users\DerekMcConnell\src\orbit-local`, `C:\Users\DerekMcConnell\src\orbit-wt\google\apps\api`;
  Sumit's include `C:\Cyclotron\Insights Agent\ai-presales-agent-main`,
  `...\ai-presales-agent-main\ai-presales-agent-main`,
  `C:\Users\SumitBhatia\.claude\projects\C--Cyclotron-Insights-Agent-ai-presales-agent-main\scratchpad`.

## Output
A verdict line: `VERDICT: PASS` | `VERDICT: NEEDS REVISION` | `VERDICT: REJECT`, then a
numbered findings list (severity: blocker / major / minor, file:line, what is wrong, what
would fix it), then a `### Footprint` block with your approximate characters read.
