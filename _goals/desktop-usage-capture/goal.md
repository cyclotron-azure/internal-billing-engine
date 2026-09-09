# Goal: desktop-usage-capture

## Problem Statement

Claude Code desktop app usage is never billed. Its OTLP metrics exporter does not exist — telemetry
export is a CLI-only capability, and the VS Code extension only works because it spawns the CLI
underneath. The fleet's `deploy/managed-settings.json` env block is correct and IS applied on desktop,
but there is no exporter for it to configure, so no settings change can ever fix this. Every token a
developer spends in the desktop app is real money that currently bills to nobody, and the gap is
invisible: nothing reports it as missing.

The fix is to capture desktop usage from the transcripts Claude Code already writes to disk
(`~/.claude/projects/**/*.jsonl`), delivered over hooks — the one mechanism that documentably runs on
every surface, desktop included.

## Discovery Summary (Phase 1 Q&A)

Pre-flight diagnosis (verified, not assumed):

- Official docs: OTLP export is documented for the CLI only.
- Local evidence: `entrypoint` values on disk are `cli`, `claude-vscode`, `claude-desktop`. Desktop
  sessions ARE recorded.
- A desktop usage record carries `sessionId`, `cwd`, `gitBranch`, `timestamp`, `requestId`,
  `message.model`, and `message.usage{input_tokens, output_tokens, cache_creation_input_tokens,
  cache_read_input_tokens}`.
- **A transcript row is NOT a billable unit.** Measured on real transcripts: 402 usage-bearing rows
  carry only 187 distinct `requestId`s, and 149 repeat up to 5x. Rows sharing a
  `(requestId, message.id)` are **cumulative streaming snapshots of ONE API request** — input and cache
  counts hold constant while `output_tokens` grows. The billable total for a request is the **terminal
  block**, identified by the highest `apiBlockIndex` (tie-break: file order, last wins). `stop_reason`
  is NOT a valid selector: measured across 230 real groups, 108 carry two or more non-null values and
  3 carry none. Summing rows over-bills by
  ~2.28x ($64.38 against a correct $28.28 across this machine's transcripts at the repo's placeholder
  rates); keeping the first block under-bills output by 34%, ~8.6% overall. The hook therefore
  collapses per request client-side, and the store's `INSERT OR IGNORE` is a replay guard only — it
  keeps the FIRST insert and cannot be relied on to pick the right snapshot.
- Hooks docs, verbatim: "Claude Code fires the same hook events wherever it runs: sessions in the
  terminal, IDE extensions, the Desktop app, and Claude Code on the web." `SessionEnd` receives
  `transcript_path`, `session_id`, `cwd` on stdin.
- Claude Code does NOT pass `OTEL_*` env vars to hook subprocesses. The existing hook correctly uses
  `CLAUDE_BILLING_*`; that pattern is preserved.
- Transcripts carry NO user identity (`userType: "external"` only). `~/.claude.json` holds
  `oauthAccount.emailAddress` / `.accountUuid` / `.organizationUuid` — the same values OTLP reports as
  `user.email` / `user.id` / `org.id`.

- **Subagent usage lives in separate, more deeply nested files.** Claude Code writes sidechain
  (subagent) usage to `<project_dir>/<sessionId>/subagents/agent-<agentId>.jsonl` — one level below the
  project directory. Those rows carry the parent's `sessionId` and `entrypoint`, are flagged
  `isSidechain: true`, and appear NOWHERE in the main session transcript. Measured at Claude Code
  `2.1.259`: a recursive walk of `~/.claude/projects` finds 9 transcript files where a flat
  per-project-directory glob finds 4 — missing every sidechain file and **30.0% of total spend**
  ($13.78 of $45.87). The hook therefore enumerates the projects tree **recursively from the root**,
  keying state by absolute path, and treats `transcript_path` purely as a priority hint. Subagent usage
  bills to its parent session's repo (the shared `sessionId` makes the existing as-of join resolve it)
  and is tagged `query_source='subagent'`, an enum `otel_store.py:31` already documents.

- **Each desktop scratch session gets its OWN project directory** (observed:
  `C--Users-…-AppData-Roaming-Claude-scratch-workspaces-<uuid>-<uuid>-scratch-<date>-<hash>`). The
  catch-up sweep must therefore span all project directories, not just the current one, or it can never
  reach a crashed desktop session — the exact case the sweep exists for.

**Load-bearing assumptions, stated plainly.** (a) The desktop app has no OTLP exporter — verified
against current documentation, but a product fact that could change; if it becomes false, both
double-billing filters are defeated at once, which is why the overlap detector is a success criterion
and not a nice-to-have. (b) One hook run can see all of a session's usage on disk — FALSE in earlier
drafts that parsed only `transcript_path` (~32% under-bill); it holds now only because the hook
enumerates recursively. (c) **The on-disk transcript layout is stable across Claude Code versions —
this is the weakest assumption in the plan and it has been violated repeatedly.** Five review cycles
found five previously-unknown data-model facts, each changing the billed amount: `dp_key` mechanics,
rows being cumulative streaming snapshots, subagent usage living in separate files, those files being
nested a level deeper than assumed, and in-flight groups shipping partially. The design reads
undocumented internal structure observed at version `2.1.259`, with no contract preventing further
change.

