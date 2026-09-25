You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-24T00:00:00Z

## Task

This is FIX CYCLE 2 for Task 02 of the `cowork-telemetry-ingest` goal. You are a fresh agent
with no memory of prior work — this context package is fully self-contained.

Task 02's module (`billing/otel/cowork_ingest.py`) is a pure, stdlib-only OTLP payload parser.
It has already been through one full implementation pass plus one fix cycle (both by a
different agent), driven by adversarial evaluator probing (constructing malicious/malformed
inputs and running them against the actual code, not just reading tests). Two full evaluation
rounds found and the first fix cycle closed 8 issues (3 blockers, 5 major) around the core
"never raise on malformed input" contract. A SECOND adversarial pass just found 1 new blocker
and 2 new majors. Fix ALL THREE below. This module's central purpose is: never let malformed
Cowork telemetry crash parsing, and never let it corrupt a stored bill with wrong values.

### Issue A [blocker]: `sorted(metrics_seen)` crashes on mixed-type metric names

`billing/otel/cowork_ingest.py` around line 565-573, 612: when a metric's `name` field is a
hashable non-string (an int like `5`, a float like `1.5`, a bool `True`, or a tuple like
`("a",)`), it currently gets added directly to the `metrics_seen` set. The existing guard only
catches UNHASHABLE names (e.g. lists), via a `try/except TypeError` around the set insertion
itself — but a non-string, HASHABLE value inserts fine and then `sorted(metrics_seen)` blows up
later with `TypeError: '<' not supported between instances of 'int' and 'str'` when the set
contains a mix of strings and non-strings. This happens on BOTH the normal cowork-accepted path
and the rejected-service-name path (since `metrics_seen` is presumably built regardless of
whether the resource entry is accepted).

