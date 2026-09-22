Task 06 FIX CYCLE 4 (Phase 5 cycle-3 finding) — resumed implementer.
CURRENT_DATETIME: 2026-09-21T13:00-04:00

Phase 5's cycle-3 audit confirmed your merge fix from last cycle closes exactly what it
targeted — independent A/B re-derivation, not test-trust. It then found a **seventh
instance**, one level upstream, and it invalidates one sentence in your own comment.

## The defect

`_attrs` (`receiver.py:176-177`):
```python
def _attrs(attr_list) -> dict:
    return {a["key"]: _attr_value(a.get("value", {})) for a in (attr_list or [])}
```

This is a plain dict comprehension over the attribute list — **duplicate keys within one
list collapse last-wins**. If a `session.id` key appears twice in the same list (resource
*or* datapoint) and the second occurrence uses an unrecognized wrapper (`arrayValue`,
`kvlistValue`, `bytesValue`, `{}`), `_attrs` hands back `{"session.id": None}` — **before**
your cycle-3 merge filter in `_common` ever runs. The filter can't help, because by the
time `_common` sees it, there was never a valid value in the returned dict to protect.

Reproduced identically to the sixth instance: a real UUID `session.id` followed in the
same list by any of the four unparseable wrappers collapses to `'unknown'`, `(1,0) ->
(5,1)` double-billed, at both resource level and datapoint level.

**Your comment overclaims.** The sentence "so this is the one place to fix it" (near
`receiver.py:195`) is now literally false — this finding is the counter-example. Fix the
sentence along with the code.

## The fix — at the true producer this time

Move the guard from where values are *consumed* (`_common`'s merge, cycle 3's fix) to
where they're *produced* (`_attrs` itself):

```python
def _attrs(attr_list) -> dict:
    result = {}
    for a in (attr_list or []):
        v = _attr_value(a.get("value", {}))
        if v is not None:
            result[a["key"]] = v
    return result
```

This drops a key entirely rather than storing `None` for it, so:
- Within one list, an earlier valid occurrence of a key survives a later unparseable one
  for the same key (the duplicate-collapse bug, closed).
- `_common`'s merge sees a `dp_attrs` dict that **never contains `None`** for any key, so
  a resource-level value can never be clobbered by a datapoint-level `None` either (the
  sixth instance, still closed, now for a structural reason rather than a filter).

**Decide, and document your decision, on `_common`'s existing merge-level filter** (the
`if v is not None` in `{k: v for k, v in dp_attrs.items() if v is not None}`, added last
cycle). With `_attrs` now never returning a `None` value, that filter is dead code — it
will never actually filter anything. You may either simplify `_common` back to
`a.update(dp_attrs)` (now safe, since `dp_attrs` structurally can't contain `None`), or
leave the filter in place as defense-in-depth against a future change to `_attrs` that
reintroduces the bug. Either is acceptable; state which you chose and why in your comment.

## Update the residual comment

- Fix the overclaiming sentence near `:195` ("so this is the one place to fix it").
- Add a fifth labeled residual point (v), same voice as (i)-(iv), describing this fix: the
  producer-level `None`-drop in `_attrs`, why it's the convergent fix (one place values are
  produced vs. many places they're consumed), and — same discipline as every prior
  residual — state plainly what this proves (no key with *any* valid occurrence in one
  attribute list, at either level, can ever surface as `None`) and do **not** claim the
  defect class is now exhaustively closed everywhere in the file. The Phase 5 audit
  separately found an unrelated commit-atomicity bug in `ingest_metrics_payload` — that is
  out of this task's scope (spun off as its own follow-up), but don't let your comment's
  confidence bleed into implying this file has been fully audited.

## Write fence

```
billing/otel/receiver.py
```

Nothing else.

## Do not regress

`dp_key` invariance, the None-vs-falsy distinction (residual iii), the merge-level fix
(residual iv, now superseded in mechanism but not in outcome — the behavior it fixed stays
fixed), the three still-open SQLite-affinity survivors (residual ii — untouched), `README.md`
(not in this fence, already fixed last cycle, do not touch).

## Model

requested: claude-sonnet-5 · tier: light · rotation: n/a (resumed)

## Rules

- Minimal diff: `_attrs`'s body, the one overclaiming sentence, one new residual paragraph,
  and (if you choose to simplify it) `_common`'s merge line.
- Standard library only.
- Do not edit any test — the regression test for this exact scenario is a separate spawn.
- Do not touch `ingest_metrics_payload`'s commit/rollback behavior — that's the spun-off
  follow-up task's job, not this one's.
- Re-run the full suite; must stay green at 428.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Fix (verbatim, the changed _attrs function)

## Reproduction — A/B
[Duplicate session.id key in one list: valid-then-unparseable, both at resource level and
at datapoint level -> now preserves the valid value. Show the pre-fix collapse too, either
by reproducing it or citing this cycle's audit reproduction directly.]

## Decision on _common's now-redundant filter
[Kept or simplified, and why.]

## Residual comment (verbatim, the corrected sentence + new point (v))

## Verification
[Full suite -> result. Must be 428 passed.]

## Anything else touched
["None" is valid.]

### Footprint
files_read: <N> (~<C> chars)
```
