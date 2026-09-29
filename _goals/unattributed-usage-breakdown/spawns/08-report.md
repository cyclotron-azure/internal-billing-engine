**Model (self-reported)**: claude-sonnet-5-5 (harness reports Sonnet 5.5)
## Task Complete: 02 export-breakdown

### Requirements checklist
- [x] Schema: `attribution_source`, `unattributed_project` appended after `generated_at` in SUMMARY_FIELDS and LINE_FIELDS (export.py:36-44). The CSV headers below confirm it.
- [x] Attributed rows identical to pre-change except generated_at; new cells "". The seeded-store diff below confirms it.
- [x] Unknown rows: line key is (day, `unknown`, model, user, src, label). Summary key is (day, bn, user, src, label). The "is unknown" test is `r["resolved_repo"] == "unknown"` (the repo key, not the bill name). The new columns never pass through name_of, repo_name or repo_name_map, and never enter `repo` / `repo_key`.
- [x] Source class comes from `resolved_view()`'s `attribution_source` column. Label is `load_session_labels(store.db).get(sid, "")`, called once per build().
- [x] Conservation: tokens and cost are summed per split key (`+=`). Spans use min/max per split row via `_span`.
- [x] Each table goes through `resolved_view()` once (shared `_scan` helper). `attribution_source` and `session_id` are wrapped in `CASE WHEN resolved_repo='unknown'` guards. The final rollup is in Python.
- [x] Timing measured (below); the gated 25% ratio is within 3x.
- [x] No new table, column, index, write or commit; single connection.
- [x] Module docstring updated (3 lines, slightly over the 1-2 sentence guide; I count it as one long sentence).
- [x] `build()`, `build_and_enqueue()` and `main()` signatures and return shapes are unchanged.

### Files changed
- C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\billing\otel\export.py — schema fields, the `load_session_labels` import, `_scan` helper with CASE-guarded columns, 6-tuple keys, docstring.
- Scratch only, in the scratchpad: `export_old.py` (HEAD copy with `billing.otel.*` imports), `check.py`, `timing.py`.

### Verification
**AC1.** Ran `python -m billing.otel.export --db <tmp> --out-dir <tmp> --no-enqueue`, which printed 4 summary rows and 4 line rows.
- Summary header: `usage_date_utc, period_start, period_end, repo, user_email, tokens, actual_cost_usd, markup, total_billed_usd, first_usage_at_utc, last_usage_at_utc, generated_at, attribution_source, unattributed_project`
- Line header: `usage_date_utc, period_start, period_end, repo, repo_key, model, user_email, tokens, actual_cost_usd, billed_usd, first_usage_at_utc, last_usage_at_utc, generated_at, attribution_source, unattributed_project`
- The old SUMMARY_FIELDS equals the old CSV header.

**AC2.** The seeded store has one attributed session (`web`), one unknown session with a `...\Dashnoard` timeline, and two unknown sessions without a timeline (one `absent`, one `no_remote`).
- Old export: one unknown line row, 940 tokens, 9.5 cost, spanning 00:00:01 to 00:00:09.
- New export line rows (day, repo, repo_key, model, user, tokens, cost, first, last, source, project):

| repo | tokens | cost | first | last | source | project |
|---|---|---|---|---|---|---|
| `web` | 150 | 2.5 | 00:00:00 | 00:00:05 | "" | "" |
| `unknown` | 400 | 4.0 | 00:00:02 | 00:00:02 | `absent` | "" |
| `unknown` | 40 | 0.5 | 00:00:03 | 00:00:03 | `no_remote` | "" |
| `unknown` | 500 | 5.0 | 00:00:01 | 00:00:09 | `timeline` | `local:Dashnoard` |

- The four summary rows carry the same splits.
- Diff of the attributed rows against the pre-change export, excluding generated_at: `summary attributed identical: True (1 row)`, `lineitems attributed identical: True (1 row)`. The new cells on attributed rows are empty.

**AC3.** Old and new totals per (day, model, user) match: `conserved: True`, 1090 tokens and 12.0 cost for (2026-01-01, claude-sonnet-5, a@x.com). The summary check is per (day, user) and also holds.

**AC4.** Timing used 48,000 datapoints across both tables (24k cost + 24k token), 400 sessions, and 5 runs each of old and new `build()`. In the 25% and 50% stores, half the unknown sessions have timeline rows and half have none. In the 0% store no session is unknown. The ratios are new/old:

| Unknown share | Old best / median | New best / median | Ratio (best) | Ratio (median) |
|---|---|---|---|---|
| 25% (gated) | 0.165 s / 0.192 s | 0.313 s / 0.338 s | 1.89 | 1.76 |
| 0% | 0.172 s / 0.189 s | 0.272 s / 0.304 s | 1.59 | 1.61 |
| 50% | 0.149 s / 0.183 s | 0.326 s / 0.331 s | 2.19 | 1.82 |

The 25% ratio is under 2.5x on the first measurement, so no extra runs or larger store were needed.

**AC5.** `python -m pytest tests/test_export.py tests/test_attribute.py tests/test_invoice.py -q` gave 25 passed.

### Notes for the evaluator
- **Behaviour change beyond the split:** the old code assigned `cost[key] = ...` and `toks[key] = ...`, so distinct raw models that `normalize_model` collapses, or a NULL and an empty-string user_email, overwrote each other. The new code accumulates with `+=`. Stores without such collisions give byte-identical attributed rows. Stores with collisions now conserve totals instead of dropping some. Confirm you accept this.
- SQL groups by `src` and `sid`, so unknown rows are grouped per session. Python then merges sessions that share a label.
- `git status` shows only export.py as my change. `client-package.zip` and the `_goals` and `project_label.py` entries were already dirty.

### Footprint
files_read: 8 (~75000 chars)
commands_run: 7
