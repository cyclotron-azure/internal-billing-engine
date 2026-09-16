Task 03 fix cycle 1 — resumed implementer. Write fence unchanged: `billing/reconcile.py`.

Evaluator verdict NEEDS FIXES. All 18 criteria verified; 2 blocking findings, both about the
legibility of the rendered output (which is this task's deliverable), plus 3 cheap minors in
the same functions.

## BLOCKING 1 — gap figures print outside the exact-integer column

`_print_funnel`, the two `_wrap(f"    gap {_pair(...).strip()} ...")` lines. `.strip()` leaks
11 spaces of internal column padding into prose:

```
    gap 7.5M       7,505,400 not received
    gap 0               0 not received
```

Two unexplained numbers with a gulf between them. The requirement names these rows
specifically ("including both `gap` figures") and asks for a right-aligned exact column.

Fix: render as a single inline token — `f"    gap {ftok(n)} ({n:,}) {suffix}"` — or keep the
pair in the same `PAIR_W` column the two rows above already use. Either is acceptable;
inline is simpler and reads better in prose.

## BLOCKING 2 — the `partial` state prints a false anomaly

`_print_dedupe`'s `counts_outside_measurement` branch gives state 3 the same alarm sentence
as states 1-2:

```
!! Counting began during this window, at 2026-07-15T08:30:00Z, so the counts below are a
LOWER BOUND -- yet 10 drop(s) dated inside this window were recorded (a replayed export, or
an interrupted first write).
```

Self-contradictory. In `partial` the epoch says part of the window *was* counted, so drops
dated inside it are entirely expected — `LOWER BOUND` already carries the real caveat. The
`!!` prefix plus an asserted cause turns a normal mid-window counting start into an anomaly
the reader will go chase.

Fix: branch on `measurement == "partial"` and print that qualifier alone (no `!!`, no
replay/interrupted-write clause). Reserve the replay/interrupted-write sentence for states
1 and 2, where the epoch genuinely contradicts the presence of counts.

## MINORS (all in the same two functions, do them)

3. `__cost__` prints as a row among real token types with no gloss; a reviewer cannot tell it
   is the cost-row sentinel. Label it `__cost__ (cost rows)` or footnote the section.
4. State 3 with an **empty** `by_type` prints "so the counts below are a LOWER BOUND." with
   nothing below it. Reword for the empty case.
5. `_dedupe_qualifier`'s `epoch is None` test: make it `not epoch`, consistent with the guard
   you already fixed. (`epoch == ""` currently falls through to state-2 wording and renders
   "(at )". Unreachable today.)

## Not in scope

Finding 6 — the banner and `!! No analytics rows for [...]` line can exceed 108 chars with
long emails. Both are on the "stays unchanged" list. Leave them.

## Rules

Unchanged from your original package. Stdlib only; consume task 02's functions, never
recompute; don't touch `ftok()`/`pct()`; both error paths stay byte-identical; `store.close()`
on every return path; rungs 1-2 only, targeted command
`python -m pytest tests/test_otel_store.py -q`.

## Output

Terse — the user is token-constrained.

```
MODEL: <model>
STATUS: completed | blocked

## Fixes applied
[One line each for blocking 1, blocking 2, and minors 3-5.]

## Evidence (required, verbatim, but ONLY these)
1. The two COVERAGE FUNNEL gap lines, before and after.
2. The DEDUPE DROPS block in state 3 (partial) WITH drops -- showing no false anomaly.
3. The DEDUPE DROPS block in state 2 WITH drops -- showing the replay sentence is retained
   where it IS warranted.
4. The DEDUPE DROPS block in state 3 with EMPTY by_type -- showing no dangling reference.

## Width re-check
[Max line length and confirmation every rule line is still exactly 108.]

## Verification
`python -m pytest tests/test_otel_store.py -q` -> [result]

### Footprint
files_read: <N> (~<C> chars)
```
