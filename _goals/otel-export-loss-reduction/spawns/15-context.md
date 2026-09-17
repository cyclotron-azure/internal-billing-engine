You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-16T18:35-04:00

## Task

Task 06 of `otel-export-loss-reduction`: coerce the OTLP `session.id` to `str` in `_common`
so the spelling SQLite persists can never differ from the spelling the OTLP-exclusion guard
builds.

**Read `_goals/otel-export-loss-reduction/06-otlp-session-id-coercion.md` in full and follow
it exactly.** It contains the measured reproduction table, the settled `dp_key` analysis,
your requirements, and your 9 acceptance criteria. Nothing here supersedes it.

The change itself is roughly one line. Everything hard about this task is in the criteria
and in what you must **not** disturb.

## Why this exists

Task 03's guard broke twice on one defect class: a transformation applied to the session key
on one side and not the other. First a `.strip()`, then a `str()` that disagreed with
SQLite's TEXT-affinity conversion. Both were reproduced as accept-and-double-bill.

This is the last surviving instance of that class, entered from the `/v1/metrics` end.
`_attr_value` returns `str | int | float | bool | None` depending on the OTLP value wrapper,
and `_common` binds the result straight into a TEXT column — so SQLite picks the stored
spelling. Five double-bills were reproduced: `intValue "0123"` stores `'123'`,
`doubleValue 42.0` stores `'42.0'`, `boolValue true` stores `'1'`, and so on, none of which
a valid `str` transcript id matches.

## Two things already settled — do not re-derive or second-guess them

1. **`dp_key` is invariant under this change.** It interpolates with an f-string, which is
   `str()`, so `dp_key(raw) == dp_key(str(v))` was measured identical for `True`, `1e20`,
   `123`, `42.0` and `'sess'`. Your coercion changes no `dp_key`, creates no duplicate rows,
   and re-bills no history. Criterion 4 asserts this — do not weaken it, because it is the
   reason this task is safe.
2. **Coerce, do not reject.** The transcript path rejects a non-`str` `session_id` because a
   rejected record simply is not billed. An OTLP datapoint carries real usage that must
   still be recorded; dropping it would turn a double-billing bug into a data-loss bug.

## The trap specific to this task

Do **not** try to make Python reproduce SQLite's TEXT-affinity conversion rules. The whole
point is to stop two conversions from existing, not to add a third. If you find yourself
writing a formatting branch per type, stop — that is the defect, re-implemented.

## Write fence

```
billing/otel/receiver.py
```

Nothing else. Not `otel_store.py`, not `transcript.py`, nothing under `tests/`.

## Do not regress — this file is heavily verified

Task 03's evaluator verified all of the following by execution, three times over. Criterion
9 requires these to be byte-identical to their end-of-task-03 state: `do_POST`,
`_authorized`, `_presented_token`, `_read_body`, `_attr_value`, `_attrs`,
`ingest_session_repo_payload`, `ingest_transcript_usage_payload`, and the `/healthz`
handler. Your change is confined to `_common` plus comments.

Also still green and not to be disturbed: the `AUTH_TOKEN and self._authorized()` detail
gate; the `{status, now}` key set under all four token/credential combinations; the
899s/900s quarantine boundary; both `claude-desktop` exemptions; the single batched guard
call; `stale_seconds` 10800 and the +60s clamp; the 503 with no path leakage; 404 on every
non-`/healthz` GET; and `user_email={"a":1}` still reaching `_RECORD_DATA_ERRORS` as
`store_error:ProgrammingError` (criterion 7 — there is a pre-existing test pinning it).

## Model

requested: claude-sonnet-5 · tier: light · rotation: n/a

## Rules

- Coerce **after** the existing `or "unknown"` fallback so its falsy semantics are
  unchanged.
- Add the residual comment required by the requirements: this prevents *future* mis-spelled
  rows; any row already stored under a non-`str`-derived spelling keeps it, none are
  expected in production because session ids are UUIDs, and a backfill is deliberately out
  of scope. Say it plainly rather than implying the fix is retroactive.
- Stdlib only. No schema change, no migration, no repair pass.
- Climb test-ladder rungs 1-2 only. Do not run the full suite.
- The targeted baseline is **6 failed, 168 passed** and those six are known and owned by
  task 05. A **seventh** failure is a finding — report it with file:line, do not fix it.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Change
[The coerced expression verbatim, and where it sits relative to the `or "unknown"`
fallback.]

## Evidence (verbatim, only these two)
a) the nine-wrapper table: OTLP wrapper -> stored session_id -> typeof
b) dp_key for the `boolValue true` datapoint, before and after the change, shown equal

## Residual
[The comment you added, verbatim.]

## Verification
[The targeted pytest line -> result and the failure names.]
[Confirmation that the nine listed functions are byte-identical to their end-of-task-03
state, and how you checked.]

## Pre-existing tests broken
["None" is expected here. Flag a seventh failure prominently.]

### Footprint
files_read: <N> (~<C> chars)
```
