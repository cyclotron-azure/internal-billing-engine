# Task 01: export-domain-filter

## Objective

`billing/otel/export.py` drops datapoints whose `user_email` is a real address outside the
allowed domain set before aggregation, so neither lake CSV contains them. `.env.example`
documents `ALLOWED_EMAIL_DOMAINS`.

## Dependencies

- none

```yaml
writes:
  - billing/otel/export.py
  - .env.example
reads:
  - billing/config.py
  - tests/test_export_unattributed.py
depends_on: []
owner: implementer
rewrite_semantics: targeted-insertion   # export.py; .env.example = append-only
eval_depth: full
# full: export.build() is consumed by the scheduler, main(), and existing tests.
```

## Requirements (exhaustive)

- [ ] Add `DEFAULT_ALLOWED_DOMAINS = ("cyclotron.com",)` and a helper
      `allowed_domains() -> tuple[str, ...]` reading `os.environ.get("ALLOWED_EMAIL_DOMAINS")`
      at CALL time; comma-split, strip, lower-case, drop empties and leading `@`; unset or
      effectively empty -> default.
- [ ] Add `is_allowed_user(email, domains) -> bool`: NULL/empty/whitespace-only or the literal
      `unknown` (case-insensitive) -> True (kept). Otherwise lower/strip the email; it must
      contain `@`; domain = text after the LAST `@`; True iff the domain exactly equals an
      allowed domain. An email with no `@` (other than unknown) -> False.
- [ ] `build(store, markup, allowed_domains=None)`: `None` -> `allowed_domains()`. In `_scan`,
      skip rows failing `is_allowed_user` BEFORE keying (SQL grouping unchanged; Python filtering
      per grouped row is acceptable). Must not alter attribution, keys, or rounding for kept rows.
- [ ] Kept rows keep their CURRENT key exactly: the raw `user_email` (NULL/"" -> `unknown`), with NO
      new case/whitespace coalescing. The filter only decides whether a row is kept.
- [ ] Add optional `stats: dict | None = None` to `build`; when given, set `stats["excluded_groups"]`
      = number of DISTINCT excluded (day, resolved_repo, model, user_email) groups, counted once even if the
      group appears in both `cost_usage` and `token_usage` and
      `stats["excluded_domains"]` (sorted set of dropped domains — domains only, never full emails).
      `build`'s return value stays `(summary_rows, line_rows)`.
- [ ] `main()` calls `billing.config.load_env()` at the start of `main()` (NOT at import time) so a
      `.env` `ALLOWED_EMAIL_DOMAINS` is honored, and, in its `--no-enqueue` branch (which calls `build()` directly), passes a `stats` dict to `build()` and prints the same
      `[export] excluded N group(s) outside <domains>` line, so the line appears on every export path.
- [ ] `build_and_enqueue` itself prints one line `[export] excluded N group(s) outside <domains>` (domains
      only, never emails) using an internal `stats` dict, on EVERY run (also when N = 0), so the scheduler
      path (`scheduler.run_once` -> `build_and_enqueue`, stdout) surfaces a mistyped domain setting.
      It still returns its existing `(ns, nl)` tuple unchanged. `scheduler.py` is NOT modified.
- [ ] `build_and_enqueue` and `main()` use the filter via `build` (default behavior); no new CLI
      flag required. Update the module docstring with one paragraph on the filter.
- [ ] `.env.example`: add a commented `# ALLOWED_EMAIL_DOMAINS=cyclotron.com` entry with a short
      explanation (commented, not blank).
- [ ] Stdlib only; no store writes.

## Acceptance Criteria

(Task-01-time verification: ad-hoc `python -c` / tmp-store check by the implementer; formal tests live in task 02.)
1. gmail address row absent from both CSVs; cyclotron row present — verification: ad-hoc tmp-store check
2. `unknown`/NULL user rows retained — verification: ad-hoc tmp-store check
3. `x@cyclotron.com.au`, `x@evil.cyclotron.com`, `cyclotron.com@gmail.com` excluded; `Y@CYCLOTRON.COM` kept — verification: ad-hoc check of `is_allowed_user`
4. `ALLOWED_EMAIL_DOMAINS="a.com, Cyclotron.com"` honored, read at call time — verification: ad-hoc check
5. `build(..., stats={})` fills `excluded_groups` (distinct-group semantics above) and `excluded_domains`; kept-row keys unchanged — verification: ad-hoc check
6. `build_and_enqueue` prints the `[export] excluded N group(s) ...` line (also for N = 0) and returns `(ns, nl)` — verification: ad-hoc check with captured stdout
7. `python -m billing.otel.export --db <tmp> --no-enqueue --out-dir <tmp>`, run with cwd = a temp dir containing a `.env` that sets `ALLOWED_EMAIL_DOMAINS`, honors it and prints the `[export] excluded N group(s)` line — verification: command output
8. Existing tests still pass — verification: `python -m pytest -q tests/test_export.py tests/test_export_unattributed.py`

Note: subprocess runs from a temp cwd need `PYTHONPATH=<repo root>` (billing is not installed).

## Files to Read

- billing/otel/export.py, .env.example, billing/config.py (load_env), tests/test_export_unattributed.py (seeding pattern)

## Files to Create / Change

- billing/otel/export.py
- .env.example

## Constraints

- Must: stdlib only; match existing style. Must NOT: touch other files, ingest, or attribution;
  persist anything; commit secrets.

## Verification

- `python -m pytest -q tests/test_export.py tests/test_export_unattributed.py`
