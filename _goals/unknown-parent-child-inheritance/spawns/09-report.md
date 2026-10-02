**Model (self-reported)**: claude-fable-5-1
## Task Complete: Fix cycle 2 of task 01 — alias collision + NULL-repo standalone/view divergence

### Requirements checklist
- [x] Inner alias collision-proof, derived from caller alias — billing/otel/attribute.py:102-111 (templates use `{ar}`), :114-116 (`_fmt(alias)` returns `ar=f"{alias}__ar"`); eval06/alias_chk2.py → `MISMATCHES: 0` for all 17 aliases, in view, `WITH r AS (...)` view, and standalone
- [x] All listed aliases (`r`, `R`, `x1`, `q`, `token_usage`, `_i`, `_r`, `_m`, `_x`, `_q`, `_ru`, `_rx`, `_w`) plus `_ar`, `t__ar`, `r__ar`, `t` return the default alias's rows in BOTH paths — alias_chk2.py output below; evaluator's alias_chk.py now prints `same` for every row including `_ar`
- [x] Standalone `resolved_repo()` agrees with view/original on a NULL-repo as-of row — attribute.py:236-243: second COALESCE term is now `_FIRST.format(col='repo')`; newrisk.py §1 → all three cases `SAME`
- [x] Docstring/comment accuracy — attribute.py:98-99 ({ar} note), :230-233 (fallback-chain paragraph in `resolved_repo`); the `resolved_view` docstring claim of identical results (~line 281) is now true
- [x] Re-verification: rung 2 `136 passed`; func2.py 124/124 with 0 view-vs-standalone disagreements; regress2.py / regress2_noties.py view==standalone 0 diffs in every mode and no new differences vs original; perf all ≤ 0.855 s/100k

### Files changed
- C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\billing\otel\attribute.py — the only repo edit. Backup of the pre-edit version: scratchpad\attribute_v4_903cdd5.py. New ad-hoc check script: scratchpad\eval06\alias_chk2.py.

#### Exact edits (before → after)
1. `_AS_OF` / `_FIRST` templates (lines 101-111 → 102-116): every `_ar` became `{ar}`:
   - before: `(SELECT _ar.{col} FROM {tl} _ar WHERE _ar.session_id = {a}.session_id AND _ar.ts <= {a}.ts ORDER BY _ar.ts DESC, _ar.seq DESC, _ar.repo DESC LIMIT 1)`
   - after: `(SELECT {ar}.{col} FROM {tl} {ar} WHERE {ar}.session_id = {a}.session_id AND {ar}.ts <= {a}.ts ORDER BY {ar}.ts DESC, {ar}.seq DESC, {ar}.repo DESC LIMIT 1)` (same for `_FIRST`)
   - new helper: `def _fmt(alias): return {"tl": TIMELINE_TABLE, "a": alias, "ar": f"{alias}__ar"}`; the three `f = {"tl": TIMELINE_TABLE, "a": alias}` sites (`resolved_repo`, `attribution_source`, `resolved_view`) became `f = _fmt(alias)`.
2. `resolved_repo` body:
   - before: `COALESCE((SELECT _i.v FROM {table} WHERE _i.rid = {as_of}), (SELECT _i.v FROM {table} WHERE _i.rid = {first}), {alias}.repo)`
   - after: `COALESCE((SELECT _i.v FROM {_inherit_table()} WHERE _i.rid = COALESCE({as_of_rowid}, {first_rowid})), {_FIRST(col='repo')}, {alias}.repo)`
   - Note: with the second term now the raw first-row repo, the first term must probe `_i` on the EFFECTIVE row (`COALESCE(as_of_rowid, first_rowid)`) — exactly the view's `eff` — otherwise a datapoint earlier than the session's first (inheritable unknown) row would lose inheritance in the standalone path only. The standalone now builds exactly one `_i` table, matching its docstring.

