You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-16T10:40-04:00

## Task

Execute task 02 of the `reconcile-coverage-diagnostics` goal: add the aggregation layer to
`billing/reconcile.py`.

**Your specification is `_goals/reconcile-coverage-diagnostics/02-reconcile-aggregation.md`.
Read it in full before writing anything and follow it exactly.** It has 16 acceptance
criteria and its requirements are exhaustive — the evaluator that reviews your work checks
every item. That file survived three goal-evaluation cycles; where it explains *why*
something must be done a certain way, that is a recorded decision, not a suggestion.

This task adds **no printing**. Task 03 renders what your functions return. If you find
yourself formatting a string for display, stop.

## Requirements

All requirements are in the task file, organized as: requirement 0 (the day-key contract),
1 (unmapped token types), 2 (surface breakdown), 3 (per-day aggregation), 4 (dedupe-drop
report), and 5 (shape and placement), then Constraints. Work from the file, not from this
summary. The shape of what you are building:

- `otel_totals` extended **additively** with a `"unmapped"` key — `"captured"` and
  `"tagged"` keep their exact current shape and meaning.
- New `otel_by_surface`, `otel_daily`, `analytics_claude_code_daily`,
  `analytics_user_daily`, `dedupe_drop_report`.
- `analytics_claude_code_totals` restructured into a thin wrapper over a **single**
  `usage_report` pass, keeping its signature; `run()` calls the daily function instead.

**Requirement 0 is the highest-risk item in the whole goal.** `usage_report` yields
`bucket.get("starting_at")` verbatim from the API — an RFC3339 timestamp, not a date. Every
day key in this feature must be exactly `YYYY-MM-DD`. If you skip the `[:10]` truncation,
`--daily` prints every day twice and the phantom rows look exactly like the
receiver-outage signal this feature exists to detect.

## Task 01 is complete — build against this verified interface

Task 01 shipped and passed evaluation 5/5, with all 15 criteria verified by direct
observation. These are the real signatures in `billing/otel/otel_store.py`, confirmed by
the evaluator against the code:

```python
DEDUPE_EPOCH_META_KEY = "dedupe_counting_since"   # module-level constant -- import it
# meta.value is a UTC ISO8601 timestamp, "%Y-%m-%dT%H:%M:%SZ"

OtelStore.dedupe_drops(start, end) -> dict          # {token_type: drops}
OtelStore.dedupe_drops_by_day(start, end) -> dict   # {YYYY-MM-DD: {token_type: drops}}
OtelStore.dedupe_epoch() -> str | None              # None == counting has never run
```

- Both read methods use a half-open `[start, end)` window, the same convention
  `otel_totals` already uses.
- A token type or day with no drops is **absent** from the dict, never present with `0`.
- `dedupe_epoch()` is a plain read that deliberately ignores the insert path's private
  in-memory latch, so it always returns committed truth.
- Import `DEDUPE_EPOCH_META_KEY` rather than hardcoding the string, and call only these
  three methods — do not query the `dedupe_drops` table directly from `reconcile.py`.

## Files to Read

Exactly as listed in the task file's `## Files to Read` section:

- `_goals/reconcile-coverage-diagnostics/02-reconcile-aggregation.md` — your spec. Read
  first, read fully.
- `billing/reconcile.py` — the whole file. Note `CANON`, `otel_totals`,
  `analytics_claude_code_totals`, `analytics_user_totals`, `run`, `_print_funnel`, and the
  `_normalize_emails` helper you must reuse.
- `billing/otel/otel_store.py` — task 01's three read helpers and the epoch constant, plus
  the `token_usage` schema for exact column names and nullability.
- `billing/otel/attribute.py` — `resolved_view()`'s contract and the resolve-at-query-time
  invariant. **Non-negotiable**: never persist an attribution decision.
- `billing/store.py` — the `user_cc_usage` schema and the `_day()` truncation helper
  (requirement 0).
- `billing/analytics_client.py` — `usage_report`'s yield shape (it yields `starting_at`
  raw), `_to_dt`'s own `[:10]` truncation, `__init__`'s no-token raise, the 31-day
  windowing and pagination, and `AnalyticsError`.
