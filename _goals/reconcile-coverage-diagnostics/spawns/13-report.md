MODEL: claude-sonnet-5
STATUS: completed

## Files written

- tests/test_dedupe_counter.py -> 15 tests (task 01 criteria 1-14; criterion 15 is command-output, correctly excluded)
- tests/test_reconcile.py -> 54 tests (task 02 criteria 1-16, task 03 criteria 1-16 incl 7b/7c, plus regression coverage for the --email and org-wide run() paths that shipped untested)
- tests/COVERAGE_MAP.md -> H1/preamble generalized to an index, existing per-goal content untouched, new section appended with sub-tables for tasks 01-03

## Coverage

69 tests, ZERO GAPs -- every criterion in tasks 01-03 maps to a test. Two items intentionally not verbatim-pinned per the orchestrator's deviation (Phase 5 changes both): the partial-with-empty-by_type sentence, and the __cost__ row's column offsets. Both covered by wording-independent assertions instead.

## Traps (all four handled)

- drops=0 residue: asserts through dedupe_drops() must be {}, never SELECT COUNT(*).
- second-granular last_seen: monkeypatches otel_store._now with a strictly-increasing fake clock rather than sleeping.
- dedupe_epoch() sharing the FROM meta shape: matches the exact insert-path SQL 'SELECT 1 FROM meta WHERE key=?' and never calls dedupe_epoch() inside the counted window.
- criterion 01.10 off-by-one: asserts len(calls) == 1, not 0.

## Discovery worth keeping

sqlite3.Connection.execute cannot be monkeypatched -- immutable C type, both instance- and class-level assignment fail. Worked around with an _ExecuteSpy delegating wrapper swapped onto store.db, which IS a plain Python attribute. Used for criteria 10, 13 and 14. Anyone writing future store tests will hit this.

## Verification

- tests/test_reconcile.py + tests/test_dedupe_counter.py -> 69 passed
- tests/test_otel_store.py -> 27 passed
- git diff --stat tests/test_otel_store.py -> empty (unmodified)

## Failures found in the implementation

None. All 69 tests pass against the shipped billing/ code as-is.
