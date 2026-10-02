You are the implementer subagent (RESUMED, fix cycle 1 of 3). Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-10-01T15:20:00-10:00

## Task
Fix the two defects the evaluator found in task 01 (`_goals/unknown-parent-child-inheritance/01-attribute-inheritance.md`),
report: `_goals/unknown-parent-child-inheritance/spawns/06-report.md` (read it fully). Logic is
CORRECT (an independent model of the spec matched on ~22,400 datapoints) - do not change behavior
except where noted. Project root: C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine

## Requirements
1. **[blocker] Performance.** Every real consumer statement - export `_scan` token_usage and
   cost_usage, bill cost/token/source aggregations, reconcile `otel_totals` and daily - must be
   <= 3.0x the ORIGINAL attribute.py AND <= 1.0 s per 100,000 datapoints, measured as the median
   of 3 runs after a warm-up, on BOTH stores:
   - your `scratchpad/perf.db`, and
   - the evaluator's `scratchpad/eval06/perf_eval.db` (built by `eval06/perf_eval.py`; reuse
     `eval06/` scripts and `consumers.py`). It is the harder store (more unknown rows, realistic
     paths, transcript rows) and the one that failed: export token 6.74x / 1.78 s per 100k,
     export cost 3.79x, bill token 4.00x, bill source 3.74x.
   Ideas, in rough order (use judgment; measure each): (a) evaluate `resolved_repo` ONCE per
   row inside `resolved_view` and derive `attribution_source` and the downstream `CASE` uses
   from that column (a private helper may take the resolved column as an input; the public
   `resolved_repo(alias)`, `attribution_source(alias)`, `resolved_view(table, alias)` signatures
   and string return types MUST stay frozen and each must still work standalone); make sure
   SQLite does not re-evaluate it per reference when the view is used inside a consumer CTE
   (e.g. a materialising inner SELECT such as `LIMIT -1`, then verify with EXPLAIN QUERY PLAN
   that only ONE as-of `_i` and ONE first-row `_i` are built per statement); (b) build the
   per-timeline-row lookup only as far as needed (blocklist/inheritance evaluated only for
   `repo = 'unknown'` rows; real rows pass straight through); (c) the tie-break: ANY
   deterministic final tie-break is acceptable provided repo and cwd still come from the SAME row
   - e.g. ordering by the PK tail (`repo`) instead of `rowid` if that lets SQLite use the
   `(session_id, ts, seq, repo)` PK index without a sort; document the choice in the docstring
   (this relaxes the task's explicit `rowid DESC/ASC` wording; orchestrator-approved); (d) avoid
   building the first-row `_i` unless needed.
   If you cannot reach BOTH limits on BOTH stores in pure SQL after a genuine effort, STOP and
   report the best numbers per statement and what you tried. Do not weaken the logic.
2. **[major] Alias collision.** Rename the inner alias `r` used by the `_AS_OF`/`_FIRST`
   templates (attribute.py ~99-109) to an underscore-prefixed name that cannot collide, and
   confirm `alias='r'` gives the same rows as the default alias (add it to your ad-hoc checks).
3. Fix the inaccurate comment ("materialises ONCE per statement") to say what really happens, and
   reword the awkward "instr-free arithmetic" docstring phrase.
4. Re-run and re-report AC1-10 and AC12 evidence (ad-hoc SQL + the exact rung-2 command), and
   re-run the evaluator's regression ideas yourself: `eval06/func.py`, `regress.py`,
   `regress_noties.py` (original vs new must show no differences outside exact-tie cases) before
   handing back. Report the new `git hash-object billing/otel/attribute.py`.

## Files to Read
- _goals/unknown-parent-child-inheritance/spawns/06-report.md (evaluator findings)
- _goals/unknown-parent-child-inheritance/01-attribute-inheritance.md, goal.md
- billing/otel/attribute.py, billing/otel/export.py (_scan), billing/otel/bill.py, billing/reconcile.py
- scratchpad: attribute_orig.py, perf.py, perf.db, consumers.py, eval06/*

## Write fence
ONLY: `billing/otel/attribute.py` (scratchpad for everything else)

## Model
requested: claude-sonnet-5 · tier: light · rotation: fix cycle 1 (normal, resumed)

## Rules
- Test ladder rungs 1-2 only (rung 2 = the AC10 command). Never the full suite.
- Stdlib only; no new imports; no tests/README/consumer edits; no new table/column/index;
  no registered SQLite functions; path text never used as a LIKE/GLOB pattern.
- NEVER run `git checkout`, `git restore`, `git stash` or `git reset` on any repo path: task 01's
  work is uncommitted. If you need the original, use `scratchpad/attribute_orig.py`. Keep a
  copy of your current `attribute.py` (hash 56e3526d...) in the scratchpad before editing.
- Do not commit. Do not touch the VM, deploy/, client-package/.

## Output
Report: what changed and why, the before/after table for every consumer statement on BOTH stores
(orig s, new s, ratio, new s per 100k), EXPLAIN QUERY PLAN excerpt showing the count of `_i`
builds in the export token statement, evidence for AC1-10 and alias='r', the regression results,
`git status --short`, the new hand-off hash, anything you could not do, and a `### Footprint` block.
