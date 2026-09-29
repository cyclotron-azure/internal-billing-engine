You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-29T13:00:00Z

## Task
Execute task 01: _goals/lake-work-email-filter/01-export-domain-filter.md (read it and goal.md in full).

## Requirements
Every requirement and acceptance criterion in the task file. Verify with ad-hoc checks (tmp store; subprocess needs PYTHONPATH=<repo root>) and run `python -m pytest -q tests/test_export.py tests/test_export_unattributed.py` (test-ladder rungs 1-2 only; do not run the full suite).

## Files to Read
_goals/lake-work-email-filter/goal.md, the task file, billing/otel/export.py, billing/config.py, .env.example, tests/test_export_unattributed.py, README.md (ground truth, do not edit).

## Write fence
billing/otel/export.py, .env.example — nothing else.

## Model
requested: claude-sonnet-5 · tier: light · rotation: n/a

## Rules
Stdlib only. No secrets. No persistence. Do not touch attribution, scheduler.py, tests, README. Env read at call time. Kept rows keep their current keys.

## Output
Report: files changed, ad-hoc verification evidence per AC, test results, deviations, and a `### Footprint` block.
