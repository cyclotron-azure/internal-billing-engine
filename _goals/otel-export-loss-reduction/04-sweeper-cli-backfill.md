# Task 04: sweeper ships CLI / VS Code transcripts, plus a one-time historical replay

## Objective

The `SessionEnd` sweeper stops discarding the CLI and VS Code transcripts it already reads,
and ships them with their real entrypoint. A one-time, idempotent replay makes the existing
on-disk history eligible instead of only future sessions. Records the server declines as
too recent are retried rather than burned. Both on-disk copies stay identical and the
always-exit-0 contract holds.

## Dependencies

- `03-receiver-health-and-cli-ingest`

**Why this ordering is load-bearing, not decorative.** This task cannot import from
`billing/`, so it duplicates task 03's constant rather than consuming it — which makes the
dependency look cosmetic. It is not. If this task landed first, the sweeper would ship
`cli` records to a server that still rejects them as `invalid_entrypoint`, and because the
sweeper marks every record in an HTTP-200 chunk resolved regardless of per-record rejection
(`:689-692`), every one of those records would be **permanently burned**. Task 03 must be
in place first.

```yaml
# --- task ownership contract ---
writes:
  - client-package/claude-transcript-usage.py
  - deploy/claude-transcript-usage.py
reads:
  - billing/otel/transcript.py       # the allowed set and BACKFILL_MIN_AGE_SECONDS
depends_on:
  - "03-receiver-health-and-cli-ingest"
owner: implementer
rewrite_semantics: targeted-insertion
eval_depth: full
# full (raised from light after Phase 3): this task now performs a one-time replay of the
# entire on-disk transcript history. Its correctness rests on the interaction between the
# state file, transcript_key's replay guard, and task 03's session-level exclusion. A
# mistake re-ships history in a way that only those guards stop.
```

## Background — the state file, exactly as it works today

Read these before writing anything; the requirements below refer to them by name.

- State shape: `files[file_key] = {"resolved": [request_id, ...], "examined_mtime": ...}`
  (`:505-511`). There is **no session-level unit** in the state file.
- The scan loop keys on `(session_id, request_id, message_id)` (`:528`) and skips any
  request id already in `resolved` (`:529`), forever.
- `install_epoch` watermark: any group whose `ts_epoch` predates install is skipped
  (`:543-545`). Forward-only.
- `_mark_resolved` (`:538`) is what today's entrypoint filter calls on every CLI record —
  which is why CLI history is already burned on every installed machine.
- Trailing-group withhold: `withheld = True` for a group still within
  `IDLE_THRESHOLD_SECONDS = 30.0` (`:137`, `:547-551`), and a withheld group skips the
  `examined_mtime` advance (`:739-744`). **This is the existing mechanism your quarantine
  must reuse, not a parallel one you invent.**
- `outcome == "ok"` marks every record in the chunk resolved and only *logs* per-record
  rejections into `state["drops"]` (`:689-700`). `transport_fail` correctly does not
  advance state (`:735-738`).

## Requirements (exhaustive — the evaluator verifies every item)

### Part A — ship CLI / VS Code

- [ ] **Do not touch enumeration.** `find_transcript_files` already recurses
      `$CLAUDE_CONFIG_DIR/projects/**/*.jsonl` (`:244`), which is where CLI and VS Code
      transcripts live. Only the filter and the payload's entrypoint field change.
- [ ] `ENTRYPOINT` becomes an allowed **set** of `claude-desktop`, `cli`, `claude-vscode`,
      matching `transcript.py` exactly. Replace its comment — "CLI and VS Code already
      bill" is now false and is the reason this gap existed.
- [ ] The payload's entrypoint is the row's **own** value. The
      `terminal_row.get("entrypoint") or ENTRYPOINT` fallback (`:385`) must not relabel a
      row as `claude-desktop`; after task 03's preserve-entrypoint fix, a mislabeled row is
      stored as claimed.
