You are the evaluator subagent. Read: .claude/agents/evaluator.md

Fresh spawn. CURRENT_DATETIME: 2026-09-16T16:50-04:00

Also read `.claude/skills/task-criteria/SKILL.md` and apply it.

## Task

Evaluate task 03 of the `otel-export-loss-reduction` goal against its **19** acceptance
criteria. Verdict: **PASS**, **PASS (with notes)**, or **NEEDS FIXES** / **REJECT**.

`eval_depth: full`. This task owns the guard call site that decides whether a CLI
transcript row gets billed.

## Files to Read

- `_goals/otel-export-loss-reduction/03-receiver-health-and-cli-ingest.md` — the task, its
  requirements and 19 criteria, with reasoning carried inline
- `_goals/otel-export-loss-reduction/spawns/08-report.md` — the report
- `billing/otel/receiver.py` and `billing/otel/transcript.py` — via `git diff` and in full
  where needed
- `billing/otel/otel_store.py` — task 02's frozen contract, read-only

## Provenance you should know

The spawned implementer returned a non-answer and silently delegated to a child; the
attached report is the child's. The orchestrator already verified by grep/diff that the
claimed symbols exist: the `AUTH_TOKEN and self._authorized()` gate at `receiver.py:557`,
`_now`/`_stale_seconds` as module helpers, the 503 degraded path, `do_GET` with a 404
fallthrough, `ALLOWED_ENTRYPOINTS` as a 3-member frozenset, the preserve-entrypoint fix at
`transcript.py:554`, both new reason strings, and zero `transcript_key` lines in the diff.
**Existence is established; correctness is yours.** Treat the report's behavioral claims
as unverified.

## Verify by execution

1. **The test claim.** The report says the targeted run is `5 failed, 169 passed` and that
   the 5 failures are exactly the 4 named pre-existing tests (one parametrized into 2
   cases). Re-run it and confirm **both** halves — the count and the identity of every
   failure. A fifth distinct failure would be a finding.
2. **Criterion 10, the double-billing criterion.** Run it in both shapes the criterion now
   demands: OTLP rows in `token_usage`, and the only OTLP row in `cost_usage` built via
   `insert_cost_datapoint` alone. Assert `SELECT COUNT(*)` over **both** `token_usage` and
   `cost_usage` is identical before and after. "Rejected" in the response body is not
   sufficient evidence that nothing was inserted.
3. **Criteria 1, 3, 4 — the leak surface.** Assert the unauthenticated body's key **set**
   is exactly `{status, now}`, under **both** token states (`no_auth` and `with_auth`
   fixtures at `tests/test_receiver.py:86-94`; note `receiver.AUTH_TOKEN` is read at import
   so `setenv` alone is insufficient). Confirm a wrong bearer token still yields 200 with
   the unauthenticated key set, and that no substring of the configured token appears in
   the body.
4. **Criterion 14, the exemptions, asserted positively.** A `claude-desktop` record for a
   session that *does* have an OTLP row must be **accepted**, and one timestamped 60
   seconds ago must be **accepted**. These are what keep desktop capture intact.
5. **Criterion 13, the boundary.** Same record at 60 seconds -> `too_recent`; at 2 hours ->
   accepted. Freeze the clock by patching `receiver._now`; do not use `sleep`.
6. **Criteria 6, 9 — staleness arithmetic and the 503.** A 3-hour-old `ingested_at` within
   5 of 10800; a row stamped 60s in the future yielding `0`, not negative; and a
   `sqlite3.Error` yielding 503 with the exception text absent from the response.
7. **Criterion 16 — batching and the preconditions.** A 40-record batch across 40 distinct
   sessions calls `sessions_with_otlp_rows` exactly once, and the captured argument is
   non-`None` with every element a `str`.
8. **Criterion 19.** No second connection during a `/healthz` request.

## Judge these three deliberate deviations

The report declares them; decide whether each is sound.

1. **`_BACKFILL_ENTRYPOINTS = ALLOWED_ENTRYPOINTS - {DESKTOP_ENTRYPOINT}`** rather than the
   two literal strings. The argument is fail-safe defaulting: a future entrypoint added to
   the allowed set gets backfill-checked rather than silently exempted. Judge whether that
   is right, and whether it can misfire — e.g. if a future entrypoint genuinely has no OTLP
   exporter, it would be quarantined and exclusion-checked unnecessarily. Is the default in
   the safe direction?
2. **The age check reuses `mapped["ts"]`** rather than re-parsing `record["ts"]`. Confirm
   `mapped["ts"]` is the right timestamp for "how old is this record" — in particular that
   `map_record` has not rewritten, floored, or defaulted it in a way that changes the age,
   and that a record with a malformed `ts` cannot reach the subtraction and raise.
3. **`transcript.py` stayed clock-free**, holding only the constant and reason strings, with
   the comparison in `receiver.py`. Confirm against `README.md:150`'s purity contract that
   nothing clock-adjacent or I/O-adjacent leaked into `transcript.py`.

## Also confirm

- `receiver.py` shows **2 deletions** in `git diff --numstat`. Identify exactly what they
  are and confirm they are permitted (the banner line is expected). Confirm the
  `/v1/metrics` and `/v1/session-repo` POST behaviors and the two pre-existing error paths
  are otherwise byte-identical, and that the deliberate error-handling divergence at the
  `/v1/transcript-usage` dispatch site is preserved rather than harmonized.
- `transcript.py` shows **10 deletions**. Confirm each is the intended removal (the
  singular constant, the overwrite line, the old validate check) and that none touches
  `transcript_key`, `dp_key`, the schema, or the rejected-record shape.
- The rejected-record structure is still `{"index", "request_id", "reason"}` with unchanged
  key names.
- No thread, no pool, no WAL, no `check_same_thread`. Stdlib only.
- `otel_store.py` is unmodified by this task (its +163 is task 02's).

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
[One line per criterion 1-19: MET / NOT MET, and "executed" or "read only".]

## Independent reproductions
[Results of items 1-8, with measured numbers. State the exact set of test failures.]

## The three deviations
[Your ruling on each.]

## Diff integrity
[The 2 receiver deletions and the 10 transcript deletions, identified. Frozen symbols and
POST paths intact / not.]

## Findings
[BLOCKING / NON-BLOCKING, 3 lines max each.]

### Footprint
files_read: <N> (~<C> chars)
```
