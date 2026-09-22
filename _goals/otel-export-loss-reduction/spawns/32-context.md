You are the test-writer subagent. Read: .claude/agents/test-writer.md

CURRENT_DATETIME: 2026-09-21T13:20-04:00

## Task

One regression test for criterion 06.13 in
`_goals/otel-export-loss-reduction/06-otlp-session-id-coercion.md` (read it for the exact
spec), plus the matching `tests/COVERAGE_MAP.md` row. `_attrs` in
`billing/otel/receiver.py` was just fixed to drop `None`-valued keys entirely rather than
ever returning them, closing a duplicate-attribute-key collapse that let a valid
resource-level `session.id` be overwritten by a later unparseable occurrence of the same
key within one attribute list.

## The test

Add to `tests/test_receiver_health.py`, near the existing `test_06_ac12_*` tests (same
family — this is the instance one level upstream of what those tests cover):

**`test_06_ac13_duplicate_session_id_key_in_one_list_keeps_first_valid_occurrence`**

Drive the real `/v1/metrics` -> `/v1/transcript-usage` HTTP path (not `_attrs`/`_common`
directly with hand-built dicts — match the standard `test_06_ac12` already set). Two cases,
either as one parametrized test or two functions:

1. **Resource-level duplicate.** A `resourceMetrics[].resource.attributes` list containing
   `session.id` **twice** — once as a valid `stringValue` UUID, once (in either order) as
   an unrecognized wrapper (`arrayValue` is sufficient; you don't need all four again,
   `test_06_ac12` already covers the wrapper-shape breadth). Assert the stored
   `token_usage.session_id` is the UUID, not `'unknown'`.
2. **Datapoint-level duplicate**, same shape, but the duplicate pair lives in the
   datapoint's own `attributes` list instead of the resource's.
3. For at least one case, **prove the ordering doesn't matter** — test both
   valid-then-unparseable and unparseable-then-valid within the same list.
4. Then, same as `test_06_ac12`, follow up with a `cli` transcript record for that same
   UUID session and assert it's rejected `session_has_otlp` with row counts over both
   tables unchanged before/after — the actual double-billing check, not just the
   stored-value check.
5. **Prove it would have failed pre-fix.** Either reason through the mechanism directly
   (a plain dict comprehension collapses duplicate keys last-wins, so the unparseable
   occurrence would have won and produced `None`, which `_common`'s existing merge-level
   filter — added the cycle before this one — can't help with because the value was
   already gone before `_common` ever saw it), or reproduce the pre-fix `_attrs` standalone
   in your test file's setup (not the repo) the way earlier cycles have done. State which
   approach you took and show the result.

## `tests/COVERAGE_MAP.md`

Add one row for criterion 06.13 citing the new test. Re-derive the file's own summary
counts after adding it — this file has regressed from stale counts twice already in this
goal; don't trust the count from before your edit, recompute it.

## Write fence

```
tests/test_receiver_health.py
tests/COVERAGE_MAP.md
```

Nothing else.

## Model

requested: claude-sonnet-5 · tier: light · rotation: n/a

## Rules

- Do not weaken an assertion to make it pass.
- `tmp_path`-scoped stores, no live network.
- Run the full suite at the end. Must be green, count = 428 + however many new test
  functions/parametrizations you add.
- Grep every node id you write against the actual collected suite before finishing —
  don't trust a name you typed from memory.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Test
[The test(s), verbatim key assertions.]

## Pre-fix-failure proof
[Which approach, and the result.]

## Coverage map
[The new row, and the re-derived summary counts.]

## Verification
[Full suite -> result.]

### Footprint
files_read: <N> (~<C> chars)
```
