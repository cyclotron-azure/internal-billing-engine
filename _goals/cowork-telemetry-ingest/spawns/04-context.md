You are the test-writer subagent. Read: .claude/agents/test-writer.md

CURRENT_DATETIME: 2026-09-24T00:00:00Z

## Task

Execute Task 00 of the `cowork-telemetry-ingest` goal in full: read
`_goals/cowork-telemetry-ingest/00-test-scaffold.md` (this IS your task file — treat every
checkbox in its Requirements and every item in its Acceptance Criteria as mandatory, exhaustive
requirements, not suggestions) and implement it completely.

This task runs FIRST, before any production file in this goal exists. Its two jobs: (1) add
new, genuinely-needed test fixtures to the EXISTING `tests/conftest.py`/`tests/test_conftest.py`
(read them fully first — they already contain real fixtures like `seed_otlp_rows`/
`seeded_otlp_db_path` from prior goals; extend, never clobber), and (2) capture a golden,
byte-exact baseline of the CURRENT, unmodified `claude_code` pipeline's behavior, so a later
task (05) can prove the rest of this goal never changed it.

Read `tests/golden/README.md` and `tests/golden/bill_otlp_baseline.txt` in full — they are the
EXACT precedent this task's own golden capture must follow: the `redirect_stdout`/
`newline=""` invocation pattern, the LF-only file discipline, the `cp1252`/`⚠` CLI-equivalence
caveat, and the determinism write-up style. Do not reinvent this pattern; replicate it.

Two determinism traps are called out explicitly in the task file's Requirements — read them
carefully, they were found by actually running code during this goal's planning review:
1. `otel_store._now()` (called by `_ensure_dedupe_epoch` on first insert) must be frozen via
   monkeypatch for EVERY capture in this task, not just one of them.
2. Each of the three `ingest_metrics_payload` captures (for `service.name="claude-code"`,
   absent, and `"cowork"`) MUST run against its own fresh, empty `OtelStore` — `dp_key` does
   NOT include `service.name`, so sharing a store between captures makes the `"cowork"` one
   look like a duplicate and hides the exact leak this capture exists to record.

## Files to Read

Everything listed in `_goals/cowork-telemetry-ingest/00-test-scaffold.md`'s own "Files to
Read" section, plus:
- `_goals/cowork-telemetry-ingest/goal.md` — full goal context, Success Criteria, and the
  goal's hard isolation constraint (no existing file may change).
- `tests/conftest.py`, `tests/test_conftest.py` — read IN FULL before writing anything.
- `tests/golden/README.md`, `tests/golden/bill_otlp_baseline.txt` — the precedent to mirror.

## Write fence

ONLY these paths (per the task file's ownership contract):
- tests/conftest.py (targeted-insertion — add to it, don't restructure)
- tests/test_conftest.py (targeted-insertion — add to it, don't restructure)
- tests/golden/cowork_isolation_baseline.txt (new file)
- tests/golden/cowork_isolation_README.md (new file)

Do NOT create, modify, or touch any file under `billing/`, `deploy/`, or `client-package/`.
This task is tests-only, full stop.

## Model

requested: claude-sonnet-5 · tier: light · rotation: cycle 1 (normal)

## Rules

- Every checkbox in the task file's "Requirements" section is mandatory.
- Every numbered item in the task file's "Acceptance Criteria" section must be satisfiable and
  actually verified by you before you report completion — run the tests yourself.
- No dependency beyond `pytest` (already installed; do not `pip install` anything).
- If you find the existing `tests/conftest.py`/`tests/test_conftest.py` already has something
  equivalent to what this task asks for, REUSE it and say so in your report — do not build a
  parallel, near-duplicate fixture.
- If anything in the task file is ambiguous or you must make a judgment call, state the call
  and your reasoning explicitly in your report rather than silently picking one.

## Output

A completion report: what you created/changed (exact file paths), how each Requirement and
Acceptance Criterion is satisfied (point to the specific test/fixture), the full output of
`python -m pytest tests/ -q`, and any judgment calls you made. End with a `### Footprint`
section: files_read count/approx chars, commands_run count.
