You are the evaluator subagent. Read: .claude/agents/evaluator.md

Fresh spawn. CURRENT_DATETIME: 2026-09-16T11:20-04:00

## Task

Evaluate task 03 of `reconcile-coverage-diagnostics` — output rendering and CLI flags in
`billing/reconcile.py`. Contract: `_goals/reconcile-coverage-diagnostics/03-reconcile-output.md`
(16 numbered criteria plus 7b and 7c = 18 items). Apply
`.claude/skills/task-criteria/SKILL.md`.

Return **PASS**, **PASS (with notes)**, **NEEDS FIXES**, or **REJECT**.

## Why you are doing more work than usual

The implementer's report (`spawns/08-report.md`) is a **summary**. It did not paste the six
required output scenarios, so the central claim of this task — that the rendered output is
correct and legible — has **no evidence in the ledger**. You must produce that evidence.

**Build one scratchpad fixture** (tmp OTEL db + tmp analytics db, never `data/`) containing:
OTLP + transcript rows, an unmapped token type, a NULL `token_type`, a NULL `entrypoint`, a
NULL `query_source`, at least one dedupe drop, and three distinct days. Then **capture and
paste the full stdout** of:

1. default (no flags)
2. `--daily`
3. `--by-surface`
4. `--detail`
5. one run per `DEDUPE DROPS` state 1, 2 and 3 (manipulate the epoch `meta` value)
6. a run with non-empty `by_type` under a non-`"full"` measurement state
   (`counts_outside_measurement` True) — the criteria 7b/7c case
7. the `--email` path, both the no-analytics-rows early return and a normal filtered funnel

Mock Analytics with **Seam A**: `monkeypatch`/`setattr` on the module-level
`billing.reconcile.analytics_claude_code_daily`. Patching `AnalyticsClient.usage_report`
alone never reaches it — the constructor raises without a token.

## Judge these specifically

1. **Counts are never suppressed by measurement state.** A non-empty `by_type` must print
   under states 1, 2 and 3, with the state as a *qualifier*. This was a real contradiction
   in an earlier plan draft; criteria 7b/7c exist to catch a regression. Verify by running
   it, not by reading.
2. **`--by-surface` labeling.** Header must contain the literal strings "share of captured"
   and "NOT coverage". Each sub-block's `TOTAL` share must read exactly `100.00%` (three
   occurrences). An unlabeled percentage here reads as coverage on an invoice review.
3. **Σdaily == period in the rendered output.** Parse the exact-integer columns out of a
   `--daily` run and confirm they sum to the printed `TOTAL`, on both truth and captured.
4. **Width.** `RULE_WIDTH = 108`. Confirm every `===`/`---` rule line is exactly that, and
   that **no** output line — including prose and the wrapped synthetic-data note — exceeds
   it, across all flag combinations.
5. **Preserved behavior.** Default output still has `BY TOKEN TYPE`, `COVERAGE FUNNEL`,
   `BILLABLE COVERAGE` with unchanged funnel arithmetic. The `if result is None:` early
   return and the `except AnalyticsError` branch print exactly as before, with no funnel and
   no new sections. `store.close()` on every return path.
6. **The two carried-over cleanups** are actually applied: the `DEDUPE_EPOCH_META_KEY`
   import is gone, and the guard reads `if not epoch or epoch_day >= end`. Confirm
   `dedupe_drop_report(store, start, end)` no longer raises on `epoch == ""` and that
   `measurement` is unchanged for every reachable input.
7. **No recomputation.** Print helpers must consume task 02's functions, not query the
   database. No new `sqlite3.connect`. Stdlib only.
8. **Out of scope respected**: no `--json`, no exit-code threshold, no `ftok()`/`pct()`
   behavior change.
9. **Legibility, as a reader.** You are the first person to see this output. Say plainly
   whether a reviewer comparing it against an invoice could act on it — especially whether
   `"(none)"` rows and the dedupe qualifiers are self-explanatory. Note that in `unmapped`,
   a NULL `token_type`, an empty string, and a literal `"(none)"` all collapse into one key,
   so the wording must not assert a cause the key cannot distinguish.
10. Run `python -m pytest tests/test_otel_store.py -q` yourself. **Not** the full suite.
11. Confirm the write fence: only `billing/reconcile.py` newly modified.

## Write fence

None. Evaluate only. Scratch files in your scratchpad dir, never the repo, never `data/`.

## Model

requested: claude-opus-5 · tier: frontier · rotation: n/a

## Rules

- Do not edit any repository file. Describe fixes.
- Every criterion verified by observation where observation is possible.
- Distinguish **blocking** (wrong number, mislabeled percentage, broken existing path,
  suppressed count) from **non-blocking** (wording, style).
- Tag `destructive` / `security` / `infra` findings explicitly.
- Keep your report **compact** — the user is token-constrained. Full captured output for the
  scenarios is required and exempt from that; everything else should be terse. No restating
  the task file back.
- `files_read: <N> (~<C> chars)` with C digits only.

## Output

```
VERDICT: ...
MODEL: ...

## Captured output
[All scenarios, verbatim. This is the deliverable.]

## Criteria
[One terse line per criterion 1-16 + 7b + 7c: VERIFIED (how) / NOT MET (why).]

## Judgment points
[One terse line per point 1-11.]

## Findings
[BLOCKING / NON-BLOCKING, each 3 lines max: where, problem, fix.]

## Reader verdict
[2-4 sentences: could someone bill a client from this output without being misled?]

### Footprint
files_read: <N> (~<C> chars)
```
