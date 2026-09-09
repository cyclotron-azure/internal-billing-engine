# Orchestration Log: desktop-usage-capture

Append-only spawn ledger. `est_tokens` = (context_chars + report_chars) / 4 — a character-based
PROXY, not a true token count; no harness in this kit exposes real token counts.

**Running est_tokens total: 0** (updated after each return)

---

## 2026-09-04 — Phase 3 — goal evaluation (cycle 1)

- **Agent:** evaluator
- **Model:** claude-opus-5 (frontier tier, agent-pinned; no rotation — cycle 1)
- **Routing reason:** Phase 3 mandatory goal evaluation. Only exit to Phase 4 is a PASS verdict.
- **Task writes fence:** NONE — evaluation only, no file writes permitted
- **Expected outputs:** Verdict, Score, Discovery Coverage table, Acceptance Criteria Validation,
  Required Fixes (failure-class tagged), Observations
- **context_chars:** 5665

### Return — Phase 3 cycle 1

- **Verdict:** NEEDS REVISION · **Score:** 3/5
- **report_chars:** 16480
- **est_tokens:** (5665 + 16480) / 4 = **5536** (estimate — character proxy, not a true token count)
- **Required fixes returned:** 10 (7 tagged `implementation`, 3 tagged `criteria-defect`; no bypass
  class — nothing tagged destructive/security/infra, so no escalation-at-detection)
- **Orchestrator verification of the three load-bearing claims** (evaluator claims are not taken on
  trust):
  - Fix 1 CONFIRMED — `resolved_view('cost_usage')` is live at `bill.py:57` and `export.py:78`.
    Task 04's branch referencing `t.usage_source` would raise `OperationalError` at prepare time and
    take down `bill.py` and the lake export for the EXISTING fleet, not just desktop rows.
  - Fix 2 CONFIRMED — `otel_store.py:138` `dp_key(session_id, model, token_type, query_source,
    time_unix_nano)` carries no `request_id`. Two desktop messages in one session/model/second
    collide and `INSERT OR IGNORE` drops the second: silent under-billing.
  - Fix 6 CONFIRMED — `invoice.py:83,86` already does `DELETE FROM invoice_line_items` +
    `INSERT OR REPLACE INTO invoices`. Task 05's "records remain immutable" requirement contradicted
    shipped behavior and would have trapped the implementer between two impossible constraints.
- **Assessment:** all 10 fixes accepted as valid. No fix rejected, none deferred.

### Structural revision decided by the orchestrator (beyond the 10 fixes)

The evaluator observed that tasks 01–06 would each land on live billing code with zero assertions,
because a single trailing test task owned all of `tests/`. That also made task 05's baseline-capture
criterion unsatisfiable — the baseline must be captured BEFORE `bill.py` is modified, but the only
task allowed to write tests ran last. Accepted. Restructure:

- New task `00-test-scaffold` (test-writer, no dependencies): creates `tests/conftest.py` with shared
  fixtures AND captures the current `bill.py` output as a golden baseline before any production file
  changes. This resolves Fix-adjacent criterion 05.1 by sequencing.
- Each implementation task now OWNS its own targeted test file, so every task evaluation has a real
  rung-1 command to run.
- Task 07 becomes integration + cross-cutting coverage (`export.py`, the desktop end-to-end path) and
  carries the written rung-3 closer mandate that Fix 8 requires.

Write-sets stay disjoint because test files are declared as explicit paths, never a `tests/` glob.

## 2026-09-04 — Phase 3 — goal revision (cycle 1 → cycle 2)

- **Actor:** orchestrator (planning artifacts only — no product code touched)
- **Revisions applied:** all 10 required fixes, plus the structural change recorded above.
  - Task count 7 → 8: added `00-test-scaffold`; `07-tests.md` deleted, replaced by `07-integration.md`.
  - Fix 1: `usage_source` now required on `cost_usage` as well as `token_usage` (task 01), with a
    `resolved_view('cost_usage')` regression criterion plus a cross-module smoke criterion (task 04).
  - Fix 2: separate `request_id`-keyed transcript key function frozen in task 01, with an explicit
    criterion that two records differing only in `request_id` produce two rows.
  - Fix 3: task 02 now owns the wire payload contract as a code-level constant including `repo_raw`;
    identity passthrough required and criterion-tested in both 02 and 03.
  - Fix 4: task 06 write-set gains `client-package/claude-transcript-usage.py` and
    `client-package/build.py`; byte-identity and CONTENTS-membership criteria added; zip regeneration
    named as a human rollout step.
  - Fix 5: watermark advances only on 200; bounded retries; drop-and-advance with a local record.
  - Fix 6: invoice split derived at generation time, not persisted; existing regeneration semantics
    moved to Out of Scope in goal.md and pinned by a criterion.
  - Fix 7: task 03 logs no request-body bytes on its 400 path, as a documented divergence.
  - Fix 8: rung-3 closer promoted to a written requirement of task 07; COVERAGE_MAP.md replaces
    self-attestation.
  - Fix 9: overlap detector added to task 05 and promoted to a goal-level success criterion.
  - Fix 10: depends_on completed, test file renamed to `tests/test_configure.py` to match the
    convention map, per-file `rewrite_semantics` noted.
