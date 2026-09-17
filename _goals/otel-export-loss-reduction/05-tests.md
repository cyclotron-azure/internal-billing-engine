# Task 05: tests

## Objective

One test per acceptance criterion across tasks 01-04 and 06 — **71 criteria** (7 + 15 + 21 + 19 + 9)
— all passing, every external service mocked, every database a temp file. The five
pre-existing assertions that encode the old behavior are *inverted*, not deleted.
`tests/COVERAGE_MAP.md` maps every criterion id to its test with zero dead ids and zero
unreferenced new tests.

## Dependencies

- `01-export-interval`, `02-store-reads`, `03-receiver-health-and-cli-ingest`,
  `04-sweeper-cli-backfill`, `06-otlp-session-id-coercion` — all must have landed

```yaml
# --- task ownership contract ---
writes:
  - tests/test_store_reads.py
  - tests/test_receiver_health.py
  - tests/test_cli_backfill.py
  - tests/COVERAGE_MAP.md
  - tests/test_transcript.py           # ONLY the two inverted assertions
  - tests/test_receiver.py             # ONLY the two inverted assertions (:278, :532)
  - tests/test_integration_desktop.py  # ONLY the one inverted assertion
  - tests/test_transcript_hook.py      # ONLY the two inverted assertions (:109, :489)
reads:
  - billing/otel/otel_store.py
  - billing/otel/receiver.py
  - billing/otel/transcript.py
  - client-package/claude-transcript-usage.py
depends_on:
  - "01-export-interval"
  - "02-store-reads"
  - "03-receiver-health-and-cli-ingest"
  - "04-sweeper-cli-backfill"
  - "06-otlp-session-id-coercion"
owner: test-writer
rewrite_semantics:
  # Per owned file. The three pre-existing test files are under a surgical fence and must
  # NOT be rewritten wholesale, which a single whole-file value contradicted.
  tests/test_store_reads.py: whole-file
  tests/test_receiver_health.py: whole-file
  tests/test_cli_backfill.py: whole-file
  tests/COVERAGE_MAP.md: targeted-insertion
  tests/test_transcript.py: targeted-insertion
  tests/test_receiver.py: targeted-insertion
  tests/test_integration_desktop.py: targeted-insertion
  tests/test_transcript_hook.py: targeted-insertion
eval_depth: full
# full: this task's output is the evidence base for the whole goal, and task 03's
# criterion 10 (no double-billing) plus task 04's criteria 3/12/13 are the only things
# standing between CLI backfill and a wrong client invoice. A test that passes for the
# wrong reason there is worse than no test. It also holds a surgical write fence on three
# pre-existing test files.
```

## The seven inverted assertions — scope this narrowly

These encode today's behavior, which this goal deliberately changes. They are yours, and
**only these seven hunks** in those four files:

- `tests/test_transcript.py:134-139` — parametrized over `["cli", "claude-vscode"]`,
  asserts `invalid_entrypoint`
- `tests/test_transcript.py:369-381` — asserts rejected indices `[1,2,4,5]`, where `req-2`
  is `cli`
- `tests/test_receiver.py:278-287`
- `tests/test_integration_desktop.py:393-399`
- **`tests/test_receiver.py:532-545`** —
  `test_wrong_typed_session_id_field_is_rejected_not_escaped`, surfaced by task 03's fix
  cycle 2. It posts `session_id=["x"]` and asserts
  `reason == "store_error:ProgrammingError"`, pinning the old behavior in which a
  wrong-typed `session_id` **escaped** `validate_batch` and was caught downstream by
  `_RECORD_DATA_ERRORS`. Change **only the reason assertion** to `invalid_session_id`;
  `rejected == 1` and `inserted == 5` at `:543-544` still hold unchanged.
  **Read this one before you edit it — it is the most instructive artifact in the goal.**
  The old downstream net caught only types SQLite *refuses* (a list raises
  `ProgrammingError`); types SQLite silently *converts* — `true`, `false`, `1e20` — sailed
  through and double-billed. The test's name asserts the hole was closed while covering
  only the half that was. Do not remove the `ProgrammingError` coverage from the file:
  `_RECORD_DATA_ERRORS` still needs `sqlite3.ProgrammingError` for the
  `user_email={"a":1}` case, so keep a case that still exercises it.

- **`tests/test_transcript_hook.py:109-122`** — `test_ac1_only_desktop_entrypoint_ships`,
  broken by task 04 Part A. Asserts `len(shipped) == 1` and desktop-only, which directly
  contradicts shipping `cli`/`claude-vscode`. Under correct behavior 2 of the fixture's 3
  rows ship (the third is still withheld by the pre-existing 30s trailing-group rule).
- **`tests/test_transcript_hook.py:489-503`** —
  `test_ac6_running_twice_ships_each_record_once`, same fixture and root cause.
- **NOT in this set:** `test_ac7e_forward_only_install_watermark`. Task 04's fix cycle 1
  drops the `install_ts` reset, so this test must pass **unmodified**. If it still fails
  after that fix, that is a finding about the implementation, not a test to invert.

Rules for each:

