You are the evaluator subagent. Read: .claude/agents/evaluator.md

CURRENT_DATETIME: 2026-09-24T00:00:00Z

## Task

Evaluate Task 03 ("Standalone Cowork receiver process") of the `cowork-telemetry-ingest` goal,
per `.claude/skills/task-criteria/SKILL.md` (eval_depth: full — this is the live ingress point
for real Cowork traffic). The implementer reports 648 tests passing (full suite), 30 new tests,
all 12 Acceptance Criteria satisfied, `git diff` on `receiver.py` empty, and ran its own
bug-reintroduction check (temporarily broke `_RECORD_DATA_ERRORS`, confirmed a test failed,
restored it).

**Do not treat that as sufficient.** Tasks 01 and 02 in this same goal both passed their own
verification and still had adversarial evaluator probing find real gaps — task 02 needed TWO
fix cycles. Apply the same standard here: actually construct adversarial/malformed inputs and
send them through the socketpair harness yourself (or a scratch script using the same
technique), don't just read the test file and trust it.

**A specific ambiguity to resolve**: the implementer flagged that the `/v1/metrics` JSON
response body omits the full `rejections` list (only returns counts + `metrics_seen`), arguing
AC4's "rejection reflected in the response body" is satisfied by a non-zero `rejected` count.
Decide whether this reading is acceptable or whether AC4 requires the itemized list — read AC4
in the task file directly and judge based on its literal wording and the goal's overall
transparency requirements.

**Specific things worth adversarial-probing, given this goal's pattern so far:**
- Send a payload that's valid JSON but where `parse_cowork_payload` itself might raise (recall
  task 02's fix history — is `cowork_receiver.py` calling the FINAL, twice-fixed version of
  `parse_cowork_payload`, or could an older cached understanding of its contract cause a
  mismatch? Check the actual current `cowork_ingest.py` return shape against what
  `cowork_receiver.py` expects).
- Try a `Content-Length` that doesn't match the actual body size, and chunked/gzip edge cases,
  since `_read_body` was duplicated from `receiver.py` rather than imported — confirm the
  duplicate is faithful and doesn't have a subtly different bug.
- Try hitting `/healthz` and `/v1/metrics` with unusual HTTP methods, malformed headers, or a
  request with no `Content-Length` at all.
- Confirm the auth check happens BEFORE any body is read/parsed (mirroring `receiver.py`'s own
  ordering, which exists so an unauthenticated caller never reaches the store).
- Confirm concurrent/sequential request handling doesn't leave the single SQLite connection in
  a bad state (single-threaded server, but check the commit/rollback discipline holds across
  multiple requests in sequence, including a failed one followed by a successful one).
- Verify the claim that no test binds a real socket — actually read every test in
  `tests/test_cowork_receiver.py`, don't just trust the one meta-test that claims to check this.

## Files to Read

- `_goals/cowork-telemetry-ingest/03-cowork-receiver.md` — the task's Requirements and all 12
  Acceptance Criteria, verbatim.
- `_goals/cowork-telemetry-ingest/spawns/15-report.md` — the implementer's completion report.
- `billing/otel/cowork_receiver.py` — the actual new module.
- `tests/test_cowork_receiver.py` — the actual new tests, read in full.
- `billing/otel/cowork_store.py`, `billing/otel/cowork_ingest.py` — the current, final,
  twice-fixed contracts this receiver depends on. Confirm `cowork_receiver.py` matches their
  ACTUAL current shape, not an assumed/stale one.
- `billing/otel/receiver.py` — ground truth for the patterns being mirrored (`_read_body`,
  `_RECORD_DATA_ERRORS`, the auth-before-body-read ordering, the rollback discipline), and to
  confirm no diff.
- `.env.example` — confirm the three new lines are a clean append.

## Write fence

None — evaluator produces a verdict only, writes nothing.

## Model

requested: claude-opus-5 · tier: frontier · rotation: n/a

## Rules

- Run `python -m pytest tests/test_cowork_receiver.py -v` and the full `python -m pytest
  tests/ -q` yourself; double-check numeric claims.
- Actually run adversarial probes through the socketpair harness (or equivalent) yourself.
- Verdict must be exactly one of PASS, PASS (with notes), NEEDS FIXES, REJECT.
- This task involves a second receiver process — do NOT flag that as a violation; it's a
  user-approved, explicitly-documented exception for this goal (see the task file's opening
  note and `goal.md`).

## Output

Verdict with itemized reasoning against the task file's Requirements and Acceptance Criteria,
including an explicit ruling on the AC4/`rejections`-in-body ambiguity.