Two structural mitigations follow from (c), and neither is optional: the hook enumerates recursively
from the projects root rather than encoding any directory shape, and rows are classified by the
`isSidechain` flag rather than by filename. **A third mitigation is deliberately deferred and named
here as the clearest known residual risk:** extending `billing/reconcile.py`'s existing coverage funnel
to cover desktop would give an independent check against the authoritative Anthropic Analytics totals,
catching a shortfall of this class regardless of what the layout does next. That is a follow-up goal,
not scope here — but without it, a future layout change fails the same way every previous one did:
silently, with a plausible number.

Decisions (Phase 1):

| Question | Answer |
|---|---|
| Double-billing vs OTLP | Desktop-only filter: ship a record only when `entrypoint == "claude-desktop"` |
| Sessions with no repo | New `desktop-scratch` attribution bucket, distinct from `unknown` |
| Reliability | SessionEnd hook + catch-up sweep against a stored watermark |
| Identity source | `oauthAccount` from `~/.claude.json`. `~/.claude/.credentials.json` is NEVER read |
| Payload | Usage metadata only — no message content, prompts, tool output, or transcript text |
| Backfill | Forward-only; watermark starts at install. Closed periods untouched |
| Rollout tracks | `deploy/` (MDM) and `client-package/` (opt-in). `pilot-package/` excluded as superseded |
| Phase 6 align docs | Yes |
| Phase 7 pull request | No — work stays local and uncommitted |

Decisions (Phase 2 gates):

| Gate | Answer |
|---|---|
| How desktop acquires a cost | Rate desktop tokens at ingest into `cost_usage`, tagged `cost_source='rate_card'`; OTLP rows tagged `'actual'`. `bill.py`/`invoice.py` label the mix honestly |
| Hook shape | New standalone `claude-transcript-usage.py`, SessionEnd only. `claude-repo-tag.py` stays untouched — it runs async on every prompt and must stay small |
| Storage | `token_usage` gains `usage_source` + `entrypoint`; `cost_usage` gains `usage_source` + `cost_source`. One message maps to the existing four `token_type` rows. All existing consumers keep working |

## Success Criteria

- [ ] A desktop-app session's token usage reaches the store and appears in `python -m billing.otel.bill`
      at the **exact correct amount** — asserted against known fixture totals, and asserted to be neither
      the naive sum of cumulative blocks nor the first-block value. "Non-zero" is not sufficient: both
      known failure modes produce non-zero, plausible-looking numbers.
- [ ] One malformed record does not discard the valid records batched alongside it.
- [ ] Two overlapping sessions, where the older one's `SessionEnd` fires last, both ship completely.
- [ ] The same usage is NOT double-counted when the machine also runs CLI or VS Code sessions.
- [ ] `bill.py` warns when any session carries both OTLP and transcript token rows — the only signal that
      would surface a breach of the double-billing guard, since the client-side and server-side filters
      test the same predicate and are not independent defenses.
- [ ] `bill.py` states how much of the total is Anthropic-reported actual cost and how much is rate-card
      estimate, rather than labelling estimates as actuals.
- [ ] Desktop usage carries `user_email` / `user_id` / `org_id` through to the stored rows, so the lake
      CSVs' per-user grain is populated for desktop the same as for CLI.
- [ ] A desktop session in a scratch workspace is reported as `desktop-scratch`, distinguishable from
      `no_remote` and `absent`.
- [ ] A session whose `SessionEnd` never fires is still captured by the catch-up sweep on a later
      session — enforced by task 06 criterion 7d, not by prose alone.
- [ ] Subagent usage from `agent-*.jsonl` sidechain files is captured and billed to the parent
      session's repo — roughly a third of total spend on a real machine.
- [ ] A batch that the receiver permanently rejects does not stall all later desktop billing behind it.
- [ ] A developer working offline for several sessions loses no billing data — transport failures retry
      indefinitely and never consume the drop bound reserved for permanent rejections.
- [ ] A session that crashes mid-request still bills its final group: a withheld in-flight group ships
      once the file goes idle, even though nothing is ever appended to it again.
- [ ] `POST /v1/transcript-usage` returns 401 unauthenticated and 400 on a malformed body, matching the
      existing endpoints, and its 400 log line contains no request-body bytes.
- [ ] Re-POSTing an identical batch inserts nothing; two records differing only in `request_id` both insert.
- [ ] No message content, prompt text, tool output, or transcript text appears in any transmitted payload.
- [ ] An existing `otel.db` migrates in place without data loss, and `bill.py` output for an OTLP-only
      store is unchanged against a baseline captured before any code changed.
- [ ] Both enrolment tracks install the hook end to end, including the opt-in track's packaging.

## Constraints

- **Standard library only.** No third-party import may enter `billing/`, `deploy/`, or `client-package/`.
  `pytest` is the sole dev dependency and lives only under `tests/`. It is not installed by default —
  `python -m pip install pytest` is a one-time step.