**Fix**: only ever add `str` values to `metrics_seen` — either skip non-string names entirely
(don't add them to the set) or coerce with `str(name)` before adding. Either is acceptable;
document your choice in a code comment. Add a parametrized test with metric names `5`, `1.5`,
`True`, and `("a",)`, exercised on BOTH the `service.name="cowork"` path and a rejected-service
path, asserting `parse_cowork_payload` never raises for any of them.

### Issue B [major]: string row fields can end up as list/dict/oversized-int, breaking
`CoworkStore.insert_datapoint`/`insert_cost_datapoint`

Row fields that are supposed to be plain strings (`model`, `token_type`, `repo`, `repo_raw`,
`user_email`, `user_id`, `org_id`, `query_source`, `session_id`) can currently end up holding a
non-string value if the source OTLP attribute uses an unexpected wrapper shape, because
`_attr_value` passes `boolValue` through unchecked and `intValue` has no upper bound. Reproduced
failures when calling `CoworkStore.insert_datapoint(**row)`/`insert_cost_datapoint(**row)` on
the returned row:
- `model` attribute = `{"boolValue": [1]}` → `sqlite3.ProgrammingError: Error binding
  parameter 9: type 'list' is not supported`
- Same for `type` (token_type), `repo`, with `boolValue` set to a list or dict
- `user.email` attribute = `{"intValue": "9"*30}` (a 30-digit string) →
  `OverflowError: Python int too large to convert to SQLite INTEGER`
- Same for `organization.id` with `intValue` = `str(2**64)`

**Fix**: every string-typed row field must genuinely be a `str` (or coerced to one) before the
row is returned — never a list/dict/oversized-int that would fail at SQLite bind time. Two
acceptable approaches (pick one, document your choice):
(a) Tighten `_attr_value` so any wrapper other than a genuinely bindable scalar (bounded int,
    finite float, bool, or string) is rejected/dropped at the attribute-parsing level, OR
(b) Coerce every string-typed row field to `str()` explicitly when building the row dict
    (`_base_row` or wherever row construction happens), with numeric/bool inputs converted to
    their string representation and any unbindable type (list/dict) causing that DATAPOINT to
    be rejected as `malformed_datapoint:<field>` rather than silently coerced to `"[1]"` or
    similar garbage.
Approach (b) is likely simpler and safer for a billing pipeline — a malformed `model` field
should probably be a rejection, not silently stringified into "[1]". Use your judgment but
justify it in your report.
Add tests that feed a list/dict `boolValue` and an over-64-bit `intValue` into EACH of the
affected fields, then actually call `insert_datapoint(**row)`/`insert_cost_datapoint(**row)`
against a real `CoworkStore` (not just assert on the dict shape) to prove the row is genuinely
insertable or was correctly rejected instead.

### Issue C [major]: float-formatted numeric strings silently lose precision

`billing/otel/cowork_ingest.py` around line 332-341 (`_to_whole_number` or equivalent): an
integer field parsed from a float-formatted string silently loses precision instead of being
rejected. Reproduced: `timeUnixNano="1767312000000000001.0"` is currently ACCEPTED as
`1767312000000000000` (off by 1) and `asInt="1.767312000000000001e18"` is accepted as
`1767312000000000000` — both are DIFFERENT VALUES from what was actually sent. Since a changed
`time_unix_nano` also changes the row's dedup key, this is a real correctness bug: two
different-but-truncated-to-the-same values would incorrectly dedupe against each other, or a
single correct value could be silently corrupted.

**Fix**: either (a) reject any float-formatted string for a field that expects an INTEGER
(`asInt`, `timeUnixNano`/`startTimeUnixNano`) rather than accepting it via float-to-int
truncation, or (b) if you believe accepting "3.0"-style whole-valued floats-as-strings is
legitimate, at minimum reject when the float value doesn't EXACTLY round-trip to the claimed
integer (i.e. `int(float(s)) == float(s)` is not sufficient once the value exceeds 2**53, since
float loses precision above that — you likely need to detect magnitude and either use decimal
parsing or reject outright above the safe-float-integer threshold). The safer, simpler choice
for a billing pipeline is (a): reject non-integer-formatted strings for integer fields outright.
Document your choice. Add a test showing `"1767312000000000001.0"` is REJECTED, not silently
accepted as a different, wrong value.

## Files to Read

- `_goals/cowork-telemetry-ingest/02-cowork-ingest-payload.md` — the task's Requirements and
  Acceptance Criteria (note: AC9's literal wording says a datapoint "missing timeUnixNano
  entirely" is malformed; this was already resolved by a prior orchestrator decision to KEEP
  the existing `startTimeUnixNano` fallback and only treat BOTH timestamps being absent as the
  real malformed case — this is ALREADY correctly implemented and tested; do not change it).
- `billing/otel/cowork_ingest.py` — the current, twice-fixed module. Read it FULLY before
  editing — understand `_attr_value`, `_attrs`, `_extract_datapoints`, `_get_list`,
  `_to_whole_number`, `_to_finite_float`, `_base_row`, and the existing rejection-reason
  vocabulary before adding to it.
- `tests/test_cowork_ingest.py` — the current 54 tests. Read fully; add to this file, don't
  duplicate or restructure what's already correct and passing.
- `billing/otel/cowork_store.py` — `CoworkStore.insert_datapoint`/`insert_cost_datapoint`'s
  frozen keyword-only signatures — the exact contract your row dicts must satisfy.
- `billing/otel/receiver.py` — reference only, for how the existing pipeline's `_attr_value`/
  `_attrs` work (do NOT import from it — this module must have zero dependency on
  `billing.otel.receiver`, verified by an existing AST + subprocess test in this task's own
  test file).
- `billing/otel/transcript.py` — reference for the fail-closed-per-record philosophy this
  module mirrors.

## Write fence

ONLY these two paths (unchanged from the original task):
- billing/otel/cowork_ingest.py
- tests/test_cowork_ingest.py

Do NOT modify `billing/otel/receiver.py`, `billing/otel/transcript.py`, or
`billing/otel/cowork_store.py` in any way.

## Model

requested: claude-fable-5-1 · tier: light · rotation: cycle 2 (different model line, per
this repo's fix-cycle rotation policy — model map: cycle 1 claude-sonnet-5, cycle 2
claude-fable-5-1, cycle 3 claude-opus-5)

## Rules

- Fix all three issues (A, B, C) completely — each with its own dedicated regression test(s)
  that would fail without the fix (verify this yourself: temporarily re-introduce the bug,
  confirm your new test catches it, then restore the fix — this exact technique is what the
  evaluator has used against this module twice already, so make sure your tests are equally
  sharp).
- Do not regress anything from the two prior rounds — every one of the 54 existing tests must
  still pass.
- Stdlib only.
- Run the FULL test suite (`python -m pytest tests/ -q`) before reporting completion, and
  double-check every numeric claim (test counts) against actual command output — this has been
  a recurring inaccuracy in this goal's earlier reports and evaluators check it directly.
- State any judgment calls explicitly in your report, especially your choice for issues B and C.

## Output

A completion report: what you changed (exact file paths and line references, verified live via
grep/read immediately before writing the report — not from memory), how each of issues A/B/C is
fixed and tested, the full output of `python -m pytest tests/ -q`, `git diff` confirmation that
`receiver.py`/`transcript.py`/`cowork_store.py` are untouched, and any judgment calls. End with
a `### Footprint` section: files_read count/approx chars, commands_run count.
