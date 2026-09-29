# Goal: lake-work-email-filter

## Problem Statement

`billing/otel/export.py` builds the two running lake CSVs (`claudeusagesummary`,
`claudeusagelineitems`) from EVERY datapoint in the OTEL store, including usage tagged
with personal emails (e.g. `veltariumsoftware@gmail.com`). Personal-account usage has no
matching Analytics API actuals and is not useful downstream, yet it is drained to ADLS.
Only work-domain (`@cyclotron.com`) usage should reach the lake.

## Discovery Summary (Phase 1 Q&A)

- **Filter point:** export build (`export.build()`), NOT ingest. The raw OTEL store keeps
  everything, so the filter is reversible and local bill/reconcile views are unchanged.
- **Unknown user:** rows with no email (`user_email` NULL/empty -> `unknown`) are KEPT.
- **Config:** env var `ALLOWED_EMAIL_DOMAINS` (comma-separated), default `cyclotron.com`.
  Match is case-insensitive, exact domain after the last `@` (so `x@cyclotron.com.au`,
  `x@evil.cyclotron.com`, `cyclotron.com@gmail.com` are excluded). Whitespace tolerated.
- **Layer:** Export & lake sync only. The Cowork path is not exported by `export.py`, so it is out of scope.
- **Docs:** README updated (user request: "update the read me after"), as a normal task in
  this goal. Phase 6 skill run: no. **PR: no.**

## Success Criteria

- [ ] Both CSVs written by `export.build_and_enqueue` / `export.main` contain no row whose
      `user_email` is a real address outside the allowed domain(s).
- [ ] Rows with `unknown` user and rows for allowed-domain users are unchanged.
- [ ] `ALLOWED_EMAIL_DOMAINS` overrides the default; documented in `.env.example`.
- [ ] Raw store usage tables (`token_usage`, `cost_usage`, `session_repo_timeline`) unchanged by export.
- [ ] every export path (scheduler via `build_and_enqueue`; `python -m billing.otel.export` with or without `--no-enqueue`) reports how many groups the filter excluded; `python -m billing.otel.export` honors `.env`.
- [ ] Tests cover the above; full suite passes.
- [ ] README describes the filter and matches the code.

## Constraints

- Stdlib only. No secrets. Nothing persisted; env read at call time (not import time).
- Repo attribution stays resolved at query time; the filter must not touch attribution.

```yaml
phases:
  align_docs: false
  pull_request: false
  ladder: escalate
```

## Out of Scope

- Ingest-time dropping; Cowork export; reconcile/bill/invoice filtering; PR; Phase 6 skill.

## Tasks (dependency order)

| # | Task file | Layer | Depends on |
|---|-----------|-------|------------|
| 01 | `01-export-domain-filter.md` | Export & lake sync | — |
| 02 | `02-tests.md` | tests | 01 |
| 03 | `03-readme.md` | docs | 01 |
