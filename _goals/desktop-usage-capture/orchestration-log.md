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

### Tooling change — pip to uv (user-directed, mid-Phase-4)

The user directed that the project use `uv` rather than `pip`. Applied as a documentation/tooling
change only; no code, no runtime behavior, and no relaxation of the stdlib-only constraint (`uv` is an
installer, never an import).

Four INSTALL COMMANDS converted: `.claude/ORCHESTRATION.md:746` (Setup block),
`00-test-scaffold.md`, `07-integration.md`, `goal.md`. Each now reads `uv pip install pytest`, with
`uv run --with pytest python -m pytest` documented as the zero-install alternative — a good fit for a
repo whose identity is "installs nothing".

Six references deliberately RETAINED as-is, because they are statements of fact about the project
having no dependencies at all, not tooling choices — and each remains true under `uv`:
`Dockerfile:2`, `README.md:8`, `deploy/README.md:210`, `.claude/ORCHESTRATION.md:7`,
`.claude/skills/align-docs/SKILL.md:60`, `.claude/agents/evaluator.md:66`.

`.claude/ORCHESTRATION.md` is manifest-tracked; it will show as user-modified on the next `/setup`
upgrade and be diff-confirmed before any overwrite. Expected, not a defect.

**`uv` is NOT currently installed on this machine** (`uv: command not found`). This does not block
Phase 4: `pytest 9.1.1` is already present in the active interpreter
(`C:\Users\ZaneChing\AppData\Local\Programs\Python\Python312`) from the earlier preflight, so every
targeted-test rung runs today. The converted commands are forward-looking.

## 2026-09-04 — Phase 4 — Task 00 (test scaffold + pre-change baseline), cycle 1 (RELAUNCH)

The first spawn of this task was interrupted by the user before it ran; no files were created. This is
a clean relaunch with an identical fence, plus the uv tooling note.

- **Agent:** test-writer · **Model:** claude-sonnet-5 (light tier, agent-pinned; effort medium)
- **Routing reason:** unchanged — contract-zero task, must run before any production file changes so the
  golden `bill.py` baseline is captured honestly and the legacy `SCHEMA` is frozen pre-task-01.
- **Task writes fence:** `tests/conftest.py`, `tests/golden/bill_otlp_baseline.txt`,
  `tests/golden/README.md`
- **Expected outputs:** files created, published fixture totals (main/sidechain/combined), proof the
  baseline capture is byte-reproducible across two runs, rung-1 command output
- **context_chars:** 7402

### Return — Task 00 cycle 1 (partial), and an ORCHESTRATOR PLAN DEFECT it exposed

- **report_chars:** 5980 · **est_tokens:** (7402 + 5980) / 4 = **3346** (estimate)
- **Silent-success check (orchestrator-executed, not taken on trust):**
  - Write fence respected — `git status` shows `?? tests/` only; nothing under `billing/`, `deploy/`,
    `client-package/`, or `fabric/` modified.
  - `LEGACY_SCHEMA` is a frozen literal, NOT imported. Verified by parsing the literal out of
    `conftest.py`: `usage_source` False, `entrypoint` False, `cost_source` False, 8 `CREATE TABLE`
    statements — correctly frozen to the pre-task-01 shape.
  - Nested tree materialized and walked for real: 3 files across 2 project directories, sidechain at
    `project-acme-web/sess-desktop-a/subagents/agent-*.jsonl` — the REAL layout, not flat.
  - Anti-fixture precondition holds: flat glob of project dir = 1 file, recursive = 2, they differ.
    Task 06's 1d-bis is therefore satisfiable against this fixture.
  - Golden baseline present (2000 B) carrying `basis: ACTUAL cost from claude_code.cost.usage
    x1.50 markup`; `python -m pytest tests/ -q` collects with zero errors.
  - Published totals arithmetic: main 53,522 + sidechain 2,053 = combined 55,575. Consistent, and
    combined > main-only as required.

**Plan defect found by the worker, confirmed and owned by the orchestrator.** Task 00's acceptance
criteria 2, 3, 3b, 3c and 3d each specify "verification: unit test", but the task's `writes:` set
contained no `test_*.py` path — so the criteria were unsatisfiable inside the fence the same task file
imposed. The worker correctly refused to breach the fence and reported it instead of silently writing
outside it or faking the verification; it validated the fixtures with a throwaway script and said so
plainly. That is the behavior the fence exists to produce.

Resolution: `tests/test_conftest.py` added to task 00's `writes:`. Disjointness re-verified — 28
owned paths across 8 tasks, still zero overlap. The fixture invariants need COMMITTED tests rather
than a scratch script precisely because task 06's anti-fixture criterion depends on this fixture's
shape; an untested fixture can drift and silently disarm that regression test.

Task 00 continued (SendMessage to the same agent, preserving its fixture context rather than paying
for a cold respawn) to write `tests/test_conftest.py`, plus a cosmetic fix to a doubled `agent-agent-`
prefix in the sidechain fixture filename.

### Return — Task 00 cycle 1 (complete)

- **report_chars:** 3410 · **est_tokens (continuation):** ~1400 (estimate)
- **Silent-success check, orchestrator-executed:**
  - `python -m pytest tests/ -q` run BY THE ORCHESTRATOR, not taken from the report: **15 passed**.
  - Fence exact: `tests/conftest.py`, `tests/test_conftest.py`, `tests/golden/bill_otlp_baseline.txt`,
    `tests/golden/README.md`. `git status --porcelain -- billing deploy client-package fabric` shows
    no modification. `__pycache__/` already covered by `.gitignore:16`.
  - Doubled-prefix fixture filename fixed: now `agent-11111111.jsonl`. Classification remains by the
    `isSidechain` row flag, not filename, as required.
  - AC3b's discriminating assertion is present and real: terminal=209, sum=214, first=5, asserted
    mutually distinct — so a terminal-block selector, a naive sum, and a first-writer-wins collapse
    each produce a different number and cannot be confused.
- **Outcome:** work verified present and green. Proceeding to the mandatory Phase 4 evaluation —
  a task is complete only on an evaluator PASS, never on a worker's self-report.

## 2026-09-04 — Phase 4 — Task 00 evaluation, cycle 1

- **Agent:** evaluator · **Model:** claude-opus-5 (frontier tier, agent-pinned; effort high)
- **Routing reason:** mandatory per-task evaluation. Task 00 is contract-zero — its golden baseline is
  the ONLY record of pre-change `bill.py` behavior and cannot be recaptured once task 05 lands, and its
  frozen `LEGACY_SCHEMA` is the only pre-task-01 schema record. A defect here is unrecoverable later,
  so this evaluation carries more weight than its small diff suggests.
- **Task writes fence:** NONE — evaluation only
- **Expected outputs:** verdict, per-criterion validation, independent findings, required fixes
- **context_chars:** 6120

### Return — Task 00 evaluation cycle 1: NEEDS FIXES (3/5)

- **report_chars:** 11480 · **est_tokens:** (6120 + 11480) / 4 = **4400** (estimate)
- Failure class: `implementation`. No bypass class — no escalation-at-detection.
- Evaluator confirmed by hash that `LEGACY_SCHEMA` is verbatim (SHA256 `6a075717…`, 4313 B, both
  literals AST-extracted) and that the golden baseline re-captures byte-identically (SHA256
  `9bc05192…`, 2000 B). The DATA was correct; the PROOF was not.

**Blocker 1 — the published-totals test could not fail.** `test_published_totals_are_internally_consistent`
compared the fixture dict against the constants used to build it (`X == X`) and never opened a
transcript file. The evaluator proved it by mutation, and the ORCHESTRATOR independently reproduced it:
setting `EXPECTED_MAIN_ONLY_TOTALS["output_tokens"] = 999999` — a value with no relation to the
fixture — still returned **15 passed**. Severity is not academic: those published totals are the single
source of truth tasks 02/06/07 assert against (task 06 criteria 1b, 1d, 1d-bis). Had they drifted to
the naive sum, task 06 would demand a 2.28x over-bill while its own "NOT the sum" clause contradicted
it, green throughout.

**Blocker 2 — CRLF corruption of the golden baseline.** `core.autocrlf=true` and
`git check-attr text -- tests/golden/bill_otlp_baseline.txt` = `unspecified`; the 2000-byte LF file
checks out as 2045 bytes CRLF, breaking task 05's AC1 byte diff — the regression gate protecting the
existing OTLP fleet — for a reason unrelated to billing. Third appearance of Windows line-ending
breakage in this goal, after the two hook copies in Phase 3 cycle 5.

