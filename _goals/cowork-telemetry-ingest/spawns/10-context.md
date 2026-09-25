You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-24T00:00:00Z

## Task

Execute Task 02 of the `cowork-telemetry-ingest` goal in full: read
`_goals/cowork-telemetry-ingest/02-cowork-ingest-payload.md` (this IS your task file — treat
every checkbox in its Requirements and every item in its Acceptance Criteria as mandatory) and
implement it completely.

This is a pure, stdlib-only payload-parsing module with NO I/O and NO store access — it takes a
parsed OTLP/JSON dict and returns which rows to store vs. which to reject. Tasks 03 (live
receiver) and 04 (reporting) both consume its output shape directly, so the exact key names in
its return dict matter — document them clearly in the module docstring.

Task 01 (already complete, PASS with notes) froze these exact keyword-only signatures your row
dicts must match with NO extra/missing fields:
`CoworkStore.insert_datapoint(*, session_id, repo, repo_raw, user_email, user_id, org_id,
model, token_type, query_source, tokens, time_unix_nano)` and
`CoworkStore.insert_cost_datapoint(*, session_id, repo, repo_raw, user_email, user_id, org_id,
model, query_source, cost_usd, time_unix_nano)` — read `billing/otel/cowork_store.py` to
confirm this yourself rather than trusting this summary.

**Critical constraint, found the hard way during this goal's planning review**: do NOT import
`billing.otel.receiver` for ANY reason, even to reuse its small parsing helpers
(`_attr_value`/`_attrs`/`_datapoints`) — importing that module executes `load_env()` and
populates a module-level `AUTH_TOKEN` global as a side effect, silently coupling this module's
behavior to the existing pipeline's environment. Duplicate the few lines of pure parsing logic
needed instead (read `receiver.py` for reference, but write your own local copies).

Read the task file's "malformed datapoint" requirement carefully — a datapoint with a
non-numeric `asInt`/missing `timeUnixNano` must become a per-record rejection, never an
unhandled exception, mirroring `receiver.py`'s and `transcript.py`'s own documented history of
exactly this class of defect.

## Files to Read

Everything listed in `_goals/cowork-telemetry-ingest/02-cowork-ingest-payload.md`'s own "Files
to Read" section, plus:
- `_goals/cowork-telemetry-ingest/goal.md` — full goal context and hard isolation constraint.
- `billing/otel/cowork_store.py` — task 01's frozen contract (read it directly, don't rely on
  the summary above).
- `tests/conftest.py` — `cowork_metrics_payload`/`build_cowork_metrics_payload` fixtures from
  task 00 you should reuse rather than duplicate.

## Write fence

ONLY these paths:
- billing/otel/cowork_ingest.py (new file)
- tests/test_cowork_ingest.py (new file)

Do NOT modify `billing/otel/receiver.py` or `billing/otel/transcript.py` in any way — the task
file's Acceptance Criteria includes `git diff` on both being empty, AND a grep/AST check that
`cowork_ingest.py` contains no import of `billing.otel.receiver`.

## Model

requested: claude-sonnet-5 · tier: light · rotation: cycle 1 (normal)

## Rules

- Every checkbox in the task file's "Requirements" section is mandatory, including all 9
  numbered Acceptance Criteria (the 9th specifically checks the malformed-datapoint rejection
  path).
- Stdlib only.
- Run the FULL test suite (`python -m pytest tests/ -q`) before reporting completion, and
  double-check your reported test counts against actual output — prior tasks in this goal were
  sent back for exactly this kind of inaccuracy.
- State any judgment calls explicitly in your report.

## Output

A completion report: what you created, how each Requirement/Acceptance Criterion is satisfied
(point to the specific test), the full output of `python -m pytest tests/ -q`, and judgment
calls. Verify every numeric claim against actual command output before writing it. End with a
`### Footprint` section.
