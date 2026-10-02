**Model (self-reported)**: claude-opus-5-5
## Verdict: PASS
**Score**: 5/5

The quoted-alias gap is fixed, the edit is a pure rename of two inner aliases with no behaviour change, and every requirement, AC, regression and strictness probe passes on hash `38d2db20fe79911ed9c9c6e49f714958ee527021`.

**Quoted-alias issue: FIXED.** `_fmt` (attribute.py:117-135) now builds the two inner names from a sanitised form of the alias: `_` + the alias with every character outside `[0-9A-Za-z_]` replaced by `_`, + `__ar` or `__i`. Everywhere else the caller's alias is used verbatim.
- `alias_chk5.py`: the `"x y"`, `"order"`, `[sp ace]`, `` `bt` `` and `"t"` aliases are `same` for both new and original code. 69 bare aliases: `problems: 0`.

### What I verified
- **New alias attack (`eval06/alias_chk7.py`): 54 aliases × 2 tables, 432 checks, 0 problems, 0 derived-name violations.**
  - Forms checked: the view SQL run directly (columns and values), the reconcile-style bare subquery, `WITH r AS`, and the standalone expressions. Column lists were also checked through `SELECT *` from both the subquery and the CTE.
  - Quoted, bracket and literal forms: `"x y"`, `[x]`, `[x y]`, backticks, the string literal `'lit'`, embedded quotes `"a""b"`, `"x'y"` and `"'x'"`, and the empty `""`.
  - Digit-leading `"1x"`/`"9"`, non-ASCII `"ÄÖü ß"`/`ÄÖü`/`é`, and 300-character aliases (quoted and bare).
  - Aliases equal to another alias's derived name: `_t__i`, `"_t__i"`, `_t__ar`, `"_t__ar"`, `[_t__i]`, `` `_t__ar` ``, `_tt__i`.
  - Quoted aliases whose dequoted name equals their OWN derived inner name: `"___x__i___i"` and `"___x__i_"`.
  - Case variants `"T"`, `T`, `t`. Keywords and column names quoted: `"order"`, `"select"`, `"rid"`, `"v"`, `"resolved_repo"`, `"session_id"`, `"ts"`, `"repo"`, `"tokens"`. Punctuation `"%_["`, `"*"`, `"a.b"`, `"))"`, `"--"`, `"/*"`, plus a tab.
  - `alias_chk3.py` (30 aliases) also reports `problems: 0`.
- **Collision argument: ✅ verified independently.**
  - Each inner name is pure ASCII, starts with `_`, and is `len(alias) + 4` or `+ 5` characters long. That is longer than the name SQLite reads after dequoting.
  - The non-ASCII case is safe too. SQLite's case-insensitive comparison folds ASCII only, so a pure-ASCII inner name can only equal an ASCII-only caller name, whose length is at most `len(alias)`.
  - `__ar` and `__i` differ, so the two inner names never equal each other.
  - Empirically, every alias built to collide (`"_t__i"`, `"___x__i___i"` and so on) passed.
- **Edit is rename-only: ✅.** For aliases `t`, `x` and `r`, the SQL from `resolved_repo`, `attribution_source` and `resolved_view` (both tables) is byte-identical to `attribute_v6_bb56eb2.py` once `_{a}__` is mapped back to `{a}__`.
- **Imports: ✅** only `from __future__ import annotations` (AST check).
- **Regressions: ✅** all scripts unchanged since I wrote them.
  - `func2.py`: 124/124 and 0 view-vs-standalone disagreements. The single-backslash literal is present, there is no LIKE, REGEXP or MATCH, and the GLOB patterns are fixed literals.
  - `samerow2.py`: 4/4.
  - `regress2.py`: new vs original 0/0/23, model 0, `attribution_source` mismatches {}, view vs standalone 0, row counts OK.
  - `regress2_noties.py`: 0/0, model 0, view vs standalone 0.
  - `x_regress4.py` and `x_regress4_nullheavy.py` (12,460 datapoints): model 0, view vs standalone 0, `diffs where ORIGINAL was not unknown: 0`.
  - `newrisk3.py`: §1 three SAME. §2 columns are the table's plus 2 for both tables, also through the CTE. §3 150/150/150, independent of insertion order. §4 real consumers (bill with and without email filter, invoice date window, reconcile ×3, export) 12/12 identical.
- **Strictness: ✅**
  - 22 BLOCKED, 8 ALLOWED, 27 extra blocked, 5 extra allowed and the adversarial list all pass.
  - The INFO list is exactly the 5 known residuals, unchanged. No unrelated folder inherits.

### AC table
| AC | Result |
|---|---|
| 1-8 | ✅ `func2.py` 124/124, `samerow2.py` 4/4 |
| 9 | ✅ every alias form above, columns and values |
| 10 | ✅ `136 passed in 14.68s` (exact rung-2 command, run by me) |
| 11 | ✅ absolute limit (perf below) |
| 12 | ✅ `git status --short` shows only ` M billing/otel/attribute.py` and `?? _goals/unknown-parent-child-inheritance/`. `git hash-object` = `38d2db20fe79911ed9c9c6e49f714958ee527021`. |

### Perf (`eval06/perf_eval.db`, separate process per statement and version, median of 3, two rounds)
| Statement | orig s | new s (runs) | new s per 100k |
|---|---|---|---|
| export `_scan` token | 0.328 / 0.330 | 0.424 (0.419, 0.424, 0.452) / 0.427 (0.419, 0.427, 0.472) | **0.327 / 0.329** |
| bill token | 0.142 / 0.141 | 0.282 (0.283, 0.280, 0.282) / 0.287 (0.287, 0.288, 0.284) | **0.217 / 0.221** |

- The machine was quiet this time; the originals ran about 2.5x faster than in the previous cycle.
- Under the earlier load the same statements measured 0.869 and 0.626 s per 100k, also within the limit.
- The query shape is unchanged, since the SQL is identical apart from the rename.

### Issues found
None.

### Footprint
files_read: 3 (~14,000 chars): 14-context.md, 13-report.md, and the diff of attribute.py against `attribute_v6_bb56eb2.py`
commands_run: 5. New scratch file: `C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\efecdfb4-de1b-4a6f-9f68-641f5525f749\scratchpad\eval06\alias_chk7.py`. No repo file was touched, and no checkout, restore, stash or reset was used.