- **Orchestrator re-validation:** 26 unique owned paths across 8 tasks, all pairs disjoint, every
  `depends_on` resolves, graph acyclic.

## 2026-09-04 — Phase 3 — goal evaluation (cycle 2)

- **Agent:** evaluator (FRESH spawn, not a continuation of the cycle-1 agent)
- **Model:** claude-opus-5 (frontier tier, agent-pinned)
- **Routing reason:** mandatory re-evaluation after revision. A fresh evaluator is spawned rather than
  continued: asking an evaluator to grade its own fix list is the self-review blindness this
  architecture exists to remove. The 10 fixes are passed as input to verify, but every other
  judgement is re-derived independently.
- **Task writes fence:** NONE — evaluation only
- **Expected outputs:** Verdict, Score, Fix Verification table (10 rows), Independent Findings,
  Acceptance Criteria Validation, Required Fixes, Observations
- **context_chars:** 5089

### CORRECTION — the cycle-2 entry above did not occur as written

The preceding "Phase 3 — goal evaluation (cycle 2)" entry was written before the spawn, per this
kit's before-launch ledger rule. **That spawn was interrupted by the user and never ran.** No
evaluator executed, no verdict was produced, and no report was returned for it. The entry is left in
place because this ledger is append-only; this correction is the authoritative record of it.

State at the time of interruption: the goal was revised through all 10 cycle-1 required fixes and
re-validated by the orchestrator (26 unique owned paths, disjoint, acyclic), but carried **no PASS
verdict**. Phase 4 had not begun and no product file had been modified.

## 2026-09-04 — Phase 3 — goal evaluation (cycle 2, actual)

- **Agent:** evaluator (FRESH spawn, not a continuation of the cycle-1 agent)
- **Model:** claude-opus-5 (frontier tier, agent-pinned; Phase 3 re-evaluation does not rotate models
  — rotation is a Phase 4 fix-cycle mechanism)
- **Routing reason:** mandatory re-evaluation after revision, resumed at the user's instruction. A
  fresh evaluator is spawned rather than continued: asking an evaluator to grade its own fix list is
  the self-review blindness this architecture exists to remove. The 10 cycle-1 fixes are passed as
  input to verify; every other judgement is re-derived independently.
- **Task writes fence:** NONE — evaluation only, no file writes permitted
- **Expected outputs:** Verdict, Score, Fix Verification table (10 rows), Independent Findings,
  Acceptance Criteria Validation, Required Fixes (failure-class tagged), Observations
- **context_chars:** 5089

### Return — Phase 3 cycle 2

- **Verdict:** NEEDS REVISION · **Score:** 3/5
- **report_chars:** 18240
- **est_tokens:** (5089 + 18240) / 4 = **5832** (estimate — character proxy)
- **Fix verification of cycle 1's ten:** 7 RESOLVED, 3 PARTIAL (2, 5, 10). None UNRESOLVED.
- **New required fixes:** 16 (11 `implementation`, 5 `criteria-defect`). No bypass class — nothing
  tagged destructive/security/infra, so no escalation-at-detection.
- **Independent orchestrator verification of the blocker (Finding 1):** CONFIRMED, and materially
  WORSE than the evaluator characterised it.

#### The blocker, measured against real transcripts on this machine

The evaluator reported that `requestId` is not unique per assistant message and that repeated rows
carry "byte-identical usage". The first half is right; the second half is wrong, and the difference
is what makes this dangerous.

Measured over 402 assistant rows carrying usage across all local transcripts:

- 187 distinct `requestId`; 149 of them repeat, up to 5x.
- Of the repeated groups: 82 carry identical usage, **67 carry DIFFERING usage**.
- All 67 differing groups share the SAME `message.id` and differ only by `apiBlockIndex`.

Inspecting them establishes the semantics: rows sharing `(requestId, message.id)` are **cumulative
streaming snapshots of one API request**, not separate charges. `input_tokens`,
`cache_creation_input_tokens`, and `cache_read_input_tokens` stay constant across the group while
`output_tokens` GROWS, and only the terminal block carries a non-null `stop_reason`:

    apiBlockIndex=0  stop=None      tok(in,out,cc,cr) = (2,   5, 13984, 35774)
    apiBlockIndex=1  stop=tool_use  tok(in,out,cc,cr) = (2, 209, 13984, 35774)

The correct total for a request is therefore the TERMINAL block, not the sum and not the first.

Three interpretations, totalled across all local transcripts, priced at the repo's own placeholder
rate card for `claude-opus-5`:

| Interpretation | input | output | cacheCreate | cacheRead | raw cost |
|---|---|---|---|---|---|
| Naive sum of rows (task 06 as written) | 2.16x | 1.90x | 2.81x | 2.15x | **$64.38** |
| First block — what `INSERT OR IGNORE` keeps (task 01 as written) | 1.00x | **0.66x** | 1.00x | 1.00x | **$25.85** |
| Terminal block — correct | 1.00x | 1.00x | 1.00x | 1.00x | **$28.28** |

**Both of the plan's two halves were wrong, in opposite directions.** Task 06 said "one usage record
per assistant message", which sums cumulative snapshots and over-bills a client by ~2.28x. Task 01's
collapse key would then have been rescued by `INSERT OR IGNORE` — except that keeps the FIRST insert,
which is `apiBlockIndex=0`, discarding 34% of output tokens and under-billing by ~8.6% overall.

