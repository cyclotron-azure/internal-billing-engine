You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-10-01T12:40:00-10:00

## Task
Execute task 01 EXACTLY: `_goals/unknown-parent-child-inheritance/01-attribute-inheritance.md`
(project root: C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine).
Implement ancestor-of-real-repo inheritance in `resolved_repo()` in
`billing/otel/attribute.py`, pure SQL, interface unchanged. The task file is the
authoritative, exhaustive requirement list - every bullet and every acceptance criterion
(1-12) is verified by an evaluator. Read the goal for context:
`_goals/unknown-parent-child-inheritance/goal.md`.

## Requirements
All of them, from the task file. Highlights you must not miss:
- Direction is ANCESTOR-ONLY: unknown folder `u` inherits only from real rows `x` that are the
  same as or BELOW `u`. A real row ABOVE `u` never qualifies.
- Anchor blocklist (roots incl. mounts/UNC/`~`, home folders, top-level folders, container
  names incl. `work, clients, temp, tmp, appdata`, `onedrive*`, `visual studio *`): the
  BLOCKED/ALLOWED example lists in the task file are the arbiter - make every one behave as
  listed (22 blocked, 5 allowed; also `/mnt/c/dev/wealthspire` and `/c/dev/wealthspire` allowed).
- Preserve today's behavior EXACTLY when the effective row is non-unknown or absent.
- Same-row repo+cwd with rowid tie-breaks; `DirectoryAdded` rows never anchor;
  session_id `'unknown'` never inherits; NULL-safe.
- Backslash literal must survive into SQL as a single `'\'` (raw string or `'\\'`; NOT `'\\\\'`).
- Performance gate: scratchpad-only synthetic store, median of 3 runs, heavy-tail session,
  ratio <= 3.0 vs a copy of the ORIGINAL attribute.py. If it fails, STOP and report - do not
  ship it.
- Report `git hash-object billing/otel/attribute.py` as the hand-off hash at the end.

## Files to Read
- _goals/unknown-parent-child-inheritance/01-attribute-inheritance.md  (authoritative)
- _goals/unknown-parent-child-inheritance/goal.md
- billing/otel/attribute.py, billing/otel/otel_store.py (session_repo_timeline), billing/otel/project_label.py (vocabulary only)
- tests/test_attribute.py (existing contracts), README.md (attribute.py bullet; do not edit)
- .claude/skills/test-ladder/SKILL.md, .claude/skills/python-performance-optimization/SKILL.md
- CLAUDE.md (hard constraints)

## Write fence
ONLY: `billing/otel/attribute.py`
(Scratch/benchmark files go in the scratchpad directory, never in the repo:
C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\efecdfb4-de1b-4a6f-9f68-641f5525f749\scratchpad\)

## Model
requested: claude-sonnet-5 · tier: light · rotation: cycle 1 (normal)

## Rules
- Test ladder: rung 1 (new tests: none in this task - say so) then rung 2 (the impacted
  command in AC10). NEVER run the full suite (`python -m pytest -q`); the orchestrator owns rung 3.
- Runtime stdlib only; no new imports; no tests/README/deploy/consumer edits; no table/column/
  index; no registered SQLite functions; never use path text as a LIKE/GLOB pattern.
- Keep a pristine copy of the original `attribute.py` in the scratchpad BEFORE editing (needed
  for the performance baseline). Do NOT use `git checkout`/`git restore` on any repo path.
- If an existing test fails because it encodes the OLD behavior: do not edit it; report the
  test id and why.
- Do not touch the VM, deploy/, client-package/, docker-compose.yml, or commit anything.

## Output
A report with: summary of the design (the SQL structure in prose), files changed, the evidence
for acceptance criteria 1-9 (ad-hoc SQL output), the rung-2 command and result (AC10), the
performance table with three-run medians and ratio (AC11), `git status --short` output and the
`git hash-object billing/otel/attribute.py` hand-off hash (AC12), anything you could not do,
and a `### Footprint` block (`files_read: <N> (~<C> chars)`).
