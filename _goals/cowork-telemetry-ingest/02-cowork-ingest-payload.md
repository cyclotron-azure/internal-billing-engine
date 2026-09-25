# Task 02: Cowork OTLP payload parsing + fail-closed validation

## Objective

A pure, stdlib-only module, `billing/otel/cowork_ingest.py`, that takes a parsed OTLP/JSON
`ExportMetricsServiceRequest` dict and returns which rows to store versus which to reject —
with no I/O and no store access, mirroring how `transcript.py` is a pure payload-contract
module that `receiver.py` calls into. This freezes the mapping tasks 03 (live receiver) and
04 (reporting) both depend on.

## Dependencies

- 00-test-scaffold
- 01-cowork-store-schema

```yaml
# --- task ownership contract ---
writes:
  - billing/otel/cowork_ingest.py
  - tests/test_cowork_ingest.py
depends_on:
  - "00-test-scaffold"
  - "01-cowork-store-schema"
owner: implementer
rewrite_semantics: whole-file
eval_depth: full   # reason: tasks 03 (live receiver) and 04 (reporting) both consume this
                    # module's output shape directly; a defect in the parse/rejection contract
                    # here propagates silently into both consumers.
reads:
  - billing/otel/receiver.py
  - billing/otel/cowork_store.py
  - billing/otel/transcript.py
```

## Requirements (exhaustive — the evaluator verifies every item)

- [ ] `KNOWN_SERVICE_NAME = "cowork"` — the only `service.name` resource-attribute value this
      module accepts. Anything else (including absent) is rejected — this module is Cowork-
      only; `receiver.py`'s existing `claude_code` handling is untouched and unrelated.
- [ ] `TOKEN_METRIC = "claude_code.token.usage"` and `COST_METRIC = "claude_code.cost.usage"`
      — the two metric names this module recognizes, per the goal's documented assumption
      that Cowork reuses Claude Code's metric names and is disambiguated purely by
      `service.name`. Define them as module constants (not copied magic strings) so the
      assumption is visible and changeable in one place if real traffic proves it wrong.
- [ ] `parse_cowork_payload(payload: dict) -> dict` that:
      - Reads `resourceMetrics[].resource.attributes` for `service.name`. If a
        `resourceMetrics` entry's `service.name` is not exactly `KNOWN_SERVICE_NAME`, every
        metric under that entry is skipped and counted as rejected (reason
        `"unrecognized_service_name:<value or 'absent'>"`) — never guessed, never stored.
      - For an entry with `service.name == "cowork"`, iterates its metrics: a datapoint under
        `TOKEN_METRIC` or `COST_METRIC` is accepted and mapped to a row dict ready for
        `CoworkStore.insert_datapoint`/`insert_cost_datapoint` (matching that method's keyword
        signature exactly — read `cowork_store.py` for the frozen contract). A datapoint under
        any OTHER metric name is rejected with reason `"unrecognized_metric:<name>"`.
      - Returns a dict shaped like `receiver.py`'s `ingest_metrics_payload` result, but
        additionally carrying rejections, e.g.:
        `{"token_rows": [...], "cost_rows": [...], "metrics_seen": [...],
          "rejections": [{"reason": str, "detail": str}, ...]}`
        — the exact key names are this task's to freeze; document them in the module
        docstring since task 03 and task 04 both consume this shape.
      - Never raises on a malformed individual `resourceMetrics`/`scopeMetrics`/`metrics`
        entry (missing keys, wrong types) — such an entry is rejected with a reason string,
        same fail-closed-per-record philosophy as `transcript.py`'s `validate_batch`. It MAY
        raise on a payload that isn't even a dict at the top level (an unusable envelope) —
        mirror `transcript.py`'s own distinction between envelope-level and record-level
        failures.
      - **Do NOT import `billing.otel.receiver`.** Importing that module executes
        `load_env()` at import time and populates the module-level `AUTH_TOKEN` global as a
        side effect — coupling this module's behavior to the existing pipeline's environment
        and secrets handling, which the goal's isolation requirement forbids even as an
        incidental side effect. Instead, duplicate the small amount of pure parsing logic
        needed (`_attr_value`, `_attrs`, `_datapoints` — each is a few lines, read them from
        `receiver.py` for reference only) directly inside `cowork_ingest.py`. This is
        deliberate, minor duplication in exchange for zero coupling to a file this goal must
        never touch or depend on the internals of.
      - `session_id` handling matches `receiver.py`'s `_common()` convention: coerce to
        `str()`, and only a genuinely absent value maps to a sentinel — do not collapse a
        falsy-but-present value (`0`, `""`) into that sentinel (this is a known prior defect
        in the codebase's own history — see the residual-fix comments in `receiver.py`'s
        `_common` — do not reintroduce it here).
      - `terminal.type` MAY be read off the resource attributes for a rejection message or
        debug purposes, but is NOT included in the row dicts returned for storage —
        `cowork_store.py`'s `insert_datapoint`/`insert_cost_datapoint` signatures (task 01)
        have no field for it, and this task's row dicts must match those signatures exactly.
        `service.name` alone gates acceptance, matching the goal's documented attribution
        rule.
      - **A malformed datapoint value is a per-record rejection, never an unhandled
        exception.** A datapoint whose `asInt`/`asDouble` is missing, non-numeric, or of an
        unexpected JSON type, or whose `timeUnixNano`/`startTimeUnixNano` is missing, is
        rejected with reason `"malformed_datapoint:<field>"` and does not abort parsing the
        rest of the payload — mirroring the exact class of defect `receiver.py`'s own history
        documents around `_common`/`ingest_metrics_payload` (a client sending an unexpected
        value type for a numeric-looking field is a real, previously-reproduced failure mode
        in this codebase, not a hypothetical).

