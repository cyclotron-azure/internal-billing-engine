You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-16T18:20-04:00

## Task

Task 04 of `otel-export-loss-reduction`: the `SessionEnd` sweeper stops discarding the CLI
and VS Code transcripts it already reads, ships them with their real entrypoint, quarantines
sessions too recent to judge, and performs a **one-time historical replay** so existing
on-disk history becomes eligible rather than only future sessions.

**Read `_goals/otel-export-loss-reduction/04-sweeper-cli-backfill.md` in full and follow it
exactly.** It holds your requirements, a "Background — the state file, exactly as it works
today" section written specifically for you, and your **18** acceptance criteria. Nothing
here supersedes it.

`eval_depth: full`. This task replays transcript history through a billing ingest path.

## Read the Background section first, and trust it

Every line/mechanism citation in it was verified against the source during Phase 3:
`resolved` / `examined_mtime` state shape (`:505-511`), the scan loop and resolved skip
(`:528-529`), the `install_ts` watermark (`:647-649` — note `install_epoch` is a *derived
local*, not a state key), the trailing-group withhold (`:137`, `:547-551`, `:739-744`),
resolve-on-200 (`:689-700`), and `transport_fail` (`:735-738`).

## The single most important requirement

**A quarantine-skipped session must not be marked processed.** Reuse the existing
`withheld = True` mechanism so `examined_mtime` does not advance and `_mark_resolved` is not
called. Implemented backwards, every CLI session is skipped exactly once and never
revisited — which *looks* like success and recovers nothing. Criterion 3 pins both halves.

By contrast, an out-of-set or missing entrypoint **is** marked resolved: it can never become
shippable, so leaving it unresolved re-parses it forever. Criteria 5 and 6 assert the
`resolved` membership, and this asymmetry is deliberate.

## Part C, the replay — three things, not two

`resolved`, `examined_mtime`, **and** the `install_ts` watermark, cleared atomically with
the flag, before any POST. Clearing `examined_mtime` is not optional: `:509-511`
short-circuits on an unchanged mtime **before** the group loop ever reads `resolved`, so
clearing only `resolved` re-scans nothing and ships nothing — while still passing a test
whose fixture left `examined_mtime` at its `None` default. The reset is **permanent**, never
restored after the pass, so an interrupted replay finishes on a later run instead of losing
its remainder.

Its safety rests on guards that are now landed and verified, not on hope: re-shipped
**desktop** records are dropped at the store by `transcript_key`, and re-shipped **CLI**
records are gated by task 03's session-level exclusion, which now spans `token_usage` **and**
`cost_usage`. So the replay can only ever *add* rows for sessions lost entirely.

## What task 03 landed that you must match

- Allowed entrypoints: `claude-desktop`, `cli`, `claude-vscode`.
  `transcript.ALLOWED_ENTRYPOINTS` is the server-side authority; you duplicate the values
  because this script cannot import from `billing/`.
- Server-side quarantine is **900s**. Your client-side window is **1800s**, deliberately
  twice that — a record clearing your gate but failing the server's is permanently burned by
  the resolve-on-200 path. A strictly larger client window makes the server boundary
  unreachable.
- New server reject reasons: `session_has_otlp`, `too_recent`, and `invalid_session_id`.
  **`too_recent` is non-resolving**; every other reason stays resolving, because the others
  are permanent verdicts.
- The server now **rejects a non-`str` `session_id`** with `invalid_session_id`. Your hook
  passes `terminal_row["sessionId"]` verbatim today, which is correct — keep it that way.

## The trap that cost this goal two fix cycles

Task 03's guard broke **twice** on the same defect: a transformation applied to the session
key on one side and not the other. First a `.strip()`, then a `str()` that disagreed with
SQLite's TEXT-affinity conversion. Both were reproduced as accept-and-double-bill.

Your requirements therefore include: **never substitute a placeholder for a missing
`session_id`** — drop the record instead. `receiver.py:190` substitutes the literal
`"unknown"` on the OTLP side, and three attribute-less datapoints were measured collapsing
into one `'unknown'` bucket. If this hook mirrored that idiom, every such record would match
"this session already has OTLP rows" and be rejected `session_has_otlp` forever — silent
loss, invisible because a rejection is not an error. Do not normalize the session id in
either direction.

## Write fence

```
client-package/claude-transcript-usage.py
deploy/claude-transcript-usage.py
```

Both copies, kept **byte-identical** (they are identical today; criterion 10 asserts equal
sha256). Nothing under `tests/`, nothing under `billing/`, no settings or config file.

## Model

requested: claude-sonnet-5 · tier: light · rotation: n/a

## Rules

- **Always exit 0.** Every new path — malformed timestamp, unparseable entrypoint,
  state-write failure, replay failure — must not raise out of the hook. A hook that exits
  non-zero breaks the user's Claude Code session.
- The clock must be patchable: a module-level helper, never an inline
  `datetime.now()`/`time.time()` at the comparison site. Task 05 freezes time and advances
  it between two runs.
- Exactly **one** shipping path. The replay is a state reset, not a second code path.
- Do not change transcript enumeration, the POST target, the payload shape beyond the
  entrypoint value, or the state-file format beyond the replay flag and the tallies. No
  existing state key renamed or removed.
- Do not add a flag or env var to disable the quarantine or re-trigger the replay.
- Stdlib only; no import from `billing/`.
- Climb test-ladder rungs 1-2 only. Do not run the full suite.
- If you break a pre-existing test, **report it with file:line — do not fix it.** Task 05
  owns test edits. Note the current baseline for the targeted selection is **6 failed, 168
  passed**, and those six are known and owned by task 05; a *seventh* is a finding.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Part A — ship CLI / VS Code
[Allowed set, the entrypoint-preservation fix, and the resolved-vs-withheld asymmetry.]

## Part B — quarantine
[The 1800s constant and its comment, the withheld reuse, too_recent non-resolving, the
desktop exemption, the clock helper.]

## Part C — replay
[The flag, the three cleared things, flag-before-POST, permanence, the pre-POST volume log,
the persisted tallies.]

## Evidence (verbatim, only these)
a) one built payload record for a cli transcript (showing entrypoint)
b) the two sha256 digests
c) the reported tallies for the replay fixture, including the pre-POST intended volume
d) state before/after a quarantine-skipped run, showing `resolved` and `examined_mtime`

## Pre-existing tests broken
[file:line each, or "None". Flag a seventh failure prominently.]

## Verification
[The targeted pytest line -> result.]

### Footprint
files_read: <N> (~<C> chars)
```
