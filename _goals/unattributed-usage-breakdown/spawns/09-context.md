You are the evaluator subagent. Read: .claude/agents/evaluator.md

CURRENT_DATETIME: 2026-09-28T23:05:00Z

## Task
Phase 4 task evaluation (eval_depth: full) of task 02 `02-export-breakdown` in goal
`unattributed-usage-breakdown`. Evaluate the modified `billing/otel/export.py` against
the task file and `.claude/skills/task-criteria/SKILL.md`. Verify independently.

## Requirements
- Re-check every Requirement and AC1–AC5 in 02-export-breakdown.md with your own seeded
  temp store(s) and your own pre-change copy (`git show HEAD:billing/otel/export.py`
  into the scratchpad with imports rewritten to `billing.otel.*`).
- Verify `attribution_source` / `session_id` are only evaluated for unknown rows
  (read the SQL; optionally EXPLAIN / timing), each table passes through
  `resolved_view()` once, `load_session_labels` is called once per build.
- Re-measure the 25%-unknown timing yourself (≥20,000 datapoints; median of 5).
- **Specific judgement required:** the implementer changed `cost[key] = …` /
  `toks[key] = …` to `+=`. In the pre-change code, raw models that `normalize_model`
  collapses to the same name, or NULL vs empty-string `user_email`, overwrite each other
  and drop usage from the export. The task requires attributed rows "identical to the
  current implementation". Determine: (a) exactly which inputs produce a different
  attributed row now; (b) whether `invoice.py` already sums (so export now agrees with
  invoicing); (c) whether any existing test fixture exercises it; (d) your ruling: a
  defect against the spec, an acceptable necessary change (e.g. the split cannot be
  conserved without `+=`), or something the orchestrator must escalate to the user
  because it changes billed dollar amounts in Fabric. Be precise about (d).
- Confirm the write fence (`git status --short`; `git diff --stat`).
- Confirm no edits to attribute.py, project_label.py, invoice.py, bill.py, normalize.py,
  tests, README.

## Files to Read
- _goals/unattributed-usage-breakdown/02-export-breakdown.md
- _goals/unattributed-usage-breakdown/goal.md
- _goals/unattributed-usage-breakdown/spawns/08-report.md
- billing/otel/export.py, billing/otel/attribute.py, billing/otel/project_label.py,
  billing/otel/invoice.py, billing/otel/normalize.py
- tests/test_export.py, tests/conftest.py
- .claude/skills/task-criteria/SKILL.md, CLAUDE.md

## Write fence
None. Evaluate only; scratch files only in the session scratchpad
(C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\0ab35cbd-cb5c-4db5-9ffc-e0282cc3cab6\scratchpad).

## Model
requested: claude-opus-5 · tier: frontier · rotation: n/a

## Rules
Never fix anything. Cite file:line. Tag destructive/security/infra if applicable.
Rung 2 allowed: `python -m pytest tests/test_export.py tests/test_attribute.py tests/test_invoice.py -q`.

## Output
`VERDICT: PASS` | `VERDICT: PASS (with notes)` | `VERDICT: NEEDS FIXES` |
`VERDICT: REJECT`, findings with exact fixes, the `+=` ruling as its own section,
`### Footprint`.
