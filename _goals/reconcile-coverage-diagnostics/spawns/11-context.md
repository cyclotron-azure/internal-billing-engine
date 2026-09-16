You are the implementer subagent. Read: .claude/agents/implementer.md

Task 03 fix cycle 2. Fresh spawn, rotated model. CURRENT_DATETIME: 2026-09-16T11:30-04:00

Write fence: **`billing/reconcile.py` only.** Stdlib only. Do not touch tests, `otel_store.py`,
or `README.md`.

## State

Fix cycle 1 applied 2 of 5 required changes and then returned without reporting. Verified by
the orchestrator against the file:

- DONE: funnel gap lines now render inline — `_wrap(f"    gap {ftok(gap1)} ({gap1:,}) not received")`.
- DONE: `_dedupe_qualifier`'s falsy-epoch test is now `not epoch`.
- **NOT DONE: the three below.** Apply exactly these, nothing else.

## 1 (BLOCKING) — the `partial` state still prints a false anomaly

In `_print_dedupe`:

```python
        if dd["counts_outside_measurement"]:
            sentence = (f"!! {qualifier} -- yet {total:,} drop(s) dated inside this "
                        "window were recorded (a replayed export, or an interrupted "
                        "first write).")
```

`counts_outside_measurement` is True whenever `by_type` is non-empty and
`measurement != "full"` — which includes `"partial"`. So a `partial` window with drops renders:

> `!! Counting began during this window, at 2026-07-15T08:30:00Z, so the counts below are a LOWER BOUND -- yet 10 drop(s) dated inside this window were recorded (a replayed export, or an interrupted first write).`

Self-contradictory. In `partial` the epoch says part of the window *was* counted, so drops
dated inside it are entirely expected, and `LOWER BOUND` already carries the caveat. The `!!`
plus an asserted cause manufactures an anomaly a reviewer will go chase.

Fix: gate the alarm sentence on `measurement == "none"` as well, so only states 1 and 2 — where
the epoch genuinely contradicts the presence of counts — get it. `partial` with drops prints
its qualifier alone, no `!!`.

## 2 (minor) — `__cost__` needs a gloss

`__cost__` prints as a row among real token types (`input`, `cacheRead`, …) and is folded into
the drop total with nothing to say it is the cost-row sentinel rather than a token type. Add a
tiny helper that renders it as `__cost__ (cost rows)` and use it in **both** row loops in
`_print_dedupe` (the `by_type` loop and the `by day:` loop). Check `LABEL_W` is wide enough for
the longer label; widen it only if needed, and if you do, re-confirm the width invariant below.

## 3 (minor) — dangling "the counts below" when there are none

`_dedupe_qualifier` returns "…so the counts below are a LOWER BOUND" for `partial`, but
`_print_dedupe`'s empty-`by_type` path prints that same string with nothing below it.

Fix: give `_dedupe_qualifier` a `has_counts` flag (or equivalent) so the `partial` wording drops
the "counts below" clause when `by_type` is empty, and say something true instead — e.g.
"…anything before that instant was never counted". Keep all four qualifier states pairwise
distinct; an evaluator asserts that.

## Invariants you must not break

- `RULE_WIDTH = 108`: every `===`/`---` rule line exactly 108, no output line over 108.
- All four measurement states stay pairwise distinguishable in text.
- A non-empty `by_type` still prints under **every** state — that is the whole point of the
  section; do not let this fix suppress counts.
- `ftok()` / `pct()` behavior unchanged; both error paths byte-identical; `store.close()` on
  every return path; no recomputation in print helpers; no `--json`, no `sys.exit`.
- Targeted command: `python -m pytest tests/test_otel_store.py -q`. Rungs 1-2 only; do NOT run
  the full suite.

## Output — terse, the user is token-constrained

```
MODEL: <model>
STATUS: completed | blocked

## Fixes
[One line each for 1, 2, 3.]

## Evidence (verbatim, ONLY these four blocks)
a) DEDUPE DROPS, state 3 (partial) WITH drops   -- must show no `!!` and no replay clause
b) DEDUPE DROPS, state 2 WITH drops             -- must still show the replay clause
c) DEDUPE DROPS, state 3 with EMPTY by_type     -- must not dangle "counts below"
d) DEDUPE DROPS, state 4 (full) WITH drops      -- must show the __cost__ gloss

## Width
[Max line length; confirm all rule lines == 108.]

## Verification
`python -m pytest tests/test_otel_store.py -q` -> [result]

### Footprint
files_read: <N> (~<C> chars)
```
