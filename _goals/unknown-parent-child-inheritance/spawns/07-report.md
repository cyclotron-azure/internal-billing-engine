**Model (self-reported)**: claude-sonnet-5-5

## Fix cycle 1 for task 01: one limit still unmet

Everything is fixed except the 3.0x ratio on the bill source aggregation. That statement runs at 2.95-3.33x, and the other six consumer statements pass on both stores. The edit is in `billing/otel/attribute.py`, uncommitted. I stopped there, as instructed, instead of weakening the logic. The new hand-off hash is **`903cdd549895384908c91d45c5dba2ac913179f8`**.

### What changed and why
1. **Alias collision.** The inner `r` in `_AS_OF`/`_FIRST` is now `_ar`. `alias='r'` gives the same rows as the default alias on both stores (`standalone.py`) and in `func.py` (`OK alias='r' same`). The original module still shows its old `r` bug (`ORIG alias='r' DIFF (pre-existing)`).
2. **`resolved_view` now evaluates the lookup once per row.**
   - It is one query: `SELECT t.*, <resolved> AS resolved_repo, CASE ... AS attribution_source FROM table t LEFT JOIN <_inherit_table> _i ON _i.rid = COALESCE(as-of rowid, first rowid)`.
   - The shared `_inherit_table()` helper builds `_i(rid, v)`, which maps every timeline row to its own repo or its inherited repo. The export token plan shows exactly one `MATERIALIZE _i` and one `SEARCH _i USING AUTOMATIC COVERING INDEX (rid=?)`, down from 8 co-routines before.
   - `resolved_view` returns a different SQL string from before, but the same columns and values. The extra join lives in the FROM clause, so no private column leaks. The view cannot call `resolved_repo()` and `attribution_source()`, which would each build their own `_i`.
   - The standalone `resolved_repo(alias)` and `attribution_source(alias)` keep their signatures and still work on their own. On the two stores, `SELECT resolved_repo(), attribution_source()` returns identical rows to the view (129,600 and 135,000 rows).
   - The wrapper-tag and NULL-repo fallback is unchanged: `COALESCE(_i.v, first row's repo, alias.repo)`. The first-row subquery only runs when `_i.v` is NULL.
3. **`_i` is cheaper to build.**
   - Real rows pass straight through a plain `UNION ALL` branch. Only `repo='unknown'` rows go through the normalise, blocklist and inherit pipeline.
   - Slash counts, the path prefix and the last segment are computed once per row. The blocklist uses `k` (slash count) instead of repeated `length`/`replace` calls. The set of blocked and allowed paths is unchanged.
   - The qualifying real rows are pre-normalised once in `_x` and matched through an automatic index on the session.
4. **Tie-break (orchestrator-approved relaxation).**
   - The final tie-break is now `repo DESC` for the as-of lookup and `repo ASC` for the first-row lookup, instead of `rowid`. The primary key is `(session_id, ts, seq, repo)`, so the order is total and deterministic, and SQLite reads it off the PK index without a sort.
   - Repo and cwd still come from the same row, selected by rowid. This is documented in the comments and the `resolved_repo` docstring.
   - Only exact `(session, ts, seq)` ties can pick a different winner than a rowid tie-break would. The two tie-break checks in `eval06/func.py` that encode the rowid rule now fail by design (the 122/124 line below).
5. **Comments.** The false "materialises ONCE per statement" comment now says what happens: `_i` is a co-routine or materialisation built once per use and probed through an automatic index. The "instr-free arithmetic" phrase is replaced. The `_norm` docstring no longer contains a stray backslash escape.

### Performance (AC11 amended, the blocker)
Measured with `consumers2.py` (a copy of `consumers.py` with an `ONLY=` filter). Each statement runs alone in a fresh process, with a 200 MB page cache, after a warm-up, and the figure is the median of 3. It is the verbatim statements from `export._scan`, `bill.py` and `reconcile.py`, built from each module's own `resolved_view`. The machine was noisy; the last two full runs were about 2x slower in absolute terms (originals included), so I give the quieter run first and the later run second where they differ.

| Statement | store | orig s | new s | ratio | new s per 100k |
|---|---|---|---|---|---|
| export `_scan` token | perf.db | 0.296 / 0.789 | 0.252 / 0.753 | 0.85 / 0.95 | 0.19 / 0.56 |
| export `_scan` token | eval | 0.268 / 0.621 | 0.359 / 0.971 | 1.34 / 1.56 | 0.28 / 0.75 |
| export `_scan` cost | perf.db | 0.301 / 0.799 | 0.253 / 0.757 | 0.84 / 0.95 | 0.19 / 0.56 |
| export `_scan` cost | eval | 0.258 / 0.659 | 0.341 / 0.878 | 1.32 / 1.33 | 0.27 / 0.69 |
| bill cost agg | perf.db | 0.094 / 0.263 | 0.190 / 0.554 | 2.02 / 2.11 | 0.14 / 0.41 |
| bill cost agg | eval | 0.096 / 0.214 | 0.232 / 0.529 | 2.42 / 2.47 | 0.18 / 0.42 |
| bill token agg | perf.db | 0.104 / 0.310 | 0.197 / 0.584 | 1.90 / 1.89 | 0.15 / 0.43 |
| bill token agg | eval | 0.105 / 0.235 | 0.238 / 0.559 | 2.27 / 2.38 | 0.18 / 0.43 |
| **bill source agg** | perf.db | 0.063 / 0.162 | 0.169 / 0.488 | 2.69 / 3.02 | 0.13 / 0.36 |
| **bill source agg** | eval | 0.071 / 0.146 | 0.211 / 0.477 | 2.96 / 3.27 | 0.16 / 0.37 |
| reconcile `otel_totals` | perf.db | 0.095 / 0.280 | 0.220 / 0.628 | 2.32 / 2.25 | 0.16 / 0.47 |
| reconcile `otel_totals` | eval | 0.097 / 0.215 | 0.260 / 0.583 | 2.67 / 2.71 | 0.20 / 0.45 |
| reconcile daily | perf.db | 0.115 / 0.333 | 0.246 / 0.701 | 2.15 / 2.11 | 0.18 / 0.52 |
| reconcile daily | eval | 0.122 / 0.252 | 0.290 / 0.644 | 2.39 / 2.56 | 0.22 / 0.50 |

