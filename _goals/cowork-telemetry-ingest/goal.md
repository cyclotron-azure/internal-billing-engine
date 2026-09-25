# Goal: cowork-telemetry-ingest

## Problem Statement

Claude Cowork (background/parallel agent sessions launched from the Claude desktop app's
Code tab) runs in a cloud VM and is invisible to this billing engine today. It cannot be
captured by the existing `claude-transcript-usage.py` hook (no on-disk transcripts —
that hook only ever sees local CLI/desktop transcript files), and `billing/reconcile.py`'s
truth-side Analytics query is hardcoded to `products=["claude_code"]`
(`analytics_claude_code_daily`/`analytics_claude_code_totals`), so Cowork usage is excluded
from both sides of the funnel symmetrically — not a visible gap today, but real spend with
nowhere to land.

Cowork does emit native OTEL telemetry — confirmed via Claude's official Cowork/OTEL
monitoring docs — distinguishable from CLI traffic by the resource attribute
`service.name="cowork"` (vs the CLI's own value, which this repo's own fixture
(`billing/otel/sample_payload.py:65`) shows is spelled `"claude-code"`, hyphenated — NOT
`"claude_code"`, which is only the metric-name prefix, e.g. `claude_code.token.usage`) and
`terminal.type="non_interactive"`, using the same `prompt.id`/`session.id` correlation
Claude Code already uses. This goal stands up a parallel ingestion + storage + reporting path
for that data, entirely separate from the existing `claude_code` pipeline, so it can be
inspected and verified before any decision is made about merging it into `reconcile.py`'s
funnel.

**A genuine architecture tension, surfaced by Phase 3 evaluation and requiring explicit
sign-off before Phase 4:** `README.md`'s "constraint that shapes everything" and
`CLAUDE.md`'s hard constraints both state "one receiver process, one host, one persistent
disk" for this repo's SQLite deployment. This goal's design — a second, wholly separate
receiver process for a second, wholly separate SQLite file (`data/cowork.db`) — does not
violate the single-connection-per-database principle that constraint exists to protect (each
of the two databases still has exactly one process holding exactly one connection to it), but
it does add a second OS process where the written constraint's plain text says one. This is
recorded here as a **deliberate, user-confirmed exception**, scoped narrowly to this goal:
"one receiver process" means one process per SQLite store, not one process for the whole
repo. Phase 6 must update `README.md`'s constraint language to say so explicitly, so a future
reader doesn't find an apparent contradiction between the codebase and its own ground truth.

## Discovery Summary (Phase 1 Q&A)

