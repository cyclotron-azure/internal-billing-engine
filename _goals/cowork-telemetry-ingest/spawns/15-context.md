You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-24T00:00:00Z

## Task

Execute Task 03 of the `cowork-telemetry-ingest` goal in full: read
`_goals/cowork-telemetry-ingest/03-cowork-receiver.md` (this IS your task file — treat every
checkbox in its Requirements and every item in its Acceptance Criteria as mandatory) and
implement it completely.

This is the highest-stakes task in the goal: a brand-new, standalone HTTP server process that
will be the live ingress point for real Cowork telemetry. Both prior tasks in this goal (01, 02)
required fix cycles because adversarial evaluator probing found gaps that passing unit tests
didn't catch — task 02 alone needed TWO fix cycles for fail-closed handling of malformed input.
Learn from that pattern: don't just write tests that exercise the happy path and the cases
explicitly named in the Acceptance Criteria — think about what a hostile or buggy client could
send, and verify your own fail-closed behavior actually holds by trying to break it yourself
before reporting done (e.g. temporarily reintroduce a bug you fixed and confirm your test
catches it, then restore the fix).

**This is a deliberate, user-approved exception to this repo's "one receiver process" hard
constraint** — read the task file's opening note and `goal.md`'s explicit discussion of this.
Do not be surprised by or second-guess the existence of a second receiver process; it is
correct and approved for this goal specifically.

## Critical constraints (read the task file for full detail, this is a summary — verify
against the task file itself, not this summary)

1. **Test via `socket.socketpair()`, NEVER a real bound port.** This repo's `tests/
   test_receiver.py` has an established, load-bearing convention: "real requirement: never bind
   a real port in a test." Reuse that same approach for this receiver's tests.
2. **Never import `billing.otel.receiver`.** That module runs `load_env()` and populates an
   `AUTH_TOKEN` global at import time as a side effect. DUPLICATE the small amount of parsing
   logic you need (`_read_body`'s chunked/gzip handling) as a local function instead.
3. **DO call `from billing.config import load_env; load_env()`** — this is a different,
   generic, shared `.env` reader (not `billing.otel.receiver`) — then read ONLY
   `os.environ.get("COWORK_RECEIVER_AUTH_TOKEN", "")`. Never reference `RECEIVER_AUTH_TOKEN`
   anywhere in this file.
4. **Task 01's frozen `CoworkStore` contract** (already implemented, PASS with notes) includes
   `store.db` (the public connection attribute, for your rollback logic) and
   `store.last_ingest_at()` (for your `/healthz` endpoint) — read `billing/otel/cowork_store.py`
   directly to confirm the exact method/attribute names before using them.
5. **Task 02's frozen `cowork_ingest.parse_cowork_payload`** (already implemented, PASS with
   notes, after 2 fix cycles closing 11 fail-closed gaps) returns
   `{"token_rows": [...], "cost_rows": [...], "metrics_seen": [...], "rejections": [...]}` —
   read `billing/otel/cowork_ingest.py`'s module docstring for the exact, current contract
   (it changed during fix cycles — do not rely on a stale summary).
6. **Per-record store-error containment + rollback**, mirroring `receiver.py`'s own documented
   `_RECORD_DATA_ERRORS`/rollback pattern — read that section of `receiver.py` for the exact
   reasoning, since this task's Requirements ask you to mirror it.
7. **Append-only to `.env.example`** — three new placeholder lines, never rewrite existing
   content.

## Files to Read

Everything listed in `_goals/cowork-telemetry-ingest/03-cowork-receiver.md`'s own "Files to
Read" section, plus:
- `_goals/cowork-telemetry-ingest/goal.md` — full context, the approved second-process
  exception, and the hard isolation constraint.
- `billing/otel/cowork_store.py` (task 01, current, final version — NOT a summary).
- `billing/otel/cowork_ingest.py` (task 02, current, final version — NOT a summary. It changed
  significantly across 2 fix cycles; read its module docstring carefully for the exact,
  current return-dict shape and rejection-reason vocabulary).
- `tests/conftest.py` and `tests/test_receiver.py` — the existing socketpair harness pattern
  and any Cowork-related fixtures from tasks 00-02 you should reuse.
- `billing/config.py` — the `load_env()` you should call.

## Write fence

ONLY these paths:
- billing/otel/cowork_receiver.py (new file)
- tests/test_cowork_receiver.py (new file)
- .env.example (append-only — three new placeholder lines only)

Do NOT modify `billing/otel/receiver.py` in any way — this task's Acceptance Criteria includes
`git diff` on it being empty, AND a grep/AST check that `cowork_receiver.py` contains no import
of `billing.otel.receiver` and no reference to `RECEIVER_AUTH_TOKEN`.

## Model

requested: claude-sonnet-5 · tier: light · rotation: cycle 1 (normal)

## Rules

- Every checkbox in the task file's Requirements and every numbered Acceptance Criterion
  (there are 12) is mandatory.
- Stdlib only — no third-party import, including no HTTP client library beyond what's already
  used elsewhere in this codebase.
- Run the FULL test suite (`python -m pytest tests/ -q`) before reporting completion.
- Double-check every numeric claim (test counts, line numbers) against actual command output
  immediately before writing your report — this has been a recurring source of evaluator
  pushback in this goal (a wrong test count sent an earlier task's report back for correction).
- Actually try to break your own fail-closed guarantees before reporting done: send a malformed
  body, an oversized payload, a request with the wrong token, a request that would fail
  mid-commit — and confirm the server responds sanely (never crashes, never leaves the
  connection dirty) rather than assuming the code is correct because it compiles and the happy
  path works.
- State any judgment calls explicitly in your report.

## Output

A completion report: what you created, how each Requirement/Acceptance Criterion is satisfied
(point to the specific test), the full output of `python -m pytest tests/ -q`, `git diff`
confirmation on `billing/otel/receiver.py`, and judgment calls. End with a `### Footprint`
section: files_read count/approx chars, commands_run count.
