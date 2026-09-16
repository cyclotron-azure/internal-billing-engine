You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-16T10:22:32-04:00

## Task

Execute task 01 of the `reconcile-coverage-diagnostics` goal: add a dedupe-drop counter
and a counting-start epoch to `billing/otel/otel_store.py`.

**Your specification is `_goals/reconcile-coverage-diagnostics/01-store-dedupe-counter.md`.
Read it in full first and follow it exactly.** It has 15 acceptance criteria and its
requirements are exhaustive — the evaluator that reviews your work checks every item.
That file went through three evaluation cycles; where it explains *why* a thing must be
done a certain way, that rationale is a recorded decision, not a suggestion.

This is the goal's **contract task**. Tasks 02, 03 and 04 build against the schema, the
meta-key constant, and the three read helpers you define here, so their names and shapes
are frozen by what you write.

## Requirements

All requirements are in the task file under `## Requirements`, organized as: Schema,
Migration, Counting-start epoch, Increment, Frozen read interface, and Constraints
restated in-task. Do not work from this summary — work from the file. The highlights,
so you know what you are walking into:

- A new six-column `dedupe_drops` table keyed `(day, token_type, usage_source)`, added to
  `SCHEMA` and migrated additively in `_migrate()`.
- `day` comes from the **dropped datapoint's own timestamp**, never wall-clock now.
- A counting-start epoch in `meta`, written by the **insert path** and never by
  `_migrate()`, stored as a UTC ISO8601 timestamp via the module's existing `_now()`.
- The epoch's in-memory guard **latches on confirmation, not on attempt** — read the
  "Why (a defect found in Phase 3 cycle 2 ...)" block before you write it. Two
  acceptance criteria (01.10 and 01.11) exist specifically to fail a latch-on-attempt
  implementation.
- The drop increment goes at the existing `cur.rowcount > 0` duplicate returns in
  `insert_datapoint` and `insert_cost_datapoint`, using the portable
  `INSERT OR IGNORE` + `UPDATE` pair — **not** `ON CONFLICT ... DO UPDATE`.
- Three read helpers: `dedupe_drops`, `dedupe_drops_by_day`, `dedupe_epoch`.

## Files to Read

Exactly as listed in the task file's `## Files to Read` section:

- `_goals/reconcile-coverage-diagnostics/01-store-dedupe-counter.md` — your spec. Read
  first, read fully.
- `billing/otel/otel_store.py` — the module you are editing. Read `SCHEMA`,
  `_existing_columns`, `_migrate`, `_now`, `_ns_to_iso`, `dp_key`, `transcript_key`,
  `insert_datapoint`, and `insert_cost_datapoint` in full before writing anything. Their
  docstrings carry recorded decisions you must not undo.
- `billing/otel/receiver.py` — read-only: the OTLP datapoint loop in
  `ingest_metrics_payload`, the transcript loop that calls `store.insert_datapoint(**row)`,
  the per-request `store.commit()` calls, the per-record error-handling constant, and the
  `rollback()` path in the transcript handler. These confirm why the counter must not
  raise and why the epoch must latch on confirmation.
- `billing/store.py` — the `set_meta`/`get_meta` pattern on the *other* store, as a style
  reference only. Do not copy the whole API over.
- `README.md` — the single-host/single-connection SQLite constraint and the
  `otel_store.py` bullet. Ground truth for this engine.
- `tests/conftest.py` — the `tmp_db_path` and `legacy_schema_db_path` fixtures, and
  `seed_otlp_rows` (a plain module-level function, **not** a pytest fixture), so you know
  what task 04 will test your work against.
- `.claude/skills/test-ladder/SKILL.md` — climb rungs 1–2 only.

## Write fence

```
billing/otel/otel_store.py
```

That is the **only** path you may create or modify in the repository. Notably:

- Do **not** modify `billing/otel/receiver.py`. Both ingest paths already route through
  the two insert methods, so your choke points cover both surfaces with zero receiver
  changes. If you conclude a receiver change is required, **stop and say so in your
  report** instead of making it.
- Do **not** modify `billing/reconcile.py` (task 02's fence) or any test file (task 04's
  fence). Task 04 writes the tests for your criteria; you are not writing them.
- Scratch scripts go in your session scratchpad directory, never in the repo and never in
  `data/`.

## Model

requested: claude-sonnet-5 · tier: light · rotation: n/a (first attempt)

## Rules

- **Stdlib only.** No third-party import may enter `billing/`. This is the single easiest
  way to break this codebase.
- **Single-host, single-connection SQLite.** Do not enable WAL, do not pass
  `check_same_thread=False`, do not add a connection pool, do not thread anything.
- Do not alter `dp_key`, `transcript_key`, the `request_id` validation in either insert
  method, or any existing column. Those carry extensive recorded rationale.
- Do not add a `request_id` column — explicitly out of scope for this goal.
- Do not `commit()` inside the increment or the epoch write; both ride the caller's
  transaction, which `receiver.py` already commits per request.
- Catch `sqlite3.Error` specifically around both the counter write and the epoch write,
  never bare `Exception`, and swallow it — losing a diagnostic count is acceptable,
  breaking billing ingest is not.
- Every change is additive. No existing store test may be modified to accommodate your
  work; if one fails, that is a regression in your implementation to fix.
- Climb test-ladder rungs 1–2 only. **Do NOT run `python -m pytest -q`** (rung 3) — that
  is the orchestrator's call at cycle end. Your targeted command is
  `python -m pytest tests/test_otel_store.py -q`.
- If a requirement seems wrong or impossible, implement nothing on a guess: report the
  conflict and what you would need.

## Output

Report in this shape:

```
MODEL: <the model you are actually running as>
STATUS: completed | blocked

## What changed
[Each edit to billing/otel/otel_store.py: what and why, by symbol name.]

## Acceptance criteria
[One line per criterion 1-15: how your implementation satisfies it, or NOT YET if it
depends on task 04's tests. Criterion 15 is the command below.]

## Frozen interface as implemented
[The exact signatures of the three read methods and the module constant's name and
value format, so tasks 02 and 03 build against reality.]

## Verification
- `python -m pytest tests/test_otel_store.py -q` -> [exact result line]
- Scratchpad evidence (required, paste verbatim):
  (a) a script that opens a tmp store, calls only a read method, and prints
      `dedupe_epoch()` -- must print None
  (b) a script that inserts one datapoint twice and prints the resulting `dedupe_drops`
      rows and `dedupe_epoch()`
  (c) a script that inserts once, rolls back, prints `dedupe_epoch()` (must be None),
      inserts again, commits, and prints `dedupe_epoch()` (must be set) -- this is the
      cycle-2 latch-on-confirmation behavior

## Deviations / concerns
[Anything you could not do as specified, or any place the task file is ambiguous. Say so
plainly rather than guessing. "None" is a valid answer.]

### Footprint
files_read: <N> (~<C> chars)     # C as digits only, no thousands separators
```
