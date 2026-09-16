# Goal: reconcile-coverage-diagnostics

## Problem Statement

`billing/reconcile.py` is the acceptance test for the OTEL rollout and invoices are
built on its number, but today it reports a single opaque percentage. A real 3-day,
two-user run produced `input 39.87% / output 96.37% / cacheRead 89.32% /
cacheCreation 60.67%` (88.20% overall) and there is no way to tell whether that spread
is telemetry that never arrived, a surface with no exporter, a token-type mapping
break, or a `dp_key` dedupe collision. Three of those four causes are currently
*silent*: `reconcile.py:91` discards unrecognized `token_type` values with a bare
`continue`, dedupe drops are tallied in `receiver.py` and then thrown away, and a
period aggregate hides a single-day receiver outage completely. This goal makes the
funnel say *where* the gap is, so the remaining roadmap phases are measurable rather
than guesswork.

## Discovery Summary (Phase 1 Q&A)

- **Layer/lane affected**: Store & schema (`billing/otel/otel_store.py` — dedupe-drop
  counter + measurement epoch) and Rating & billing (`billing/reconcile.py` — all
  aggregation and output). No ingest, attribution, export, or client-rollout changes.
- **Truth side has no surface dimension** (raised by the orchestrator in Phase 1, and
  the decision that shapes requirement 1): `analytics_claude_code_totals` pulls
  product-level rows via `usage_report(..., products=["claude_code"])` and
  `analytics_user_totals` reads `user_cc_usage` — *neither carries `usage_source`,
  `entrypoint`, or `query_source`*. A per-surface coverage percentage therefore has no
  real denominator. **Decision: break the CAPTURED side down by surface and label it
  "share of captured — NOT coverage", with the gap attributed only at the period level
  where the denominator is real.** A modeled per-surface denominator derived from
  enrollment was offered and explicitly rejected as a number that could be wrong while
  looking authoritative on an invoice.
- **Dedupe drops**: new additive `dedupe_drops` counter table keyed on
  `(day, token_type, usage_source)`. Rejected alternatives: a quarantine table storing
  full dropped rows (grows with traffic, adds a write to the receiver's hot path) and
  parsing `receiver.log` (not queryable by date window, lost on rotation).
- **Counter epoch** (raised by the orchestrator: an empty counter reads `0 drops`,
  which means "not measured", not "no collisions"): record a counting-start **UTC
  ISO8601 timestamp** in `meta` the first time the counting code path actually runs, and
  render an unmeasured or partially-measured window as such instead of as a misleading
  `0`. **Revised after Phase 3 cycle 1**: the epoch must be written by the *insert*
  path, not by `_migrate()`. `_migrate()` runs on every `OtelStore` construction and ten
  call sites open the store (`reconcile.py`, `bill.py`, `export.py`, `invoice.py`,
  `fabric_sync.py`, `records.py`, `repos.py` ×2, `scheduler.py`, `receiver.py`), so a
  read-only consumer running the new code before the receiver restarts would stamp an
  epoch for a period in which nothing was ever counted — reintroducing the exact
  misleading `0` by another route. Writing it from the insert path makes the epoch mean
  "the counting code has run at least once", which is the only claim the number can
  honestly support.
- **Why count collisions rather than eliminate them** (the strongest alternative,
  recorded so it is not relitigated): `transcript_key`'s docstring
  (`billing/otel/otel_store.py`) is the precedent for fixing a collision class
  *structurally* instead of measuring it. That is not available for OTLP `dp_key`
  without persisting `request_id`, which is roadmap Phase 1 and explicitly out of scope
  here. Counting is therefore the honest interim: it tells us whether the collision
  class is worth eliminating before we pay for the column.
- **Per-day rows**: both modes, with real denominators — org-wide from
  `usage_report()`'s existing `(day, row)` yield, `--email` from `user_cc_usage.day`.
- **Raw integers**: separate aligned exact-integer column beside the `ftok()` column,
  so the arithmetic is auditable by eye without losing scannability.
- **Verbosity**: default output keeps today's shape (per-token-type table + funnel +
  billable coverage); detail behind `--by-surface`, `--daily`, `--detail`. Sections
  that indicate a *defect* — unmapped token types, dedupe drops — print regardless of
  flags, because a silent failure is precisely what this goal exists to kill.
- **Interface shape**: new/extended aggregation functions stay importable and
  independently unit-testable, never inlined into `argparse`/`main()` — carried
  forward from the `email-filtered-reconciliation` goal's note that a future dashboard
  will call them directly.
