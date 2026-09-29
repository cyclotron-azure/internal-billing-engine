# Task 02: tests

## Objective

Outcome-verifying tests for the export domain filter.

## Dependencies

- 01

```yaml
writes:
  - tests/test_export_email_filter.py
  - tests/COVERAGE_MAP.md
reads:
  - billing/otel/export.py
depends_on:
  - "01-export-domain-filter"
owner: test-writer
rewrite_semantics: whole-file   # test file is new; COVERAGE_MAP.md = append-only
eval_depth: light
```

## Requirements

- [ ] New `tests/test_export_email_filter.py` (pytest + stdlib only; `tmp_path` OtelStore; no network),
      seeding pattern as in `tests/test_export_unattributed.py`.
- [ ] Cover every Acceptance Criterion of task 01 on both CSVs (via `build_and_enqueue` reading the
      files), env var override/default/blank, unit tests of `is_allowed_user`/`allowed_domains`, raw
      `token_usage`/`cost_usage`/`session_repo_timeline` row counts unchanged after export (do not compare fabric_outbox), and kept-row totals equal to those of a store without
      the personal rows.
- [ ] Isolation (subprocess env must include `PYTHONPATH=<repo root>`; billing is not installed): every test that calls `main()` either runs it as a subprocess with `cwd=tmp_path` and an explicit
      `env=`, or in-process after `monkeypatch.chdir(tmp_path)` and `monkeypatch.setattr(billing.config, "_LOADED", False)`;
      any `.env` needed is written into `tmp_path`. No test may read the repo's real `.env`. Env vars are set/removed with
      `monkeypatch`.
- [ ] Cover `build_and_enqueue`'s printed excluded line (capsys; also N = 0) and return value.
- [ ] Cover `export.main()` via `--no-enqueue` on a store with a gmail row (CSV contents + printed excluded line), and `build(stats=...)`.
- [ ] Append a coverage-map section for this goal to `tests/COVERAGE_MAP.md` (append only).

## Acceptance Criteria

1. All new tests pass — verification: `python -m pytest -q tests/test_export_email_filter.py`
2. Each task-01 criterion maps to a named test in COVERAGE_MAP — verification: read the map
3. Full suite passes — verification: `python -m pytest -q`

## Files to Create / Change

- tests/test_export_email_filter.py
- tests/COVERAGE_MAP.md

## Constraints

- Must NOT edit product code or conftest.py.

## Verification

- `python -m pytest -q tests/test_export_email_filter.py`
