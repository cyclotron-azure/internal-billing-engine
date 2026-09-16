MODEL: claude-sonnet-5
STATUS: blocked -> resolved by orchestrator (see below)

## Code

1a. Shortened the label '__cost__ (cost rows)' (20 chars) -> '__cost__ (cost)' (15), keeping LABEL_W=18. Chose shortening over widening so RULE_WIDTH needed no recheck.
1b. Same label expression applied in the 'by day:' sub-table loop (:534).
1c. Replaced the 'elif measurement == "partial":' branch body with the evaluator's exact sentence; left _dedupe_qualifier's shared LOWER BOUND string untouched because the with-drops path still needs it verbatim.

## Docs

2a. otel_store.py bullet now lists dedupe_drops plus the one-clause epoch-provenance note (written by the insert path, not migration).
2b. reconcile.py bullet rewritten: exact-integer figures, UNMAPPED TOKEN TYPES, the four-state DEDUPE DROPS section, --by-surface/--daily/--detail, and the share-of-captured-not-coverage statement.
2c. Pilot Coverage bullet notes the per-day/per-surface breakdown so a receiver outage shows as a one-day cliff.

## Evidence

State 3 (partial) EMPTY by_type:
  'Counting began during this window, at 2026-07-15T00:00:00Z -- no duplicate datapoints were recorded from that instant onward, and any earlier in this window were never counted.'

State 4 (full) WITH drops -- __cost__ row now column-aligned:
  input                    120             120
  output                    30              30
  __cost__ (cost)            7               7

## Width

Max line 108; all rule lines == 108; RULE_WIDTH unchanged.

## Verification

1 failed, 95 passed. Failure: tests/test_reconcile.py::test_03_6_partial_state_names_epoch_and_says_lower_bound asserts 'LOWER BOUND' in out for _STATE_3, the partial+EMPTY-by_type fixture, which 1c's mandated text no longer contains.

## Escalation (correct call)

The agent applied the code exactly as instructed, left the out-of-fence test alone, and escalated rather than silently reinterpreting either side. It also correctly contradicted my context file, which had claimed the 69 tests avoided pinning this spot.

## Orchestrator resolution

Root cause is MINE, in two steps. (1) Criterion 03.6 was written as 'State 3 (partial) names the epoch instant and says the counts are a lower bound', which is ambiguous -- that phrasing only makes sense when counts exist, but _STATE_3 is the empty fixture. (2) I instructed task 04 not to pin this wording, it reported compliance, and I accepted the self-report without checking -- the same class of error as trusting task 03's unverified output claims.

Code is correct and stays. Criterion 03.6 disambiguated in the task file: with a non-empty by_type it must say lower bound; with an empty by_type it must say nothing was recorded from that instant onward. Test routed back to the test-writer that owns the file, to split the assertion across both fixtures.