- `README.md` — the "Typical OTEL flow" section. Ground truth. The rate card in
  `rating.py` is a placeholder, not real pricing — irrelevant here, do not "fix" it.
- `.claude/skills/test-ladder/SKILL.md` — rungs 1–2 only.
- `.claude/skills/python-performance-optimization/SKILL.md` — consult only if the per-day
  or per-surface aggregation tempts you toward a per-day query in a loop. Prefer one
  grouped query per shape over N queries.

## Write fence

```
billing/reconcile.py
```

That is the **only** path you may create or modify. Notably:

- Do **not** modify `billing/otel/otel_store.py` — task 01 owns it and it is complete and
  evaluated. If you need something from it that is not in the three frozen methods, **stop
  and report that** instead of adding it.
- Do **not** modify `billing/otel/receiver.py`, any test file (task 04's fence), or
  `README.md` (the goal's docs phase owns it).
- Scratch scripts go in your session scratchpad directory, never in the repo, never in
  `data/`.

## Model

requested: claude-sonnet-5 · tier: light · rotation: n/a (first attempt)

## Rules

- **Stdlib only.** No third-party import may enter `billing/`.
- **No printing, no `sys.exit`, no `argparse` changes** in any function you add. Rendering
  is task 03's.
- `otel_totals`, `analytics_claude_code_totals` and `analytics_user_totals` keep their
  exact current signatures and return shapes. Extend additively only.
- `otel_totals` and `otel_daily` must read `resolved_repo` via `resolved_view("token_usage")`,
  never the raw `repo` column. `otel_by_surface` reads no repo column and **may** query
  `token_usage` directly — if you take that option, add the comment the task requires
  saying it must never grow a repo dimension without switching to `resolved_view`.
- `otel_daily`'s `"tagged"` must apply the identical predicate `otel_totals` uses. Factor it
  out rather than reimplementing it, so the two cannot diverge.
- Exactly **one** `usage_report` pass on the org-wide path, returning a fully materialized
  `dict` (never a generator), executed inside `run()`'s existing `try`/`except
  AnalyticsError` so that error path still works.
- Reuse `_normalize_emails`; email matching stays case/whitespace-insensitive via
  `LOWER(TRIM(...))`.
- All DB access through `OtelStore` / `Store`. No new `sqlite3.connect`.
- Climb test-ladder rungs 1–2 only. **Do NOT run `python -m pytest -q`** (rung 3). Your
  targeted command is `python -m pytest tests/test_otel_store.py -q`.
- If a requirement seems wrong or impossible, implement nothing on a guess: report the
  conflict and what you would need.

## Output

```
MODEL: <the model you are actually running as>
STATUS: completed | blocked

## What changed
[Each edit to billing/reconcile.py, by symbol name: what and why.]

## Pre-change baseline (required by criterion 1)
[Criterion 1 compares otel_totals' "captured"/"tagged" against a baseline captured BEFORE
your changes. Paste that baseline and the fixture you ran it on. A comparison of
post-change code against itself proves nothing, which is why this is required.]

## Acceptance criteria
[One line per criterion 1-16: how your implementation satisfies it, or NOT YET if it
depends on task 04's tests.]

## Return shapes as implemented
[The exact return shape of every function you added or extended, so task 03 renders
reality. Include the day-key format you produce.]

## Verification
- `python -m pytest tests/test_otel_store.py -q` -> [exact result line]
- Scratchpad evidence (required, paste verbatim): a script building a tmp OTEL store with
  a mixed otlp+transcript fixture that includes an unmapped token type, a NULL
  token_type, a NULL query_source, a NULL entrypoint, and three distinct days -- printing
  the full return value of otel_totals, otel_by_surface, otel_daily and
  dedupe_drop_report, PLUS an explicit check that sum-over-days == period total for every
  CANON bucket on both the captured and tagged sides.
- Day-key evidence: show that a fake usage_report yielding "2026-07-14T00:00:00Z" produces
  the key "2026-07-14", and that it compares equal to otel_daily's key for that day.

## Deviations / concerns
[Anything you could not do as specified, or where the task file is ambiguous. Say so
plainly rather than guessing. "None" is a valid answer.]

### Footprint
files_read: <N> (~<C> chars)     # C as digits only, no thousands separators
```
