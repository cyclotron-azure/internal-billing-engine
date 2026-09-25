You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-24T00:00:00Z

## Task

Execute Task 01 of the `cowork-telemetry-ingest` goal in full: read
`_goals/cowork-telemetry-ingest/01-cowork-store-schema.md` (this IS your task file — treat
every checkbox in its Requirements and every item in its Acceptance Criteria as mandatory) and
implement it completely.

This is the CONTRACT task for the whole goal — every later task (02, 03, 04) consumes the
schema, insert signatures, `resolve_repo`, and `otel_db_reachable` contracts you freeze here
without re-deriving them. Two real bugs were found and fixed during this goal's planning
review (Phase 3, 3 evaluation cycles) — both are now explicit, mandatory requirements in the
task file, read them carefully:
1. The read-only SQLite URI MUST be built as `Path(path).resolve().as_uri() + "?mode=ro"`,
   never `f"file:{path}?mode=ro"` with the raw path string — the naive form opens the database
   READ-WRITE (and can create a file) if the path contains `#` or `?`.
2. `otel_db_reachable`'s probe MUST check for the `session_repo_timeline` table specifically
   (e.g. `SELECT 1 FROM session_repo_timeline LIMIT 1`), never a bare `SELECT 1` — a bare
   `SELECT 1` succeeds against ANY valid SQLite file, including this goal's own `cowork.db`
   sitting right next to `otel.db`, which is the single most likely wrong-path mistake.

Task 00 (already complete, PASS) built fixtures you can and should reuse:
`tests/conftest.py`'s `seeded_otlp_db_path` fixture (an existing-otel.db-shaped fixture with a
`session_repo_timeline` row plus matching `token_usage`/`cost_usage` rows for the same session
— `COWORK_LOOKUP_SESSION_ID` names that session id) and `cowork_metrics_payload` (a synthetic
Cowork OTLP payload fixture). Read `tests/conftest.py` in full before writing your own tests —
do not duplicate what's already there.

## Files to Read

Everything listed in `_goals/cowork-telemetry-ingest/01-cowork-store-schema.md`'s own "Files
to Read" section, plus:
- `_goals/cowork-telemetry-ingest/goal.md` — full goal context and the hard isolation
  constraint (no existing file may change).
- `tests/conftest.py` — read in full; reuse `seeded_otlp_db_path`, `COWORK_LOOKUP_SESSION_ID`,
  `cowork_metrics_payload`, `cowork_db_path` rather than rebuilding equivalents.

## Write fence

ONLY these paths (per the task file's ownership contract):
- billing/otel/cowork_store.py (new file)
- billing/otel/cowork_attribute.py (new file)
- tests/test_cowork_store.py (new file)
- tests/test_cowork_attribute.py (new file)

Do NOT modify `billing/otel/otel_store.py` or `billing/otel/attribute.py` in any way — this
task's Acceptance Criteria includes `git diff` on both being empty.

## Model

requested: claude-sonnet-5 · tier: light · rotation: cycle 1 (normal)

## Rules

- Every checkbox in the task file's "Requirements" section is mandatory.
- Every numbered/lettered item in the task file's "Acceptance Criteria" section (including the
  3b, 5b, 5c, 5d sub-items) must be satisfiable and actually verified by you before you report
  completion — write the test, run it, confirm it passes.
- Stdlib only. No third-party import.
- Run the FULL test suite (`python -m pytest tests/ -q`), not just your new files, before
  reporting completion — confirm no regression anywhere.
- If anything in the task file is ambiguous, state the judgment call and your reasoning
  explicitly in your report.

## Output

A completion report: what you created (exact file paths), how each Requirement and each
Acceptance Criterion is satisfied (point to the specific test), the full output of
`python -m pytest tests/ -q`, and any judgment calls. Double-check every numeric claim
(test counts, etc.) against what you actually ran before writing it — a previous task's
report was sent back for exactly this kind of inaccuracy. End with a `### Footprint` section:
files_read count/approx chars, commands_run count.
