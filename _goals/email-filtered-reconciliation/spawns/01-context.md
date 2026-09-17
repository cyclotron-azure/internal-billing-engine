You are the evaluator subagent. Read: .claude/agents/evaluator.md

CURRENT_DATETIME: 2026-09-14T00:00:00Z

## Task
Phase 3 goal evaluation for the `email-filtered-reconciliation` goal. Validate that
`goal.md` and its two task files fully and correctly capture the Phase 1 alignment
decisions, that every task's Acceptance Criteria are specific/verifiable, that the
task ownership contracts (writes/reads/depends_on/owner/eval_depth) are internally
consistent and non-overlapping, and that nothing in scope was dropped and nothing out
of scope crept in.

## Requirements
- Read `.claude/skills/goal-criteria/SKILL.md` and apply its checklist.
- Confirm every Phase 1 Q&A decision recorded in goal.md's "Discovery Summary" section
  is reflected in at least one task's Requirements or Acceptance Criteria:
  - Repeatable `--email` flag shape
  - Analytics-side-empty -> warning + skip funnel; OTEL-side-empty -> valid zero funnel
  - No-`--email` behavior unchanged
  - Reusable (importable) filtering functions, not inlined in argparse/main()
  - Stdlib-only constraint
  - Docs (Phase 6 on) and PR (Phase 7 on) both recorded in the phases: yaml block
- Confirm task 01's write-set (`billing/reconcile.py`, `billing/store.py`) and task
  02's write-set (`tests/test_reconcile.py`) are disjoint, and task 02's
  `depends_on: ["01-reconcile-email-filter"]` is correct given it reads task 01's
  output.
- Confirm task 01's `eval_depth: full` is justified (future dashboard consumer of
  these functions) and task 02's `eval_depth: light` is reasonable for a test-only task.
- Confirm Acceptance Criteria in both task files are each independently verifiable
  (unit test / command output) and not vague.
- Flag any scope creep, missing error-handling case, or ambiguity that would leave an
  implementer guessing.

## Files to Read
- _goals/email-filtered-reconciliation/goal.md
- _goals/email-filtered-reconciliation/01-reconcile-email-filter.md
- _goals/email-filtered-reconciliation/02-tests.md
- .claude/skills/goal-criteria/SKILL.md
- billing/reconcile.py (current state, pre-implementation)
- billing/store.py
- billing/otel/otel_store.py
- README.md (the "Analytics path (per-user)" and reconcile.py bullets)

## Write fence
None — this is an evaluation pass. Do not create or modify any file; report your
verdict only.

## Model
requested: claude-opus-5 · tier: frontier · rotation: n/a

## Rules
- Never edit product code, goal files, or task files yourself.
- Verdict must be one of: PASS, NEEDS REVISION, REJECT.
- For NEEDS REVISION, list every specific defect with the file and section it's in,
  precise enough that the orchestrator can revise without further back-and-forth.

## Output
A verdict (PASS / NEEDS REVISION / REJECT), a short rationale, and — if not PASS — an
itemized list of required changes. End with a `### Footprint` line estimating your own
work in tokens (e.g. `### Footprint: ~4000 tokens`).
