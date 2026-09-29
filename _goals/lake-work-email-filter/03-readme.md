# Task 03: readme

## Objective

README.md (ground truth) documents the work-domain filter on the lake export.

## Dependencies

- 01

```yaml
writes:
  - README.md
reads:
  - billing/otel/export.py
  - .env.example
depends_on:
  - "01-export-domain-filter"
owner: implementer
rewrite_semantics: targeted-insertion
eval_depth: light
```

## Requirements

- [ ] Update the `export.py` bullet (~line 167), the lake-CSV section (~lines 300-325) and the
      config/env section to state: only rows whose user_email is in `ALLOWED_EMAIL_DOMAINS`
      (default `cyclotron.com`; exact, case-insensitive domain match) are exported; `unknown`-user
      rows are kept; the raw store is unfiltered and other tools (bill/reconcile) are unaffected.
- [ ] Add a note under the existing "For Power BI / semantic-model owners" section (README ~398-407)
      that the tables are overwritten in full, so the first sync after this ships removes personal-domain
      rows from ALL history and past-month lake totals may drop.
- [ ] State that every export run (scheduler and `python -m billing.otel.export`) prints an `[export] excluded N group(s)` line, and that the CLI honors `.env`.
- [ ] Fix any other README statement only if it now contradicts the code.
- [ ] Surgical edits only; every unrelated line untouched; no code changes.

## Acceptance Criteria

1. README mentions `ALLOWED_EMAIL_DOMAINS`, the default, the matching rule, unknown-kept, raw store unfiltered, the Power BI/lake-consumer history note, and the `[export] excluded ...` line / `.env` honoring — verification: grep/read
2. Statements match export.py behavior — verification: evaluator cross-check
3. Task touched only README.md — verification: `git status --porcelain` snapshot before vs after the task, diffed (other tasks' edits may be uncommitted)

## Files to Create / Change

- README.md

## Constraints

- Must NOT edit any file except README.md.

## Verification

- `git diff --stat -- README.md`
