You are the test-writer subagent. Read: .claude/agents/test-writer.md

CURRENT_DATETIME: 2026-09-29T00:15:00Z

## Task
Execute task 04 of goal `unattributed-usage-breakdown`: write outcome-verifying pytest
coverage for `billing/otel/project_label.py` and the export split in
`billing/otel/export.py`, plus a coverage-map section. The full specification is
`_goals/unattributed-usage-breakdown/04-tests.md`. Implement it as written.

## Requirements
Every checkbox and Acceptance Criterion in 04-tests.md. Key points and decisions that
landed during execution (all reflected in the task files; restated so you don't miss
them):
- `tests/test_project_label.py`: all 38 worked examples from 01-project-label.md as
  parametrized cases (22 has parts a/b). Build backslash / UNC / NUL strings as Python
  literals (e.g. `"\\\\host\\Users\\bob"`, `"C:\\Cyclotron\\bad\x00name"`), never via
  shell. Plus the extra cases listed in 04-tests.md.
- Privacy assertions use WHOLE-SEGMENT reading for `Users`/`home` (evaluator ruling):
  `local:users-api` and `local:Project.Users` are allowed labels; a label body must
  never contain `/`, `\`, a `:` other than the prefix's, `.claude`, `OneDrive`
  (case-insensitive), a `C--` / `-Users-` slug, a bare `Users`/`home` segment, or a
  seeded username.
- `root_label` never raises / never returns a bare `local:` (malformed inputs listed).
- `load_session_labels`: one SELECT (count via `sqlite3.Connection.set_trace_callback`),
  `{}` on empty timeline, empty-label sessions omitted, no writes.
- `tests/test_export_unattributed.py` (seed a temp OtelStore locally in this file; do
  NOT edit conftest.py): header order with hard-coded pre-change lists; attributed rows
  unchanged vs hard-coded baseline on a collision-free store; Derek-shaped `timeline` /
  `local:Dashnoard` vs no-timeline (`absent`/`no_remote`, "") split; conservation vs the
  DATABASE; span per split row; repo_name_map override does not change the split and
  the label never appears in `repo`/`repo_key`; privacy on the two new columns + no
  seeded full path anywhere in either CSV; `invoice.py` totals unchanged.
- **Collision correction (user decision):** an attributed session with raw models
  `claude-sonnet-5`, `claude-sonnet-5[1m]`, `claude-sonnet-5-20251001` on the same
  day/user, and a user split across NULL and `""` emails → export totals equal the
  database, and per (repo, normalized model, period) equal `invoice.py`'s totals for the
  same store.
- `tests/COVERAGE_MAP.md`: append ONE section `# Coverage map: unattributed-usage-breakdown`
  mapping every acceptance criterion of tasks 01–03 to node ids (command-output /
  doc-review-only criteria listed as GAP with the reason). Leave every other section
  untouched.

## Files to Read
- _goals/unattributed-usage-breakdown/04-tests.md (spec)
- _goals/unattributed-usage-breakdown/01-project-label.md (38 examples + Definitions)
- _goals/unattributed-usage-breakdown/02-export-breakdown.md, 03-readme-columns.md (ACs
  to map)
- _goals/unattributed-usage-breakdown/goal.md (Success Criteria)
- billing/otel/project_label.py, billing/otel/export.py, billing/otel/attribute.py,
  billing/otel/invoice.py, billing/otel/otel_store.py (store API for seeding)
- tests/conftest.py (fixture and seeding patterns), tests/test_export.py (CSV-reading
  style), tests/COVERAGE_MAP.md (section format)
- .claude/skills/test-ladder/SKILL.md, .claude/skills/python-testing-patterns/SKILL.md

## Write fence
- tests/test_project_label.py (new, whole file)
- tests/test_export_unattributed.py (new, whole file)
- tests/COVERAGE_MAP.md (append one section only)

## Model
requested: claude-sonnet-5 · tier: light · rotation: n/a (cycle 1)

## Rules
- pytest only; stdlib + pytest; temp dirs (`tmp_path`); deterministic data; no network,
  no ADLS, no live services.
- Do not edit product code, conftest.py, or existing tests; do not weaken anything.
- No git command that changes the working tree or index.
- Close stores before tmp cleanup (Windows locks).
- Rungs 1–2 only: run
  `python -m pytest tests/test_project_label.py tests/test_export_unattributed.py -q`
  and `python -m pytest tests/test_export.py tests/test_attribute.py tests/test_invoice.py -q`.
  Do NOT run the full suite (rung 3 belongs to the orchestrator).
- If a test fails because product behaviour contradicts the spec, do not change the test
  to match: report it as a finding.

## Output
Report: files created/changed; test counts; both rung-2 command outputs;
`pytest --collect-only -q` for the two new files; the coverage-map section; any product
behaviour that contradicted the spec; `### Footprint`.