**Cross-task routing (orchestrator, since the real fix is outside task 00's fence):**
- Task 06 gains a requirement + criterion to pin `tests/golden/** -text` in `.gitattributes`.
- Task 05's AC1 now REQUIRES the golden comparison to normalize line endings independently.
- Both are required; either alone leaves a sharp edge.

**Major 3** — the README's documented CLI reproduction command exits 1 with `UnicodeEncodeError` on
`⚠` under cp1252, writing 1712 truncated bytes instead of 2000.

## 2026-09-04 — Phase 4 — Task 00 fix cycle 1

- **Agent:** test-writer (continued — same agent, retains fixture context) · **Model:** claude-sonnet-5
- **Model rotation:** none. Rotation begins at fix cycle 2; cycle 1 stays on the light tier.
- **Fence:** unchanged four paths. `.gitattributes` explicitly OFF-limits. Baseline regeneration
  explicitly forbidden — it is hash-verified correct and regenerating risks changing it.

### Return — Task 00 fix cycle 1

- **Orchestrator verification, executed not trusted:**
  - **The mutation now goes RED.** Identical mutation to the one that previously yielded 15 passed now
    yields `2 failed, 19 passed` — `test_recomputed_main_only_totals_match_published` and
    `test_recomputed_combined_totals_match_published_and_exceed_main_only`. The test has teeth.
  - Full suite: **21 passed** (was 15; +3 recompute tests, +4 previously-unpinned fixture tests).
  - Golden baseline byte-unchanged: SHA256 `9bc05192…`, 2000 B, 0 CRLF.
  - `.gitattributes` not touched by the worker (`M ` is the kit install's pre-existing staged change,
    working tree clean).
- Proceeding to mandatory re-evaluation. A task is complete only on an evaluator PASS; fixes without
  re-verification are forbidden.

### Return — Task 00 evaluation cycle 2: **PASS (4/5)**

- **report_chars:** 9860 · **est_tokens:** (5240 + 9860) / 4 = **3775** (estimate)
- **Verdict: PASS.** Task 00 is the first task in this goal to clear its gate.

**How the PASS was earned — 15 mutations, not a re-read.** The evaluator re-ran both of its cycle-0
mutations (now RED, previously green) and wrote SEVEN more aimed specifically at the new recompute
code, because the orchestrator asked whether the new tests could still be circular through a longer
path. The two that answer that directly:

| Mutation | Target | Result |
|---|---|---|
| m10 | `_terminal_row` comparison inverted (`>=` → `<=`) | **3 failed** |
| m11 | `_recompute_totals_from_rows` degenerated to a per-row sum | **2 failed** |

Corrupting either helper turns the suite red, so the constants are a genuinely independent second
source: the helper derives from the file's bytes, the constants are declared. The recompute path is
NOT self-fulfilling. m8 (a coordinated fixture+constant edit of the output value) was also caught, by
the hard literal `== MULTI_BLOCK_OUTPUT_TERMINAL == 209`.

**Independently re-verified by the evaluator:** `LEGACY_SCHEMA` still SHA256 `6a075717…` byte-identical
to live `SCHEMA` (4313 B) and still a plain literal; golden baseline still SHA256 `9bc05192…` / 2000 B
/ 0 CRLF and byte-reproducible; write fence exactly four paths; `.gitattributes` byte-unchanged with no
`tests/golden` rule, correctly left to task 06.

It also tested the REVISED README rather than trusting it: the Python snippet reproduces the file
byte-exactly, and the CLI caveat is accurate in both directions — under `PYTHONUTF8=1` the command now
exits 0, but a bare shell redirect still yields 2045 bytes with 45 CRLF, exactly the second condition
the README warns about. The README's claim that both conditions must hold TOGETHER is correct as
written.

**Two minor issues, neither blocking:**

1. Only `output` of the four multi-block values is pinned to a literal, so a coordinated fixture+constant
   edit of the other three slips through (m13/m14/m15 each: 21 passed). Failure mode is LOUD, not
   silent — a drift makes task 06's criterion 1b go red at its own literals. That is the exact inverse
   of the cycle-0 defect, where wrong totals stayed green everywhere and would have shipped a 2.28x
   over-bill. Hardening, not a gate.
2. `test_published_totals_combined_strictly_greater_than_main_only` remains tautological, but is now
   redundant rather than load-bearing — the recompute test proves the same claim from fixture bytes.
   Recorded so it is not miscounted as coverage. Deliberately left alone; not worth the churn.

## 2026-09-04 — Phase 4 — Task 00 hardening pass (post-PASS, optional)

- **Agent:** test-writer (continued) · **Model:** claude-sonnet-5
- **Routing reason:** the evaluator supplied the exact four-line change and proved the three mutations
  it closes. This fixture is contract-zero — every downstream task asserts against its published
  totals — so grounding all four values against literals is cheap insurance on the foundation.
  Delegated rather than orchestrator-edited: the orchestrator coordinates and never executes, and that
  separation is not suspended for small diffs.
- **Verification standard:** this is hardening ON A PASSED TASK, not a defect fix, so it does not
  re-open the gate. Proportionate verification is re-running the evaluator's own m13/m14/m15 and
  confirming each goes RED — not a third full evaluation cycle.
- **Fence:** unchanged. Baseline regeneration still forbidden.

### Return — Task 00 hardening pass

- **Orchestrator verification:** m13 reproduced independently (`MULTI_BLOCK_CACHE_CREATION 13984 →
  20000`) → `1 failed, 20 passed`, failing at
  `test_multiblock_group_terminal_is_highest_api_block_index`. `conftest.py` restored byte-identical
  (`diff -q` clean). Suite **21 passed**. Baseline SHA256 `9bc05192…`, 2000 B, 0 CRLF — untouched.
- All four multi-block values are now grounded against both their constant and a hard literal, with an
  in-code comment recording that the duplication with task 06's criterion 1b is deliberate and must not
  be "de-duplicated" into a shared constant.

**TASK 00 CLOSED — evaluator PASS 4/5, hardening applied and independently verified.**

Deliverables: `tests/conftest.py`, `tests/test_conftest.py` (21 tests),
`tests/golden/bill_otlp_baseline.txt` (SHA256 `9bc05192…`, the only record of pre-change `bill.py`
behavior), `tests/golden/README.md`.

## 2026-09-04 — Phase 4 — Task 01 (store schema), cycle 1

- **Agent:** implementer · **Model:** claude-sonnet-5 (light tier, agent-pinned; effort medium)
- **Routing reason:** next in dependency order and the goal's CONTRACT task — tasks 02-07 build against
  the column names, defaults, key composition, and insert signatures frozen here. It is also the first
  task in this goal to modify a production file, and it modifies the one every other module opens.
- **Task writes fence:** `billing/otel/otel_store.py`, `tests/test_otel_store.py`
- **Carried forward into the context package — a defect the task-00 evaluator predicted:** the legacy
  fixture builds an EMPTY database, so AC1's "leaves every existing row's billed value identical"
  clause is VACUOUS unless this task seeds rows itself via raw `sqlite3`. It cannot use
  `seed_otlp_rows`, which takes an `OtelStore` that auto-migrates on open and would destroy the
  pre-migration state under test. Passing this explicitly, because a vacuous AC1 here is exactly the
  failure class that cost task 00 two evaluation cycles.
- **Expected outputs:** files changed, the frozen contract (column names/defaults, key composition,
  insert signatures) stated verbatim for downstream tasks, rung-1 output, rung-2 impacted-set output.
- **context_chars:** 8020

### Return — Task 01 cycle 1

- **report_chars:** 5240 · **est_tokens:** (8020 + 5240) / 4 = **3315** (estimate)
- **Silent-success check, orchestrator-executed:**
  - Fence held: `M billing/otel/otel_store.py` + `tests/` only. No other production file touched.
  - Suite **30 passed** (21 from task 00 + 9 new).
  - Columns confirmed present on BOTH tables by live `PRAGMA table_info`: `token_usage` has
    `usage_source` + `entrypoint`; `cost_usage` has `usage_source` + `cost_source`. Trap 1 cleared.
  - Key behavior verified directly: OTLP and transcript keys do not collide; two records differing only
    in `request_id` produce different keys (AC5); the five token types incl. the `__cost__` sentinel are
    all distinct (AC6).

- **CROSS-CUTTING CHECK the worker could not have known to run — the golden baseline survives.**
  Task 01 altered the schema that `bill.py` reads. Task 00's golden baseline is the regression gate
  protecting the existing OTLP fleet in task 05, and it was captured BEFORE this change. If the new
  columns had perturbed `bill.py`'s output by even one byte, that gate would already be dead and
  nothing would have surfaced it until task 05 failed for an unrelated-looking reason. Re-captured
  against a store built on the NEW schema:

      recaptured sha256 9bc05192e963db53…  2000 B
      committed  sha256 9bc05192e963db53…  2000 B
      IDENTICAL: True

  The gate is intact.

**DEFECT FOUND BY THE ORCHESTRATOR — `request_id=None` reintroduces silent under-billing.**

The worker flagged this against itself and deliberately left it unguarded, reasoning it would be
over-engineering. It is not. Demonstrated:

    transcript_key("s1", None, "input")  ->  f0f6d333e38309398242b832bd1be057
    transcript_key("s1", None, "input")  ->  f0f6d333e38309398242b832bd1be057   (a DIFFERENT request)

`transcript_key` hashes the literal string `"None"`, so every request in a session with a missing
`request_id` collapses to ONE key per token_type and `INSERT OR IGNORE` drops all but the first. That
is the exact silent under-billing failure this goal exists to eliminate, re-entering through a null
path. Task 02's validator rejects records missing `request_id`, so the server path should never pass
None — but "should never" is what the store must not depend on, and a wiring bug in task 03 would
produce a quietly short invoice with no error anywhere. Routed to the evaluator as a named attack
vector rather than fixed unilaterally.

## 2026-09-04 — Phase 4 — Task 01 evaluation, cycle 1

- **Agent:** evaluator · **Model:** claude-opus-5 (frontier tier, agent-pinned; effort high)
- **Routing reason:** mandatory per-task evaluation. Task 01 is the CONTRACT task — its column names,
  key composition, and insert signatures are consumed verbatim by tasks 02-07, and it is the first
  change in this goal that can break the existing OTLP fleet.
- **Task writes fence:** NONE — evaluation only
- **context_chars:** 6890

### Return — Task 01 evaluation cycle 1: NEEDS FIXES (3/5)

- **report_chars:** 13940 · **est_tokens:** (6890 + 13940) / 4 = **5208** (estimate)
- Failure class: `implementation`. No bypass class.
- **What the evaluator PROVED rather than asserted:** a 70-row production-shaped legacy database
  migrated across three opens with a byte-identical snapshot each time (`c2731bba…f326f1ad`) and
  exactly 4/0/0 ALTERs, the counts captured via `set_trace_callback` rather than inferred from the
  absence of an exception; `inspect.getsource(_migrate)` confirmed to contain no `except`, so
  idempotency comes from the PRAGMA guard and not a swallowed error; `dp_key` unchanged across **864**
  input combinations reconstructed from `git show HEAD`; `bill.run()` byte-identical even when replayed
  through a MIGRATED legacy database. 15 mutations, 12 killed, no vacuous test.

**Blocker 1 — `request_id=None`.** The orchestrator had flagged this; the evaluator found the parts
that make it worse and reproduced the damage end to end: three distinct requests billed **100 tokens
instead of 1050 — 90.5% silently lost**. Two facts neither the orchestrator nor the worker had reached:
(a) `transcript_key("s1","None",…)` COLLIDES with `transcript_key("s1",None,…)` — both
`f0f6d333e38309…` — so an `is None` guard would not have fixed it; (b) the MIRROR case, where
`usage_source='otlp'` with a `request_id` set silently ignores it and uses the timestamp key —
orchestrator-confirmed at 1 row / 100 tokens where 2 rows / 300 were due. The decisive argument:
`request_id` is persisted in NO column, so no post-hoc query can ever distinguish "one request" from
"950 tokens dropped", and task 03's own AC4 would PASS while the bug was live.

**Blocker 2 — `cost_source` vocabulary conflict, found by reading four documents against each other,
not by testing code.** `otel_store.py:61` and `tests/test_otel_store.py:292,307` pinned `'estimated'`
while `goal.md:102`, `02-transcript-payload.md:98` and `05-billing-basis.md:8` all say `'rate_card'`.
The column is free-text with no validation, so nothing catches the mismatch at runtime; task 05 derives
the invoice's actual-vs-estimated split from it, and desktop cost would have dropped out of the
estimated bucket silently, on a client invoice. Task 01 is the contract owner — its comment and its
test are what tasks 02/03/05/07 copy.

## 2026-09-04 — Phase 4 — Task 01 fix cycle 1

- **Agent:** implementer (continued) · **Model:** claude-sonnet-5 · **Rotation:** none at cycle 1.

### Return — Task 01 fix cycle 1

- **Orchestrator verification, executed:**
  - Guard fires in all four directions: `None`, `""`, literal `"None"`, and the `otlp`+`request_id`
    mirror — every one raises `ValueError`. The 90.5% loss path is closed.
  - Three distinct transcript requests now bill **3 rows / 600 tokens** (was 1 row / 100).
  - Golden baseline still `9bc05192e963db53…` — byte-identical. Task 05's gate survives fix cycle 1.
  - `receiver.ingest_metrics_payload` drives the real OTLP path unchanged:
    `{'inserted': 1, 'token_inserted': 1, 'duplicate': 0}`.
  - `cost_source` vocabulary now consistent — the only remaining occurrences of "estimated" are in
    explanatory comments that deliberately contrast the two tokens.
  - Suite **41 passed** (was 30; +11 tests). Fence held: `M billing/otel/otel_store.py` + `tests/`.
- The worker chose to RAISE on the `otlp`+`request_id` mirror rather than document-and-ignore, per the
  orchestrator's stated preference that raising is safer. Verified safe: `receiver.py` never passes
  `request_id` on the OTLP path.
- Proceeding to mandatory re-evaluation. Fixes without re-verification are forbidden.

### Return — Task 01 evaluation cycle 2: **PASS (4/5)**

- **report_chars:** 12100 · **est_tokens:** (5480 + 12100) / 4 = **4395** (estimate)
- 21 mutations run (the original 15 re-run + 6 new ones attacking the guard). **18 killed.**
  G5 — guard raising `TypeError` instead of `ValueError` — was KILLED, which proves the new
  `pytest.raises` blocks are narrow enough to catch a wrong exception type. That was the specific
  "passes for the wrong reason" failure mode the orchestrator asked about; it does not occur.
- **Guard audit: zero false rejections across 11 legitimate-id probes**, including the falsy-adjacent
  traps `"0"`, `"false"`, `"-1"`, `"null"`, the all-zero uuid, and `"none"` lowercase (correctly
  accepted — `str(None)` produces exactly `"None"`, so the exact-case check targets the real collision
  source without over-matching a legitimate id).

**RULING on the orchestrator's failure-mode question — raise is correct, not rejection.** The concern
was that a store `ValueError` might surface as an unhandled 500, or break a developer's session,
trading one defect for another. Resolved on evidence:
- **Task 06 cannot be affected at all.** Every call site of both insert methods was enumerated
  repo-wide: `receiver.py:163`, `receiver.py:176`, and test code. The hook never imports `otel_store`;
  it POSTs over HTTP, so a store raise executes server-side in the receiver process and can never reach
  a developer's Claude Code session.
- **Task 03 gets 400, not 500.** Orchestrator-confirmed at `receiver.py:261` and `:274` — both existing
  endpoints catch `(ValueError, KeyError)` and `send_response(400)`.
- In the designed flow the guard is unreachable from client data (task 02's validator rejects a record
  missing `request_id` first), so it fires only on a WIRING bug — where a loud 400 is exactly right,
  and the alternative is a silent short invoice.

**Integration constraint recorded into `03-receiver-endpoint.md`** rather than left for task 03 to
discover: its per-record loop must not let a store `ValueError` escape, or one bad record returns 400
for the whole batch and violates its own AC 3b. Written into the task file with the verified line
numbers, so the implementer meets it as a requirement instead of tripping over it as a bug.

**Contract viability for tasks 02/03/07: sufficient and unambiguous, no remaining gap.** The
`request_id` requirement is now ENFORCED rather than asserted in prose — downstream tasks inherit a
contract that fails loudly on a wiring bug instead of quietly short-billing.

## 2026-09-04 — Phase 4 — Task 01 hardening pass (post-PASS, optional)

- **Agent:** implementer (continued) · **Model:** claude-sonnet-5
- **Routing reason:** one substantive mutation survives — M10, re-keying the OTLP branch to
  `transcript_key(...)`, passes the full 41-test suite. The requirement "`dp_key` for OTLP rows is
  unchanged" is genuinely MET (proved over 864 combinations against `git HEAD`), but NO test in the
  repo pins it, and the golden baseline cannot catch it because re-keying without collision leaves
  `bill.py`'s SUMs identical. That is the task's headline constraint and the thing protecting dedupe
  against already-stored production rows. Plus `.strip()` on `request_id`, closing the whitespace-only
  and inconsistent-padding residuals at zero cost.
- **Verification standard:** hardening on a PASSED task, so it does not re-open the gate — proportionate
  proof is M10 going RED and whitespace rejection, not a third evaluation cycle.

### Return — Task 01 hardening pass

- **Orchestrator verification, executed:**
  - Suite **48 passed** (was 41; +4 tests, +2 parametrize variants).
  - M10 closed: the OTLP `dp_key` is now pinned at the call site for BOTH tables. Re-keying the OTLP
    branch to `transcript_key(...)` turns `test_insert_datapoint_otlp_uses_dp_key` RED. The task's
    headline constraint finally has a regression test, symmetric with the `__cost__` sentinel pin.
  - `.strip()` residuals closed: whitespace-only `"  "` raises; `" None "` raises;
    `"req-1"` then `" req-1 "` → `inserted=True,False`, one row. All three verified directly.
  - Golden baseline still `9bc05192e963db53…` — byte-identical through three consecutive cycles of
    changes to the file `bill.py` reads.
  - Fence held: `M billing/otel/otel_store.py` + `tests/`.

- **Contract wrinkle the worker flagged against itself, orchestrator-confirmed and recorded:**
  `transcript_key` does NOT strip — normalization lives in the insert methods.
  `transcript_key("s"," req-1 ","input") != transcript_key("s","req-1","input")`, while the insert
  methods treat the two as the same row. A downstream caller computing an expected key directly from
  unstripped input would mismatch what the store wrote. Failure mode is a loud test mismatch, not wrong
  data — but it would read as a store bug when it is not, so it is recorded as a requirement in
  `07-integration.md` rather than left to be rediscovered during integration.

**TASK 01 CLOSED — evaluator PASS 4/5, hardening applied and independently verified.**

Deliverables: `billing/otel/otel_store.py` (4 new columns across 2 tables, guarded idempotent
migration, `transcript_key`, enforced `request_id` contract in both directions),
`tests/test_otel_store.py` (20 tests). Frozen contract published to tasks 02-07.

Cumulative suite: 48 tests. `dp_key` unchanged across 864 verified combinations. Golden baseline
intact. Existing OTLP fleet bit-for-bit unaffected.

## 2026-09-04 — Phase 4 — Task 02 (wire payload contract), cycle 1

- **Agent:** implementer · **Model:** claude-sonnet-5 (light tier, agent-pinned; effort medium)
- **Routing reason:** next in dependency order, and the sharpest remaining task. `transcript.py` is
  where both catastrophic arithmetic errors are decided: summing records that share a `request_id`
  over-bills by 2.28x, and mis-keying re-opens the first-writer-wins path that under-bills by 8.6%.
  It is also the wire-contract owner — tasks 03 and 06 must agree with it field-for-field or desktop
  rows land in `unknown` and never invoice.
- **Task writes fence:** `billing/otel/transcript.py`, `tests/test_transcript.py`
- **Orchestrator-added guidance not in the task file:**
  - `RatingService.raw_cost()` is a DIRECT public method. The task file says to match `bill.py:96`'s
    `rates.billed(...)/markup` convention; that phrasing means produce the same VALUE, not copy the
    expression. `billed() == raw_cost() * markup` by definition, so `raw_cost()` yields the identical
    number without a multiply-then-divide float round-trip. AC5 asks for "RatingService's raw
    pre-markup value" — `raw_cost()` is exactly that.
  - `_base()` matches by SUBSTRING (`if key in (model or "")`). `claude-opus-5` matches no key and
    correctly falls through to `DEFAULT_RATE` (5.0, 25.0). Expected, not a bug — the placeholder rate
    card is explicitly Out of Scope.
  - Carry task 01's contract wrinkle: `transcript_key` does NOT strip; the insert methods do. Do not
    call it directly with unnormalized input.
- **Expected outputs:** the frozen wire schema stated verbatim for tasks 03/06, rung-1 output,
  rung-2 impacted-set output.
- **context_chars:** 9140

### Return — Task 02 cycle 1

- **report_chars:** 7180 · **est_tokens:** (9140 + 7180) / 4 = **4080** (estimate)
- **Silent-success check, orchestrator-executed:**
  - Suite **79 passed** (48 + 31 new). Fence held: `?? billing/otel/transcript.py` + `tests/`.
  - **The 2.28x trap is closed.** Two records sharing `(session_id, request_id)` → 1 accepted,
    1 rejected `duplicate_request_id`; billed output = **5, not 214**. Not summed.
  - `cwd` rejected as `unknown_field:cwd` by the generic fail-closed rule, with no special case —
    the consent guarantee is enforced structurally rather than by a bespoke check.
  - `ts` format agrees with `otel_store._ns_to_iso` exactly (`2026-09-04T15:58:04Z` from a
    millisecond-precision input).

**DEFECT FOUND BY THE ORCHESTRATOR — the rejection channel echoes the content it rejected.**

`validate_batch` returns rejections shaped `{"record": <the entire original record>, "reason": ...}`.
So a record rejected *for carrying a file path* carries that same file path back out:

    reason='unknown_field:cwd'
    record={... 'cwd': 'C:\Users\Zane\AppData\Roaming\Claude\scratch-workspaces\SECRET-CLIENT-NAME'}
    "SECRET-CLIENT-NAME" in json.dumps(rejections) -> True

Task 03's own requirement states the 200 body's reject entries must "identify records by `request_id`
and reason — never by echoing record content", and its 400 log path must contain no request bytes. As
shaped, task 03 must remember to strip the record — and if it forgets, the consent guarantee is
defeated by the very mechanism built to enforce it. The safer contract is for task 02 to never emit the
record at all.

Second-order problem in the same shape: records rejected BEFORE `request_id` is known (`not_a_dict`,
`missing_field:session_id`) have no `request_id` to report — orchestrator-verified, both return
`request_id=None`. A `(request_id, reason)` entry therefore needs a defined fallback, such as the
record's batch index, or task 03 cannot build a safe entry for those cases at all.

Routed to the evaluator as a named finding rather than fixed unilaterally.

- **Two lesser notes carried to the evaluator:** the worker duplicated `otel_store`'s
  `%Y-%m-%dT%H:%M:%SZ` pattern locally instead of importing `_ns_to_iso` (they agree today —
  verified — but it is a second definition of a format `attribute.py`'s lexicographic as-of join
  depends on, so drift would break attribution silently); and it added an unrequested `process_batch()`
  convenience wrapper, which is pure and harmless but is unasked-for contract surface.

## 2026-09-04 — Phase 4 — Task 02 evaluation, cycle 1

- **Agent:** evaluator · **Model:** claude-opus-5 (frontier tier, agent-pinned; effort high)
- **Routing reason:** mandatory per-task evaluation. Task 02 owns the wire contract that tasks 03 and 06
  must match field-for-field, and it is where both catastrophic arithmetic errors are decided.
- **Task writes fence:** NONE — evaluation only
- **context_chars:** 7460

### Return — Task 02 evaluation cycle 1: NEEDS FIXES (3/5)

- **report_chars:** 13620 · **est_tokens:** (7460 + 13620) / 4 = **5270** (estimate)
- Failure class: `implementation`. The evaluator explicitly DECLINED to tag the rejection-echo defect
  `security`, reasoning that `transcript.py` performs no I/O so no leak has occurred, and a security
  tag would halt the continuation ladder for a harm that has not happened. It blocked it as a CONTRACT
  GAP instead. Correct call and correct severity — the bypass classes exist for real breaches, not for
  a shape that could enable one downstream.

**Blocker 1 — the third instance in this goal of correct code with a test that cannot fail, and the
most dangerous.** `map_record` returns `ts` as a top-level SIBLING key; the row dicts carry
`time_unix_nano`, and `insert_datapoint` recomputes the stored `ts` itself via `_ns_to_iso`.
Orchestrator-confirmed: `'ts' in token_row -> False`. So AC9's two tests asserted a value with **no
consumer in the designed flow**, while the value that actually decides the stored timestamp was
asserted nowhere. Four mutations survived all 31 tests; two of them silent:

| Mutation | Consequence |
|---|---|
| `time_unix_nano=0` | row persists at `1970-01-01T00:00:00Z`; the as-of join finds no timeline entry AND the invoice period filter excludes it — **desktop bills zero, silently** |
| `entrypoint=None` | task 05's `entrypoint == 'claude-desktop'` predicate misses the row — silent |
| `request_id=None` | loud (task 01's guard), but it is the most money-critical field in the goal |
| `usage_source='otlp'` | loud, same reasoning |

This also resolved the `ts`-duplication question in an inverted direction: the locally re-defined
strftime pattern is NOT an attribution drift risk, because the store ignores `map_record`'s `ts`
entirely — which is precisely why asserting it proved nothing.

**Blocker 2 — rejection shape.** Confirmed. Beyond the content echo, rejections decided before
`request_id` is known carried NO identifier at all (no batch index), so task 03 could not satisfy its
own stated requirement for those cases without inventing contract.

## 2026-09-04 — Phase 4 — Task 02 fix cycle 1

- **Agent:** implementer (continued) · **Model:** claude-sonnet-5 · **Rotation:** none at cycle 1.

### Return — Task 02 fix cycle 1

- **Orchestrator verification, executed. NOTE:** the orchestrator's first two mutation attempts used
  `sed` patterns that did not match the source, and reported a misleading "42 passed". Re-run against
  the real assignment sites (`transcript.py:400,402,414`), all four mutants die:

      time_unix_nano -> 0        RED  test_time_unix_nano_matches_emitted_ts_via_store_conversion
      entrypoint     -> None     RED  test_entrypoint_present_on_token_rows_and_absent_from_cost_row
      usage_source   -> 'otlp'   RED  test_usage_source_is_transcript_on_every_row
      request_id     -> None     RED  test_request_id_is_carried_onto_every_row

  Recorded because a mutation that silently fails to apply looks exactly like a test with teeth — the
  same class of false confidence these mutation runs exist to detect.
- Rejection entries are now content-free and always identifiable:
  `[{"index":0,"request_id":"r1","reason":"unknown_field:cwd"},{"index":1,"request_id":null,"reason":"not_a_dict"}]`
  — a seeded `SECRET-CLIENT-NAME` in a rejected record's `cwd` does not appear in `json.dumps`.
- Folded fixes verified: padded `request_id` now caught at validate time (`accepted=1`,
  `duplicate_request_id`) rather than silently colliding in the store; `100.7` rejected as
  `invalid_tokens:output_tokens` rather than truncated; `process_batch` removed.
- Suite **90 passed** (48 + 42). Fence held. `transcript.py` restored byte-identical after mutation.
- Proceeding to mandatory re-evaluation.

### Return — Task 02 evaluation cycle 2: NEEDS FIXES (4/5)

- **report_chars:** 14380 · **est_tokens:** (6210 + 14380) / 4 = **5148** (estimate)
- Both original blockers **FIXED** and verified: all four mutants die; the rejection channel is
  content-free with `index` correctly naming the ORIGINAL batch position (`[1,2,4,5]` on a mixed
  batch). All four observations folded in. 28 mutants run, **26 killed**. No regression in the
  rewritten `validate_batch` loop.
- The new `time_unix_nano` test was audited for circularity — the specific trap the orchestrator
  flagged — and is genuinely non-circular: it anchors `mapped["ts"]` to an independent literal derived
  from the input, so the store-formatter assertion transitively pins the nanoseconds.

**The evaluator corrected its OWN tooling mid-audit.** Its automated leak check reported `leak=False`
for the unknown-field-name channel; it noticed `json.dumps` had escaped the backslashes in a Windows
path, making its literal comparison a FALSE NEGATIVE, and reported the finding rather than dropping it.
That is the same failure the orchestrator hit with non-matching `sed` anchors one cycle earlier — a
verification step that silently does nothing looks exactly like a clean result. The evaluator also
hardened its mutation plugin to hard-exit on a non-matching anchor, and found that 3 of its 20 original
anchors had been invalidated by the fix and would have reported false passes.

**NEW BLOCKER — malformed `ts` escapes validation and detonates in `map_record`. Orchestrator-confirmed:**

    ts='garbage'                -> validate_batch rejects? False  -> map_record RAISES
                                   ValueError: Invalid isoformat string: 'garbage'
    ts='2026-13-45T99:99:99Z'   -> validate_batch rejects? False  -> map_record RAISES
                                   ValueError: month must be in 1..12

`_validate_record` checks only truthiness of `ts`. The consequence is not a crash — it is the
batch-poisoning path this goal already fixed once: a `map_record` raise escapes task 03's per-record
loop, reaches `receiver.py:261`/`:274`, and returns **400 for the whole batch**; task 06 retries,
exhausts its bound, and drops a full batch of valid billable records.

**This is partly an ORCHESTRATOR error.** `03-receiver-endpoint.md:53` asserted, in the orchestrator's
own words, that the store guard was "unreachable from client data — `transcript.py` rejects a record
before the store is ever called." That claim was false when written: validation was never exhaustive.
The requirement has been rewritten to (a) record the correction explicitly, (b) require catching
`ValueError` around BOTH `map_record` AND the store insert per-record, and (c) instruct task 03 NOT to
rebuild on an assumption that upstream validation is exhaustive. The blast radius is the problem, not
the status code.

## 2026-09-04 — Phase 4 — Task 02 fix cycle 2 (MODEL ROTATION)

- **Agent:** implementer — **FRESH SPAWN, not a continuation**
- **Model:** `claude-fable-5-1` (light tier, different model LINE), per the fix-cycle rotation table in
  `.claude/skills/setup-models.map.md`. Cycle 1 ran on `claude-sonnet-5`; cycle 2 rotates on the
  principle that a model blind to its own class of mistake rarely fixes it on retry. A `SendMessage`
  continuation would have kept the original model and defeated the rotation entirely — the rotation
  requires a new spawn carrying full context.
- **Task writes fence:** `billing/otel/transcript.py`, `tests/test_transcript.py`
- **context_chars:** 6640

### Return — Task 02 fix cycle 2 (rotated model)

**The model rotation demonstrably earned its cost.** The orchestrator's instruction said to "parse `ts`
inside a `try`". The rotated implementer did not stop there: it probed the baseline first and found TWO
further escape routes nobody had named, then chose a strictly stronger fix.

| Escape route | Why parse-only would have missed it |
|---|---|
| `ts=12345` (non-string) | `.strip()` raises `AttributeError` in `map_record`, not `ValueError` — a `try/except ValueError` around the parse would not catch it |
| `ts="0001-01-01T00:00:00Z"` (pre-epoch) | **parses fine**; `datetime.fromtimestamp` of the negative value raises `OSError [Errno 22]` on Windows, in `_unix_nano_to_ts` AND identically in the store's `_ns_to_iso` at insert time |

It validated via the FULL ROUND TRIP `_unix_nano_to_ts(_ts_to_unix_nano(ts))` rather than the parse
alone, and proved the difference with mutation M5 — a parse-only validator lets the pre-epoch case
through. That is precisely the "blind to its own class of mistake" effect the rotation table exists to
break, and it is the first cycle in this goal where a different model line changed the outcome rather
than merely confirming it.

- **Its mutation discipline also exceeded the orchestrator's.** The mutation script asserted
  `src.count(old) == 1` BEFORE writing, re-read the file to confirm the change was on disk, ran the
  suite, restored, and asserted the SHA-256 matched. M5's first attempt **refused to apply** because the
  anchor occurred twice (docstring + code) — exactly the silent-no-op failure that burned the
  orchestrator two cycles ago, caught automatically instead of by luck.

- **Orchestrator verification, executed:** all four `ts` escape routes rejected `invalid_ts`; date-only
  accepted and maps to midnight UTC; `int` and integral `float` accepted, fractional `float` and `bool`
  rejected; a path-shaped unknown key yields a BARE `unknown_field` with no leak, while a real field
  name keeps its suffix (`unknown_field:cwd`) for task 03's diagnostics. Suite **108 passed** (90 → 108,
  +18). Fence held.

- **Platform-dependency finding to carry forward:** pre-1970 timestamps are rejected as `invalid_ts` on
  Windows (`OSError` from `fromtimestamp`) but would be ACCEPTED on Linux, where negatives are handled.
  Production runs `python:3.12-slim` per the `Dockerfile`, so dev (Windows) and prod (Linux) diverge on
  this input. Unreachable in practice — desktop transcripts carry current timestamps — but recorded so
  it is not a surprise, and flagged to the evaluator for a ruling.

## 2026-09-04 — Phase 4 — Task 02 evaluation, cycle 3

- **Agent:** evaluator (continued — same agent, holds the 28-mutant corpus and its hardened plugin)
- **Model:** claude-opus-5 (frontier tier)
- **Routing reason:** mandatory re-evaluation after fix cycle 2.
- **context_chars:** 5980

### Return — Task 02 evaluation cycle 3: NEEDS FIXES (4/5)

- **report_chars:** 13100 · **est_tokens:** (5980 + 13100) / 4 = **4770** (estimate)
- Blocker FIXED and the two unprompted escape routes independently confirmed. 35 mutants re-cut and
  re-run, **34 killed**; the sole survivor (`TS_HALF_SECOND_OFF`) is correct to survive.
- **The evaluator validated the round-trip design as better than what it had itself specified**, and
  found a reason neither the orchestrator nor the implementer had stated: the store's `_ns_to_iso`
  catches only `(TypeError, ValueError)`, so an `OSError` there would ESCAPE `insert_datapoint` rather
  than fall back to `_now()`. Because `_validate_ts` runs the identical `fromtimestamp` path on the
  identical nanos, anything validation accepts the store can format. Structural closure, not case-by-case.
- **Over-rejection audit: clean.** 20 timestamp forms probed — nanosecond fractions, `+05:30` /
  `-08:00` offsets (correctly converted), naive, whitespace-padded, 2038 boundary, leap day, year 2999
  — all accepted. No silent-loss path in the opposite direction.

**BLOCKER — the validator's accept/reject boundary is set by the host C library, and the suite asserts
that host-specific outcome as universal. Orchestrator-confirmed WITHOUT leaving Windows:**

    1970-01-01T00:00:00Z  -> ACCEPTED
    1969-12-31T23:59:59Z  -> ACCEPTED      <-- pre-1970, yet accepted
    1969-12-01T00:00:00Z  -> rejected
    0001-01-01T00:00:00Z  -> rejected

`transcript.py:279-280` states "Windows raises OSError for pre-1970 values". That is **false** — the
real cutoff sits inside December 1969, wherever the platform's `fromtimestamp` gives up, and it is
documented nowhere. A contract module carrying a factually wrong docstring is its own defect: future
readers trust it.

`tests/test_transcript.py:257` then asserts the pre-epoch case rejects, unconditionally, while the
code's own docstring calls the behavior platform-specific. One of the two must be wrong, and that
contradiction is verifiable locally.

The evaluator marked the Linux half ⚠️ **Unverified** — it had no Linux host and declined to assert
what it could not test, resting the blocker on the locally-provable contradiction instead. Correct
discipline.

**Direction of the divergence is the unsafe one.** Tests run on the STRICTER platform (Windows);
`Dockerfile` ships `python:3.12-slim`, so billing runs on the more PERMISSIVE one. A pre-epoch record
accepted there stores a year-0001 `ts`, which sorts below every `session_repo_timeline` entry in
`attribute.py`'s lexicographic as-of join and falls outside every invoice period — accepted, never
invoiced, no error anywhere.

The evaluator's closing argument is the one that decides it: *"unreachable in practice" is the argument
that was wrong twice already in this goal* — the second-granularity `dp_key` collision and the `cwd`
echo were both judged unreachable before they were closed.

## 2026-09-04 — Phase 4 — Task 02 fix cycle 3 (MODEL ROTATION → FRONTIER)

- **Agent:** implementer — FRESH SPAWN · **Model:** `claude-opus-5` (frontier tier)
- **Routing reason:** third and final fix cycle for this task. Per the rotation table, cycle 3 escalates
  to the frontier tier. If this cycle does not clear the gate, the continuation ladder engages
  (rung 5 arbitration → rung 4 diagnosis → rung 6 decomposition) before any human escalation.
- **Scope:** deliberately narrow — a two-line epoch floor, a false docstring corrected, and a
  platform-independent test boundary. Everything else in this file is verified correct and is
  explicitly off-limits.
- **context_chars:** 5320

### Return — Task 02 fix cycle 3 (frontier tier)

- **Orchestrator verification, executed:**
  - `EPOCH_FLOOR_NANO = 0` present. Boundary now explicit and platform-independent:
    `1970-01-01T00:00:00Z` ACCEPTED (the epoch itself is legal), `1969-12-31T23:59:59Z` **rejected**
    — it was ACCEPTED before this fix, which is precisely the undefined-boundary case.
    Date-only, 2038, and 2999 unchanged, so the over-rejection surface is untouched.
  - The false docstring sentence is gone; `grep` for "Windows raises OSError" / "pre-1970" returns nothing.
  - The floor is genuinely load-bearing: removing the two lines (anchor asserted unique before writing)
    turns `test_epoch_floor_boundary_is_platform_independent[1969-12-31T23:59:59Z-False]` RED. Restored
    byte-identical.
  - Suite **111 passed** (108 → 111). Fence held.

**The implementer reported a surviving mutant and argued it SHOULD survive, rather than faking a kill.**
`TS_ONLY_VALUEERROR` (narrowing the catch to `except ValueError`) now passes all 63 tests. Its reasoning,
which the orchestrator finds sound and is routing to the evaluator for a ruling: with the floor
intercepting every pre-epoch value BEFORE the `fromtimestamp` call, the only inputs still raising
`OSError` from the round trip are far-future extremes (`9999-12-31T23:59:59Z`), which raise on Windows
and are accepted on `python:3.12-slim`. A test pinning those would be platform-dependent at the UPPER
boundary — the same defect relocated, not removed. It therefore declined both to add such a test and to
weaken the catch so the mutant would look killed. That is the correct call: an unkillable mutant that is
honestly reported beats a green one bought with a platform-dependent assertion.

## 2026-09-04 — Phase 4 — Task 02 evaluation, cycle 4

- **Agent:** evaluator (continued — holds the 35-mutant corpus and its hardened plugin)
- **Model:** claude-opus-5 (frontier tier)
- **Routing reason:** mandatory re-evaluation after fix cycle 3. This was the LAST fix cycle; a further
  NEEDS FIXES verdict engages the continuation ladder (rung 5 arbitration on a different frontier line
  → rung 4 diagnosis → rung 6 decomposition) rather than a fourth cycle.
- **context_chars:** 4880

### Task 02 evaluation cycle 4 — SPAWN STALLED, no verdict returned

- **Outcome:** the evaluator stalled — "no progress for 600s (stream watchdog did not recover)". Its last
  emitted line was *"35 of 38 killed. Now the over-rejection re-check and regression probes."*
- So the mutation corpus DID complete (38 mutants re-cut, 35 killed) and the stall occurred during the
  over-rejection and regression phases. **No verdict was produced.** This entry records that plainly:
  a stalled spawn is not a NEEDS FIXES and is not a PASS, and must not be read later as either.
- **Handling per `.claude/ORCHESTRATION.md` § Subagent Invocation:** a transient failure is retried on
  the SAME subagent type — never substituted for a different agent, and never treated as a verdict.
  Attempt 2 of 3.
- **Resumed rather than respawned**, deliberately: the agent holds the 38-mutant corpus, its hardened
  anchor-checking plugin, and three cycles of accumulated findings. A cold respawn would repeat ~20
  minutes of mutation work already completed and lose the continuity that let it re-cut anchors across
  the fix.
- **Scope narrowed on resume.** The orchestrator has independently verified the two phases the stall
  interrupted — the floor removes only sub-epoch values (2026-01-01, 2038, 2999 all still ACCEPTED,
  so the over-rejection surface is untouched) and the full suite is green at 111 with the fence held.
  The resume therefore asks only for the remaining judgement, not a re-run of settled work.

### Return — Task 02 evaluation cycle 4 (resumed): **PASS (5/5)**

- **report_chars:** 10240 · **est_tokens:** (4880 + 10240) / 4 = **3780** (estimate)
- First 5/5 in this goal. 38 mutants re-cut, **35 killed**; all three survivors ruled correct to survive.
- **Decisive boundary evidence** — the check that proves the undefined boundary is gone:

      1969-12-31T23:59:59Z  floor_intercepts=True | platform: fromtimestamp OK
                                                    (i.e. WOULD be accepted without the floor)

  The value the host C library would have accepted is now intercepted by the constant. Boundary pinned
  at `nano=0` accepted / `nano=-1000000` rejected. `FLOOR_OFF_BY_ONE` and `FLOOR_CONST_NEGATIVE` both die.

**RULING on `TS_ONLY_VALUEERROR`: KEEP the `OverflowError`/`OSError` arms — they are NOT dead code.**
Orchestrator-confirmed independently: `9999-12-31T23:59:59Z` still raises `OSError` inside the round
trip and is caught, yielding `invalid_ts`. Drop those arms and the `OSError` escapes `_validate_ts` →
escapes `validate_batch` → the receiver's `except (ValueError, KeyError)` does NOT match → the whole
batch fails. That is the batch-poisoning class this task exists to close, reintroduced purely to make a
mutant look dead. The trade is asymmetric: cost of keeping is one non-portably-killable mutant; cost of
dropping is an unhandled-exception path on the validation boundary. The implementer's refusal to buy a
green mutant with a platform-dependent assertion was the right call and is recorded as such.

**A survivor the implementer did NOT disclose — `TS_PARSE_ONLY`.** Orchestrator-confirmed: deleting the
`_unix_nano_to_ts(nano)` round-trip call now passes all 63 tests. It DIED in cycle 2, killed by the
pre-epoch case; the floor now intercepts pre-epoch before the round trip is reached, so the formatting
half is no longer proven by any test. Same root cause as `TS_ONLY_VALUEERROR` and covered by the same
correct reasoning — but as the evaluator put it, a self-report that names one survivor of a pair should
name both. Non-blocking: the code is right, only the coverage is absent.

**ACCEPTED KNOWN GAP, recorded so a future maintainer can close it cheaply.** A `TS_CEILING_NANO`
constant mirroring `EPOCH_FLOOR_NANO` would make BOTH `TS_PARSE_ONLY` and `TS_ONLY_VALUEERROR` portably
killable and reduce the `OverflowError`/`OSError` arms to genuine unreachable defense in depth. Not
required: the upper boundary is unreachable from real transcript data, no test asserts anything false
about it, and the code is correct as written. Deliberately not spent as a fourth cycle on a PASSED task.

**THE TOOLING TRAP FIRED A THIRD TIME, and was caught.** The evaluator's first 38-mutant run returned an
empty result line for all 38 — indistinguishable from "all killed" at a glance. Cause: a corrupted
plugin (`SyntaxError: unterminated string literal` from its own in-place edit). It diagnosed and re-ran
from a clean rewrite, and its plugin now hard-exits on `ANCHOR-MISS`, `ANCHOR-AMBIGUOUS`, and `NO-OP`.
Running tally of this exact failure in this goal: the orchestrator's non-matching `sed` anchors, the
evaluator's `json.dumps` backslash-escaping false negative, and now its corrupted plugin. **Every
verification step in this goal that silently did nothing looked exactly like a clean pass.** Each was
caught only because someone checked that the check had run.

**TASK 02 CLOSED — evaluator PASS 5/5.**

Deliverables: `billing/otel/transcript.py` (14-field frozen wire schema, `MAX_BATCH_SIZE=500`,
per-record validation with a content-free `{index, request_id, reason}` rejection channel, round-trip
`ts` validation with an explicit epoch floor, terminal-block-per-request mapping, raw pre-markup
rating), `tests/test_transcript.py` (63 tests). Cumulative suite: **111 tests**.

Tasks 03 and 06 now have a contract they can bind to without guessing — kwarg parity with task 01's
insert signatures verified by live store calls, and the arithmetic verified at every cycle: cumulative
snapshots bill 94 not 308, cost `22.05` un-marked-up.

## 2026-09-04 — Phase 4 — Task 03 (receiver endpoint), cycle 1

- **Agent:** implementer · **Model:** claude-sonnet-5 (light tier, agent-pinned; effort medium)
- **Routing reason:** next in dependency order. Task 03 is the wiring seam — it joins task 02's frozen
  wire contract to task 01's enforced store contract. Both of its sharpest requirements were written
  into the task file DURING earlier tasks' evaluations rather than at planning time: the per-record
  `ValueError` containment (from task 01's guard ruling) and the correction that upstream validation
  must not be assumed exhaustive (from task 02's `invalid_ts` blocker).
- **Task writes fence:** `billing/otel/receiver.py`, `tests/test_receiver.py`
- **Frozen API passed into the context package verbatim** so the worker binds to the real surface:
  `validate_batch` / `map_record` are the ONLY two public entry points (`process_batch` was removed in
  task 02's fix cycle 1), `MAX_BATCH_SIZE=500`, `REJECTION_REASONS` is an 8-tuple, and the rejection
  entry shape is `{index, request_id, reason}` — content-free by construction.
- **context_chars:** 8760

### Return — Task 03 cycle 1

- **report_chars:** 4120 · **est_tokens:** (8760 + 4120) / 4 = **3220** (estimate)
- **Silent-success check, orchestrator-executed:**
  - Suite **125 passed** (111 + 14). Fence held: `M billing/otel/receiver.py` + `tests/`.
  - Happy path: 3 valid records → 3 token rows + 3 cost rows, 300 tokens. Replay → `inserted=0`,
    `duplicate=6`, rows unchanged. Idempotent through the real endpoint function.
  - **AC 3b verified directly — the batch-poisoning path is closed.** A 5-record batch carrying one
    `invalid_ts` and one `invalid_entrypoint` stored **3 rows / 300 tokens** (exactly the good records)
    and returned both rejections with full `{index, request_id, reason}`.
  - Envelope failures raise `ValueError` and do NOT degrade to per-record: non-list and 501-record
    batches both raise.
  - Identity and `query_source` persist correctly, `subagent` included, alongside
    `usage_source='transcript'` and `entrypoint='claude-desktop'`.

**Two contract wrinkles the worker flagged against itself — routed to the evaluator, not fixed
unilaterally:**

1. **It invented a rejection reason, `store_error:<ExceptionClassName>`, that is not in task 02's frozen
   `REJECTION_REASONS` 8-tuple.** Its stated rationale is sound — a caller should be able to distinguish
   "validation rejected this" from "the store's wiring-bug guard rejected this" — but nothing upstream
   froze that string, and task 06/07 may match on reasons. Either it belongs in the frozen vocabulary or
   it needs a stable documented prefix.

2. **Store-error rejections carry `index: None`, breaking the always-defined guarantee** that task 02's
   fix cycle 1 introduced specifically so task 03 could identify every rejection. Orchestrator-verified
   root cause: `validate_batch` returns `accepted` as a filtered list whose members carry NO positional
   field, so an accepted record's ORIGINAL batch index is not recoverable from the record itself. The
   worker chose `None` over a wrong index, which is the honest choice — but it leaves the rejection
   contract mixed-type (`int` from validation, `None` from the store path). `request_id` is always
   present on that path, so identification survives; the inconsistency is in the contract, not the
   diagnosis. Task 03 CAN derive the original index (order is preserved and the rejected indices are
   known), or task 02 could hand it over — the latter is outside task 03's fence.

## 2026-09-04 — Phase 4 — Task 03 evaluation, cycle 1

- **Agent:** evaluator · **Model:** claude-opus-5 (frontier tier, effort high)
- **Routing reason:** mandatory per-task evaluation. Task 03 is the wiring seam between two frozen
  contracts, and its central requirement — per-record containment — has already been got wrong twice in
  this goal's history.
- **Task writes fence:** NONE — evaluation only
- **context_chars:** 7180

### Return — Task 03 evaluation cycle 1: NEEDS FIXES (3/5)

- **report_chars:** 16240 · **est_tokens:** (7180 + 16240) / 4 = **5855** (estimate)
- 17 mutations, 13 killed. Auth, privacy, `commit()` discipline, and existing-endpoint regression all
  verified clean by execution — `commit()` proven by INSTRUMENTATION (a counting wrapper recorded
  exactly 1 call for a 25-record / 125-row batch), auth proven by replacing `_read_body` with a
  booby trap that never fired on an unauthenticated POST.

**BLOCKER — the containment is typed to `ValueError`, and the upstream validator type-checks only 5 of
15 fields. Third appearance of the assumption this task file explicitly forbids.**
Orchestrator-confirmed, all four:

    session_id: ["x"]     -> sqlite3.ProgrammingError   ESCAPES
    model: 123            -> TypeError                  ESCAPES
    repo_raw: 123         -> AttributeError             ESCAPES
    user_email: {"a":1}   -> sqlite3.ProgrammingError   ESCAPES

Each passes `validate_batch` (which checks those fields for truthiness only) and then raises something
that is not a `ValueError`, so it escapes BOTH the per-record loop AND `do_POST`'s
`except (ValueError, KeyError)`. The client receives **no HTTP response at all** — a dropped
connection, not a 400. Task 06 then retries a deterministically-failing batch, exhausts its bound, and
discards every valid billable record behind the bad one. Worse than the 400 the requirement warns of.

**A second-order defect the evaluator found and the orchestrator reproduced — an unacknowledged partial
transaction that commits later, on the next unrelated request:**

    REQ1 [good-A, bad(list session_id)] -> raises, client gets NO RESPONSE
         rows visible to an outside connection: (0 rows, 0 tokens)
    REQ2 [unrelated later record]       -> 200
         rows visible to an outside connection: (2 rows, 150 tokens)   <- good-A committed by REQ2

`store.commit()` is never reached on the escape path, so rows written before the raise sit uncommitted
on the single long-lived connection and are committed as a SIDE EFFECT of a later request. The
receiver's persisted state never matched any response it sent. `transcript_key` dedupe prevents a
double-bill on retry, but the batch is still dropped and the ledger is incoherent.

**Four surviving mutations, one on the central requirement:**

| Mutation | Result |
|---|---|
| M3 — store-side containment removed (`map_record` still wrapped) | **14 passed** — the half reachable from REAL client data has NO test |
| M15 — `request_id` on a store-error rejection set to `None` | **14 passed** — with `index` already `None`, the rejection then carries NO identifier at all |
| M4 — banner drops the endpoint, name left in a comment | **14 passed** — AC 8's test asserts on `inspect.getsource(serve)`, not the banner |
| M6 — `commit()` moved inside the per-record loop | **14 passed** — behavior correct, nothing defends it |

The evaluator found the store-side path IS reachable from client-shaped data without mocking:
`request_id="   "` and `request_id="None"` are truthy, pass validation, and trip task 01's guard. Those
are contained correctly — but no test exercises them.

**Rulings on the two disclosed wrinkles:** keep `store_error:` as a stable documented prefix (do not
push it into task 02's frozen tuple — that would be a fence violation, and the two families deserve to
be distinguishable); DERIVE the real batch index rather than shipping `None`, since `accepted` preserves
order and the rejected indices are known, so preserving task 02's always-defined invariant costs two
lines.

## 2026-09-04 — Phase 4 — Task 03 fix cycle 1

- **Agent:** implementer (continued) · **Model:** claude-sonnet-5 · **Rotation:** none at cycle 1.

### Return — Task 03 fix cycle 1

- **Orchestrator verification, executed:**
  - **Blocker 1 closed.** All four wrong-typed fields are now contained per record, each with a REAL
    index, its `request_id`, and a distinguishable reason:

        session_id: ["x"]    -> store_error:ProgrammingError   good rows survive 2/200
        model: 123           -> store_error:TypeError          good rows survive 2/200
        repo_raw: 123        -> store_error:AttributeError     good rows survive 2/200
        user_email: {"a":1}  -> store_error:ProgrammingError   good rows survive 2/200

    `index=1` and `request_id='req-2'` on every one — the always-defined invariant is restored, so
    mutation M15 (blanking both) can no longer hide.
  - **Blocker 1b closed.** Forcing a `sqlite3.OperationalError` mid-batch: it still propagates by design
    (an outage must not become a cheerful 200), but the batch is now rolled back first. An OUTSIDE
    read-only connection sees `(0 rows, 0 tokens)`, and a subsequent unrelated request surfaces only its
    own record — `(1 row, 50 tokens)`. The orphan-commit-by-side-effect path is gone.
  - Suite **131 passed** (111 + 20). Fence held.
- The catch boundary is `_RECORD_DATA_ERRORS = (ValueError, TypeError, AttributeError, KeyError,
  sqlite3.InterfaceError, sqlite3.ProgrammingError)`, with `sqlite3.OperationalError` deliberately
  excluded and documented per-field — the module docstring records which exception each of the four
  reproductions raises and why, so the boundary is a stated decision rather than an accident.

## 2026-09-04 — Phase 4 — Task 03 evaluation, cycle 2

- **Agent:** evaluator (continued — holds the 17-mutation corpus)
- **Model:** claude-opus-5 (frontier tier)
- **context_chars:** 5760

### Return — Task 03 evaluation cycle 2: **PASS (4/5)**, and hardening

- **report_chars:** 15900 · **est_tokens:** (5760 + 15900) / 4 = **5415** (estimate)
- 20 mutations re-cut, **19 killed**. Every cycle-0 survivor now dies: M3 (store-side containment, killed
  by 3 tests), M5 (banner), M7 (commit-once), M15 (rejection identifier).
- **Catch-boundary audit — the mirror-image defect is NOT present.** Six exception classes injected at
  the store call: `OperationalError("database is locked")`, `OperationalError("disk I/O error")`,
  `DatabaseError("disk image is malformed")` and `MemoryError` all **propagate**; only
  `ProgrammingError("closed database")` and a generic `InterfaceError` are swallowed, and both are
  structurally unreachable in a single-threaded receiver whose `store.close()` runs only after
  `serve_forever()` returns. The `OperationalError` exclusion is real, not decorative.
- **Rollback audit — cannot over-reach.** A previously committed row survives the rollback intact; since
  `commit()` runs exactly once per request, "since the last commit" is precisely "this request's
  uncommitted rows". Verified through a SEPARATE `sqlite3.connect` to the file rather than the writing
  connection — the only way that assertion means anything.
- **Derived index — correct, and faster than feared.** `rejected_indices` is a SET (O(1), not O(n²)); a
  500-record batch with 250 rejections completed in 0.02s. On a 12-record interleaved batch the store
  rejections at true positions 4, 6, 9 were reported as 4, 6, 9 — a naive derivation would have said
  2, 4, 6.

**The single survivor was this goal's signature defect for the fourth consecutive task.**
`accepted_indices = list(range(len(accepted)))` passed all 20 tests, because every test asserting an
index placed the bad record at position 1 with no PRECEDING validation rejection — so both derivations
agreed there. Orchestrator-confirmed on an interleaved batch that the real logic reports index 3 where
naive reports 2. Correct code, undefended.

Running tally of this exact pattern: task 00's published totals asserted against themselves · task 01's
`dp_key` unpinned at the call site · task 02's AC9 asserting an orphan `ts` the store never reads ·
task 03's index derivation. **Four for four.** Every one was found by mutation, none by reading.

### Return — Task 03 hardening

- `test_store_path_rejection_index_survives_a_preceding_validation_rejection` added: batch
  `[good, bad_ts, whitespace_request_id]` where the store rejection sits AFTER a validation rejection,
  so the two derivations diverge. **Orchestrator-verified: mutating to `list(range(len(accepted)))` now
  turns it RED** (`{1} == {1, 2}` — the naive form collapses the store rejection onto index 1, colliding
  with the validation rejection). Restored byte-identical.
- `KeyError` kept with a documented rationale: no client-triggerable reproduction exists, its only
  reachable source is a receiver-side wiring bug (a future rename of `map_record`'s return keys), and
  containing it converts that bug into "every record rejected with `store_error:KeyError` and a 200" —
  which is exactly the signature task 07 now alarms on.
- Suite **132 passed**.

**TASK 03 CLOSED — evaluator PASS 4/5, hardening applied and independently verified.**

Deliverables: `billing/otel/receiver.py` (`POST /v1/transcript-usage`, per-record containment across the
documented `_RECORD_DATA_ERRORS` family with `OperationalError` deliberately excluded, rollback-before-
escape, derived batch indices, documented 200 response contract with the stable `store_error:` prefix,
content-free 400 logging), `tests/test_receiver.py` (21 tests). Cumulative suite: **132 tests**.

Requirement recorded into `07-integration.md`: alarm on `accepted > 0 AND rejected == len(accepted) AND
every reason starts with 'store_error:'` — the systemic signature covering both residual swallow paths.

## 2026-09-04 — Phase 4 — Task 04 (attribution), cycle 1

- **Agent:** implementer · **Model:** claude-sonnet-5 (light tier, agent-pinned; effort medium)
- **Routing reason:** next in dependency order. Task 04 modifies `attribute.py`, whose SQL is applied to
  BOTH `token_usage` and `cost_usage`. A mistake here is not a degraded feature — it is
  `OperationalError` at query-prepare time, taking down `python -m billing.otel.bill` and the lake
  export for the existing OTLP-only fleet who never touch the desktop app.
- **Task writes fence:** `billing/otel/attribute.py`, `tests/test_attribute.py`

**Orchestrator precondition check, and a trap worth more than the task file gives it:**

    token_usage:  usage_source=True   entrypoint=True
    cost_usage:   usage_source=True   entrypoint=FALSE

`cost_usage` deliberately has NO `entrypoint` column — task 01's contract puts it on token rows only,
and task 03's evaluation confirmed that as correct. So the new `desktop-scratch` branch MUST key on
`usage_source='transcript'`, never on `entrypoint='claude-desktop'`. `entrypoint` is the semantically
obvious field to reach for and it is the one that breaks: `resolved_view('cost_usage')` at `bill.py:57`
and `export.py:78` would raise `no such column: t.entrypoint` at prepare time. Passed into the context
package explicitly rather than left to be discovered by a failing smoke test.

Also confirmed: `deploy/claude-repo-tag.py` is registered on `SessionStart`, so a desktop scratch
session genuinely DOES get a `session_repo_timeline` row carrying `repo='unknown'` — which is why a
naive append to the `CASE` never fires and the ordering requirement is real rather than theoretical.

- **context_chars:** 7940

### Return — Task 04 cycle 1

- **report_chars:** 5480 · **est_tokens:** (7940 + 5480) / 4 = **3355** (estimate)
- **Silent-success check, orchestrator-executed:**
  - Suite **142 passed** (132 + 10). Fence held.
  - **Cross-table safety confirmed** — the failure mode that would have taken down the existing fleet:
    `resolved_view('token_usage')` and `resolved_view('cost_usage')` BOTH compile and execute. OTLP rows
    classify to `['absent','timeline','wrapper']` on both tables — no `desktop-scratch` leakage.
  - **The golden baseline is STILL byte-identical** (`9bc05192e963db53…`) after a change to `attribute.py`,
    which feeds `bill.py` directly. Four consecutive tasks have now modified the code path `bill.py`
    reads and the pre-change baseline has survived every one.
  - **The ordering trap is handled.** Seeded two desktop sessions that BOTH have `session_repo_timeline`
    rows — the condition under which a naive append never fires:

        desk-scratch  resolved_repo=unknown                attribution_source=desktop-scratch
        desk-real     resolved_repo=github.com/acme/web    attribution_source=timeline

    The scratch session is claimed by the new branch before `timeline` can take it; the real-repo desktop
    session still reports `timeline`. `resolved_repo()` unchanged on both.
  - The branch is keyed on `usage_source='transcript'` AND `resolved_repo = 'unknown'`, not on
    `entrypoint` — the trap flagged in the context package was avoided.
- The worker mutated its own classification logic unprompted (branch order inverted, `usage_source`
  predicate dropped, literal changed) and reported RED for all three, with SHA-verified restores.

**Doc gap flagged by the worker, outside its fence, recorded for Phase 6:** `README.md`'s `attribute.py`
bullet documents only the four-value fallback chain and now omits `desktop-scratch`. Correctly not
edited here; `align-docs` owns it.

## 2026-09-04 — Phase 4 — Task 04 evaluation, cycle 1

- **Agent:** evaluator · **Model:** claude-opus-5 (frontier tier, effort high)
- **Routing reason:** mandatory per-task evaluation. This task can break `bill.py` and the lake export
  for OTLP-only customers, and its correctness depends on SQL branch ordering that is invisible to a
  reader who does not construct the collision case.
- **context_chars:** 6520

### Return — Task 04 evaluation cycle 1: NEEDS FIXES (3/5)

- **report_chars:** 14700 · **est_tokens:** (6520 + 14700) / 4 = **5305** (estimate)
- **The production code is CORRECT.** The evaluator built a differential harness — extracting
  `git show HEAD:billing/otel/attribute.py` into a scratch module and emitting the PRE and POST SQL
  expressions as sibling columns of one `SELECT`, so row identity is structural rather than by
  re-seeding. Matrix: 162 sessions (usage_source × repo × repo_raw × 9 timeline shapes including the
  `_FIRST` fallback, multi-entry as-of picks, same-second `seq` ordering) × 2 tables = **324 rows**.

      resolved_repo differences:        0
      attribution_source differences:  78   (all transcript rows moving into desktop-scratch)
      OTLP-row classification changes:  0

  Downstream equality confirmed too: `bill.py` stdout PRE == POST, `export` summary and line-items
  PRE == POST, and the golden baseline re-derived independently at `9bc05192e963db53…`.
- Query-time invariant verified by execution: a late timeline entry retroactively flips BOTH
  `resolved_repo` and `attribution_source` with the usage row's bytes and `dp_key` untouched, and a
  corrected entry flips it back. `desktop-scratch` participates in the retroactive property rather than
  freezing a label.

**BLOCKER — test gap, and the FIFTH consecutive instance of this goal's signature defect.**
Mutation M9 replaces `{resolved_repo(alias)}` with `{alias}.repo` in the new branch — reading the
STORED repo instead of the RESOLVED one — and **passes all 142 tests**. Orchestrator-confirmed.

It is not a semantic no-op. Demonstrated on a real shape:

    Session B: launched in a real repo, then cd'd OUT to a scratch directory.
      SHIPPED   resolved_repo=unknown   attribution_source=desktop-scratch
      M9 naive  resolved_repo=unknown   attribution_source=timeline

The session bills NOWHERE, and the naive form labels it `timeline` — exactly the misreport this task
exists to prevent, reached via a `cd` rather than at launch. The mirror case (launched in scratch, cd'd
INTO a real repo) is wrong in the opposite direction.

Root cause of the gap: **every existing test sets the stored `repo` and the timeline repo to the SAME
value** — AC1's tests use `unknown` for both, AC2's uses the same real repo for both. So nothing pins
the branch to the resolved repo rather than the stored one. The worker's own three mutations (branch
order, `usage_source` predicate, result literal) did not probe this axis either.

Running tally: task 00 totals · task 01 `dp_key` · task 02 orphan `ts` · task 03 index derivation ·
task 04 stored-vs-resolved repo. **Five for five**, every one found by mutation, none by reading.

No production change is required or wanted — `attribute.py` is already right.

## 2026-09-04 — Phase 4 — Task 04 fix cycle 1 (TEST-ONLY)

- **Agent:** implementer (continued) · **Model:** claude-sonnet-5 · **Rotation:** none at cycle 1.

### Return — Task 04 fix cycle 1 (test-only)

- **Orchestrator verification, executed:**
  - `billing/otel/attribute.py` SHA256 `b7468f2b99d0199149787e21a04e0112…` — **identical to the cycle-0
    gold**. The production file was genuinely not modified; the fix is tests only, as required.
  - **M9 now dies in BOTH directions.** Mutating line 89 (`{resolved_repo(alias)}` → `{alias}.repo`,
    anchor asserted unique) fails exactly the two new tests:

        test_resolved_repo_not_stored_repo_scratch_launch_cd_into_real_repo  FAILED
        test_resolved_repo_not_stored_repo_real_launch_cd_into_scratch       FAILED
        2 failed, 10 passed

    Both directional failures are the predicted ones: `'desktop-scratch' == 'timeline'` for the
    cd-into-real case, and `'timeline' == 'desktop-scratch'` for the cd-out-to-scratch case.
  - Restored byte-identical. Suite **144 passed** (132 + 12).
- The `_fetch_*` hazard was folded in with a `_sole_value_per_session` helper that ASSERTS all rows of a
  session agree on the column rather than silently keeping the last — a stricter fix than the
  `(session_id, dp_key)` keying suggested, and it converts a future silent-hide into a loud failure.

## 2026-09-04 — Phase 4 — Task 04 evaluation, cycle 2 (NARROW SCOPE)

- **Agent:** evaluator (continued — holds the differential harness and the 10-mutant corpus)
- **Model:** claude-opus-5 (frontier tier)
- **Routing reason:** mandatory re-evaluation after a fix. **Scope deliberately narrowed:** the fix is
  test-only, `attribute.py` is SHA-verified unchanged, and the evaluator's own 324-row differential
  already established the production code correct. Re-running that audit would re-derive settled work.
  The re-evaluation is therefore asked only to confirm its stated acceptance criterion is met and that
  the new tests are not themselves vacuous — not to repeat the regression matrix.
- **context_chars:** 3980

### Return — Task 04 evaluation cycle 2: **PASS (4/5)**, and hardening

- Full 10-mutant corpus re-run: **M9 is dead** (2 failed, was 10 passed) and NO previously-killed mutant
  regressed — six of them got strictly stronger kill counts. Clean suite 144.
- The evaluator verified the fence without trusting the reported SHA: independently confirmed 5510
  bytes, 109 lines, `git diff --stat` unchanged at `33 insertions(+), 11 deletions(-)`, and re-read
  lines 66-109 to see the branch verbatim. It noted `attribute.py`'s mtime was LATER than the test
  file's — consistent with mutate-and-restore — and reasoned that content, not mtime, is what matters.
- `_sole_value_per_session` verified strictly stricter: all 24 pre-existing assertions byte-identical
  (only renumbered), the helper genuinely raises on disagreement, return shape unchanged.

**The orchestrator's `_FIRST` concern was HALF right, and the right half mattered.** The tests did not
fall through to `_FIRST` — `_AS_OF` fired. But the timeline `ts` EQUALLED the datapoint `ts` rather than
preceding it; they passed only because `_AS_OF` uses `<=`. Three comments claimed the entry "precedes
the datapoint", which was false. The trap: a maintainer trusting those comments could shift
`DESKTOP_NANO` earlier, silently converting both into `_FIRST`-fallback tests — still green, no signal,
and M9 quietly resurrected.

### Return — Task 04 hardening (agent STALLED, orchestrator completed the verification)

The hardening agent hit a watchdog stall (`no progress for 600s`), last line: *"SHA restored and content
re-verified correct. Now confirm all tests pass green on the restored file and run the full suite."* The
outstanding step was verification the orchestrator could perform directly, so it was completed here
rather than paying for a resume. **The stall produced no verdict and is not read as one.**

State verified by the orchestrator:
- `attribute.py` restored to gold `b7468f2b99d0199149787e21a04e0112…` — production file untouched.
- Suite **144 passed**.
- **The worker exceeded the instruction.** Asked to move the timeline `ts` an hour earlier, it instead
  seeded TWO genuinely-ordered, DIFFERENT timeline entries per test — "not one entry restated at two
  timestamps" — which is what actually pins the branch to `_AS_OF` (the LATEST entry `<=` the
  datapoint) rather than to `_FIRST`.
- **The payoff lands:** neutering `_AS_OF` to `SELECT NULL` now fails BOTH new tests (it survived all 12
  before). Restored to gold after each mutation.

**TASK 04 CLOSED — evaluator PASS 4/5, hardening applied and independently verified.**

Deliverables: `billing/otel/attribute.py` (the `desktop-scratch` branch, keyed on `usage_source` so it
prepares on both tables, ordered ahead of `timeline`), `tests/test_attribute.py` (12 tests).
Cumulative suite: **144 tests**. Golden baseline intact through a fifth consecutive task.

Note on the task 07 requirement added earlier: this hardening partially closes the `_AS_OF` vs `_FIRST`
discrimination gap at the unit level. The task 07 requirement remains worth keeping — it covers the
INTEGRATION path end to end — but it is no longer the only thing defending that mechanism.

**Correction to the note above, after direct verification:** the hardening closed `_AS_OF`
discrimination only. Neutering `_FIRST` to `SELECT NULL` still leaves all 12 tests green — with every
timeline entry positioned BEFORE the datapoint, `_AS_OF` always answers and `_FIRST` never executes.
The task 07 requirement has been rewritten to target precisely that remaining arm: a datapoint whose
`ts` PRECEDES every timeline entry for its session, which `attribute.py`'s own docstring says exists for
"export-interval rounding, small clock skew". Acceptance: mutating `_FIRST` to NULL must turn it red.

## 2026-09-04 — Phase 4 — Task 05 (billing basis), cycle 1

- **Agent:** implementer · **Model:** claude-sonnet-5 (light tier, agent-pinned; effort medium)
- **Routing reason:** next in dependency order, and the largest remaining task by requirement count. It
  is where the actual-vs-estimated distinction finally reaches a CLIENT INVOICE, and the first task to
  consume task 00's golden baseline as the regression gate it was captured for.
- **Task writes fence:** `billing/otel/bill.py`, `billing/otel/invoice.py`, `tests/test_bill.py`,
  `tests/test_invoice.py` — four paths, the widest fence in this goal.
- **Orchestrator scoping notes passed into the context package:**
  - `bill.py:60` `have_cost = bool(actual_rows)` is the global basis switch that must become
    source-aware; `:111` is the "ACTUAL cost" label that would otherwise print over estimates.
  - `invoice.py` uses the identifier `actual_cost` throughout — including as a CSV column name — so
    the mislabelling risk is literal, not conceptual.
  - The golden baseline (`9bc05192e963db53…`, LF-only, 2000 B) has survived five consecutive tasks
    touching the path `bill.py` reads. Task 05 is the first task ALLOWED to change that output, and
    must therefore prove the OTLP-only case still matches byte-for-byte while the mixed case differs.
- **context_chars:** 9840

### Return — Task 05 cycle 1

- **report_chars:** 7960 · **est_tokens:** (9840 + 7960) / 4 = **4450** (estimate)
- **Silent-success check, orchestrator-executed:**
  - Suite **162 passed** (144 + 18). Fence held — `bill.py` and `invoice.py` modified,
    `tests/test_bill.py` and `tests/test_invoice.py` added, nothing else.
  - **THE GOLDEN GATE HELD.** Task 05 substantially rewrote `bill.py` — the basis switch, the labels,
    the attribution column, a new detector — and an OTLP-only store's output is still byte-identical to
    the pre-change baseline (`9bc05192e963db53…`, 2000 B, 0 CRLF, newline-normalized comparison). The
    baseline file itself was never touched. This is the gate doing exactly what it was captured for six
    tasks ago, on the one task allowed to change this output.
  - Mixed-store behavior verified directly:

        basis: MIXED — ACTUAL cost.usage + RATE-CARD estimate (desktop, placeholder rates)  x1.50 markup
          actual (claude_code.cost.usage)  $ 5.0000
          rate-card estimate (desktop)     $15.0000
        GRAND TOTAL cost basis   $50.0000     (= 35 actual + 15 rate-card)
        GRAND TOTAL billed       $75.0000     (= 50 x 1.50)
        desktop-scratch  1.0M  59.2%  desktop session with no billable repo -> unattributed
                                      (billable, review before invoicing)

    Markup applied **exactly once**: $75, not the $112.50 a double application would produce. The
    `desktop-scratch` line renders with its own note and the widened column.

**The worker caught this goal's signature defect IN ITSELF, before evaluation — a first.** It ran the
four mutations it was asked to run, then added a fifth of its own on `invoice.py`: dropping the
rate-card portion from the per-line billed value (`cost_basis = v["actual_cost"] + v["estimated_cost"]`
→ `v["actual_cost"]`). That mutation **passed all 7 invoice tests**. It recognised the gap, added a
per-model `billed_usd` assertion to `test_line_items_csv_splits_actual_and_estimated`, and re-ran the
mutation to RED (`0.0 == 1.35`). Five previous tasks needed an evaluator to find that class of hole;
this is the first time a worker found its own.

- **Design decision the worker flagged, and the orchestrator endorses:** `invoices.actual_cost` and
  `invoice_line_items.actual_cost` keep their pre-existing honest meaning — the pure OTLP-actual sum,
  matching the schema's own column comment. Only `total_billed` and the rendered outputs include the
  desktop rate-card portion. Since the schema is frozen and the column is literally named
  `actual_cost`, widening its meaning would have been the mislabelling this task exists to prevent.

## 2026-09-04 — Phase 4 — Task 05 evaluation, cycle 1

- **Agent:** evaluator · **Model:** claude-opus-5 (frontier tier, effort high)
- **Routing reason:** mandatory per-task evaluation. This is the task whose output reaches a client
  invoice, and the widest fence in the goal (4 files).
- **context_chars:** 8420

### Return — Task 05 evaluation cycle 1: NEEDS FIXES (3/5)

- **report_chars:** 15800 · **est_tokens:** (8420 + 15800) / 4 = **6055** (estimate)
- **The implementation is correct.** 20/20 money checks computed independently from `RatingService`:
  actual-only, rate-card-only, mixed, and `--basis rates` over each. The sharpest trap is genuinely
  closed — `--basis rates` on a mixed store yields `$1.90`, not the `$2.80` double-count, and a
  `999999.0` sentinel planted in a rate_card `cost_usage` row is completely absent from the rates path.
  Markup proven linear across a 1.0/2.0/3.0 sweep (a double-apply would be quadratic).
- **Existing-fleet path proven safe on a REAL migration**: the evaluator built a pre-task-01
  `LEGACY_SCHEMA` database, inserted legacy-shaped rows, opened it through `OtelStore` to trigger
  `_migrate`, and confirmed `$63.00` billed with `estimated_cost_usd=0.0`. No silent loss.
- Golden gate confirmed adversarially: three separate conditionality-breaking mutations (unconditional
  split lines, always-MIXED label, unconditional column widening) were ALL killed by the golden test.
- 22 mutations, **19 killed**.

**BLOCKER — two named tests cannot fail on the property they exist to prove, and one guards a client
invoice. Sixth consecutive task with this pattern.**

`M13` — the `.txt` subtotal `Subtotal (Anthropic actual cost)` printing `actual_cost + estimated_cost`.
Orchestrator-reproduced: mutating both sites so the line reads **$10.9000 under a label saying
"Anthropic actual cost"** when the true Anthropic figure is $10.0000 — and **all 18 tests pass**. That
is a client-facing invoice presenting placeholder-rate estimates as Anthropic's reported cost, which is
verbatim the mislabelling this task exists to prevent.

`M12` — the per-line `Actual` column folding in the estimate. 18/18 green.

Mechanism for both: `test_txt_distinguishes_actual_from_estimated` asserts only label-substring
presence plus free-floating `"$10.0000" in text`. Both are satisfied by SOME OTHER LINE under the
mutant. **No assertion binds a number to its label.**

`M18` — the overlap detector subtracting the desktop rate-card portion when it fires (billed $10.95 →
$10.50). 18/18 green. The fixture gives the overlapping session NO `cost_usage` row, so any silent
correction subtracts zero. The test's own comment says the session "contributes 0" — which is exactly
why it cannot distinguish "the detector changed nothing" from "the detector changed the total by an
amount that happens to be zero here."

Both fixes are test-only; `bill.py` and `invoice.py` are correct as written.

## 2026-09-04 — Phase 4 — Task 05 fix cycle 1 (TEST-ONLY)

- **Agent:** implementer (continued) · **Model:** claude-sonnet-5 · **Rotation:** none at cycle 1.

### Return — Task 05 fix cycle 1 (test-only + two approved minor edits)

- **Orchestrator verification, executed:**
  - **M13 now RED** — folding `estimated_cost` into the `Subtotal (Anthropic actual cost)` line (applied
    at both sites) fails `test_txt_distinguishes_actual_from_estimated`. The client-invoice
    mislabelling is now defended.
  - **M18 now RED** — making the detector drop the desktop portion when it fires
    (`0.0 if overlap_sessions else desktop_rc_by_name.get(nm, 0.0)`) fails
    `test_overlap_detector_does_not_change_billed_total`. The fixture now carries a non-zero rate-card
    row, so a silent correction is observable rather than subtracting zero.
  - **`bill.py` SHA `c5bdb7b32044e654…` — IDENTICAL to the version the evaluator ran its 20/20 money
    checks and 19/22 mutation kills against.** No billing logic was edited in this cycle. The money
    audit therefore carries forward unchanged and does not need re-deriving.
  - Golden gate holds: OTLP-only output still byte-identical after the `invoice.py` edits.
    Baseline `9bc05192e963db53…` untouched.
  - Suite **162 passed**.
- Both minor items were fixed and re-verified: the estimate-branch table now measures exactly 104
  characters per row (matching its rules and subtotals, so a client-facing invoice no longer overhangs
  its own rule), and `invoice.py`'s `cost_source` handling now uses strict equality on both branches,
  matching `bill.py` — an unrecognized value is excluded from both files' actual bucket rather than
  being dropped in one and silently folded into `actual_cost_usd` in the other.

## 2026-09-04 — Phase 4 — Task 05 evaluation, cycle 2 (NARROW SCOPE)

- **Agent:** evaluator (continued — holds the 22-mutant corpus and the independent money harness)
- **Model:** claude-opus-5 (frontier tier)
- **Scope narrowed deliberately:** `bill.py` is SHA-identical to the version already audited, so the
  20/20 money matrix and the legacy-migration check carry forward. Only `invoice.py` (two minor edits)
  and the two test files changed. The re-evaluation is asked to confirm its three surviving mutants are
  dead, that the new assertions are not themselves vacuous, and that the `invoice.py` edits did not
  perturb the money — not to re-run the full matrix.
- **context_chars:** 4610

### Return — Task 05 evaluation cycle 2: **PASS (4/5)**, and hardening

- 29 mutations, **28 killed**. M12, M13 and M18 dead; M11 died as a bonus; no previously-killed mutant
  regressed despite `invoice.py` changing.
- **The orchestrator's adjacency concern was answered directly.** The new parsing helpers were attacked
  on exactly that axis and held: N2 moved a value onto a neighbouring line WITHOUT changing it and was
  caught by `_sole_money`'s `len(vals) == 1`; N1 swapped the two subtotal values between their labels —
  killed; N3 swapped the Actual and Est. columns — killed. The binding is real, not positional luck.
- **Truncation audit clean:** no model name truncates (longest is 17 chars after `normalize_model`,
  exactly the limit), long repos truncate visibly with `…`, and the untruncated value remains in
  `line_items.csv`. The `cost_source` strict-equality change was proven money-neutral END TO END on a
  real pre-task-01 legacy database (`actual=42.0, estimated=0.0, billed=63.0`).

**Orchestrator overrode the evaluator's non-blocking ruling on N6, and the worker's fix proved the
override right.** The evaluator judged the unasserted `.txt` `TOTAL DUE (USD)` line non-blocking —
sound reasoning: the expression is byte-unchanged from `HEAD` and `total_billed` is pinned by the CSV
test and the persisted row. The orchestrator closed it anyway on one ground the evaluator itself
raised: **this task duplicated that line into two branches** (verified: lines 168 and 179), so the
copies can drift independently, and the `.txt` is the document the client reads. A divergence would
undercharge by $5.45 on the example store with every test green and the CSV still correct.

The worker pinned BOTH copies, not just the one named. Orchestrator-verified: mutating both
`money(total_billed)` sites to print the cost basis now fails **two** tests —
`test_txt_distinguishes_actual_from_estimated` and
`test_txt_actual_only_store_has_no_estimate_subtotal`. Pinning only the estimate branch would have left
half the hazard.

**TASK 05 CLOSED — evaluator PASS 4/5, hardening applied and independently verified.**

Deliverables: `billing/otel/bill.py` (source-aware basis with three accurate labels, conditional split
lines, widened attribution column with `desktop-scratch`, the double-billing overlap detector),
`billing/otel/invoice.py` (actual-vs-estimated in `.txt`, `summary.csv` and `line_items.csv`, derived at
generation time, regeneration semantics untouched), `tests/test_bill.py` + `tests/test_invoice.py`
(18 tests). Cumulative suite: **162 tests**.

`bill.py` sha `c5bdb7b32044e654…` and golden baseline `9bc05192e963db53…` — the gate captured in task 00
has now survived all six implementation tasks and is still byte-identical for an OTLP-only store.

## 2026-09-04 — Phase 4 — Task 06 SPLIT into 06a / 06b (orchestrator planning decision)

**Why.** Task 06 is 9 write paths, 55 requirements, 28 acceptance criteria — roughly THREE TIMES the
size of any other task in this goal. Every completed task has needed 1-3 fix cycles at a third that
size. Running it as a single spawn risks a long cycle whose failures are hard to attribute, and the
continuation ladder's decomposition rung exists precisely because oversized tasks fail this way.
Splitting proactively is cheaper than splitting after exhaustion.

**The seam is natural, not arbitrary.** The hook is a self-contained standalone program that must run
on a developer machine with no imports from `billing/`. The rollout is packaging: registering that
program on two enrolment tracks and pinning line endings. Different failure modes, different reviewers'
attention, no shared file.

**Derived ownership contracts — both write-sets are strict subsets of task 06's, and disjoint from each
other:**

    06a — the hook
      writes: deploy/claude-transcript-usage.py
              tests/test_transcript_hook.py
      depends_on: 00, 02, 03

    06b — rollout on both tracks
      writes: deploy/managed-settings.json
              client-package/claude-transcript-usage.py
              client-package/configure.py
              client-package/build.py
              client-package/VERSION
              .gitattributes
              tests/test_configure.py
      depends_on: 06a   (the hook must exist before it can be registered, copied, or line-ending pinned)

Union = task 06's write set exactly, with no path in both. Task 06 is complete only when BOTH derived
tasks hold an evaluator PASS — the parent's acceptance criteria are split across them, not relaxed.

`.gitattributes` sits in 06b and carries three pins routed here from earlier evaluations:
`tests/golden/** -text` (task 00's CRLF blocker), `deploy/*.py text eol=lf` (task 06's own byte-identity
requirement), and it must not disturb the existing `merge=union` and `*.sh`/`*.ps1` entries.

## 2026-09-04 — Phase 4 — Task 06a (the standalone hook), cycle 1

- **Agent:** implementer · **Model:** claude-sonnet-5 (light tier, agent-pinned; effort medium)
- **Routing reason:** first half of the split. This is the only component in the goal that runs on a
  DEVELOPER'S MACHINE rather than the server, and the only one whose failure can break a colleague's
  Claude Code session. Its non-negotiable rule — always exit 0 — outranks every other requirement in it.
- **Task writes fence:** `deploy/claude-transcript-usage.py`, `tests/test_transcript_hook.py`
- **context_chars:** 10240

### Return — Task 06a cycle 1

- **report_chars:** 8900 · **est_tokens:** (10240 + 8900) / 4 = **4785** (estimate)
- **Silent-success check, orchestrator-executed:**
  - Suite **189 passed** (162 + 27). Fence held — only `deploy/claude-transcript-usage.py` added.
    Nothing under `client-package/`, no `managed-settings.json`, no `.gitattributes` — 06b's scope
    was respected exactly.
  - **Always-exit-0 verified as REAL SUBPROCESSES**, not by reading: empty stdin, malformed JSON,
    missing `transcript_path`, and a nonexistent path all exit **0**.
  - **The collapse is correct:** a cumulative pair (output 5 → 209, same `requestId`+`message.id`)
    yields **209** — verified neither the sum (214) nor the first block (5).
  - **Privacy holds:** a seeded `SECRET_PROMPT_TEXT_MARKER` in `message.content` appears nowhere in the
    built payload, no `cwd` field is emitted, and the record carries exactly the 14 frozen fields.
  - **CROSS-CONTRACT CHECK — the hook's output was fed through the REAL server validator**
    (`billing/otel/transcript.validate_batch`) and came back `accepted=2, rejected=0`. This is the
    check that would catch a field-name mismatch between task 06's producer and task 02's consumer,
    and it is the first time in this goal that a producer and its consumer have been run against each
    other directly. The worker built the same check into its own suite (`test_ac3`).
  - Malformed trailing line skipped, not fatal: 3 of 3 valid rows parsed from a file ending mid-token.
  - Driven through `run()`, CLI (999 tokens) and VS Code (888 tokens) rows are both excluded.
- **Orchestrator harness limitation, recorded for honesty:** two of my probes initially misread the
  hook's internals — I called `build_payload_record` directly (bypassing the entrypoint filter that
  lives in `run()` at :469-472) and seeded a state file with the wrong shape (`post_batch` returns a
  3-tuple, and the forward-only watermark needs a properly seeded install epoch). Both produced
  misleading output that looked like defects. Neither was. Recorded because a wrong harness reporting a
  false defect is the same class of error as a wrong harness reporting a false pass — and this goal has
  now seen three of the latter.

**Design observation routed to the evaluator, not raised as a defect:** `build_payload_record` STAMPS
`"entrypoint": ENTRYPOINT` rather than carrying `terminal["entrypoint"]`. Since `run()` filters on the
row's real entrypoint first, the two are provably equal at that point — but it means the SERVER's
desktop-only check can never reject anything this hook sends, because the client always labels its
output `claude-desktop`. That is the "two filters testing the same predicate are not independent"
concern the goal already documents, and task 05's overlap detector is its mitigation. Carrying the
value instead of stamping it would make the server check a genuine second defense. Worth a ruling.

## 2026-09-04 — Phase 4 — Task 06a evaluation, cycle 1

- **Agent:** evaluator · **Model:** claude-opus-5 (frontier tier, effort high)
- **Routing reason:** mandatory per-task evaluation. This is the only component that runs on a
  developer's machine and the only one whose failure can break a colleague's session.
- **context_chars:** 7620

### Return — Task 06a evaluation cycle 1: NEEDS FIXES (3/5)

- **report_chars:** 18900 · **est_tokens:** (7620 + 18900) / 4 = **6630** (estimate)
- The most thorough evaluation in this goal: **30 real-subprocess exit-code cases**, **36 mutations**
  (28 killed) run inside an isolated repo copy, and **live loopback receivers** rather than injected
  outcomes.
- **Money exact**: shipped totals match `conftest`'s published constants field-for-field
  (main 12/752/14984/37774, sidechain 3/50/500/1500, combined **55575** = `EXPECTED_COMBINED_TOTAL_TOKENS`,
  and ≠ the main-only 53522). Batching 1201 records → `[500,500,201]`, every batch passing the real
  `validate_batch` with zero rejections.
- **Privacy airtight under adversarial seeding**: 16 distinct markers across content, thinking blocks,
  tool results, file paths, `cwd`, `gitBranch`, uuids — **none** reached the payload, state file, or log.
  `.credentials.json` proven untouched by TRACING `builtins.open` and `Path.read_text`, then by
  ACL-denying the file and confirming the hook still runs — not by grepping.

**BLOCKER 1 — a path that does not exit 0.** Orchestrator-confirmed:

    CLAUDE_BILLING_TIMEOUT=''            exit=1
    CLAUDE_BILLING_TIMEOUT='not-a-float' exit=1
    CLAUDE_BILLING_TIMEOUT='2s'          exit=1
    CLAUDE_BILLING_TIMEOUT='  '          exit=1

`TIMEOUT = float(os.environ.get(...))` at `:104` sits at module scope, outside every `try`. The empty
string is the realistic trigger — a shell exporting an unset variable, or an MDM profile writing an
empty value. **`deploy/claude-repo-tag.py:44` carries the byte-identical defect**, so this is inherited
from the precedent rather than invented — but that also means it is a live bug in the hook ALREADY
DEPLOYED to the fleet. Recorded separately for the user; `claude-repo-tag.py` is outside 06a's fence.

**BLOCKER 2 — 401/5xx consume the drop bound, destroying billing permanently.**
Orchestrator-confirmed end to end against a real loopback receiver: after six runs against a 401, the
operator fixes the token and **the record is never re-sent — 0 records, 500 output tokens gone.** The
requirement scopes the bound to "an envelope 400"; the implementation applies it to every non-200
(`:533`). Its own rationale — "costs nothing to retry, self-heals the moment the network returns" —
applies verbatim to 401/5xx. **This is reachable on the most likely rollout mistake:**
`deploy/managed-settings.json` ships the `REPLACE_WITH_FLEET_BILLING_TOKEN` placeholder, so a
mis-substituted token yields exactly this 401.

**BLOCKER 3 — the drop bound never fires on an active machine, so a poison batch stalls forever.**
The retry counter is keyed on `_batch_hash`, which changes whenever batch composition changes. Against
a real always-400 receiver with one new record added before each of 15 runs: counters `[1]×15`,
`drops == []`, `resolved == []` — every later record stalled behind the poison batch indefinitely.
AC7's fixture uses a STATIC batch, so it passes either way.

**BLOCKER 4 — `test_ac7h` does not exercise the code AC7h is about.** It injects a `post_batch` that
returns the literal `"transport_fail"`, so `_default_post_batch` — the function that performs the
classification — is never run. Mutation **M13**, making `_default_post_batch` classify
connection-refused/DNS/timeout/TLS as `envelope_reject`, survives all 27 tests. That is the
offline-laptop data-loss bug AC7h exists to prevent, undetected by the test named for it.

**Two majors:** M02 (selector ignoring `apiBlockIndex` entirely, pure file order) survives because
AC1f's entries put the higher index last; M08 (sidechain detected by filename instead of the
`isSidechain` flag) survives because no fixture separates the flag from the `subagents/` path.

**Ruling on stamp-vs-carry: observation, not blocking** — and the evaluator PROVED the equivalence
rather than arguing it (mutation M06, carrying instead of stamping, leaves all 27 green). Recommended
anyway: one expression, `terminal.get("entrypoint")` already in hand, converts a documented
"not independent" seam into a real second defense.

## 2026-09-04 — Phase 4 — Task 06a fix cycle 1

- **Agent:** implementer (continued) · **Model:** claude-sonnet-5 · **Rotation:** none at cycle 1.

### Task 06a fix cycle 1 — AGENT STALLED MID-REFACTOR, suite left RED

- **Outcome:** watchdog stall (`no progress for 600s`), last line: *"Now fix the drop-bound keying
  (blocker 3) — per-record instead of whole-batch hash:"*. **The stall produced no verdict and is not
  read as one.** Third stall in this goal.
- **Unlike the two previous stalls, this one left the working tree BROKEN.** 18 tests fail — all of
  them in `tests/test_transcript_hook.py`, none in any other task's file, so the damage is contained.
- **Root cause diagnosed by the orchestrator:** a half-applied refactor. `_batch_hash` was deleted, its
  replacement `_record_retry_key(file_key, request_id)` was added at `:424`, but the call site at
  `:649` still references the deleted function:

      NameError: name '_batch_hash' is not defined
      deploy/claude-transcript-usage.py:649

  Syntactically valid, semantically dangling — exactly the failure mode a stall mid-edit produces.

- **State established before resuming, rather than resuming blind:**

  | Item | Status |
  |---|---|
  | Blocker 1 — `_parse_timeout` guard | **DONE** (`:107-117`) |
  | Blocker 2 — 401/403/408/429/5xx → `transport_fail` | **DONE** (`:536-588`), with rationale documented in-file |
  | Blocker 3 — per-record retry keying | **HALF-APPLIED** — helper exists, call sites not migrated |
  | Blocker 4 — `test_ac7h` driving the real `_default_post_batch` | **NOT STARTED** (no reference in tests) |
  | Major M02 — `apiBlockIndex` vs file-order disagreement | **NOT STARTED** |
  | Major M08 — `isSidechain` flag vs filename | **NOT STARTED** |

- Resumed rather than reverted: the completed halves (blockers 1 and 2) are the two most consequential
  fixes in the cycle, both verified present, and re-doing them would cost more than finishing the
  refactor already in flight.

### Return — Task 06a fix cycle 1 (resumed to completion)

- Suite **207 passed** (189 + 18 new). Fence held: only the two owned paths.
  `.gitattributes` showed `MM` in `git status`, which the orchestrator investigated as a possible 06b
  fence breach — it is byte-identical to the index (581 B, 0 CRLF both sides) and carries neither of
  06b's pins. Pure autocrlf bookkeeping, not an edit.
- **Blocker 1 CLOSED, orchestrator-verified as real subprocesses:** `CLAUDE_BILLING_TIMEOUT` of `''`,
  `'not-a-float'`, `'2s'`, `'  '` and `'2.0'` now ALL exit **0**. Previously four of those exited 1.
- **Blocker 2 CLOSED, orchestrator-verified against a live loopback receiver:**

      HTTP 401 -> transport_fail      HTTP 500 -> transport_fail
      HTTP 403 -> transport_fail      HTTP 503 -> transport_fail
      HTTP 429 -> transport_fail      HTTP 400 -> envelope_reject
      refused connection -> transport_fail

  Only a genuine 400 consumes the drop bound. The placeholder-token 401 path no longer destroys billing.
- Blockers 3 and 4 and both majors reported complete with RED proofs; `http.client.HTTPException` now
  caught; `entrypoint` now CARRIED from the row rather than stamped, adding the second structural
  defense the evaluator recommended.

**ORCHESTRATOR HARNESS FAILURE — recorded because it nearly produced a false blocker.**

Across four probes the orchestrator observed what looked like a severe unfixed defect: a 401 marking
the record `resolved` on the first attempt, no retry on later runs, and `('ok', 200, {})` returned for
BOTH a real 401 and a refused connection. It was about to be reported as a blocker.

Root cause: `RECEIVER`, `TOKEN` and `TIMEOUT` are read at **module scope**. The probes set
`os.environ["CLAUDE_BILLING_RECEIVER"]` AFTER `exec_module`, so the constant kept its default and the
fake servers were never contacted. Re-running with the environment set **before** import produced the
correct classification on every status.

Two earlier probes in the same task failed the same way for a different reason — calling
`build_payload_record` directly (bypassing the entrypoint filter in `run()`) and seeding the state file
with `install_epoch` when the real key is `install_ts`, so the forward-only watermark silently excluded
every test record.

**Running tally of verification steps in this goal that silently did nothing while looking like a clean
result:** the orchestrator's non-matching `sed` anchors · the evaluator's `json.dumps` backslash-escaping
false negative · the evaluator's corrupted mutation plugin · and now three orchestrator harness bugs in
this task alone. **Four of the seven were the orchestrator's own.** The discipline that catches them is
identical in every case: validate that the check can fail before trusting that it passed. The probe that
finally settled this one began by asserting the harness could ship a record at all.

## 2026-09-04 — Phase 4 — Task 06a evaluation, cycle 2

- **Agent:** evaluator (continued — holds the 36-mutation corpus and the 30-case exit-0 harness)
- **Model:** claude-opus-5 (frontier tier)
- **context_chars:** 6180

### Return — Task 06a evaluation cycle 2: **PASS (4/5)**, and hardening

- **43 mutations, 37 killed, ZERO anchor failures.** All 36 cycle-0 anchors still matched exactly once
  despite the send-loop restructure, so nothing was silently skipped. M13a, M02 and M08 all dead; six
  NEW mutations against the restructured code (M13b, M37, M38, M39, M40, M43) all killed; no regression
  among the 28 previously killed.
- **34 exit-0 cases, zero non-zero** — including four new state-shape cases (old batch-hash format,
  `envelope_retries` as a list, `files` as a string, garbage `install_ts`).
- **Per-record keying proven with the exact counter progression:**

      counters:  req-new-1: 5, req-new-2: 4, req-new-3: 3, req-new-4: 2, req-new-5: 1
      resolved:  ['req-poison']            <- drops ALONE
      recovery:  all five newcomers ship

  And the inverse: a newcomer joining a batch whose neighbour had burned 5 attempts starts at 1, not
  inheriting the exhausted count. Cycle 0 gave `[1]x15`, `drops == []`, permanent stall.
- **The 401 path fully recovers**: 8 runs → `drops: []`, `envelope_retries: {}`, token fixed → the
  receiver sees `['req-401']`. Cycle 0 lost it permanently after 6.
- Money, privacy, credentials-never-opened, in-flight, and batching all re-confirmed unchanged.

**The evaluator opened with a POSITIVE CONTROL** — `control record reached a REAL receiver:
['req-control']` — before drawing any conclusion from a record not shipping. That is exactly the
discipline the orchestrator's own probes lacked, and it is why its findings are trustworthy.

**It also corrected the orchestrator.** The orchestrator had suggested its cycle-0 harness might share
the env-before-import bug; it did not — it used a `load_hook(env)` helper that mutated `os.environ`
BEFORE `exec_module`, which is precisely why it got the correct classification in cycle 0. The broken
harness was only ever the orchestrator's.

### Return — Task 06a hardening

- **Header rewritten** (`:52-63`). It had described the OLD behavior — non-200 rejections, batch-hash
  keying, whole-batch drops — all three now false. This mattered beyond tidiness: **06b copies this file
  into `client-package/`**, so the wrong documentation would have shipped to developer machines in two
  places, and the header is the first thing a fleet admin reads. Fixed before the copy, not after.
- **The carried entrypoint is now pinned.** Orchestrator-verified: reverting
  `terminal_row.get("entrypoint") or ENTRYPOINT` to the stamped constant now fails
  `test_build_payload_record_carries_entrypoint_not_stamps_it`. The comment claiming a "second
  structural defense" is load-bearing rather than aspirational.
- Suite **208 passed**.

**TASK 06a CLOSED — evaluator PASS 4/5, hardening applied and independently verified.**

Deliverables: `deploy/claude-transcript-usage.py` (standalone stdlib-only hook: recursive enumeration,
terminal-block collapse, `isSidechain` classification, desktop-only filter, per-record retry keying,
400-only envelope rejection, in-flight withholding, forward-only watermark, always-exit-0),
`tests/test_transcript_hook.py` (46 tests). Cumulative suite: **208 tests**.

## 2026-09-04 — Phase 4 — Task 06b (rollout on both tracks), cycle 1

- **Agent:** implementer · **Model:** claude-sonnet-5 (light tier, agent-pinned; effort medium)
- **Routing reason:** second half of the split, and the last implementation task before integration.
  It is packaging rather than logic, but it decides whether the hook 06a built ever RUNS on a
  developer's machine — a correct hook that is never registered bills nothing.
- **Task writes fence:** `deploy/managed-settings.json`, `client-package/claude-transcript-usage.py`,
  `client-package/configure.py`, `client-package/build.py`, `client-package/VERSION`, `.gitattributes`,
  `tests/test_configure.py`
- **Orchestrator scoping — the exact shapes 06b must generalize, read from the code:**
  - `configure.py:50` — `HOOK_NAME = "claude-repo-tag.py"` is a SINGLE string; `:147` and `:416` build
    one path from it and `SystemExit` if that one file is absent. Must become two hooks.
  - `configure.py:52` — `HOOK_EVENTS` is a FLAT tuple of five events including `UserPromptSubmit`, and
    `:348` registers every hook on every event. The transcript hook must be **SessionEnd ONLY** —
    registering it on `UserPromptSubmit` would run a recursive transcript sweep on every prompt, which
    is exactly the latency the async registration exists to avoid. This needs a per-hook event map, not
    a shared tuple.
  - `build.py:45-59` — `CONTENTS` lists shipped files explicitly; omitting the new hook means the
    archive builds fine and installs nothing.
  - `.gitattributes` currently has no `text` rule for `deploy/` or `tests/golden/`. Both pins routed
    here from earlier evaluations must land without disturbing the existing `*.zip binary`,
    three `merge=union` lines, or `*.sh`/`*.ps1 text eol=lf`.
  - `VERSION` is `1.1.0`; `ADMIN.md` requires a bump.
- **context_chars:** 9420

### Return — Task 06b cycle 1

- **report_chars:** 7440 · **est_tokens:** (9420 + 7440) / 4 = **4215** (estimate)
- **Silent-success check, orchestrator-executed. Suite 234 passed** (208 + 26 new) — the orchestrator
  ran rung 3, which the worker had correctly deferred per the test-ladder skill.
- Fence held exactly: `.gitattributes`, `client-package/{VERSION,build.py,configure.py}`,
  `deploy/managed-settings.json`, plus the new `client-package/claude-transcript-usage.py`.
  `pilot-package/` untouched; `deploy/claude-transcript-usage.py` (06a's, verified) unmodified.

- **THE CRLF PROBLEM IS CLOSED.** This defect recurred four times across this goal — the two hook
  copies in Phase 3 cycle 5, the golden baseline in task 00, and the byte-identity requirement in
  task 06. Verified live:

      git check-attr text -- tests/golden/bill_otlp_baseline.txt   ->  text: unset
      git check-attr eol  -- deploy/claude-transcript-usage.py     ->  eol: lf
      git check-attr eol  -- deploy/claude-repo-tag.py             ->  eol: lf

  `text: unset` means git performs NO newline translation on the golden baseline, so task 05's
  regression gate can no longer fail on a Windows clone for a reason unrelated to billing. The
  `deploy/*.py` pin also retroactively protects the pre-existing hook.

- **Registration verified by parsing the JSON, not by reading it:**

      claude-repo-tag.py         -> ['CwdChanged','DirectoryAdded','SessionEnd','SessionStart','UserPromptSubmit']
      claude-transcript-usage.py -> ['SessionEnd']

  The transcript hook is `SessionEnd`-ONLY — the recursive sweep never runs on a prompt submit, which
  was the latency risk that justified the per-hook event map. The existing hook keeps all five events.
  `REPLACE_WITH_FLEET_BILLING_TOKEN` placeholder preserved; no real token committed.

- **Two operational facts the worker surfaced unprompted, both worth keeping:**
  1. `client-package.zip` is a build artifact and was NOT regenerated. **No developer on the opt-in
     track receives the new hook until someone runs `python3 build.py --endpoint <url> --token <token>`
     from `client-package/` and redistributes the zip** through an access-controlled channel per
     `ADMIN.md`. A required manual rollout step, not automatic from this work.
  2. A rollback runbook: unregister the hook (remove the `SessionEnd` entry from
     `managed-settings.json`, and/or `configure.py uninstall` plus a rebuilt zip), and remediate stored
     rows with `DELETE FROM token_usage WHERE usage_source='transcript'` and the matching
     `cost_usage` delete. Both filter on a column only the new hook's writes ever set, so they touch
     zero OTLP rows on a mixed store. This closes the rollback gap flagged back in Phase 3 cycle 2.

- The worker also self-corrected a test that false-failed on a COMMENT containing `import billing`,
  replacing the substring check with an AST walk over real `Import`/`ImportFrom` nodes.

## 2026-09-09 — Phase 4 — Task 06b evaluation, cycle 1

- **Agent:** evaluator · **Model:** claude-opus-5 (frontier tier, effort high)
- **Routing reason:** mandatory per-task evaluation, and the LAST implementation task in the goal.
  Packaging decides whether a verified hook ever runs on a developer's machine.
- **context_chars:** 6980

### Return — Task 06b evaluation cycle 1: **PASS (5/5)**

- **report_chars:** 12600 · **est_tokens:** (6980 + 12600) / 4 = **4895** (estimate)
- First 5/5 awarded to an implementation task in this goal.
- **21 mutations, ALL caught. Zero vacuous tests** — the first task in this goal where the signature
  defect does not appear at all. Every one of the 26 tests fired under at least one proven mutation,
  including four separate mutations dropping each pre-existing `.gitattributes` line.
- **Seven hostile install/uninstall starting states** all round-trip clean: empty file, no settings
  file, no `hooks` key, unrelated hooks on the same events, a STALE registration from a prior version,
  and — the sharp one — a stale registration at a DIFFERENT install directory (`/old/place/`,
  `C:\legacy\`), which is stripped because the needle is the basename. Three consecutive installs stay
  idempotent; a partial install still uninstalls to zero orphans.
- **End-to-end proof a built package installs a WORKING hook:** the evaluator built a real archive to
  scratch, extracted it, ran `configure.py install` against a fake HOME, then executed the INSTALLED
  hook as Claude Code would — empty stdin → exit 0; real payload with missing transcript and
  unreachable receiver → exit 0. Uninstall returned settings to `{}`.
- **The CRLF pins are live, not textual**: dropping `deploy/*.py text eol=lf` fails a test that shells
  out to `git check-attr`. The pin also retroactively protects the pre-existing `claude-repo-tag.py`,
  which was exposed to the same CRLF-shebang failure.
- The evaluator hit the silent-no-op trap itself — two mutations reported "26 passed" because shell
  backslash-escaping made the anchor assertion fail, so the mutation was never applied. It **discarded
  those results and re-ran via a file-based mutator**, both then failing correctly. Recorded because
  this is now the ninth instance in this goal, and the first where the agent caught it unprompted.

**TASK 06b CLOSED — evaluator PASS 5/5.** With 06a, task 06 is complete.

Cumulative suite: **234 tests**.

---

## SECURITY ESCALATION — a live fleet billing token is committed to git

Surfaced by the 06b evaluator as an out-of-scope observation; **orchestrator-verified independently.**

`client-package.zip` — TRACKED in git — contains `billing-config.json` carrying a real 64-hex token
(prefix `b1b217`, NOT the `REPLACE_WITH_FLEET_BILLING_TOKEN` placeholder) and the endpoint
`http://20.83.107.157:4318`.

Present across three commits: `381a60c`, `2cf0e9f`, `3738e86` — the earliest dated 2026-08-18, well
before this goal began.

This directly violates a hard constraint in `CLAUDE.md`: *"**Never commit a secret.**
`RECEIVER_AUTH_TOKEN`, `ANTHROPIC_ANALYTICS_TOKEN`, **the fleet billing token**, and every
`AZURE_*`/`ADLS_*` value live in `.env` only."*

**Not caused by this goal and explicitly not gating task 06b:** the zip predates the work, 06b was
forbidden to regenerate it, and the evaluator proved all seven files 06b owns are secret-free.

**Deliberately NOT remediated by the orchestrator.** Rotating a credential and rewriting git history
are consequential, outward-facing actions that belong to the user. Escalated for decision.

## 2026-09-09 — Phase 4 — Task 07 (integration + closer), cycle 1

- **Agent:** test-writer · **Model:** claude-sonnet-5 (light tier, agent-pinned; effort medium)
- **Routing reason:** the goal's final task and its designated CLOSER — the rung-3 full-suite run is a
  written mandate here, not an inherited default. It is also the only task that tests whether the seams
  BETWEEN tasks meet; every prior task verified its own seam in isolation.
- **Task writes fence:** `tests/test_export.py`, `tests/test_integration_desktop.py`,
  `tests/COVERAGE_MAP.md`
- **`owner: test-writer`** per the ownership contract — the first test-writer spawn since task 00.
- **Requirements routed into this task across the goal, now all present in its file:**
  1. `_FIRST` fallback discrimination (from task 04's evaluation — `_AS_OF` is now covered, `_FIRST` is
     not; neutering it still leaves all 12 attribute tests green)
  2. The systemic-failure alarm on 100% `store_error:` rejections (from task 03's evaluation)
  3. The `transcript_key` does-not-strip contract note (from task 01's hardening)
  4. **NEW, added now:** the `_mark_resolved` cross-task key seam (from task 06a's evaluation). The hook
     groups by `(sessionId, requestId, message.id)` but resolves by `request_id` alone, while task 02
     dedupes by `(session_id, request_id)`. Two groups sharing a `requestId` would lose the second
     group's tokens permanently with a cheerful 200. Measured 0 occurrences across 314 real request
     groups — latent, not active — but precisely the class of defect no single task's tests can reach.
     Task 07 is instructed to seed it, assert what happens, and REPORT rather than fix: the fix belongs
     to whichever key must change, which is an orchestrator routing decision.
- **Environment correction passed into the context package:** the task file says to use `uv`, but `uv`
  is NOT installed on this machine (confirmed by two evaluators). `pytest 9.1.1` is present; the worker
  is told to run `python -m pytest` directly and install nothing.
- **context_chars:** 8360

### Return — Task 07 cycle 1

- **report_chars:** 7900 · **est_tokens:** (8360 + 7900) / 4 = **4065** (estimate)
- **Closer run: `python -m pytest -q` → 253 passed, TWICE consecutively** (234 + 19 new). No manual
  cleanup between runs, so no cross-test state leakage. Fence held — three new test files, no
  production file and no task 00-06 test file touched.
- All four routed requirements implemented, including the `_FIRST` discrimination via a monkeypatched
  `attribute._FIRST` (proving the acceptance condition without hand-editing an out-of-fence file).
- End-to-end asserts the EXACT billed dollar figure, computed independently from `RatingService`, and
  pins all three negatives: not the naive block sum, not the first-block value, not the main-file-only
  total.
- `COVERAGE_MAP.md`: every criterion across tasks 00-07 mapped, **2 explicit GAPs** (task 00 AC1
  bare-collection at scaffold time, and AC5 golden-baseline capture determinism — no automated
  re-capture-and-diff exists). Three mapped node ids spot-checked by running them.

**The task did exactly what a closer is for: it found two defects no single task's tests could reach,
and REPORTED both rather than fixing across a fence.**

**FINDING 1 — task 03 owns it. Orchestrator-verified, and worse than reported.**
`receiver.py:371`'s `store.commit()` sits OUTSIDE the `try/except Exception: rollback; raise` block that
ends at `:368`. The worker reproduced it with a closed database; the orchestrator found the realistic
trigger:

    s.commit = raises OperationalError("database is locked")
      -> RAISES uncaught, escapes do_POST's `except (ValueError, KeyError)` -> NO HTTP RESPONSE
      -> rows written but UNCOMMITTED: 1
      -> after a LATER request's commit(): 1   <- committed as a side effect

That is the **orphan-commit-by-side-effect defect task 03's rollback was added to close**, still open
for a failure AT the commit itself. `database is locked` and `disk I/O error` are ordinary conditions
on a single-host SQLite deployment, not exotic ones. The rollback guards the record loop but not the
final commit.

Money impact is contained — task 06's hook treats a no-response as `transport_fail` and retries
forever, and `transcript_key` dedupes the replay — so nothing is lost or double-billed. The defect is
incoherent persisted state plus a dropped connection. **Routed back to task 03 as a fix cycle.**

**FINDING 2 — the cross-task key seam is REAL when triggered, and quantified.**
Seeded one session with two groups sharing a `requestId` but differing `message.id`: the hook ships
both, the server rejects the second as `duplicate_request_id`, and the loser's **3800 tokens /
$0.051412 billed** are permanently lost. A standalone retry does not even reach a rejection — the
loser's `transcript_key` collides with the winner's stored rows (the key composition excludes
`message.id` by task 01's frozen contract), so the store's replay guard absorbs it as 5 duplicates.

Latent, not active: **0 occurrences across 314 real request groups.** The fix requires changing a
FROZEN key consumed by multiple tasks — either the hook's grouping or the server's dedupe — which is
invasive this late. Escalated to the user as a decision rather than routed unilaterally.

## 2026-09-09 — Phase 4 — Task 03 fix cycle 2 (routed from task 07's closer)

- **Agent:** implementer (continued — task 03's owner) · **Model:** claude-sonnet-5
- **Rotation:** this is task 03's SECOND fix cycle; the rotation table calls for a different model line
  at cycle 2. Deliberately NOT rotated here: the fix is a two-line scope change to code this agent
  wrote and whose surrounding rationale it documented, the defect is precisely understood, and the
  rotation exists to break a model's blindness to its OWN class of mistake — which is not the failure
  mode here. Recorded as a deliberate deviation rather than an oversight.

### Return — Task 03 fix cycle 2

- **Orchestrator verification, executed:** `store.commit()` moved inside the guarded region.

      commit() raises OperationalError("database is locked")
        -> still raises (fails loudly, as designed — an outage must not become a 200)
        -> outside connection sees: 0 rows            (rolled back)
        -> after a later unrelated request: {'sess-later'} only   (no orphan)

  The orphan-commit-by-side-effect path is now closed for a commit-time failure as well as a
  loop-time one. `commit()` is still called exactly once per request; the `_RECORD_DATA_ERRORS`
  boundary and the `OperationalError` exclusion are untouched.
- The worker's RED proof is the right shape: reverting the fix made the new test fail with
  `{'sess-desktop-a','sess-desktop-commit-fail'} == {'sess-desktop-commit-fail'}` — the failed
  request's session leaking into a later request's commit, i.e. the defect itself.
- Suite **254 passed**.

### TWO EVALUATIONS OUTSTANDING — recorded so neither is lost

1. **Task 07 has never been evaluated.** It completed, its closer ran green, and its findings were
   routed — but no evaluator has returned a verdict on it. Under the Phase 4 invariant it is NOT
   complete.
2. **Task 03's PASS is stale.** It passed at 4/5, then received a fix routed from task 07. The
   invariant is explicit: *"Fixes without re-evaluate are forbidden."* Its verdict was issued against
   a version of `receiver.py` that no longer exists.

Both are being dispatched now rather than deferred. The orchestrator's own verification of the task 03
fix is evidence, not a verdict — the distinction the whole architecture rests on.

### Return — Task 03 re-evaluation (cycle 3): **PASS (5/5)**

- 16 send-loop mutations, **all 16 killed**, every anchor re-cut for the new structure with the harness
  hard-exiting on any non-applying mutation. **C8 — the naive index derivation, its lone survivor last
  cycle — is now dead**, killed by the interleaving test it had recommended as a non-blocking follow-up.
- Commit-path rollback reproduced through a separate connection, with a previously-committed request in
  place first so the blast radius is observable:

      prior committed request -> outside sees 1 row
      commit() raises OperationalError -> RAISED/NO-RESPONSE (fails loudly, correct)
        outside sees 1 row, sessions ['sPRIOR']   -> PRIOR COMMITTED ROWS SURVIVED
      later unrelated request -> outside sessions ['sLATER','sPRIOR']  -> NO ORPHAN

  Both halves closed, and the rollback still cannot reach past the current request.
- **A COMPLETENESS CHECK, which is the part worth recording.** Rather than re-testing the guard, the
  evaluator walked EVERY statement in `ingest_transcript_usage_payload` and classified each by whether
  it can write rows — establishing that only the loop and the commit can, and both are now guarded.
  Its own assessment: *"I verified the guard did what it claimed, not that the guard covered everything
  it needed to."* That is the difference between the cycle-1 audit that passed this defect and the
  cycle-3 audit that would have caught it.
- All prior properties re-confirmed: `commit()` exactly once (including on a mixed batch with per-record
  rejections), `OperationalError` and `DatabaseError` still propagate, all four wrong-typed field cases
  still contained with correct indices and distinct reasons, envelope 400 unchanged.

**TASK 03 CLOSED (again) — PASS 5/5 on the current version of the file.**

### Task 07 evaluation — relaunching after an interrupted spawn

The first dispatch of task 07's evaluation was interrupted before it ran. No verdict was produced and
none is implied. Relaunching; task 07 remains INCOMPLETE until an evaluator returns one.

### Return — Task 07 evaluation cycle 1: **PASS (4/5)**, and hardening

- **19/19 new tests killed by at least one mutation — ZERO vacuous tests.** Task 07 joins 06b as one of
  only two tasks in this goal without the signature defect.
- The three billing negatives were proven by mutating REAL PRODUCTION SOURCE, not by inspection:
  `max`→`min` in the hook's terminal-block selector → RED; hook discovery excluding `subagents/` → RED;
  a 0.09% drift in `bill.py` → RED. Those are the 8.6% under-bill, the ~30% subagent gap, and the
  2.28x over-bill respectively.
- `_FIRST` discrimination confirmed against the ACTUAL `attribute.py` (md5 `b1f3bfc9…` → `442b07db…`),
  not through the test's monkeypatch. The key-seam loss independently re-derived at $0.051412 —
  matching the test's emitted line byte-for-byte.
- **COVERAGE_MAP holds up:** all 144 referenced test names resolve against the 254-test suite, 8 node
  ids spot-checked by running them, both GAPs judged legitimate, and no overstated mapping found —
  where coverage is indirect the map says so explicitly.
- **Resolution limit recorded:** a 0.04% over-bill passes undetected, because `bill.py` prints 4
  decimals on a $0.127 total. Adequate for the three named historical errors (the smallest, the naive
  sum, is 0.0886%) but thin — 1.32x margin on that negative.
- Hardening applied: the tautological `assert lost_billed == lost_raw_cost * MARKUP` replaced with a
  literal `pytest.approx(0.051412, abs=1e-6)`; two docstrings corrected to describe `receiver.py` AFTER
  the task-03 commit fix; the stale `253 passed` count updated; unused imports dropped. The worker's
  RED proof was careful — its first mutation was caught by a DIFFERENT assertion, so it re-mutated
  holding the token sum fixed at 3800 to isolate the dollar assertion specifically.

**TASK 07 CLOSED — PASS 4/5. All eight tasks now hold evaluator verdicts.**

### NEW FINDING — a flaky test in a task-06a-owned file

Surfaced incidentally in task 07's hardening report ("failed once, then passed in isolation and on
every subsequent run"), and the orchestrator chased it rather than accepting it as noise.

**Reproduced: 1 failure in 15 isolated runs of
`test_transcript_hook.py::test_ac7_growing_batch_poison_record_eventually_drops_others_still_ship`.**
A further 40 runs produced none, putting the rate near 1-in-55 (~2%). Six consecutive full-suite runs
were all green.

It fails **in isolation**, so this is NOT cross-test state leakage — it is non-determinism inside the
test itself. The file already carries a `_soon()` helper (a deliberate 2-second forward clock buffer)
written by 06a's worker precisely for mtime-resolution hazards, and this test uses it — so the obvious
cause is already mitigated and the real one is something else.

Why it matters more than a typical flake: this is the regression test for the **poison-batch drop
bound** — the fix for a defect that previously stalled billing forever on an active machine. A test
that fails ~2% of the time in CI invites exactly one response: weakening it until it stops. The
production code is not implicated; the suite is green.

Routed to 06a's owner. Not blocking Phase 5's audit of production correctness, but it should not ship
as-is.

### Return — Task 06a flake investigation: root cause was PRODUCTION, not the test

The flake the orchestrator chased down to ~1-in-55 was diagnosed correctly and turned out not to be a
test artifact at all.

**Captured failure**, via an isolation script bypassing pytest overhead plus instrumentation on
`_save_state`:

    DEBUG SAVE_STATE OSError: PermissionError(13, 'Access is denied')

**Mechanism:** `_save_state`'s `tmp.replace(state_path)` can transiently raise `PermissionError` on
Windows when another process — almost certainly real-time antivirus — briefly holds the freshly-written
temp file at the exact moment of rename. The existing `except OSError: pass` is CORRECT under the
hook's never-fatal rule and must stay. But it meant an occasional legitimate save silently cost one
increment: the poison record's attempt count reached 5 instead of 6, never crossed
`MAX_ENVELOPE_RETRIES`, and never dropped.

Only a test asserting an exact attempt count could ever have observed this. In production it would
present as the drop bound occasionally taking an extra run — or, under sustained interference, not
firing when expected.

**Fix:** `_replace_with_retry()` — 5 attempts, 20ms apart, retrying `PermissionError` only on the
rename step. On exhaustion the exception still reaches `_save_state`'s `except OSError: pass`, so
always-exit-0 and the "worst case: work is redone next run" tolerance are unchanged. Worst-case added
latency ~80ms against a 2s network timeout.

**Proof, exactly as demanded:**
- **150/150** clean fully-isolated pytest invocations of the originally-flaky test
- **300/300** clean direct-call repro trials at the timing shape that reproduced it
- **Still RED under the correctness mutation** — reinstating the whole-batch-hash retry keying fails
  the test identically to before. The reliability fix does NOT mask the assertion it exists for.

That last check is why the instruction insisted on both halves: a flake "fixed" by loosening an
assertion passes the first and fails the second.

Three direct unit tests were added pinning the mechanism itself (transient recovery, exhaustion still
raising, and `_save_state` still never raising) rather than merely asserting the flake is gone.

### Consequence — the two-copy arrangement bit, exactly as predicted

Changing `deploy/claude-transcript-usage.py` put it out of sync with 06b's checked-in copy, so
`test_configure.py::test_transcript_hook_copies_are_equal_after_newline_normalization` fails and the
**suite is RED: 1 failed, 256 passed.**

Orchestrator-verified divergence — 3 hunks, and only 3:

    deploy/         33119 bytes
    client-package/ 31825 bytes
    equal after newline normalization: False
    (import time · the _replace_with_retry helper + docstring · the call site)

That the diff is exactly the fix confirms the copies were in sync beforehand. 06a's owner correctly
declined to touch `client-package/*` and reported it instead — the fence discipline working as intended.

This is precisely the risk recorded when 06a's stale header was corrected BEFORE 06b copied it. The
copy-equality test caught it immediately, which is the mechanism working — but it only fires after
someone edits `deploy/`. Re-sync routed to 06b's owner, with a note to record (not implement) the
follow-up idea that `build.py` copying from `deploy/` at build time would make the divergence
structurally impossible.

### Return — Task 06b re-sync

- **Orchestrator-verified:** both copies now 33119 bytes and normalized-equal. `VERSION` bumped
  1.2.0 → 1.2.1, with reasoning recorded: `ADMIN.md`'s convention is "bump when you change anything
  here", the shipped hook's BEHAVIOR changed (a real Windows AV-interaction fix, not packaging), and
  patch-level fits a reliability fix to an already-shipped hook where 1.1.0→1.2.0 already carried the
  feature-level change.
- **Suite 257 passed, no deselections, no filters.**
- **The flake is closed: 0 failures in 20 isolated runs** of the previously-flaky test (was 1 in 15).
- 06b's owner agreed with the follow-up observation and recorded it rather than implementing it:
  having `build.py` read `../deploy/claude-transcript-usage.py` at build time instead of shipping a
  checked-in duplicate would make this class of divergence structurally impossible and remove the
  recurring re-sync obligation. Correctly deferred as a design change beyond the current fix.

---

# PHASE 4 COMPLETE

All eight tasks hold evaluator PASS verdicts:

| Task | Verdict | Fix cycles |
|---|---|---|
| 00 test scaffold | PASS 4/5 | 1 + hardening |
| 01 store schema | PASS 4/5 | 1 + hardening |
| 02 transcript payload | PASS 5/5 | 3 (model rotation at 2 and 3) |
| 03 receiver endpoint | PASS 5/5 | 2 + hardening (2nd routed from task 07) |
| 04 attribution | PASS 4/5 | 1 + hardening |
| 05 billing basis | PASS 4/5 | 1 + hardening |
| 06a client hook | PASS 4/5 | 2 + hardening + flake fix |
| 06b rollout | PASS 5/5 | re-sync only |
| 07 integration + closer | PASS 4/5 | hardening |

**257 tests.** Golden baseline `9bc05192e963db53…` byte-identical throughout — the pre-change record of
`bill.py`'s behavior survived every one of the eight tasks.

## 2026-09-09 — Phase 5 — Final audit, cycle 1

- **Agent:** evaluator · **Model:** claude-opus-5 (frontier tier, effort high)
- **Routing reason:** mandatory Phase 5 gate. Every task passed its OWN criteria; this audit asks the
  different question — does the assembled whole satisfy the GOAL's success criteria, and is there
  anything true of the system that was not true of any task in isolation?
- **Task writes fence:** NONE — audit only
- **INVARIANT:** the only exit to Quality Checks is an APPROVED verdict.

### Return — Phase 5 Final Audit: **APPROVED (4/5)**

- **report_chars:** 17800 · **est_tokens:** (7240 + 17800) / 4 = **6260** (estimate)
- **All 18 goal success criteria MET**, each with executed evidence and — repeatedly — a POSITIVE
  CONTROL proving the check could fail. The auditor confirmed the privacy marker DOES appear via
  `/v1/metrics` before concluding it was absent from the transcript endpoint's log; confirmed adding one
  transcript row DOES change the golden sha before concluding the baseline matched; confirmed its
  harness reports a nonzero exit before concluding the hooks exit 0.
- **Money verified from a scenario it built itself**, not task 07's fixtures: expected $0.106875
  hand-computed from the rate card, `bill.py` reported **$0.1069**. The three historical errors excluded
  NUMERICALLY — naive sum would be 1.73x, first-block 0.475x, main-only a 63.8% gap.
- **Existing fleet untouched:** golden baseline regenerated from scratch, sha256 `9bc05192e963db53…`
  identical; a legacy-schema DB migrated in place with every row byte-preserved.

**A NEW EMERGENT DEFECT — Seam C, owned by no task.**

If `~/.claude/billing-hook-state.json` is destroyed — reimage, a cleared `~/.claude`, a manual delete —
`install_ts` resets to NOW and every still-unshipped request older than that instant is marked resolved
and permanently unbilled. **Reproduced at 1.8M billable tokens dropped, `drops == []`, nothing logged.**

Reachability is limited (`configure.py uninstall` does NOT delete the state file, so a normal
uninstall→reinstall preserves the watermark), and the loss follows from the goal's own explicit
forward-only decision — with no state, the hook genuinely cannot distinguish "lost yesterday" from
"never installed". What makes it SILENT rather than merely conservative is that `run()` logs nothing at
all when it initialises a new watermark.

Rated `[major, follow-up]`, not blocking. Cheapest mitigation is one line: `_append_log` when
`install_ts` is initialised, so the event is at least detectable on the machine.

**Two further seams found, both correctly attributed:**
- **Seam D** — `bill.py` resolves repo through `attribute.resolved_view()` while `invoice.py:gather()`
  groups on the RAW stored `repo` column. Measured $4.50 billed vs $0.00 invoiced on one store. The
  auditor PROVED this pre-existing by reproducing it with a pure OTLP row and no transcript data
  anywhere — so it is not this goal's defect, though desktop makes it slightly more reachable.
- **Seam E** — a sidechain file is never the `transcript_path` hint, so its trailing group waits for the
  30s idle threshold and a later hook run. Subagent usage (~a third of spend) is systematically one
  session behind. Bounded, never lost; invoice periods key on request `ts`, not ingest time.

**The auditor measured Seam A/B incidence itself rather than accepting the goal's figure: 0 occurrences
across 2014 request groups — 6.4x the 314 the goal cites, still at zero.**

Seams probed and found clean: `attribute.py`'s CASE vs `export.py`; the two hook copies vs `build.py`
CONTENTS; the receiver's guarded `commit()`; `normalize.py` bypass on all three write paths; other
table consumers.

**Required Fixes: NONE.** No criterion unmet, no wrong money, no privacy or consent breach, no broken
existing-fleet path, no constraint violated. Out of Scope respected in both directions.

**INVARIANT SATISFIED — the only exit to Quality Checks is an APPROVED verdict, and this is one.**

## 2026-09-09 — Phase 5 — Quality Checks (ladder rung 3)

- **Agent:** terminal · **Model:** claude-sonnet-5 (light tier)
- **Routing reason:** rung 3 is executed by SPAWNING `terminal`, never by the orchestrator running it in
  session — the raw stream stays out of the orchestrator's context. Per `ORCHESTRATION.md`'s Quality
  Checks table, the full suite is the only configured cycle-end command; no lint or type-check tool is
  configured in this project, so none is invented.

### Return — Phase 5 Quality Checks

    run 1: 257 passed in 26.37s
    run 2: 257 passed in 24.36s
    exit code: 0
    working tree: CLEAN (no data/, no invoices/, no stray artifacts)

Run via a `terminal` spawn, not in the orchestrator's session — the raw stream never entered the
orchestrator's context, which is the point of the light-tier command runner.

# PHASE 5 COMPLETE — audit APPROVED, Quality Checks green

Per `goal.md`'s `phases:` block — `align_docs: true`, `pull_request: false` — Phase 6 runs next and
Phase 7 is skipped by the user's Phase 1 decision.

### Open items carried out of Phase 5, none blocking

1. **Seam C mitigation (recommended).** One `_append_log` line when `install_ts` is initialised, making
   a watermark reset detectable rather than silent. Closes the only path found that can drop 1.8M
   tokens with no record. In 06a's fence. NOT applied — the audit is APPROVED, and changing code after
   an APPROVED verdict reopens the gate. Offered to the user as a scoped follow-up.
2. **The cross-task key seam.** Auditor recommendation: do not block, do not fix now. It measured
   incidence itself at 0 in 2014 request groups, and the fix would change a key four completed tasks
   consume and `otel_store.py` documents as deliberately frozen — a real regression surface traded
   against a loss the data says has never occurred. The recorded decision plus the seeded regression
   test is the right resting state.
3. **The committed fleet token in `client-package.zip`** — predates this goal, independent of it,
   escalated to the user separately.
4. **`bill.py` vs `invoice.py` repo-attribution divergence (Seam D)** — proven PRE-EXISTING by
   reproduction on a pure OTLP row. Not this goal's defect; desktop makes it marginally more reachable.
   Follow-up candidate.
5. **`COVERAGE_MAP.md` records "254 passed"; the suite is now 257.** Stale count in a document meant to
   be checkable without rerunning. Trivial, in task 07's fence.

---

# PHASE 6 — Align docs

## 2026-09-09 — Phase 6.0-6.2 — surface discovery and edit plan (orchestrator)

**6.0 Preconditions:** goal `desktop-usage-capture`; implementation confirmed landed —
`git status` shows 10 modified/new files across `billing/otel/`, `deploy/`, `client-package/`.

**6.1 What shipped (each fact with its source):**

1. `POST /v1/transcript-usage` — new authenticated batched endpoint (`receiver.py`)
2. `billing/otel/transcript.py` — new module: 14-field wire contract, per-record validation,
   `MAX_BATCH_SIZE=500`, terminal-block mapping, rate-card costing
3. Four new columns (`otel_store.py`): `token_usage.usage_source`/`.entrypoint`,
   `cost_usage.usage_source`/`.cost_source`; plus `transcript_key()` and a guarded idempotent migration
4. `desktop-scratch` — a FIFTH `attribution_source` value (`attribute.py`)
5. `bill.py` — source-aware basis with three labels (ACTUAL / RATE-CARD / MIXED), conditional split
   lines, `desktop-scratch` in the attribution breakdown, the double-billing overlap detector
6. `invoice.py` — actual-vs-estimated in the `.txt` and a new `estimated_cost_usd` column in
   `summary.csv` / `line_items.csv`
7. `deploy/claude-transcript-usage.py` — new standalone hook, registered on **SessionEnd only**
8. `client-package/` — ships a second hook; `configure.py` per-hook event map; `build.py` CONTENTS;
   VERSION 1.1.0 → 1.2.1
9. `.gitattributes` — `tests/golden/** -text`, `deploy/*.py text eol=lf`
10. `tests/` — 257 tests, the repo's first suite (`pytest` is the sole dev dependency)

**6.2 Edit list — 6 docs IN, 4 excluded with reasons:**

| Doc | Why IN |
|---|---|
| `README.md` | canonical; `:147` documents the fallback chain as 4 values (`timeline → wrapper → no_remote → absent`) — `desktop-scratch` missing; module list, endpoint list, dependency claim |
| `deploy/README.md` | 6 `claude-repo-tag` hits, 3 endpoint hits; the new hook and its SessionEnd-only registration are undocumented |
| `client-package/ADMIN.md` | file table lists only `claude-repo-tag.py`; says "currently `1.1.0`" — VERSION is **1.2.1** |
| `client-package/INSTRUCTIONS.md` | lists one hook; needs the second |
| `.claude/ORCHESTRATION.md` | `:416` lists only `/v1/metrics` and `/v1/session-repo`; `:821`'s auto-fail trigger names `claude-repo-tag.py` alone though two hooks now share the exit-0 rule |
| `tests/COVERAGE_MAP.md` | `:132` records "254 passed" — the suite is **257** |

**Excluded, each with a reason rather than silence:**
- `fabric/README.md` — its `actual_cost_usd` is the LAKE schema from `export.py`, which this goal
  deliberately did not change (no `cost_source` column, pinned by a test). No stale claim.
- `CLAUDE.md` — its dependency claim ("Runtime is standard-library only… `pytest` under `tests/` is the
  single permitted dev dependency") is already exactly right.
- `tests/golden/README.md` — its `usage_source`/`attribution` mentions are DESCRIPTIVE of the goal's own
  tasks and still accurate.
- `pilot-package/INSTRUCTIONS.md` — superseded; explicitly Out of Scope in `goal.md`.

**A trap recorded for the executors:** `client-package/INSTRUCTIONS.md:76` says the hook does **not**
collect "your prompts, your code, file contents, or file paths." That claim is **STILL TRUE** — `cwd`
was deliberately dropped from the wire schema in task 02 precisely to keep it true. It must be
preserved VERBATIM, not "corrected" to mention the new hook's data.

**6 docs > 3, so Phase 6.3 runs as its own evaluator spawn — no small-change fold.**

## 2026-09-09 — Phase 6.3 — edit-plan evaluation

- **Agent:** evaluator · **Model:** claude-opus-5 (frontier tier)
- **Criteria:** coverage (every stale doc caught?), scope (zero excluded-path or code edits planned?),
  anti-invention (every planned edit cites its source file?)

### Return — Phase 6.3 cycle 1: NEEDS REVISION (3/5)

The plan had **zero false positives** — every doc listed was genuinely stale and every line number
exact — but it systematically missed sibling docs carrying IDENTICAL stale text, and two edit reasons
were framed in a way that would have produced wrong prose.

**Coverage misses — the plan caught one instance of two defect classes and missed every sibling:**

| Stale claim | Caught | Missed |
|---|---|---|
| Route list omits `/v1/transcript-usage` | `ORCHESTRATION.md:416` | `agents/qa-evaluator.md:42`, `skills/qa-criteria/SKILL.md:35`, `agents/test-writer.md:26` |
| Exit-0 rule names only `claude-repo-tag.py` | `ORCHESTRATION.md:821` | `agents/evaluator.md:91`, `skills/feature/SKILL.md:93` |

The qa-evaluator and qa-criteria misses matter beyond tidiness: those are the QA gate's checklists.
Leaving the new authenticated route off them means its 401 behavior never gets QA'd.

**Three "would make it worse" findings, all orchestrator-confirmed:**

1. **The `README.md:147` reason invited a WRONG edit.** Stating it as "`desktop-scratch` missing"
   invites appending. Verified actual precedence by executing `attribution_source()`:

       actual:  desktop-scratch -> timeline -> absent -> no_remote -> wrapper
       README:                     timeline -> wrapper -> no_remote -> absent

   The existing chain was ALREADY wrong — `wrapper` is last in code, second in the README. An append
   would have produced a still-incorrect doc. This needs a REORDER.

2. **`client-package/INSTRUCTIONS.md:77-78` — a true claim propped up by a now-false reason.** Line 76
   ("does not collect your prompts, your code, file contents, or file paths") stays true because `cwd`
   was dropped. But :77-78 justifies it with *"None of that is in Claude Code's telemetry, and this
   ships metrics only."* That is now FALSE for the desktop path: the hook walks
   `~/.claude/projects/**/*.jsonl`, files that DO contain prompts, code and paths, and deliberately
   extracts only usage metadata. Preserving :76 verbatim while leaving :77-78 untouched would leave the
   repo's one privacy-facing doc making a true promise for a reason that no longer holds. The honest
   version is a STRONGER assurance, not a weaker one.
   Also `:70-74`'s "what is collected" list omits `entrypoint`, `query_source`, `user_id`, `org_id`.

3. **`README.md:485` "Three artifacts, not two" and `:503` "All three together"** — now four. None of
   the plan's four README reasons covered the Phase 4 rollout section.

**Two exclusions overturned:**
- `fabric/README.md` — the plan's reason (schema unchanged) is true but misses that the column's
  SEMANTICS changed: desktop rows now carry rate-card ESTIMATES inside `actual_cost_usd`. `goal.md`
  itself calls this "the clearest known gap this goal leaves open." Adding the caveat is a doc edit.
- `tests/golden/README.md:45` — "Once task 04 **adds** a `usage_source` branch" is forward-tense about
  shipped work, exactly the stale marker Phase 6.2 says to grep for.

## 2026-09-09 — Phase 6.3 cycle 2 — revised edit plan

Edit list grows from 6 to **13 docs**. Every addition traces to a confirmed line-cited defect.

### Return — Phase 6.3 cycle 2: NEEDS REVISION (4/5)

All seven cycle-1 fixes discharged and line-accurate; the evaluator re-executed
`attribution_source("t")` itself and confirmed `['desktop-scratch','timeline','absent','no_remote',
'wrapper']` matches the revised target. Zero false positives again across 13 docs.

**Two coverage gaps remain, both orchestrator-confirmed:**

1. **`.claude/skills/test-ladder/SKILL.md` missing entirely — and it is the consequential one.**
   `:77` routes `deploy/**` and `client-package/**` changes to
   *"`tests/test_configure.py` if present; otherwise rung 2 is a no-op."*
   `tests/test_transcript_hook.py` now exists with **46 tests** and is the ONLY coverage of
   `deploy/claude-transcript-usage.py`'s always-exit-0 discipline. As written, an implementer changing
   that hook runs `test_configure.py` — which tests PACKAGING, not hook behavior — and skips every
   exit-0 assertion. **Exit-0 is an auto-fail trigger, and the routing doc routes around its tests.**
   Same defect class as the `evaluator.md:91` gap, one layer down.
   Also `:73` — the store-opening test list omits `test_integration_desktop.py`.

2. **`.claude/ORCHESTRATION.md:7`** — *"Two client-rollout tracks install **the same telemetry hook**"*
   — singular, now false; both tracks install two. The doc was on the list but this line was not cited,
   so an executor working the stated reasons would fix `:416` and `:821` and leave the opening summary
   wrong.

3. **`fabric/README.md` caveat under-scoped.** Telling a Fabric consumer that `actual_cost_usd` may
   contain estimates, without telling them **no column distinguishes which rows**, sends an analyst
   hunting for a discriminator that does not exist. The caveat needs all three parts: desktop rows carry
   rate-card estimates; nothing separates them from Anthropic actuals; this is a deliberate deferral.

**Ruling on the privacy framing — name the files.** The evaluator endorsed the orchestrator's instinct
with three reasons worth recording: the claim becomes VERIFIABLE (those files are on the developer's own
disk, so they can check rather than trust); the assurance genuinely STRENGTHENS (from a claim about the
pipe — "not in the telemetry" — to a claim about a privileged reader choosing to send less); and
concealment is the worse failure mode (a developer who opts in on "ships metrics only" and later
discovers the hook reads their transcripts experiences that as having been misled). It also matches the
doc's established voice — `:80-81` already says "raise it before installing rather than after."

Three constraints recorded for the executor: frame it as a SCOPE statement, not a reassurance; bound the
claim to `PAYLOAD_FIELDS` (`transcript.py:113-128`); and never imply it reads credentials — identity
comes from `~/.claude.json`, and `:79` explicitly says **NEVER** `.credentials.json`.

**Watch item:** `:76` is a SENTENCE-level freeze, not paragraph-level — `:77-78` are adjacent lines in
the same paragraph, and the executor must neither rewrite the whole paragraph nor refuse to touch it.

## 2026-09-09 — Phase 6.3 cycle 3 (final) — edit list now 14 docs

### Return — Phase 6.3 cycle 3: **PASS (5/5)**

**The evaluator changed its METHOD, and that is why this cycle was clean.** Cycles 1-2 were
pattern-driven — grep per shipped fact, report what the pattern caught. That finds real gaps but its
completeness is bounded by the choice of patterns, which is exactly why it yielded twice. Cycle 3
inverted it: enumerate EVERY in-scope markdown file, compute hits against a single union pattern
covering all ten shipped facts, then require every file with a nonzero count to be individually
accounted for.

    38 files with hits
      14  on the edit list          (all fourteen confirmed to have hits)
       2  confirmed exclusions      (CLAUDE.md, pilot-package/INSTRUCTIONS.md)
      15  vendored kit              (.claude/skills/setup/** — zero project-specific hits)
       7  examined and cleared this cycle
      --
      38  accounting closes exactly

**Its diagnosis of why the first two sweeps yielded is the lasting lesson:** `.claude/**` carries
MIRRORED enumerations — the receiver route list appears in four files, the always-exit-0 rule in three,
test routing in two. A pattern sweep surfaces whichever mirror the pattern happens to hit; a
file-complete sweep surfaces all of them or none.

**Two things it declined to take, both correctly:**
- Two PRE-EXISTING template defects (`implementer.md:22`'s duplicated substitution,
  `align-docs/SKILL.md:36-41`'s duplicated paragraph) — setup-emitter artifacts predating this goal, not
  shipped-fact staleness. Folding them in would be scope creep and would muddy 6.5's "only these 14
  docs changed" check.
- An improvement to `align-docs/SKILL.md:59`'s own surface map (this goal proved `tests/**` changes
  reach three more docs than it lists) — declining to self-modify the skill governing the phase
  currently executing.

**Noted for the 6.5 audit:** `tests/COVERAGE_MAP.md` and `tests/golden/README.md` are currently
UNTRACKED, so they will appear as additions rather than modifications. Expected, not a scope violation.

Across three cycles and 14 docs: **zero false positives**. Every doc placed on the list was genuinely
stale and every line number exact.

## 2026-09-09 — Phase 6.4 — execute per doc (4 parallel implementers, disjoint fences)

| Spawn | Docs | Why grouped |
|---|---|---|
| A | `README.md`, `deploy/README.md` | the two largest narrative surfaces; both carry the rollout story |
| B | `client-package/INSTRUCTIONS.md`, `client-package/ADMIN.md` | same package; B carries the hardest edit in the set (the privacy rationale) |
| C | the seven `.claude/**` mirrors | mechanical — the same two stale claims repeated across files |
| D | `fabric/README.md`, `tests/COVERAGE_MAP.md`, `tests/golden/README.md` | three small, unrelated single-point corrections |

Fences are disjoint by construction; docs are independent, so these run concurrently.

### Return — Phase 6.4: all four spawns complete, 14 docs edited

**Spawn A — `README.md`, `deploy/README.md`.** Precedence reordered to
`desktop-scratch → timeline → absent → no_remote → wrapper`, confirmed by the executor against
`attribute.py:87-94` rather than taken on the orchestrator's word. It also made a call worth recording:
rather than renumber `deploy/README.md`'s §4 onward, it inserted the new hook as **§3a**, because §4 is
cross-referenced by name from three other sections — renumbering would have silently broken those
pointers. And it left the `CLAUDE_BILLING_TOKEN` row alone, reasoning the existing wording is still
accurate with the transcript hook documented separately. Scope discipline, not omission.

**Spawn B — `client-package/INSTRUCTIONS.md`, `ADMIN.md`. The best work in this pass, and it caught an
ORCHESTRATOR ERROR.** The context package asserted "`:79` already says NEVER `.credentials.json`". The
executor grepped, found **no such line anywhere in the file**, and flagged it rather than inventing text
to match. Orchestrator-confirmed against `git show HEAD:client-package/INSTRUCTIONS.md` — the claim was
mis-attributed from the HOOK's docstring. The anti-invention guardrail working against the person who
wrote it.

The frozen sentence survived verbatim (now `:80`). The replacement satisfies all four constraints and
ends on the line that matters: *"Because the files are on your own disk, you can check this claim
yourself rather than take it on trust."* The old text asked developers to trust a claim about a pipe;
the new one hands them something verifiable. The identity bullet threads the hardest needle —
*"the identifiers your Claude account profile already carries, not anything read off your machine's
credentials"* — accurate, and forecloses the misreading without implying the file is touched.

**Spawn C — the seven `.claude/**` mirrors.** All three route-list sites and all three exit-0 sites
generalized; `ORCHESTRATION.md:7` corrected to two hooks with `:6` deliberately left alone; the
consequential `test-ladder:77` row now routes `deploy/**` to BOTH `test_transcript_hook.py` and
`test_configure.py` with the "rung 2 is a no-op" escape removed. **It also corrected a second
orchestrator error:** the brief said the hook file has 46 tests; the real count is **49**
(orchestrator-confirmed via `--collect-only`) — the flake fix added three after the figure was recorded.
It declined to write either number into the doc, sidestepping the staleness entirely.

**Spawn D — `fabric/README.md`, `COVERAGE_MAP.md`, `golden/README.md`.** The three-part caveat landed;
its central claim is orchestrator-verified TRUE — neither `SUMMARY_FIELDS` nor `LINE_FIELDS` in
`export.py` contains any `source`/`estimate` discriminator. Count corrected to 257 by running the suite.
Tense fixes applied, and it correctly distinguished forward-tense-about-unshipped-work from timeless
conditionals ("would" in a hypothetical), leaving the latter verbatim.

**Two orchestrator verification errors, both self-inflicted, both caught:** a `grep` for "no column in"
returned 0 because the phrase wraps across lines in the source — the caveat had landed; and the stale
46-vs-49 test count. Recorded because the running theme of this goal is that a check which silently does
nothing is indistinguishable from one that passes.

**Scope boundary for the 6.5 audit, captured by mtime:**

    all 14 Phase 6 docs:   2026-09-09 18:24:27 - 18:28:17
    newest non-doc file:   2026-09-09 17:19:31  (client-package/VERSION, from task 06b)

Over an hour of separation. Nothing non-markdown moved in Phase 6's window. This matters because
Phase 4's code changes and the kit install are still uncommitted in the same working tree, so
`git status` alone cannot separate them — mtime can.

## 2026-09-09 — Phase 6.5 — final doc audit

- **Agent:** evaluator (continued — carries all three 6.3 cycles and the file-complete sweep method)
- **Model:** claude-opus-5 (frontier tier)
- **INVARIANT:** the doc set ships only on APPROVED.

### Return — Phase 6.5 cycle 1: ISSUES FOUND (3/5)

Most of the set verified excellent — the route list agrees across all five files, the exit-0 rule across
all four, the precedence reorder is correct with its rationale, `deploy/README.md` §3a holds with no
broken cross-reference, and the frozen sentence survived verbatim. **Three blockers, all NEWLY
INTRODUCED by the pass itself** — none existed before 18:24.

**1. `README.md:7-11` — an INVENTED claim in the ground-truth doc.** It asserted "this project uses
`uv`, not `pip`". Verified: `uv` NOT installed, and no `pyproject.toml`, `uv.lock`, `requirements.txt`,
`setup.py` or `.python-version` anywhere. A developer following the README would get "command not
found."
**This one traces to the orchestrator.** The user's instruction to switch from `pip` to `uv` was correct
for `.claude/ORCHESTRATION.md`, which is orchestration-kit TOOLING guidance — and the orchestrator's
brief carried it into `README.md`, which is a PROJECT FACT doc. Promoting a tooling preference into
ground truth is an anti-invention violation, and the executor was set up for it.
Fixed: the runtime-vs-`pytest` distinction is preserved, no package manager is named, and the stated
command (`python -m pytest`) actually works. The `uv` preference remains recorded at
`ORCHESTRATION.md:782`, where it belongs.

**2. `.claude/skills/test-ladder/SKILL.md` — ACCURATE PROSE DESTROYED.** The pass deleted a "Command
forms" block containing three worked invocations. The auditor grepped: gone, not relocated. Nothing
shipped made them stale, and `implementer.md:31-33` sends implementers to that exact block.
This is the documentation analogue of this goal's signature defect: **every individual edit was
correct, the resulting file still read fine, and something was silently lost.** Invisible to a reader;
only a diff against the prior state surfaced it. Restored verbatim, with the `:73`/`:77` edits intact.

**3. `client-package/INSTRUCTIONS.md` — an inaccurate claim in the consent text.** It told developers
the receiver records "the **entrypoint** the session ran from (CLI, VS Code, or the desktop app)."
Verified false: `receiver.py` contains **zero** occurrences of `entrypoint` (the OTLP path never sets
it), `ALLOWED_ENTRYPOINT = "claude-desktop"` is the only accepted value, and the schema comment marks
the column "(transcript rows only)". The only value ever stored is `claude-desktop`.
The error ran toward OVER-disclosure — the safer direction — but this is the text people consent
against and must be accurate in both directions. The executor dropped the CLI/VS Code framing entirely
rather than keep a value that is never stored, and took both non-blocking refinements.

### Return — Phase 6.5 remediation: all three fixed, plus one follow-up

- **`test_asof` in the restored block did not resolve** (`no tests ran`). Spawn C restored it verbatim
  as instructed and FLAGGED it rather than silently changing it — the right instinct. But the situation
  changed underneath: before this goal `tests/` did not exist at all, so the whole block was
  hypothetical. Now two of its three examples are real and one was not, making it newly
  copy-pasteable into a failure. Replaced with a node verified to resolve (`1 passed`).
- **Orchestrator verification of the corrected set:** all three command forms resolve; zero `uv` claims
  in `README.md`; zero CLI/VS Code overclaim in `INSTRUCTIONS.md`; the Command forms block is present;
  the frozen sentence is byte-identical to the committed original after TWO rounds of edits; nothing
  non-markdown modified after 18:24; suite **257 passed**.

## 2026-09-09 — Phase 6.5 cycle 2 — final doc audit (re-run on the corrected set)

### Return — Phase 6.5 cycle 2: **APPROVED (5/5)**

All three blockers fixed and verified BY EXECUTION rather than inspection:

- `README.md` — zero `uv` occurrences; the standing accuracy trap satisfied in both directions, neither
  half flattened; `python -m pytest` confirmed working.
- `test-ladder/SKILL.md` — diffed against the pre-edit state: the change set is **exactly three lines**
  (`:73`, `:77`, and the one command-form replacement). The heading, fence and both surrounding examples
  are back in position, byte-identical. **All three documented forms executed:** 12 passed / **1 passed**
  / 23 passed. Every form resolves.
- `INSTRUCTIONS.md` — the entrypoint bullet is accurate; both refinements taken; the paragraph reads
  cleanly end to end after two rounds, "no seams".

**Frozen sentence byte-identical after TWO rounds**, compared against `git show HEAD:` with `cat -A`
including line ending and trailing whitespace.

**No newly introduced issues** — all three re-edited files diffed in full. Second edits to
already-edited files were the exact shape that produced blocker 2, and this time they introduced nothing.

**Ruling on the `test_asof` scope question, with a distinguishing test worth keeping:**
the line is not "was this defect pre-existing" but **"did the shipped work change this content's truth
value or how it reads?"**
- `test_asof`: before this goal `tests/` did not exist, so the whole block was uniformly hypothetical and
  no reader could mistake any example for runnable. The goal created the test tree, making two of three
  genuinely executable and leaving the third as the lone trap in a block that now reads as
  copy-pasteable. **The shipped work ACTIVATED the defect.** In scope.
- The duplicated paragraphs: equally broken before and after; nothing shipped touched them. Excluded.

Same rule, opposite answers, because the inputs differ.

**The auditor's closing observation, which is the sharpest lesson of Phase 6:**

> "Both [brief errors] were resisted by executors rather than propagated... The `uv` error is the one
> that got through — and it got through because it arrived as an INSTRUCTION rather than as a FACT to
> verify, which is the harder shape to catch."

Executors caught the stale test count and the mis-attributed `.credentials.json` line because both were
checkable claims. The `uv` error passed because it was phrased as a directive about how the project
works. **An agent verifies facts; it obeys instructions.** Putting an unverified premise in the
imperative bypasses the anti-invention guardrail entirely.

**Suite green at approval time: 257 passed.**

---

# PHASE 6 COMPLETE — doc set APPROVED

14 documentation files aligned to shipped code. `git status` shows only markdown changed in Phase 6's
window; nothing non-markdown modified after 18:24.

Per `goal.md`'s `phases:` block — `align_docs: true`, `pull_request: false` — **Phase 7 is skipped by
the user's Phase 1 decision.**

# GOAL COMPLETE

    Phase 1  Alignment              user-confirmed
    Phase 2  Goal creation          8 tasks, 3 decision gates
    Phase 3  Goal evaluation        5 cycles (3 by budget, 2 user-authorized)
    Phase 4  Task execution         8 tasks, all evaluator-PASSED
    Phase 5  Final audit            APPROVED 4/5, all 18 success criteria MET
    Phase 6  Align docs             APPROVED 5/5, 14 docs
    Phase 7  Pull request           SKIPPED per goal.md

**257 tests.** Golden baseline `9bc05192e963db53…` byte-identical from task 00 through to close —
the pre-change record of `bill.py`'s behavior survived all eight tasks and the doc pass.
