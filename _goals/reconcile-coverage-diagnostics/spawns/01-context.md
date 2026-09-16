You are the evaluator subagent. Read: .claude/agents/evaluator.md

CURRENT_DATETIME: 2026-09-16T09:40:54-04:00

## Task

Evaluate the goal definition and all four task files for the
`reconcile-coverage-diagnostics` goal. This is Phase 3 (goal evaluation) — no code has
been written yet. You are judging whether this plan is sound, complete, internally
consistent, and safe to execute, and whether every task's `## Acceptance Criteria`
section is verifiable as written.

Return a verdict of **PASS**, **NEEDS REVISION**, or **REJECT**.

## Requirements

Apply `.claude/skills/goal-criteria/SKILL.md` in full. In addition, verify each of the
following, which are the specific risks in this plan:

1. **Every Phase 1 decision is reflected in a task.** The Discovery Summary in
   `goal.md` records eight answered decisions. A decision the user answered that no
   task implements is a defect.
2. **Write-fence disjointness.** Tasks 02 and 03 both declare
   `writes: billing/reconcile.py`. Confirm the `depends_on` ordering between them is
   present and correct, and that no *other* pair of tasks without an ordering shares a
   write path.
3. **Additive-compatibility claims are actually achievable.** Task 02 requires
   `otel_totals`, `analytics_claude_code_totals`, and `analytics_user_totals` to keep
   their current signatures and return shapes while restructuring the org-wide path to
   a single `usage_report` pass. Read `billing/reconcile.py` and
   `billing/analytics_client.py` and judge whether those two requirements are mutually
   satisfiable as specified. If they are not, say so concretely.
4. **The single-API-pass requirement vs. the `AnalyticsError` path.** Task 02 requires
   both one `usage_report` pass and that `AnalyticsError` still propagate into
   `run()`'s existing `except AnalyticsError` branch. Verify the task text specifies
   this unambiguously enough that an implementer cannot satisfy one by breaking the
   other.
5. **The dedupe-counter increment is genuinely off the hot path.** Task 01 puts an
   increment inside `insert_datapoint`/`insert_cost_datapoint` — code that runs in the
   receiver's serial request handler on a single-connection SQLite store. Judge whether
   the task's constraints (collision path only, `sqlite3.Error` swallowed, no
   `commit()`, portable two-statement form, no receiver changes) are sufficient and
   internally consistent. Flag anything that could degrade live billing ingest.
6. **The epoch semantics are unambiguous.** The point of the measurement epoch is that
   an unmeasured window must never print `0`. Check that tasks 01, 02, and 03 agree on
   exactly when `measured` is False, and that task 03's three rendering cases
   (unmeasured / measured-zero / measured-nonzero) are mutually exclusive and
   exhaustive.
7. **The share-of-captured labeling requirement is enforced, not merely suggested.**
   The single biggest correctness risk in this goal is a per-surface percentage being
   read as coverage on an invoice review. Judge whether task 03's requirements make
   that mislabeling impossible to ship, and whether task 02's `captured_total`
   invariant is strong enough to catch a dimension that silently stops summing to 100%.
8. **Acceptance criteria are verifiable.** Every criterion in all four task files must
   name a verification method and be checkable without ambiguity. Flag any criterion
   that is a restatement of a requirement rather than an observable outcome, and any
   that cannot actually be verified by the method it names.
9. **Scope discipance.** `goal.md`'s Out of Scope list is explicit (no `--json`, no
   exit-code threshold, no `request_id` column, no receiver changes, no coverage
   *fixes*). Flag any task requirement that creeps past it.
10. **Constraint propagation.** Every task that could introduce a runtime import must
    state the stdlib-only constraint. The single-host/single-connection SQLite
    constraint must be stated in task 01. The resolve-at-query-time invariant
    (`resolved_view` / `resolved_repo`, never the raw `repo` column) must be stated in
    task 02. Verify each is present, not merely implied.
11. **Test task realism.** Task 04 claims `tests/COVERAGE_MAP.md` with
    `targeted-insertion` while that file's title scopes it to a different goal
    (`desktop-usage-capture`). Judge whether appending a second goal's section there is
    coherent, or whether it should be a separate file.
