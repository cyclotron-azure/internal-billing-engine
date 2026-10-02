**Model (self-reported)**: claude-opus-5-5
## Verdict: NEEDS FIXES
**Score**: 4/5
**failure_class:** implementation

Task 01 is functionally sound, and the `_i` column leak is fixed. One gap remains. A quoted alias such as `alias='"x y"'` used to work in the original code and now raises a syntax error. It never produces wrong numbers, and nothing in the repo passes a quoted alias, but the requirement says "works for any alias" and the constraints say "valid SQL for any alias". So under the task-criteria minor rule it cannot be a note, and this final cycle escalates it to you. Part of the cause is my own cycle-1 prescription (`f"{alias}__ar"`). Details are under Issues found. Every other check passed:
- The cycle-3 issue is fixed: no internal alias can leak columns or collide for any bare-identifier alias.
- No behaviour regressed.
- Nothing unrelated inherits.
- The amended absolute perf gate holds.

**Cycle-3 issue (alias='_i' leaks `rid` and `v`): FIXED.**
- The join alias is now derived from the caller's alias, `{alias}__i`, in both the view and the standalone path (attribute.py:116-125, 169-173, 215, 250-251, 300-315).
- `alias_chk3.py` reports `problems: 0`, checking both columns and values.

**Correction carried from cycle 2:** my cycle-2 report wrongly said the user ruled on the NULL-repo as-of case. The user made no such ruling. On the merits:
- When the effective as-of row has a NULL repo, the code falls back to the first row's RAW repo, then to the wrapper tag.
- That is exactly the original COALESCE chain.
- It is the conservative choice: no inheritance on a malformed row.
- It is unreachable, because the receiver always writes `normalize_remote(...)`, which is never NULL.
- View, standalone and original agree on it (`newrisk3.py` §1: all three cases SAME).
- Not a defect.

### AC table
| AC | Result | Evidence (re-run on bb56eb27) |
|---|---|---|
| 1-8 | ✅ | `func2.py` 124/124, with 0 view-vs-standalone disagreements. `samerow2.py` 4/4 (same-row and tie determinism). |
| 7 / strictness | ✅ | All 22 BLOCKED, 8 ALLOWED, 27 extra blocked and 5 extra allowed paths behave as listed. The INFO list holds exactly the 5 known residual paths, unchanged. No unrelated folder inherits. |
| 9 | ✅ for bare identifiers, ❌ for quoted aliases | See the issue below. |
| 10 | ✅ | `136 passed in 15.81s`, exact rung-2 command run by me. |
| 11 | ✅ | Perf tables below. |
| 12 | ✅ | `git status --short` shows only ` M billing/otel/attribute.py` and `?? _goals/unknown-parent-child-inheritance/`. `git hash-object` = `bb56eb27449e8d9a41d80879f993068cdbbfea36`. The delta against `attribute_v5_3a2a637.py` is confined to the alias derivation and docstrings. |

### Regressions (all scripts unmodified since I wrote them; timestamps checked)
- **`regress2.py`**
  - New vs original: 0 / 0 / 23 differences.
  - New vs independent model: 0, and `attribution_source` mismatches: 0.
  - View vs standalone: 0 in every mode. Row-count mismatches: none.
- **`regress2_noties.py`:** 0 / 0, model 0, view vs standalone 0.
- **`x_regress4.py` and `x_regress4_nullheavy.py`** (model uses the NULL-repo rule; 12,460 datapoints in the NULL-heavy run):
  - Model mismatches: 0. View vs standalone: 0.
  - `diffs where ORIGINAL was not unknown: 0`. Every change against the original is an inheritance of a datapoint the original left `unknown`.
- **`newrisk3.py`**
  - Column lists are the table columns plus 2, for both tables, also through a CTE.
  - LEFT JOIN cardinality is 150/150/150 with ties and NULL primary-key duplicates.
  - Results do not depend on insertion order.
  - Real consumers, 12 of 12 identical: `bill.run` (with and without an email filter), `invoice.gather` (date window), `reconcile` totals/daily/by-surface, and `export.build`. The 6 inheritance seeds match the standalone-built view, and the 6 no-unknown seeds match the ORIGINAL view.

