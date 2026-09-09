# Task 06: Client hook + rollout on both enrolment tracks

## Objective

A new standalone hook `claude-transcript-usage.py` ships desktop usage metadata from local transcripts
to the receiver on `SessionEnd`, plus a watermarked catch-up sweep for sessions whose `SessionEnd` never
fired. It is wired into BOTH enrolment tracks end to end: the MDM-enforced `deploy/` track and the
opt-in `client-package/` track, including the packaging that track depends on.

## Dependencies

- 00 (fixtures), 02 (the wire payload contract and max batch size), 03 (the endpoint)

```yaml
# --- task ownership contract ---
writes:
  - deploy/claude-transcript-usage.py
  - deploy/managed-settings.json
  - client-package/claude-transcript-usage.py
  - client-package/configure.py
  - client-package/build.py
  - client-package/VERSION
  - .gitattributes
  - tests/test_transcript_hook.py
  - tests/test_configure.py
reads:
  - deploy/claude-repo-tag.py
  - client-package/claude-repo-tag.py
  - billing/otel/transcript.py
  - billing/otel/receiver.py
  - client-package/ADMIN.md
  - tests/conftest.py
depends_on:
  - "00-test-scaffold"
  - "02-transcript-payload"
  - "03-receiver-endpoint"
owner: implementer
rewrite_semantics: targeted-insertion   # per file: the two NEW hook copies are whole-file;
                                        # managed-settings.json, configure.py, build.py, VERSION
                                        # are targeted-insertion into existing content
eval_depth: full
```

## Requirements (exhaustive — the evaluator verifies every item)

**The hook script**

- [ ] Standalone and stdlib-only. It is copied to developer machines and CANNOT import from `billing/` —
      follow the `claude-repo-tag.py` precedent exactly.
- [ ] **Always exits 0**, on every path including every error path. A hook that fails must never break a
      developer's session. This is the single most important rule in the file.
- [ ] Reads the hook payload from stdin. **`transcript_path` is a PRIORITY HINT — which file to handle
      first — never the set of files to parse, and never a source of directory structure.**

- [ ] **Enumerates `~/.claude/projects/**/*.jsonl` RECURSIVELY from the projects root**, and keys
      per-file state by **absolute path**. Do not derive a directory from `transcript_path` and glob
      inside it; do not assume any particular nesting depth.

      This is a structural requirement, not a path correction, and the reason is recorded plainly:
      subagent usage lives in `agent-<agentId>.jsonl` files whose real location is
      `<project_dir>/<sessionId>/subagents/agent-<agentId>.jsonl` — one level deeper than a project
      directory. Measured on a real machine at Claude Code `2.1.259`: a recursive walk finds 9 files, a
      flat per-project-directory glob finds 4, missing all 5 sidechain files and **30.0% of total
      spend** ($13.78 of $45.87). An earlier draft of this very task specified the flat layout and was
      wrong. A recursive walk from the root is correct for the observed layout, for the flat layout, and
      for any future re-nesting — it removes the dependency on an undocumented directory shape rather
      than encoding today's shape more carefully.
- [ ] Sidechain rows carry the parent's `sessionId` and `entrypoint` and are flagged
      `isSidechain: true`; they appear NOWHERE in the main session transcript. Identify them by the
      `isSidechain` flag on the row, not by the filename, so a filename convention change cannot
      silently reclassify them as main usage.
- [ ] **Honors `CLAUDE_CONFIG_DIR`** when locating the projects root, defaulting to `~/.claude` when it
      is unset. This is an existing Claude Code environment variable; on a machine that sets it, a
      hard-coded `~/.claude/projects` walk finds zero files and desktop bills **zero, silently** — the
      exact failure class this goal exists to eliminate, reintroduced by a one-line assumption.
- [ ] **Records locally when a full-root sweep yields zero transcript files.** On a machine that has
      run Claude Code at all, zero files means the root is wrong, not that there is no usage. This
      converts the last remaining layout dependency's failure mode from silent-zero to visible, which
      is the single cheapest safeguard available given that every defect in this plan's five review
      cycles failed silently.
