**Model (self-reported)**: claude-opus-5-5
## Verdict: NEEDS FIXES
**Score**: 4/5
**failure_class:** implementation

Both of my cycle-1 findings are fixed for the cases that matter. The amended AC11 gate passes on my store and on the implementer's, with every statement run in its own process. AC1-10 and AC12 pass again. The single-LEFT-JOIN view matches the standalone expressions on every randomized and consumer-level comparison I ran. The two remaining defects are both narrow. I mark them major only because a requirement names each one, so neither can be minor. The orchestrator may choose to route them to the user instead of a fix cycle.

1. **`alias='_ar'` collides.** The new inner alias `_ar` breaks "works for any alias" and silently misattributes every row.
2. **NULL repo on the as-of row.** When the as-of row's repo is NULL and the first row is an inheritable `unknown`, `resolved_view` and the standalone `resolved_repo()` disagree. The docstring at attribute.py:270 says they are the same. The receiver cannot write a NULL repo today.

### My two cycle-1 findings
| Finding | Status | Evidence |
|---|---|---|
| Perf blocker (amended AC11: at most 1.0 s per 100k, each statement in its own process) | **FIXED** | All 7 statements are at most 0.884 s per 100k on my store and at most 0.596 s per 100k on `perf.db` (tables below). `EXPLAIN QUERY PLAN` on the export token statement shows exactly one `MATERIALIZE _i` and one `SEARCH _i USING AUTOMATIC COVERING INDEX (rid=?) LEFT-JOIN`. Before the fix there were 8 co-routines. |
| `alias='r'` collision | **FIXED for 'r', but new residual `_ar`** | `alias_chk.py` and `func2.py`: `r`, `R`, `x1`, `q`, `token_usage`, `_i`, `_r`, `_m`, `_x`, `_q`, `_ru`, `_rx` and `_w` all match the default alias, in both the view and the standalone path. `_ar` misattributes every row (see issue 1). |
| Comments and docstrings (minor note from cycle 1) | FIXED | attribute.py:159-163 now says "co-routine once per use". The "instr-free" wording is gone (line 130). Lines 207-208 and 223-224 document the tie-break and the per-use `_i`. |

### AC table
| AC | Result | Evidence |
|---|---|---|
| 1-6 | ✅ | `func2.py` scored 124/124. The tie expectations were updated to the repo rule, and every scenario was also checked view against standalone (0 disagreements). |
| 7 | ✅ | All 22 BLOCKED, the 8 ALLOWED (5 required plus the three extra allowed paths), 27 extra blocked and 5 extra allowed paths behave as listed. The 5 INFO residual cases are unchanged. |
| 8 | ✅ | DirectoryAdded-only anchor, session_id 'unknown', empty and NULL cwd, real rows with NULL cwd or NULL repo all stay unknown. A real row with NULL event counts. |
| 9 | ✅ | `alias='x'` inside `WITH r AS` and the reconcile bare subquery both match the default. See issue 1 for `_ar`. |
| 10 | ✅ | I ran the rung-2 command myself: `136 passed in 15.59s`. |
| 11 | ✅ | Per-process tables below. |
| 12 | ✅ | `git status --short` shows ` M billing/otel/attribute.py` and `?? _goals/unknown-parent-child-inheritance/` only. `git hash-object` = `903cdd549895384908c91d45c5dba2ac913179f8`. |

### Perf: seven statements, one process per statement and version
Method:
- `eval06/perf_drive.py` and `perf_one.py`.
- A fresh `sqlite3.connect` with default settings, as `OtelStore` uses. No 200 MB cache.
- One warm-up, then the median of 3.

**Store `eval06/perf_eval.db`** (129,600 token rows, 126,600 cost rows). Two full rounds, shown as round 1 / round 2:

| Statement | orig s | new s | ratio (information only) | new s per 100k |
|---|---|---|---|---|
| export `_scan` token | 0.753 / 0.832 | 1.114 / 1.146 | 1.48 / 1.38 | **0.860 / 0.884** |
| export `_scan` cost | 0.790 / 0.804 | 1.095 / 1.099 | 1.38 / 1.37 | 0.865 / 0.868 |
| bill cost | 0.361 / 0.350 | 0.768 / 0.766 | 2.13 / 2.19 | 0.606 / 0.605 |
| bill token | 0.383 / 0.385 | 0.796 / 0.794 | 2.08 / 2.06 | 0.614 / 0.613 |
| bill source | 0.260 / 0.266 | 0.678 / 0.678 | 2.60 / 2.55 | 0.523 / 0.523 |
| reconcile `otel_totals` | 0.359 / 0.360 | 0.867 / 0.857 | 2.41 / 2.38 | 0.669 / 0.661 |
| reconcile daily | 0.434 / 0.430 | 0.960 / 0.959 | 2.21 / 2.23 | 0.741 / 0.740 |