### Alias attack (`eval06/alias_chk5.py`)
69 bare-identifier aliases × 2 tables × 3 forms (bare view, `WITH r AS`, standalone), plus a column-list check on each: **problems: 0**. The aliases tried:
- **Nested derived names:** `t__i__ar`, `t__ar__i`, `x__i__i`, `_i__i`, `__i`, `__ar`, `a__b__c`.
- **Mixed case:** `T__I`, `Tt__Ar`, `T__AR`.
- **Column names:** `session_id`, `ts`, `repo`, `tokens`, `seq`, `cwd`, `rid`, `v`, `resolved_repo`, `attribution_source`, `usage_source`.
- **Row-id names:** `rowid`, `oid`, `_rowid_`.
- **Schema and keyword-like names that are legal unquoted:** `temp`, `main`, `key`, `action`, `abort`, `replace`, `row`, `view`, `first`, `last`, `filter`.
- **Odd names:** a 200-character alias, a non-ASCII alias (`ÄÖü`), `sqlite_master`, `_`, `t0`.
- **All the earlier aliases:** `_i`, `_ar`, `t__ar`, `r__ar`, `_r`, `_m`, `_x`, `_q`, `_ru`, `_rx`, `_w`, `token_usage`, `cost_usage`, `session_repo_timeline`.
- **Keywords that are illegal as unquoted aliases in SQLite itself:** `order`, `select`, `where`, `group`, `join`, `on`. These cannot be passed bare at all.

### Perf (`eval06/perf_eval.db`, own process per statement and version, median of 3, two rounds)
| Statement | orig s | new s (runs) | new s per 100k |
|---|---|---|---|
| export `_scan` token | 0.835 / 0.836 | 1.127 (1.107, 1.136, 1.127) / 1.125 (1.117, 1.125, 1.153) | **0.869 / 0.868** |
| bill token | 0.389 / 0.397 | 0.794 (0.799, 0.794, 0.783) / 0.812 (0.799, 0.812, 0.816) | **0.613 / 0.626** |

Both are under the 1.0 s per 100k limit. Ratios (information only): 1.35x and 2.04x.

### Issues found
1. **[major] attribute.py:116-125 (`_fmt`): quoted-identifier aliases now produce invalid SQL.**
   - `alias` values `'"x y"'`, `'"order"'`, `'[sp ace]'`, `` '`bt`' `` and even `'"t"'` all fail. `{alias}__ar` / `{alias}__i` render as `"x y"__i`, which raises `OperationalError: near "__i": syntax error`.
   - The original module accepts all five and returns the default rows (`alias_chk5.py`, `QUOTED orig ... same`).
   - This is a narrowing of the accepted alias domain. It began in cycle 2 with `{alias}__ar`, which was my own cycle-1 prescription, and cycle 3 extends it to `__i`.
   - The `_fmt` docstring's claim "whatever the caller's alias is" is false for these inputs.
   - **Impact:** none in production. No caller in `billing/` or `deploy/` passes `alias=` at all; every consumer uses the default `t`. The failure is loud at prepare time and can never produce a wrong bill.
   - **Why it cannot be a note:** the task names it twice. The Requirements say "Alias safety: works for any alias", and the Constraints say "valid SQL for any alias". The behaviour also changes from working to raising. The task-criteria minor rule excludes anything a requirement names and anything that alters behaviour.
   - **Decision for the user (escalation):**
     - (a) Accept "alias must be a bare SQL identifier" as a documented limitation and correct the `_fmt` docstring. No code change; it would then be a note.
     - (b) One small fix: derive the inner names from a sanitised bare form of the alias, e.g. `_` plus the alias with non-alphanumerics replaced, plus the `__ar`/`__i` suffix. That form can never equal a quoted caller alias. Then re-run `alias_chk5.py` until QUOTED new shows `same`.

### Notes (non-blocking)
- The known residuals (AC5 wording, `/media/<u>/<disk>/proj`, deny-list, relative / `..` / trailing-dot paths) are unchanged and, as instructed, not re-raised.

### Footprint
files_read: 3 (~13,000 chars): 12-context.md, 11-report.md, and the diff of attribute.py against `attribute_v5_3a2a637.py`.
commands_run: 6. New scratch file: `C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\efecdfb4-de1b-4a6f-9f68-641f5525f749\scratchpad\eval06\alias_chk5.py`. No repo file was touched, and no checkout, restore, stash or reset was used.