- [ ] Sidechain records ship with `query_source='subagent'`; main-transcript records ship with
      `query_source='main'`. `otel_store.py:31` already documents this exact enum
      (`main | subagent | auxiliary`), and `deploy/claude-repo-tag.py:85-87` already posts `agent_id`
      with a comment anticipating separate attribution.
- [ ] Subagent usage bills to the SAME repo as its parent session — the sidechain files carry the
      parent's `sessionId`, so `attribute.py`'s existing as-of join resolves it with no extra work and
      no schema change.
- [ ] Each file — main and each sidechain, at whatever depth — is its own per-file state unit keyed by
      absolute path, so a sidechain file that appears after its parent has been shipped is still picked
      up on a later run.
- [ ] **Emits one usage record per API REQUEST, not per assistant message.** This is the single most
      important correctness rule in the task. Group usage-bearing rows by
      `(sessionId, requestId, message.id)` and emit ONE record per group, using the **terminal block's**
      usage values. **The sole normative selector is: highest `apiBlockIndex`; tie-break by file order,
      last wins.** Where `apiBlockIndex` is absent on any row in a group, treat it as lower than every
      present value and fall back to file order — never let a comparison span `None` and `int`, which
      raises `TypeError` and, under the always-exit-0 rule, would silently discard the whole session.

      **Do NOT use `stop_reason` as the selector.** An earlier draft called it equivalent; it is not.
      Measured across 230 real request groups: 108 carry two or more non-null `stop_reason` rows, and 3
      carry none at all. It is multi-valued for 47% of groups and undefined for others.

      Why: rows sharing a `(requestId, message.id)` are cumulative streaming snapshots of one request.
      Measured on real transcripts, 402 usage-bearing rows carry only 187 distinct `requestId`s. Within
      a group, `input_tokens` / `cache_creation_input_tokens` / `cache_read_input_tokens` hold constant
      while `output_tokens` grows:

          apiBlockIndex=0  stop_reason=None      input=2  output=5    cache_creation=13984  cache_read=35774
          apiBlockIndex=1  stop_reason=tool_use  input=2  output=209  cache_creation=13984  cache_read=35774

      Emitting one record per message and letting the server sum them **over-bills by ~2.28x**
      ($64.38 against a correct $28.28 across this machine's transcripts, at the repo's placeholder
      rates). Emitting them and relying on the store's `INSERT OR IGNORE` to dedupe is equally wrong in
      the other direction: it keeps the FIRST insert, `apiBlockIndex=0`, discarding 34% of output
      tokens and **under-billing by ~8.6%**. Neither error raises anything; both produce a
      plausible-looking invoice. Collapse client-side, deliberately, and test the amount.
- [ ] Ships a record ONLY when `entrypoint == 'claude-desktop'`.
- [ ] Produces **exactly** the payload schema frozen in `billing/otel/transcript.py` — same field names,
      including `repo_raw` carrying the raw git remote for the server to normalize. A mismatch means every
      desktop row lands in `unknown` and never invoices, or the batch is rejected record by record.
- [ ] **Does NOT send `cwd`.** It is absent from the frozen schema by decision: the opt-in consent
      notice at `client-package/configure.py:109` and `client-package/INSTRUCTIONS.md:76` states that
      file paths are not collected, and a desktop `cwd` is a file path. The server's fail-closed
      unknown-field rule will reject a record carrying it.
- [ ] Caches the git-remote lookup per distinct `cwd`. A 215-record transcript must not spawn 215
      `git config` subprocesses inside a `SessionEnd` hook.
- [ ] Transmits usage metadata only. NEVER message content, prompts, tool output, file contents, or any
      transcript text.
- [ ] Reads identity from `~/.claude.json` → `oauthAccount.emailAddress` / `.accountUuid` /
      `.organizationUuid`. NEVER reads `~/.claude/.credentials.json`.
- [ ] Missing or unreadable identity degrades gracefully — the record still ships with empty identity
      fields rather than being dropped.
