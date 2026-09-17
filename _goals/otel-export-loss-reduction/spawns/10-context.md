Task 03 FIX CYCLE 1 — resumed child implementer (a2d556055c49fbded, the agent that
actually did the work). CURRENT_DATETIME: 2026-09-16T17:10-04:00

Your task 03 work was evaluated: **all 19 criteria MET, every one executed**, the four
pre-existing test breaks were exactly the anticipated set with no fifth failure, all three
of your declared deviations were ruled **SOUND**, and the POST paths were confirmed
byte-identical function by function. Good work.

**Verdict is NEEDS FIXES for one reason: a reproduced double-billing path.** Criteria
satisfaction was not the same as correctness — criteria 10 and 16 pass only because your
build site and lookup site strip *consistently with each other*, and neither matches the
store.

## The defect

`receiver.py:417` and `receiver.py:443` both key on
`str(record["session_id"]).strip()`. **The store persists `session_id` verbatim.**
`insert_datapoint`'s `.strip()` applies only to `request_id` (`otel_store.py:51`), never to
`session_id`, and `sessions_with_otlp_rows` compares verbatim via
`IN (SELECT x FROM ids)`.

So a session id carrying surrounding whitespace is queried under a key that does not exist
in the table, the guard returns `set()`, and `set()` reads as "no OTLP rows, safe to
insert". Reproduced independently twice — by the evaluator end-to-end, and by the
orchestrator directly against the store:

```
STORED: [' sess-ws-777 ']
guard with stripped key : set()
guard with verbatim key : {' sess-ws-777 '}
```

End-to-end: the `cli` record was accepted and 4 token rows + 1 cost row landed on a session
that already had an OTLP row. That is precisely what criterion 10 exists to prevent.

**Reachable, not theoretical.** The OTLP path takes `a.get("session.id") or "unknown"` with
no strip (`receiver.py:190`), and transcript validation checks `session_id` for truthiness
only (`if not record.get(field)`, `transcript.py:253`), so `" sess-x "` validates and is
stored padded on both sides.

## Why you were misled — and the second half of the fix

Your report justified the strip as "matching `validate_batch`'s own dedupe-key
normalization". The code does not support that, and the comment that suggests it is
actively wrong:

- `validate_batch`'s strip (`transcript.py:450`) feeds an **in-batch dedupe hash key**, a
  different key space entirely.
- `transcript.py:352-356` states: "Does NOT strip whitespace on session_id/request_id --
  transcript_key itself doesn't either; **the store's insert_* methods do their own
  stripping**." That last clause is true only of `request_id`. For `session_id` it is
  false, and it is what led you here.

## Required fixes

1. **Drop `.strip()` from both session-key sites** — `receiver.py:417` (the
   `backfill_session_ids` comprehension) and `receiver.py:443` (`session_key`). Use the
   same expression at both, and make it the value the store actually receives. The build
   site and the lookup site must agree with **the store**, not merely with each other.
2. **Correct the misleading clause in `transcript.py:352-356`** so it names the field:
   the store's insert paths strip `request_id` only, and `session_id` is persisted
   verbatim. One clarifying edit, in your existing fence. This is the comment that caused
   the defect; leaving it in place invites the same mistake again.
3. Do **not** add a normalization to the store to meet the guard halfway.
   `otel_store.py` is not in your fence, and changing how `session_id` is persisted would
   alter `dp_key` inputs and silently re-bill history.

## Write fence — unchanged

```
billing/otel/receiver.py
billing/otel/transcript.py
```

Still nothing under `tests/`. A new criterion 20 now pins this regression, and **task 05
writes that test** — not you.

## Do not regress what already passed

All 19 criteria were verified by execution, including these, which your fix must not
disturb: the `AUTH_TOKEN and self._authorized()` gate and the `{status, now}` key set under
both token states; the 899s/900s quarantine boundary and the future-stamp clamp; both
`claude-desktop` exemptions; the single batched guard call with non-`None`, all-`str`
arguments; `stale_seconds` of 10800 and the +60s clamp to 0; the 503 `{"status":
"degraded"}` with no path leakage; 404 on every non-`/healthz` GET; and the rejected-record
key order `["index", "request_id", "reason"]`.

## Model

requested: claude-sonnet-5 · tier: light · rotation: cycle 1 (resumed, no rotation)

## Rules

- Minimal diff. This is a two-site fix plus one comment correction, not a refactor.
- Re-run:
  `python -m pytest tests/test_receiver.py tests/test_transcript.py tests/test_transcript_hook.py tests/test_integration_desktop.py tests/test_otel_store.py -q`
  The expected result is still **5 failed, 169 passed**, with the same five names. Any
  change to that set is a finding — report it.
- Do not run the full suite.
- **Report your own reproduction of the fix**, not just the change: show that a
  whitespace-padded `session_id` now rejects with `session_has_otlp` and that the row
  counts over both tables are unchanged.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Fixes
[One line each: the two call sites, the comment.]

## Reproduction (verbatim)
[Before/after row counts over token_usage AND cost_usage for a whitespace-padded
session_id, plus the rejection record.]

## Regression check
[The pytest line -> result, and the five failure names.]

## Anything else the fix touched
["None" is valid.]

### Footprint
files_read: <N> (~<C> chars)
```
