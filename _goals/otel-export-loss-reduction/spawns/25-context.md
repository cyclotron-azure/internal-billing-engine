Task 06 FIX CYCLE 2 (Phase 5 finding) — resumed implementer. CURRENT_DATETIME: 2026-09-21T10:00-04:00

Phase 5's final audit found a **fifth double-billing path**, in the same function you
already fixed once. Read `_goals/otel-export-loss-reduction/06-otlp-session-id-coercion.md`
criteria 10-11 for the full spec. This note gives you everything else you need.

## The defect

`billing/otel/receiver.py:221`:
```python
"session_id": str(a.get("session.id") or "unknown"),
```

`or` treats **every** falsy value as "missing" — not just a genuinely absent attribute.
`_attr_value` can legitimately return `0`, `False`, `0.0` or `""` for a real (if degenerate)
`session.id`. All of those collapse into the single shared key `'unknown'`.

Reproduced by the auditor: an OTLP datapoint with `session.id` sent as `intValue "0"`
(`_attr_value` parses to Python `int` `0`) gets stored as `session_id='unknown'`. A `cli`
transcript record for session `'0'` is then posted. The guard looks up `'0'`, finds
nothing (the real row is filed under `'unknown'`), and accepts it — `(1,0) -> (3,1)`,
double-billed, even though an OTLP row for that exact session already existed.

## The fix

Distinguish **`None`** (attribute truly absent, or `_attr_value` couldn't parse the
wrapper) from **any other falsy value**. Only `None` maps to `"unknown"`.

```python
a = dict(res)
a.update(_attrs(dp.get("attributes")))  # datapoint attrs win
repo_raw = a.get("repo")
_raw_session_id = a.get("session.id")
return {
    ...
    "session_id": str(_raw_session_id) if _raw_session_id is not None else "unknown",
    ...
}
```

Compute it once into a local (`_raw_session_id`) rather than calling `.get()` twice inside
the dict literal — keeps the diff small and avoids a subtle "the two calls could return
different things" trap if `_attrs` were ever made non-deterministic.

**What this does and does not fix**, so your comment stays honest:
- `intValue "0"` → stores `'0'` (was `'unknown'`) — **fixed**.
- `boolValue false` → stores `'False'` (was `'unknown'`) — **fixed**.
- `doubleValue 0.0` → stores `'0.0'` (was `'unknown'`) — **fixed**.
- `stringValue ""` → stores `''` (was `'unknown'`) — **fixed as a side effect**; `''`
  can never collide with a transcript record because `transcript.py`'s validator rejects
  an empty `session_id` as `missing_field` before it ever reaches the guard.
- Attribute **genuinely absent** → still stores `'unknown'`. **Do not change this.** It is
  criterion 11, and it is the same accepted-residual class as partially-lost sessions: an
  anonymous datapoint has no safe unit of comparison, and inventing a unique placeholder
  per datapoint is a much larger change that is out of scope here.

## Extend the existing comment, don't replace it

Your residual-(i)/(ii) comment above this line is correct and must stay. Add a short
residual-(iii) paragraph for this fix, in the same voice, and update the "partial by
design" closing line to reflect that this fix closes a class-adjacent-but-distinct bug
(None-vs-falsy), not one of the three SQLite-affinity survivors. Do not remove or weaken
anything already there — the three `intValue`/`doubleValue 42.0` survivors are still open
and the comment must keep saying so.

## Write fence

```
billing/otel/receiver.py
```

Nothing else. Not `otel_store.py`, not `transcript.py`, nothing under `tests/` — task 05's
test-writer adds the regression test in a follow-up spawn, not you.

## Do not regress

Everything in `_common` besides the `session_id` line is untouched: `repo`, `repo_raw`,
`user_email`, `user_id`, `org_id`, `model`, `query_source`, `type`, `time_unix_nano`. The
`dp_key` invariance you already proved (`str()` matches what the f-string interpolates)
is unaffected — this fix runs *before* the `str()` coercion path in the sense that it
decides what value gets coerced, but does not change how `dp_key` builds its key.

The current five-file baseline (before your fix) — re-establish it before you start, since
Phase 4/5 work has landed since your last spawn. Expect roughly the same shape (a handful
of task-05-owned red tests, no new ones from you).

## Model

requested: claude-sonnet-5 · tier: light · rotation: n/a (resumed)

## Rules

- Minimal diff: the local variable, the one changed line, the comment addition.
- Do not touch `_attr_value` or the body-parse (`json.loads`) site — unrelated to this fix.
- Standard library only.
- Do not edit any test.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Fix (verbatim, the changed lines)

## Reproduction
[The four now-fixed wrappers -> stored value -> guard result, and the absent-attribute
case shown UNCHANGED at 'unknown'.]

## dp_key check
[Confirm dp_key for one of the newly-distinct values, e.g. session_id=0, is unaffected /
still computed correctly from the new string.]

## Verification
[Targeted pytest line -> result. Report the failure count and names; do not assume the
old baseline.]

## Anything else the fix touched
["None" is valid.]

### Footprint
files_read: <N> (~<C> chars)
```