- [ ] Resolves the git remote from `cwd` as `claude-repo-tag.py` does; a non-git `cwd` (the scratch case)
      ships `repo_raw=''` rather than being skipped.
- [ ] Uses `CLAUDE_BILLING_RECEIVER` and `CLAUDE_BILLING_TOKEN`, defaulting to `http://127.0.0.1:4318`.
      Must NOT read `OTEL_*` variables — Claude Code does not pass those to hook subprocesses.
- [ ] Short network timeout; failures swallowed.
- [ ] Batches to the max batch size exported by `transcript.py`.
- [ ] A corrupt or partially-written transcript line is skipped, not fatal — transcripts are appended
      live and the final line may be incomplete.

**Watermark and failure handling — the permanent-stall trap**

- [ ] **State is tracked per transcript file, not as one global timestamp.** A single global watermark
      loses records from overlapping sessions: desktop session A ends at 10:00 and advances the mark;
      long-running session B, holding unshipped messages timestamped 09:30, ends at 11:00 — its file
      qualifies for the sweep but every record predates the mark, so filtering by timestamp drops them
      silently. That directly defeats this goal's own success criterion about sessions whose
      `SessionEnd` never fires. Key state by transcript path (or by shipped `request_id`), so each
      file's progress is independent.
- [ ] Per-file state **advances only on an HTTP 200**, and never past the earliest record that has not
      been confirmed shipped. Advancing on attempt loses records silently.
- [ ] Records within a batch are emitted in non-decreasing `ts` order, so a partial failure cannot
      strand an earlier record behind a later confirmed one.
- [ ] **The drop bound applies ONLY to a permanently-rejecting response — an envelope 400 — never to a
      transport failure.** A batch that receives a 400 is retried a bounded number of times across runs;
      after the bound is exhausted it is dropped, that file's state advances past it, and the drop is
      recorded locally. Without this, one poison batch blocks every later record forever while the hook
      exits 0 and reports nothing.
- [ ] **A transport failure — connection refused, DNS failure, timeout, TLS error — retries with
      backoff INDEFINITELY and never consumes the drop bound.** State does not advance and nothing is
      dropped.

      The distinction is load-bearing and the two cases are not alike. A poison batch will never
      succeed and genuinely blocks later records behind it; that is what the bound exists for. A
      transport failure blocks every batch equally, costs nothing to retry — the transcripts are
      durable on disk and the state is a watermark, not a growing queue — and self-heals the moment the
      network returns. Applying the bound to it means a developer working off-VPN, on a plane, or
      simply away from the network for a few sessions has that entire period's billing **dropped and
      the watermark advanced past it**. The plan is forward-only with no backfill, so that spend is
      unrecoverable. For a laptop fleet running a desktop app, offline is a routine state, not an edge
      case.

      Note the scoping in `goal.md`: its success criterion is that a batch the receiver *permanently
      rejects* must not stall later billing. An earlier draft of this task broadened the bound to cover
      transport failures too; that broadening is what created the data-loss path, and it is corrected
      here.
- [ ] The local record of a drop or rejection names the session and batch so it can be investigated, and
      contains no message content.
- [ ] State lives with the hook's own state on the developer's machine, never inside the repo.
- [ ] Forward-only by default, disambiguated: on first run, record an **install timestamp** and skip
      records whose `ts` precedes it — do NOT mark every existing file as fully shipped. The two
      readings differ for the session that triggers the first run: marking files done would discard the
      in-progress session entirely, including records written after install. Per-file state then
      advances normally from that point.
- [ ] The catch-up sweep re-scans transcripts modified since their own last-shipped state and is bounded
      so it cannot run unboundedly on a machine with a large transcript history.
- [ ] **The sweep covers sessions whose `SessionEnd` never fired.** A crashed or force-quit session
      leaves a transcript with unshipped records and no hook run of its own; the next session's hook
      run must ship them. This is the mechanism `goal.md` promises and is the reason per-file state
      exists — the sweep must not be limited to the current session's own files.