Neither error would have surfaced: every acceptance criterion in the goal checked presence, shape, or
non-zero-ness. Not one pinned an amount. This is precisely the "plausible but wrong number" failure
the cycle-1 evaluator predicted in its pre-mortem.

**Resolution to apply:** collapse client-side per `(requestId, message.id)` to the terminal block
(highest `apiBlockIndex`, or the row whose `stop_reason` is non-null), emit ONE record per request,
and pin the exact expected token counts and dollar amount in an acceptance criterion against a
fixture built from a real multi-block transcript shape.

- **Other confirmed cycle-2 findings:** `cwd` in the frozen payload contradicts the consent notice in
  `client-package/configure.py` and `INSTRUCTIONS.md` ("does not collect file paths"), and `cwd` is
  stored nowhere. Byte-identity of the two hook copies is unenforceable under `core.autocrlf=true`
  (the existing precedent pair already differs, 4521 B CRLF vs 4414 B LF). `bill.py` `/markup` is at
  line 96, not 107, in tasks 02 and 05.

## 2026-09-04 — Phase 3 — goal revision (cycle 2 → cycle 3)

- **Actor:** orchestrator (planning artifacts only — no product code touched)
- **All 16 cycle-2 required fixes applied.** The substantive ones:
  - **Fixes 1 & 2 (the blocker).** Task 01's false "`request_id` is unique per assistant message"
    premise replaced with the measured truth and the cumulative-snapshot semantics. Task 06 now emits
    one record per API REQUEST, collapsing `(sessionId, requestId, message.id)` groups to the terminal
    block, with the real observed numbers written into the task. Task 00's fixture must contain the
    cumulative multi-block shape and publish expected totals. Tasks 06 and 07 now assert EXACT amounts
    and explicitly assert the result is neither the naive sum nor the first block. Task 01 gains
    criterion 5b pinning `INSERT OR IGNORE` first-writer-wins so no task can quietly depend on the
    store to choose the right snapshot.
  - **Fix 3.** Per-transcript-file state replaces the single global watermark; advance only on 200 and
    never past the earliest unconfirmed record; batches emitted in non-decreasing `ts` order;
    criterion 7b covers two overlapping sessions where the older ends last.
  - **Fix 4.** Validation is now per-record in task 02, with a rejected count in the 200 body (task 03).
    Whole-batch 400 is reserved for an unusable envelope. One bad record can no longer discard a batch.
  - **Fix 5.** `cwd` removed from the frozen payload — it is a file path, and the opt-in consent notice
    at `configure.py:109` / `INSTRUCTIONS.md:76` promises file paths are not collected. Enforced by the
    fail-closed unknown-field rule, so the guarantee holds server-side rather than trusting the client.
  - **Fix 6.** Actual-vs-estimated labelling extended to `summary.csv` and `line_items.csv`, which sit
    beside the `.txt` in the same client-facing directory and carry an `actual_cost_usd` column.
    `export.py`'s lake CSVs remain Out of Scope, as scoped.
  - **Fix 7.** Task 05's split lines are emitted conditionally, so the golden byte-match on an
    OTLP-only store stays satisfiable alongside the reporting requirement.
  - **Fix 8.** Task 01 criterion 3 restated as set-equality over `(name, type, notnull, dflt_value)`,
    dropping `cid`, since `ALTER TABLE` can only append.
  - **Fix 9.** Byte-identity restated as content-identity after newline normalization, with the
    measured precedent (4521 B CRLF vs 4414 B LF) written into the task. `.gitattributes` added to
    task 06's write fence with a requirement to pin `deploy/*.py text eol=lf`, closing the CRLF-shebang
    failure on macOS/Linux fleet machines.
  - **Fix 10.** Task 00 names the seeded-OTLP fixture (not the frozen legacy one) as the golden
    baseline's source, with the reason.
  - **Fix 11.** Per-hook event map: the transcript hook is `SessionEnd` only on BOTH tracks;
    `claude-repo-tag.py` keeps all five. `cmd_verify` scope stated.
  - **Fixes 12–16.** `bill.py:96` citation corrected in tasks 02 and 05; `test_receiver.py` renamed per
    the convention map; `LOG_PATH` module-attribute patching noted; rollback runbook required in task
    06 criterion 15; task 07's out-of-fence escalation path written into its constraints.
  - Also added: git-remote lookup cached per distinct `cwd` (215 records must not spawn 215
    subprocesses inside a hook).
- **Orchestrator re-validation:** 27 unique owned paths across 8 tasks, all pairs disjoint, every
  `depends_on` resolves, graph acyclic.

## 2026-09-04 — Phase 3 — goal evaluation (cycle 3, FINAL cycle)

- **Agent:** evaluator (FRESH spawn)
- **Model:** claude-opus-5 (frontier tier, agent-pinned)
- **Routing reason:** mandatory re-evaluation after revision. **This is cycle 3 of 3.** Per the feature
  skill, a non-PASS verdict here exhausts Phase 3's retry budget and the orchestrator escalates to the
  user with options rather than revising a fourth time.
- **Task writes fence:** NONE — evaluation only
- **Expected outputs:** Verdict, Score, Fix Verification (16 rows), Independent Findings, Acceptance
  Criteria Validation, Required Fixes, Observations
