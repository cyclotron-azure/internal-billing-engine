# Task 04: Tests for the label and the export split

## Objective

Outcome-verifying pytest coverage exists for `billing/otel/project_label.py` and for the
export split, plus a coverage-map section mapping every acceptance criterion of tasks
01–03 to a test node id (or marking it a GAP with a reason).

## Dependencies

- 01-project-label, 02-export-breakdown, 03-readme-columns

```yaml
# --- task ownership contract ---
writes:
  - tests/test_project_label.py
  - tests/test_export_unattributed.py
  - tests/COVERAGE_MAP.md
reads:
  - billing/otel/project_label.py
  - billing/otel/export.py
  - billing/otel/attribute.py
  - billing/otel/invoice.py
  - tests/conftest.py
  - tests/test_export.py
depends_on:
  - "01-project-label"
  - "02-export-breakdown"
  - "03-readme-columns"
owner: test-writer
rewrite_semantics:
  tests/test_project_label.py: whole-file
  tests/test_export_unattributed.py: whole-file
  tests/COVERAGE_MAP.md: targeted-insertion   # append one section; leave all others untouched
eval_depth: light
```

## Requirements (exhaustive — the evaluator verifies every item)

**tests/test_project_label.py**
- [ ] All 38 worked examples in task 01 as parametrized cases.
- [ ] Deep start where several candidates apply: start `...\Code\Dashnoard\OfficeDashboard\backend`
      with history containing `...\Code\Dashnoard\OfficeDashboard` → `local:Dashnoard`.
- [ ] History containing the outer container itself (`...\Code`) → still `local:Dashnoard`.
- [ ] No SessionStart row: first non-empty cwd is used.
- [ ] Case-insensitive ancestor match.
- [ ] Claude-internal folders with and without a `scratchpad` segment, Windows and POSIX
      (`~/.claude/...`, `/tmp/claude/...`).
- [ ] Allowlist guard: a root equal to the username → `local:(other)`; a root starting
      with `C--` or `.` → `local:(other)` or `local:(scratchpad)` as the rules dictate.
- [ ] Truncation at 100 characters after the prefix.
- [ ] Never raises / never a bare `local:` for malformed inputs (`":"`, `"\\\\"`,
      `" "`, `"C:"`, a 10,000-character path).
- [ ] Privacy property: over every path used in this file, no label contains `/`, `\`,
      `:` other than the prefix's, `Users`, `OneDrive`, `.claude`, a `C--` slug, or the
      username.
- [ ] `load_session_labels`: empty timeline → `{}`; multi-session store groups
      correctly; empty-label sessions omitted; issues exactly one statement (use a
      `sqlite3` trace callback or a connection wrapper).

**tests/test_export_unattributed.py** (seed a temp `OtelStore` locally in the test file;
do not edit `conftest.py`)
- [ ] Header order: both field lists end with `attribution_source, unattributed_project`
      and the preceding fields equal the pre-change lists (hard-code the pre-change
      lists in the test).
- [ ] Attributed rows unchanged: a seeded attributed session yields the same rows as a
      pre-change baseline (hard-coded expected dicts) with empty new columns.
- [ ] Unknown split: Derek-shaped session (`timeline`, `local:Dashnoard`) and a
      session with no timeline rows (`absent` or `no_remote`, `""`) land in separate
      rows for the same day/user.
- [ ] Conservation: per (day, model, user) token and cost sums across the split equal
      the database totals.
- [ ] Collision correction: an attributed session with raw models `claude-sonnet-5`,
      `claude-sonnet-5[1m]` and `claude-sonnet-5-20251001` on the same day/user, and a
      user split across NULL and `""` emails, export totals equal to the database, and
      per (repo, model, period) equal to `invoice.py`'s totals for the same store.
- [ ] Span: first/last usage per split row are the min/max of its own datapoints.
- [ ] `repo_name_map` override of a real repo does not change the split; the label
      never appears in `repo` or `repo_key`.
- [ ] Privacy: no `unattributed_project` or `attribution_source` cell in either CSV
      contains a seeded full path, a path separator, `Users`, `OneDrive`, `.claude`, a
      drive letter, a `C--` slug, or a seeded username. Also assert no seeded full path
      appears anywhere in either CSV.
- [ ] `invoice.py` totals for the seeded store are unchanged by the export (call the
      invoice builder and compare to expected).
- [ ] All external services are absent (no network, no ADLS); tests use temp dirs only.

**tests/COVERAGE_MAP.md**
- [ ] Append one section `# Coverage map: unattributed-usage-breakdown` mapping every
      acceptance criterion in tasks 01–03 to node ids; criteria verified only by command
      output or doc review are listed as GAP with that reason.

## Acceptance Criteria

1. `python -m pytest tests/test_project_label.py tests/test_export_unattributed.py -q`
   passes — verification: command output.
2. Each requirement above is covered by at least one named test, and the coverage map
   lists every task 01–03 criterion — verification: command output (`pytest --collect-only -q` for the two files) plus reading the map section.
3. The pre-existing suite still passes for the neighbouring modules:
   `python -m pytest tests/test_export.py tests/test_attribute.py tests/test_invoice.py -q`
   — verification: command output.

## Files to Read

- `billing/otel/project_label.py`, `billing/otel/export.py`, `billing/otel/attribute.py`,
  `billing/otel/invoice.py`
- `tests/conftest.py` (fixtures, `_usage_row`, `seed_otlp_rows` patterns),
  `tests/test_export.py` (CSV reading helper style)
- `tests/COVERAGE_MAP.md` (format of existing sections)
- `.claude/skills/test-ladder/SKILL.md`, `.claude/skills/python-testing-patterns/SKILL.md`
- `_goals/unattributed-usage-breakdown/01-project-label.md`, `02-export-breakdown.md`,
  `03-readme-columns.md` (criteria to map)

## Files to Create / Change

- `tests/test_project_label.py` — new.
- `tests/test_export_unattributed.py` — new.
- `tests/COVERAGE_MAP.md` — append one section.

## Constraints

- Must: pytest only; outcome-verifying assertions; temp directories; deterministic data.
- Must NOT: edit product code or `conftest.py`; call real services; weaken or delete
  existing tests.

## Verification

- `python -m pytest tests/test_project_label.py tests/test_export_unattributed.py -q`
- `python -m pytest tests/test_export.py tests/test_attribute.py tests/test_invoice.py -q`
