You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-16T16:05-04:00

## Task

Task 02 of the `otel-export-loss-reduction` goal: add exactly **two** read-only methods to
`OtelStore` — `last_ingest_at(usage_source=None)` and `sessions_with_otlp_rows(session_ids)`.

**Read `_goals/otel-export-loss-reduction/02-store-reads.md` in full and follow it
exactly.** It holds your requirements, your **15** acceptance criteria, the files to read,
and the constraints. Nothing here supersedes it.

This is the goal's **contract task**. Two downstream tasks build against these signatures,
and `sessions_with_otlp_rows` is the guard that decides whether a transcript row gets
billed. It went through three evaluation cycles; the requirement text now carries the
reasoning inline because two of its subtleties were found only by adversarial review. Read
that reasoning rather than skimming to the signatures.

## The three things most likely to go wrong

1. **Both tables, not one.** The guard must find a session with an OTLP row in
   `token_usage` **OR** `cost_usage`. A transcript record writes a cost row too, and
   `invoice.py:215`/`:224-225` sum `actual_cost + estimated_cost` into `total_billed` — so
   the cost side is billed. The receiver's token and cost branches are independent
   (`receiver.py:163`/`:176`), so a partial flush can leave a session with OTLP rows in
   `cost_usage` and none in `token_usage`. Narrowing this to one table **double-bills a
   client**, and `transcript_key` cannot catch it because it and `dp_key` are designed
   never to collide. `last_ingest_at` spans both tables for the same reason.
2. **Bind each chunk exactly once.** The task gives you the `VALUES` CTE to use. A two-arm
   `UNION` repeating the `IN` list binds 500 ids twice — 1002 parameters against a 999 cap
   on older sqlite3 builds, which raises `OperationalError: too many SQL variables`. This
   was reproduced at `setlimit(999)`. **This machine's cap is 32766, so the fault is
   invisible here and appears only in production.** Keep the invariant
   `ids_per_chunk x arms + literal_binds <= 999` true.
3. **Do not swallow `sqlite3.Error`.** Unlike the `dedupe_drops` counter from the previous
   goal — where a failed diagnostic count must never become a billing rejection — a failed
   membership test must **propagate**, because the caller's only safe fallback is to refuse
   the insert.

## Write fence

```
billing/otel/otel_store.py
```

Nothing else. Not `receiver.py`, not `transcript.py`, not anything under `tests/`.

## Model

requested: claude-sonnet-5 · tier: light · rotation: n/a

## Rules

- Additive only. `dp_key`, `transcript_key`, `SCHEMA`, `_migrate`, `insert_datapoint`,
  `insert_cost_datapoint`, the transcript insert path and the `dedupe_drops` counter must
  all be **byte-unmodified**. `git diff` must show no deleted or altered pre-existing line.
- Standard library only — no new import beyond what the module already has.
- Use the existing `self.db`. No `sqlite3.connect`, no `check_same_thread`, no WAL pragma,
  no pool, no threading. Single-host single-connection is a hard constraint from
  `CLAUDE.md`.
- Read-only: no `INSERT`/`UPDATE`/`DELETE`/`CREATE`, no `commit()`.
- Bind every session id as a `?` parameter. Ids arrive from a client-posted payload; never
  interpolate them into SQL.
- No caching or memoization. A stale "no OTLP rows" answer double-bills.
- Neither method may read or return the raw `repo` column. Repo attribution is resolved at
  query time elsewhere and must stay that way.
- Docstrings must state the `ingested_at`-vs-`ts` distinction, the `IN ()` hazard, and the
  parameter-cap arithmetic — all three are things a later reader will try to simplify away.
- Climb test-ladder rungs 1-2 only. Do not run the full suite.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Signatures (verbatim)
[Both, plus the chunk constant.]

## SQL (verbatim)
[The exact statement sessions_with_otlp_rows issues, and the one last_ingest_at issues.]

## Parameter arithmetic
[ids_per_chunk x arms + literal_binds = N, and N <= 999.]

## Requirements
[One line per requirement group: last_ingest_at, sessions_with_otlp_rows, Both.]

## Verification
[`python -m pytest tests/test_otel_store.py -q` -> result, and confirm the count is
unchanged from before your change.]
[`git diff --stat billing/otel/otel_store.py` -> insertions/deletions. Deletions must be 0.]
[A manual check that a 500-id chunk succeeds under
`conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)` -- do this in your scratchpad
against a temp database, never against `data/`.]

## Anything you could not satisfy
["None" is valid. If a requirement is impossible as written, say so rather than
improvising -- a wrong guess here bills a client twice.]

### Footprint
files_read: <N> (~<C> chars)
```