12. **The known pre-existing gap is handled honestly.** `goal.md` records that
    `tests/test_reconcile.py` does not exist because the sibling goal
    `_goals/email-filtered-reconciliation/` stalled at a Phase 3 escalation on
    2026-09-14 while its code shipped anyway (commits `5dd7d94`, `947a686`). Task 04
    folds regression coverage for those untested paths into this goal. Judge whether
    that is correct scoping or scope creep, and whether the write-fence collision with
    the stalled goal's task 02 (which also claims `tests/test_reconcile.py`) is a real
    problem.

## Files to Read

- `_goals/reconcile-coverage-diagnostics/goal.md` — the goal, its Discovery Summary
  (Phase 1 Q&A record), Success Criteria, Constraints, and Out of Scope.
- `_goals/reconcile-coverage-diagnostics/01-store-dedupe-counter.md`
- `_goals/reconcile-coverage-diagnostics/02-reconcile-aggregation.md`
- `_goals/reconcile-coverage-diagnostics/03-reconcile-output.md`
- `_goals/reconcile-coverage-diagnostics/04-tests.md`
- `.claude/skills/goal-criteria/SKILL.md` — the criteria you apply.
- `billing/reconcile.py` — the module tasks 02 and 03 modify. Read it in full; the
  plan's compatibility claims are only judgeable against the real code.
- `billing/otel/otel_store.py` — `SCHEMA`, `_migrate`, `dp_key`, `transcript_key`,
  `insert_datapoint`, `insert_cost_datapoint`. Task 01 modifies this.
- `billing/otel/receiver.py` — lines 140–190 and 340–365 only, to check the claim that
  both ingest paths route through the two insert methods so the receiver needs no
  changes.
- `billing/analytics_client.py` — `usage_report`'s yield shape, windowing, pagination,
  and `AnalyticsError`, for risks 3 and 4.
- `billing/store.py` — `user_cc_usage` schema, for the per-day per-user query.
- `tests/conftest.py` — the fixtures task 04 plans to reuse.
- `tests/COVERAGE_MAP.md` — the existing format and scoping, for risk 11.
- `CLAUDE.md` — the project's hard constraints.
- `README.md` — ground truth for this engine; specifically the single-host SQLite
  constraint, the `reconcile.py` bullet, and the pilot "Coverage" bullet.

## Write fence

None. You are evaluating only. Do not create, modify, or delete any file, including the
goal and task files you are judging. Report findings; the orchestrator applies fixes.

## Model

requested: claude-opus-5 · tier: frontier · rotation: n/a

## Rules

- Do NOT write or edit any file. No code, no task-file corrections, no test files.
- Default to pessimism. A plan that "looks fine" is not a PASS unless you have
  checked each numbered risk above against the real source files.
- Judge the plan as specified, not the plan you would have written. Flag a genuinely
  better alternative only when the specified approach is actually defective.
- Where a requirement is unachievable as written, say precisely which requirement and
  why, citing the file and line in the real source that makes it so.
- Distinguish **major** findings (would produce wrong billing numbers, break an
  existing path, degrade live ingest, or ship a misleading figure) from **minor** ones
  (wording, ordering, redundancy). Label each.
- Tag any finding that is `destructive`, `security`, or `infra` in nature explicitly
  with that word — those bypass fix cycles and escalate immediately.
- Do not accept "the orchestrator will notice" as mitigation for an ambiguous
  requirement. The implementer subagents run with zero conversation history and see
  only their own task file.

## Output

```
VERDICT: PASS | NEEDS REVISION | REJECT
MODEL: <the model you are actually running as>

## Summary
[2-4 sentences: is this plan executable as written, and what is the single biggest risk]

## Findings
### [MAJOR|MINOR] <short title>  (risk #N, or "additional")
- **Where**: <file : section or line>
- **Problem**: <what is wrong>
- **Consequence**: <what ships or breaks if this is not fixed>
- **Fix**: <the specific change needed>

## Acceptance-criteria validation
[Per task file: are all criteria verifiable as written? Name every criterion that is
not, with the reason.]

## Risks checked
[One line per numbered risk 1-12: PASS / FLAGGED, with a pointer to the finding.]

### Footprint
files_read: <N> (~<C> chars)
```