- [ ] Invert it to the intended behavior, and **keep the old expectation alive as a
      negative case** — an entrypoint genuinely outside the allowed set (`claude-web`)
      must still reject with the unchanged reason string `invalid_entrypoint`. Deleting the
      rejection coverage instead of moving it is the failure mode here.
- [ ] Touch no other line in those three files. `git diff` on each must show only the
      inverted hunk plus its new negative case.
- [ ] Cross-check against task 03's and task 04's reports, which are required to list every
      pre-existing test they break, with file:line. Invert exactly that set. If their lists
      name a test **not** in the seven above, stop and report it rather than editing — an
      unexpected break is a finding about the implementation, not a test to fix.

## Requirements (exhaustive — the evaluator verifies every item)

- [ ] One test per acceptance criterion: task 01 (1-7), task 02 (1-15), task 03 (1-21),
      task 04 (1-19), task 06 (1-9). Task 01's criteria are command-shaped — cover them as tests that
      parse the config files and assert their values, not by shelling out to grep.
- [ ] Naming: `test_<NN>_<criterion>_<what_it_pins>` so a failure maps to a criterion
      without opening the map.
- [ ] `tests/COVERAGE_MAP.md` gains a section for this goal in the format the previous
      goal's section established. Every criterion id present, zero dead ids, zero
      unreferenced new tests. Report the three counts.

### Testability traps — handle these deliberately

- [ ] **`sqlite3.Connection.execute` cannot be monkeypatched** — it is an immutable C type
      and `monkeypatch.setattr(conn, "execute", ...)` raises. For task 02's criteria 5, 6,
      7 and 11 use the delegating wrapper that already exists as `_ExecuteSpy` in
      **`tests/test_dedupe_counter.py:57`** (used at `:392`, `:467`, `:492`) — *not* in
      `test_reconcile.py`. Reuse it; do not reinvent it, and do not assert on SQL text as a
      substitute for behavior.
- [ ] **Freeze time; never `sleep`.** A `_FakeClock` already exists at
      `tests/test_dedupe_counter.py:80`. Use it (or the same approach) for the quarantine
      boundary, `stale_seconds` arithmetic, the future-timestamp clamp, and task 04's
      criteria 3 and 13 two-run sequences. A wall-clock-dependent test is a defect even
      when it passes.
- [ ] **Task 02 criterion 15 needs `setlimit`, and it is the only trap here that cannot
      be caught any other way.** Apply
      `conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)` to the store's
      connection before the call. This machine's real cap is 32766, so a test without
      `setlimit` passes against a statement that would raise on the production host.
- [ ] **Task 02 criteria 13/14 are the C1/C2 guards.** Criterion 13's cost-only session
      must be built with `insert_cost_datapoint` **alone**, and criterion 14's newer cost
      row likewise -- a fixture that also inserts a token row makes both pass vacuously.
- [ ] **Task 02 criterion 11 must not use `PRAGMA data_version` or file size.** The Phase 3
      evaluator demonstrated both are unchanged across a same-connection `INSERT` +
      `commit()` (8192 -> 8192, 1 -> 1). Use the `_ExecuteSpy` write-verb assertion plus a
      full-file SHA-256 taken after commit and close.
- [ ] **The `entrypoint IS NULL` OTLP row (task 02, criterion 9) must be created through
      `insert_datapoint`, not raw SQL.** The criterion exists because real OTLP rows carry
      a NULL entrypoint; a raw `INSERT` setting the column explicitly would test a shape
      that never occurs, and the criterion would pass while the guard was broken in
      production.
- [ ] **Task 03 criterion 10 asserts counts over both tables.** Capture
      `SELECT COUNT(*)` from `token_usage` *and* `cost_usage` before and after, and assert
      equality. "No exception raised" and "the response says rejected" both pass against an
      implementation that inserts anyway.
- [ ] **Task 03 criteria 1 and 4 assert the key *set*.** `assert "status" in body` passes
      against a body that also leaks freshness. Compare `set(body) == {...}`.
- [ ] **`receiver.AUTH_TOKEN` is read at module import**, so `monkeypatch.setenv` alone
      does not take effect. `tests/test_receiver.py:86-94` already solves this with
      `no_auth` / `with_auth` fixtures that patch the module attribute — reuse them. Note
      that `no_auth` is exactly the posture under which task 03 criterion 1 must hold, so
      test the unauthenticated body under **both** token states, not just one.
- [ ] **Task 04 criterion 3 is the trap.** The natural implementation marks a skipped
      session resolved, which makes every CLI session ship never and look fine. Write it as
      one test with both halves — withhold, advance the frozen clock, assert the record
      appears — and assert `resolved` and `examined_mtime` **by name**, so the test would
      fail if state were advanced.
- [ ] **Task 04 criterion 13/14 (replay) must assert the flag write happens before the
      POST.** Order is the whole safety property. A mock that raises on POST and an
      assertion that the flag is nonetheless persisted is the way to pin it.

### Isolation

- [ ] Every store is a `tmp_path` file. No test reads or writes `data/otel.db`,
      `data/analytics.db`, the real `~/.claude`, or the real state file.