- [ ] A terminal row with a **missing, empty, or non-string** entrypoint is skipped and
      **marked resolved**. It can never become shippable, so leaving it unresolved would
      re-parse it on every run forever.
- [ ] An entrypoint outside the allowed set (e.g. `claude-web`) is likewise skipped and
      **marked resolved** — exactly today's behavior (`:537-539`). This resolves the
      contradiction the Phase 3 evaluator found between the old requirements 5 and 7: only
      the **quarantine** skip leaves state unadvanced, because only the quarantine skip is
      temporary.

### Part B — quarantine, with the server boundary made unreachable

- [ ] `BACKFILL_MIN_AGE_SECONDS = 1800` locally — deliberately **twice** task 03's
      server-side 900s. Comment must say why: the server also enforces 900s, and a record
      that clears the client gate but fails the server's (clock skew, or latency between
      candidate-building and the POST) is **permanently burned** by the resolve-on-200 path
      at `:689-692`. A strictly larger client window makes the server boundary unreachable
      in practice. Belt and braces, in the safe direction.
- [ ] A `cli`/`claude-vscode` group whose newest terminal-row timestamp is within the
      window is **withheld** using the existing `withheld = True` mechanism, so
      `examined_mtime` does not advance and `_mark_resolved` is not called. It stays
      eligible on a later run. **This is the single most important requirement in the
      goal**: implemented backwards, every CLI session is skipped exactly once and never
      revisited, which looks like success and recovers nothing.
- [ ] **`too_recent` is non-resolving.** On `outcome == "ok"`, a record whose per-record
      rejection reason is `too_recent` must **not** be marked resolved. Every other reason
      (`session_has_otlp`, `invalid_entrypoint`, and the pre-existing reasons) stays
      resolving — those are permanent verdicts, and `session_has_otlp` in particular is
      permanent by construction. Keep logging all of them to `state["drops"]` as today.
- [ ] `claude-desktop` groups are **not** quarantined by the new window. They keep only the
      pre-existing 30s trailing-group withhold. Desktop capture must not get slower.
- [ ] **The clock must be patchable** — the quarantine's "now" reads through a module-level
      helper, not an inline `datetime.now()`/`time.time()` at the comparison site. Task 05
      freezes time and advances it between two runs; neither works against an inline call,
      and `sleep`-based tests are not acceptable.

### Part C — the one-time historical replay

- [ ] Gate it on a single state flag (e.g. `state["cli_backfill_replay_at"]`). While the
      flag is **absent**, perform the replay; once set, behave normally forever.
- [ ] The replay does exactly **two** things, atomically with setting the flag and
      **before any POST**: clear every `files[*]["resolved"]` list and clear every
      `files[*]["examined_mtime"]`.
- [ ] **The `install_ts` watermark is NOT reset. Decided by the user after fix cycle 1.**
      Measured: `install_ts` is set to *now* on the first run (`:752-753`), so every
      transcript written **after** installation already passes the watermark -- what
      actually blocked recovery was `resolved` and `examined_mtime`, not the watermark.
      Resetting it therefore adds nothing to the goal's target (post-install sessions whose
      OTLP export never flushed) and instead unlocks **pre-installation** history, for
      `claude-desktop` as well as CLI. That usage was never captured by OTLP either,
      because the tool was not installed yet -- so billing it now would expand client
      invoices retroactively rather than recover lost telemetry. Leave `state["install_ts"]`
      exactly as found, and leave the `:543-545` watermark check untouched.
- [ ] **`examined_mtime` is not optional, and omitting it makes the whole replay a
      no-op.** `:509-511` does `if examined_mtime is not None and examined_mtime ==
      current_mtime: ... continue` -- and that `continue` fires **before** the group loop
      that consults `resolved` at `:529`. Every historical transcript file has an
      `examined_mtime` from a prior run and an unchanged mtime, because history is not
      being appended to. Clearing only `resolved` would re-scan nothing and ship nothing,
      while still passing a test whose fixture left `examined_mtime` at its `None` default.
- [ ] Writing the flag *before* shipping is what makes a crash mid-replay safe -- a partial
      replay does not replay twice.
