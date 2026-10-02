You are the evaluator subagent (RESUMED, Phase 6.5 docs final audit). Read: .claude/agents/evaluator.md

CURRENT_DATETIME: 2026-10-02T21:00:00-10:00

## Task
PHASE 6.5 - final audit of the documentation change set for goal `unknown-parent-child-inheritance`
(project root: C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine). Verdict:
APPROVED | ISSUES. Phase 6.3 (plan evaluation) was FOLDED into this audit because the edit list has only 2
docs, so you ALSO verify the plan criteria: coverage (is any doc that the shipped change makes stale
missing from the edit list?), scope (zero code / excluded-path edits), anti-invention (each documented
claim traces to a file read). Docs-only guardrails: `_research/` and `_goals/` read-only, no code edits,
surgical edits preserving accurate prose verbatim.

## What changed (read the diffs: `git diff -- README.md tests/COVERAGE_MAP.md`; reports in
`spawns/23-report.md` (README) and `spawns/24-report.md` (COVERAGE_MAP))
- `README.md` (24 insertions / 9 deletions): the 9 items you listed in the Phase 5 audit (your report
  `spawns/21-report.md`) plus one extra clause in the `bill.py` bullet.
- `tests/COVERAGE_MAP.md` (+58 lines): a new goal section appended per the file's own convention.
- Unchanged by design: `fabric/README.md` (accurate), and FENCED / flag-only: `deploy/README.md`
  (~lines 109-110, 179, 201-203, 247), `client-package/INSTRUCTIONS.md` (107, 164),
  `client-package/ADMIN.md`, `billing/otel/cowork_attribute.py` docstring (code), and the
  `otel_store.multi_repo_sessions` diagnostic (code; documented in README instead). `goal.md`
  Constraints forbid touching `deploy/` and `client-package/`.

## Requirements
1. **Accuracy against code:** verify EVERY new/changed README sentence against `billing/otel/attribute.py`
   (module docstring, `_blocked`, `_norm`, `_inherit_table`, `resolved_repo`, `resolved_view`),
   `billing/otel/otel_store.py:718-731`, `billing/otel/bill.py`, and your own Phase 5 evidence. Look for
   overclaims (e.g. a stated blocklist name that is not in `_CONTAINER_NAMES`; "ancestor-only"; "before or
   after"; "exactly one repo"; the `timeline` table row; the 0.24 s per 100k figure and its caveat). Flag
   anything not traceable.
2. **Mutual consistency:** README statements vs each other (the `attribute.py` bullet, the table row,
   Accepted mislabels, the unattributed_project paragraph, the developer-cost and pilot lines, the
   capacity note), and vs `fabric/README.md`, `tests/COVERAGE_MAP.md`.
3. **Coverage (folded plan check):** grep every in-scope doc (all markdown EXCEPT `_goals/`, `_research/`)
   for stale markers: `as-of`, `session_repo_timeline`, `timeline`, `unknown`, `outside a git repo`,
   `no git remote`, `no_remote`, `desktop-scratch`, `local:(`. Confirm nothing ELSE (outside the fenced
   list above) is now untrue; list fenced-doc staleness precisely so the user can decide.
4. **COVERAGE_MAP:** every cited node id/test name exists in `tests/test_attribute_inheritance.py`
   (script it), parametrized counts are right, GAP entries are honest, no existing section was edited
   (`git diff` must show insertions only for that file), and the map does not claim a mutant result the
   suite cannot prove (it should frame mutation outcomes as evaluator-measured).
5. **Scope:** `git status --short` must show ONLY documentation files changed by Phase 6 on top of the
   code/test work already audited: ` M README.md`, ` M tests/COVERAGE_MAP.md`, plus the pre-existing
   ` M billing/otel/attribute.py` (hash 38d2db20fe79911ed9c9c6e49f714958ee527021, unchanged),
   `?? tests/test_attribute_inheritance.py`, `?? _goals/unknown-parent-child-inheritance/`. Line endings
   preserved (no CRLF/LF churn: check `git diff --stat` size matches the content change).
6. Markdown lint if a linter is configured (check repo for markdownlint config; if none, say so and
   at least verify tables render: column counts per row, fenced blocks closed, links not broken by
   the edit).
7. Do NOT run the full suite (already green: 1202 passed before Phase 6; docs-only since).

## Files to Read
- README.md (diff regions + surrounding context), tests/COVERAGE_MAP.md (new section), fabric/README.md
- billing/otel/attribute.py, billing/otel/otel_store.py, billing/otel/bill.py, tests/test_attribute_inheritance.py
- spawns/21-report.md, 23-report.md, 24-report.md; goal.md (Constraints/Out of Scope)

## Write fence
none (never edit repo files; scratch in the scratchpad; NEVER git checkout/restore/stash/reset any repo
path - the work is uncommitted)

## Model
requested: claude-opus-5 · tier: frontier · rotation: n/a (resumed)

## Rules
- Do not fix anything. Cite file:line. Separate blocking ISSUES from notes.
- Known non-blocking items already carried: AC5 wording `C:\mono` vs `C:\dev\mono` in the (read-only)
  task file; vocabulary-completeness test absent; `_win_case` docstring example; the fenced docs.

## Output
Verdict first: APPROVED | ISSUES, score out of 5; a table of every README/COVERAGE_MAP claim checked
(claim -> source -> status); coverage findings; fenced-doc staleness list; blocking issues; notes;
`### Footprint`.