- **context_chars:** 4610

### Return — Phase 3 cycle 3 (FINAL cycle)

- **Verdict:** NEEDS REVISION · **Score:** 3/5
- **report_chars:** 17920
- **est_tokens:** (4610 + 17920) / 4 = **5632** (estimate — character proxy)
- **Cycle-2 fix verification:** 14 of 16 RESOLVED, 2 PARTIAL (fix 3's sweep half, fix 9's stale
  constraint line). None UNRESOLVED.
- **Collapse-rule audit:** the terminal-block rule was independently verified correct against 496 real
  usage rows — input/cache constant per group, output non-decreasing, `apiBlockIndex` unique and
  ascending, max-`apiBlockIndex` always the last row in file order, no group spanning files. The
  cycle-2 blocker is genuinely fixed.
- **New required fixes:** 8 (6 `implementation`, 2 `criteria-defect`), of which 2 are BLOCKING. No
  bypass class — nothing destructive/security/infra.

#### BLOCKING-1, independently verified by the orchestrator — and larger than reported

Claude Code writes **subagent usage to separate `agent-<agentId>.jsonl` files** in the same project
directory. They carry the same `sessionId` and `entrypoint` as the parent, are flagged
`isSidechain: true`, and appear **nowhere** in the main session transcript.

Orchestrator's own measurement across all 8 local transcript files, collapsed by the terminal-block
rule and priced through `RatingService` at the repo's markup:

| Source | Files | Request groups | Output tokens | Cache-read tokens | Billed USD |
|---|---|---|---|---|---|
| Main transcripts | 4 | 138 | 222,567 | 30,253,278 | $39.80 |
| `agent-*.jsonl` | 4 | 109 | 143,129 | 10,238,824 | $18.65 |
| **Combined (correct)** | 8 | 247 | — | — | **$58.45** |

Cross-checks: 0 rows with `isSidechain=True` appear in any non-agent file; 217 of 217 rows in
`agent-*.jsonl` are flagged sidechain. The two sets are disjoint.

**A hook that parses only the file named by `transcript_path` under-bills by 31.9%** — the evaluator
measured 27.9%, and the figure rose during this very session because each evaluator spawn wrote
another `agent-*.jsonl`. Half this project's transcript files are sidechain files.

This is a silent scope narrowing rather than a scoped-out decision: `goal.md`'s Problem Statement
scopes the feature to `~/.claude/projects/**/*.jsonl`, a glob that includes `agent-*.jsonl`. A
`grep -rniE "sidechain|subagent|agent-|agentId"` over the goal directory returns zero hits outside
this log. The repo already knows subagents are a distinct signal: `deploy/claude-repo-tag.py:85-87`
posts `agent_id` with the comment "keep the id so a future refinement can attribute them separately",
and `otel_store.py:31` already types `query_source` as `main | subagent | auxiliary`.

**BLOCKING-2:** `goal.md`'s success criterion "a session whose `SessionEnd` never fires is still
captured by the catch-up sweep" has no acceptance criterion in any task. Criterion 6 tests re-running
over one transcript; 7b tests two sessions that both end. Neither tests the never-fired case — the
mechanism whose implementation also determines whether BLOCKING-1 is accidentally mitigated.

Remaining 6 fixes are small and concrete: the `stop_reason` "equivalently" claim is false (108 of 230
groups carry ≥2 non-null, 3 carry zero — zero money impact, but it invites an undefined
implementation); task 00's duplicate-pair fixture must carry non-null `stop_reason` on both rows to
match the only real desktop request; a stale "byte-identical" line survives in task 06's Constraints;
`query_source` is unspecified for transcript rows; forward-only first-run initialisation is ambiguous
under per-file state; `configure.py:109` should be `:110`.

## 2026-09-04 — Phase 3 — ESCALATION (retry budget exhausted)

- **Trigger:** three goal-evaluation cycles completed, none returning PASS. Per the feature skill,
  Phase 3 escalates to the user rather than revising a fourth time.
- **Cycle history:** cycle 1 → NEEDS REVISION (10 fixes; 2 defects reproduced as executed code
  failures). Cycle 2 → NEEDS REVISION (16 fixes; 1 catastrophic billing-semantics defect worth
  2.28x over / 8.6% under). Cycle 3 → NEEDS REVISION (8 fixes; 1 blocking 31.9% under-bill).
- **Ladder:** n/a — the continuation ladder is a Phase 4 mechanism. Phase 3 escalates directly.
- **Assessment:** converging, not thrashing. Blocking findings per cycle: 2 → 1 → 2, and every one was
  new empirical information about the transcript data model that could not have been known from the
  previous cycle's artifacts. All three cycles verified their claims by execution against real data
  rather than by reading. No product code has been written; no wrong invoice has been produced.
- **State:** 8 task files, 27 unique owned paths, disjoint, acyclic. No PASS verdict. Phase 4 not
  started. `billing/`, `deploy/`, `client-package/` untouched.
- **Awaiting:** user decision on how to proceed.

## 2026-09-04 — Phase 3 — goal revision (cycle 3 → cycle 4), USER-AUTHORIZED EXTENSION