- [ ] **The cleared state is permanent, not restored after the pass.** A full-history replay
      is many `MAX_BATCH_SIZE`-sized batches on a laptop that may sleep or lose the
      receiver mid-pass, and `stop_due_to_transport` (`:735-738`) ends the run early. If
      the reset were rolled back afterwards, a replay that died on batch 3 of 80 would
      permanently lose the remainder: the flag blocks a retry and the cleared state is back.
      Leaving the reset permanent lets ordinary subsequent runs finish the job, which is
      safe because the quarantine, the session-level exclusion and `transcript_key` all
      make re-shipping idempotent.
- [ ] **Why clearing all resolved ids is safe, and must be in the comment.** Re-shipped
      *desktop* records are dropped at the store by `transcript_key`, which exists
      precisely as a replay guard (see its rationale in `otel_store.py`). Re-shipped
      *CLI* records are additionally gated by task 03's session-level exclusion. So the
      replay can only ever *add* rows for sessions that were lost entirely — which is the
      whole target — and its worst case is one wasted re-POST of history.
- [ ] **Known, accepted side effect, to be stated in the module docstring.** The replay
      will push a large number of already-known records through the store's
      `INSERT OR IGNORE` paths, so the `dedupe_drops` counter added by the previous goal
      will spike and `reconcile --detail`'s `DEDUPE DROPS` section will show a one-day
      cliff of drops. That is the replay working as designed, not a dp_key collision.
      Note the replay date so whoever reads that output can attribute it.
- [ ] The replay respects the quarantine and the allowed-entrypoint filter like any other
      pass. It is a state reset, not a second code path — there must be exactly **one**
      shipping path in the script.
- [ ] **Log the intended volume before the first POST** -- files eligible, groups
      eligible, records to ship. A replay that intends to ship zero records is then visible
      immediately, at the moment it happens, rather than inferred later from a tally that
      reads zero. This is the cheap half of the dry-run the Phase 3 evaluator argued for; a
      full human-gated two-step is deliberately **not** adopted, because the hook runs
      unattended on `SessionEnd` across a fleet of laptops and there is no operator in the
      loop to gate it. The guards, not a review step, are what make the writes safe.
      **Persist the intended-volume numbers into `state` alongside the outcome tallies,
      not only to stdout** -- the hook's own output goes nowhere anybody reads on a
      laptop, so `state` is what will actually be inspected after the fact.
- [ ] **Recovery must be measurable.** The run reports, at minimum: records shipped,
      records rejected by reason (including `session_has_otlp` and `too_recent`), and
      whether this run performed the replay. Persist the replay's own tallies in `state`
      so the outcome is inspectable after the fact. A zero-recovery replay must be a
      *visible* result.

### Part D — invariants

- [ ] **Never substitute a placeholder for a missing `session_id`.** If a terminal row has
      no usable `sessionId`, **drop the record**; do not emit `"unknown"` or any other
      sentinel. `receiver.py:190` substitutes the literal `"unknown"` on the **OTLP** side
      when `session.id` is absent, and task 03's evaluator measured three attribute-less
      datapoints all collapsing into one `'unknown'` bucket. If this hook mirrored that
      idiom, every such record would match the guard's "this session already has OTLP rows"
      answer and be rejected `session_has_otlp` **forever** -- silently discarding
      recoverable usage, and invisible because a rejection is not an error. Today the hook
      is correct (`:370` passes `terminal_row["sessionId"]` verbatim) and the transcript
      path has no substitution at all; keep it that way. Note also that the fix for this
      belongs here, not in the guard: excluding an `'unknown'` sentinel inside
      `sessions_with_otlp_rows` would flip it into the double-billing direction for a
      session genuinely named `unknown`.
- [ ] **Always exit 0.** Every new path — malformed timestamp, unparseable entrypoint,
      state-file write failure, replay failure — must not raise out of the hook.
- [ ] The two copies (`client-package/`, `deploy/`) are byte-identical when done, as they
      are today (sha256 currently matches).
