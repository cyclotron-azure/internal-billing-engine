# Goal: otel-export-loss-reduction

## Problem Statement

Phase 0 (`reconcile-coverage-diagnostics`) made the coverage gap measurable; this goal
closes it. A 3-day two-user run reported input 39.87% / output 96.37% / cacheRead 89.32% /
cacheCreation 60.67% against Analytics truth. The missing usage is enriched ~5.2x in
uncached input and ~3.4x in cacheCreation and depleted in output — the signature of whole
early sessions lost rather than uniform sampling loss. `README.md` documents the cause:
the OTLP exporter holds datapoints in an in-memory queue with no disk spool and flushes
once per `OTEL_METRIC_EXPORT_INTERVAL` (60s), so a session that exits before its first
flush contributes nothing, forever. `README.md` also gates the fleet rollout on this:
"Do not start the fleet rollout until coverage is a number worth defending to a client."

Two secondary losses compound it: a receiver outage is invisible until someone runs
`reconcile` (there is no health route — `receiver.py` has no `do_GET` handler at all), and
CLI/VS Code sessions whose export never flushed are unrecoverable even though their
transcripts are sitting on disk and the desktop sweeper already reads them.

## Discovery Summary (Phase 1 Q&A)

- **Levers to pull** — shorten the export interval; add a receiver uptime check; backfill
  from transcripts. The user explicitly did NOT select "persist `request_id`" as a
  standalone lever.
- **Interval** — 60s -> **10s**. `deploy/dev-selftest.sh:24` already runs the receiver at
  5s, so 6x the fleet POST rate is a known-tolerable load, not a guess.
- **Rollout surface** — all four config sources plus docs, because drift between them is
  silent and per-machine.
- **Gates** — `align_docs: true` (README.md is ground truth and this goal edits values
  cited in two READMEs). `pull_request: false` — the user ships this one.
- **Backfill dependency, raised by the orchestrator and answered by the user** — the
  backfill cannot dedupe against OTLP rows, because `transcript_key` is deliberately
  constructed so it can never equal a `dp_key` (recorded as a design guarantee in
  `otel_store.py`). The user chose "add `request_id` first" as the prerequisite.
- **That answer rests on a false premise, discovered during Phase 2 planning.**
  `request_id` cannot be persisted on the OTLP path: the `claude_code.token.usage`
  datapoint carries only `session.id`, `repo`, `user.email`, `user.id`,
  `organization.id`, `model`, `query_source`, `type` and `timeUnixNano` (`receiver.py`
  `_common()`, :133-149), so the column would be permanently NULL on exactly the rows the
  dedupe needs. Corroborated structurally: `otel_store.py` (:395-408) *raises* if
  `request_id` is passed with `usage_source='otlp'`. Scope of the claim, stated precisely
  because the whole design rests on it — this repo proves `request_id` is **not readable
  and not persistable today**, not that Claude Code never emits such an attribute; no
  in-repo fixture or vendor doc enumerates the emitted attribute set. If a request id is
  ever confirmed on the wire, revisit this decision.
  **Substituted design: session-level exclusion.** A CLI/VS Code
  transcript record is accepted only when its `session_id` has no `usage_source='otlp'`
  row. This recovers sessions lost *entirely* — the dominant case at a 60s interval — and
  deliberately declines partially-lost sessions, where no safe unit of comparison exists.
  The residual is a known, stated limitation, not an oversight.
- **One-time historical replay, added after Phase 3 evaluation.** The evaluator established
  that backfill as first specified would recover almost nothing: the sweeper skips any
  group older than `install_epoch` (`claude-transcript-usage.py:543-545`), and every CLI
  `request_id` on every already-installed machine has *already* been marked resolved by
  today's discard filter (:537-539), with resolved ids skipped forever (:529). So it would
  only ever see *future* CLI sessions — which task 01 is simultaneously shrinking ~6x. The
  user chose to add a one-time, idempotent replay that makes the existing on-disk history
  eligible again. It resets per-file state wholesale rather than selectively -- see the
  matching success criterion for why selective is unimplementable. This is safe for exactly the reason the design
  already relies on: session-level exclusion skips any session with an OTLP row wholesale,
  so a replay can only ever add sessions that were lost entirely.

