NOTE ON PROVENANCE: spawn 08's implementer returned a non-answer ("launched the implementer
subagent... running in the background") having silently delegated to a child
(a2d556055c49fbded). No replacement was spawned -- see the GUARD TRIP note in the
orchestration log. This report is the CHILD's, and the orchestrator independently verified
every artifact claim below by grep/diff before accepting it.

MODEL: claude-sonnet-5
STATUS: completed

## Part A -- /healthz
- `do_GET` in `Handler` (receiver.py:573-579): `path = self.path.rstrip("/")`;
  `if path.endswith("/healthz"): self._healthz(); return`; else 404. Suffix match, so a
  prefix still works, and `/`, `/v1/metrics`, `/healthzz` all 404.
- Detail gate, verbatim (receiver.py:557): `if AUTH_TOKEN and self._authorized():` --
  reuses `_authorized()` unmodified for the credential comparison; `AUTH_TOKEN` supplies
  the "is a token even configured" half.
- Four detail fields: last_ingest_at, last_otlp_ingest_at, stale_seconds,
  otlp_stale_seconds -- from `store.last_ingest_at()` and
  `store.last_ingest_at(usage_source="otlp")`.
- Null vs zero: `_stale_seconds(ts, now)` returns None (-> JSON null) when ts is None,
  else `max(0, int((now - parsed).total_seconds()))`.
- Negative clamp: the `max(0, ...)` clamps a future-stamped row to 0.
- 503: `except sqlite3.Error:` around the two last_ingest_at calls ->
  `self._json(503, {"status": "degraded"})`, no traceback, no detail.
- Banner: "... (POST /v1/metrics, /v1/session-repo, /v1/transcript-usage; GET /healthz)".
- New module-level clock helpers `_now()`, `_iso()`, `_parse_store_ts()`,
  `_stale_seconds()` -- all read-through, none inline at a comparison site, so task 05 can
  monkeypatch `receiver._now`.
- do_POST and all existing POST branches byte-unmodified except the Part B insertions
  inside `ingest_transcript_usage_payload`.

## Part B -- CLI ingest
- `transcript.ALLOWED_ENTRYPOINTS = frozenset({"claude-desktop","cli","claude-vscode"})`
  replaces the singular constant; `DESKTOP_ENTRYPOINT = "claude-desktop"` names the exempt
  one; `_validate_record` checks `record.get("entrypoint") not in ALLOWED_ENTRYPOINTS` ->
  unchanged `invalid_entrypoint` reason string.
- Preserve-entrypoint fix in `map_record` (transcript.py:554):
  `row["entrypoint"] = record["entrypoint"]` (was the constant), with a comment.
- New reasons `session_has_otlp` and `too_recent` in `transcript.REJECTION_REASONS`;
  `BACKFILL_MIN_AGE_SECONDS = 900` a plain module constant (no clock, no env var).
- `receiver._BACKFILL_ENTRYPOINTS = ALLOWED_ENTRYPOINTS - {DESKTOP_ENTRYPOINT}`.
- Exclusion call site, before the per-record loop:
  `backfill_session_ids = sorted({str(record["session_id"]).strip() for record in accepted
  if record.get("entrypoint") in _BACKFILL_ENTRYPOINTS})`, then
  `otlp_sessions = store.sessions_with_otlp_rows(backfill_session_ids) if
  backfill_session_ids else set()` -- at most once per batch, only when at least one
  backfill-eligible record exists.
- Quarantine: inside the per-record loop, after `map_record`, only
  `if entrypoint in _BACKFILL_ENTRYPOINTS`: first the `session_key in otlp_sessions` check
  (-> session_has_otlp, continue), then
  `age_seconds = max(0.0, (now - _parse_store_ts(mapped["ts"])).total_seconds())` and
  `if age_seconds < BACKFILL_MIN_AGE_SECONDS: -> too_recent, continue`.
  `now = _now()` computed once per request, before the loop.
- claude-desktop records skip both checks entirely via the same guard, so they insert
  exactly as before regardless of OTLP state or age.

## Preconditions
- None never reaches the guard: the call is gated `if backfill_session_ids else set()`, so
  an empty/absent id set short-circuits locally instead of calling the store.
- str-only ids: `backfill_session_ids` is built via `str(record["session_id"]).strip()`
  (matching validate_batch's own dedupe-key normalization), and the SAME expression is
  reused for the membership lookup, so the comparison side matches the call side exactly.

## Evidence (verbatim)

a) unauthenticated GET /healthz body:
`{"status": "ok", "now": "2026-09-16T18:21:43Z"}`

b) authorized body against a seeded store:
`{"status": "ok", "now": "2026-09-16T18:21:43Z", "last_ingest_at": "2026-09-16T18:21:43Z",
"last_otlp_ingest_at": "2026-09-16T18:21:43Z", "stale_seconds": 0, "otlp_stale_seconds": 0}`
Token-substring check: `"secrettoken123" in unauth_body` -> False.

c) rejected-records from a mixed batch (all three reasons together):
```json
[
  {"index": 2, "request_id": "req-c", "reason": "invalid_entrypoint"},
  {"index": 0, "request_id": "req-a", "reason": "session_has_otlp"},
  {"index": 1, "request_id": "req-b", "reason": "too_recent"}
]
```
4th record, a valid old-enough cli record with no OTLP session, accepted:
`inserted: 2, rejected: 3`.

d) stored values for the accepted cli record:
`{'entrypoint': 'cli', 'usage_source': 'transcript'}`

## Pre-existing tests broken (4, as anticipated)
- tests/test_transcript.py:134-139 test_ac2_non_desktop_entrypoint_rejected
  (parametrized over cli/claude-vscode) -- asserts accepted == [] and invalid_entrypoint;
  both are now accepted by validate_batch.
- tests/test_transcript.py:369-381
  test_rejection_index_is_original_batch_position_in_larger_mixed_batch -- asserts rejected
  indices [1,2,4,5] where index 2 (req-2, cli) is expected rejected; now accepted, so
  accepted becomes [req-0, req-2, req-3] and rejected becomes [1,4,5].
- tests/test_receiver.py:278-287 test_non_desktop_entrypoint_is_rejected -- posts a cli
  record with ts 2026-01-01T00:00:00Z (well past the quarantine) and no OTLP rows; now
  accepted (inserted=5, rejected=0 observed).
- tests/test_integration_desktop.py:393-399
  test_systemic_alarm_silent_for_pure_validation_rejections -- same shape.
NO test outside this named set broke.

## Verification
`python -m pytest tests/test_receiver.py tests/test_transcript.py
tests/test_transcript_hook.py tests/test_integration_desktop.py tests/test_otel_store.py -q`
-> **5 failed, 169 passed** -- the 5 failures are exactly the 4 named tests (one
parametrized into 2 cases).

## Notes for the evaluator (deliberate deviations)
1. `_BACKFILL_ENTRYPOINTS` is DERIVED as `ALLOWED_ENTRYPOINTS - {DESKTOP_ENTRYPOINT}`
   rather than a hardcoded {"cli","claude-vscode"} literal, so a future entrypoint addition
   is backfill-checked by DEFAULT instead of silently exempted. Semantically identical
   today.
2. The quarantine age check reuses `mapped["ts"]` (the store-format string map_record
   already produces) rather than re-parsing `record["ts"]` with a second helper, so
   transcript.py gained no clock-adjacent code beyond the two pure constants.
3. No test file modified, per the write fence.

### Footprint
files_read: 9 (~68000 chars) / commands_run: 6