**Store `scratchpad/perf.db`** (135,000 rows), one round:

| Statement | orig s | new s | ratio | new s per 100k |
|---|---|---|---|---|
| export `_scan` token | 0.862 | 0.804 | 0.93 | 0.595 |
| export `_scan` cost | 0.888 | 0.805 | 0.91 | 0.596 |
| bill cost | 0.333 | 0.592 | 1.78 | 0.439 |
| bill token | 0.367 | 0.617 | 1.68 | 0.457 |
| bill source | 0.241 | 0.515 | 2.14 | 0.382 |
| reconcile `otel_totals` | 0.345 | 0.677 | 1.96 | 0.502 |
| reconcile daily | 0.409 | 0.760 | 1.86 | 0.563 |

The machine was slow during these runs: the originals ran about 2x slower than in my cycle-1 runs. Even so, every statement passes. The thinnest margin is export token on my store at 0.884 s per 100k, which leaves about 12% headroom on a loaded machine.

### New risk surface: what I verified
- **(a) Column list.**
  - ✅ For both token_usage and cost_usage, the view's `cursor.description` equals `PRAGMA table_info` plus `resolved_repo` and `attribution_source`.
  - The same holds through `WITH r AS (...) SELECT *`. No `_i` column leaks (`newrisk.py` §2).
- **(b) View against standalone.** ✅ 0 disagreements:
  - in every `func2.py` scenario;
  - on the randomized generators: `regress2.py` (noun, noqual and mixed modes, 22,398 datapoints) and `regress2_noties.py`;
  - in the cardinality store.
- **Independent spec model, re-keyed to `(ts, seq, repo)` with NULL sorted first:**
  - ✅ 0 mismatches on `resolved_repo` and 0 on `attribution_source` in all modes.
  - New against original: 0 differences in the no-unknown and no-qualifying modes, now even with ties. The repo tie-break follows the same PK order the original effectively used.
  - In mixed mode the 23 differences are all inheritance, and the model agrees with every one.
- **(c) Real consumers** (`newrisk3.py`). These called the actual functions, with only `resolved_view` monkeypatched:
  - `bill.run` with and without an email filter;
  - `invoice.gather` with a date window;
  - `reconcile.otel_totals` (with emails, and over all dates), `otel_daily` and `otel_by_surface`;
  - `export.build`.
  - ✅ Over 6 seeds each, the new view gives identical output to a view built from the standalone expressions (on a store with inheritance) and to the ORIGINAL view (on a store with no unknown rows).
  - I masked lambda addresses and `generated_at`, which change between runs regardless of the view.
- **(d) LEFT JOIN cardinality.** ✅ View count = table count = distinct `dp_key`, for both tables.
  - This includes 5-way identical (session, ts, seq) ties with the same cwd, and duplicate rows with NULL session_id, ts, seq or repo.
  - Counts also match on both perf stores (rows 129,600 / 135,000).
  - Reinserting the timeline in reverse rowid order gives identical results.
- **(e) Frozen interface.** ✅ The signatures still return `str`. `TIMELINE_TABLE` is unchanged. The only import is `from __future__`, and there is no CREATE, INSERT, UPDATE or `create_function`.
- **Same-row property and determinism under the repo tie-break** (`samerow.py`, `samerow2.py`). ✅ All cases below pass:
  - An as-of tie between `unknown` at an unrelated cwd and a related real row stays `unknown`. Mixing repo and cwd across rows would have produced Q.
  - A real repo `zeta` that sorts above `unknown` wins the tie in both insertion orders.
  - A first-row tie goes to `github.com/q` under ASC.
- **SQL text.** ✅ The single-backslash `'\'` is present and `'\\'` is absent. There is no LIKE, REGEXP or MATCH, and every GLOB pattern is a fixed literal.
- **Strictness.** ✅ No unrelated folder newly inherits. The adversarial results are identical to cycle 1.