- [ ] Standard library only; no import from `billing/`.
- [ ] No new network call, no new endpoint, no change to the POST body shape beyond the
      entrypoint value. Still posts to `/v1/transcript-usage`.
- [ ] The state-file *format* gains only the replay flag and the tallies. No key is
      renamed or removed — an older script version must still read it without crashing.

## Acceptance Criteria

1. A fixture projects root with one `cli` transcript aged 2 hours produces a payload whose
   record has `entrypoint == "cli"` — verification: unit test
2. The same fixture aged 60 seconds produces **no** record — verification: unit test
3. **The trap.** After the aged-60-seconds run: the file's `resolved` list does not contain
   that request id **and** `examined_mtime` has not advanced; then, with the frozen clock
   advanced past 1800s, a second run **does** produce the record. One test, both halves,
   asserting the two state fields by name — verification: unit test
4. A `claude-desktop` transcript aged 60 seconds still produces its record — verification:
   unit test
5. A terminal row with no `entrypoint` key produces no record, does not raise, **and is
   marked resolved** (assert the id is in `resolved`) — verification: unit test
6. `entrypoint: "claude-web"` produces no record and **is** marked resolved —
   verification: unit test
7. A mixed projects root (one desktop, one `cli` aged 2h, one `cli` aged 60s, one
   `claude-web`) produces exactly two records with the expected entrypoints —
   verification: unit test
8. A malformed terminal-row timestamp produces no record, does not raise, and does not
   prevent other sessions in the same run from shipping — verification: unit test
9. Exit code is 0 on every path above, including when the state file's directory is
   read-only — verification: command output
10. The two copies have identical sha256 digests — verification: command output
11. `python -c "import ast;ast.parse(open('client-package/claude-transcript-usage.py').read())"`
    exits 0 — verification: command output
12. **`too_recent` is non-resolving.** Given a mocked server response of HTTP 200 whose
    rejected list marks one record `too_recent` and another `session_has_otlp`: the
    `too_recent` id is absent from `resolved` and the `session_has_otlp` id is present.
    One test, both halves — verification: unit test
13. **Replay runs once, and actually re-scans.** The fixture state file must have
    populated `resolved` lists and `examined_mtime` set to each transcript file's real
    current mtime -- not left at its `None` default. Without that last part the test passes
    against a production no-op (see the `:509-511` short-circuit). Set `install_ts`
    **earlier** than the fixtures' timestamps, representing post-install history, which is
    what the replay exists to recover. The run then clears both, sets the flag, and ships
    those groups; a second run with the flag set ships **nothing**. Additionally assert
    `state["install_ts"]` is **unchanged** by the replay -- verification: unit test
14. **Replay is crash-safe in both directions.** With the POST mocked to raise after the
    state write: (a) the flag is already persisted and the next run does **not** replay
    again; **and (b) the un-shipped remainder still ships on that next run** -- because the
    cleared `resolved`/`examined_mtime` were left in place. Both
    halves in one test; (a) alone passes whether or not the remainder is lost, which is the
    whole failure mode -- verification: unit test
15. **Replay does not bypass the guards.** In the replay run, a `cli` group aged 60 seconds
    is still withheld, and a `claude-web` group is still skipped — verification: unit test
16. **Recovery is reported, and `shipped` counts only ACCEPTED records.** The run persists
    `shipped`, `rejected_by_reason`, `deferred` and `replay_performed` into
    `state["cli_backfill_last_run"]`, plus the pre-POST intended volume into
    `state["cli_backfill_replay_intended"]`. Assert the **values** for a known fixture, not
    merely that the keys exist. Two assertions carry the weight:
    (a) a **fully-rejected** fixture reports `shipped == 0`. Before fix cycle 2 this
    reported `shipped: 1` with zero records accepted, because the counter incremented for
    every *resolved* record and only `too_recent` was skipped -- inverting the one property
    this criterion exists for.
    (b) the identities hold: `records_to_ship == shipped + sum(rejected_by_reason.values())`
    and `deferred == rejected_by_reason.get("too_recent", 0)`.
    **Corrected by the orchestrator:** the fix-cycle package proposed
    `records_to_ship == shipped + sum(rejected) + deferred`, which double-counts
    `too_recent` -- the requirement at line 170 puts `too_recent` inside
    `rejected_by_reason`, and the implementer was right to flag it rather than regress that
    -- verification: unit test