- [ ] No live network call. The sweeper's POST is mocked; the receiver is exercised through
      its handler or a loopback server bound to **port 0**, never a fixed port.
- [ ] `tests/conftest.py`, `tests/test_otel_store.py`, `tests/test_reconcile.py` and
      `tests/test_dedupe_counter.py` are **byte-unmodified**.
      The only pre-existing edits anywhere are the seven hunks named above.
- [ ] If a pre-existing test outside those seven fails, that is a genuine finding in tasks
      01-04 — report it, do not edit it.
- [ ] Standard library plus `pytest` only.

## Acceptance Criteria

1. `python -m pytest tests/test_store_reads.py tests/test_receiver_health.py tests/test_cli_backfill.py -q`
   passes with zero failures and zero skips — verification: command output
2. `python -m pytest tests/ -q` passes. Report the final count against the 331 baseline and
   account for the delta explicitly: new tests added, plus any net change from the seven
   inverted assertions — verification: command output
3. `git diff --stat tests/` shows exactly five pre-existing files modified
   (`COVERAGE_MAP.md`, `test_transcript.py`, `test_receiver.py`,
   `test_integration_desktop.py`, `test_transcript_hook.py`) and three new files — verification: command output
4. `git diff tests/test_transcript.py tests/test_receiver.py tests/test_integration_desktop.py`
   shows only the seven inverted hunks and their new negative cases. Paste the diff in the report
   — verification: command output
5. Each of the three inverted files still contains a test asserting `invalid_entrypoint`
   for an entrypoint outside the allowed set:
   `grep -c invalid_entrypoint` is non-zero in each — verification: command output
6. `COVERAGE_MAP.md` has an entry for all **71** criteria (7 + 15 + 21 + 19 + 9), zero dead
   node ids, zero unreferenced new tests. Report all three counts — verification: command
   output
7. The eleven trap mitigations above are each present, verified by
   `grep -n "_ExecuteSpy\|_FakeClock\|no_auth\|with_auth\|sha256\|cost_usage\|examined_mtime" tests/test_*.py`
   returning a hit in the expected file for each — verification: command output
8. Each of these seven mutations, applied to a **scratchpad copy** of the tree, is caught by
   at least one test, and you report which test caught each: (a) drop the
   `usage_source='otlp'` predicate from `sessions_with_otlp_rows`; (b) remove the
   `claude-desktop` quarantine exemption; (c) restore `row["entrypoint"] = <constant>` in
   `transcript.py`; (d) make `too_recent` resolving in the sweeper; (e) move the replay's
   flag write to *after* the first POST; (f) **narrow `sessions_with_otlp_rows` back to
   `token_usage` only** -- the double-billing path, and the mutation that pre-existing
   coverage would miss entirely; (g) omit `examined_mtime` from the replay's reset, which
   criterion 13 must catch rather than silently pass. Never mutate the repo — verification: command
   output

## Files to Read

- `tests/COVERAGE_MAP.md` — the format and the previous goal's section
- `tests/test_dedupe_counter.py` — `_ExecuteSpy` (`:57`) and `_FakeClock` (`:80`)
- `tests/test_receiver.py` — the `no_auth` / `with_auth` fixtures (`:86-94`) and the
  established way to drive the receiver's handler
- `tests/test_transcript_hook.py` — the established sweeper fixture shape (read-only)
- `tests/conftest.py` — existing fixtures (read-only)
- All four task files in this goal, plus tasks 03's and 04's reports (for their lists of
  broken pre-existing tests)
- The four implementation files listed in `reads`

## Files to Create / Change

- `tests/test_store_reads.py` — task 02
- `tests/test_receiver_health.py` — task 03 (both parts)
- `tests/test_cli_backfill.py` — task 04 plus task 01's config assertions
- `tests/COVERAGE_MAP.md` — new section (targeted insertion; leave every other line alone)
- `tests/test_transcript.py`, `tests/test_receiver.py`,
  `tests/test_integration_desktop.py`, `tests/test_transcript_hook.py` — the seven
  inverted hunks, nothing else

## Constraints

- Must: mock every external service; bind any server to port 0.
- Must: use `tmp_path` for every database and state file.
- Must NOT: edit any pre-existing test file beyond the seven named hunks, or any file under
  `billing/`, `client-package/`, `deploy/`, or `pilot-package/`.
- Must NOT: delete the `invalid_entrypoint` rejection coverage — move it to a genuinely
  out-of-set entrypoint instead.
- Must NOT: weaken an assertion to make a test pass. A failure against shipped code is a
  finding to report.
- Must NOT: assert on SQL text as a substitute for behavior.
- Must NOT: add a third-party test dependency.

## Verification

- `python -m pytest tests/test_store_reads.py tests/test_receiver_health.py tests/test_cli_backfill.py tests/test_transcript.py tests/test_receiver.py tests/test_integration_desktop.py -q`
  -> passing
- Do **not** run the full suite; the orchestrator runs it at Phase 5.
- Report the final test count, the three `COVERAGE_MAP.md` counts, the diff from criterion
  4, and the five mutation results.