## Acceptance Criteria

1. A payload with one `resourceMetrics` entry tagged `service.name="cowork"`, carrying one
   `claude_code.token.usage` datapoint and one `claude_code.cost.usage` datapoint, produces
   one token row and one cost row, zero rejections — verification: unit test.
2. The identical payload with `service.name="claude-code"` instead (the CLI's real,
   hyphenated value per `billing/otel/sample_payload.py`) produces zero token/cost rows and
   one rejection per metric, reason prefixed `unrecognized_service_name` — verification: unit
   test.
3. The identical payload with `service.name` absent entirely behaves the same as case 2 (not
   silently accepted) — verification: unit test.
4. A payload with `service.name="cowork"` but a datapoint under `some.other.metric` produces
   a rejection reason prefixed `unrecognized_metric`, and does not raise — verification: unit
   test.
5. A payload that is a non-dict (e.g. a bare list or `None`) either raises a documented
   exception type or returns an envelope-level rejection — whichever this task's docstring
   commits to — verification: unit test asserting that documented behavior specifically.
6. `session_id=0` and `session_id=""` (present-but-falsy) are preserved as their own string
   values, not collapsed into the same sentinel as a genuinely absent `session_id` —
   verification: unit test with three payloads (falsy-int, falsy-string, absent) asserting
   three distinct outcomes.
7. `git diff -- billing/otel/receiver.py billing/otel/transcript.py` is empty after this
   task — verification: command output.
8. `cowork_ingest.py` contains no `import` of, or `from`, `billing.otel.receiver` — verification:
   grep/AST check in a unit test.
9. A `service.name="cowork"` payload with a token datapoint whose `asInt` is a string like
   `"not-a-number"`, and a separate payload with a datapoint missing `timeUnixNano` AND
   `startTimeUnixNano` (both absent), each produce a `malformed_datapoint:*` rejection and zero
   raised exceptions, while any OTHER valid datapoint in the same payload is still accepted —
   verification: unit test.
   **Resolution recorded during Phase 4 implementation (fix cycle 1, task 02):** the original
   wording above ("missing `timeUnixNano` entirely") was ambiguous against `receiver.py`'s own
   existing convention (`dp.get("timeUnixNano") or dp.get("startTimeUnixNano") or 0`). Resolved
   by the orchestrator: a datapoint with `timeUnixNano` absent but `startTimeUnixNano` present
   is ACCEPTED via that same fallback (matches existing pipeline behavior, tested explicitly,
   not merely by omission); a datapoint with BOTH absent is the real "missing entirely" case
   this criterion means, and IS rejected as `malformed_datapoint:time_unix_nano` rather than
   silently defaulting to 0. Both branches are tested in `tests/test_cowork_ingest.py`.

## Files to Read

- `billing/otel/receiver.py` — `_attrs`, `_attr_value`, `_datapoints`, `_common`, and
  `ingest_metrics_payload` for the wire shape and the `session_id`-sentinel defect history
  (read the surrounding comments — they document a real, previously-shipped bug this task
  must not reintroduce). Read-only.
- `billing/otel/cowork_store.py` — the frozen `insert_datapoint`/`insert_cost_datapoint`
  keyword signatures this module's row dicts must match exactly.
- `billing/otel/transcript.py` — the pure-module, fail-closed-per-record pattern to mirror
  (`validate_batch`'s envelope-vs-record distinction, `REJECTION_REASONS` convention).

## Files to Create / Change

- `billing/otel/cowork_ingest.py`
- `tests/test_cowork_ingest.py`

## Constraints

- Must: stay pure — no file I/O, no store access, no network, from this module.
- Must: stdlib only.
- Must: fail closed per-record; never let one malformed metric/datapoint abort the whole
  payload's parsing.
- Must NOT: modify `billing/otel/receiver.py` or `billing/otel/transcript.py`.
- Must NOT: import `billing.otel.receiver` (see Requirements — `load_env()` import-time side
  effect). Duplicate the few lines of pure parsing logic needed instead.
- Must NOT: accept any `service.name` other than exactly `"cowork"`.

## Verification

- Targeted test command: `python -m pytest tests/test_cowork_ingest.py -q`
