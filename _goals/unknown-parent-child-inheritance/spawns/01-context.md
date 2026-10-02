You are the evaluator subagent. Read: .claude/agents/evaluator.md

CURRENT_DATETIME: 2026-10-01T10:50:00-10:00

## Task
Phase 3 goal evaluation (attempt 1). Validate the goal and its two task files BEFORE any
execution, using `.claude/skills/goal-criteria/SKILL.md`. Validate every task's
`## Acceptance Criteria` once. Be skeptical: look for requirement/criterion gaps, tasks that
cannot be verified, ownership-contract defects, hidden behavior changes, and mismatches
between the goal's Discovery Summary and the tasks.

## Requirements
- Every decision in goal.md's Discovery Summary must be reflected in a task.
- The rule is STRICT: no misattribution. Hunt for any reading of the task text under which an
  unrelated folder could inherit a repo, or under which today's behavior (non-unknown
  effective row, no timeline row, wrapper fall-through, 'unknown' effective row never falling
  back to the wrapper tag) could silently change.
- Check the SQL spec for correctness against SQLite semantics (NULL handling, `substr` and
  `||` precedence, `GLOB '[a-z]:'`, `replace` with a backslash literal, `rtrim` charset,
  correlated subquery aliasing inside `WITH r AS (...)` used by bill/invoice/reconcile/export).
- Check the performance gate is measurable and the escalation path is clear.
- Check disjoint write sets and depends_on ordering; eval_depth reasons.

## Files to Read
- _goals/unknown-parent-child-inheritance/goal.md
- _goals/unknown-parent-child-inheritance/01-attribute-inheritance.md
- _goals/unknown-parent-child-inheritance/02-tests.md
- .claude/skills/goal-criteria/SKILL.md
- billing/otel/attribute.py (current implementation, for grounding)
- billing/otel/otel_store.py (session_repo_timeline schema and index)
- tests/test_attribute.py (existing contracts)
- CLAUDE.md and README.md (hard constraints; README is ground truth)

## Write fence
none (evaluator never edits)

## Model
requested: claude-opus-5 · tier: frontier · rotation: n/a

## Rules
- Do not fix anything. Report findings only.
- Cite file and line for each finding; mark severity (major/minor).

## Output
Verdict line first: PASS | PASS (with notes) | NEEDS REVISION | REJECT, then a score out of 5,
then findings, then a `### Footprint` block (`files_read: <N> (~<C> chars)`).
