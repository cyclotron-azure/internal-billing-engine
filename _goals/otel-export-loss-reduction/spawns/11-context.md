Task 03 fix cycle 1 RE-EVALUATION — resumed evaluator (delta prompt per the resume policy).
CURRENT_DATETIME: 2026-09-16T17:25-04:00

Your NEEDS FIXES verdict was accepted in full. The finding was real, and it was the most
valuable single result of this goal: all 19 criteria passed while the guard was broken,
because criteria 10 and 16 only proved the build site and lookup site agreed with *each
other*. Thank you for going past the criteria.

## Applied

1. **`.strip()` removed from both session-key sites** — `receiver.py:426` (the
   `backfill_session_ids` comprehension) and `receiver.py:452` (`session_key`). Both are
   now `str(record["session_id"])`, matching the store's verbatim persistence.
   `grep -c 'session_id"]).strip()'` over `receiver.py` returns 0.
2. **The misleading comment is corrected**, which was your finding's root cause. The
   docstring at `transcript.py:352-360` now reads, in part: "Of the store's insert_*
   methods, only `request_id` gets stripped there; `session_id` is persisted VERBATIM
   (otel_store.py:51) and any guard that keys off it -- e.g. receiver.py's
   `sessions_with_otlp_rows` lookup -- must match that verbatim value, not a stripped one,
   or it will look up a key the table can never contain."
3. **No store-side normalization was added.** `otel_store.py` was not touched;
   `session_id` persistence is unchanged, so `dp_key` inputs and billing history are
   unaffected.
4. **A new criterion 03.20 pins the regression** with your reproduction written into it,
   and task 05 owns the test. Task 03 now has 20 criteria; the goal total is 60.
5. Your NON-BLOCKING README finding is logged as a Phase 6 carry-in (`README.md:147` still
   calls `/v1/transcript-usage` desktop-only and its route list omits `GET /healthz`),
   alongside two carry-ins from task 01.

Final diff: `receiver.py` +164/-2, `transcript.py` +52/-13.

## The orchestrator's own verification, for you to check rather than repeat

I reproduced end-to-end against a temp store with a positive case and **two negative
controls**, on the reasoning that a guard which rejected everything would also show "counts
unchanged" on the padded case:

```
PADDED    before=(1, 0) after=(1, 0) inserted=0 reasons=['session_has_otlp']
CONTROL   before=(1, 0) after=(3, 1) inserted=3 reasons=[]
DESKTOP   before=(3, 1) after=(5, 2) inserted=3 reasons=[]
```

Also recorded in the report: one false alarm of mine, where the control appeared rejected
and turned out to be `unknown_field:cost_usd` in my own probe record, not a code defect.

## What I need from you

1. **Confirm the fix closes the finding**, using your existing `probe_ws.py` rather than a
   fresh build. Check the padded case in **both** shapes — OTLP rows in `token_usage`, and
   the only OTLP row in `cost_usage` via `insert_cost_datapoint` alone.
2. **Look for a normalization mismatch I have not thought of.** The lesson generalizes: any
   transformation applied on one side of that key and not the other is a double-billing
   path. Consider case, Unicode normalization, embedded newlines or tabs, an empty-string
   session id, a session id that differs only by a trailing NUL, and `"unknown"` — which
   the OTLP path substitutes for a missing `session.id` (`receiver.py:190`) and which could
   therefore collide across unrelated sessions. Does `"unknown"` create a *false* exclusion
   that silently discards recoverable CLI usage?
3. **Confirm no regression** in what you already verified by execution: the detail gate and
   the `{status, now}` key set under both token states, the 899s/900s boundary and the
   future-stamp clamp, both desktop exemptions, the single batched guard call with
   non-`None` all-`str` arguments, `stale_seconds` 10800 and the +60s clamp, the 503 with
   no path leakage, 404 on every non-`/healthz` GET, and the rejected-record key order.
4. **Re-run the targeted selection** and confirm it is still `5 failed, 169 passed` with the
   same five names — no sixth failure introduced by the fix.
5. Re-check the two new deletions in `transcript.py` (13 now, up from 10) are only the
   comment rewrite.

Do not re-report the fixed finding unless the fix is wrong or incomplete. Same rules:
evaluate only, no repository writes, no full-suite run.

## Output

Same format as before, with a leading `## Fix verification` section. Verdict line first.