- [ ] **The sweep spans ALL project directories under `~/.claude/projects`, not just the current one.**
      Recorded reason: every desktop scratch session gets its OWN project directory — observed
      `C--Users-ZaneChing-AppData-Roaming-Claude-scratch-workspaces-<uuid>-<uuid>-scratch-<date>-<hash>`
      — which is never the "current" directory for any later session. A project-directory-scoped sweep
      would therefore never reach a crashed desktop scratch session, making this goal's never-fired-
      `SessionEnd` success criterion false in production for the dominant real desktop shape, while a
      single-directory fixture passes. Cross-directory scope is mandatory, not an optimization.
- [ ] A file that yielded **nothing shippable at all** (a CLI or VS Code session on a mixed machine) is
      marked examined, keyed by absolute path plus modification time, so the sweep does not re-parse the
      entire history on every `SessionEnd` forever.
- [ ] **A file whose trailing group was WITHHELD as in-flight is NEVER marked examined**, and the
      examined-mark is in any case bypassed once a file's idle threshold has elapsed.

      These two rules are stated together because they conflict if either is written alone. The idle
      branch of the completeness rule ships a trailing group precisely when a file's mtime has NOT
      changed — that is what "idle" means — while an mtime-keyed examined-mark skips exactly those
      files. Without this clause: a file swept mid-flight is marked examined at mtime M; its session
      then ends without another write (crash, force-quit, or simply its last group); mtime stays M
      forever; the file is never revisited; **the withheld group is lost permanently and silently**
      under the always-exit-0 rule. Withholding a group and then refusing to look again is strictly
      worse than never withholding it.

**In-flight completeness — do not ship a partial cumulative group**

- [ ] **A request group must not be shipped until it is final.** Because the hook now parses files
      belonging to sessions other than the one ending, it will encounter transcripts that are still
      being written. A group currently holding only `apiBlockIndex=0, output=5` would ship at 5, per-file
      state would advance past it, and the terminal `output=209` written seconds later would then sit
      behind the watermark — and even if re-sent, task 01 criterion 5b's first-writer-wins means the
      partial value survives permanently. Silent, uncorrectable without a manual DELETE, and criterion
      6 ("running twice ships each record once") would pass while it is happening.
- [ ] The completeness rule is: ship a file's **trailing** request group only when either (a) the file
      is the one named by `transcript_path` and the hook is running on that session's own `SessionEnd`,
      or (b) the file's modification time is older than a stated idle threshold. All non-trailing groups
      in a file are complete by construction — a later group exists after them — and ship immediately.
      State the chosen threshold explicitly in the file.
- [ ] The observed streaming window is ~6 seconds (real desktop group: `21:19:53.999` →
      `21:20:00.187`), so the threshold need not be large; it must simply exist and be documented.

**Rollout — both tracks, end to end**

- [ ] `deploy/managed-settings.json` registers the new hook on `SessionEnd` alongside the existing
      `claude-repo-tag.py` registration, preserving every existing registration exactly.
- [ ] The `REPLACE_WITH_FLEET_BILLING_TOKEN` placeholder convention is preserved. A real token is NEVER committed.
- [ ] `client-package/claude-transcript-usage.py` exists and is **content-identical after newline
      normalization** to `deploy/claude-transcript-usage.py` — NOT byte-identical. Byte-identity is
      unachievable here: `core.autocrlf=true` on this machine and `client-package/.gitattributes` pins
      `*.py text eol=lf`, so the existing precedent pair already differs in the working tree
      (`deploy/claude-repo-tag.py` 4521 B CRLF vs `client-package/claude-repo-tag.py` 4414 B LF). A
      byte-comparison test would pass on the machine that wrote the files and fail on the next clone.
- [ ] Add `deploy/*.py text eol=lf` to the repo root `.gitattributes`, so the `deploy/` hook is checked
      out with LF on every platform. Without it, a macOS or Linux fleet machine receives a CRLF shebang
      line and the hook fails to execute — silently, because the hook is required to exit 0.
