You are the evaluator subagent. Read: .claude/agents/evaluator.md

CURRENT_DATETIME: 2026-09-29T00:30:00Z

## Task
Phase 4 task evaluation (eval_depth: light) of task 04 `04-tests` in goal
`unattributed-usage-breakdown`. Evaluate the new tests and coverage-map section against
the task file and `.claude/skills/task-criteria/SKILL.md`.

## Requirements
- Run `python -m pytest tests/test_project_label.py tests/test_export_unattributed.py -q`
  and `python -m pytest tests/test_export.py tests/test_attribute.py tests/test_invoice.py -q`.
- Check every requirement checkbox in 04-tests.md is covered by a real, outcome-verifying
  test (read the tests; spot-check that key assertions would fail if the product
  regressed, e.g. mutate a copy of project_label.py / export.py in the scratchpad or
  monkeypatch, and confirm the relevant tests go red — do not edit repo files).
- In particular confirm: all 38 worked examples are present with the exact expected
  labels from 01-project-label.md; the collision-correction test compares against the
  database AND invoice.py; privacy assertions use the whole-segment reading; no test is
  tautological (e.g. comparing export to itself).
- Coverage-map section: appended only, every task 01–03 criterion present, GAPs have
  reasons, node ids exist (`pytest --collect-only -q` on the two files).
- Write fence: only the three task-04 paths changed by this task (`git status --short`;
  pre-existing dirty: client-package.zip, export.py, project_label.py, README.md,
  fabric/README.md, _goals/). conftest.py and existing tests untouched
  (`git diff --quiet HEAD -- tests/conftest.py tests/test_export.py ...`).

## Files to Read
- _goals/unattributed-usage-breakdown/04-tests.md, 01-project-label.md (examples),
  02-export-breakdown.md, 03-readme-columns.md
- _goals/unattributed-usage-breakdown/spawns/15-report.md
- tests/test_project_label.py, tests/test_export_unattributed.py, tests/COVERAGE_MAP.md
  (new section)
- billing/otel/project_label.py, billing/otel/export.py, billing/otel/invoice.py
- .claude/skills/task-criteria/SKILL.md

## Write fence
None. Evaluate only; mutation copies and scratch files only in the session scratchpad
(C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\0ab35cbd-cb5c-4db5-9ffc-e0282cc3cab6\scratchpad).

## Model
requested: claude-opus-5 · tier: frontier · rotation: n/a

## Output
`VERDICT: PASS` | `VERDICT: PASS (with notes)` | `VERDICT: NEEDS FIXES` |
`VERDICT: REJECT`, findings with exact fixes, `### Footprint`.
