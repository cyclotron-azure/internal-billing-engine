**Model (self-reported)**: claude-sonnet-5

## Task Complete: Task 02 -- Cowork OTLP payload parsing + fail-closed validation

### Requirements checklist
- [x] KNOWN_SERVICE_NAME = "cowork" module constant -- cowork_ingest.py:60
- [x] TOKEN_METRIC/COST_METRIC module constants -- cowork_ingest.py:67-68
- [x] parse_cowork_payload(payload: dict) -> dict implemented -- cowork_ingest.py:263
- [x] Unrecognized/absent service.name -> per-metric rejection unrecognized_service_name:<value|absent>
- [x] cowork service + recognized metric -> row dict matching insert_datapoint/insert_cost_datapoint exactly
- [x] Unrecognized metric name -> unrecognized_metric:<name>, no raise
- [x] Return shape {token_rows, cost_rows, metrics_seen, rejections} documented
- [x] Never raises on malformed per-record entries; raises only on non-dict envelope (TypeError)
- [x] No import of billing.otel.receiver; local copies of _attr_value/_attrs/_datapoints -- verified by AST test
- [x] session_id sentinel handling: falsy-but-present preserved distinctly from absent
- [x] terminal.type never in returned rows
- [x] Malformed datapoint (non-numeric asInt/asDouble, missing timeUnixNano) -> malformed_datapoint:<field> rejection, sibling data still accepted

### Acceptance Criteria (1-9) all covered by dedicated tests (see full detail in notification).

### Files changed
- billing/otel/cowork_ingest.py -- new, pure stdlib module
- tests/test_cowork_ingest.py -- new, 23 tests

### Verification
- python -m pytest tests/test_cowork_ingest.py -v -> 23 passed
- python -m pytest tests/ -q -> 492 passed (full suite)
- git diff -- billing/otel/receiver.py billing/otel/transcript.py -> empty
- git status --porcelain -> only the 2 new files from this task

### Notes for the evaluator
- repo/repo_raw are NOT normalized here (no normalize_remote call) -- deliberate, since resolution happens later at report time via cowork_attribute.py; documented in module docstring, differs from receiver.py's _common which normalizes at ingest.
- Rejection shape {"reason": str, "detail": str}; reason carries the full matchable prefix+suffix string, detail carries non-sensitive debug context only.
- unrecognized_service_name is one rejection per metric under the mismatched resource entry, not per-datapoint, per the requirement's literal wording.
- Malformed envelope entries (non-dict resourceMetrics/scopeMetrics/metrics list entries) get their own reason strings, not explicitly required but consistent with fail-closed philosophy.
- Both AST-based and textual checks included for the no-import-of-receiver requirement (AC8).

### Footprint
files_read: 6 (~62,000 chars)
commands_run: 4
