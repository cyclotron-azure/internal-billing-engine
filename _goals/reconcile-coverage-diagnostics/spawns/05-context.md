You are the evaluator subagent. Read: .claude/agents/evaluator.md

You are a **fresh spawn**, not the goal evaluator from Phase 3. You are evaluating
**implemented code** for the first time.

CURRENT_DATETIME: 2026-09-16T10:31-04:00

## Task

Evaluate the implementation of task 01 of the `reconcile-coverage-diagnostics` goal:
the dedupe-drop counter and counting-start epoch in `billing/otel/otel_store.py`.

Return **PASS**, **PASS (with notes)**, **NEEDS FIXES**, or **REJECT**.

## Requirements

Apply `.claude/skills/task-criteria/SKILL.md` in full against
`_goals/reconcile-coverage-diagnostics/01-store-dedupe-counter.md` — its Requirements
section is exhaustive and its 15 acceptance criteria are the contract.

**Read the actual code, not the report.** The implementer's completion report is at
`spawns/04-report.md`; treat every claim in it as a claim to verify, not as evidence.
Several criteria are self-reported as "satisfied by construction" or "NOT YET
unit-tested" — decide for yourself whether the construction actually satisfies them.

Verify these specifically. They are where this task can be subtly wrong:

1. **The latch rule.** Task 01 §"Counting-start epoch" mandates latch-on-**confirmation**:
   on each insert attempt, if the flag is unset, `SELECT` the key; if found, latch; if
   absent, write it and leave the flag **unset** so the next insert re-checks. Read
   `_ensure_dedupe_epoch` and confirm the flag can never be set by a write this instance
   merely issued. A latch-on-attempt implementation leaves `dedupe_epoch()` permanently
   `None` after a rolled-back first request — that is the defect criteria 10 and 11 exist
   to catch, and it is the single most important thing to check.
2. **Criterion 10's exact count.** After one insert plus `commit()`, ten further inserts
   must issue **exactly one** `SELECT ... FROM meta` — the first, which finds the key and
   closes the latch. Confirm the implementation produces one, not zero and not ten, and
   that no other code path in the module issues a `meta` SELECT that would confound the
   count.
3. **The `day` value.** It must come from the dropped datapoint's own timestamp
   (`_ns_to_iso(...)[:10]`), never wall-clock now. Check both insert methods.
4. **Error containment.** `sqlite3.Error` (not bare `Exception`) around both the counter
   write and the epoch write, swallowed, and the insert method still returns its correct
   `True`/`False`. Confirm a swallowed failure leaves the flag unset so the next insert
   retries.
5. **Hot-path cost.** A *successful* insert must issue no statement beyond the epoch
   check. Confirm `_record_dedupe_drop` is unreachable when `rowcount > 0`.
6. **Portability.** The counter must use `INSERT OR IGNORE` + `UPDATE`, **not**
   `ON CONFLICT ... DO UPDATE` (the production host's sqlite3 version is unpinned).
   `first_seen` must be set on insert and left alone afterwards; `last_seen` must advance.
7. **Additive only.** Confirm no existing column, `dp_key`, `transcript_key`, or
   `request_id` validation was altered, and that `_migrate()` does **not** write the
   epoch. `git diff` shows 172 insertions and 0 deletions — verify that is genuinely
   additive and not an artifact.
8. **The frozen interface.** Tasks 02–04 build against `DEDUPE_EPOCH_META_KEY`,
   `dedupe_drops(start, end)`, `dedupe_drops_by_day(start, end)`, and `dedupe_epoch()`.
   Confirm each exists with the documented shape and half-open `[start, end)` window
   semantics, that absent keys mean "no drops" rather than `0` entries, and that all use
   `self.db` with no new `sqlite3.connect`. **If any signature differs from what the
   report claims, say so explicitly** — tasks 02 and 03 will be written against your
   finding.
9. **The receiver is untouched** and genuinely did not need touching.
10. **Run the targeted suite yourself**: `python -m pytest tests/test_otel_store.py -q`.
    Do not take the reported `27 passed` on trust. Rungs 1–2 only — do **not** run the
    full `python -m pytest -q`.

You may run additional targeted verification (a scratchpad script, a SQL query against a
tmp store) to observe behavior directly. Prefer observing over reasoning where a cheap
observation is available — notably for criteria 3, 5, 10 and 11.

## Files to Read

- `_goals/reconcile-coverage-diagnostics/01-store-dedupe-counter.md` — the task
  definition and its 15 acceptance criteria. This is the contract.
- `billing/otel/otel_store.py` — the implementation. Read the whole diff region plus the
  surrounding methods it touches.
- `_goals/reconcile-coverage-diagnostics/spawns/04-report.md` — the implementer's claims,
  to be verified rather than believed.
- `.claude/skills/task-criteria/SKILL.md` — the criteria you apply.
- `billing/otel/receiver.py` — the OTLP and transcript ingest paths, the per-request
  `store.commit()`, the per-record error-handling set, and the transcript handler's
  `rollback()` path, to judge criteria 1, 4, 5 and 9.
- `tests/conftest.py` — the `legacy_schema_db_path` fixture, for criterion 6 of the task
  (the migration criterion).
- `CLAUDE.md` and `README.md` — the project's hard constraints (stdlib-only in `billing/`,
  single-host single-connection SQLite, no persisted attribution).

## Write fence

None. You are evaluating only. Do not modify `billing/otel/otel_store.py`, any test file,
or any task file. Report findings; the orchestrator routes fixes.

Scratch scripts for your own verification go in your session scratchpad directory, never
in the repo and never in `data/`.

## Model

requested: claude-opus-5 · tier: frontier · rotation: n/a

## Rules

- Do NOT write or edit any repository file. If a fix is obvious, describe it; do not apply
  it.
- Default to pessimism. "Looks correct" is not a PASS — for each of the ten points above,
  either cite the code that satisfies it or flag it.
- A criterion the implementer marked "satisfied by construction" still needs your
  judgment that the construction is correct. A criterion marked "NOT YET unit-tested" is
  legitimate — task 04 writes the tests — but the *implementation* must still be right,
  and where a cheap direct observation is available, make it.
- Distinguish **blocking** findings (wrong billing behavior, a broken existing path,
  degraded live ingest, a frozen-interface mismatch that would mislead tasks 02–04) from
  **non-blocking** notes (style, naming, redundancy).
- Tag any finding that is `destructive`, `security`, or `infra` in nature explicitly with
  that word — those bypass fix cycles and escalate immediately.
- Report which model produced this verdict.
- `files_read: <N> (~<C> chars)` with **C as digits only, no thousands separators**.

## Output

```
VERDICT: PASS | PASS (with notes) | NEEDS FIXES | REJECT
MODEL: <the model you are actually running as>

## Summary
[2-4 sentences: is this implementation correct, and what is the biggest residual risk]

## Acceptance criteria
[One line per criterion 1-15: VERIFIED (with how) / NOT MET (with why) / DEFERRED to
task 04 with the implementation judged correct-by-inspection.]

## Verification points
[One line per numbered point 1-10 above: PASS / FLAGGED, with a pointer to the code or
the observation that settles it.]

## Findings
### [BLOCKING|NON-BLOCKING] <short title>
- **Where**: <file : symbol or line>
- **Problem**:
- **Consequence**:
- **Fix**:

## Frozen interface, as actually implemented
[The real signatures and semantics, for tasks 02-04 to build against. Flag any drift from
the report.]

## Commands run
[Each command and its result line.]

### Footprint
files_read: <N> (~<C> chars)
```