## Success Criteria

- [ ] `OTEL_METRIC_EXPORT_INTERVAL` is `10000` in all four config sources, and no source
      still says `60000`. A fleet-wide grep for `60000` returns only historical prose.
      **Amended after the goal closed.** `pilot-package/` (2 of the original 4 sources) was
      deleted by user decision on 2026-09-21 -- it was already documented in `README.md` as
      "superseded by `client-package/`", not a config-drift risk this goal needed to guard.
      The live criterion is now: `10000` in both **surviving** sources
      (`deploy/managed-settings.json`, `client-package/configure.py`), and no source
      describing the current interval still says `60000`. The zips (`client-package.zip`)
      are a separate, still-open finding from the Phase 5 audit -- not resolved by this
      amendment.
- [ ] `GET /healthz` answers without authentication and reports liveness only, so a
      stalled receiver is detectable by an unauthenticated prober. Freshness detail is
      served **only** when `RECEIVER_AUTH_TOKEN` is non-empty *and* the caller presents a
      matching token. Note `_authorized()` returns `True` when the token is unset
      (`receiver.py:415`) — reusing it alone would hand freshness detail to any prober on
      the documented open-receiver posture, and would make the body's shape disclose
      whether a token is configured. On an open receiver, detail is simply never served;
      if you want diagnostics, set a token.
- [ ] The health route adds no thread, no second connection, and no connection pool to
      the receiver, and a `GET` to an unknown path still 404s rather than 200s.
- [ ] The OTLP-exclusion guard tests **both** `token_usage` and `cost_usage`. A session
      whose only OTLP row is a cost row is still excluded — the cost side is billed
      (`invoice.py:215`, `:224-225`) and the two key spaces cannot collide.
- [ ] A CLI transcript record for a `session_id` that already has an OTLP row is
      **rejected**, counted under a distinct reason, and inserts nothing. Verified by a
      test that asserts the post-ingest row count is unchanged.
- [ ] A CLI transcript record for a `session_id` with no OTLP row is accepted and lands
      with `usage_source='transcript'` and its real `entrypoint` (`cli` /
      `claude-vscode`), never rewritten to `claude-desktop`.
- [ ] A CLI session too recent to be sure its final OTLP flush has landed is withheld
      without its request ids entering `resolved` and without `examined_mtime` advancing,
      so it remains eligible on a later run.
- [ ] Desktop capture behavior is unchanged: every existing `claude-desktop` assertion
      still holds, and the two copies of the sweeper stay byte-identical to each other.
- [ ] **The four pre-existing assertions that pin `cli`/`claude-vscode` as *rejected* are
      inverted, not deleted.** `tests/test_transcript.py` (the entrypoint parametrization
      and the rejected-index batch test), `tests/test_receiver.py` and
      `tests/test_integration_desktop.py` encode today's behavior as correct. They are
      task 05's to change, and each must keep the old expectation alive as a negative case
      (an entrypoint genuinely outside the allowed set still rejects).
- [ ] A `too_recent` rejection is retried, not burned. The sweeper does not mark a record
      resolved when the server declines it as too recent.
- [ ] The one-time historical replay is idempotent: running it twice re-ships nothing, and
      it does **not** reset the `install_ts` watermark -- pre-installation usage stays
      unbilled, because it was never captured by OTLP either and billing it now would
      expand invoices retroactively rather than recover lost telemetry.
      It clears **all** per-file resolution state, desktop included — selectively clearing
      only CLI ids is unimplementable, because `resolved` is a flat list of request ids
      carrying no entrypoint, so deciding which are CLI would require re-parsing every
      transcript, which is exactly what the watermark prevents. Clearing desktop state is
      safe because `transcript_key` is a replay guard by design: a re-shipped desktop
      record is dropped at the store. The cost is one wasted POST, not a duplicate row.