- [ ] `client-package/configure.py` installs, verifies, and uninstalls BOTH hooks. Today `HOOK_NAME` at
      line 50 is a single string and line 416 copies exactly that one file from the script's own
      directory, raising `SystemExit` if absent. Generalize to a collection; `strip_our_hooks` already
      takes a `hook_file` argument and can be called per hook.
- [ ] **Each hook is registered on its own event set.** `configure.py:348` currently registers a hook
      across all five `HOOK_EVENTS`. `claude-repo-tag.py` keeps all five; the transcript hook is
      `SessionEnd` ONLY, matching the decision recorded in `goal.md` and the `deploy/` track. Registering
      the transcript sweep on `UserPromptSubmit` would run a full transcript parse on every prompt.
      Generalize to a per-hook event map, not a shared constant.
- [ ] State what "verify" covers for the new hook. `cmd_verify` today only pings the receiver and checks
      no hook at all; extend it to confirm both hooks are registered and their files exist, or record
      explicitly that verification remains receiver-only.
- [ ] Update the collection notice in `configure.py` ONLY if the payload ever changes to include
      something it disclaims. As specified, the payload sends no prompts, no code, no file contents, and
      no file paths, so the existing notice at line 109 stays accurate and must be left alone.
- [ ] `configure.py` keeps its atomic-merge-with-timestamped-backup behavior unchanged.
- [ ] Uninstall fully reverses BOTH hooks' registrations, leaving no orphan entry.
- [ ] `client-package/build.py` adds `claude-transcript-usage.py` to `CONTENTS` (line 57). `CONTENTS`
      also gates `scan_for_secrets`, so omitting it both ships a broken package and skips the secret scan
      on the new file.
- [ ] `client-package/VERSION` is bumped from `1.1.0`, per `client-package/ADMIN.md`.
- [ ] `pilot-package/` is NOT modified.
- [ ] The completion report states explicitly that `client-package.zip` is a build artifact that is NOT
      regenerated by this task, and that no developer on the opt-in track receives the hook until someone
      runs `build.py` and redistributes. Name that as a required rollout step.
- [ ] No third-party import anywhere.

## Acceptance Criteria

1. Given a synthetic transcript with desktop, CLI, and VS Code records, the hook builds payload records
   for the desktop ones only — verification: unit test importing the script by path.
1b. **EXACT AMOUNT.** Against task 00's cumulative multi-block fixture, the hook emits ONE record per
   `(requestId, message.id)` group whose token counts equal the fixture's published TERMINAL-block
   totals exactly — input=2, output=209, cache_creation=13984, cache_read=35774 for the modelled group.
   The test must assert equality with those numbers, and must additionally assert the result is NOT the
   sum (output=214) and NOT the first block (output=5) — verification: unit test. This is the single
   criterion standing between this feature and a 2.28x over-bill or an 8.6x under-bill; "non-zero" or
   "records were produced" does not satisfy it.
1c. An exact-duplicate pair (same `requestId`, same `message.id`, identical usage, **both rows carrying
   a non-null `stop_reason`**) collapses to one record, not two — verification: unit test.
1d. **SUBAGENT CAPTURE, against the real nested layout.** Given task 00's fixture tree — a main
   `<session_id>.jsonl` plus a sidechain file at `<session_id>/subagents/agent-<agentId>.jsonl` — the
   hook ships records from BOTH. Assert the combined token totals equal task 00's published combined
   expectation, and assert explicitly that the total is NOT the main-file-only value — verification:
   unit test.
1d-bis. **ANTI-FIXTURE CHECK — the criterion a wrongly-shaped fixture cannot satisfy.** In the same
   test, compute two totals over the fixture tree: one from a FLAT enumeration
   (`glob(project_dir/*.jsonl)`) and one from the hook's own enumeration. Assert the flat total equals
   the published **main-only** total and the hook's total equals the published **combined** total, and
   that the two differ. Rationale, recorded because it already happened: an earlier draft specified
   both the hook AND the fixture to a flat layout, so this regression test would have passed green
   while production missed 30% of spend. A test whose fixture encodes the defect is worse than no test.
   This assertion fails if the fixture is flat, if the hook globs flatly, or if either is later
   "simplified" back — it cannot be satisfied by a consistently-wrong pair.
