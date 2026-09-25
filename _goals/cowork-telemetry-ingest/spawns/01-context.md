You are the evaluator subagent. Read: .claude/agents/evaluator.md

CURRENT_DATETIME: 2026-09-23T00:00:00Z

## Task

Validate the goal `cowork-telemetry-ingest` (Phase 3 — goal evaluation) per
`.claude/skills/goal-criteria/SKILL.md`. Check every task file's `## Acceptance Criteria`
for specificity and verifiability, check task ownership contracts for disjoint `writes` sets
where no `depends_on` ordering exists, and check that every Phase 1 decision recorded in
`goal.md`'s Discovery Summary is actually reflected in at least one task.

Pay particular attention to the goal's hard isolation requirement (stated explicitly by the
user, not inferred): no file belonging to the existing `claude_code` pipeline
(`billing/otel/receiver.py`, `billing/otel/otel_store.py`, `billing/otel/attribute.py`,
`billing/otel/normalize.py`, `billing/otel/transcript.py`, `billing/otel/records.py`,
`billing/otel/sample_payload.py`, `billing/reconcile.py`, `billing/otel/bill.py`,
`billing/report.py`) may be modified by any task in this goal. Confirm every task's
`writes:` list is consistent with this, and that task 00 and task 05 together make this a
tested claim, not merely an assertion in prose.

## Files to Read

- `_goals/cowork-telemetry-ingest/goal.md`
- `_goals/cowork-telemetry-ingest/00-test-scaffold.md`
- `_goals/cowork-telemetry-ingest/01-cowork-store-schema.md`
- `_goals/cowork-telemetry-ingest/02-cowork-ingest-payload.md`
- `_goals/cowork-telemetry-ingest/03-cowork-receiver.md`
- `_goals/cowork-telemetry-ingest/04-cowork-reporting.md`
- `_goals/cowork-telemetry-ingest/05-integration.md`
- `.claude/skills/goal-criteria/SKILL.md`
- `README.md` (ground truth for existing conventions these tasks must follow)
- `billing/otel/receiver.py`, `billing/otel/otel_store.py`, `billing/otel/attribute.py` (to
  judge whether the new tasks' designs are actually achievable without touching them)

## Write fence

None — evaluator produces a verdict only, writes nothing.

## Model

requested: claude-opus-5 · tier: frontier · rotation: n/a

## Rules

- Validate once for all tasks; do not re-derive the goal, only check it.
- Flag any task whose Acceptance Criteria are vague, unverifiable, or inconsistent with its
  Requirements.
- Flag any two tasks with overlapping `writes:` sets that lack a `depends_on` ordering
  between them.
- Flag any Phase 1 decision in goal.md's Discovery Summary that no task actually implements.
- Flag specifically if the isolation requirement is not enforceable as written (e.g. a task
  reads a file in a way that could tempt an implementer to "fix" it, or the write fences
  don't actually cover every file that would need touching to hit a stated Acceptance
  Criterion).
- Verdict must be exactly one of PASS, NEEDS REVISION, REJECT, with reasoning.

## Output

Verdict (PASS / NEEDS REVISION / REJECT) with itemized reasoning per task file, and any
specific line-level fixes required if NEEDS REVISION.
