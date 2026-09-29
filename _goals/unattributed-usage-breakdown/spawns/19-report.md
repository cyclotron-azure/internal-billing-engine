**Model (self-reported)**: claude-sonnet-5-5
## Task Complete: Phase 6.4 README alignment (unattributed-usage-breakdown)

### Requirements checklist
- [x] Edit 1: `local:(other)` bullet now lists both missing guard triggers. Source: `billing/otel/project_label.py:148-158` (`seg.startswith("-Users-")` at line 152, `any(ord(ch) < 32 ...)` at line 155).
- [x] Edit 2: `unknown` rate bullet keeps its existing sentence and gains a clause with the anchor link. Source: `export.py:18-19, 44, 48, 128` for the column names; anchor target is the README heading "### Unattributed usage in the lake tables" (README line 337).
- [x] Edit 3: capacity checkpoint sentence added, with no numbers. Source: `export.py:85` (one `load_session_labels` call per build), `export.py:91-99` (CASE-guarded src/sid, applied to `resolved_repo = 'unknown'` rows only).
- [x] Nothing else touched: no `_research/`, `_goals/`, code, tests, config or zip edits. No git commands that change the tree or index.

### Edits (before -> after)
1. Before: "...contains `OneDrive` anywhere in the name, is a bare `Users`/`home` folder, or is the username (allowlist guard)."
   After: "...contains `OneDrive` anywhere in the name, starts with `-Users-`, is a bare `Users`/`home` folder, contains a control character, or is the username (allowlist guard)."
2. Before: "...High means a workflow problem to fix with policy, not code."
   After: same, followed by "The lake tables now break `unknown` down by `attribution_source` and `unattributed_project`; see [Unattributed usage in the lake tables](#unattributed-usage-in-the-lake-tables)."
3. Before: "...to find the date, and plan a compaction step (roll datapoints...)"
   After: "...to find the date. The `unknown` breakdown adds a per-datapoint class lookup for `unknown` rows only, plus one read of the session timeline per build. Plan a compaction step (roll datapoints...)"

### Files changed
- `README.md`: the three edits above (in the repo root).

### Verification
- `git diff --stat README.md` gave `1 file changed, 86 insertions(+), 5 deletions(-)`. That total includes README changes that were already uncommitted before this task (the git status snapshot showed README.md as modified). My three edits account for about 6 added and 3 removed lines.
- No tests run, since this task is docs only.

### Notes for the evaluator
- In edit 3, "per-datapoint class lookup" is my wording for the `attribution_source` class carried on `unknown` rows. Per `export.py:83-84` that class is carried only by rows that resolve to `unknown`. Row-level scan cost otherwise is unchanged, so I gave no timing.
- I did not read `.claude/skills/align-docs/SKILL.md` or `goal.md`; the context package's guardrails were enough and every claim traces to `project_label.py` or `export.py`. Say so if you need me to cross-check them.

### Footprint
files_read: 6 (~70000 chars: context file, README.md excerpts, project_label.py excerpt, export.py excerpts and grep hits)
commands_run: 1