- **Existing patterns to follow**: `reconcile.py`'s plain functions returning dicts
  keyed by the `CANON` buckets, the `ftok`/`pct` helpers, `argparse` in `main()`;
  `OtelStore`/`Store` for all DB access — never a hand-rolled `sqlite3.connect`.
- **Pre-existing test gap** (found in Phase 2, corrected in Phase 3 cycle 1):
  `tests/test_reconcile.py` does not exist. The `email-filtered-reconciliation` goal
  planned it but stalled at a Phase 3 escalation on 2026-09-14, while its code landed
  anyway (commits `947a686` and `f5b76cc` — *not* `5dd7d94`, which is a `bill.py`-only
  change). The `--email` path therefore has zero coverage today and this goal's changes
  touch it, so regression tests for the *existing* filtered and unfiltered `run()`
  paths are in scope as the regression surface of this change. Verified in cycle 1 that
  the shipped code is sound — that goal's escalation findings were defects in its *task
  text*, not in the code — so these regression tests pin correct behavior rather than
  enshrine a bug.
- **`_goals/email-filtered-reconciliation/02-tests.md` is superseded by this goal's task
  04.** It declares `writes: tests/test_reconcile.py` and that goal is stalled, not
  closed. If it is ever resumed, its whole-file rewrite would delete this goal's tests.
  Task 04 here owns that file.
- **`tests/COVERAGE_MAP.md` is task-04-owned and excluded from Phase 6.** It falls
  inside `align-docs`' markdown surface, so Phase 6 must not edit what task 04 writes
  there.
- **Accepted cost**: `otel_by_surface` and `otel_daily` add aggregation passes over
  `token_usage`, and `otel_daily` reads through `resolved_view`'s correlated subqueries.
  On a large store `reconcile.py`'s runtime grows materially. Accepted: reconcile is an
  operator-invoked diagnostic run at most daily, never in the receiver's request path.
- **Phase 6 (docs)**: yes — `README.md` is ground truth and documents reconcile's
  output and flags.
- **Phase 7 (PR)**: yes — draft shown to the user before anything is pushed.
- **QA evaluation**: yes — the terminal output *is* the deliverable here, not just the
  code, so real captured output goes to `qa-evaluator` after the audit.

## Success Criteria

- [ ] `python -m billing.reconcile --start S --end E` with no new flags still prints
      the `BY TOKEN TYPE` table, `COVERAGE FUNNEL`, and `BILLABLE COVERAGE` sections,
      with the same funnel arithmetic as today.
- [ ] Every token-count table shows an exact-integer column alongside the `ftok()`
      column, and the integers reconcile with the printed percentages.
- [ ] A `token_type` present in `token_usage` but absent from `CANON` is reported in an
      `UNMAPPED TOKEN TYPES` section with its token total, and is never silently
      dropped. The section prints whether or not any detail flag was passed.
- [ ] `--daily` prints one row per UTC day in `[start, end)` with a real coverage
      percentage per day, in **both** org-wide and `--email` modes.
- [ ] `--by-surface` breaks the captured side down by `usage_source`, `entrypoint`, and
      `query_source`, labeled as a share of captured and never as coverage.
- [ ] Each `--by-surface` sub-block prints its own `TOTAL` row whose share reads
      `100.00%`, so a dimension that silently stops summing to the captured total is
      visible in the output itself and not only in a fixture test.
- [ ] Every day key produced or rendered anywhere in this feature is exactly
      `YYYY-MM-DD`, including the org-wide truth side, whose `usage_report` yields a
      raw RFC3339 `starting_at` that must be truncated.
- [ ] Per-day figures reconcile with the period figures: for every `CANON` bucket, the
      sum over days equals the period total, on both the truth and the captured side.
- [ ] `--detail` implies both `--by-surface` and `--daily`.
- [ ] A `dp_key` collision in `OtelStore.insert_datapoint` / `insert_cost_datapoint`
      increments a persisted per-`(day, token_type, usage_source)` counter, and
      reconcile reports the counts for the reconciled window.
- [ ] The counting-start epoch is written by the **insert** path, so a store opened only
      by a read-only consumer (`reconcile`, `bill`, `export`, …) never acquires one.
- [ ] Reconcile distinguishes exactly these four dedupe states, each with distinct
      wording, and never prints a bare `0` for any but the last: (1) counting never ran
      against this database; (2) counting began **after** this window; (3) counting began
      **during** this window, so counts are a lower bound; (4) the window is fully
      counted — rendered as "no duplicate datapoints in this window" when the count is
      zero, and as per-type counts when it is not.