1e. Sidechain records carry `query_source='subagent'` and main-transcript records carry
   `query_source='main'`, and both resolve to the same repo for a shared `sessionId` — verification:
   unit test.
1f. A group whose rows have a missing `apiBlockIndex` selects by file order without raising —
   verification: unit test seeding a group with mixed `None`/int and asserting a record is produced and
   the process exits 0.
2. The built payload contains no message content — verification: unit test seeding distinctive text in a
   message body and asserting it appears nowhere in the payload. Assert on the seeded text, not on field names.
3. The built payload validates against `billing/otel/transcript.py`'s validator without error —
   verification: unit test feeding the hook's output through the real server-side validator. This is the
   contract test that closes the client/server schema-drift risk.
4. The hook exits 0 when the receiver is unreachable, stdin is empty, the transcript is missing, and
   `~/.claude.json` is absent — verification: unit test per case asserting exit code 0.
5. A malformed final line is skipped and preceding records still ship — verification: unit test.
6. Running twice over the same transcript ships each record once — verification: unit test on per-file state.
7. **A batch that receives an envelope 400 does not advance that file's state; after the retry bound it
   is dropped, state advances, and later records ship** — verification: unit test simulating a
   persistent 400. Regression test for the permanent-stall trap.
7b. **Two overlapping sessions, where the older session's `SessionEnd` fires LAST, both ship completely**
   — session A (records at 09:30) ends at 11:00, after session B (records at 10:00) ended at 10:05.
   Verification: unit test asserting every record from both sessions is shipped exactly once. This is
   the regression test for the global-watermark defect; with a single shared timestamp, session A's
   records are silently lost.
7c. A 200 response reporting per-record rejections advances state and records the rejection locally,
   without retrying the whole batch — verification: unit test.
7d. **NEVER-FIRED `SessionEnd`, ACROSS PROJECT DIRECTORIES.** Session C's transcript exists on disk with
   unshipped records in its OWN project directory (modelling a desktop scratch session), and C's hook
   never ran; session D's `SessionEnd` then fires from a DIFFERENT project directory. All of C's records
   ship, exactly once — verification: unit test. The cross-directory placement is the point: a
   same-directory fixture would pass against a project-scoped sweep that can never reach a real crashed
   desktop session.
7f. **IN-FLIGHT GROUP NOT SHIPPED PARTIALLY.** A transcript whose trailing group currently holds only
   `apiBlockIndex=0, output=5`, belonging to a session other than the one ending and modified within the
   idle threshold, is NOT shipped for that group. After the terminal `apiBlockIndex=1, output=209` is
   appended and the threshold passes, the group ships once at 209 — verification: unit test asserting
   both halves. Regression test for permanently frozen partial values.
7g. **ABANDONED IN-FLIGHT GROUP STILL SHIPS.** A file whose trailing group was withheld as in-flight,
   and to which **nothing further is ever appended**, still ships that group exactly once after the idle
   threshold elapses — verification: unit test that advances the clock (or the threshold) WITHOUT
   touching the file, so its mtime is unchanged. This is the case criterion 7f cannot reach: 7f appends
   a row, which changes mtime and bypasses the examined-mark, so 7f passes green while the
   permanent-loss bug is present. A crashed session's final group is exactly this shape.
7h. **TRANSPORT FAILURE DOES NOT DROP.** A batch failing with a transport error more times than the drop
   bound neither advances state nor drops; once the receiver becomes reachable, every withheld record
   ships exactly once — verification: unit test simulating N+1 connection failures followed by a success.
   Regression test for the offline-laptop data-loss path; criterion 7 covers only a persistent 400,
   which is the case the bound legitimately applies to.
7e. On a first run, records predating the install timestamp are not shipped, while records written
   after it in the same in-progress transcript ARE — verification: unit test. Pins the forward-only
   semantics against the mark-all-files-done reading, which would lose the triggering session.
