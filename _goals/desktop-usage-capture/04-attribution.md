# Task 04: Attribution — the desktop-scratch bucket

## Objective

`billing/otel/attribute.py` reports a fifth `attribution_source` value, `desktop-scratch`, for
transcript-sourced rows that resolve to no billable repo — distinguishing "desktop session in a scratch
workspace" from `no_remote` and `absent`. Resolution stays derived at query time, and the change must be
safe on **both** tables `resolved_view` is applied to.

## Dependencies

- 00 (fixtures), 01 (the `usage_source` column, on `token_usage` AND `cost_usage`)

```yaml
# --- task ownership contract ---
writes:
  - billing/otel/attribute.py
  - tests/test_attribute.py
reads:
  - billing/otel/otel_store.py
  - billing/otel/bill.py
  - billing/otel/export.py
  - tests/conftest.py
depends_on:
  - "00-test-scaffold"
  - "01-store-schema"
owner: implementer
rewrite_semantics: targeted-insertion
eval_depth: full
```

## Requirements (exhaustive — the evaluator verifies every item)

- [ ] `attribution_source()` gains a `desktop-scratch` branch for rows where `usage_source='transcript'`
      and the resolved repo is not a billable repo.
- [ ] **The branch must be safe on `cost_usage` as well as `token_usage`.** `resolved_view` is applied to
      `cost_usage` at `bill.py:57` and `export.py:78`. Task 01 puts `usage_source` on both tables, so the
      branch prepares on both — verify this rather than assuming it. A missing column here is not a
      degraded feature, it is `OperationalError` at query-prepare time taking down `bill.py` and the lake
      export for the existing OTLP-only fleet.
- [ ] The new branch is ordered correctly within the existing `CASE`. Today the first branch returns
      `'timeline'` whenever the session has ANY timeline row, and `claude-repo-tag.py` already runs on
      desktop — so a scratch session WILL have a timeline row carrying `repo='unknown'`. A naive append
      never fires. The `desktop-scratch` test must be evaluated before the timeline branch can claim the
      row, while leaving every OTLP row's classification bit-for-bit unchanged.
- [ ] A desktop session that DOES resolve to a real repo still reports `timeline`.
- [ ] `resolved_repo()` behavior is unchanged; `desktop-scratch` rows still resolve to the `unknown` key
      so existing grouping and the `UNATTRIBUTED` display keep working.
- [ ] Every existing classification (`timeline`, `wrapper`, `no_remote`, `absent`) is unchanged for every
      OTLP row. Regression-critical: attribution decides who gets billed.
- [ ] Resolution stays at query time. No column written, no table materialized, no ingest-time resolution.
- [ ] `resolved_view()` keeps `SELECT {alias}.*` so new store columns flow through to consumers.
- [ ] The module docstring's fallback-chain documentation covers the new value alongside the existing four.
- [ ] No third-party import is added.

## Acceptance Criteria

1. A transcript row for a desktop session with no billable repo classifies as `desktop-scratch` even
   though the session has a timeline row with `repo='unknown'` — verification: unit test seeding both a
   token row and a matching timeline row.
2. A transcript row for a desktop session resolving to a real repo classifies as `timeline` —
   verification: unit test.
3. An OTLP row with a timeline entry still classifies `timeline`; `repo_raw=''` still `absent`;
   `repo='unknown'` with non-empty `repo_raw` still `no_remote` — verification: unit test per case.
4. `resolved_repo()` returns identical values for every OTLP row before and after this change —
   verification: unit test over the seeded fixture set.
5. **`resolved_view('cost_usage')` compiles and returns the same rows as before this change** —
   verification: unit test executing the query against a seeded store. This is the regression test for
   the prepare-time failure; a `token_usage`-only criterion would let the defect ship.
6. **`bill.py` and `export.py` both still run against an OTLP-only store after this change** —
   verification: execute both and assert exit 0. Cross-module smoke check, because this task can break
   files it does not own.
7. `resolved_view('token_usage')` still yields `resolved_repo` and `attribution_source` and includes the
   new store columns — verification: unit test inspecting returned column names.

## Files to Read

- `billing/otel/attribute.py` — `_AS_OF`, `_FIRST`, `resolved_repo`, `attribution_source`, `resolved_view`,
  and the docstring's fallback chain.
- `billing/otel/otel_store.py` — the `usage_source` / `entrypoint` columns from task 01 and the
  `session_repo_timeline` schema.
- `billing/otel/bill.py` line 57 and `billing/otel/export.py` line 78 — the `resolved_view('cost_usage')`
  call sites this change must not break.
- `tests/conftest.py` — fixtures from task 00.
- `README.md` — the `attribute.py` bullet; the resolve-at-query-time invariant.
- `.claude/skills/test-ladder/SKILL.md`

## Files to Create / Change

- `billing/otel/attribute.py` — the `desktop-scratch` branch in the correct `CASE` position; updated docstring.
- `tests/test_attribute.py` — the seven acceptance criteria above.

## Constraints

- Must: keep attribution derived at query time — a late or corrected timeline must still retroactively fix
  past bills with no re-ingest. Non-negotiable, and stated in `README.md`.
- Must: leave `resolved_repo()` semantics and every existing `attribution_source` value unchanged for OTLP rows.
- Must: express the change in SQL within the existing helper structure — not in Python post-processing.
- Must: verify against BOTH tables, not just `token_usage`.
- Must NOT: add a third-party import; persist any resolution; alter `dp_key`; modify the store schema,
  `bill.py`, or `export.py` — other tasks own those, and `export.py` is owned by no task in this goal.

## Verification

- Targeted test command: `python -m pytest tests/test_attribute.py -v`
- Rung 2 impacted set per the convention map: `tests/test_bill.py`, plus `tests/test_export.py` once
  task 07 creates it.