- [ ] A non-empty drop count is **never suppressed** by the measurement state. Drops can
      legitimately exist in a window that precedes the epoch (a replayed export records
      drops dated to the day they describe), and an interrupted first epoch write can
      leave the epoch absent while later drops commit. In every such case reconcile
      prints the count *and* the measurement qualifier, never the qualifier alone.
- [ ] Opening a pre-existing `otel.db` migrates it without dropping, renaming, or
      retyping any column, and is a no-op on second open.
- [ ] `--email` mode and org-wide mode both still work, including the existing
      "no analytics rows matched" message and the unreachable-Analytics-API error path.
- [ ] `python -m pytest -q` passes, and the new behavior has tests.
- [ ] No new runtime import outside the standard library anywhere in `billing/`.

## Constraints

- Stdlib-only in `billing/` — `pytest` under `tests/` is the one permitted dev
  dependency.
- SQLite is single-host, single-connection: one receiver process, one host. Do NOT
  thread the receiver, add a connection pool, enable WAL, or pass
  `check_same_thread=False`.
- The dedupe counter's increment runs inside the receiver's **serial** request path, so
  it must touch the database only on the collision path and must never raise into the
  caller. Note the collision path is *bursty*, not rare — a retried OTLP export re-sends
  the whole batch, so every datapoint in it collides at once. What bounds the cost is
  that both statements are primary-key-targeted against a table holding at most a few
  rows per day, not the rarity of the path.
- Repo attribution stays resolved at **query** time: `otel_totals` and `otel_daily` must
  read `resolved_repo` via `resolved_view()`, never the raw `repo` column, so a late or
  corrected `session_repo_timeline` still retroactively fixes past bills.
  `otel_by_surface` reads no repo column and may query `token_usage` directly (see task
  02 requirement 2), provided it carries a comment that it must never grow a repo
  dimension without switching to `resolved_view`. Verified in Phase 3 cycle 2 that
  `resolved_view` is a strict 1:1 projection, so the two row universes are identical and
  the `captured_total` equality in criterion 02.4 holds either way — that criterion
  remains the guard if `resolved_view` ever stops being a projection.
- `otel_totals`' return value must be extended **additively** — the existing
  `"captured"` and `"tagged"` keys keep their exact current shape and meaning.
- `analytics_claude_code_totals(start, end)` and
  `analytics_user_totals(emails, start, end, analytics_db)` must keep their current
  signatures and return shapes working.
- Must NOT modify `billing/otel/receiver.py` — both ingest paths already funnel through
  `store.insert_datapoint` (`receiver.py:167` OTLP, `receiver.py:358` transcript), so
  the counter increments at the single `cur.rowcount > 0` choke point in
  `otel_store.py` and the receiver needs no changes.
- Must NOT commit a secret.
- Aggregation logic stays in importable module-level functions, not inlined in `main()`.

```yaml
phases:
  align_docs: true
  pull_request: true
  ladder: escalate
```

## Out of Scope

- `--json` / machine-readable output, threshold-based non-zero exit, and coverage SLOs
  (roadmap Phase 4 — deliberately deferred so the format is designed against a real
  consumer).
- Persisting `request_id` on `token_usage` and any request-grain reconciliation
  (roadmap Phase 1).
- Any modeled or estimated per-surface truth denominator.
- Changing `OTEL_METRIC_EXPORT_INTERVAL`, the network posture, or anything under
  `deploy/` or `client-package/`.
- Changes to `billing/otel/receiver.py`, `billing/ingest.py`, `billing/otel/bill.py`,
  `invoice.py`, `export.py`, or the Analytics API client's request shape.
- Backfilling historical dedupe-drop counts (structurally impossible — the drops were
  never recorded; the epoch exists precisely to say so).
- Fixing the coverage gap itself. This goal only measures it.

## Tasks (dependency order)

| # | Task file | Layer | Depends on |
|---|-----------|-------|------------|
| 01 | `01-store-dedupe-counter.md` | Store & schema | — |
| 02 | `02-reconcile-aggregation.md` | Rating & billing | 01 |
| 03 | `03-reconcile-output.md` | Rating & billing | 02 |
| 04 | `04-tests.md` | tests | 01, 02, 03 |

**Contract first.** Task 01 is the contract task: it freezes the `dedupe_drops` schema,
the counting-start epoch `meta` key, and the **three** read helpers task 02 consumes
(`dedupe_drops`, `dedupe_drops_by_day`, `dedupe_epoch`). Task 02 builds against that
frozen interface, and task 03 renders what task 02 returns.
