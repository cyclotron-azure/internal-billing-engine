You are the test-writer subagent. Read: .claude/agents/test-writer.md

CURRENT_DATETIME: 2026-09-16T20:45-04:00

## Task

Task 05 of `otel-export-loss-reduction` — the goal's test task. **Read
`_goals/otel-export-loss-reduction/05-tests.md` in full and follow it exactly.** It holds
your requirements, the seven inverted assertions, **eleven** testability traps, the
isolation rules, and your 8 acceptance criteria. Nothing here supersedes it.

You are writing **71 tests**, one per acceptance criterion:

| task | file | criteria |
|---|---|---|
| 01 export interval | `_goals/.../01-export-interval.md` | 1-7 |
| 02 store reads | `02-store-reads.md` | 1-15 |
| 03 healthz + CLI ingest | `03-receiver-health-and-cli-ingest.md` | 1-21 |
| 04 sweeper backfill + replay | `04-sweeper-cli-backfill.md` | 1-19 |
| 06 OTLP coercion | `06-otlp-session-id-coercion.md` | 1-9 |

Read all five task files. Their criteria carry their reasoning inline, because most of them
exist because something already went wrong.

## The suite is RED right now, and turning it green is part of your job

Current state: **8 failed, 323 passed** on the full suite. All eight are pre-existing tests
that this goal deliberately inverts, and all eight are yours. The seven hunks are listed in
your task file with file:line. When you are done the suite must be **green**, with your 71
new tests added.

The eighth failure, `test_integration_desktop.py:398
test_systemic_alarm_silent_for_pure_validation_rejections`, is covered by the same
entrypoint change — it calls `receiver.ingest_transcript_usage_payload` directly with an
`entrypoint="cli"` record and expects `rejected == 1`.

**Keep the negative coverage alive.** Every inverted assertion must retain the old
expectation against a genuinely out-of-set entrypoint (`claude-web`), and
`tests/test_receiver.py` must keep a case exercising `store_error:ProgrammingError` for the
`user_email={"a":1}` path — `_RECORD_DATA_ERRORS` still needs it. Move the coverage; do not
delete it.

## Why these criteria are worded so defensively

This goal found **four** separate double-billing paths, and in three of the four **every
acceptance criterion passed while the code was broken**. The criteria were checking
internal consistency, not agreement with the system on the other side. Specifically:

- Task 03's guard stripped whitespace from its session key while the store persists
  `session_id` verbatim. Criteria 10 and 16 passed because the build site and lookup site
  agreed with *each other*.
- Then it used `str()`, which disagrees with SQLite's TEXT-affinity conversion
  (`str(True) == 'True'`, SQLite stores `'1'`).
- The OTLP side had the same asymmetry from the other end.
- Task 04's `shipped` tally counted resolved rather than accepted records, so a replay that
  recovered nothing reported success.

So: a test that only proves the code agrees with itself is worthless here. Assert against
stored values, row counts, and state keys by name.

## Highest-risk items — do not get these wrong

- **`sqlite3.Connection.execute` cannot be monkeypatched** (immutable C type). Reuse
  `_ExecuteSpy` at **`tests/test_dedupe_counter.py:57`** — not `test_reconcile.py`.
- **`_FakeClock` at `tests/test_dedupe_counter.py:80`.** Freeze time; never `sleep`.
- **`receiver.AUTH_TOKEN` is read at module import**, so `setenv` alone does nothing. Reuse
  the `no_auth` / `with_auth` fixtures at `tests/test_receiver.py:86-94`. Task 03 criterion
  1 must hold under **both** token states.
- **Task 02 criterion 15 needs `conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)`.**
  This machine's real cap is 32766, so without `setlimit` the test passes against a
  statement that raises in production.
- **Task 02 criteria 13 and 14 must build their row with `insert_cost_datapoint` ALONE.** A
  fixture that also inserts a token row makes both pass vacuously.
- **Task 03 criterion 10 counts BOTH `token_usage` and `cost_usage`**, in two shapes: OTLP
  rows in the token table, and the only OTLP row in `cost_usage`.
