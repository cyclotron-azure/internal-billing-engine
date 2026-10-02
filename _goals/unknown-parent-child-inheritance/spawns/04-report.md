**Model (self-reported)**: claude-sonnet-5-5

## Task Complete (PARTIAL, performance gate FAILED): task 01 ancestor-of-real-repo inheritance in resolved_repo

AC11 failed: the new view is 3.52x the original, against a limit of 3.0. Per the task I did not try to ship around it. The functional work is done and passes AC1-10 and AC12. `attribute.py` is edited in the working tree and not committed. Please decide whether to accept it, amend the gate, or take the precompute fallback named in goal.md. The decision is yours.

### Design (prose)
- `resolved_repo()` still returns `COALESCE(lookup(as-of row), lookup(first row), {alias}.repo)`.
- Each lookup picks the effective row's rowid with the same as-of or first selection as before. The tie-breaks are now `rowid DESC` for as-of and `rowid ASC` for first, appended after `ts, seq`. That rowid is looked up in `_i`, which maps every timeline rowid to its resolved repo.
- `_i` has no reference to the datapoint, so SQLite materialises it once per statement (`LIMIT -1` stops it being flattened) and probes it through an automatic index. The plan shows `CO-ROUTINE _i`, `BLOOM FILTER`, and `SEARCH _i USING AUTOMATIC COVERING INDEX (rid=?)`.
- For each timeline row, `_i.v` is:
  - the row's own repo when it is not `'unknown'` (via `IS NOT 'unknown'`, so NULL repo does not inherit);
  - `'unknown'` when the row is `'unknown'` and the session_id is NULL or `'unknown'`, or the path is blocked;
  - otherwise the inherited repo: a scalar subquery over a materialised `_x`, keyed by session. `_x` holds the rows with `repo <> 'unknown'` and `ifnull(event,'') <> 'DirectoryAdded'`, each with its normalised cwd. A row qualifies when `x.n <> ''` and `u.n <> ''` and `(x.n = u.n OR substr(x.n,1,length(u.n)+1) = u.n || '/')`. The result is `min(repo)` when `count(*) > 0 AND min(repo) = max(repo)`, else NULL, which becomes `'unknown'` through `ifnull`.
- Repo and inherited value always come from the same row because both are keyed by rid.
- `_norm()` uses a raw string, so the SQL contains the single-backslash literal `'\'`. A check shows the count of `'\'` is above 0 and the count of `'\\'` is 0.
- `_blocked()` is built from module constants (`_CONTAINER_NAMES` with 19 names, `_HOME_PARENTS`, `_MOUNT_PREFIXES`) using only equality, `substr`, `IN`, and `GLOB` with fixed literal patterns. Path text is never a pattern. The last segment uses the `rtrim(n, replace(n,'/',''))` idiom.
- `attribution_source` keeps its CASE order. It now calls `_AS_OF`/`_FIRST` with `col='repo'`, and those templates gained the rowid tie-breaks. `desktop-scratch` is still first and keys off `resolved_repo = 'unknown'`.
- The module docstring and the `resolved_repo` docstring describe the new rule. No new imports, tables, or indexes. Nothing is persisted.

### Files changed
- `C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\billing\otel\attribute.py` (whole-file rewrite). Nothing else in the repo was touched.

### Evidence
No new tests belong to this task (task 02 owns them), so rung 1 is empty. All ad-hoc output below came from `ac.py` in the scratchpad, using a temp `OtelStore` DB with raw INSERTs. The final run matches earlier runs exactly.
- **AC1:** `[('R','timeline'), ('R','timeline')]`. The datapoint on the t1 unknown row resolves to R, source `timeline`.
- **AC2:** `[('R','timeline'), ('unknown','timeline')]`. The real parent holds R and the unknown child stays `unknown`.
- **AC3:** Dashnoard (unknown) versus the unrelated orbit-local real row gives `unknown` at all three datapoints.
- **AC4:**
  - Two different qualifying repos: `unknown`.
  - Two qualifying rows naming the same repo: `A`.
  - Zero real rows: `unknown`.
  - A real row in another session does not leak: `unknown`.
- **AC5:** effective row M gives `M` and effective row S gives `S2`. A real effective row with a related unknown row keeps `R`.
- **AC6:** `C:\dev\wealth` versus `C:\dev\wealthspire\x` stays `unknown`. Mixed case, mixed separators, and a trailing `/` resolve correctly to `R`.
- **AC7:** all 22 BLOCKED paths gave `unknown` even with a real child. All 5 ALLOWED paths plus `/mnt/c/dev/wealthspire` and `/c/dev/wealthspire` gave `R`. The run reported `blocklist mismatches: 0`.
- **AC8:**
  - DirectoryAdded-only anchor: `unknown`.
  - session_id `'unknown'`: `unknown`.
  - Empty cwd: `unknown`.
  - NULL cwd (raw INSERT): `unknown`.
  - Real row with NULL cwd: `unknown`.
  - Real row with NULL event: counts, gives `R`.
  - Same-folder real row: `R`.
  - A transcript session that stays unknown reports `desktop-scratch`. One that inherits reports `timeline`.
  - No timeline rows at all gives the wrapper tag with source `wrapper`.
  - A datapoint before the first row uses the first row.
  - Paths containing `%` and `_`: related path gives `R`, a lookalike path gives `unknown`.