- [ ] An interrupted replay finishes on a later run rather than losing its remainder.
- [ ] **Recovery is measurable.** The sweeper reports how many records the replay shipped
      and how many the server excluded as `session_has_otlp`, so "this shipped and
      recovered nothing" is a visible outcome rather than an invisible one.
- [ ] The OTLP write path stores `session_id` as a `str` in every case, so the spelling
      SQLite persists cannot differ from the spelling the exclusion guard builds. Five
      double-bills were reproduced from the `/v1/metrics` end before this was closed; the
      fix is provably `dp_key`-invariant, so no history is re-billed.
- [ ] `reconcile.py` output and `billing/reconcile.py` are unmodified by this goal.
- [ ] Full suite green. Baseline is 331 passed; the final count is 331 plus the new tests,
      with the four inverted assertions accounted for explicitly in the task 05 report.

## Constraints

- **Runtime is standard-library only.** No third-party import may enter `billing/`.
- **SQLite is single-host, single-connection.** The health route runs on the receiver's
  existing single connection inside its existing request thread model. No WAL, no pool,
  no `check_same_thread=False`, no threading the receiver.
- **Repo attribution is resolved at query time, never persisted.** No task here may
  persist a resolved repo or read the raw `repo` column as if it were authoritative.
- **Never commit a secret.** `RECEIVER_AUTH_TOKEN` and every `AZURE_*`/`ADLS_*` value
  live in `.env` only. The health route must not echo a token, even partially, and must
  not reveal whether `RECEIVER_AUTH_TOKEN` is set to an unauthenticated caller.
- `dp_key` and `transcript_key` are frozen. Neither may be redefined, merged, or given a
  new field — a change to either silently re-bills or un-bills history.
- The two pre-existing `run()` error paths in `reconcile.py` and the `/v1/metrics` and
  `/v1/session-repo` POST behaviors stay byte-identical.
- `claude-transcript-usage.py` must keep its always-exit-0 contract: a hook that fails
  loudly breaks the user's Claude Code session.

```yaml
phases:
  align_docs: true
  pull_request: false
  ladder: escalate
```

## Out of Scope

- Persisting `request_id` on `token_usage` — established as not implementable for OTLP
  rows (see Discovery Summary). Request-grain reconciliation stays out of reach.
- Recovering **partially**-lost sessions. Session-level exclusion declines them by design.
- Public HTTPS posture, certificate management, and receiver hosting changes (roadmap
  Phase 2).
- Surface enumeration / fleet inventory (roadmap Phase 3).
- Coverage SLOs, alert thresholds, non-zero exit codes, and any paging integration
  (roadmap Phase 4). This goal makes the receiver *observable*; it does not decide what
  number is unacceptable or who gets woken up.
- Any change to `billing/reconcile.py`, including reporting the new reject reasons.
  **Consequence to accept knowingly:** the one-time replay pushes a large volume of
  already-known records through `INSERT OR IGNORE`, so the `dedupe_drops` counter from the
  previous goal will spike and `reconcile --detail` will show a one-day cliff of drops on
  the replay date. That is the replay working, not a `dp_key` collision. Task 04 records
  the replay date so the output can be attributed; teaching `reconcile` to say so itself
  is out of scope.
- Lowering the export interval below 10s, or making it configurable per user.

## Tasks (dependency order)

| # | Task file | Layer | Depends on |
|---|-----------|-------|------------|
| 01 | `01-export-interval.md` | Client rollout | — |
| 02 | `02-store-reads.md` | Store & schema | — |
| 03 | `03-receiver-health-and-cli-ingest.md` | Ingest | 02 |
| 04 | `04-sweeper-cli-backfill.md` | Client rollout | 03 |
| 06 | `06-otlp-session-id-coercion.md` | Ingest | 03 |
| 05 | `05-tests.md` | tests | all |

**Contract first.** Task 02 is the contract task: it freezes the two read methods that
tasks 03 and 04's server-side guard depend on, and nothing else in the goal may add a
read to `otel_store.py`. Task 01 is deliberately independent of every other task so the
single highest-value change — the interval cut — can land and ship without waiting on the
backfill work.
