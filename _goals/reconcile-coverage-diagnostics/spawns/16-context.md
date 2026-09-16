Task 04 fix cycle — resumed test-writer. CURRENT_DATETIME: 2026-09-16T12:40-04:00

Fence: `tests/test_reconcile.py`, `tests/test_dedupe_counter.py`, `tests/COVERAGE_MAP.md`.
**Nothing under `billing/`.** The product code is correct; every finding below is a test or
map defect.

The final audit ran **24 mutations** against a scratchpad copy of `billing/`. 20 were caught by
exactly the mapped test — genuinely strong work, and the three testability traps and seven hard
criteria all verified real. But **4 mutations escaped all 55 tests**, so the zero-GAP claim is
falsified. Close the gaps.

## BLOCKING

**B1 — `COVERAGE_MAP.md` has a dead node id and two unmapped tests.** Row 03.6 names
`test_03_6_partial_state_names_epoch_and_says_lower_bound`, which no longer exists (you split
it). The two real tests appear nowhere in the map. Of 63 mapped ids exactly 1 is dead and
exactly 2 tests are unreferenced. Fix the row to name both real tests. This matters because the
file promises a reviewer can spot-check any node id, and "GAPs: None" was certified against a
map that no longer matches the suite.

**B2 — criterion 03.10 is not actually tested (a real GAP).** `test_03_10` asserts only
`"DAILY" in out` and `"%" in day_line`; that `%` comes from the *coverage* column. Two mutations
pass all 55 tests: deleting the `tagged` **and** `billable` columns from every DAILY row, and
forcing DAILY `tagged` to `0` so billable always reads `0.00%`. `test_03_9` only parses truth
and captured, so it does not cover this either. Criterion 03.10 names the tagged and billable
columns explicitly. Assert their **values** for a known fixture — a row where tagged differs
from captured, so a forced-zero mutation fails.

**B3 — the `partial`-with-empty-`by_type` pair is too weak.** Replacing the whole mandated
clause with a bare `"Counting began during this window, at <epoch>."` passes everything. Task 03
criterion 6 makes that wording the substance of the criterion, not punctuation. Add one
assertion on a distinctive phrase — `"were never counted"` — alongside the existing
`LOWER BOUND`-absent check. Do not re-pin the full sentence.

## NON-BLOCKING (do these too; all small)

**N4 — `cache_creation_5m` has no effective pin on either new daily truth path.** Dropping it
from `analytics_claude_code_daily` or `analytics_user_daily` passes everything. Two causes: the
org-wide identity in 02.7 is tautological (task 02 made `analytics_claude_code_totals` a thin
wrapper that sums `analytics_claude_code_daily`, so `Σdaily == totals` cannot fail), and the
user-scoped fixture seeds no `cache_creation_*` at all. Fix: seed a **nonzero
`cache_creation_5m`** in the user-scoped fixture and assert an **absolute expected dict**, not
just the identity. Consider the same for the org-wide path.

**N5 — 03.13 counts `100.00%` occurrences.** `count == 3` holds only for the constructed
fixture; a realistic run produced four (a single-valued dimension makes its data row read 100%
too). Anchor the assertion to the three `TOTAL` lines instead of counting occurrences.

**N6 — four assertions constrain nothing.** `test_reconcile.py:217`
(`all("cacheCreation5m" not in str(v) for v in result["captured"])` iterates dict **keys**, so
it is true for any result — check the values); `:581-582` (`assert 1000+500+300+200 == 2000`
asserts Python's arithmetic, not the program); `:418`
(`not isinstance(result, type(iter([])))` is unreachable-false after the preceding
`isinstance(result, dict)`); and `test_03_7` matches the single character `"3"` rather than
`f"{n:,}"` as its `03_7b` sibling correctly does.

**N7 — `test_ac6` under-asserts criterion 01.6.** "Preserved byte-for-byte" and "no-op on second
open" are checked via one row's `tokens` value and a `COUNT(*)`. Compare the **column set and
types** before/after, and assert the schema is identical on reopen.

**N8 — `test_03_9`'s day-line filter is latently wrong.** `l.strip()[:4].isdigit() and
l.strip()[:10].count("-") == 2` would also match the DEDUPE `by day:` rows, whose column offsets
differ; it passes only because that fixture seeds no drops. Anchor on the DAILY section slice.

## Also

Your report said 69 tests; the audit counted **70** (15 + 55). Use the real number in the map.

## Rules

Do not weaken any assertion to make something pass. Do not touch `billing/`, `tests/conftest.py`
or `tests/test_otel_store.py`. If a strengthened test now fails against the shipped code, that
is a genuine finding — leave it failing and report it.

Run `python -m pytest tests/test_reconcile.py tests/test_dedupe_counter.py tests/test_otel_store.py -q`.
Do **not** run the full suite.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Fixes
[One line each: B1, B2, B3, N4, N5, N6, N7, N8.]

## Mutation self-check
[For B2, B3 and N4: state how you confirmed your new assertion actually fails when the
behavior it pins is broken. Temporarily break it in a scratchpad copy if you need to -- never
in the repo.]

## Verification
[The pytest line -> result. Final test count.]

## Any test now failing against shipped code
["None" is valid.]

### Footprint
files_read: <N> (~<C> chars)
```
