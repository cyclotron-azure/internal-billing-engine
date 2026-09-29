You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-29T13:10:00Z

## Task
Execute task 03: _goals/lake-work-email-filter/03-readme.md (read it and goal.md in full).

## Requirements
All requirements/ACs in the task file. Implemented behavior to document (read billing/otel/export.py to confirm every claim): ALLOWED_EMAIL_DOMAINS (comma-separated, default cyclotron.com, case-insensitive exact domain after last @; `x@cyclotron.com.au` etc. excluded); NULL/empty/`unknown` user rows kept; raw store unfiltered and bill/reconcile unaffected; every export run (scheduler via build_and_enqueue; `python -m billing.otel.export` with or without --no-enqueue) prints `[export] excluded N group(s) outside <domains>` (also when 0) — N counts distinct excluded (day, repo, model, user) groups; the CLI loads .env, the scheduler already does; lake tables are overwritten in full so the first sync after shipping removes personal-domain rows from all history (add to the Power BI / semantic-model owners section).

## Files to Read
_goals/lake-work-email-filter/goal.md, 03-readme.md, billing/otel/export.py, .env.example, README.md (lines ~160-170, ~270-335, ~395-410).

## Write fence
README.md only.

## Model
requested: claude-sonnet-5 · tier: light · rotation: n/a

## Rules
Surgical edits; no code changes. Before starting run `git status --porcelain` and save it; after finishing run it again and confirm the only new difference is README.md (other tasks may be editing tests/ concurrently — those are not yours).

## Output
Report: edits made (line refs), verification per AC, `### Footprint` block.
