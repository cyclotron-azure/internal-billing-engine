You are the evaluator subagent, in **audit mode**. Read: .claude/agents/evaluator.md

Fresh spawn. CURRENT_DATETIME: 2026-09-21T13:40-04:00

## Task

Phase 5 final audit — **narrowly scoped confirmation pass**, not a fresh open-ended cycle.
Verdict: **APPROVED** or **ISSUES**.

## Why this cycle is scoped the way it is

Cycle 3 (three cycles ago in the ledger) returned ISSUES and escalated to the user per
this goal's `ladder: escalate` policy. Its own auditor gave an explicit, direct answer to
"is there an eighth instance, or has this hunt converged": the `_common`/`_attrs` merge
surface is now well-scrutinized and further search *there* specifically would be
diminishing returns — but the hunt had *relocated* twice already (fifth instance in the
fallback logic, sixth in the merge, seventh in the producer), so it wasn't safe to simply
stop without fixing the seventh.

The user approved exactly two things: apply the seventh instance's fix (the producer-level
`None`-drop in `_attrs`), and spin off an unrelated commit-atomicity bug the same audit
found in `ingest_metrics_payload` as its own separate follow-up task (already created,
`task_f183dcac`, explicitly out of this goal's fence).

**This audit's job is to confirm those two decisions were executed correctly** — not to
restart the open-ended "attack the fix that just landed" hunt a fourth time. That hunt's
own most recent finding said it had reached the point of diminishing returns in this exact
code; re-running it identically now would be ignoring that finding, not respecting it.

## What to verify

1. **The seventh-instance fix.** `_attrs` (`receiver.py:176`) now drops a key entirely
   when its parsed value is `None`, rather than ever returning `None` for it. Confirm by
   execution: a duplicate `session.id` key within one attribute list, in both orderings
   (valid-then-unparseable, unparseable-then-valid), at both resource and datapoint level,
   preserves the valid value. This is exactly what the new test
   `test_06_ac13_duplicate_session_id_key_in_one_list_keeps_first_valid_occurrence`
   (4 parametrized cases) checks — re-derive at least one case yourself rather than
   trusting the test alone.
2. **The overclaiming sentence is corrected.** `_common`'s merge-filter comment no longer
   says "this is the one place to fix it"; confirm the corrected text is honest about scope
   (protects the merge, does not claim exhaustive coverage of the file).
3. **`_common`'s merge-level filter was kept, not removed**, documented as deliberate
   defense-in-depth now that `_attrs` structurally can't return `None`. Confirm the
   reasoning is stated, not just the code.
4. **The follow-up task was correctly scoped out.** Confirm `ingest_metrics_payload`'s
   commit/rollback behavior was **not** touched by this fix cycle — that bug is explicitly
   the separate task's job, not this goal's.
5. **Coverage map**: re-derive the dead-id count yourself, independently, one more time.
   It has regressed twice before in this goal; verify it hasn't a third time. Also confirm
   criterion 06.13 has a mapped row.
6. **Full suite**: confirm 432 passed (428 + the 4 new parametrized cases). Run it yourself.
7. **`README.md`, `goal.md`, and the task files**: confirm nothing from cycles 1-3's fixes
   has regressed (spot-check, don't re-derive everything from scratch — that work was
   already independently verified three times over in this goal's ledger).

## What NOT to do

Do not go hunting for an eighth instance of the session-id normalization-asymmetry class
in `_common`/`_attrs`/the merge. That specific search already got a direct, considered
answer from the previous cycle: converged. If you notice something in the course of
verifying items 1-7 above, report it as a finding — but this cycle is not a mandate to
re-run the open-ended search from scratch a fourth time.

## Rules

Evaluate only — **no repository writes**. Scratch files in your scratchpad, never `data/`
and never the real `~/.claude`. Run the full suite once.
Model: claude-opus-5 · tier: frontier.
Keep the report compact.

## Output

```
VERDICT: APPROVED | ISSUES
MODEL: <model>

## Items 1-7
[One line each: confirmed / not, brief evidence.]

## Findings
[Only things you noticed incidentally while verifying 1-7, not from a fresh open-ended
hunt. BLOCKING / NON-BLOCKING, 3 lines max each, or "none".]

### Footprint
files_read: <N> (~<C> chars)
```
