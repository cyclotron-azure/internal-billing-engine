# Task 07: Integration coverage + full-suite closer

## Objective

The end-to-end desktop path is proven with an integration test, `export.py` gains the coverage it has
never had (and which task 04's change now makes load-bearing), a criterion-to-test traceability map
exists as a checkable artifact, and the full suite runs green. This is the goal's designated **closer
task**: the rung-3 full-suite run is a written mandate of this task, not an inherited default.

## Dependencies

- all (00–06)

```yaml
# --- task ownership contract ---
writes:
  - tests/test_export.py
  - tests/test_integration_desktop.py
  - tests/COVERAGE_MAP.md
reads:
  - billing/otel/otel_store.py
  - billing/otel/transcript.py
  - billing/otel/receiver.py
  - billing/otel/attribute.py
  - billing/otel/bill.py
  - billing/otel/invoice.py
  - billing/otel/export.py
  - deploy/claude-transcript-usage.py
  - tests/conftest.py
depends_on:
  - "00-test-scaffold"
  - "01-store-schema"
  - "02-transcript-payload"
  - "03-receiver-endpoint"
  - "04-attribution"
  - "05-billing-basis"
  - "06-client-hook"
owner: test-writer
rewrite_semantics: whole-file
eval_depth: full
```

## Requirements (exhaustive — the evaluator verifies every item)

- [ ] **Discriminate `_AS_OF` from `_FIRST` in the attribution join.** Task 04's evaluation found that no
      test in the goal distinguishes the two arms of `attribute.py`'s COALESCE chain: mutating either
      `_AS_OF` or `_FIRST` to NULL leaves the whole suite green, because every seeded session carries
      exactly ONE timeline entry, so both subqueries return the same value. That was correctly ruled out
      of scope for task 04 — those subqueries are pre-existing and unmodified, and `resolved_repo()` was
      proven unchanged across 324 rows — but it is a genuine hole in the goal's overall coverage, and
      this task owns the integration suite.
      **Status update — `_AS_OF` is now covered; `_FIRST` is NOT.** Task 04's hardening seeded two
      genuinely-ordered, different timeline entries per test, so neutering `_AS_OF` to `SELECT NULL` now
      fails `tests/test_attribute.py`. Orchestrator-verified. But neutering `_FIRST` still leaves all 12
      green, because with every entry positioned BEFORE the datapoint, `_AS_OF` always answers and
      `_FIRST` never executes.
      So the remaining gap is specifically the `_FIRST` fallback: the case where a datapoint's `ts`
      PRECEDES every timeline entry for its session. That is not exotic — `attribute.py`'s own docstring
      says it exists for "export-interval rounding, small clock skew", i.e. a metric datapoint arriving
      timestamped just before the session's first hook fired. Seed exactly that shape — a datapoint
      whose `ts` is earlier than the session's earliest timeline entry — and assert it resolves to that
      earliest entry rather than falling through to the wrapper tag.
      Acceptance: mutating `_FIRST` to NULL must turn this test red. Without it, the arm that rescues
      clock-skewed datapoints from being mis-attributed is defended by nothing.

- [ ] **Systemic-failure alarm: treat "every accepted record rejected with a `store_error:` reason" as an
      alarm, not as ordinary client-data noise.** Task 03's receiver contains per-record failures and
      returns 200 with a `rejected` count — correct behavior, and the fix for a defect that previously
      dropped whole batches. But two residual paths would present as a cheerful 200 with 100% rejections:
      a `sqlite3.ProgrammingError("Cannot operate on a closed database")`, and a receiver-side `KeyError`
      if a future change to `map_record`'s return keys breaks the contract. Task 06's hook treats a
      200-with-rejections as PERMANENT (AC 7c) — it advances state without retrying — so either path
      would silently discard all desktop billing while every component reported success.
      The discriminating signature is cheap: `accepted > 0 AND rejected == len(accepted) AND every reason
      starts with 'store_error:'`. Ordinary bad client data does not produce a 100% store-error rate.
      Surface it as a loud failure in the integration run, with a test that seeds the condition.

- [ ] **Contract note carried from task 01 — `transcript_key` does NOT strip; the insert methods do.**
      If this task computes an expected key by calling `transcript_key(...)` directly, pass an
      already-stripped `request_id`, or the computed key will not match what the store actually wrote.
      Verified: `transcript_key("s", " req-1 ", "input") != transcript_key("s", "req-1", "input")`, while
      `insert_datapoint` normalizes first and treats the two as the same row. The failure mode is a loud
      test mismatch rather than wrong data, but it will look like a store bug when it is not.

- [ ] **A cross-task key seam surfaced by task 06a's evaluation — only integration can catch it.**
      The hook groups usage by the triple `(sessionId, requestId, message.id)`, but the hook's own
      `_mark_resolved` keys by `request_id` ALONE, and task 02's server-side dedupe keys by
      `(session_id, request_id)`. So if one session ever produces two groups sharing a `requestId` but
      differing in `message.id`, the hook ships two records, the server rejects the second as
      `duplicate_request_id`, and the hook then marks that `request_id` resolved — losing the second
      group's tokens permanently, with a cheerful 200 and no retry.
      Neither side is individually wrong: the hook follows the grouping this goal mandated, and the
      server follows the key task 01 froze. The defect lives in the seam, which is why no single task's
      tests could find it. **Measured on real transcripts: 0 occurrences across 314 request groups**, so
      this is a latent risk rather than an active loss — but it is exactly the class of bug an
      integration suite exists to surface.
      Seed that shape deliberately (one session, two groups, same `requestId`, different `message.id`)
      and assert what actually happens end to end. If tokens are lost, report it as a FINDING with the
      amount — do not fix it here; the fix belongs to whichever task's key must change, and that is the
      orchestrator's routing decision.

**Integration coverage**

- [ ] An end-to-end test drives the whole desktop path in-process: task 00's synthetic projects TREE
      (main transcript plus a sidechain at `<session_id>/subagents/agent-*.jsonl`, across two project
      directories) → the hook's payload builder → the real server-side validator → the receiver handler
      → the store → `bill.py`. Each task tested its own seam; nothing has yet tested that the seams meet.
- [ ] The end-to-end assertion uses task 00's published **combined** expected total, and asserts the
      billed figure is NOT the main-file-only total. A test driven from a single transcript file would
      pass at roughly two-thirds of the correct amount.
- [ ] **The integration test asserts the EXACT billed amount, not merely a non-zero one.** Using task
      00's cumulative multi-block fixture and its published terminal-block totals, assert the dollar
      figure `bill.py` reports, computed independently from `RatingService` and the markup. "Non-zero"
      is precisely what let a 2.28x over-bill and an 8.6% under-bill pass every earlier version of this
      plan; presence is not correctness on a billing system.
- [ ] A companion assertion pins the negative cases: the reported amount is NOT the naive sum of the
      cumulative blocks, and NOT the first-block value.
- [ ] A second integration case covers the scratch-workspace path: a desktop record with `repo_raw=''`
      reaches billing classified as `desktop-scratch`.
- [ ] A third covers non-duplication: a store containing OTLP rows for a CLI session and transcript rows
      for a desktop session bills each exactly once, and the overlap detector stays silent.

**export.py coverage**

- [ ] `tests/test_export.py` covers `export.py`, which no task in this goal owns yet is put at risk by
      task 04's change to `attribution_source` — `export.py:78` calls `resolved_view('cost_usage')`.
- [ ] Asserts both lake CSVs still build after all changes, and that transcript-sourced rows appear in
      them with the documented UTC date columns present and correct.
- [ ] Asserts explicitly that `export.py` currently emits NO `cost_source` column, so rate-card estimates
      and Anthropic actuals are indistinguishable downstream in Fabric. `goal.md` lists this as accepted
      Out of Scope; the test pins the accepted state so a future change to it is deliberate and visible
      rather than accidental.

**Traceability**

- [ ] `tests/COVERAGE_MAP.md` maps every acceptance criterion in tasks 00–07 to the test that verifies it,
      by task, criterion number, and test node id. A criterion with no test is listed as a GAP rather than
      quietly omitted.
- [ ] The map is a committed artifact, not a claim in a completion report — a reviewer can check it
      against the suite without rerunning anything.

**Closer mandate (rung 3)**

- [ ] **This task runs the full suite: `python -m pytest -q`.** Stated here as a requirement, which is
      what makes the rung-3 run legitimate under the `test-ladder` closer-task carve-out; it does not
      replace the orchestrator's own Phase 5 Quality Checks run.
- [ ] The full suite passes green before this task reports complete.
- [ ] The suite passes twice consecutively with no manual cleanup, proving no cross-test state leakage.
- [ ] This project uses **`uv`**, not `pip`. `pytest 9.1.1` is already installed in the active
      interpreter. If a future environment lacks it, the command is `uv pip install pytest`, or
      `uv run --with pytest python -m pytest` to run with nothing persisted. Do not invoke `pip`.
      If pytest is unavailable and cannot be installed, report that plainly — never describe a suite
      as passing when it was not run.

**Hygiene**

- [ ] No test performs live network I/O; nothing reaches the Anthropic Analytics API, ADLS Gen2, OneLake,
      or Fabric; no test binds a real port.
- [ ] Every test needing a database uses `tmp_path` or `:memory:`; none writes to `data/otel.db`.
- [ ] Tests assert outcomes. "No exception was raised" is not an assertion, and no test mocks the unit
      under test.
- [ ] No dependency beyond `pytest`.

## Acceptance Criteria

1. `python -m pytest -q` passes from the repo root — verification: command output, exit code 0.
2. Two consecutive full-suite runs both pass with no manual cleanup — verification: command output from both.
3. The end-to-end desktop test proves the EXACT billed amount from transcript directory to `bill.py`
   output, and asserts it is none of: the naive sum of cumulative blocks, the first-block value, or the
   main-file-only total (which omits subagent usage) — verification: the named test passing. These three
   negatives are the three billing errors this plan's earlier drafts actually contained.
4. The scratch-workspace case reaches billing as `desktop-scratch` — verification: the named test passing.
5. A mixed OTLP + transcript store bills each session exactly once and the overlap detector stays silent —
   verification: the named test passing.
6. `export.py` builds both CSVs after all changes — verification: the named test passing.
7. `tests/COVERAGE_MAP.md` exists and every criterion in tasks 00–07 appears with a test node id or an
   explicit GAP entry — verification: read the file; spot-check three mapped node ids actually exist in the
   suite by running them.

## Files to Read

- Every task file 00–06 in this goal directory — their acceptance criteria are the input to the coverage map.
- The modules in the ownership contract's `reads` — for real signatures and behavior.
- `.claude/skills/test-ladder/SKILL.md` — rung rules and the closer-task carve-out.
- `.claude/agents/test-writer.md` — mocking boundaries and the dependency budget.
- `README.md` — "Shipping invoices to a data lake" for the exact lake CSV column list.

## Files to Create / Change

- `tests/test_export.py` — lake CSV build, UTC date columns, the pinned no-`cost_source` state.
- `tests/test_integration_desktop.py` — end-to-end desktop path, scratch case, non-duplication case.
- `tests/COVERAGE_MAP.md` — criterion → test traceability.

## Constraints

- Must: mock all external services; use `tmp_path`; assert outcomes.
- Must: keep `pytest` the only dependency.
- Must NOT: bind a real port; write to `data/otel.db`; add a mocking library.
- Must NOT: modify any production file, or any test file owned by tasks 00–06. If a defect is found in
  one, report it as a finding — do not fix it here. Fixing across a write fence hides which task was wrong.

**Out-of-fence failure escalation.** This task must report a green full suite but may not edit the files
that would make it green. If rung 3 fails inside a file owned by tasks 00–06: stop, do not edit, and
report the failing test node id, the owning task, and the failure output. The orchestrator routes the fix
to that task's owner and re-runs the closer. Reporting a red suite honestly is the correct outcome —
describing an unrun or failing suite as passing is an auto-fail.

## Verification

- Targeted: `python -m pytest tests/test_export.py tests/test_integration_desktop.py -v`
- Rung 3 closer (mandated by this task): `python -m pytest -q`, run twice.