| Question | Answer |
|---|---|
| Data path | Live OTLP ingest (new receiver process), not the Analytics API — chosen specifically so repo/folder attribution is possible via the existing `session_repo_timeline` join, which the Analytics API cannot provide (it carries no repo dimension at all — the same limitation `report.py` already documents for `claude_code`'s Analytics path) |
| Storage | A **new, fully separate** SQLite database (`data/cowork.db`), not a table added to `otel_store.py`. Explicitly NOT merged into the existing `token_usage`/`cost_usage` schema at this stage |
| Product tagging | Every stored row is unambiguously Cowork's own (separate db + separate tables) — no shared `product` column needed to disambiguate, since nothing is shared |
| Reporting | A new, dedicated inspection tool (mirroring the shape of `records.py`'s per-record dump) over the new Cowork store — not an extension of `report.py`/`bill.py`, both of which are wired to the `claude_code` pipeline |
| Unknown/unexpected data | Fail closed, mirroring `transcript.py`'s per-record convention: reject and log rather than guess, whenever `service.name` is present but not a recognized value, or a payload doesn't match the expected metric/attribute shape |
| Rollout/admin docs | Out of scope for this goal — no changes to `deploy/README.md` or similar |
| **Isolation (hard requirement, stated explicitly by the user)** | The `claude_code` pipeline is still being actively tweaked. **No file, table, schema, process, or behavior belonging to the existing pipeline may change in any way** — not the existing `receiver.py`, not `otel_store.py`'s schema, not its default port, not any existing CLI command's output. Cowork ingestion is a brand-new, additive set of files and a brand-new server process, full stop. Merging the two pipelines is an explicit, separate, future decision |
| Phase 6 (docs alignment) | Yes |
| Phase 7 (pull request) | Yes |

**Load-bearing assumption, stated plainly, and handled by the fail-closed rule above:**
Cowork's exact OTLP metric names are not confirmed from docs alone. This goal assumes they
match the CLI's (`claude_code.token.usage` / `claude_code.cost.usage`), disambiguated purely
by the `service.name` resource attribute, because Cowork is documented to follow the same
OTEL semantic conventions. If real Cowork traffic uses different metric names, ingestion
sees `metrics_seen` in its response (mirroring `ingest_metrics_payload`'s existing pattern)
and rejects/logs unrecognized ones rather than silently dropping or mis-storing them — this
is exactly what the reporting task exists to surface before anyone trusts the numbers.

**Second load-bearing assumption:** repo attribution requires a `session_repo_timeline`
entry keyed by the Cowork session's `session.id`. It is UNCONFIRMED whether Cowork's
cloud-VM sessions ever produce one (the repo-tag hook is a `deploy/`-shipped, dev-machine
artifact; Cowork's execution environment is Anthropic-managed, not this fleet's). If no
timeline entry ever matches, Cowork rows resolve through the same `absent` fallback
`attribute.py` already defines for a session with no timeline row at all — visible, not
silently wrong. Confirming which bucket real Cowork traffic lands in is exactly what the
verification step (Success Criteria, below) is for.

**Ownership of the two constraint documents, resolved:** `README.md` (this repo's stated
ground truth, per `CLAUDE.md`'s own "`README.md` is ground truth" rule) is updated in Phase 6
to add the "one receiver process per SQLite store" clarification. `CLAUDE.md` itself is
DELIBERATELY left unchanged by this goal — it is a terse, org-level hard-constraints file, and
Phase 6 (`align-docs`) only ever touches user-facing documentation (`README.md` and friends),
never `CLAUDE.md`. A future, explicit, human-reviewed edit to `CLAUDE.md`'s wording is a
separate decision outside this goal's scope, not an oversight.

## Success Criteria

- [ ] A synthetic Cowork OTLP payload (`service.name="cowork"`), sent to the new receiver,
      is stored in the new, separate Cowork store — verified by the new reporting tool.
- [ ] A payload with `service.name="claude-code"` (the CLI's real, hyphenated value — see
      `billing/otel/sample_payload.py`) or no `service.name` at all, sent to the **existing**
      `receiver.py`, continues to behave exactly as it does today — proven by an unchanged
      fixture-DB baseline captured before any code in this goal is written.
- [ ] A payload with an unrecognized `service.name`, or a metric name other than the two
      known ones, is rejected and logged by the new Cowork receiver, never silently stored
      and never crashing the process.
- [ ] Re-sending an identical Cowork payload inserts nothing new (dedupe holds, same
      `dp_key` discipline as the existing `token_usage`/`cost_usage` tables).
- [ ] A Cowork datapoint whose `session.id` matches an existing `session_repo_timeline`
      entry (in the existing `otel.db`, read-only) resolves to that repo; one with no match
      resolves to an explicit `absent`/unknown bucket, distinguishable in the report output —
      and distinguishable from a lookup FAILURE (wrong path, unreachable db), which the report
      must flag separately rather than silently rendering as the same `absent` bucket.
      **Which bucket REAL Cowork traffic lands in is confirmed only after deployment**, once
      Cowork's Admin-settings OTLP endpoint is actually pointed at this receiver — every
      Success Criterion here is verified against synthetic payloads only, and this goal does
      not claim to know the real answer in advance.
- [ ] The new Cowork receiver runs as its own process, on its own configurable port,
      requiring its own auth token — never sharing a port, token, or database file with the
      existing `receiver.py`.
- [ ] `python -m billing.otel.bill`, `billing/reconcile.py` (run with a mocked Analytics
      client so the baseline never depends on live network access), and `receiver.py`'s own
      `ingest_metrics_payload` behavior are byte-for-byte/value-for-value unchanged against a
      pre-goal baseline (same commands, same fixture data, same output) — the isolation
      requirement is a tested assertion, not a design intention.
- [ ] A synthetic `service.name="cowork"` payload sent to the EXISTING `receiver.py` (not the
      new one) behaves in this goal exactly as it does today — that receiver has no
      `service.name` filter and never will, per the isolation constraint, so such a payload is
      still accepted and billed as ordinary `claude_code` usage. This is documented, tested,
      and captured as a known, accepted consequence of never touching `receiver.py`: this goal
      makes correctly-routed Cowork traffic visible, it does not make the existing receiver
      reject Cowork traffic sent to the wrong port.
- [ ] No existing file's schema, default port, or CLI flags changed. `git status --porcelain`
      against `billing/otel/receiver.py`, `billing/otel/otel_store.py`,
      `billing/otel/attribute.py`, `billing/otel/normalize.py`, `billing/otel/transcript.py`,
      `billing/otel/records.py`, `billing/otel/sample_payload.py`, `billing/reconcile.py`,
      `billing/otel/bill.py`, and `billing/report.py` is empty.

## Constraints

- **Standard library only.** No third-party import may enter `billing/`. `pytest` remains
  the sole dev dependency, under `tests/` only.
- **Full isolation from the `claude_code` pipeline.** Every new file is additive. Existing
  files listed above must show a clean `git diff` at the end of this goal. If achieving a
  requirement would require touching one of them, stop and flag it rather than doing it.
- **New, separate SQLite database** (`data/cowork.db`, single-host/single-connection, same
  constraint class as the existing `otel.db`) — never a table inside `otel_store.py`'s schema.
- **Repo attribution stays resolved at query time**, same invariant as `attribute.py`: the
  Cowork store never persists a resolved repo, only the raw session id + attributes needed
  to resolve it later, exactly like `token_usage`/`cost_usage` do today.
- **Read-only access to the existing `otel.db`** for the `session_repo_timeline` lookup only
  — opened as a separate, explicitly read-only connection (SQLite URI `mode=ro`); nothing in
  this goal ever writes to `otel.db` or opens it read-write.
- **Fail closed on anything unrecognized** — an unknown `service.name`, an unknown metric
  name, or a malformed attribute is rejected and logged per-record (batches never poisoned
  by one bad record), mirroring `transcript.py`'s existing `validate_batch` convention. "Logged"
  is a concrete requirement, not a figure of speech: the new receiver process (task 03) must
  write every rejection to its own request log, with reason + minimal identifiers, never raw
  payload bytes — the same privacy discipline `receiver.py` already applies to its own
  `/v1/transcript-usage` 400 path.
- **Own auth token, own port.** A distinct env var (not `RECEIVER_AUTH_TOKEN`) gates writes
  to the new receiver, and it listens on its own configurable port, default distinct from
  `4318`. Never committed — same secrets discipline as the rest of `.env`.

## Out of Scope

- Any change to `reconcile.py`'s funnel, `bill.py`, `invoice.py`, or the Analytics-API path
  (`analytics_client.py`, `products=[...]` filters). Merging Cowork into the funnel is an
  explicit, separate future goal, gated on this one's verification succeeding.
- Any change to `deploy/README.md`, `deploy/managed-settings.json`, or any rollout/admin
  guidance for pointing Cowork's Admin-settings OTLP endpoint at the new receiver. That is a
  human/ops follow-up once this pipeline is proven.
- Fabric/ADLS export (`export.py`, `fabric_sync.py`, `fabric_client.py`) for Cowork data.
- A rate card or cost estimation for Cowork specifically — `cost.usage` datapoints are
  stored as reported; no `rating.py`-style markup logic is added in this goal.
- Any change to the existing `token_usage`/`cost_usage`/`session_repo_timeline` schema.
- Exposing the new receiver's port (`4319` by default) through `docker-compose.yml`/Caddy, or
  any other network/TLS-reachability work. Today only `4318` is proxied; making the new
  receiver reachable off-box is a deployment decision for a human, deliberately deferred.

```yaml
phases:
  align_docs: true
  pull_request: true
  ladder: escalate
```

## Tasks (dependency order)

| # | Task file | Layer | Depends on |
|---|-----------|-------|------------|
| 00 | `00-test-scaffold.md` | Tests (scaffold + pre-change baseline) | — |
| 01 | `01-cowork-store-schema.md` | Store & schema | 00 |
| 02 | `02-cowork-ingest-payload.md` | Ingest (payload contract) | 00, 01 |
| 03 | `03-cowork-receiver.md` | Ingest (endpoint / process) | 00, 01, 02 |
| 04 | `04-cowork-reporting.md` | Rating & billing (reporting-only) | 00, 01, 02, 03 |
| 05 | `05-integration.md` | Tests (integration + isolation proof + closer) | all |

**Contract first.** Task 00 captures the pre-change baseline (existing `bill.py`/
`reconcile.py`/`receiver.py` output against a fixture `otel.db`) before any production file
in this goal is touched — the only point at which that baseline can honestly be taken. Task
01 then freezes the new store's schema and insert signatures that 02–04 consume. Task 02
freezes the OTLP-payload-to-row mapping (including the fail-closed rules) that 03 depends on
for the live receiver and that 04 depends on for report field names.
