Task 06 FIX CYCLE 1 — resumed implementer. CURRENT_DATETIME: 2026-09-16T19:50-04:00

Your one-line coercion is **correct and verified safe**, and the evaluator says explicitly
not to re-litigate it. It measured `dp_key` identical before and after
(`976d3d3280a2a0caef859ae0f817c12e` both ways), confirmed re-ingest still dedupes to one
row, confirmed the real `stringValue` UUID case is byte-identical, confirmed the falsy
fallback is unchanged, and confirmed seven of the nine protected functions byte-identical to
`HEAD` by per-function sha256. It also independently reproduced your reverted-change
neutrality check: 8 failed / 166 passed either way.

**No code change is required.** The blocker is the comment.

## The defect

Your comment at `receiver.py:190-199` states the first residual correctly:

> `This fixes future rows only: any row already stored under a non-str-derived spelling
> keeps that spelling (no backfill/migration here, deliberately out of scope)`

Two problems with the rest:

1. **The second residual is missing entirely.** Nothing says the fix is *partial*.
   Measured: the coercion closes only two of the five reproduced double-billing cases.
   `intValue "0123"`, `intValue "+123"` and `doubleValue 42.0` still double-bill.
2. **The example is wrong, and wrong in the dangerous direction.** The comment offers
   `'123' from intValue "0123"` as a spelling SQLite produced and this fix corrects.
   Neither is true: `'123'` is stored both before *and* after, because `_attr_value` does
   `int(v["intValue"])` — Python destroys the spelling before SQLite is involved. The
   comment attributes a Python-side parse loss to SQLite and presents it as fixed.

This matters more than a normal comment error. This goal has already been burned twice by
exactly this: `transcript.py` claimed the store strips `session_id` (true only of
`request_id`), which is what caused task 03's first fix cycle; and a test named
`..._is_rejected_not_escaped` documented a hole as closed while covering only half of it.
An overstating comment in the file that was supposed to *warn* about this class is the third
instance.

**This was my fault, not yours.** Your package (`spawns/15-context.md:79-82`) asked for
residual (i) only; I added the residual-(ii) requirement to the task file after you had
already run. You satisfied your package.

## Required fix — comment only

1. **Keep residual (i) exactly as written.** It is correct and complete.
2. **Add residual (ii):** the coercion closes only the divergences **SQLite** caused. Name
   the three survivors and the real reason:
   - `intValue "0123"` and `intValue "+123"` lose their spelling in `_attr_value`'s
     `int(...)` call, in Python, before SQLite sees anything.
   - `doubleValue 42.0` cannot be fixed by changing `_attr_value` **at all** — the
     evaluator established this and I verified it: `json.loads` has already produced a
     Python `float` before `_attr_value` runs, and `_attr_value` returns it untouched.
     Recovering `'42'` would need `json.loads(..., parse_float=str)` at the body-parse
     site, which would change `asDouble` cost values and `timeUnixNano` globally. Arguably
     it is not a defect at all: if the producer sent the number `42.0`, `'42.0'` is the
     faithful spelling and a transcript claiming `'42'` is asserting a different id.
3. **Say plainly that the fix is partial.** A reader must not close this file believing the
   class is closed.
4. **Remove or correct the `'123' from intValue "0123"` example.** Use only spellings SQLite
   actually produced: `'1'` from `boolValue true`, and `'1.0e+20'` from `doubleValue 1e20`.

## Write fence — unchanged

```
billing/otel/receiver.py
```

Comment text only. Do **not** touch the coercion itself, `_attr_value`, the body-parse
site, or anything else. Nothing under `tests/`, nothing in `otel_store.py` or
`transcript.py`.

## Model

requested: claude-sonnet-5 · tier: light · rotation: cycle 1 (resumed, no rotation)

## Rules

- Comment-only diff. `git diff` must show no change to any executable line.
- Do not add a per-type formatting branch, a TODO that implies someone should "finish" the
  three survivors without stating the `parse_float` consequence, or a claim that the
  remaining cases are unreachable in production without also saying they are unfixed.
- Re-run the five-file selection and confirm it is still **8 failed, 166 passed** with the
  same eight names. A ninth is a finding.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Comment (verbatim, final text)
[The whole comment as it now stands.]

## Verification
[`git diff billing/otel/receiver.py` -> confirm no executable line changed, and say how you
checked.]
[The five-file pytest line -> result and the eight names.]

## Anything else the fix touched
["None" is valid.]

### Footprint
files_read: <N> (~<C> chars)
```