- **AC9:** `resolved_view('token_usage', alias='x')` inside `WITH r AS (...)` returned the same rows as the default alias (`AC9 same: True`). `resolved_repo('zz')` also works as a subquery.
- **AC10 (rung 2):** `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_invoice.py tests/test_reconcile.py tests/test_export.py tests/test_export_unattributed.py tests/test_integration_desktop.py -q` gave 136 passed. No existing test encoded the old behaviour.

### AC11: performance gate (FAILED)
- **Synthetic store:** `perf.db` in the scratchpad (not in the repo).
  - 135,000 `token_usage` rows and 2,001 sessions.
  - 40,400 timeline rows (20 per session, 7 of the 20 unknown), plus a heavy-tail session of 400 timeline rows and 25,000 datapoints.
  - 32.5% of datapoints have an unknown effective row.
- **Method:** `SELECT resolved_repo, count(*) FROM (resolved_view('token_usage')) GROUP BY 1`, median of 3 runs, same warm DB file.

| Version | Runs (s) | Median |
|---|---|---|
| original | 0.075, 0.075, 0.076 | 0.075 s |
| new | 0.280, 0.263, 0.266 | 0.266 s |

- **Ratio: 3.52 (limit 3.0).** Earlier iterations of the new code ran at 14x, 5x, and 4.5x. Runs from the same design vary between roughly 3.5x and 4.6x with machine noise.
- **Why it fails:** the original does one covering-index probe per datapoint (about 0.5 µs, 0.072 s total). The new design needs two:
  - **Per datapoint:** the as-of lookup now also returns the rowid and needs a sort for the `rowid DESC` tie-break, about 0.09-0.11 s. The probe into `_i` adds about 0.07 s.
  - **Once per statement:** building `_i` over 40k timeline rows costs about 0.11 s. Of that, evaluating the blocklist costs about 0.03-0.05 s and the inheritance subqueries about 0.07-0.09 s.
- **Tried without enough gain:**
  - Correlated per-datapoint inheritance: 141x.
  - Materialising only the unknown rows, with a join back to the table row: 14x, then 5x.
  - Replacing `rowid` with `repo` as the tie-break to avoid the sort: no gain.
  - De-duplicating by (session, cwd): 0.099 s versus 0.113 s for building `_i`.
- **Why I think 3.0 is unlikely in pure SQL:** I did not exhaust every design. The baseline is only 0.072 s for 135k datapoints, so +0.144 s is the whole budget. The two probes per datapoint already use about 0.16 s before building `_i`.
- **Fallback:** goal.md names the Python-precomputed temp table. A less adversarial store (fewer unknown timeline rows per session) would also lower the ratio, but I did not benchmark one, so I cannot say by how much.
- **Scratch files** (in the scratchpad only):
  - `attribute_orig.py`: the pristine original, used as the baseline.
  - `attribute_rowid_v.py`: an earlier iteration, not the current code.
  - `perf.py`, `perf.db`, `adhoc.py`, `ac.py` and `prof*.py`: the benchmark and ad-hoc checks.
  - The scratchpad also held older scripts that were already there (`blocklist_check*.py`, `escape_check.py`, `spec_check*.py`). I did not use or modify them.

### AC12
`git status --short`:
```
 M billing/otel/attribute.py
?? _goals/unknown-parent-child-inheritance/
```
**Hand-off hash:** `git hash-object billing/otel/attribute.py` = `56e3526d8aa251c99017a0a783aa718a202189ab`. This is the current functionally-complete state that fails AC11. Do not hand it to task 02 as final until the gate decision is made.

### Notes for the evaluator
- **Tie-break semantics:** the spec asks for `rowid DESC`/`ASC` as the final tie-break, and that is what I implemented. Putting `repo` ahead of `rowid` would match the PK index order and skip the sort, but it changes which row wins on a tie, and it gave no measurable gain.
- **NULL repo behaviour:** a timeline row with a NULL `repo` now yields NULL for that lookup. That falls through to the first-row lookup and then `{alias}.repo`, which is close to the old behaviour. The column is not nullable in practice.
- **Second `_i` copy:** `resolved_repo` contains `_i` twice, once for the as-of lookup and once for the first-row fallback. SQLite builds the second only if a datapoint actually precedes the first timeline row. `resolved_view` calls `resolved_repo` twice, once for the column and once inside `attribution_source`, so a view that selects both columns builds `_i` twice. The benchmark query selects only `resolved_repo`.
- **Alias safety:** inner aliases are `_u`, `_i`, `_m`, `_q`, `_ru`, `_rx`, `_x`, and `r`.

### Footprint
files_read: 3 (~35,000 chars: the task file, goal.md and `attribute.py`, plus the context package and grep excerpts of `otel_store.py` and `test_attribute.py`)
commands_run: about 30
