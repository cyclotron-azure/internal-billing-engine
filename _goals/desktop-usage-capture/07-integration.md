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
- [ ] `pytest` is not installed in this environment by default. Run `python -m pip install pytest` once
      first. If installation is unavailable, report that plainly — never describe a suite as passing
      when it was not run.

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
