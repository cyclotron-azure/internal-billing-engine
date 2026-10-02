**Model (self-reported)**: claude-sonnet-5-5

## Measurement complete (no repo file touched)

Store: 135,000 `token_usage` rows, 135,000 `cost_usage` rows, 40,400 timeline rows, 2,001 sessions, 32.5% of datapoints with an unknown effective row. I seeded `cost_usage` from `token_usage` with `cost_source='actual'`, and gave `token_usage` models (3), user emails (40) and token types (4).

I ran the statements from `export.py` `_scan`, `bill.py` and `reconcile.py` verbatim, built from each module's own `resolved_view`. I did not run `export.build()` itself. Timings are the median of 3 runs on the same warm `perf.db`, after one warm-up run.

| Statement | orig s | new s | ratio | new s per 100k datapoints |
|---|---|---|---|---|
| export `_scan` token_usage | 0.327 | 0.909 | 2.78 | 0.674 |
| export `_scan` cost_usage | 0.404 | 0.947 | 2.35 | 0.702 |
| bill cost agg | 0.137 | 0.361 | 2.63 | 0.267 |
| bill token agg | 0.146 | 0.376 | 2.57 | 0.279 |
| bill source agg (`attribution_source`) | 0.090 | 0.236 | 2.62 | 0.175 |
| reconcile `otel_totals` | 0.143 | 0.367 | 2.57 | 0.272 |
| reconcile daily | 0.165 | 0.420 | 2.55 | 0.311 |

- **Row counts:** the export result drops from 35,737 groups to 960 because the unknown sessions collapse into their inherited repos. The other statements go from 27/108/36/40 rows to 24/96/32/32.
- **Worst case:** `export _scan` at about 0.7 s per 100k datapoints. That is roughly 0.9 s on this 135k store, so a million datapoints would take on the order of 7 s.
- **Real queries stay under 3x:** the real consumer statements all came in below 3.0x (2.35-2.78), unlike the bare `GROUP BY` benchmark at 3.52x. The original queries do more work per row, which dilutes the fixed cost.

**Plan for the export token statement.**
- The second `_i` copy is not the only repeat. `resolved_view` builds `resolved_repo` several times in that statement: the `resolved_repo` column, the two `CASE WHEN resolved_repo = 'unknown'` expressions, and the one inside `attribution_source`. Each copy has an as-of `_i` and a first-row `_i`.
- Excerpt of the 8 `CO-ROUTINE _i` blocks and 8 `SEARCH _i USING AUTOMATIC COVERING INDEX (rid=?)` probes:
```
15   CO-ROUTINE _i
418  SEARCH _i USING AUTOMATIC COVERING INDEX (rid=?)
478  CO-ROUTINE _i
881  SEARCH _i USING AUTOMATIC COVERING INDEX (rid=?)
... (8 pairs in total)
```
- Each block has its own build and index, so the repeated copies probably cost more than the single-column benchmark suggested. The plan does not show how much of the 0.9 s that is. I did not measure how much the first-row copies add, because SQLite only builds them if a datapoint precedes its session's first timeline row, and none do in this store.

**Cheap, spec-compatible improvement (described, not applied).**
- Split `resolved_view` so `resolved_repo` is computed once per row and `attribution_source` and the two `CASE` expressions reuse that column. For example, wrap the view as `SELECT *, <resolved_repo> AS resolved_repo FROM (...)` and derive `attribution_source` from the inner column.
- That would cut about four `_i` build and probe pairs to one. It needs a restructure of `resolved_view` and `attribution_source`, so the evaluator should check it still honours the frozen interface.

**Hand-off hash.**
- `git hash-object billing/otel/attribute.py` = `56e3526d8aa251c99017a0a783aa718a202189ab`, unchanged.
- `git status --short` shows ` M billing/otel/attribute.py` and `?? _goals/unknown-parent-child-inheritance/`, nothing else.
- `consumers.py` in the scratchpad reproduces the timings.
- The measurement-only task is done. The earlier report on task 01 stands: AC11 under the original 3x gate was 3.52x on the bare view.

### Footprint
files_read: 4 (~25,000 chars: `05-context.md` plus excerpts of `export.py`, `bill.py` and `reconcile.py`)
commands_run: 3
