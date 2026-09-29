You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-28T22:10:00Z

## Task
Execute task 01 of goal `unattributed-usage-breakdown`: create
`billing/otel/project_label.py` exactly as specified in
`_goals/unattributed-usage-breakdown/01-project-label.md`. That file is the full
specification: frozen interface, Definitions, Root algorithm steps 1–7, and 30 worked
examples. Implement it as written; do not reinterpret it.

## Requirements
Every checkbox under "Requirements" in 01-project-label.md, every Definition, every
Root algorithm step, all 30 worked examples, and Acceptance Criteria 1–5. In short:
- Frozen public names: LOCAL_PREFIX, HOME_LABEL, SCRATCHPAD_LABEL, OTHER_LABEL,
  CONTAINER_DIRS, path_segments, is_scratchpad, root_label, load_session_labels.
- `root_label` never raises and never returns a bare "local:".
- `load_session_labels` runs exactly one SELECT (table name from
  `attribute.TIMELINE_TABLE`), groups in Python, returns {} on an empty timeline, omits
  empty labels, and never writes, commits or opens a connection.

## Files to Read
- _goals/unattributed-usage-breakdown/01-project-label.md (the spec; read in full)
- _goals/unattributed-usage-breakdown/goal.md (context: Discovery Summary, Constraints)
- CLAUDE.md
- billing/otel/attribute.py (TIMELINE_TABLE, module/docstring style)
- billing/otel/otel_store.py lines 60–95 (session_repo_timeline schema) and the OtelStore
  constructor (for building a temp store in your checks)
- .claude/skills/test-ladder/SKILL.md (rungs 1–2 only)

## Write fence
- billing/otel/project_label.py   (the ONLY path you may create or modify in the repo)
Throwaway check scripts go ONLY in the session scratchpad:
C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\0ab35cbd-cb5c-4db5-9ffc-e0282cc3cab6\scratchpad

## Model
requested: claude-sonnet-5 · tier: light · rotation: n/a (cycle 1)

## Rules
- Standard library only (re, sqlite3, typing / collections.abc). No third-party import
  may enter billing/ (CLAUDE.md hard constraint).
- Repo attribution is resolved at query time: persist nothing, no schema change.
- No filesystem access to resolve paths; these paths come from other machines.
- Do not edit attribute.py, otel_store.py, tests, README, or anything else.
- No git command that changes the working tree or index (stash/checkout/restore/reset);
  the tree holds the user's uncommitted work.
- Comments: at most one short line where the why is non-obvious. A concise module
  docstring is fine.
- Do NOT run the full suite (`python -m pytest -q`); rung 3 belongs to the orchestrator.
  Rung 2 allowed: `python -m pytest tests/test_attribute.py -q`.

## Output
A report with:
1. Files changed.
2. Evidence for each Acceptance Criterion 1–5: the exact commands run and their output
   (for AC2, print all 30 examples as `#n expected got OK/FAIL`).
3. Rung 2 result.
4. Any deviation from the spec, with the reason (should be none).
5. A `### Footprint` block (approximate chars read, commands run).
