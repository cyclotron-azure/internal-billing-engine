You are the evaluator subagent, in **audit mode**. Read: .claude/agents/evaluator.md

Fresh spawn. CURRENT_DATETIME: 2026-09-16T12:20-04:00

## Task

Final audit of the `reconcile-coverage-diagnostics` goal. Verdict: **APPROVED** or **ISSUES**.

Three reviews are merged into this one spawn because the user is token-constrained, so weight
each deliberately:

1. **Task 04's dedicated evaluation, which was never run.** Tasks 01-03 each got their own
   evaluator; task 04 did not. It self-reports 69 tests, **zero GAPs**, all passing, no failures
   found in the implementation. A 0-GAP all-green test report is exactly where skeptical review
   belongs. **Audit test QUALITY, not presence.**
2. **Cross-task integration and regression** across tasks 01-04 plus the cleanup pass.
3. **Doc audit** (Phase 6 was merged into the cleanup spawn, so its output is unreviewed).

## State

Full suite: **331 passed** (run by the orchestrator). Working tree:

```
 M README.md                      (+27/-)    docs sync, this goal + an earlier VS Code correction
 M billing/otel/otel_store.py     (+172/-0)  task 01
 M billing/reconcile.py           (+480/-)   tasks 02, 03, cleanup
 M client-package/INSTRUCTIONS.md (+5/-)     earlier VS Code correction, NOT this goal
 M deploy/README.md               (+7/-)     earlier VS Code correction, NOT this goal
 M tests/COVERAGE_MAP.md          (+120/-)   task 04
?? tests/test_dedupe_counter.py              task 04, 15 tests
?? tests/test_reconcile.py                   task 04, 55 tests
?? _goals/…                                  orchestration artifacts
```

Goal + task definitions: `_goals/reconcile-coverage-diagnostics/{goal.md,01-…,02-…,03-…,04-…}.md`.
Per-spawn ledger: `_goals/reconcile-coverage-diagnostics/orchestration-log.md` and `spawns/`.
Note reports from spawn 08 onward are **condensed stubs**, not verbatim, by the same token
constraint.

## 1 — Test quality (the priority)

Read both new test files in full and judge:

- **Do the assertions actually constrain the code?** Hunt for tests that would pass against a
  broken implementation: asserting a substring that is always present, asserting a dict has
  keys without checking values, `assert x is not None`, try/except swallowing, a "no output"
  check on a function that never printed anyway.
- **Are the pinned numbers derived or copied?** A test asserting `captured == {…}` is only
  meaningful if those numbers follow from the fixture. Spot-check two or three against the
  fixture rows and say whether the arithmetic holds independently.
- **Zero GAPs is a strong claim.** `04-tests.md` requires one test per acceptance criterion
  across tasks 01-03 (01: 1-14, with 15 a command; 02: 1-16; 03: 1-16 plus 7b and 7c = 18).
  Verify the mapping in `tests/COVERAGE_MAP.md` is real: pick at least six criteria, including
  the ones that were hardest to get right, and confirm the named test actually tests that
  criterion rather than something adjacent. The hard ones: **01.7** (read-only open leaves
  `dedupe_epoch()` None), **01.10** (exactly one meta lookup, not zero), **01.11** (rolled-back
  epoch write recovers), **02.6/02.7** (Σdaily == period, all four identities), **02.8** (day-key
  literal), **02.14** (query-time attribution — raw `repo` unknown, timeline resolves it),
  **03.7b** (non-empty `by_type` prints under states 1-3).
- **The three testability traps.** Task 04 claims it handled: the `drops = 0` residue row
  (asserted through public readers, never `SELECT COUNT(*)`), second-granular `last_seen`
  (monkeypatched `_now`, not `sleep`), and `dedupe_epoch()` sharing the `FROM meta` SQL shape
  (matched the exact insert-path SQL). Confirm each in the code.
- **Isolation.** Every `run()` call passes an explicit `db=`; no test touches `data/otel.db` or
  `data/analytics.db`; no live network call; every Seam B use includes
  `monkeypatch.setenv("ANTHROPIC_ANALYTICS_TOKEN", …)` — without it the constructor raises first
  and an `AnalyticsError` test passes for the wrong reason. Confirm `tests/conftest.py` and
  `tests/test_otel_store.py` are byte-unmodified (`git diff --stat` on both).
- **One late repair to scrutinize.** `test_03_6` was split after the cleanup pass changed the
  `partial`-with-empty-`by_type` wording. The empty case now asserts the epoch and that
  `LOWER BOUND` is **absent**, deliberately not re-pinning the new text. Judge whether that pair
  still constrains the behavior or whether it went too weak.

## 2 — Integration and regression

- Every **Success Criterion** in `goal.md` — met, or not. Check each; do not sample.
- The goal's hard constraints: stdlib-only in `billing/`; single-host single-connection SQLite
  (no WAL, no pool, no `check_same_thread`, no threading); **repo attribution resolved at query
  time, never persisted**; no secret committed.
- `billing/otel/receiver.py` unmodified, and genuinely not needing modification.
- The two pre-existing error paths in `run()` byte-identical.
- `dp_key`, `transcript_key` and the `request_id` validation untouched.
- Anything the four task files promised that no task actually delivered.

## 3 — Doc audit

`CLAUDE.md` makes `README.md` ground truth. Verify the three updated spots describe the code as
**shipped**:

- the `otel_store.py` bullet (must name `dedupe_drops` and the epoch's insert-path provenance);
- the `reconcile.py` bullet (exact-integer figures, `UNMAPPED TOKEN TYPES`, the four-state
  `DEDUPE DROPS`, the three flags, and that `--by-surface` is a **share of captured, not
  coverage**);
- the pilot **Coverage** bullet.

Flag any *other* place in `README.md` that is now wrong. `client-package/INSTRUCTIONS.md` and
`deploy/README.md` belong to an earlier VS Code correction — check they are consistent with
the README but do not attribute them to this goal.

## Known and accepted — do not re-report as new

- `_ns_to_iso(time_unix_nano)` is evaluated twice per insert in `otel_store.py`; on the
  malformed-input fallback path it returns `_now()`, so `day` could disagree with the row's own
  `ts` across a midnight-UTC boundary. Deferred from task 01 with the one-line fix recorded
  (hoist `ts` and use `ts[:10]`). **Say whether you agree it is still safe to defer.**
- The banner and the `!! No analytics rows for [...]` line can exceed `RULE_WIDTH` with long
  email addresses. Both are on the "stays unchanged" list.

## Rules

Evaluate only — no repository writes. Scratch files in your scratchpad, never `data/`.
Run targeted commands freely; **do not** run the full suite (the orchestrator has it: 331).
Model: claude-opus-5 · frontier.
Keep the report **compact**: findings over narration, no restating the task files.
`files_read: <N> (~<C> chars)`, C digits only.

## Output

```
VERDICT: APPROVED | ISSUES
MODEL: <model>

## Test quality
[The priority section. Name specific weak tests, or state plainly that you tried to find them
and could not. Include the spot-checked arithmetic and the six+ criteria you traced.]

## Success criteria
[One line per goal.md success criterion: MET / NOT MET.]

## Integration & constraints
[One line per item in section 2.]

## Docs
[One line per updated spot, plus anything else now stale.]

## Deferred items
[Your ruling on the two accepted items.]

## Findings
[BLOCKING / NON-BLOCKING, 3 lines max each. Only what a reviewer must act on.]

### Footprint
files_read: <N> (~<C> chars)
```
