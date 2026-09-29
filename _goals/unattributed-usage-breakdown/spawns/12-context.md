You are the evaluator subagent. Read: .claude/agents/evaluator.md

CURRENT_DATETIME: 2026-09-28T23:45:00Z

## Task
Phase 4 task evaluation (eval_depth: light) of task 03 `03-readme-columns` in goal
`unattributed-usage-breakdown`: README.md and fabric/README.md edits documenting the new
lake columns. Evaluate against the task file and `.claude/skills/task-criteria/SKILL.md`.

## Requirements
- Read the real `git diff README.md fabric/README.md` (the report abbreviates it).
- Check every checkbox and AC1–AC3 in 03-readme-columns.md.
- Check factual accuracy against the code, not just the task wording:
  `billing/otel/project_label.py` (label rules, special values, examples used in the
  README must actually produce the stated labels — run them), `billing/otel/export.py`
  (columns, grain, summing), `billing/otel/attribute.py` (class meanings).
- Privacy: no real person's full path or username in the docs.
- No unrelated lines changed; no out-of-scope follow-up described as done.
- Write fence: only README.md and fabric/README.md changed by this task
  (`git status --short`; pre-existing dirty: client-package.zip, export.py,
  project_label.py, _goals/).

## Files to Read
- _goals/unattributed-usage-breakdown/03-readme-columns.md
- _goals/unattributed-usage-breakdown/goal.md
- _goals/unattributed-usage-breakdown/spawns/11-report.md
- README.md, fabric/README.md (current) and their git diff
- billing/otel/project_label.py, billing/otel/export.py, billing/otel/attribute.py
- .claude/skills/task-criteria/SKILL.md

## Write fence
None. Evaluate only; scratch in the session scratchpad only.

## Model
requested: claude-opus-5 · tier: frontier · rotation: n/a

## Output
`VERDICT: PASS` | `VERDICT: PASS (with notes)` | `VERDICT: NEEDS FIXES` |
`VERDICT: REJECT`, findings with exact fixes (quote the README line), `### Footprint`.
