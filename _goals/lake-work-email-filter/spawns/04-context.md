You are the test-writer subagent. Read: .claude/agents/test-writer.md

CURRENT_DATETIME: 2026-09-29T13:10:00Z

## Task
Execute task 02: _goals/lake-work-email-filter/02-tests.md (read it, goal.md and 01-export-domain-filter.md in full). Skills: test-ladder (rungs 1-2 only), python-testing-patterns.

## Requirements
All requirements/ACs in the task file. Task 01 is implemented in billing/otel/export.py (allowed_domains, is_allowed_user, build(store, markup, allowed_domains=None, stats=None), _print_excluded, main() with load_env, build_and_enqueue printing `[export] excluded N group(s) outside <domains>`).
Evaluator notes to respect: stats["excluded_groups"] counts distinct (day, resolved_repo, RAW model, raw user_email) groups, once across cost_usage and token_usage; a no-@ address is excluded but adds no domain to excluded_domains; main() calls load_env() after parse_args. Subprocess tests need PYTHONPATH=<repo root> and cwd=tmp_path with a controlled env; never read the repo .env; reset billing.config._LOADED for in-process tests.

## Files to Read
_goals/lake-work-email-filter/*.md, billing/otel/export.py, billing/config.py, tests/test_export_unattributed.py (seeding pattern), tests/conftest.py, tests/COVERAGE_MAP.md (tail, for format).

## Write fence
tests/test_export_email_filter.py, tests/COVERAGE_MAP.md (append only).

## Model
requested: claude-sonnet-5 · tier: light · rotation: n/a

## Rules
pytest + stdlib only; tmp_path stores; no network; do not edit product code or conftest.py. Run `python -m pytest -q tests/test_export_email_filter.py` and the two existing export test files; do not run the full suite (the orchestrator does).

## Output
Report: tests written mapped to ACs, results, deviations, `### Footprint` block.
