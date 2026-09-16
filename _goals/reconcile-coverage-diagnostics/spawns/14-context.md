You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-16T12:00-04:00

Cleanup + docs pass. Tasks 01-04 of `reconcile-coverage-diagnostics` are complete and passed
evaluation; full suite green at **330 passed**. This closes out three cosmetic findings and
syncs the docs. Phase 6 is merged into this spawn to save a subagent run — the user is
token-constrained.

## Write fence

```
billing/reconcile.py
README.md
```

Nothing else. Not `otel_store.py`, not any test file.

## Part 1 — three carried minors in `billing/reconcile.py`

All three were raised by task 03's evaluator, are non-blocking, and have exact fixes.

**1a.** `LABEL_W = 18`, but `_print_dedupe`'s `"__cost__ (cost rows)"` label is 20 chars, so
`{label:<LABEL_W}` expands and that one row's figure fields start 2 chars right of every other
row (exact column ends at 47 vs 45). Fix: set `LABEL_W = 20`, **or** shorten the label to
`__cost__ (cost)`. Pick one; if you widen `LABEL_W`, re-confirm the width invariant below.

**1b.** The `by day:` sub-table in `_print_dedupe` prints raw `__cost__` with no gloss, two
lines under a main table that now glosses it. Apply the same `label` expression in that loop.

**1c.** The `partial`-with-empty-`by_type` sentence still dangles. It currently reads
`"Counting began during this window, at {epoch}, so the counts below are a LOWER BOUND, and no
drops were recorded during it."` — "the counts below" when nothing is below, a LOWER BOUND on
an empty set, and "it" ambiguous between the window and the counted portion. The earlier fix
appended a clause instead of removing the one that dangles.

Use the evaluator's exact replacement, and note *where* it goes: build the sentence in
`_print_dedupe`'s `elif measurement == "partial":` branch rather than appending to
`_dedupe_qualifier`'s shared string, which the with-drops path still needs verbatim.

```python
    elif measurement == "partial":
        for line in _wrap(
                f"Counting began during this window, at {epoch} -- no duplicate "
                "datapoints were recorded from that instant onward, and any earlier "
                "in this window were never counted."):
            print(line)
```

### Invariants you must not break

- `RULE_WIDTH = 108`: every `===`/`---` rule exactly 108, no output line over 108.
- The four measurement-state qualifiers stay **pairwise distinct** in text.
- A non-empty `by_type` still prints its rows under **every** measurement state.
- `ftok()` / `pct()` unchanged; both error paths byte-identical; `store.close()` on every
  return path; no recomputation in print helpers; stdlib only.
- **`tests/test_reconcile.py` and `tests/test_dedupe_counter.py` must still pass.** They were
  written to avoid pinning exactly these three spots, so they should survive — but run them.

## Part 2 — `README.md` sync (it is ground truth per CLAUDE.md)

Three places are now stale. Keep the file's existing voice and density; do not restructure.

**2a.** The `otel_store.py` bullet enumerates the store's tables and omits the new one. Add
`dedupe_drops` (per-`(day, token_type, usage_source)` count of datapoints rejected as
duplicates) and the counting-start epoch in `meta`. The epoch's semantics are the point worth
one clause: it is written by the **insert path**, not by migration, so a store opened only by a
read-only consumer never acquires one — which is what lets reconcile distinguish "never
counted" from "counted, zero duplicates".

**2b.** The `reconcile.py` bullet describes the old single-percentage output. It now has:
exact integers beside every abbreviated figure; an `UNMAPPED TOKEN TYPES` section that prints
whenever a token type outside `CANON` appears; a `DEDUPE DROPS` section with four
measurement states; and `--by-surface`, `--daily`, `--detail` flags. Say plainly that the
surface breakdown is a **share of captured, not coverage**, because the Analytics truth side
carries no `usage_source`/`entrypoint`/`query_source` dimension to compare against — that is
the single most important thing a reader of this output needs to know.

**2c.** The pilot **Coverage** bullet (in the Phase 2 pilot section) should mention that the
funnel can now be broken down per-day and per-surface, so a receiver outage shows as a
one-day cliff instead of being averaged away.

Do **not** add a changelog, do not document `--json` or exit-code thresholds (they do not
exist), and do not touch `deploy/README.md` or `client-package/`.

## Verification

- `python -m pytest tests/test_reconcile.py tests/test_dedupe_counter.py tests/test_otel_store.py -q`
- Confirm the width invariant after your `LABEL_W` decision.
- Do **not** run the full suite; the orchestrator has it (330 passed).

## Model

requested: claude-sonnet-5 · tier: light

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Code (1a/1b/1c)
[One line each. State which LABEL_W option you chose.]

## Docs (2a/2b/2c)
[One line each.]

## Evidence (verbatim, ONLY these two)
a) DEDUPE DROPS, state 3 (partial) with EMPTY by_type
b) DEDUPE DROPS, state 4 (full) WITH drops, showing the __cost__ row aligned with the others

## Width
[Max line length; all rule lines == 108.]

## Verification
[The pytest line -> result.]

### Footprint
files_read: <N> (~<C> chars)
```