- **Authorization:** the feature skill caps Phase 3 at 3 cycles and the budget was exhausted. The user
  was escalated to with four options and chose to authorize a fourth cycle. This entry records that
  the cap was exceeded deliberately and with consent, not by the orchestrator overrunning its budget.
- **Orchestrator decision recorded (user did not specify):** subagent usage bills to its PARENT
  session's repo, tagged `query_source='subagent'`. Rationale: sidechain files carry the parent's
  `sessionId`, so `attribute.py`'s existing as-of join resolves it with no schema change, and
  `otel_store.py:31` already documents that enum value. Stated to the user as an assumption, open to
  reversal.
- **All 8 cycle-3 fixes applied:**
  - **BLOCKING-1 (subagent capture).** Task 06 now treats `transcript_path` as a HINT identifying the
    project directory and parses every `*.jsonl` in it, including `agent-*.jsonl`. Each file is its own
    per-file state unit. Records tagged `query_source='main'|'subagent'`. Made enforceable by task 00
    building a project DIRECTORY fixture (main + sidechain sharing a `sessionId`) publishing three
    totals (main / sidechain / combined), task 06 criterion 1d asserting the combined total AND that it
    is not the main-only value, criterion 1e on `query_source`, task 03 criterion 6b on distinct
    `dp_key`s, and task 07 criterion 3 adding main-only to its list of negative assertions.
  - **BLOCKING-2 (never-fired SessionEnd).** Task 06 criterion 7d: session C's records exist, C's hook
    never ran, D's `SessionEnd` fires, all of C ships exactly once. Plus a requirement that the sweep is
    not limited to the current session's own files.
  - **Fix 4 (`stop_reason`).** The false "equivalently" claim removed from `goal.md`, `00`, `01`, `06`.
    Highest `apiBlockIndex` (tie-break file order, last wins) is now the sole normative selector, with
    a stated fallback for absent `apiBlockIndex` so a mixed `None`/int comparison cannot raise
    `TypeError` and be swallowed by the always-exit-0 rule. Criterion 1f covers it.
  - **Fix 5.** Task 00's duplicate-pair fixture must carry non-null `stop_reason` on BOTH rows, matching
    the only real `claude-desktop` request observed.
  - **Fix 6.** Stale "Must: keep the two hook copies byte-identical" removed from task 06 Constraints.
  - **Fix 7.** `query_source` added to task 02's frozen schema as a required, enum-validated field, and
    to task 03's persistence requirements. Criteria 6b in both.
  - **Fix 8.** Forward-only first-run disambiguated: record an install timestamp and skip earlier
    records; do NOT mark existing files done, which would lose the triggering session. Criterion 7e.
  - Also: sweep marks examined-but-empty files so a CLI/VS Code machine does not re-parse all history
    every session.
- **Fix 12 REJECTED by the orchestrator, with evidence.** Cycle 3 claimed `configure.py:109` should be
  `:110`. Verified by direct read: line 109 IS "Not collected: your prompts, your code, file contents,
  or file paths." The original citation was correct and was left unchanged. Evaluator findings are
  checked, not applied on trust — this is the second cycle-3 claim to be corrected by verification
  (the first being the under-reported 27.9% figure, which measured at 31.9%).
- **Orchestrator re-validation:** 27 unique owned paths across 8 tasks, all disjoint, every
  `depends_on` resolves, graph acyclic. Criteria counts: 00→7, 01→8, 02→11, 03→10, 04→7, 05→10,
  06→24, 07→7.

## 2026-09-04 — Phase 3 — goal evaluation (cycle 4, user-authorized)

- **Agent:** evaluator (FRESH spawn)
- **Model:** claude-opus-5 (frontier tier, agent-pinned)
- **Routing reason:** re-evaluation after the cycle-3 revision, under user authorization to exceed the
  3-cycle cap. A fresh evaluator again, for the same reason as cycles 2 and 3.
- **Task writes fence:** NONE — evaluation only
- **Expected outputs:** Verdict, Score, Fix Verification (8 rows), Subagent Capture Audit, Independent
  Findings marked BLOCKING/NON-BLOCKING, Acceptance Criteria Validation, Required Fixes, Observations
- **context_chars:** 4874

### Return — Phase 3 cycle 4 (user-authorized extension)

- **Verdict:** NEEDS REVISION · **Score:** 3/5
- **report_chars:** 16960
- **est_tokens:** (4874 + 16960) / 4 = **5459** (estimate — character proxy)
- **Cycle-3 fix verification:** 7 of 8 RESOLVED, 1 PARTIAL (fix 1, subagent capture — criteria correctly
  shaped but encoding the wrong on-disk layout). Fix 8 CONFIRMED IN THE ORCHESTRATOR'S FAVOUR: the
  evaluator independently re-checked and agreed cycle 3's `configure.py:110` claim was wrong; line 109
  is correct as originally cited.
- **New required fixes:** 5, all BLOCKING, all `implementation`. No bypass class.

#### BLOCKING-1, verified by the orchestrator — an orchestrator error, not an evaluator error

Sidechain transcripts are NOT in the project directory. Real layout:

    <project_dir>/<sessionId>/subagents/agent-<agentId>.jsonl

Direct measurement:

    recursive rglob : 9 files
    flat per-dir    : 4 files
    MISSED by flat  : 5   (every sidechain file)
    missed spend    : $13.78 of $45.87 = 30.0%

