# Task 04: Cowork reporting + synthetic payload generator

## Objective

Two small CLI tools so the Cowork pipeline can be verified by a human without touching the
existing `claude_code` reporting tools: `billing/otel/cowork_records.py` (dumps stored
Cowork rows with resolved attribution) and `billing/otel/cowork_sample_payload.py` (generates
and sends a synthetic Cowork OTLP payload, mirroring `sample_payload.py`'s role for the
existing pipeline, including known-bad variants for exercising the fail-closed path).

## Dependencies

- 00-test-scaffold
- 01-cowork-store-schema
- 02-cowork-ingest-payload
- 03-cowork-receiver

```yaml
# --- task ownership contract ---
writes:
  - billing/otel/cowork_records.py
  - billing/otel/cowork_sample_payload.py
  - tests/test_cowork_records.py
depends_on:
  - "00-test-scaffold"
  - "01-cowork-store-schema"
  - "02-cowork-ingest-payload"
  - "03-cowork-receiver"
owner: implementer
rewrite_semantics: whole-file
eval_depth: light   # reason: reporting-only tooling with no write path to any store other than
                    # its own already-isolated CoworkStore; mirrors existing records.py/
                    # sample_payload.py patterns closely, low interface-consumer risk.
reads:
  - billing/otel/records.py
  - billing/otel/sample_payload.py
  - billing/otel/cowork_store.py
  - billing/otel/cowork_attribute.py
  - billing/otel/cowork_ingest.py
```

## Requirements (exhaustive — the evaluator verifies every item)

- [ ] `python -m billing.otel.cowork_records` (mirroring `records.py`'s ACTUAL CLI flags —
      read `records.py` first; it defines `--db`, `--repo`, `--limit`, not `--start`/`--end`
      — reuse whichever of those genuinely fit, add a new one only if this report needs
      filtering `records.py` doesn't already model) prints one line per stored Cowork usage
      row: at minimum `session_id`, `ts`, `model`, `token_type` or `cost_usd`, `user_email`,
      and the row's RESOLVED repo + `attribution_source` (computed at report time via
      `cowork_attribute.resolve_repo`, never read from a stored column — this store never
      persists a resolved repo, per task 01).
- [ ] Prefer opening the existing `otel.db` read-only connection ONCE per report run rather
      than once per row, where task 01's frozen `resolve_repo(session_id, ts, otel_db_path)`
      signature allows it without changing that signature (e.g. by calling
      `cowork_attribute._connect_ro` directly and reusing the connection across rows, if
      `cowork_attribute.py`'s internals allow that without modification). If task 01's frozen
      interface makes per-row calls the only option without touching that file, that's
      acceptable for now — do not modify task 01's frozen `resolve_repo` signature to
      accommodate this. Note whichever choice was made in the module docstring.
- [ ] The report clearly labels its output as Cowork data (e.g. a header line), so it can
      never be mistaken for `records.py`'s existing `claude_code` output if both are run in
      the same terminal session.
- [ ] The report accepts a `--otel-db` (or similarly named) flag pointing at the existing
      `otel.db` for the read-only attribution lookup, defaulting to `otel_store.DEFAULT_DB`'s
      value — but this flag is read-only-consumption; nothing here ever writes through it.
- [ ] **Before iterating rows, call `cowork_attribute.otel_db_reachable(otel_db_path)` once.**
      If it returns `False`, print a loud, unmistakable warning banner (e.g. `WARNING: could
      not reach <path> — every row below will show attribution_source=absent, which may mean
      "genuinely no timeline data" OR "this report couldn't read the database". Check
      --otel-db.`) before printing any rows. This is the fix for a real defect found in Phase 3
      review: without it, a wrong `--otel-db` path and "Cowork genuinely has no timeline
      entries" are visually indistinguishable in this report's output, defeating the goal's own
      stated verification purpose (Success Criteria: "which bucket real Cowork traffic lands
      in").
- [ ] `billing/otel/cowork_sample_payload.py` (mirroring `sample_payload.py`'s role) builds at
      least three synthetic payloads and can send them via HTTP to a running
      `cowork_receiver.py` instance (default `http://127.0.0.1:4319`, distinct from
      `sample_payload.py`'s existing target): (a) a valid `service.name="cowork"` payload with
      token + cost datapoints, (b) a payload with `service.name="claude-code"` to exercise the
      fail-closed rejection, (c) a payload with an unrecognized metric name. Print what was
      sent and the receiver's JSON response for each, so a human can eyeball the fail-closed
      behavior working end to end. This script's own manual/CLI usage is expected to bind a
      real port (that's the point — it drives a real running receiver process by hand); its
      AUTOMATED test (Acceptance Criterion 3) must not, per this repo's test-suite rule.
- [ ] `cowork_sample_payload.py` sends no auth token by default (mirroring
      `sample_payload.py`'s existing documented behavior of getting a 401 against an enforcing
      receiver) — the same "expected result, not a bug" property the current README documents
      for the existing sample script.
- [ ] Both new scripts are stdlib-only (`urllib.request` for the HTTP send, no `requests`).

## Acceptance Criteria

1. Running `cowork_records.py` against a `CoworkStore` seeded with a token row whose
   `session_id` matches a fixture `otel.db` timeline entry prints that row's resolved repo and
   `attribution_source="timeline"` — verification: unit/integration test capturing stdout.
2. The same tool against a row with no matching timeline entry prints `attribution_source="absent"`
   rather than a resolved repo — verification: unit test.
3. `cowork_sample_payload.py`'s three payload-building functions, exercised in a test through
   the SAME `socket.socketpair()` in-process harness task 03 established (call the payload
   builders directly and feed their output through the harness — do not spin up a real
   `cowork_receiver.py` process or bind a real port in this test), produce exactly one stored
   token row + one stored cost row from payload (a), and zero stored rows from payloads (b)
   and (c) — verification: integration test.
4. `git diff -- billing/otel/records.py billing/otel/sample_payload.py` is empty after this
   task — verification: command output.
5. Running the report with `--otel-db` pointed at a nonexistent path prints the warning banner
   BEFORE any row output, and every row still prints (as `absent`, per the fail-safe contract)
   rather than crashing — verification: unit test capturing stdout.
5b. Running the report with `--otel-db` pointed at a DIFFERENT, real, valid SQLite file that
   is not the real `otel.db` (e.g. a fresh `CoworkStore` db, which has no
   `session_repo_timeline` table) ALSO prints the warning banner — verification: unit test.
   This is the realistic wrong-path case (`cowork.db` sitting next to `otel.db`), not merely
   the nonexistent-path case in item 5.

## Files to Read

- `billing/otel/records.py` — the CLI/output shape to mirror. Read-only.
- `billing/otel/sample_payload.py` — the synthetic-payload/send pattern to mirror. Read-only.
- `billing/otel/cowork_store.py`, `billing/otel/cowork_attribute.py` — the frozen contracts
  this task's tools consume.

## Files to Create / Change

- `billing/otel/cowork_records.py`
- `billing/otel/cowork_sample_payload.py`
- `tests/test_cowork_records.py`

## Constraints

- Must: resolve attribution at report time only, never persist it.
- Must: label output unambiguously as Cowork data.
- Must NOT: modify `billing/otel/records.py` or `billing/otel/sample_payload.py`.
- Must NOT: add any dependency beyond the standard library.

## Verification

- Targeted test command: `python -m pytest tests/test_cowork_records.py -q`
- Manual verification evidence to capture: sample stdout from `cowork_records.py` and from a
  `cowork_sample_payload.py` run against a locally started `cowork_receiver.py`.
