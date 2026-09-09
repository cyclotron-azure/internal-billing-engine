# Task 00: Test scaffold + pre-change billing baseline

## Objective

`tests/` exists with shared fixtures, and the CURRENT billing output is captured as a golden baseline
**before any production file is modified**. This task exists for two reasons: it gives tasks 01–06 a
place to write targeted tests so no change lands on live billing code without assertions, and it
captures the pre-change `bill.py` behavior that task 05 must prove it did not regress — a comparison
that is impossible to make after `bill.py` has already been rewritten.

## Dependencies

- none. **This task runs FIRST, before any production file changes.**

```yaml
# --- task ownership contract ---
writes:
  - tests/conftest.py
  - tests/golden/bill_otlp_baseline.txt
  - tests/golden/README.md
reads:
  - billing/otel/otel_store.py
  - billing/otel/bill.py
  - billing/otel/rating.py
depends_on: []
owner: test-writer
rewrite_semantics: whole-file
eval_depth: full
```

## Requirements (exhaustive — the evaluator verifies every item)

- [ ] `tests/conftest.py` provides a fixture returning a temporary SQLite database path under
      `tmp_path`. No fixture may touch `data/otel.db` or any shared path two tests could race on.
- [ ] A fixture builds a **pre-change-schema** database — the schema exactly as it exists in
      `otel_store.py` at this moment, before task 01 — so task 01's migration test exercises the real
      legacy path rather than an already-correct schema. Capture the current `SCHEMA` text verbatim
      into the fixture rather than importing it, since task 01 will change the imported value.
- [ ] A fixture builds a synthetic transcript JSONL in `tmp_path`, parameterised by entrypoint, so
      tests can produce `claude-desktop`, `cli`, and `claude-vscode` records, plus a deliberately
      malformed trailing line.
- [ ] **The transcript fixture MUST include the cumulative multi-block shape, because it is the
      dominant real shape and the one that produces wrong invoices.** Measured on real transcripts: 402
      usage-bearing rows carry only 187 distinct `requestId`s; 149 repeat, up to 5x. Rows sharing a
      `(requestId, message.id)` are cumulative snapshots of ONE API request — `input_tokens`,
      `cache_creation_input_tokens`, and `cache_read_input_tokens` hold constant while `output_tokens`
      grows. The terminal block is identified by the **highest `apiBlockIndex`** (tie-break: file order,
      last wins) — NOT by `stop_reason`, which is multi-valued for 108 of 230 real groups and absent
      from 3. Reproduce that exactly, using this real observed pair as the model:

          apiBlockIndex=0  stop_reason=None      input=2  output=5    cache_creation=13984  cache_read=35774
          apiBlockIndex=1  stop_reason=tool_use  input=2  output=209  cache_creation=13984  cache_read=35774

      The correct total for that request is the TERMINAL block: input=2, output=209,
      cache_creation=13984, cache_read=35774. Summing the two over-bills; keeping the first
      under-bills output by 97%.
- [ ] The fixture also includes an exact-duplicate pair (same `requestId`, same `message.id`, identical
      usage) — the other real repeated shape, 82 of the 149 repeat groups. **Both rows must carry a
      non-null `stop_reason`**, because that is the shape of the ONLY real `claude-desktop` request
      observed: `abi=0 stop=end_turn out=543` / `abi=1 stop=end_turn out=543`. A fixture whose duplicate
      pair has a `None` on the non-terminal row would never exercise the real desktop case.
- [ ] **The fixture builds a projects TREE, not a single file, and it must reproduce the REAL nested
      layout exactly:**

          <projects_root>/
            <project_dir_a>/
              <session_id>.jsonl                                  <- main transcript
              <session_id>/subagents/agent-<agentId>.jsonl        <- sidechain, ONE LEVEL DEEPER
            <project_dir_b>/
              <other_session_id>.jsonl                            <- a second project directory

      Sidechain rows carry the parent's `sessionId` and `entrypoint` and are flagged
      `isSidechain: true`. The nesting is not cosmetic: measured at Claude Code `2.1.259`, a recursive
      walk finds 9 files where a flat per-project-directory glob finds 4, missing every sidechain file
      and 30.0% of spend. An earlier draft of this task specified a FLAT fixture, which would have made
      task 06's subagent regression test pass green against a layout that does not exist. **If this
      fixture is built flat, the test it exists to support is worthless.**
- [ ] The second project directory (`<project_dir_b>`) exists so tasks 06 and 07 can test the
      cross-directory sweep — a crashed session in one project directory being shipped by a hook run
      that fires in another. Every desktop scratch session gets its own project directory in reality,
      so this is the normal case, not an edge case.
- [ ] The fixture also provides a transcript whose TRAILING request group holds only
      `apiBlockIndex=0` (an in-flight session), plus the terminal row available separately for a test
      to append, so the in-flight completeness rule in task 06 is testable.
- [ ] Published expected totals cover three cases: main-file-only, sidechain-only, and **combined**.
      Tasks 06 and 07 assert against the combined figure and assert the result is not the
      main-only figure.
