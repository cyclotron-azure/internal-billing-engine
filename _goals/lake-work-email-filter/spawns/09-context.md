You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-29T13:20:00Z

## Task
Fix cycle 2 for task 03 (_goals/lake-work-email-filter/03-readme.md). One accuracy fix in README.md.

## Requirements
1. README ~lines 348-349 (in the "Work-domain filter" subsection, the "Kept" bullet) currently claims whitespace-only users and the literal `unknown` (any case) are "exported as `unknown`". That is false: only NULL and "" become `unknown` (export.py: `r["user_email"] or UNKNOWN_USER`); whitespace-only values and case variants of `unknown` (UNKNOWN, Unknown) are kept but exported exactly as stored. Reword, e.g.: "Kept: rows with a NULL/empty user (exported as `unknown`); rows whose user is whitespace-only or the literal `unknown` in any case (kept, exported as stored); and rows for allowed-domain users; all unchanged." Confirm against billing/otel/export.py.
2. Optional: rewrap the ~717 line ("(`invoice.py` locally, the notebook in Fabric). Assert per-month totals match after restricting...") to the width of the surrounding paragraph (~84 chars).
Change nothing else.

## Files to Read
README.md (lines ~340-360 and ~710-722), billing/otel/export.py.

## Write fence
README.md only.

## Model
requested: claude-sonnet-5 · tier: light · rotation: cycle 2 (no other family available)

## Rules
Surgical; no code changes; keep the file's existing line endings.

## Output
Report: exact edited lines, `### Footprint` block.
