You are the evaluator subagent. Read: .claude/agents/evaluator.md

Fresh spawn. CURRENT_DATETIME: 2026-09-16T16:20-04:00

Also read `.claude/skills/task-criteria/SKILL.md` and apply it.

## Task

Evaluate task 01 of the `otel-export-loss-reduction` goal against its 7 acceptance
criteria. Verdict: **PASS**, **PASS (with notes)**, or **NEEDS FIXES** / **REJECT**.

`eval_depth: light` — this is a six-file config-and-docs change with no new code. Keep it
proportionate. Do not re-audit the goal; Phase 3 is closed.

## Files to Read

- `_goals/otel-export-loss-reduction/01-export-interval.md` — the task, its 10
  requirements and 7 criteria
- `_goals/otel-export-loss-reduction/spawns/04-report.md` — the implementer's report
- The six changed files, via `git diff`

## Verify, do not trust

The report's claims are the thing under test. In particular:

1. **Criterion 5 is the one most likely to be wrong.** It requires that no `60s`/`60000`
   remains in a sentence describing the *current* interval, while historical and unrelated
   uses of `60` are explicitly to be **left alone**. The report states
   `grep -n "60000\|60s" README.md deploy/README.md` returns **no matches at all**.
   Confirm that, and then judge whether anything legitimate was removed — e.g. a reference
   to Claude Code's own 60s *default*, which is still 60s and which the task told the
   implementer not to touch. Zero matches is a slightly suspicious result for a file that
   documents an override.
2. **The `README.md:88` edit is outside the Network bullet.** The report changed "give it a
   minute before checking" to "give it a few seconds". `README.md` is in the write fence so
   this is permitted, but judge whether it is correct and whether "a few seconds" is
   accurate for a 10s interval — a reader following it may check before the first flush.
3. **The troubleshooting row rewrite changed the *remedy* column.** It previously advised
   lowering the interval; it now says the split is "not worth further tightening". The task
   required only that it stop advising a lowering of an already-lowered value and that it
   state the new window. Judge whether replacing an actionable remedy with "expected" is a
   faithful correction or an over-reach that removes information a reader needed.
4. Confirm `deploy/dev-selftest.sh` is **byte-unmodified** and that
   `client-package/configure.py`'s var-name list is untouched.
5. Confirm the value is a JSON **string** in all four sources, and that `install.sh`'s
   emitted block still parses.
6. Confirm no file outside the six-file write fence was changed by this task.
   `_goals/reconcile-coverage-diagnostics/orchestration-log.md` was already modified before
   the task began — that is pre-existing, not a fence violation.
7. Re-run the targeted test selection yourself rather than accepting `32 passed`.

## Rules

Evaluate only — **no repository writes**. Scratch files in your scratchpad, never `data/`.
Do **not** run the full suite; the orchestrator runs it at Phase 5.
Model: claude-opus-5 · tier: frontier.
Keep the report compact — findings over narration.

## Output

```
VERDICT: PASS | PASS (with notes) | NEEDS FIXES | REJECT
MODEL: <model>

## Criteria
[One line per criterion 1-7: MET / NOT MET + how you verified it.]

## The four judgment calls
[Your ruling on items 1, 2, 3 above, plus anything else the implementer decided rather
than was told.]

## Fence
[Clean / violated.]

## Findings
[BLOCKING / NON-BLOCKING, 3 lines max each. Only what must be acted on.]

### Footprint
files_read: <N> (~<C> chars)
```
