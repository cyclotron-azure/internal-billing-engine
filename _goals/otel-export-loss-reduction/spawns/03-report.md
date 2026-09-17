CONDENSED STUB (token-constrained session). Full report in transcript.

VERDICT: NEEDS REVISION -- but ONE defect, mechanical, working form proven.
MODEL: claude-opus-5
Evaluator's own framing: "scope the escalation as 'one requirement bullet in
02-store-reads.md', not as a broken goal. Everything else closes."

## Part C -- CLOSED
All three requirements present and correctly reasoned. cr.13 now forces the fixture to set
examined_mtime to each file's real mtime; cr.14 carries both halves. Nothing left to attack.

## Verified this cycle (empirically, with setlimit)
- A naive two-arm UNION binds the chunk twice: 500 ids x 2 arms + 2 usage_source binds =
  1002 parameters. CONFIRMED raises OperationalError "too many SQL variables" at
  conn.setlimit(SQLITE_LIMIT_VARIABLE_NUMBER, 999).
- A single-bind VALUES CTE covers both tables in one statement with 500 parameters and
  returns both the token_usage-only and cost_usage-only session correctly at a 999 cap.
- This machine: sqlite3 3.49.1, cap 32766 -- THE FAULT IS INVISIBLE IN DEV.
- C1 propagation CONFIRMED complete across 02 (:34-39, :54-65, cr.13/14), 03 (:155-160),
  04 (:222-227), goal.md:77, 05 mutation (f) + vacuous-fixture trap.
- C2/C3/NB4/NB5 CONFIRMED landed. Counts CONFIRMED 7+14+19+18=58 as of cycle 3 start.

## BLOCKING-1 (silent-no-op, host-conditional; no wrong bills)
02-store-reads.md:70-77 -- the UNION-per-chunk requirement and the 500-id chunk constant
were jointly self-defeating: the bullet that existed to prevent "too many SQL variables"
guaranteed it on exactly the older builds it named. Traced consequence: guard raises ->
task 02 forbids swallowing sqlite3.Error -> receiver.py:379-387 rolls back and re-raises ->
do_POST returns no response -> sweeper reads transport_fail and never advances state
(:735-738) -> CLI backfill retries forever, always-exit-0 hides it. Desktop unaffected.
Most likely to first fire during the replay, where batches are full.
Fix given verbatim (VALUES CTE, bind once, keep 500). Halving does NOT work cleanly:
499x2+2 = 1000. Largest safe two-IN chunk is 498. Also: add a task 05 assertion that the
guard survives setlimit(999) -- the only way this is catchable in CI on a modern build.

## NON-BLOCKING (all cosmetic)
N2 chunk rationale misstates the production bound: MAX_BATCH_SIZE = 500 caps the caller at
   500 ids, so the sweeper cannot exceed it. Justify by the public unbounded-iterable
   contract instead.
N3 task 02 criteria 2 and 3 say "the table" singular now that the reader spans two.
N4 put the intended-volume numbers in state, not only stdout -- the hook's output goes
   nowhere anybody reads on a laptop.

## Ruling on the dry-run rebuttal
"Your rebuttal holds; I withdraw the two-step." A SessionEnd hook on a fleet has no
operator to gate anything, and a gate nobody answers is worse than none. Notes the
orchestrator took the half carrying the diagnostic value -- a pre-POST volume log would
have made C2 visible at the moment it happened.

## Devil's advocate
Remaining live steelman (sequencing preference, NOT a blocking defect): the replay's
correctness now rests on four interacting guards (transcript_key, two-table session
exclusion, quarantine, state reset), and BLOCKING-1 is evidence that each fix to that
lattice can introduce a fault elsewhere in it. Shipping 01-03 first and holding Part C for
its own goal would let the guards be proven against future sessions before being pointed at
all of history.
Load-bearing assumption now visible: that the production sqlite3 build behaves like dev --
false for exactly the limit this task reasons about, and nothing in the repo pins it.
Pre-mortem: replay runs, receiver throws "too many SQL variables" on the first full batch,
sweeper retries forever without advancing state, always-exit-0 means nobody ever sees it.

### Footprint
files_read: 6 (~72000) this cycle; 26 (~369000) cumulative / commands_run: 7 this cycle
