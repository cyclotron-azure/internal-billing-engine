You are the evaluator subagent. Read: .claude/agents/evaluator.md

CURRENT_DATETIME: 2026-09-24T00:00:00Z

## Task

Evaluate Task 02 ("Cowork OTLP payload parsing + fail-closed validation") of the
`cowork-telemetry-ingest` goal, per `.claude/skills/task-criteria/SKILL.md` (eval_depth: full —
tasks 03/04 both consume this module's output shape directly). The implementer (light tier)
reports 492 tests passing (full suite), 23 new tests, and claims: no import of
`billing.otel.receiver`, `git diff` on `receiver.py`/`transcript.py` empty, deliberate
non-normalization of `repo`/`repo_raw` (left raw, normalization deferred to
`cowork_attribute.py` at report time).

Given this goal's track record so far (task 01 needed a fix cycle after mutation testing
exposed tests that passed even with bugs re-injected), don't just read the new test file —
actually try to break the implementation:
- Try constructing a payload where `service.name` is present but is some falsy-but-not-absent
  value (e.g. an empty string `""` or `0`) — does it correctly get rejected as "not cowork", or
  does it accidentally get treated as absent/pass some truthy check incorrectly?
- Confirm the "no import of `billing.otel.receiver`" claim is actually enforced (not just
  tested by a fragile string check) — try adding a local `import billing.otel.receiver` inside
  the module and see if the implementer's own AST-based test would actually catch it, or if
  it's checking something too narrow.
- Check the malformed-datapoint handling against a genuinely adversarial input: a datapoint
  whose `asInt` is a list, a dict, `NaN`-as-string, or `float('inf')`-shaped values — does
  `malformed_datapoint:*` fire cleanly, or does something slip through as a huge/garbage stored
  value instead of being rejected?
- Verify the row dicts returned for `token_rows`/`cost_rows` EXACTLY match
  `CoworkStore.insert_datapoint`/`insert_cost_datapoint`'s keyword-only signatures (frozen in
  task 01) — try actually calling those store methods with the returned dicts via `**row` and
  confirm it works with zero KeyError/TypeError, for both a normal accepted payload and any
  edge case you construct.
- Check the `unrecognized_service_name` rejection reason format is genuinely useful/matches the
  documented pattern for a `None`/absent case vs. an actual wrong string.

## Files to Read

- `_goals/cowork-telemetry-ingest/02-cowork-ingest-payload.md` — the task's Requirements/
  Acceptance Criteria to check against.
- `_goals/cowork-telemetry-ingest/spawns/10-report.md` — the implementer's completion report.
- `billing/otel/cowork_ingest.py` — the actual new module.
- `tests/test_cowork_ingest.py` — the actual new tests.
- `billing/otel/cowork_store.py` — task 01's frozen `insert_datapoint`/`insert_cost_datapoint`
  signatures to check row dicts against.
- `billing/otel/receiver.py`, `billing/otel/transcript.py` — ground truth for the patterns being
  mirrored, and to confirm no diff.

## Write fence

None — evaluator produces a verdict only, writes nothing.

## Model

requested: claude-opus-5 · tier: frontier · rotation: n/a

## Rules

- Actually run adversarial inputs against `parse_cowork_payload` yourself (a scratch script is
  fine) rather than only reading the test file — this goal's pattern so far is that tests can
  look complete while missing the actual discriminating case.
- Run `python -m pytest tests/test_cowork_ingest.py -v` and the full `python -m pytest tests/ -q`
  yourself; double-check any numeric claim against actual output.
- Verdict must be exactly one of PASS, PASS (with notes), NEEDS FIXES, REJECT.

## Output

Verdict with itemized reasoning against the task file's Requirements and Acceptance Criteria.
