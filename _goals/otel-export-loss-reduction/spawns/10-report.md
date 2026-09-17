MODEL: claude-sonnet-5
STATUS: completed

## Fixes
- `billing/otel/receiver.py` build site (`backfill_session_ids`):
  `str(record["session_id"]).strip()` -> `str(record["session_id"])` -- matches the store's
  verbatim persistence.
- `billing/otel/receiver.py` lookup site (`session_key`): same change; both sites now agree
  with the store rather than only with each other.
- `billing/otel/transcript.py:352-356` docstring: corrected the misleading "the store's
  insert_* methods do their own stripping" clause to name the field -- only `request_id` is
  stripped by `insert_datapoint`/`insert_cost_datapoint`; `session_id` is persisted
  verbatim (otel_store.py:51), and any guard keying off it must use the verbatim value.

## Reproduction (verbatim, implementer's)
```
BEFORE token_usage: 1 cost_usage: 0
rejections: [{"index": 0, "request_id": "req-ws-1", "reason": "session_has_otlp"}]
inserted: 0 rejected: 1
AFTER  token_usage: 1 cost_usage: 0
guard verbatim: {' sess-ws-777 '}
guard stripped: set()
```

## Regression check
`python -m pytest tests/test_receiver.py tests/test_transcript.py
tests/test_transcript_hook.py tests/test_integration_desktop.py tests/test_otel_store.py -q`
-> **5 failed, 169 passed** -- same five names as before the fix:
test_receiver.py::test_non_desktop_entrypoint_is_rejected;
test_transcript.py::test_ac2_non_desktop_entrypoint_rejected[cli];
test_transcript.py::test_ac2_non_desktop_entrypoint_rejected[claude-vscode];
test_transcript.py::test_rejection_index_is_original_batch_position_in_larger_mixed_batch;
test_integration_desktop.py::test_systemic_alarm_silent_for_pure_validation_rejections.
Also re-verified the untouched invariants: the 40-record single-call spy still returns
exactly 1 call with a non-None, all-str argument, and normal (non-padded) cli records still
insert correctly (80 rows for 40 records, 0 rejected).

## Anything else the fix touched
None -- two call-site edits plus the one clarifying comment edit.

### Footprint
files_read: 3 (~4000 chars)

---

## ORCHESTRATOR'S INDEPENDENT VERIFICATION

Not taken on trust. Confirmed directly:

- Both guard sites are now `str(record["session_id"])` (receiver.py:426, :452) and
  `grep -c 'session_id"]).strip()'` over receiver.py returns **0**.
- The corrected docstring reads, in part: "Of the store's insert_* methods, only
  `request_id` gets stripped there; `session_id` is persisted VERBATIM (otel_store.py:51)
  and any guard that keys off it ... must match that verbatim value, not a stripped one,
  or it will look up a key the table can never contain."
- Final diff: receiver.py +164/-2, transcript.py +52/-13.

End-to-end against a temp store, with **both** a positive and two negative controls -- a
guard that rejected everything would also show "counts unchanged" on the padded case, so
the controls are the load-bearing half:

```
PADDED    before=(1, 0) after=(1, 0) inserted=0 reasons=['session_has_otlp']
CONTROL   before=(1, 0) after=(3, 1) inserted=3 reasons=[]
DESKTOP   before=(3, 1) after=(5, 2) inserted=3 reasons=[]
```

- PADDED: whitespace-padded session with an existing OTLP row -> rejected
  `session_has_otlp`, counts unchanged over both tables. The double-billing path is closed.
- CONTROL: clean session with no OTLP rows -> accepted, 3 rows added. Not over-blocking.
- DESKTOP: `claude-desktop` record on a session that DOES have OTLP rows -> accepted. The
  exemption is intact.

One false alarm of the orchestrator's own making, recorded for honesty: an earlier probe
showed the control being rejected, which looked like over-blocking. It was
`unknown_field:cost_usd` -- an invalid field in the probe's record, not a code defect. The
harness was wrong, not the implementation.
