**Model (self-reported)**: claude-sonnet-5

## Task Complete: Task 03 -- Standalone Cowork receiver process

All 12 Acceptance Criteria and all Requirements checked off (see full detail in completion
notification for agentId a6a6a5ee81c60e7d9). Highlights:
- Single-threaded HTTPServer, own CLI (--host/--port 4319/--db/--require-auth)
- Auth via COWORK_RECEIVER_AUTH_TOKEN only, loaded via billing.config.load_env (not receiver.py)
- POST /v1/metrics: parse_cowork_payload -> per-record try/except around store inserts ->
  commit inside guarded region with rollback on non-data-shape errors
- Every rejection logged (reason + minimal identifiers, no raw bytes) to cowork_receiver.log
- GET /healthz: last_ingest_at only with valid token AND non-empty configured token
- Other POST paths ack 200 {}; GET-other -> 404
- .env.example appended (3 placeholders), no existing content touched
- Tested entirely via socket.socketpair(), verified by a test asserting no real socket is bound

### Verification
- python -m pytest tests/test_cowork_receiver.py -v -> 30 passed
- python -m pytest tests/ -q (full suite) -> 648 passed
- git diff -- billing/otel/receiver.py -> empty
- Manual adversarial probing outside pytest: garbage bytes, 2MB garbage body, false gzip
  Content-Encoding, empty body -- all clean 400/200, never crashed
- Deliberately reintroduced a bug (_RECORD_DATA_ERRORS = ()) confirming the per-record test
  actually fails without the fix, then restored and reconfirmed all 30 pass

### Judgment call flagged for evaluator
The JSON response body for /v1/metrics omits the full `rejections` list (only returns counts +
metrics_seen), keeping detailed reasons in the log only. AC4 says "with the rejection reflected
in the response body" -- satisfied via a non-zero `rejected` count, not an itemized list. Flagged
as a one-line addition if the evaluator expects the full list in the body too.

### Footprint
files_read: 9 (~85,000 chars)
commands_run: 9
