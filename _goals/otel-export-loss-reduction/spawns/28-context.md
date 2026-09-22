Task 06 FIX CYCLE 3 (Phase 5 cycle-2 finding) — resumed implementer.
CURRENT_DATETIME: 2026-09-21T12:00-04:00

Phase 5's cycle-2 re-audit confirmed your None-vs-falsy fix closes what it targeted — A/B
proof, no test-trust needed. It then found a **sixth instance** of the same defect class,
in the same function, and it's more dangerous than the fifth: it hits **real UUID
sessions**, not just contrived falsy values.

## The defect

`_common`'s merge (`receiver.py:186-187`):
```python
a = dict(res)
a.update(_attrs(dp.get("attributes")))  # datapoint attrs win
```

`_attrs` calls `_attr_value`, which returns `None` for any wrapper it doesn't recognize
(`arrayValue`, `kvlistValue`, `bytesValue`, or an empty `{}`). `dict.update` doesn't care
*what* the new value is — a key present with value `None` still overwrites. So a
datapoint-level `session.id` attribute using an unparseable wrapper **clobbers a perfectly
valid resource-level session id**, and the fix I just landed then correctly-but-wrongly
treats that clobbered `None` as "genuinely absent" and stores `'unknown'`.

Reproduced, matching the real call site's data flow exactly
(`ingest_metrics_payload`'s `res = _attrs(rm.get("resource",{}).get("attributes"))` runs
*before* `_common` ever sees it):

```python
res = _attrs([{'key':'session.id','value':{'stringValue':'019a2f3c-real-uuid'}}])
# res == {'session.id': '019a2f3c-real-uuid'}
dp  = {'attributes': [{'key':'session.id','value':{'arrayValue': {'values': []}}}]}
_common(res, dp)['session_id']   # -> 'unknown'  (was '019a2f3c-real-uuid')
```

A `cli` transcript record for that real session is then accepted and double-billed, exactly
the same shape as the fifth path — just triggered by an unrecognized wrapper instead of a
falsy scalar, and hitting the case this whole goal has called "the real case" throughout
(a genuine UUID session), not an edge case.

## The fix — at the merge, not the fallback

Your None-vs-falsy logic from the last cycle is correct and stays. **This fix is one level
up**: a datapoint-level attribute whose parsed value is `None` must never overwrite a
resource-level value that's already present. Change the merge itself:

```python
a = dict(res)
dp_attrs = _attrs(dp.get("attributes"))
a.update({k: v for k, v in dp_attrs.items() if v is not None})  # datapoint attrs win,
                                                                  # but never with a None
                                                                  # that would clobber a
                                                                  # resource-level value
```

This is deliberately **general**, not scoped to `session.id` — the same clobbering
mechanism could silently blank any merged field (`user.email`, `model`, `repo`, ...) if a
datapoint sends an unrecognized wrapper for a key the resource already had. Fixing it at
the merge is what closes the *class*, not just this one field. Your existing
`_raw_session_id is not None` check downstream is unaffected and stays exactly as it is —
it now simply never sees a spuriously-`None`'d value for a key the resource actually had.

**What does NOT change:** a datapoint that genuinely provides its own distinct value (even
falsy — `intValue "0"`) still overrides the resource level, because `0` is not `None`. Only
an *unparseable* datapoint-level attribute stops clobbering.

## Update the residual comment

Your comment above the `"session_id"` line currently enumerates what's fixed and what's
still open. Correct it to state plainly: the merge-level clobber (unrecognized
datapoint-level wrapper overwriting a valid resource-level value) is now also closed, and
say so as a fourth residual point, in the same voice as (i)/(ii)/(iii). Do not claim the
class is now *exhaustively* closed — you don't know that, and this goal has been burned
three times by a comment implying more than was verified. State what's proven: no
`_attr_value`-unparseable wrapper can clobber a present value from the other level anymore.

## Also in this spawn: correct `README.md`'s stale `pilot-package/` references

Separate, unrelated issue, but small and tied to the same deletion this session already
made. `README.md` (declared ground truth by `CLAUDE.md`) still says:

- Line ~115, folder-layout tree: `pilot-package/      the earlier opt-in package —
  superseded by client-package/` — remove this line.
- Lines ~221-227, a whole `### pilot-package/ — superseded` section describing it as
  "Kept for reference" and telling readers to send `client-package/` instead — this
  directory no longer exists, so "kept for reference" is now false. Delete the section.
  Fold its one load-bearing fact — that `client-package/`'s installer also cleans up the
  bad `OTEL_LOGS_EXPORTER=none` key on machines that ran the old pilot — into the
  `client-package/` section itself as a one-line footnote, so that operational detail isn't
  lost.

Do **not** touch `client-package/ADMIN.md`'s "Fixed relative to `pilot-package/`" section —
that's legitimate historical context explaining a design decision, not a claim that the
directory currently exists.

## Write fence

```
billing/otel/receiver.py
README.md
```

Nothing else. Not `otel_store.py`, not `transcript.py`, nothing under `tests/` — the
regression test is a separate spawn.

## Do not regress

Everything already proven in this function across three prior cycles: `dp_key` invariance,
the None-vs-falsy distinction for present values, the three still-open SQLite-affinity
survivors (`intValue "0123"`, `intValue "+123"`, `doubleValue 42.0` — unrelated to this fix,
leave them exactly as documented), the four other merged fields' existing `or "unknown"`/
`or ""` fallback behavior for the case where the resource level *also* has nothing (that
should be unaffected by this change — verify it).

## Model

requested: claude-sonnet-5 · tier: light · rotation: n/a (resumed)

## Rules

- Minimal diff in `receiver.py`: the dict-comprehension filter, the comment update.
- Standard library only.
- Do not edit any test.
- Re-run the full suite at the end and report the count — it must still be green, since
  you're not supposed to be changing any currently-tested behavior, only closing a gap
  nothing currently exercises.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Fix (verbatim, the changed lines)

## Reproduction — A/B, matching the exact call-site data flow
[Resource with a real UUID + datapoint with each of arrayValue/kvlistValue/bytesValue/{}
-> stored session_id, shown fixed. Plus the control: datapoint with NO session.id
attribute at all -> resource-level value still wins, unaffected.]

## Residual comment (verbatim, final text)

## README.md (verbatim, the two edited spots)

## Verification
[Full suite -> result. Must be green, same count as before your change.]

## Anything else touched
["None" is valid.]

### Footprint
files_read: <N> (~<C> chars)
```
