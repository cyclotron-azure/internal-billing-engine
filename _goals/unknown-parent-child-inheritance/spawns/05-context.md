You are the implementer subagent (RESUMED). Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-10-01T13:30:00-10:00

## Task
MEASUREMENT ONLY - the user accepted the pure-SQL design in principle and replaced the 3x ratio
gate with an absolute one, pending real-query numbers. Measure the REAL consumer query paths on
your synthetic store (perf.db in the scratchpad) with the ORIGINAL attribute.py
(scratchpad/attribute_orig.py) versus the NEW billing/otel/attribute.py, and report absolute
times. Do not change any repo file.

## Requirements
Measure, for original vs new, median of 3 runs on the same warm DB, in the scratchpad only:
1. The `export.build()` hot path: `export.py` `_scan` for `token_usage` and `cost_usage`
   (the `WITH r AS (resolved_view(table)) SELECT ... resolved_repo ... attribution_source ...
   GROUP BY d, resolved_repo, model, user_email, src, sid` statement). Seed `cost_usage` in the
   synthetic store comparably to `token_usage` if it is empty. Run the real `export.build`
   (store + markup=1.0) if feasible; otherwise run the two `_scan` statements verbatim.
2. `bill.py` token and cost aggregation statements (`GROUP BY resolved_repo, model, ...`).
3. `reconcile.py` `otel_totals` / daily statement (subquery form, no CTE).
For each: original seconds, new seconds, ratio, and seconds per 100,000 datapoints.
Also report: store sizes (datapoint rows, timeline rows) and whether the second `_i`
materialisation (resolved_view calls resolved_repo twice) shows up in the plan for export's
statement (EXPLAIN QUERY PLAN excerpt is enough).
Do NOT optimise or edit attribute.py. If you notice a cheap, spec-compatible improvement,
describe it in one paragraph but do not apply it.

## Files to Read
- billing/otel/export.py (_scan), billing/otel/bill.py (lines ~70-100), billing/reconcile.py (otel_totals, daily)
- scratchpad: attribute_orig.py, perf.py, perf.db (your own earlier files)

## Write fence
none in the repo (scratchpad files only). Do not edit, stage, restore or checkout any repo path.

## Model
requested: claude-sonnet-5 · tier: light · rotation: n/a (resumed)

## Rules
- Do not run the full test suite. Do not commit. Do not touch the VM.
- The repo's attribute.py must still hash to 56e3526d8aa251c99017a0a783aa718a202189ab when you finish; report `git hash-object billing/otel/attribute.py` to prove it.

## Output
A table (statement, original s, new s, ratio, new s per 100k datapoints), the plan excerpt, the
final hash, and a `### Footprint` block.
