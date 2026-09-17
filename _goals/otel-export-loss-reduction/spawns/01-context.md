You are the evaluator subagent. Read: .claude/agents/evaluator.md

Fresh spawn. CURRENT_DATETIME: 2026-09-16T14:10-04:00

## Task

Phase 3 goal evaluation of `otel-export-loss-reduction`. Validate every task's
`## Acceptance Criteria` once, plus goal coherence. Verdict: **PASS**, **NEEDS REVISION**,
or **REJECT**.

Also read `.claude/skills/goal-criteria/SKILL.md` and apply it.

## Files to Read

- `_goals/otel-export-loss-reduction/goal.md`
- `_goals/otel-export-loss-reduction/01-export-interval.md`
- `_goals/otel-export-loss-reduction/02-store-reads.md`
- `_goals/otel-export-loss-reduction/03-receiver-health-and-cli-ingest.md`
- `_goals/otel-export-loss-reduction/04-sweeper-cli-backfill.md`
- `_goals/otel-export-loss-reduction/05-tests.md`
- `CLAUDE.md` — the five hard constraints
- The source files the tasks claim facts about: `billing/otel/otel_store.py`,
  `billing/otel/receiver.py`, `billing/otel/transcript.py`,
  `client-package/claude-transcript-usage.py`, and the four config sources

## Priorities — weight these above criterion formatting

1. **Verify the claimed source facts, do not take them on trust.** The previous goal in
   this repo lost two evaluation cycles to citations that were stale or to mocking seams
   that did not exist. Specifically confirm or refute:
   - `receiver.py` has no `do_GET` handler today.
   - The OTLP `claude_code.token.usage` datapoint really carries no per-request
     identifier. The goal's substituted design rests entirely on this. If a request id
     *is* available, say so — it changes the whole backfill approach.
   - `transcript.py` really overwrites `row["entrypoint"]` with the constant.
   - The sweeper really enumerates all of `projects/**/*.jsonl` and then filters by
     entrypoint, i.e. CLI transcripts are already read and discarded.
   - `entrypoint` really is NULL on OTLP rows (task 02 criterion 9 and the
     no-`entrypoint`-predicate requirement both depend on it).
   - The four config sources and two doc lines task 01 names are at the values it claims.
   - Whether any existing test asserts `60000` or `ALLOWED_ENTRYPOINT`'s single value —
     task 01 and task 03 both forbid editing tests, so a test that pins the old value
     means a task is unsatisfiable as written.

2. **The double-billing guard is the safety-critical path.** Session-level exclusion is
   the only thing preventing a backfilled CLI session that *did* flush OTLP from being
   billed twice on a client invoice. Attack it:
   - Is there an ordering, race, or partial-flush case the design misses that a test
     could not catch? The known-and-accepted residual is partially-lost sessions; the
     quarantine window is the stated mitigation for the SessionEnd/shutdown-flush race.
   - Is 900s defensible, or is there a documented flush behavior that makes it wrong?
   - Does any criterion pass for the wrong reason — in particular task 03's criterion 10?

3. **Testability.** Tasks 03 and 04 each require the clock to route through a patchable
   module-level helper, and task 05 lists six traps. Are there *further* traps that will
   make task 05 impossible or make a test pass for the wrong reason? `receiver.AUTH_TOKEN`
   being read at import time is already flagged — check for siblings.

4. **Write-set disjointness and dependency correctness.** No two tasks without a
   `depends_on` ordering may share a write path. Confirm, and confirm each `depends_on`
   is real rather than decorative.

5. **Criterion quality.** Each criterion verifiable, non-tautological, and pinning
   behavior rather than activity. The previous goal shipped two defective criteria: one
   tautological by construction (an identity that could not fail) and one ambiguous about
   its fixture. Look for both shapes here — especially task 02's criteria 6/7 (statement
   counts) and task 05's criterion 6 (mutation list).

6. **Scope.** Anything in a task not traceable to the Discovery Summary, and anything the
   user asked for that no task delivers. Note the user selected "persist `request_id`"
   and the goal substitutes a different design — judge whether the substitution is
   justified by the source facts and whether goal.md is honest about it.

## Rules

Evaluate only — **no repository writes**. Scratch files in your scratchpad, never `data/`.
Run targeted read-only commands freely; do **not** run the full suite.
Model: claude-opus-5 · tier: frontier.
Keep the report compact: findings over narration. Do not restate the task files.

## Output

```
VERDICT: PASS | NEEDS REVISION | REJECT
MODEL: <model>

## Source facts verified
[One line per item in priority 1: CONFIRMED / REFUTED + the evidence, file:line.]

## Double-billing guard
[Your attack on the design. State plainly whether you found a hole.]

## Testability
[Further traps, or none.]

## Write sets & dependencies
[Disjoint / not. Each depends_on real / decorative.]

## Criteria
[Only the defective ones, by task and number, with what is wrong and the fix.]

## Scope
[Drift, gaps, and your ruling on the request_id substitution.]

## Findings
[BLOCKING / NON-BLOCKING, 3 lines max each.]

### Footprint
files_read: <N> (~<C> chars)
```