- **Task 03 criteria 1 and 4 assert the key SET** (`set(body) == {...}`), not membership.
- **Task 04 criterion 3 is the single most important test in the goal.** Assert `resolved`
  and `examined_mtime` **by name** after a quarantine skip, then advance the frozen clock
  and confirm the record ships. The natural implementation marks it resolved, which makes
  every CLI session ship *never* while looking like success.
- **Task 04 criterion 13's fixture must set `examined_mtime` to each file's real mtime**, or
  the test passes against a production no-op.
- **Task 04 criterion 16 needs both directions**: a fully-rejected fixture reports
  `shipped == 0`, **and** an all-accepted fixture reports `shipped == n`. A counter guarded
  too aggressively would satisfy the first alone.
- **Task 06 criterion 1 tests only TWO cases as fixed** — `doubleValue 1e20` and
  `boolValue true`. The other three (`intValue "0123"`, `intValue "+123"`,
  `doubleValue 42.0`) **still double-bill by design** and their root cause is different.
  Do not write a test asserting they are fixed; if you want to pin them, pin the *current*
  documented behavior.

## Byte-identity reference

Tasks 02-06 are all uncommitted, so `git diff` against `HEAD` cannot isolate any one task.
A snapshot of `receiver.py`, `transcript.py`, `otel_store.py` and
`claude-transcript-usage.py` as of end-of-phase-4, with `MANIFEST.sha256`, is at
`baseline-phase4/` inside this session's scratchpad directory. Use it if a criterion needs a
byte-identity comparison.

## Write fence

```
tests/test_store_reads.py            (new)
tests/test_receiver_health.py        (new)
tests/test_cli_backfill.py           (new)
tests/COVERAGE_MAP.md                (targeted insertion — new section only)
tests/test_transcript.py             (ONLY the 2 inverted hunks)
tests/test_receiver.py               (ONLY the 2 inverted hunks)
tests/test_integration_desktop.py    (ONLY the 1 inverted hunk)
tests/test_transcript_hook.py        (ONLY the 2 inverted hunks)
```

`tests/conftest.py`, `tests/test_otel_store.py`, `tests/test_reconcile.py` and
`tests/test_dedupe_counter.py` are **byte-unmodified**. Nothing under `billing/`,
`client-package/`, `deploy/` or `pilot-package/`.

Task 06's criteria can live in whichever of the three new files fits best — say which you
chose.

## Model

requested: claude-sonnet-5 · tier: light · rotation: n/a

## Rules

- Every store is a `tmp_path` file. No test touches `data/otel.db`, `data/analytics.db`,
  the real `~/.claude`, or the real state file.
- No live network call. Mock the sweeper's POST; bind any server to **port 0**.
- Standard library plus `pytest` only.
- **Do not weaken an assertion to make a test pass.** If a strengthened test fails against
  the shipped code, that is a genuine finding — leave it failing and report it. Four real
  defects in this goal were found exactly that way.
- If a pre-existing test outside the seven named hunks fails, report it; do not edit it.
- Climb test-ladder rungs 1-2. You may run the full suite **once** at the end to confirm
  green, since turning it green is your deliverable.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Coverage
[Tests per task: 01=7, 02=15, 03=21, 04=19, 06=9, total 71. Say where task 06's went.]

## The seven inversions
[One line each: file:line, what it asserted, what it asserts now, and where the negative
case moved to.]

## Trap handling
[One line per trap in the task file's list — how you satisfied it, citing the test name.]

## Mutation self-check (criterion 8)
[The seven mutations, and which test caught each. Scratchpad copy only, never the repo.]

## COVERAGE_MAP.md
[The three counts: criteria mapped, dead node ids, unreferenced new tests.]

## Verification
[Full suite -> result. It must be GREEN. Report the final count and reconcile it against
the 323 passed + 8 inverted + 71 new arithmetic.]

## Any test failing against shipped code
["None" is valid, but say so explicitly rather than omitting the section.]

### Footprint
files_read: <N> (~<C> chars)
```
