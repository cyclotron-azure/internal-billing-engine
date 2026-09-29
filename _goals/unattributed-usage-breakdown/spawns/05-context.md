You are the evaluator subagent. Read: .claude/agents/evaluator.md

CURRENT_DATETIME: 2026-09-28T22:20:00Z

## Task
Phase 4 task evaluation (eval_depth: full) of task 01 `01-project-label` in goal
`unattributed-usage-breakdown`. Evaluate the delivered `billing/otel/project_label.py`
against the task file and `.claude/skills/task-criteria/SKILL.md`. Verify independently;
do not trust the implementer's report.

## Requirements
- Re-run all 30 worked examples yourself against the real module (22 has parts a/b).
- Re-run AC1 (interface + stdlib-only imports), AC3 (malformed inputs; construct a real
  UNC string `"\\\\host\\share"` in Python rather than trusting the report), AC4
  (privacy over every example cwd), AC5 (one SELECT via set_trace_callback, `{}` on
  empty timeline, empty labels omitted, no writes).
- Check each Definition and Root algorithm step in the code, not just the outputs.
- Judge the implementer's three flagged judgement calls:
  1. `claude` counted anywhere after Temp/tmp/T (not only immediately after).
  2. A cwd whose last segment is bare `Users` / `home` (e.g. `C:\Users`, `/home`)
     yields `local:Users`. goal.md success criterion 5 says no label cell may contain a
     `Users` path segment. Decide whether this is a defect in the delivered module
     against the goal's success criteria (the orchestrator's reading: yes; the fix is to
     treat a bare `Users`/`home` as within the outer zone → `local:(home)`).
  3. `root_label` wrapping everything in `try/except Exception` → `""`.
- Also check: `" "` (whitespace-only cwd) returned `""`; spec step 1 says "non-empty
  cwd" and step 3 maps zero segments to `local:(home)`. Decide whether `""` or
  `local:(home)` is the correct reading and whether it matters.
- Confirm nothing outside `billing/otel/project_label.py` changed (`git status --short`;
  expected pre-existing: ` M client-package.zip` and untracked `_goals/unattributed-usage-breakdown/`).

## Files to Read
- _goals/unattributed-usage-breakdown/01-project-label.md
- _goals/unattributed-usage-breakdown/goal.md (Success Criteria, Constraints)
- _goals/unattributed-usage-breakdown/spawns/04-report.md (implementer report)
- billing/otel/project_label.py
- billing/otel/attribute.py
- .claude/skills/task-criteria/SKILL.md
- CLAUDE.md

## Write fence
None. Evaluate only; throwaway scripts via stdin or the session scratchpad
(C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\0ab35cbd-cb5c-4db5-9ffc-e0282cc3cab6\scratchpad) only.

## Model
requested: claude-opus-5 · tier: frontier · rotation: n/a

## Rules
- Never fix anything. Cite file:line. Tag any finding `destructive`, `security` or
  `infra` if it is one.
- Do not run the full suite; `python -m pytest tests/test_attribute.py -q` is allowed.

## Output
`VERDICT: PASS` | `VERDICT: PASS (with notes)` | `VERDICT: NEEDS FIXES` |
`VERDICT: REJECT`, numbered findings with severity and an exact fix for each, then
`### Footprint`.
