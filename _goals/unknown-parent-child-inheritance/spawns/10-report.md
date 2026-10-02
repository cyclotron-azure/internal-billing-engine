**Model (self-reported)**: claude-opus-5-5
## Verdict: NEEDS FIXES
**Score**: 4/5
**failure_class:** implementation

Both of my cycle-2 issues are fixed. The implementer's extra change to the standalone's first term is correct: the standalone is now the same expression chain as the view, and it matches the original everywhere the original applies. The amended perf gate passes. No new behaviour defect appeared.

One defect still blocks. It dates from cycle 1 and I missed it then. When the caller passes `alias='_i'`, `resolved_view` returns two extra columns, `rid` and `v`. It happens because the view joins the `_inherit_table()` derived table under the fixed alias `_i` and selects `{alias}.*`.
- The resolved values are still correct.
- The column list breaks the frozen-interface requirement ("the view's added columns are unchanged") and alias safety ("inner subquery aliases must not collide").
- The cycle-1 code (903cdd) has the same leak. In cycle 1 I compared aliases by values only and not by column list, so this is my miss, not something this cycle introduced.
- The fix is the same pattern the implementer used for `{alias}__ar`.

### My two cycle-2 issues
| Issue | Status | Evidence |
|---|---|---|
| 1. `alias='_ar'` collision | **FIXED** | `alias_chk.py`: `_ar` view and standalone both `same`. `alias_chk3.py` covers 30 aliases × 2 tables × 3 forms (bare view, `WITH r AS`, standalone) and compares values on all of them. Aliases: `t r R T x1 x9 q _ar t__ar r__ar t__ar__ar T__AR _i _r _m _x _q _ru _rx _w rid v token_usage cost_usage session_repo_timeline main a__ar ar _1 Tbl2`. Values are identical to the default for every alias; the only problem is the `_i` column leak (issue below). The fix is the derived inner alias `{alias}__ar` (attribute.py:103-118). |
| 2. NULL-repo as-of row: view vs standalone | **FIXED** | `newrisk3.py` §1: all three cases match across view, standalone and original. Case a (NULL as-of repo, inheritable unknown first row) gives `('unknown','timeline')` on all three. The standalone at attribute.py:238-243 is now `COALESCE(_i.v on COALESCE(as_of_rid, first_rid), FIRST.repo, alias.repo)`, the same chain as the view's `rr` (lines 296, 304). |

### The extra first-term change
I judge it correct and necessary. With only the second term changed, a datapoint that comes before the session's first row (an inheritable unknown row) would have lost inheritance in the standalone path only. Checks:
- **Datapoint before an inheritable unknown first row:** both paths give `Q` (`alias_chk3.py`, k2). The original gives `unknown`, as expected, because the original never inherits.
- **NULL as-of repo:** both paths give `unknown`, the same as the original.
- **First row real:** unchanged.
- **Ties:** `samerow2.py` 4/4. A real repo that sorts above `unknown` wins in either insertion order. An `unknown` row at an unrelated cwd that wins the tie does not borrow a real row's cwd. A first-row tie goes to the lower repo under ASC.

### Regressions and independent model (re-run on hash 3a2a637)
- **`func2.py`:** 124/124, 0 view-vs-standalone disagreements. All 22 BLOCKED and 8 ALLOWED paths, the extra 27 blocked and 5 allowed paths, and the adversarial list are unchanged. No unrelated folder inherits.
- **`regress2.py` / `regress2_noties.py`:**
  - new vs original: 0 / 0 / 23 differences.
  - new vs model: 0.
  - view vs standalone: 0 in every mode.
  - row-count mismatches: 0.
- **NULL-heavy variant (`regress3_nullheavy.py`):** 12,460 datapoints with many NULL repos and datapoints before the first row. View vs standalone: 0. It showed 2 differences against my cycle-1 model. Both are the case the user ruled on in cycle 2: the as-of row has a NULL repo, so the fallback is the first row's raw repo with no inheritance. My cycle-1 model still inherited there.
- **Model updated to that rule (`regress4.py`, `regress4_nullheavy.py`):** 0 mismatches on `resolved_repo` and on `attribution_source`.
- **New vs original:** every difference (23 and 18) is a datapoint the original resolved to `unknown`. Not one datapoint the original billed to a real repo was changed (`x_regress4*.py`: `diffs where ORIGINAL was not unknown: 0`).
- **Real consumers (`newrisk3.py` §4):** `bill.run` with and without an email filter, `invoice.gather` with a date window, `reconcile.otel_totals` / `otel_daily` / `otel_by_surface`, and `export.build`.
  - On an inheritance store, over 6 seeds, output is identical to a view built from the standalone expressions.
  - On a no-unknown store, over 6 seeds, output is identical to the ORIGINAL view.
