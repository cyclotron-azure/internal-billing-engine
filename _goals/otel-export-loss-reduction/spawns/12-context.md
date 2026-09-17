You are the implementer subagent. Read: .claude/agents/implementer.md

Task 03 FIX CYCLE 2 — **fresh spawn with model rotation** (cycle 1 was a resume; per the
orchestration policy cycles 2-3 are fresh and pin a different model family).
CURRENT_DATETIME: 2026-09-16T17:50-04:00

## Context

Task 03 of `otel-export-loss-reduction` is implemented and almost done. Two evaluation
passes found the same class of bug twice, in the guard that decides whether a CLI
transcript row gets billed. Cycle 1 fixed the first instance. **You are fixing the class.**

The guard is `sessions_with_otlp_rows`, and its contract is: a `session_id` for which the
store already holds an OTLP row must be found, so the transcript record is rejected rather
than billed on top. It works by building a lookup key in Python and comparing it against
what SQLite holds.

**The defect, both times, is a normalization asymmetry between those two sides.**
- Cycle 1: the guard applied `.strip()`; the store persists `session_id` verbatim.
- Now: the guard applies `str()`; the store binds the raw value and lets **SQLite's TEXT
  affinity** convert it. Those two conversions disagree.

Verified empirically by the orchestrator:

```
python=True    str()='True'    sqlite_stores='1'         MATCH=False
python=False   str()='False'   sqlite_stores='0'         MATCH=False
python=1e+20   str()='1e+20'   sqlite_stores='1.0e+20'   MATCH=False
python=123     str()='123'     sqlite_stores='123'       MATCH=True
python=1.5     str()='1.5'     sqlite_stores='1.5'       MATCH=True
```

Reproduced over the real HTTP path with raw JSON, OTLP row pre-seeded: a `cli` record with
`"session_id": true` was **accepted and double-billed** — 4 token rows + 1 cost row landed
on a session that already had an OTLP row.

## The fix

**Type-validate `session_id` in `_validate_record` (`billing/otel/transcript.py`).**

- Reject a non-`str` `session_id` with a **new** reason string, added to
  `transcript.REJECTION_REASONS`. Follow the existing vocabulary — `invalid_ts`,
  `invalid_entrypoint`, `invalid_tokens:*` — so `invalid_session_id` fits.
- Do **not** reuse or alter any existing reason string. In particular do not overload
  `missing_field:session_id`, which means *absent*; a wrong-typed id is *present and
  invalid*, and a client needs to tell those apart.
- Put the check alongside the existing truthiness test at `transcript.py:253`, and mind the
  ordering: a missing id must still report `missing_field:session_id`, not the new reason.

**Why validation rather than coercion**, so you do not "improve" on this: normalizing in
`otel_store.py` is out of fence, and changing how `session_id` is persisted would alter
`dp_key` inputs and silently re-bill history. Making the guard mimic SQLite's conversion
rules would be a second implementation of type affinity — the thing that just broke twice.
Rejecting a non-`str` id makes the two sides *unable* to diverge, which is the only fix
that closes the class rather than another instance.

**The structural argument for this fix, worth understanding:** `session_id` is currently
the **only** billing-critical field with no type check. `ts` is checked
(`transcript.py:339`), `request_id` is (`:385`), token values are numeric-checked
(`:284-289`), `entrypoint` and `query_source` are enum-checked, and unknown fields fail
closed. This receiver's posture is "validate everything server-side, never trust the
client." You are closing the one gap in it, and it happens to sit on the key the guard
depends on.

## Write fence

```
billing/otel/receiver.py
billing/otel/transcript.py
```

The fix is most likely `transcript.py` only. Nothing under `tests/` — criterion 21 pins
this and **task 05 writes that test**, not you.

## Do not regress what is already verified by execution

Two evaluation passes confirmed all of this green; your change must not disturb any of it:
the `AUTH_TOKEN and self._authorized()` detail gate and the `{status, now}` key set under
all four token/credential combinations; token-substring absence for all 14 prefixes; the
899s→`too_recent` / 900s→accepted boundary and the future-stamp clamp; both
`claude-desktop` exemptions; the single batched guard call with a non-`None`, all-`str`
40-element argument; `stale_seconds` 10800 and the +60s→0 clamp; the 503
`{"status": "degraded"}` with no path leakage; 404 on every non-`/healthz` GET and 200 on
`/prefix/healthz`; the rejected-record key order `["index", "request_id", "reason"]`; and
the cycle-1 whitespace fix (both guard sites are bare `str(record["session_id"])` — leave
them that way).

A 36-case normalization sweep already cleared whitespace, embedded newline/tab, trailing
NUL, case, Unicode NFC/NFD, full-width digits, zero-width space, CRLF, a 400-char id, and
the literal `"unknown"`. Case and Unicode are safe **only** because `session_id TEXT`
carries no `COLLATE NOCASE` — do not add one.

## Model

requested: claude-fable-5-1 · tier: light · rotation: **cycle 2, different family**

## Rules

- Minimal diff. This is a validation check plus a reason string.
- Do not change `dp_key`, `transcript_key`, the schema, or `otel_store.py`.
- Do not add `COLLATE NOCASE` anywhere.
- Standard library only.
- Re-run:
  `python -m pytest tests/test_receiver.py tests/test_transcript.py tests/test_transcript_hook.py tests/test_integration_desktop.py tests/test_otel_store.py -q`
  The expected result is still **5 failed, 169 passed** with the same five names. **If your
  change breaks a sixth test, that is a finding — report it, do not fix the test.** A
  pre-existing test that posts a non-`str` `session_id` would now reject, and the
  orchestrator needs to know.
- Do not run the full suite.
- **Report your own reproduction**: `true` and `1e20` both rejected with the new reason, and
  `COUNT(*)` over both tables unchanged. Include a positive control — an ordinary `str`
  session id with no OTLP rows must still be **accepted** — because a validator that
  rejects everything would also show "counts unchanged".

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Fix
[The check, where it sits, the new reason string, and the ordering vs missing_field.]

## Reproduction (verbatim)
[true and 1e20: reason + before/after counts over BOTH tables. Plus the positive control.]

## Regression check
[The pytest line -> result and the failure names. Flag any sixth failure prominently.]

## Anything else the fix touched
["None" is valid.]

### Footprint
files_read: <N> (~<C> chars)
```
