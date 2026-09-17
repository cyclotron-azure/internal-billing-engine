You are the evaluator subagent. Read: .claude/agents/evaluator.md

Fresh spawn. CURRENT_DATETIME: 2026-09-16T16:20-04:00

Also read `.claude/skills/task-criteria/SKILL.md` and apply it.

## Task

Evaluate task 02 of the `otel-export-loss-reduction` goal against its **15** acceptance
criteria. Verdict: **PASS**, **PASS (with notes)**, or **NEEDS FIXES** / **REJECT**.

`eval_depth: full`. This is the goal's contract task. `sessions_with_otlp_rows` is the
guard that decides whether a transcript row gets billed, and two downstream tasks build
against these signatures. A wrong answer from it either double-bills a client or silently
discards recoverable usage.

## Files to Read

- `_goals/otel-export-loss-reduction/02-store-reads.md` — the task, its requirements and
  its 15 criteria, with the reasoning carried inline
- `_goals/otel-export-loss-reduction/spawns/05-report.md` — the implementer's report
- `billing/otel/otel_store.py` — via `git diff` and in full where needed

## Verify by execution, not by reading the report

**The report verified several criteria by "manual reasoning" rather than by a test**, and
no tests exist for these methods yet (task 05 writes them). That makes independent
behavioral verification your job, not an optional extra. Write scratchpad scripts against
temp databases — never `data/` — and actually run the following:

1. **Criterion 13, the double-billing criterion.** A session whose only OTLP row is in
   `cost_usage`, created through `insert_cost_datapoint` **alone**, must be returned.
   Build it yourself. The report claims `{'sess-3'}`; reproduce it independently.
2. **Criterion 5 — zero queries on empty input.** The report asserts a short-circuit.
   Prove it with an execute-counting spy. Note `sqlite3.Connection.execute` **cannot** be
   monkeypatched (immutable C type); use a delegating wrapper swapped onto `store.db`, the
   pattern at `tests/test_dedupe_counter.py:57`.
3. **Criteria 6 and 7 — statement counts.** 1200 distinct ids with 3 present must return
   those 3 in exactly 3 statements; 600 copies of one id must be 1 statement. Count them.
4. **Criterion 15 — the parameter cap.** Independently apply
   `conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)` and run a full 500-id chunk.
   Then **count the actual parameters bound** in the statement the code issues and confirm
   the claimed 502. This machine's real cap is 32766, so this is the only way the defect
   class is observable here.
5. **Criterion 9 — `entrypoint IS NULL`.** The OTLP row must be created through
   `insert_datapoint`, not raw SQL. Confirm the code has no `entrypoint` predicate.
6. **Criterion 11 — writes nothing.** Spy for write verbs and `commit()`, plus a full-file
   SHA-256 after commit and close. Do **not** accept `PRAGMA data_version` or file size as
   evidence — both are unchanged across a same-connection `INSERT` + `commit()`.
7. **Criterion 4 and 14 — the column and the table.** A row with an old `ts` but a fresh
   `ingested_at` must read as fresh, and a `cost_usage` row newer than every `token_usage`
   row must be reflected. These are the assertions that fail if someone narrows the reader.

## Also scrutinize

- **`git diff` must show 0 deletions** and no altered pre-existing line. The report claims
  163 insertions / 0 deletions — verify, and confirm `dp_key`, `transcript_key`, `SCHEMA`,
  `_migrate`, `insert_datapoint`, `insert_cost_datapoint`, the transcript insert path and
  the `dedupe_drops` counter are all byte-unmodified.
- **`sqlite3.Error` must propagate**, not be swallowed. The task is explicit that this
  differs from the `dedupe_drops` counter's deliberate swallowing. Check for a bare
  `except`.
- **`last_ingest_at`'s `MAX(MAX())` shape.** `MAX(ingested_at)` over an empty table yields
  NULL; confirm the outer `MAX` over two NULLs returns `None` and not something else, and
  that a subquery without an alias is valid on the sqlite3 build in use.
- No new connection, no `check_same_thread`, no WAL pragma, no pool, no threading.
- Neither method reads or returns the raw `repo` column.
- Standard library only; no new import.
- Docstrings state all three things the task required: the `ingested_at`-vs-`ts`
  distinction, the `IN ()` hazard, and the parameter-cap arithmetic.
- Signatures are frozen for downstream consumers — flag anything a consumer could
  misread, including the bare `-> set` return annotation and whether `session_ids` really
  accepts any iterable (a generator would be consumed twice if the code iterates it more
  than once — **check this specifically**, it is a realistic bug in dedupe-then-chunk code).

## Rules

Evaluate only — **no repository writes**. Scratch files in your scratchpad, never `data/`.
Do **not** run the full suite; the orchestrator runs it at Phase 5.
Model: claude-opus-5 · tier: frontier.
Keep the report compact — findings over narration, no restating the task file.

## Output

```
VERDICT: PASS | PASS (with notes) | NEEDS FIXES | REJECT
MODEL: <model>

## Criteria
[One line per criterion 1-15: MET / NOT MET + how you verified it. Say "executed" or
"read only" for each so it is clear which were proven behaviorally.]

## Independent reproductions
[The results of items 1-7 above, with the numbers you measured — especially the actual
bound-parameter count.]

## Diff integrity
[0 deletions / not. Frozen symbols byte-unmodified / not.]

## Contract risks for downstream
[Anything task 03 or 04 could misread, including the generator question.]

## Findings
[BLOCKING / NON-BLOCKING, 3 lines max each.]

### Footprint
files_read: <N> (~<C> chars)
```