**Root cause is the orchestrator's, and is worth recording precisely.** When verifying cycle 3's
subagent finding, the orchestrator measured the 31.9% figure using `root.rglob("*.jsonl")` — recursive,
so it found the nested files and the dollar figure was right. But when writing the fix into the task
files, it transcribed "in the same project directory" from the cycle-3 evaluator's prose without
checking the actual paths. The verification was recursive; the specification was flat. The measurement
and the mandate disagreed and nothing caught it, because the orchestrator never re-read its own
enumeration code against the sentence it was writing.

**The compounding failure is worse than the location error.** The orchestrator also specified task 00's
fixture to the same flat layout (`00:62`, criterion 3c), which task 07 inherits. So task 06 criterion 1d
— the regression test authored specifically to catch a subagent under-bill — would have run against a
fixture shaped like the bug and passed green while production missed 30% of spend. A regression test
whose fixture encodes the defect is worse than no test: it converts an open question into false
assurance.

#### Remaining blocking fixes

- **Sweep directory scope unstated.** Every desktop scratch session gets its OWN project directory
  (observed: `C--Users-ZaneChing-AppData-Roaming-Claude-scratch-workspaces-…`). A project-dir-scoped
  sweep therefore never reaches a crashed desktop scratch session, making `goal.md`'s never-fired-
  `SessionEnd` success criterion false in production for the dominant real desktop shape — while
  criterion 7d passes in a single-directory fixture.
- **In-flight cumulative groups.** Whole-directory parsing means the hook parses files belonging to
  live sessions it cannot know are complete. A group currently holding only `apiBlockIndex=0,
  output=5` ships at 5; per-file state advances; the terminal `output=209` is then behind the
  watermark, and task 01 criterion 5b's first-writer-wins pins the partial value permanently. Bounded
  (~6 s streaming window, observed `21:19:53.999` → `21:20:00.187`) but silent and uncorrectable
  without a manual DELETE. Criterion 6 would pass while this bug is present.

#### Pattern assessment — the strategic finding

Four cycles, four previously-unknown facts about the transcript data model, each changing the billed
amount: (1) schema/dp_key mechanics, (2) rows are cumulative streaming snapshots, (3) subagent usage
lives in separate files, (4) those files are nested one level deeper than assumed. The evaluator named
the underlying assumption directly: *"that the on-disk layout is stable across Claude Code versions —
this goal has now been bitten by a layout fact four cycles running."* Observed layout is version
`2.1.259`.

This is no longer a sequence of fixable oversights. It is a property of the chosen architecture: the
design depends on undocumented internal on-disk structure, and there is no contract preventing it from
changing again. Escalated to the user as an architectural question rather than a fifth fix round.

- **State:** 8 task files, 27 unique owned paths, disjoint, acyclic. No PASS verdict after 4 cycles.
  Phase 4 not started. `billing/`, `deploy/`, `client-package/` untouched.

## 2026-09-04 — Phase 3 — goal revision (cycle 4 → cycle 5), USER-AUTHORIZED

- **Authorization:** second user-authorized extension past the skill's 3-cycle cap.
- **Approach:** the orchestrator applied the STRUCTURAL fix it recommended at escalation, not the
  minimal path correction cycle 4 asked for. Cycle 4's fixes 1-3 would have corrected the layout;
  the change made instead removes the dependency on layout altogether.

### The five cycle-4 fixes, as applied

1. **Location + enumeration contract (structural).** Task 06 no longer derives a directory from
   `transcript_path` and globs inside it. It **enumerates `~/.claude/projects/**/*.jsonl` recursively
   from the projects root** and keys per-file state by absolute path; `transcript_path` is demoted to a
   priority hint. Rationale written into the task: this is correct for the observed nested layout, for
   a flat layout, and for any future re-nesting. The real path
   (`<project_dir>/<sessionId>/subagents/agent-<agentId>.jsonl`) is recorded in `goal.md`, `00`, `06`,
   `07`, but no task depends on it being right.
   Additionally: sidechain rows are now identified by the **`isSidechain` flag on the row**, not by
   filename, so a filename convention change cannot silently reclassify subagent spend as main spend.
2. **Fixture rebuilt to the real nested tree.** Task 00 now builds a projects TREE: two project
   directories, a main transcript, and a sidechain at `<session_id>/subagents/agent-<agentId>.jsonl`.
   Criterion 3c asserts the sidechain's exact relative path, not merely its existence.
3. **Anti-fixture criterion added** (task 06, 1d-bis). The test computes BOTH a flat-glob total and the
   hook's own enumeration total over the same fixture tree, and asserts flat == published main-only
   while hook == published combined, and that they differ. This is the one construction a
   consistently-wrong pair cannot satisfy: it fails if the fixture is flat, if the hook globs flatly,
   or if either is later "simplified" back. Task 00 criterion 3d independently asserts the fixture's
   flat glob finds strictly fewer files than a recursive walk.
4. **Sweep scope pinned cross-directory.** Task 06 requires the sweep to span ALL project directories,
   with the reason recorded: every desktop scratch session gets its own project directory, so a
   project-scoped sweep can never reach a crashed desktop session. Criterion 7d now places session C in
   a DIFFERENT project directory from session D.