- **The hook must never break a developer's session.** Always exit 0, short timeouts, failures swallowed.
- **Never read `~/.claude/.credentials.json`.** Identity comes from `~/.claude.json` only.
- **SQLite stays single-host, single-connection.** No threading the receiver, no pool.
- **Repo attribution stays resolved at query time.** `attribute.py` must not persist resolution.
- **Migrations are additive and idempotent** — a live billing DB is in use; every `ALTER TABLE` guarded.
- Existing OTLP rows must keep billing exactly as they do today; `usage_source='otlp'` and
  `cost_source='actual'` defaults preserve current behavior for every existing row.
- **Repo-key canonicalization is server-side only.** The hook ships the raw remote; `normalize.py` on the
  receiver decides the key, exactly as `claude-repo-tag.py` already works.
- **No file paths on the wire.** `cwd` is deliberately excluded from the payload: the opt-in consent
  notice at `client-package/configure.py:109` and `client-package/INSTRUCTIONS.md:76` states that file
  paths are not collected, and a desktop `cwd` is one. `repo_raw` carries everything attribution needs.
  The server's fail-closed unknown-field rule enforces this rather than trusting the client.
- **A rollback path must exist.** Unregistering the hook stops ingest; `usage_source='transcript'` makes
  every row this feature wrote selectable for deletion without touching an OTLP row.

## Out of Scope

- Web-surface (`claude.ai/code`) capture — the desktop-only filter deliberately excludes it.
- Backfilling transcripts that predate install.
- Replacing the OTLP path for CLI/VS Code; OTLP remains authoritative where it works.
- **Surfacing `cost_source` in the lake CSVs (`export.py`).** Desktop usage WILL flow into
  `claudeusagesummary` / `claudeusagelineitems` automatically, but Fabric will not be able to tell
  rate-card estimates from Anthropic actuals. Accepted for now and pinned by a test in task 07 so the
  state is deliberate. **Follow-up candidate, and the clearest known gap this goal leaves open.**
- **Invoice regeneration semantics.** `invoice.py:83-86` already does `DELETE` + `INSERT OR REPLACE`;
  regenerating replaces in place. That shipped behavior is explicitly untouched here — task 05 must
  neither change it nor be failed for leaving it. Note this is *separate* from `summary.csv` /
  `line_items.csv` labelling, which IS in scope for task 05.
- **Web/scratch revenue expectation.** The only real `claude-desktop` session observed ran in a scratch
  workspace with no git remote, and `invoice.py` excludes `unknown` from invoicing. For scratch-mode
  desktop work this goal delivers *visibility* (the `desktop-scratch` bucket) rather than *billable
  attribution*. That is the accepted outcome of the Phase 1 decision, not a defect.
- Replacing the placeholder rate card in `rating.py`. Desktop cost is estimated at placeholder rates;
  `claude-opus-5` has no entry and falls back to `DEFAULT_RATE` ($5/$25 per 1M).
- **`server_tool_use` (web search / web fetch), which Anthropic prices per request.** The payload schema
  has no field for it. Measured zero across all local transcripts, so nothing is lost today — but if
  desktop users adopt web search, that spend is structurally uncapturable by this design. Recorded as a
  decision rather than an omission, and a follow-up candidate.
- **The 1-hour vs 5-minute cache-write split.** `cache_creation` conflates
  `ephemeral_1h_input_tokens` and `ephemeral_5m_input_tokens` (measured 58% / 42% of 5.2M tokens),
  which price differently. Pre-existing and identical on the OTLP path — this goal inherits the
  limitation rather than introducing it, and it belongs with the deferred rate-card work.
- Regenerating `client-package.zip`. Task 06 wires the packaging; producing and distributing a new zip
  is a human rollout step called out in that task's report.
- `pilot-package/` — superseded.

## Tasks (dependency order)

| # | Task file | Layer | Depends on |
|---|-----------|-------|------------|
| 00 | `00-test-scaffold.md` | Tests (scaffold + pre-change baseline) | — |
| 01 | `01-store-schema.md` | Store & schema | 00 |
| 02 | `02-transcript-payload.md` | Ingest (payload contract) | 00, 01 |
| 03 | `03-receiver-endpoint.md` | Ingest (endpoint) | 00, 01, 02 |
| 04 | `04-attribution.md` | Attribution & normalization | 00, 01 |
| 05 | `05-billing-basis.md` | Rating & billing | 00, 01, 04 |
| 06 | `06-client-hook.md` | Client rollout | 00, 02, 03 |
| 07 | `07-integration.md` | Tests (integration + closer) | all |

**Contract first.** Task 00 scaffolds tests and captures the pre-change billing baseline before any
production file is touched — the only point at which that baseline can honestly be taken. Task 01 then
freezes the schema, key composition, and insert signatures that 02–06 consume, and task 02 freezes the
wire payload contract that 03 and 06 both depend on. Each implementation task owns its own targeted test
file, so no change lands on live billing code without assertions.