### Verification
- `python alias_chk2.py` (seeded: inheritable unknown+real, other session, no-timeline wrapper, dp-before-first-row inheritance, NULL-repo as-of row, transcript scratch, absent) → base `[('k0','R','timeline'),('k1','Z','timeline'),('k2','wtag','wrapper'),('k3','Q','timeline'),('k4','unknown','timeline'),('k5','unknown','desktop-scratch'),('k6','unknown','absent')]`; `view==standalone(default): True`; for each of `t r R x1 q token_usage _i _r _m _x _q _ru _rx _w _ar t__ar r__ar` × {view, cte-view, standalone}: `same`; `MISMATCHES: 0`
- `python alias_chk.py` (evaluator's) → `_i/_ar/_r/_x/_m` view and standalone all `same`
- `python newrisk.py` §1 → `SAME a view ('unknown','timeline') standalone ('unknown','timeline') orig ('unknown','timeline')`; `SAME b ('github.com/w/t','wrapper')` ×3; `SAME c ('wt','wrapper')` ×3. §2 column lists True/True both tables; §3 cardinality 150/150/150 both tables
- `python func2.py` → `functional OK: 124 / 124`, `view-vs-standalone disagreements: 0 []`; backslash literal present / no LIKE / fixed GLOBs unchanged
- `python regress2.py` → noun 7487 dp new!=orig 0, noqual 7426 new!=orig 0, mixed 7485 new!=orig 23 (all inheritance, new!=reference 0 — identical to the evaluator's prior run); `view != standalone per mode: {'noun': 0, 'noqual': 0, 'mixed': 0}`
- `python regress2_noties.py` → new!=orig 0 / new!=reference 0 both modes; view != standalone 0
- Rung 2: `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_invoice.py tests/test_reconcile.py tests/test_export.py tests/test_export_unattributed.py tests/test_integration_desktop.py -q` → `136 passed in 15.50s`
- Perf (perf_drive.py, one process per statement/version, warm-up + median of 3, default sqlite3 connect):

  eval06/perf_eval.db (129,600 token / 126,600 cost rows)

  | Statement | orig s | new s | ratio | new s/100k |
  |---|---|---|---|---|
  | export_scan_token | 0.827 | 1.108 | 1.34 | 0.855 |
  | export_scan_cost | 0.686 | 1.077 | 1.57 | 0.850 |
  | bill_cost | 0.362 | 0.752 | 2.08 | 0.594 |
  | bill_token | 0.393 | 0.793 | 2.02 | 0.612 |
  | bill_source | 0.271 | 0.681 | 2.52 | 0.526 |
  | reconcile_totals | 0.356 | 0.852 | 2.40 | 0.657 |
  | reconcile_daily | 0.420 | 0.961 | 2.29 | 0.742 |

  scratchpad/perf.db (135,000 rows)

  | Statement | orig s | new s | ratio | new s/100k |
  |---|---|---|---|---|
  | export_scan_token | 0.866 | 0.794 | 0.92 | 0.588 |
  | export_scan_cost | 0.863 | 0.809 | 0.94 | 0.599 |
  | bill_cost | 0.332 | 0.581 | 1.75 | 0.430 |
  | bill_token | 0.363 | 0.614 | 1.69 | 0.455 |
  | bill_source | 0.241 | 0.517 | 2.15 | 0.383 |
  | reconcile_totals | 0.310 | 0.679 | 2.19 | 0.503 |
  | reconcile_daily | 0.408 | 0.784 | 1.92 | 0.581 |

  All 14 ≤ 1.0 s/100k; within noise of the evaluator's cycle-1 tables (expected: the view SQL for the default alias differs only in the inner alias name `t__ar`).
- `git status --short` → ` M billing/otel/attribute.py` and `?? _goals/unknown-parent-child-inheritance/` only
- `git hash-object billing/otel/attribute.py` → **3a2a637fa5804abe008ebc7aa787a42ff535ebc8** (was 903cdd549895384908c91d45c5dba2ac913179f8)

### Notes for the evaluator
- Collision argument: `f"{alias}__ar"` is strictly longer than `alias`, so it can never equal it; none of the fixed internal aliases (`_i`, `_r`, `_m`, `_x`, `_q`, `_ru`, `_rx`, `_w`) end in `__ar`, so the derived name cannot collide with them for any caller alias. The fixed internal aliases live only inside the `_inherit_table()` derived table (closed scope), which is why caller aliases equal to them already worked and still do (verified empirically, including `_i`).
- Requirement 2 said "second COALESCE term must be the first row's raw repo, keeping every other behavior". Doing only that would have broken standalone inheritance for a datapoint before the session's first row (the `k3` case in alias_chk2.py), so the first term now probes `_i` on `COALESCE(as_of_rowid, first_rowid)` — the view's own `eff`. The standalone is now a literal mirror of the view's chain. This is the smallest change that keeps view == standalone on all seeded and randomized cases.
- No git checkout/restore/stash/reset was run. No commit. No other repo path touched; no new imports, tables, columns, indexes, or SQLite functions.
- perf_drive.py reports differing result-row counts between orig and new (e.g. perf.db 35737 vs 960): that is inheritance merging groups on those synthetic stores, present in the evaluator's prior cycle too, not an effect of this edit.
- Nothing I could not do.

### Footprint
files_read: 10 (~60,000 chars) — 09-context.md, 08-report.md, 01-attribute-inheritance.md, attribute.py, CLAUDE.md (via system context), eval06/alias_chk.py, newrisk.py, perf_drive.py, perf_one.py, heads of func2.py/regress2.py/regress2_noties.py
commands_run: 7
