You are the evaluator subagent. Read: .claude/agents/evaluator.md

Fresh spawn. CURRENT_DATETIME: 2026-09-16T19:30-04:00

Also read `.claude/skills/task-criteria/SKILL.md` and apply it.

## Task

Evaluate task 04 of `otel-export-loss-reduction` against its **19** acceptance criteria.
Verdict: **PASS**, **PASS (with notes)**, or **NEEDS FIXES** / **REJECT**.

`eval_depth: full`. This task replays transcript history through a billing ingest path.

## Files to Read

- `_goals/otel-export-loss-reduction/04-sweeper-cli-backfill.md` — the task, its
  "Background — the state file, exactly as it works today" section, and its 19 criteria
- `_goals/otel-export-loss-reduction/spawns/14-context.md` and `16-context.md` — the
  original package and the fix-cycle-1 delta
- `client-package/claude-transcript-usage.py` via `git diff`, and `deploy/` to confirm
  byte-identity
- `billing/otel/transcript.py` — the server-side allowed set, reason strings, and the 900s
  constant (read-only)

## State

Fix cycle 1 removed Part C's `install_ts` reset after the implementer correctly flagged that
it could not coexist with `test_ac7e_forward_only_install_watermark`. The orchestrator
verified: the reset is gone, both copies share one sha256, `test_ac7e` passes unmodified,
and the five-file selection is **8 failed, 166 passed**.

## Verify by execution

1. **Criterion 3 is the one that matters most.** The natural implementation marks a
   quarantine-skipped session resolved, which makes every CLI session ship *never* while
   looking like success. Assert `resolved` membership and `examined_mtime` **by name**, then
   advance a frozen clock past 1800s and confirm the record ships. The implementer's
   Evidence (d) claims `resolved: []` / `examined_mtime: null` then shipping — reproduce it
   independently.
2. **Criteria 5 and 6 are the deliberate asymmetry.** A missing/non-string entrypoint and
   an out-of-set entrypoint must be skipped **and marked resolved** (permanent). Only the
   quarantine skip leaves state unadvanced. Assert the `resolved` membership positively —
   "produces no record" alone cannot tell these apart from criterion 3.
3. **Criterion 12 — `too_recent` is non-resolving, everything else resolves.** Mock an HTTP
   200 whose rejected list carries one `too_recent` and one `session_has_otlp`; the first id
   must be absent from `resolved` and the second present. One test, both halves.
4. **Criteria 13, 14, 19 — the replay.** 13: fixture must set `examined_mtime` to each
   file's real mtime and `install_ts` *earlier* than the fixtures, then assert both cleared,
   the flag set, groups shipped, a second run shipping nothing, **and `install_ts`
   unchanged**. 14: with the POST mocked to raise after the state write, the flag persists
   **and** the remainder still ships on the next run. 19: a `cli` group predating
   `install_ts` must not ship even on the replay run — this is the criterion that fails if
   the watermark reset is reintroduced.
5. **Criterion 15 — the replay is a state reset, not a second code path.** Confirm there is
   exactly one shipping path, and that a too-recent group is still withheld and a
   `claude-web` group still skipped *during* the replay run.
6. **Criterion 16 — recovery is measurable.** Assert the tallies' **values** for a known
   fixture, not merely that the keys exist, plus the pre-POST intended-volume numbers.
   Confirm the volume numbers are persisted in `state`, not only logged to stdout.
7. **Criterion 9 — always exit 0.** Include the read-only state-directory case and a
   malformed-timestamp case, and confirm neither raises out of the hook.
8. **Criterion 4 — desktop is not quarantined.** A `claude-desktop` transcript aged 60
   seconds still ships.

## Also confirm

- The flag is written **before** the first POST. Order is the whole crash-safety property.
- `install_ts` and the `:543-545` watermark check are untouched, and the module docstring
  plus the Part C comment now explain why the reset was deliberately *not* done — a future
  reader must not restore it as an oversight.
- Enumeration (`find_transcript_files`) unchanged; POST target unchanged; payload shape
  unchanged beyond the entrypoint value; no state key renamed or removed.
- No placeholder substituted for a missing `session_id` — the hook must still pass
  `terminal_row["sessionId"]` verbatim. `receiver.py:190`'s `or "unknown"` idiom must **not**
  be mirrored here; doing so would make every such record match "session already has OTLP
  rows" and be rejected forever. This is a requirement, so verify it.
- The client window is **1800s**, deliberately twice the server's 900s.
- Stdlib only, no import from `billing/`, both copies byte-identical.
- The only remaining hook-side failures are `test_ac1_only_desktop_entrypoint_ships`
  (`:109-122`) and `test_ac6_running_twice_ships_each_record_once` (`:489-503`), both owned
  by task 05. A third is a finding.

## Rules

Evaluate only — **no repository writes**. Scratch files in your scratchpad, never `data/`
and never the real `~/.claude`. Do **not** run the full suite.
Model: claude-opus-5 · tier: frontier.
Keep the report compact — findings over narration.

## Output

```
VERDICT: PASS | PASS (with notes) | NEEDS FIXES | REJECT
MODEL: <model>

## Criteria
[One line per criterion 1-19: MET / NOT MET, "executed" or "read only".]

## Independent reproductions
[Results of items 1-8 with measured numbers.]

## Replay safety
[Your judgment on the two-item reset, flag-before-POST, permanence, and pre-install
exclusion. State plainly whether a replay can bill anything twice.]

## Diff integrity
[Byte-identity, untouched mechanisms, state-key additions only.]

## Findings
[BLOCKING / NON-BLOCKING, 3 lines max each.]

### Footprint
files_read: <N> (~<C> chars)
```