- **Absolute limit:** every statement is at most 0.75 s per 100k datapoints, under the 1.0 s limit.
- **Ratio limit:** every ratio is at most 2.77x except `bill source agg`.
- **`bill source agg` repeated runs:** eval 2.76, 2.98, 2.98, 3.00 (quiet machine) and 3.25, 3.27, 3.33 (loaded machine). perf.db was 2.95-3.02.
- **Why it sits near 3x:** the original does almost no work (about 0.07 s, one index probe per row). The new statement adds the build of `_i` (about 0.10 s) and one probe. The source aggregation uses almost none of the work that the other statements pay anyway.
- **Not tried:** deduplicating inherit work by (session, cwd), or returning repo and rowid from a single probe, both of which look worse than the current design.
- **Harness artifact:** running all statements in one process (the old `consumers.py`) inflated every number, the originals included. On the evaluator's store it showed bill statements at about 0.8 s new against about 0.28 s original, with no sign of it in isolated runs. If the evaluator measures that way, expect higher ratios (up to 4-5x) for the bill and reconcile statements.
- **Export plan check:** `EXPLAIN QUERY PLAN` on the export token statement now shows exactly one `MATERIALIZE _i` and one `SEARCH _i USING AUTOMATIC COVERING INDEX (rid=?) LEFT-JOIN`.

### Evidence AC1-9 (scratchpad `ac.py`; full output in `ac_final2.txt`)
- **AC1:** `[('R','timeline'), ('R','timeline')]`.
- **AC2:** `[('R','timeline'), ('unknown','timeline')]`.
- **AC3:** all three datapoints are `unknown`.
- **AC4:** two repos gives `unknown`, two rows naming the same repo gives `A`, zero real rows gives `unknown`, another session's row does not leak.
- **AC5:** effective row M gives `M`, effective row S gives `S2`, and a real effective row with a related unknown row keeps `R`.
- **AC6:** `C:\dev\wealth` against `wealthspire\x` stays `unknown`. Case, separator and trailing-slash variants give `R`.
- **AC7:** `blocklist mismatches: 0` across the 22 BLOCKED and 7 ALLOWED paths. `func.py` adds 27 more blocked and 5 more allowed paths, all correct.
- **AC8:**
  - DirectoryAdded-only anchor: `unknown`.
  - Session id `'unknown'`: `unknown`.
  - Empty cwd: `unknown`.
  - NULL cwd: `unknown`.
  - Real row with NULL cwd: `unknown`.
  - Real row with NULL event: counts, gives `R`.
  - Same folder: `R`.
  - A transcript session that stays unknown reports `desktop-scratch`; one that inherits reports `timeline`.
- **AC9:** the default alias, `x` inside `WITH r AS`, and `r` all return the same rows. So do the reconcile-style bare subquery and `q`, `token_usage`, `_i`, `_m`, `_x`, `_q`, `_ru`, `_rx`.
- **Backslash check:** `'\'` is present 4 times and `'\\'` is absent.

### Evaluator regressions
- **`func.py`:** 122/124 OK. The two failures are the rowid tie-break checks ("tie as-of rowid DESC (real Q last)" and "tie first rowid ASC (unknown first -> R)"), which encode the rule that was relaxed. The earlier NULL-repo as-of check passes again after the first-row fallback fix.
- **`regress_noties.py`:** `new != orig = 0` on 7,487 and 7,426 datapoints. The 3 and 1 differences it reports against its reference model are exact-tie cases under the old rowid tie-break.
- **`regress.py`:** `new != orig = 0`, 0, and 23 datapoints (the 23 are in the mixed mode, which includes inheritance). The 461, 367 and 384 differences against its reference model are exact ties.
- **Reference model with the repo tie-break:** I rewrote its tie-break key to `(ts, seq, repo)` in `regress_repotb.py` and `regress_noties_repotb.py` in `eval06/`. It shows 0 mismatches on `resolved_repo` and 0 on `attribution_source` across all modes.

### AC10 and AC12
- **Rung 2:** `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_invoice.py tests/test_reconcile.py tests/test_export.py tests/test_export_unattributed.py tests/test_integration_desktop.py -q` gave 136 passed. No existing test needed an edit.
- **`git status --short`:**
  ```
   M billing/otel/attribute.py
  ?? _goals/unknown-parent-child-inheritance/
  ```
- **Hash:** `git hash-object billing/otel/attribute.py` = `903cdd549895384908c91d45c5dba2ac913179f8`. The previous version (`56e3526d...`) is saved as `attribute_v1_56e3526.py` in the scratchpad, with intermediate versions `attribute_v2_join.py` and `attribute_v3.py`. I used no checkout, restore, stash or reset.

### Notes
- `resolved_view` is now a single join-based query, so it diverges structurally from `attribution_source()` and `resolved_repo()`. The standalone check above confirms the results are identical, but the evaluator should keep the two code paths in mind.
- Orchestrator decision needed: accept `bill source agg` at about 3.0-3.3x, or amend that statement's limit (it is 0.17-0.37 s absolute).

### Footprint
files_read: 6 (~30,000 chars: `07-context.md`, `06-report.md`, and `attribute.py` in several slices, plus `eval06` script heads)
commands_run: about 45
