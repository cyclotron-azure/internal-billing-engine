You are the evaluator subagent. Read: .claude/agents/evaluator.md

CURRENT_DATETIME: 2026-09-24T00:00:00Z

## Task

Evaluate Task 00 ("Test scaffold + pre-change isolation baseline") of the
`cowork-telemetry-ingest` goal, per `.claude/skills/task-criteria/SKILL.md`. This is a Phase 4
task-level evaluation (eval_depth: full). The implementer (test-writer) reports the task
complete: 444 tests passing across the full suite, a new golden baseline captured, and two
draft bugs (a `Path.read_text(newline=...)` incompatibility, a `sqlite3.Row` vs tuple
comparison mismatch) plus one real determinism-leak bug (mishandled `pytest.MonkeyPatch`
lifecycle across two captures, which leaked a fake `AnalyticsClient`/`_now` into unrelated
tests) found and fixed during the implementer's OWN verification pass.

Verify every checkbox in the task file's Requirements and every numbered item in its
Acceptance Criteria is actually satisfied — read the actual files the implementer wrote, run
the tests yourself, don't just trust the report. Pay particular attention to:
- The two determinism traps this task exists specifically to close (see the task file's
  Requirements): `otel_store._now()` frozen for EVERY capture (not just some), and each of the
  three `ingest_metrics_payload` captures run against its own FRESH store (never shared,
  because `dp_key` excludes `service.name`).
- Whether the golden baseline is genuinely LF-only and reproducible.
- Whether `tests/conftest.py`/`tests/test_conftest.py` were genuinely extended (not clobbered)
  — check that pre-existing fixtures/tests from prior goals still exist and still pass.
- Whether the implementer's claimed fix for the monkeypatch-leak bug is actually correct and
  the full suite is clean when run multiple times / in different orders (the implementer
  claims to have verified this — confirm it yourself, don't take it on faith, since this is
  exactly the kind of bug that can look fixed while still being fragile).
- The judgment call to put `capture_cowork_isolation_baseline` in `conftest.py` rather than
  `test_conftest.py` (for task 05 reuse) — is this consistent with the existing codebase's
  precedent (`seed_otlp_rows`) as claimed?
- No file under `billing/`, `deploy/`, or `client-package/` was touched (this task's write
  fence is tests-only).

## Files to Read

- `_goals/cowork-telemetry-ingest/00-test-scaffold.md` — the task's Requirements/Acceptance
  Criteria to check against.
- `_goals/cowork-telemetry-ingest/spawns/04-report.md` — the implementer's completion report.
- `tests/conftest.py`, `tests/test_conftest.py` — the actual changes (diff against what you'd
  expect prior content to look like; check nothing pre-existing was removed).
- `tests/golden/cowork_isolation_baseline.txt`, `tests/golden/cowork_isolation_README.md` —
  the new golden artifacts.
- `tests/golden/README.md` — the precedent this task was told to mirror.
- `billing/otel/otel_store.py`, `billing/reconcile.py`, `billing/otel/receiver.py` — ground
  truth for checking the captured baseline's accuracy.

## Write fence

None — evaluator produces a verdict only, writes nothing. (If you find a trivial, unambiguous
fix is needed and the task-criteria skill's process allows you to note it precisely rather
than requiring a fix cycle, follow that skill's own process.)

## Model

requested: claude-opus-5 · tier: frontier · rotation: n/a

## Rules

- Run `python -m pytest tests/ -q` yourself (and a second time, and in reverse file order if
  practical) rather than trusting the reported pass count.
- Verdict must be exactly one of PASS, PASS (with notes), NEEDS FIXES, REJECT, per
  `.claude/skills/task-criteria/SKILL.md`'s format.
- Flag `destructive`/`security`/`infra`-tagged issues distinctly if any exist (none expected
  for a tests-only task, but check).

## Output

Verdict with itemized reasoning against the task file's Requirements and Acceptance Criteria.
