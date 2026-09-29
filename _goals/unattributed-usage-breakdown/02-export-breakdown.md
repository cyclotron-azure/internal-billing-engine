# Task 02: Split unknown rows in the lake exports

## Objective

`billing/otel/export.py` emits two new trailing columns, `attribution_source` and
`unattributed_project`, in both `claudeusagesummary.csv` and `claudeusagelineitems.csv`.
Rows billed to a real repo are byte-for-byte what they were before, apart from two empty
trailing cells. Rows whose resolved repo is `unknown` are split by attribution class and
session project label, with totals conserved.

## Dependencies

- 01-project-label (frozen `billing/otel/project_label.py` interface)

```yaml
# --- task ownership contract ---
writes:
  - billing/otel/export.py
reads:
  - billing/otel/project_label.py    # load_session_labels(); not edited
  - billing/otel/attribute.py        # resolved_view(); not edited
  - billing/otel/normalize.py        # normalize_model, repo_name; not edited
depends_on:
  - "01-project-label"
owner: implementer
rewrite_semantics: whole-file
eval_depth: full
# full: the CSV schema is consumed by the Fabric notebook and a Power BI report.
```

## Requirements (exhaustive — the evaluator verifies every item)

**Schema**
- [ ] `SUMMARY_FIELDS` and `LINE_FIELDS` each gain `"attribution_source"` then
      `"unattributed_project"`, appended AFTER `"generated_at"`. No existing field is
      renamed, removed, or moved.

**Attributed rows (resolved repo != `unknown`)**
- [ ] Keys, row count, and every pre-existing column value except `generated_at` are
      identical to the current implementation for the same store, except on
      collision inputs (below). `attribution_source` and `unattributed_project` are `""`.
- [ ] Collision correction (user decision): cost and tokens are SUMMED per export key,
      so raw models that `normalize_model` collapses and NULL / `""` / `"unknown"`
      user emails no longer overwrite each other. On such inputs attributed rows differ
      from the pre-change export, and totals equal the database.

**Unknown rows (resolved repo == `unknown`)**
- [ ] Line-item key becomes (day, `unknown`, model, user_email, attribution_source,
      unattributed_project); summary key becomes (day, bill name, user_email,
      attribution_source, unattributed_project).
- [ ] `attribution_source` comes from `attribute.resolved_view()`'s
      `attribution_source` column (not re-derived).
- [ ] `unattributed_project` = `load_session_labels(store.db).get(session_id, "")`, so
      sessions without timeline rows get `""`.
- [ ] Tokens and cost across the split rows sum to the database total for the same
      (day, model, user) (which equals the single pre-change unknown row whenever the
      store has no collisions); `first_usage_at_utc` /
      `last_usage_at_utc` are the min/max of the datapoints rolled into each split row.
- [ ] The "is unknown" test uses the resolved repo key (`resolved_repo == "unknown"`),
      not the bill name, so a `repo_name_map` override cannot move rows in or out of
      the split.

**Performance / store rules**
- [ ] `load_session_labels` is called once per `build()`.
- [ ] Each of `cost_usage` and `token_usage` is scanned through `resolved_view()` at most
      once per `build()`, with the final rollup done in Python.
- [ ] `attribution_source` is evaluated only for unknown rows, e.g. by grouping on
      `CASE WHEN resolved_repo = 'unknown' THEN attribution_source END` and
      `CASE WHEN resolved_repo = 'unknown' THEN session_id END`. A restructure that
      computes `resolved_repo` once per row (e.g. an `AS MATERIALIZED` CTE over
      `resolved_view()`) is allowed, provided the class values still come from
      `attribute.py`'s expressions.
- [ ] Timing: seed a temp store with at least 20,000 datapoints, 25% of them resolving
      to `unknown` (half of those in sessions with timeline rows, half without). The
      post-change `build()` takes no more than 3× the pre-change `build()` on that store
      (best of 3). Also report, ungated, the ratios at 0% and 50% unknown.
- [ ] No new table, column, index, write, or commit in `otel.db`; single connection.

**Diagnostic isolation**
- [ ] `unattributed_project` never passes through `name_of`, `repo_name`, or
      `repo_name_map`, and never appears in the `repo` or `repo_key` columns.
- [ ] `invoice.py`, `bill.py`, and `attribute.py` are untouched.
- [ ] The module docstring is updated to describe the two new columns in one or two
      sentences.

## Acceptance Criteria

1. Both CSV headers end with `attribution_source, unattributed_project` and all earlier
   headers are unchanged — verification: command output (`python -m billing.otel.export --db <temp db> --out-dir <tmp> --no-enqueue` then read the header lines).
2. For a store seeded with one attributed session and two unknown sessions (one with a
   `Dashnoard` timeline, one with no timeline), attributed rows match the pre-change
   export exactly (excluding `generated_at`) and unknown rows split into
   `timeline`/`local:Dashnoard` and `absent`-or-`no_remote`/`""` — verification:
   command output. Method: `git show HEAD:billing/otel/export.py` (HEAD equals the
   working tree for this file) written into the session scratchpad with its relative
   imports rewritten to `billing.otel.*`, run against the same seeded store, and diffed.
3. Token and cost totals per (day, model, user) equal the database totals, and equal
   the pre-change export on a collision-free store — verification: command output.
4. The 25%-unknown timing comparison from Requirements is within 3× — verification:
   command output (all three ratios reported).
5. Existing tests still pass: `python -m pytest tests/test_export.py tests/test_attribute.py tests/test_invoice.py -q`
   — verification: command output.

## Files to Read

- `CLAUDE.md` — hard constraints
- `README.md` §"Shipping invoices to a data lake (Fabric / ADLS Gen2)" (lines ~293–330)
  — exact column contract
- `fabric/README.md` — downstream consumers (notebook uses `overwriteSchema`)
- `billing/otel/export.py` — current implementation
- `billing/otel/attribute.py` — `resolved_view`, `attribution_source`
- `billing/otel/project_label.py` — interface from task 01
- `tests/test_export.py` — existing expectations that must keep passing
- `.claude/skills/test-ladder/SKILL.md`, `.claude/skills/python-performance-optimization/SKILL.md`

## Files to Create / Change

- `billing/otel/export.py` — schema, grouping, label lookup, docstring.

## Constraints

- Must: stdlib only; reuse `resolved_view()`; keep `build()` / `build_and_enqueue()` /
  `main()` signatures and return shapes unchanged.
- Must NOT: edit any other file; change `resolved_repo` semantics; add a correlated
  subquery for labels; persist anything; touch hooks, `client-package/`, `deploy/`, the
  Fabric notebook.
- Must NOT run any git command that changes the working tree or index (`stash`,
  `checkout`, `restore`, `reset`); the tree holds the user's uncommitted work. Use a
  scratch copy of the pre-change file instead.

## Verification

- `python -m pytest tests/test_export.py tests/test_attribute.py tests/test_invoice.py -q`
- Before/after export of a seeded temp store, diffed, captured in the report.