17. Desktop resolution state survives the replay in the sense that matters: a desktop record
    re-shipped by the replay is accepted by the store's `transcript_key` guard without
    creating a duplicate row. Assert the post-run `token_usage` row count for that session
    is 1, not 2 -- **and the `cost_usage` count for that session is likewise 1, not 2**. The
    cost row is the half that the exclusion guard's table scope turns on, so it belongs
    in this assertion -- verification: integration test
18. Every pre-existing test in `tests/test_transcript_hook.py` and
    `tests/test_integration_desktop.py` passes with no edit **except** any of the seven
    assertions task 05 owns (across four files). List every pre-existing test your change breaks, with
    file:line, in your report — verification: unit test
19. **Pre-installation history stays excluded.** A `cli` transcript group whose timestamp
    predates `state["install_ts"]` is **not** shipped, even on the replay run. This is the
    criterion that fails if the watermark reset is reintroduced, and it is the reason
    `tests/test_transcript_hook.py::test_ac7e_forward_only_install_watermark` must keep
    passing **unmodified** -- verification: unit test

## Files to Read

- `client-package/claude-transcript-usage.py` — the whole script. Specifically: the
  `ENTRYPOINT` constant and its comment; `find_transcript_files` (`:244`); the entrypoint
  filter (`:537-539`); the payload builder's `or ENTRYPOINT` fallback (`:385`); the state
  read/write (`:505-511`); the scan loop and resolved skip (`:528-529`); `install_epoch`
  (`:543-545`); the trailing-group withhold (`:137`, `:547-551`, `:739-744`); the
  resolve-on-200 path (`:689-700`); `transport_fail` (`:735-738`); `run()` (`:635`)
- `deploy/claude-transcript-usage.py` — confirm currently identical
- `billing/otel/transcript.py` — the allowed set, the reason strings, and
  `BACKFILL_MIN_AGE_SECONDS` as landed by task 03 (read-only)
- `billing/otel/otel_store.py` — `transcript_key`'s replay-guard rationale, which Part C's
  safety argument depends on (read-only)
- `tests/test_transcript_hook.py` — the existing fixture shape (read-only)
- `deploy/README.md` — the hook's registration and the always-exit-0 rule

## Files to Create / Change

- `client-package/claude-transcript-usage.py` — allowed set, entrypoint preservation,
  quarantine via the existing withhold, non-resolving `too_recent`, one-time replay,
  tallies, docstring notes
- `deploy/claude-transcript-usage.py` — the identical change

## Constraints

- Must: keep the two copies byte-identical.
- Must: keep always-exit-0.
- Must: reuse the existing `withheld` / `examined_mtime` mechanism for the quarantine.
- Must: write the replay flag before the first POST of the replay pass.
- Must: keep exactly one shipping path — the replay is a state reset, not a second path.
- Must NOT: change transcript enumeration, the POST target, or the payload shape beyond the
  entrypoint value.
- Must NOT: remove or rename an existing state key.
- Must NOT: import outside the standard library, or from `billing/`.
- Must NOT: edit `tests/`, `billing/`, or any settings/config file.
- Must NOT: add a flag or env var to disable the quarantine or to re-trigger the replay. A
  re-trigger switch is a double-billing lever in a support engineer's hands; deleting the
  state key by hand is the documented escape hatch and needs no code.

## Verification

- `python -m pytest tests/test_transcript_hook.py tests/test_integration_desktop.py -q`
  -> record the result and any pre-existing failures with file:line
- Capture verbatim: the two sha256 digests, one built payload record, and the run's
  reported tallies for the replay fixture.
