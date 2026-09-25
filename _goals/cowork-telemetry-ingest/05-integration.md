# Task 05: Integration tests + isolation proof + closer

## Objective

An end-to-end test proving the Cowork pipeline works (synthetic payload in → resolved,
attributed row out), and — the goal's central, non-negotiable requirement — a proof that the
existing `claude_code` pipeline is byte-for-byte unchanged, by replaying task 00's baseline
against unmodified code paths.

## Dependencies

- 00-test-scaffold
- 01-cowork-store-schema
- 02-cowork-ingest-payload
- 03-cowork-receiver
- 04-cowork-reporting

```yaml
# --- task ownership contract ---
writes:
  - tests/test_cowork_integration.py
  - tests/test_cowork_isolation.py
depends_on:
  - "00-test-scaffold"
  - "01-cowork-store-schema"
  - "02-cowork-ingest-payload"
  - "03-cowork-receiver"
  - "04-cowork-reporting"
owner: test-writer
rewrite_semantics: whole-file
eval_depth: full   # reason: this task's replay test IS the proof of the goal's central,
                    # non-negotiable isolation claim; a weak or wrong assertion here would let
                    # the whole goal ship without ever having actually verified it.
reads:
  - billing/otel/cowork_store.py
  - billing/otel/cowork_ingest.py
  - billing/otel/cowork_attribute.py
  - billing/otel/cowork_receiver.py
  - billing/otel/cowork_records.py
  - billing/otel/otel_store.py
  - billing/otel/bill.py
  - billing/reconcile.py
  - tests/golden/cowork_isolation_baseline.txt
```

## Requirements (exhaustive — the evaluator verifies every item)

- [ ] `tests/test_cowork_integration.py`: a full round trip — build a synthetic
      `service.name="cowork"` OTLP payload with a `session.id` matching a fixture
      `otel.db`'s `session_repo_timeline` entry, POST it (or call the equivalent ingestion
      path directly) through `cowork_receiver.py` into a `CoworkStore`, then run
      `cowork_records.py`'s reporting path and assert the row appears with the CORRECT
      resolved repo. Repeat with a session id that has NO timeline entry and assert
      `attribution_source="absent"`.
- [ ] The same test file exercises re-sending an identical payload and asserts nothing new is
      inserted (dedupe holds end to end, not just at the unit level tested in task 01).
- [ ] The same test file exercises a rejected payload (`service.name="claude-code"` or an
      unrecognized metric) through the full receiver path and asserts zero rows land in
      `CoworkStore` and the response reflects the rejection.
- [ ] The same test file also asserts a rejected record produces a log line in the Cowork
      receiver's own log file (task 03's logging requirement), exercised end to end rather
      than only at the unit level.
- [ ] No test in either new file binds a real network socket — reuse the `socket.socketpair()`
      harness established in task 03.
- [ ] `tests/test_cowork_isolation.py`: replays task 00's exact baseline-capture calls (the
      `bill.py` invocation, the mocked-`reconcile.py` run, and the three
      `ingest_metrics_payload` calls) against the SAME fixture `otel.db`, now that every file
      in this goal exists, and asserts the output/return values are identical to what
      `tests/golden/cowork_isolation_baseline.txt` recorded. This is the automated test that
      proves the goal's hard behavioral-isolation claim — that using the existing pipeline's
      code, unmodified, produces unmodified results. It does NOT need to (and does not)
      independently prove the FILES are byte-identical; that is a separate, simpler check,
      done as a manual step below, precisely BECAUSE the `claude_code` pipeline is still being
      actively edited outside this goal — a permanent automated file-hash test on
      `receiver.py`/`otel_store.py`/etc. would break the first time a legitimate, unrelated
      edit lands on one of them, for a reason that has nothing to do with this goal's own
      correctness.
- [ ] This task's write fence is `tests/` only — it CANNOT independently prove no production
      file changed; only a `git status`/`git diff` against the actual repo state can. That
      check is Acceptance Criterion 4 below, run once as this task's closing manual
      verification step, not encoded as a unit test.

## Acceptance Criteria

1. `python -m pytest tests/ -q` passes in full — verification: command output.
2. The end-to-end synthetic payload test asserts a specific, correct repo string (not merely
   "non-null") for the timeline-matched case, and `attribution_source="absent"` for the
   unmatched case — verification: test assertions, read directly.
3. The isolation replay test fails (by design, verified once during development and then left
   passing) if a single byte/value of ANY of the three replayed baselines (`bill.py` stdout,
   the mocked `reconcile.py` run, the three `ingest_metrics_payload` results) changes —
   verification: read the test and confirm it does a real content/value comparison against
   `tests/golden/cowork_isolation_baseline.txt`, not a weaker check like "no exception raised".
4. `git status --porcelain -- billing/otel/receiver.py billing/otel/otel_store.py
   billing/otel/attribute.py billing/otel/normalize.py billing/otel/transcript.py
   billing/otel/records.py billing/otel/sample_payload.py billing/reconcile.py
   billing/otel/bill.py billing/report.py` is empty — verification: command output, captured
   as this task's closing manual verification step.

## Files to Read

- `tests/golden/cowork_isolation_baseline.txt` and `cowork_isolation_README.md` — the exact
  baseline and command this task replays.
- Every Cowork module built in tasks 01–04 — the full pipeline this task wires together
  end to end.
- `billing/otel/otel_store.py`, `billing/otel/bill.py`, `billing/reconcile.py` — confirmed
  unmodified; read to build the isolation-replay assertions.

## Files to Create / Change

- `tests/test_cowork_integration.py`
- `tests/test_cowork_isolation.py`

## Constraints

- Must: replay task 00's baseline verbatim, same fixture, same command.
- Must: assert exact values, not just absence of exceptions.
- Must NOT: modify any production file — this task is tests-only.
- Must NOT: add any dependency beyond `pytest`.

## Verification

- Targeted test command: `python -m pytest tests/ -q`
- Manual verification evidence to capture: output of the `git status --porcelain` command
  listed in Acceptance Criteria item 4, run from the repo root at the end of this task.
