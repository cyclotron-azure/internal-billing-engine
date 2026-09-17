You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-16T16:40-04:00

## Task

Task 03 of the `otel-export-loss-reduction` goal. Two things in one task:

**Part A** — the receiver answers `GET /healthz`: liveness to anyone, ingest-freshness to
an authorized caller.
**Part B** — `/v1/transcript-usage` accepts `cli` and `claude-vscode` records alongside
`claude-desktop`, but only for sessions with no OTLP rows and only once they are old
enough that a final export flush cannot still be in flight.

**Read `_goals/otel-export-loss-reduction/03-receiver-health-and-cli-ingest.md` in full and
follow it exactly.** It holds your requirements and your **19** acceptance criteria.
Nothing here supersedes it.

`eval_depth: full`. This task decides whether a transcript row gets billed.

## Task 02's contract is landed and frozen — build against exactly this

```python
OtelStore.last_ingest_at(usage_source=None) -> str | None
OtelStore.sessions_with_otlp_rows(session_ids) -> set
```

`last_ingest_at` spans `token_usage` and `cost_usage` and reads `ingested_at`, not `ts`.
`sessions_with_otlp_rows` finds a session with an OTLP row in **either** table, chunked at
500 ids via a single-bind `VALUES` CTE. Do not reimplement either, and do not add a third
read method to the store — `otel_store.py` is **not** in your fence.

**Two preconditions you own**, established by task 02's evaluator and now written into your
requirements. Both fail in the double-billing direction, so neither is cosmetic:

- `sessions_with_otlp_rows(None)` returns `set()`, which your code would read as "no OTLP
  rows, safe to insert". Never let a `None` reach it.
- Non-string ids normalize silently: `[123]` returns `{'123'}`, the stored string, so
  `123 in result` is `False` while that session really does have OTLP rows. Pass `str`
  ids and compare against returned strings.

## The five things most likely to go wrong

1. **The detail gate is `AUTH_TOKEN and self._authorized()` — both halves.**
   `_authorized()` alone returns `True` when `RECEIVER_AUTH_TOKEN` is unset
   (`receiver.py:415`), which is the documented open-receiver posture. Reusing it alone
   would hand freshness detail to any prober and would make the body's *shape* disclose
   whether a token is configured. On an open receiver, detail is never served.
2. **`transcript.py` must stay pure.** `README.md:150` documents it as "no I/O, no store
   access" and it has no clock. Put the constant and the two new reason strings there; put
   the age **comparison** in `receiver.py`.
3. **Preserve the record's own entrypoint.** `transcript.py:519` currently *overwrites* it
   with the constant. Left as-is, every backfilled CLI row is stored as `claude-desktop`.
4. **`claude-desktop` is exempt from both new checks.** This is what keeps existing
   desktop behavior intact — and it is asserted positively by criterion 14, not just
   implied.
5. **Call `sessions_with_otlp_rows` once per batch**, not once per record.

## Expect to break four pre-existing tests — report them, do not fix them

Four assertions pin `cli`/`claude-vscode` as *rejected*, which this task deliberately
inverts: `tests/test_transcript.py:134-139` and `:369-381`,
`tests/test_receiver.py:278-287`, `tests/test_integration_desktop.py:393-399`.

**Task 05 owns those edits. You must not touch any file under `tests/`.** Instead, list
every pre-existing test your change breaks, with file:line, in your report. Task 05
inverts exactly the set you name, so a break you fail to report becomes a defect. If you
break a test **outside** those four, say so prominently — that is a finding about the
implementation, not a test to fix.

## Write fence

```
billing/otel/receiver.py
billing/otel/transcript.py
```

Nothing else. Not `otel_store.py`, not `tests/`, not `client-package/`, not
`billing/reconcile.py`.

## Model

requested: claude-sonnet-5 · tier: light · rotation: n/a

## Rules

- The clock must be patchable: every "now" you introduce reads through a module-level
  helper, never an inline `datetime.now()` / `time.time()` at the comparison site. Task 05
  freezes time to test a 15-minute boundary and a future-stamped row.
- Do not thread the receiver, add a connection pool, set WAL, or pass `check_same_thread`.
  Single-host single-connection is a hard constraint from `CLAUDE.md`.
- Do not change `dp_key`, `transcript_key`, the schema, or add a column or table. If this
  task appears to need one, **stop and escalate** rather than improvising.
- Do not change any existing reason string, the rejected-record shape
  (`{"index", "request_id", "reason"}`), or the `/v1/metrics` and `/v1/session-repo`
  behaviors. A client parses the rejected-record shape.
- Preserve the deliberate divergence in `/v1/transcript-usage`'s error handling relative to
  the other POST paths; there is an explanatory comment at the dispatch site. Do not
  harmonize it.
- The health route must not echo configuration. When in doubt about a field, leave it out —
  a field can be added later, a leak cannot be withdrawn.
- Standard library only.
- Climb test-ladder rungs 1-2 only. Do not run the full suite.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Part A — /healthz
[Route matching, the detail gate expression verbatim, the four detail fields, the null vs
zero handling, the negative clamp, the 404 path, the 503 path, the banner line.]

## Part B — CLI ingest
[Allowed set, the preserve-entrypoint fix, the exclusion call site and its batching, the
quarantine placement, the two new reason strings, the desktop exemptions.]

## Preconditions
[How you guarantee the guard never receives None, and that ids are str.]

## Evidence (verbatim, only these four)
a) unauthenticated GET /healthz body
b) authorized GET /healthz body against a seeded store
c) the rejected-records list from a mixed batch exercising session_has_otlp, too_recent
   and invalid_entrypoint together
d) the stored entrypoint value for an accepted cli record (SELECT entrypoint, usage_source)

## Pre-existing tests broken
[file:line each, with the assertion. "None" would be surprising -- four are expected.]

## Verification
[The targeted pytest line -> result, and which failures are the expected four.]

### Footprint
files_read: <N> (~<C> chars)
```