- **Default-alias checks:**
  - Column lists are the table columns plus `resolved_repo` and `attribution_source`, for both tables (§2).
  - LEFT JOIN cardinality is 150/150/150 with ties and NULL primary-key duplicates (§3).
  - Reversing the insertion order changes nothing.
- **SQL text:**
  - The single-backslash `'\'` literal is present.
  - There is no LIKE, REGEXP or MATCH.
  - Every GLOB uses a fixed literal pattern.

### AC table
| AC | Result |
|---|---|
| 1-8 | ✅ `func2.py` 124/124 plus `samerow2.py` |
| 9 | ✅ for `x`, `r` and every other alias except the `_i` column leak (issue below) |
| 10 | ✅ I ran the rung-2 command myself: `136 passed in 15.60s` |
| 11 | ✅ absolute limit (table below) |
| 12 | ✅ `git status --short` shows ` M billing/otel/attribute.py` and `?? _goals/unknown-parent-child-inheritance/` only. `git hash-object` = `3a2a637fa5804abe008ebc7aa787a42ff535ebc8`. This cycle's change against `attribute_v4_903cdd5.py` is confined to `_AS_OF`/`_FIRST`/`_fmt`, the `resolved_repo` body and its docstring. |

### Perf (`eval06/perf_eval.db`, one process per statement and version, default connect, warm-up then median of 3, two rounds)
| Statement | orig s | new s | ratio (information only) | new s per 100k |
|---|---|---|---|---|
| **export `_scan` token** | 0.850 / 0.846 | 1.113 / 1.116 | 1.31 / 1.32 | **0.859 / 0.861** |
| export `_scan` cost | 0.790 / 0.797 | 1.086 / 1.093 | 1.37 / 1.37 | 0.858 / 0.864 |
| bill cost | 0.359 / 0.375 | 0.772 / 0.776 | 2.15 / 2.07 | 0.610 / 0.613 |
| **bill token** | 0.377 / 0.393 | 0.786 / 0.791 | 2.09 / 2.01 | **0.606 / 0.611** |
| bill source | 0.267 / 0.266 | 0.679 / 0.681 | 2.55 / 2.56 | 0.524 / 0.526 |
| reconcile `otel_totals` | 0.360 / 0.355 | 0.855 / 0.841 | 2.38 / 2.37 | 0.660 / 0.649 |
| reconcile daily | 0.432 / 0.388 | 0.949 / 0.943 | 2.20 / 2.43 | 0.732 / 0.728 |

All seven are under 1.0 s per 100k. The export plan still shows one `MATERIALIZE _i` and one `SEARCH _i USING AUTOMATIC COVERING INDEX (rid=?) LEFT-JOIN`.

### Issues found
1. **[major] attribute.py:296 and 304 (the `_i` alias is hard-coded in `_inherit_table()`, see its docstring at :163): `resolved_view(table, alias='_i')` leaks `rid` and `v`.**
   - Output columns become the table columns, then `rid`, `v`, `resolved_repo`, `attribution_source` (`alias_chk3.py`, both tables).
   - The cause: `SELECT _i.*` expands over both `{table} _i` and the joined derived table `_i`.
   - The values stay correct and no current caller passes `_i`.
   - It is a column-list change, and a requirement names both alias safety and the frozen view columns, so it is not minor.
   - It already existed at 903cdd (verified by running the saved copy). I missed it in cycle 1 because I compared values only.
   - Fix: derive the join alias from the caller's alias, e.g. `f"{alias}__i"`, the same way `{alias}__ar` is derived, in both the view and the standalone probe. Re-run `alias_chk3.py`, which checks columns as well as values.

### Notes (non-blocking)
- Residual paths from earlier cycles are unchanged and are not re-raised, as instructed.
- The two NULL-repo differences against my cycle-1 model are the rule the user decided in cycle 2, not regressions. The updated model agrees completely.

### Required fixes
- [ ] Make the view's join alias, and the standalone's `_i` probe alias, collision-proof against the caller's alias, e.g. `f"{alias}__i"`. Confirm that `alias_chk3.py` reports `problems: 0`, so `SELECT *` from the view returns exactly the table columns plus `resolved_repo` and `attribution_source` for every alias, `_i` included. Re-run rung 2 and record the new hash.

### Footprint
files_read: 3 (~14,000 chars): 10-context.md, 09-report.md, and the git/diff output of attribute.py against `attribute_v4_903cdd5.py`.
commands_run: 11. New scratch files are under `C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\efecdfb4-de1b-4a6f-9f68-641f5525f749\scratchpad\eval06\`: alias_chk3.py, regress3_nullheavy.py, regress4.py, regress4_nullheavy.py, x_regress4.py and x_regress4_nullheavy.py. No repo file was touched, and no checkout, restore, stash or reset was used.