- [ ] The fixture exposes the **expected correct totals** as data alongside the file it builds, so
      tasks 02, 06, and 07 can assert exact token counts rather than each re-deriving them and
      re-deriving them wrongly.
- [ ] A fixture seeds OTLP-shaped `token_usage` and `cost_usage` rows, and `session_repo_timeline`
      rows, so attribution and billing tests have realistic data.
- [ ] `tests/golden/bill_otlp_baseline.txt` contains captured stdout from the CURRENT `bill.py`, run
      against a deterministic OTLP-only fixture store, with the exact command and the fixture's
      construction recorded in `tests/golden/README.md` so it is reproducible and reviewable.
- [ ] **Name explicitly which fixture backs the golden baseline, and it must NOT be the frozen
      legacy-schema fixture.** Use the seeded-OTLP-rows fixture built on the CURRENT `SCHEMA`, which
      task 01 will migrate normally. If the baseline were captured against the frozen legacy schema, then
      once task 04's branch references `usage_source`, task 05's replay of this baseline would raise
      `OperationalError: no such column` instead of comparing output — the golden gate would fail for a
      reason unrelated to billing.
- [ ] The baseline capture is deterministic: fixed timestamps, fixed markup, fixed model names. No
      wall-clock time, no random ids, no dependence on machine locale.
- [ ] `tests/golden/README.md` states plainly what the baseline is for, that it encodes PRE-change
      behavior, and the exact circumstances under which it may legitimately be regenerated.
- [ ] No production file is modified. This task's write fence is tests only.
- [ ] No dependency beyond `pytest`.
- [ ] Note for the implementer: `pytest` is not installed in this environment. Per
      `.claude/ORCHESTRATION.md`, run `python -m pip install pytest` once before the first test run.
      If installation is unavailable, report that plainly rather than faking a passing run.

## Acceptance Criteria

1. `python -m pytest tests/ -q` runs and collects successfully with zero tests failing (a scaffold with
   no tests yet collecting cleanly is a pass) — verification: command output.
2. The pre-change-schema fixture produces a database whose `PRAGMA table_info(token_usage)` lacks
   `usage_source` and `entrypoint` — verification: unit test asserting their absence, proving the
   fixture really is the legacy schema.
3. The transcript fixture produces records for all three entrypoints plus a malformed line —
   verification: unit test parsing the generated file and asserting the mix.
3b. The transcript fixture contains a cumulative multi-block request (constant input/cache, growing
   output) and an exact-duplicate pair with non-null `stop_reason` on both rows, and its published
   expected totals equal the TERMINAL block's values selected by highest `apiBlockIndex` —
   verification: unit test asserting the fixture's own shape and that its declared expected totals are
   neither the sum nor the first block. A fixture that does not contain these shapes cannot catch the
   defects it exists to catch.
3c. The fixture tree places its sidechain file at `<project_dir>/<session_id>/subagents/agent-*.jsonl`
   — asserted by path, not merely by existence — contains a second project directory, and its published
   combined total is strictly greater than its main-only total — verification: unit test asserting the
   exact relative paths and that the three published totals (main, sidechain, combined) are
   self-consistent.
3d. A FLAT glob of the fixture's project directory yields strictly fewer files than a recursive walk of
   the fixture tree — verification: unit test. This asserts the fixture actually reproduces the nesting
   that makes task 06's anti-fixture criterion meaningful; a flat fixture fails here immediately rather
   than silently weakening a downstream test.
4. `tests/golden/bill_otlp_baseline.txt` is non-empty and contains the current basis line — verification:
   command output showing the captured file's contents.
5. Re-running the baseline capture produces byte-identical output — verification: run twice, diff, no
   differences. This proves determinism; a non-deterministic baseline is worse than none.

## Files to Read

- `billing/otel/otel_store.py` — the CURRENT `SCHEMA` to freeze into the legacy fixture, and the shape of
  `token_usage` / `cost_usage` / `session_repo_timeline` rows.
- `billing/otel/bill.py` — how to invoke it and what its output looks like, for the golden capture.
- `billing/otel/rating.py` — the markup default, so the baseline is captured at a pinned markup.
- `.claude/skills/test-ladder/SKILL.md` — the convention map and rung rules.
- `.claude/agents/test-writer.md` — mocking boundaries and the dependency budget.

## Files to Create / Change

- `tests/conftest.py` — shared fixtures: tmp db path, legacy-schema db, synthetic transcript, seeded OTLP rows.
- `tests/golden/bill_otlp_baseline.txt` — captured pre-change `bill.py` output.
- `tests/golden/README.md` — what the baseline is, and when regenerating it is legitimate.

## Constraints

- Must: run before any production change; capture the baseline from unmodified code.
- Must: keep fixtures deterministic and isolated to `tmp_path`.
- Must NOT: modify any file under `billing/`, `deploy/`, or `client-package/` — this task is tests-only.
- Must NOT: import `SCHEMA` from `otel_store.py` for the legacy fixture; task 01 changes it, which would
  make the "legacy" fixture silently become the new schema and destroy the migration test's value.
- Must NOT: add any dependency beyond `pytest`.

## Verification

- Targeted test command: `python -m pytest tests/ -q`
- Baseline determinism: capture twice and diff.
