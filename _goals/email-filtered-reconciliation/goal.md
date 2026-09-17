# Goal: email-filtered-reconciliation

## Problem Statement

`billing/reconcile.py` compares org-wide Analytics API totals against OTEL-captured
totals to compute the coverage/attribution funnel (truth → captured → tagged). With
only a small number of developers currently emitting telemetry, org-wide totals are too
noisy to represent "how well is the OTEL pipeline capturing/attributing usage for the
devs actually piloting it" — the signal is diluted by other org activity outside the
pilot. Reconciliation needs an optional per-user-email scope so the funnel can be
computed for just the piloting developers, while remaining fully backward compatible
when no filter is given.

## Discovery Summary (Phase 1 Q&A)

- **Layer/lane affected**: Rating & billing (`billing/reconcile.py`), reusing the
  existing per-user ingest path (`billing/ingest.py` → `billing/store.py`'s
  `user_cc_usage` table) and the existing `user_email` column already present in
  `billing/otel/otel_store.py`'s `token_usage` table.
- **External surfaces touched**: none — CLI-only change (`python -m billing.reconcile`).
  No new network calls, no new auth surface.
- **Auth/permissions**: unchanged. No new token/secret introduced.
- **Interface shape**: `--email` is a repeatable CLI flag (`--email a@x.com --email
  b@x.com`), collected via `argparse action="append"`. The existing `--db` flag keeps
  meaning the OTEL database path unchanged; a new, separate `--analytics-db` flag
  (optional, defaults to `billing.store.Store`'s own default path) addresses the
  analytics side — the two are never overloaded onto one parameter.
- **Error/empty-data behavior**:
  - If `--email` is given and the **analytics side** (`user_cc_usage`) has zero
    matching rows for the requested date range, print a clear message telling the
    user to run `python -m billing.ingest --start ... --end ...` first, and do **not**
    print a funnel (a 0/n/a funnel here would misleadingly look like a real coverage
    number rather than "data was never pulled").
  - If `--email` is given and the **OTEL side** (`token_usage`) has zero matching
    rows for those emails/range, that IS a valid data point (the dev hasn't used
    Claude Code in that window yet) — print the funnel normally with `captured=0`.
  - With no `--email` passed, behavior is byte-for-byte unchanged from today (existing
    org-wide funnel via `analytics_claude_code_totals` / `otel_totals`).
- **Existing patterns to follow**: match `reconcile.py`'s existing style (plain
  functions returning dicts keyed by the `CANON` token buckets, `ftok`/`pct` helpers,
  `argparse` CLI in `main()`); reuse `billing.store.Store` for `analytics.db` access
  (don't hand-roll a second sqlite connection helper) and `OtelStore` for `otel.db`,
  exactly as `reconcile.py` already does.
- **Priority / future consumer**: a future dashboard task (out of scope here) will call
  these same filtering functions directly to render both company-wide token usage and
  reconciliation efficiency, so the filtering logic must live in reusable, importable
  functions — not inlined into `argparse`/`main()` handling.
- **Phase 6 (docs)**: yes — update `README.md`'s `reconcile.py` section with a
  `--email` usage example.
- **Phase 7 (PR)**: yes — draft a PR for review at the end.

## Success Criteria

- [ ] `python -m billing.reconcile --start S --end E` (no `--email`) produces output
      identical to today's org-wide funnel.
- [ ] `python -m billing.reconcile --start S --end E --email a@x.com --email b@x.com`
      computes the truth side from `user_cc_usage` filtered to those emails, and the
      captured/tagged side from `token_usage` filtered to those emails.
- [ ] If the analytics side has no rows for the given emails/range, a clear
      "run `billing.ingest` first" message is printed and no funnel table is printed.
- [ ] If the OTEL side has no rows for the given emails/range (analytics side non-empty),
      the funnel prints normally with captured/tagged = 0.
- [ ] The filtering functions are unit-testable in isolation (not only via CLI/`main()`).
- [ ] `README.md`'s reconcile section documents the new `--email` flag with an example.
- [ ] No new runtime imports outside the standard library.
- [ ] Email matching between the Analytics-side (`user_cc_usage.email`) and OTEL-side
      (`token_usage.user_email`) is case- and whitespace-insensitive, and any supplied
      `--email` value that matched zero analytics rows is named explicitly in the
      output — a spelling/casing mismatch between the two producers must be visible,
      never silently indistinguishable from a legitimate "dev hasn't used Claude Code
      yet" zero.
- [ ] The OTEL database path (`db`) and the analytics database path (`analytics_db`)
      are separate, independently addressable parameters/flags — never overloaded
      onto one.

## Constraints

- Must reuse `billing.store.Store` and `billing.otel.otel_store.OtelStore` for DB
  access — no new ad-hoc `sqlite3.connect` calls.
- Must NOT change the org-wide (no-`--email`) output or its function signatures in a
  way that breaks the existing `analytics_claude_code_totals(start, end)` /
  `otel_totals(store, start, end)` call sites used when no filter is applied.
- Must NOT touch `billing/ingest.py`, `billing/otel/receiver.py`, or any other module
  outside `billing/reconcile.py`, `billing/store.py` (read-only query addition only if
  needed), `README.md`, and `tests/`.
- Stdlib-only — no third-party imports anywhere in `billing/`.
- Repo attribution stays resolved at query time (unchanged) — this feature only adds a
  `WHERE ... IN (...)` scope, it does not persist any attribution decision.

```yaml
phases:
  align_docs: true
  pull_request: true
  ladder: escalate
```

## Out of Scope

- The dashboard that will visualize company-wide usage + reconciliation efficiency
  (future goal; this goal only needs to leave clean, reusable functions for it to call).
- Any change to `billing/ingest.py`'s pull behavior, `billing/otel/receiver.py`, or the
  Analytics API client's request shape.
- Any UI/web surface.
- Filtering by any dimension other than `user_email` (e.g. by repo) — already possible
  today via existing repo grouping and not part of this goal.

## Tasks (dependency order)

| # | Task file | Layer | Depends on |
|---|-----------|-------|------------|
| 01 | `01-reconcile-email-filter.md` | Rating & billing | — |
| 02 | `02-tests.md` | tests | 01 |
