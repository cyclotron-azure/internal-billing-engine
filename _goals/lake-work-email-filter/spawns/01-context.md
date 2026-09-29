You are the evaluator subagent. Read: .claude/agents/evaluator.md

CURRENT_DATETIME: 2026-09-29T12:00:00Z

## Task
Phase 3 goal evaluation for goal `lake-work-email-filter`. Validate goal.md and every task's
Acceptance Criteria once, against the goal criteria.

## Requirements
Check that every Phase 1 decision is reflected in a task: filter at export build (not ingest);
`unknown` user rows kept; env var ALLOWED_EMAIL_DOMAINS default cyclotron.com with exact
case-insensitive domain match; README updated after the code; no PR / no Phase 6.
Check write-set disjointness (tasks 02 and 03 both depend only on 01 and write disjoint files),
that requirements are verifiable, and that scope is right against the real code.

## Files to Read
- _goals/lake-work-email-filter/goal.md and 01..03 task files
- .claude/skills/goal-criteria/SKILL.md
- billing/otel/export.py, README.md (ground truth), CLAUDE.md, .env.example

## Write fence
None. Read-only evaluation.

## Model
requested: claude-opus-5 · tier: frontier · rotation: n/a

## Rules
Do not edit any file. Verdict: PASS / NEEDS REVISION / REJECT with concrete flagged items.

## Output
Verdict + itemized findings + `### Footprint` block.
