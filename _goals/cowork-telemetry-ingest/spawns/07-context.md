You are the evaluator subagent. Read: .claude/agents/evaluator.md

CURRENT_DATETIME: 2026-09-24T00:00:00Z

## Task

Evaluate Task 01 ("Cowork store schema + read-only repo-attribution lookup") of the
`cowork-telemetry-ingest` goal, per `.claude/skills/task-criteria/SKILL.md`. This is the
CONTRACT task for the whole goal (eval_depth: full) — every later task depends on what's frozen
here, so defects here propagate silently into tasks 02-04. The implementer (light tier) reports
462 tests passing (full suite), 18 new tests across two new files, and `git diff` on
`otel_store.py`/`attribute.py` empty.

Two specific bugs were found during Phase 3 planning review (by actually running code) and are
now hard requirements — verify BOTH are genuinely fixed, don't just trust the report's claim:
1. The read-only URI must be `Path(path).resolve().as_uri() + "?mode=ro"`, never
   `f"file:{path}?mode=ro"` — the naive form opens read-write (and can create a file) when the
   path contains `#` or `?`. There should be a regression test with `#` in the path.
2. `otel_db_reachable` must check for the `session_repo_timeline` TABLE specifically, never a
   bare `SELECT 1` — a bare `SELECT 1` succeeds against ANY valid SQLite file (e.g. the goal's
   own `cowork.db`), which is exactly the wrong-path case this function exists to catch. There
   should be a test proving `otel_db_reachable` returns `False` against a valid SQLite file that
   lacks that table (not just against a nonexistent path).

Also specifically check the implementer's stated judgment call: `cowork_dp_key` is a wholly
local/independent implementation, not importing `otel_store`'s dp_key logic. Is this consistent
with the task file's actual requirement, or an overcorrection?

Check the exact `insert_datapoint`/`insert_cost_datapoint` signatures against what the task
file froze verbatim — no more fields, no fewer.

Check `CoworkStore`'s connection is genuinely on a public `self.db` attribute (task 03 will
call `store.db.rollback()` directly — if this attribute doesn't exist or is named/spelled
differently, task 03 breaks on a contract it was told was frozen).

## Files to Read

- `_goals/cowork-telemetry-ingest/01-cowork-store-schema.md` — the task's Requirements/
  Acceptance Criteria (including 3b, 5b, 5c, 5d) to check against.
- `_goals/cowork-telemetry-ingest/spawns/06-report.md` — the implementer's completion report.
- `billing/otel/cowork_store.py`, `billing/otel/cowork_attribute.py` — the actual new code.
- `tests/test_cowork_store.py`, `tests/test_cowork_attribute.py` — the actual new tests; read
  them, don't just count them.
- `billing/otel/otel_store.py`, `billing/otel/attribute.py`, `billing/otel/normalize.py` —
  ground truth for what's being mirrored/frozen.
- `tests/conftest.py` — confirm the claimed reused fixtures (`cowork_db_path`,
  `seeded_otlp_db_path`, `COWORK_LOOKUP_SESSION_ID`) actually exist as described.

## Write fence

None — evaluator produces a verdict only, writes nothing.

## Model

requested: claude-opus-5 · tier: frontier · rotation: n/a

## Rules

- Run `python -m pytest tests/test_cowork_store.py tests/test_cowork_attribute.py -v` and the
  full `python -m pytest tests/ -q` yourself.
- Actually exercise the two named bug-fix requirements yourself if practical (e.g. construct a
  `#`-containing path and confirm read-only holds; construct a valid SQLite file without
  `session_repo_timeline` and confirm `otel_db_reachable` returns `False`) rather than only
  reading the test code — this contract task's correctness is unusually high-stakes for the
  rest of the goal.
- Verdict must be exactly one of PASS, PASS (with notes), NEEDS FIXES, REJECT.
- Double-check any numeric claim in the report (test counts) against actual output — a prior
  task in this goal was sent back for exactly a wrong test count.

## Output

Verdict with itemized reasoning against the task file's Requirements and Acceptance Criteria.