8. The hook never opens `~/.claude/.credentials.json` — verification: unit test asserting the path is
   neither present in the source nor opened during a run.
9. `deploy/managed-settings.json` is valid JSON, retains every existing registration, and adds the new
   one — verification: unit test parsing the file.
10. `configure.py` install-then-uninstall leaves a settings file equivalent to the starting state, with
    both hooks installed and both removed — verification: unit test over a temporary settings file.
11. The two hook copies are identical after newline normalization — verification: unit test comparing
    content with line endings normalized, NOT raw bytes. Prevents silent drift without encoding a
    platform assumption that breaks on the next clone.
12. `build.py`'s `CONTENTS` includes the new hook — verification: unit test importing `CONTENTS` and asserting membership.
13. The transcript hook is registered on `SessionEnd` only, on BOTH tracks, while `claude-repo-tag.py`
    retains all five events — verification: unit test asserting the event set per hook in the
    `deploy/managed-settings.json` file and in the settings `configure.py` produces.
14. The repo root `.gitattributes` pins `deploy/*.py` to LF — verification: unit test reading the file,
    plus `git check-attr eol -- deploy/claude-transcript-usage.py` reporting `lf`.
15. The completion report documents the rollback path: unregister the hook to stop ingest, and
    `DELETE FROM token_usage WHERE usage_source='transcript'` (with the matching `cost_usage` delete) to
    remediate a bad ingest — verification: the report contains both, and the delete statements are shown
    to affect no OTLP row on a mixed store.

## Files to Read

- `deploy/claude-repo-tag.py` — the precedent: stdin handling, `CLAUDE_BILLING_*`, short timeout,
  swallowed failures, always-exit-0, git remote resolution.
- `client-package/claude-repo-tag.py` — proof of the byte-copy convention.
- `billing/otel/transcript.py` — the frozen payload schema and max batch size from task 02.
- `billing/otel/receiver.py` — endpoint path and auth header convention.
- `deploy/managed-settings.json` — existing registrations and the placeholder convention.
- `client-package/configure.py` — `HOOK_NAME` line 50, the copy at line 416, `strip_our_hooks` line 284,
  the atomic merge and backup.
- `client-package/build.py` — `CONTENTS` line 57 and `scan_for_secrets`.
- `client-package/ADMIN.md` — the VERSION bump instruction.
- `deploy/README.md` — deployment paths and enforcement.
- `tests/conftest.py` — fixtures from task 00.

## Files to Create / Change

- `deploy/claude-transcript-usage.py` — new standalone hook.
- `client-package/claude-transcript-usage.py` — copy, identical after newline normalization.
- `.gitattributes` (repo root) — pin `deploy/*.py text eol=lf`.
- `deploy/managed-settings.json` — register on `SessionEnd`.
- `client-package/configure.py` — install/verify/uninstall both hooks.
- `client-package/build.py` — add the hook to `CONTENTS`.
- `client-package/VERSION` — bump.
- `tests/test_transcript_hook.py`, `tests/test_configure.py` — every acceptance criterion above.

## Constraints

- Must: always exit 0; be stdlib-only and standalone; transmit usage metadata only.
- Must: read identity from `~/.claude.json` only; never `~/.claude/.credentials.json`.
- Must: preserve every existing hook registration, the placeholder token convention, and `configure.py`'s
  atomic merge and backup.
- Must: keep the two hook copies identical after newline normalization — NOT byte-identical. See the
  requirement and criterion 11 for why byte-equality is unachievable under `core.autocrlf=true`.
- Must NOT: modify `deploy/claude-repo-tag.py` or `client-package/claude-repo-tag.py` — untouched by
  explicit decision; that hook runs async on every prompt and must stay small.
- Must NOT: modify `pilot-package/`; commit a real token; read `OTEL_*`; add a third-party import;
  ship transcripts predating the watermark; regenerate `client-package.zip`.

## Verification

- Targeted test command: `python -m pytest tests/test_transcript_hook.py tests/test_configure.py -v`
- Tests import the hook by file path and must never post to a real receiver.