5. **In-flight completeness rule added.** A file's trailing request group ships only when the file is
   the one named by `transcript_path` on its own session's `SessionEnd`, or when the file has been idle
   past a stated threshold. Non-trailing groups are complete by construction. Criterion 7f asserts a
   partial trailing group is withheld and later ships once at its terminal value.

### Assumption (c) promoted into goal.md

The pattern itself is now written into the goal as a named load-bearing assumption: *the on-disk
transcript layout is stable across Claude Code versions* — identified as the weakest assumption in the
plan, violated in five consecutive cycles. Two structural mitigations are recorded as non-optional
(recursive enumeration, flag-based classification), and a third is named as deferred residual risk:
extending `billing/reconcile.py`'s coverage funnel to check desktop capture against the authoritative
Anthropic Analytics totals. That is the only mitigation that would catch a layout change of this class
regardless of what the layout does — recorded as a follow-up goal, explicitly not scope here.

- **Orchestrator re-validation:** 27 unique owned paths across 8 tasks, disjoint, resolving, acyclic.
  Criteria: 00→8, 01→8, 02→11, 03→10, 04→7, 05→10, 06→26, 07→7.
- **Residual-claim sweep:** `grep` for flat-layout phrasing across goal and task files returns zero.

## 2026-09-04 — Phase 3 — goal evaluation (cycle 5, user-authorized)

- **Agent:** evaluator (FRESH spawn)
- **Model:** claude-opus-5 (frontier tier, agent-pinned)
- **Routing reason:** re-evaluation after the cycle-4 revision, under the user's second authorization to
  exceed the cap. Fresh spawn again, for the same reason as cycles 2-4.
- **Task writes fence:** NONE — evaluation only
- **Expected outputs:** Verdict, Score, Fix Verification (5 rows), Layout-Independence Audit,
  Independent Findings marked BLOCKING/NON-BLOCKING, Acceptance Criteria Validation, Required Fixes,
  Observations
- **context_chars:** 5240

### Return — Phase 3 cycle 5 (second user-authorized extension)

- **Verdict:** NEEDS REVISION · **Score:** 4/5 — the highest of the five cycles, and the evaluator's own
  characterisation: "the strongest version of this plan yet".
- **report_chars:** 17280
- **est_tokens:** (5240 + 17280) / 4 = **5630** (estimate — character proxy)
- **Cycle-4 fix verification:** 4 of 5 RESOLVED, 1 PARTIAL (fix 5, in-flight rule — the rule was sound
  but its criterion could not reach the failure it existed to catch).
- **New required fixes:** 2, both tagged `criteria-defect`, both in task 06's failure handling, both
  authored by the orchestrator in the cycle-4 revision. **No new external data-model fact.**

#### THE CONVERGENCE SIGNAL — no fifth fact exists

Cycles 1-4 were each invalidated by a previously-unknown fact about the transcript data model. Cycle 5
was explicitly tasked with hunting for a fifth and **found none**, documenting eight eliminated
hypotheses against real data rather than asserting absence:

| Hypothesis | Result |
|---|---|
| `usage.iterations` hides under-reported sub-calls | eliminated — 0 rows where sum ≠ top-level |
| `server_tool_use` billable, no payload field | 0 across 715 rows — real gap, but no impact today |
| `service_tier` varies (batch/priority pricing) | eliminated — `{'standard': 714, None: 1}` |
| Resumed sessions copy history → double-bill | eliminated — 0 requestIds in >1 file or >1 session |
| `requestId` spans multiple `message.id`s | eliminated — 0 occurrences |
| requestId in both main and sidechain → key collision | eliminated — 0 across 314 groups |
| Usage on non-`assistant` rows | eliminated — `{'assistant': 713}` |
| `<synthetic>`/error rows carry billable usage | 1 row, all counters zero, rejected per-record |

It also independently re-derived the four KNOWN facts rather than trusting the plan: cumulative
snapshots confirmed (output monotonic by `apiBlockIndex`; sum-vs-terminal ratio 2.125x; first-block
loses 40% of output) and the subagent share confirmed at 34.6% ($28.53 of $82.47 through the real
`RatingService`) against goal.md's 30.0% at an earlier snapshot. Both hold; the share grew because this
session kept spawning evaluators.

**This is the signal that was absent from cycles 1-4.** The plan is no longer being invalidated by
unknown properties of the data; it is being refined on its own internal consistency.

#### The two blockers — both orchestrator drafting errors, both fixed

1. **Transport failure consumed the drop bound.** Task 06 read "reserve the retry bound for transport
   failures and envelope 400s" — but `goal.md`'s success criterion scopes the anti-stall bound to a
   batch the receiver *permanently rejects*. The orchestrator broadened it in the cycle-4 revision, and
   the broadening created a data-loss path: a developer off-VPN or on a plane would have every
   `SessionEnd` fail at transport, exhaust the bound, and have the batch **dropped with the watermark
   advanced past it**. Forward-only, no backfill — unrecoverable. Offline is routine for a laptop fleet.
   FIXED: the bound now applies only to permanent rejection; transport failures retry indefinitely with
   backoff, never advance state, never drop. New criterion 7h.