### Issues found
1. **[major] attribute.py:101-103, 109-111 — inner alias `_ar` collides with `alias='_ar'`.**
   - The correlation becomes `_ar.session_id = _ar.session_id`, which is always true. Every datapoint then resolves to whatever row is globally first. In `alias_chk.py`, all three datapoints became `('R','timeline')`. Expected: R, Z, and wtag/wrapper.
   - Both the view and the standalone path are affected. This contradicts "works for any alias; inner subquery aliases must not collide with it".
   - No current caller passes `_ar`. My cycle-1 required fix said "rename to an underscore-prefixed name", and the implementer did exactly that, so the gap is partly in my own prescription.
   - It is still major because a requirement names it. The fix is trivial: derive the correlated inner alias from the caller's alias, e.g. `f"{alias}__ar"`, which can never equal `alias`.
2. **[major] attribute.py:282-283 vs 230-231 and docstring line 270 — `resolved_view` and standalone `resolved_repo` diverge.**
   - The case: the as-of row has NULL repo, and the session's first row is an inheritable `unknown`.
   - Seeded case (`newrisk.py` §1): an unknown row at `C:\dev\proj`, then a NULL-repo row, then real R at `C:\dev\proj\x`; the datapoint comes after the NULL-repo row.
   - Result: the view gives `('unknown','timeline')`, the same as the original. The standalone gives `('R','timeline')`.
   - The view falls back to the first row's RAW repo, while the standalone falls back to the first row's `_i` value.
   - It cannot occur through ingest: `receiver.py:383-385` always passes `normalize_remote(...)`, which never returns NULL (normalize.py:56, 67). No consumer calls the standalone functions.
   - It is still a behaviour divergence that the docstring explicitly denies, so by definition it is not minor.
   - Smallest fix: make the standalone's second COALESCE term `_FIRST.format(col='repo')`, matching both the view and the original. Alternatively, have the user rule the NULL-repo case undefined and soften the docstring.

### Notes (non-blocking)
- These residuals are unchanged from cycle 1 and still inherit:
  - `\\?\UNC\srv\share` (an extended-length UNC share root);
  - non-canonical `..` segments;
  - trailing-dot names such as `Code.`;
  - relative paths;
  - `C:\Users\x\AppData\Local`;
  - `/media/<u>/<disk>/proj` (already known).
  - All of these are spec-conformant. Surface them at delivery.
- Repo tie-break: on an exact (session, ts, seq) tie, the `unknown` row beats lowercase real repos (`'u' > 'g'`). That matches the original's effective PK order (0 differences against the original under ties), and it was orchestrator-approved.
- Duplicate rows with NULL primary-key columns are possible in a rowid table, so the tie-break is not strictly total there. The NULL-session rows never join, and NULL-repo rows never inherit, so the effect is cosmetic. It cannot be reached through the receiver.
- The implementer's own pass of `eval06/func.py` reported 122/124. The 2 failures were the old rowid-rule tie expectations. `func2.py` encodes the repo rule and passes 124/124.
- Known notes, carried forward: AC5 wording `C:\mono` vs `C:\dev\mono` (both verified).

### Required fixes
- [ ] Make the correlated inner alias in `_AS_OF`/`_FIRST` collision-proof against any caller alias (e.g. derive it from `alias`). Confirm that `alias='_ar'` (and the new name itself) match the default, in both the view and the standalone path.
- [ ] Make standalone `resolved_repo()` and `resolved_view` agree when the as-of row has a NULL repo. Preferred: the standalone falls back to the first row's raw repo, as the original and the view do. Alternatively, get a user ruling and correct the docstring at attribute.py:270. Re-run `eval06/newrisk.py` §1 and the rung-2 command, then record the new hash.

### Footprint
files_read: 5 (~32,000 chars): 08-context.md, 07-report.md, attribute.py, otel_store.py `__init__` excerpt, and sed/grep excerpts of bill.py, invoice.py, export.py, receiver.py and normalize.py.
commands_run: 19. New scratch files are all under `C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\efecdfb4-de1b-4a6f-9f68-641f5525f749\scratchpad\eval06\`: func2.py, regress2.py, regress2_noties.py, newrisk.py, newrisk2.py, newrisk3.py, alias_chk.py, samerow2.py, perf_one.py and perf_drive.py. No repo file was touched, and no checkout, restore, stash or reset was used.
