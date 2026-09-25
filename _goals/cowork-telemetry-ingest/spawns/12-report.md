Fix cycle 1 for task 02. All 8 issues (3 blockers, 5 major) addressed:

1-3 (never-raise + overflow + NaN/Infinity): defensive guards added at every attribute/value
extraction point (_attr_value, _attrs, _extract_datapoints), new _to_whole_number/
_to_finite_float parsers catching (TypeError, ValueError, OverflowError) plus math.isfinite
checks. Verified via wire-level json.loads("Infinity")/json.loads("NaN") tests, not just
Python-level float('inf').
4 (bound-checking before return): SQLITE_INT64_MAX / MAX_TIME_UNIX_NANO bounds added; oversized
values rejected as malformed rather than returned unusable. Discovered and documented a
Windows-specific datetime.fromtimestamp ceiling (~year 3001) while choosing the timestamp
bound. Verified via real CoworkStore inserts at the boundary.
5 (AC8 test too narrow): AST check now also inspects alias.name on ImportFrom nodes; added a
subprocess check that importing the module leaves billing.otel.receiver out of sys.modules.
6 (AC9 ambiguity): resolved per orchestrator instruction -- fallback to startTimeUnixNano
kept (matches receiver.py's own convention) and now explicitly tested; "both absent" is the
real malformed case and is now rejected instead of defaulting to 0.
7 (silent drops): non-list resourceMetrics/scopeMetrics/metrics/dataPoints now produce
explicit rejections via a new _get_list helper; the test that previously asserted
rejections==[] for this case was flipped to assert the opposite.
8 (fractional/negative values): explicitly rejected as the safer default for billing data.

python -m pytest tests/test_cowork_ingest.py -v -> 54 passed (up from 23)
python -m pytest tests/ -q (full suite) -> 523 passed, no regressions
git diff -- billing/otel/receiver.py billing/otel/transcript.py -> empty
git status --porcelain -- billing/otel/cowork_ingest.py tests/test_cowork_ingest.py -> exactly
the two owned files

Full corrected report with per-issue test names in the completion notification for the
resumed implementer (ab5c76d289e8b3357).
