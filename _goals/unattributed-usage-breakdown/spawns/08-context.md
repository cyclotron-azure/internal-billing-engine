You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-28T22:55:00Z

## Task
Execute task 02 of goal `unattributed-usage-breakdown`: change
`billing/otel/export.py` so both lake CSVs carry two new trailing columns,
`attribution_source` and `unattributed_project`, and rows whose resolved repo is
`unknown` split by them. The full specification is
`_goals/unattributed-usage-breakdown/02-export-breakdown.md`. Implement it as written.

## Requirements
Every checkbox under "Requirements" and Acceptance Criteria 1–5 in
02-export-breakdown.md. Highlights:
- Append `"attribution_source", "unattributed_project"` AFTER `"generated_at"` in both
  `SUMMARY_FIELDS` and `LINE_FIELDS`; nothing else moves.
- Attributed rows (resolved repo != "unknown"): identical keys, row count and values
  (except `generated_at`) to today; new columns "".
- Unknown rows: keys gain (attribution_source, unattributed_project); class from
  `resolved_view()`'s `attribution_source` column; label =
  `project_label.load_session_labels(store.db).get(session_id, "")`, called once per
  build; tokens/cost conserved; first/last span per split row; "is unknown" decided on
  the resolved repo KEY, never the bill name.
- `attribution_source` / `session_id` evaluated only for unknown rows (CASE guards, or
  a materialized CTE if faster); each table goes through `resolved_view()` at most once.
- Timing: ≥20,000 datapoints, 25% unknown (half with timeline rows, half without);
  post/pre full `build()` ≤ 3×. If the first measurement lands above 2.5×, use the
  median of 5 runs and/or a larger store (evaluator note). Report 0% and 50% too.
- The label never passes through `name_of` / `repo_name` / `repo_name_map` and never
  appears in `repo` / `repo_key`.
- Update the module docstring by one or two sentences.

## Files to Read
- _goals/unattributed-usage-breakdown/02-export-breakdown.md (spec; read in full)
- _goals/unattributed-usage-breakdown/goal.md (Success Criteria, Constraints, Risks)
- CLAUDE.md
- README.md lines 293–330 (lake table contract)
- billing/otel/export.py (current implementation)
- billing/otel/attribute.py (resolved_view, attribution_source)
- billing/otel/project_label.py (frozen interface from task 01; use load_session_labels)
- billing/otel/otel_store.py (OtelStore constructor, insert helpers, schema) — for
  seeding temp stores in your checks
- tests/conftest.py (`_usage_row`, `seed_otlp_rows` patterns for seeding)
- tests/test_export.py (existing expectations that must keep passing)
- .claude/skills/test-ladder/SKILL.md, .claude/skills/python-performance-optimization/SKILL.md

## Write fence
- billing/otel/export.py   (the ONLY repo path you may modify)
Scratch scripts and the pre-change copy go ONLY in:
C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\0ab35cbd-cb5c-4db5-9ffc-e0282cc3cab6\scratchpad
Pre-change copy: `git show HEAD:billing/otel/export.py` (HEAD equals the working tree for
this file) into the scratchpad, with its relative imports rewritten to `billing.otel.*`.

## Model
requested: claude-sonnet-5 · tier: light · rotation: n/a (cycle 1)

## Rules
- Standard library only; no third-party import may enter billing/.
- Repo attribution stays resolved at query time: no new table/column/index, no writes
  or commits to otel.db, single connection.
- Do not edit attribute.py, project_label.py, invoice.py, bill.py, normalize.py, tests,
  README, or anything else.
- No git command that changes the working tree or index (stash/checkout/restore/reset);
  `git show` / `git diff` are fine.
- Keep `build()`, `build_and_enqueue()`, `main()` signatures and return shapes.
- Comments: at most one short line where the why is non-obvious.
- Do NOT run the full suite; rung 2 is
  `python -m pytest tests/test_export.py tests/test_attribute.py tests/test_invoice.py -q`.
- Close stores before deleting temp files (Windows file locks).

## Output
Report with: files changed; evidence for AC1–AC5 (commands + output: both CSV headers;
the before/after diff of the seeded store excluding generated_at; per (day, model,
user) token/cost conservation; the three timing ratios with method); rung 2 result;
any deviation with reason; `### Footprint`.