2. **Examined-at-mtime skip contradicted the idle-threshold ship rule.** Both were written into the
   same cycle-4 revision and cannot both hold: the idle branch ships a trailing group precisely when
   mtime has NOT changed, while an mtime-keyed examined-mark skips exactly those files. A file swept
   mid-flight, whose session then crashed, would be marked examined at mtime M and never revisited —
   the withheld group lost permanently and silently. Criterion 7f could not catch it, because 7f
   appends a row, which changes mtime and bypasses the skip. FIXED: a file whose trailing group was
   withheld is never marked examined, and the mark is bypassed once idle. New criterion 7g, which
   advances the clock WITHOUT touching the file — the case 7f structurally cannot reach.

#### Non-blocking items also applied (cheap, risk-reducing)

- **`CLAUDE_CONFIG_DIR` honored**, plus a local record when a full-root sweep yields zero files. This
  was the last hard-coded layout dependency; on a machine setting that variable the hook would have
  found nothing and billed zero, silently. Converts the failure mode to visible — the cheapest
  available safeguard given that every defect across five cycles failed silently.
- **`query_source`'s exclusion from the transcript key documented** in task 01 with its measured
  justification (0 collisions in 314 groups), so the asymmetry with OTLP `dp_key` is a recorded
  decision rather than something a future reader must reconstruct.
- **`server_tool_use` and the 1h/5m cache-write split added to Out of Scope** with measurements, as
  decisions rather than omissions.

#### Orchestrator assessment

Not carried to a sixth evaluation cycle. Basis: no external fact remains outstanding (documented
negative result across 8 hypotheses); both cycle-5 blockers were narrow defects in orchestrator-authored
text, precisely diagnosed with exact remedies, now applied along with three risk-reducing extras; and
Phase 4 gates every implementation task through its own evaluator, so the plan is not the last line of
defence. Returned to the user with a recommendation rather than a sixth spawn.

- **State:** 8 task files, 27 unique owned paths, disjoint, resolving, acyclic. Criteria: 00→8, 01→8,
  02→11, 03→10, 04→7, 05→10, 06→28, 07→7. Phase 4 not started. `billing/`, `deploy/`,
  `client-package/`, `fabric/` all untouched.

---

# PHASE 4 — Task execution

## 2026-09-04 — Phase 4 entered by USER OVERRIDE of the Phase 3 gate

- The feature skill states: "INVARIANT: The ONLY exit to Phase 4 is a PASS verdict from the evaluator
  subagent." **No PASS verdict was obtained.** Five goal-evaluation cycles ran (3 by budget, 2 by user
  authorization) and all returned NEEDS REVISION.
- The user, having been given the cycle-5 result and a recommendation, directed that Phase 4 begin.
  Recorded here as a deliberate, informed override — not as a satisfied gate, and not as an
  orchestrator decision. The ledger must not imply a PASS that does not exist.
- Mitigating context, stated for the record rather than as justification: cycle 5 scored 4/5, found no
  outstanding external data-model fact after an eight-hypothesis documented hunt, and its two blocking
  findings were orchestrator drafting defects that have since been fixed with criteria that reach the
  cases the previous criteria could not. Every Phase 4 task remains individually evaluator-gated, so
  the plan is the first line of defence, not the last.

### Execution order (dependency-resolved)

    00 → 01 → 02 → 03 → 04 → 05 → 06 → 07

04 depends only on 00+01 and 03 depends on 00+01+02, so 03 and 04 could run concurrently; the feature
skill specifies sequential task execution, so they are run in order.

## 2026-09-04 — Phase 4 — environment preflight

- **Agent:** terminal
- **Model:** claude-sonnet-5 (light tier, agent-pinned)
- **Routing reason:** `pytest` is not installed in this environment; `.claude/ORCHESTRATION.md` records
  `python -m pip install pytest` as the one-time setup step, and tasks 00 and 07 both flag it. Run via
  `terminal` rather than inline so the install output does not land in the orchestrator's context, and
  so the orchestrator does not execute commands itself.
- **Task writes fence:** none — environment only, no repository file touched
- **Expected outputs:** installed version string and exit code only

- **Return:** exit 0, `pytest 9.1.1` installed (with transitive dev deps colorama, iniconfig,
  packaging, pluggy, pygments). None is imported by `billing/`, `deploy/`, or `client-package/`, so the
  stdlib-only RUNTIME constraint is unaffected — the dependency budget was always "pytest under
  tests/", and that is what was installed.

## 2026-09-04 — Phase 4 — Task 00 (test scaffold + pre-change baseline), cycle 1

- **Agent:** test-writer
- **Model:** claude-sonnet-5 (light tier, agent-pinned; effort medium)
- **Routing reason:** first task in dependency order and the goal's contract-zero task. It must run
  BEFORE any production file changes, because the golden `bill.py` baseline it captures is only
  honest while `bill.py` is unmodified, and because its legacy-schema fixture must freeze the CURRENT
  `otel_store.py` SCHEMA before task 01 alters it. `owner: test-writer` per the ownership contract.
- **Task writes fence:** `tests/conftest.py`, `tests/golden/bill_otlp_baseline.txt`,
  `tests/golden/README.md` — three paths, nothing else. No production file may be touched.
- **Expected outputs:** completion report naming each file created, the three published fixture totals
  (main / sidechain / combined), confirmation the baseline capture is byte-reproducible across two
  runs, and the rung-1 command output.
- **context_chars:** 7134
