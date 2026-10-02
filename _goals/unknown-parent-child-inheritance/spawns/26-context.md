You are the implementer subagent (RESUMED, Phase 6 docs fix cycle 1). Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-10-02T22:00:00-10:00

## Task
Fix the documentation issues found by the Phase 6.5 audit (report: the audit's findings are reproduced
below; the full report text is in this session's orchestration log entry #25 - you do not need it).
DOCS-ONLY, surgical edits, same guardrails as your previous package: never write under `_goals/` or
`_research/`; never modify code, tests, config, `deploy/`, `client-package/`; every claim must trace to a
file you read this run; preserve accurate prose verbatim and the files' existing line endings; never run
git checkout/restore/stash/reset/commit (UNCOMMITTED code from this goal is in the tree).
Project root: C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine

## Required edits (5, plus 1 optional wording note)
1. **README.md, the `attribution_source` table `timeline` row (~line 371).** Your reason list after
   "could not inherit a real repo:" omits the most common reason. Add: no real-repo timeline row in the
   session at or below that folder (for example an unrelated sibling folder, or a session whose timeline
   rows are all `unknown`), and an empty or missing cwd. Keep the existing reasons. Verify against
   `billing/otel/attribute.py` (`_inherit_table`: `_x` qualifying rows, the `n <> ''` guards, the
   count/min/max rule). Keep the row a single table row (do not break the table).
2. **README.md, Capacity checkpoint (~lines 618-623).** You quoted only "about 0.24 s per 100,000
   datapoints". Replace with the measured RANGE and keep the "synthetic stores, not production data"
   caveat: about 0.24 s per 100,000 datapoints for a plain `resolved_view` scan, up to about 0.87 s per
   100,000 datapoints for the real export / bill / reconcile statements (measured one statement per
   process on synthetic stores of ~130k datapoints and ~40k-44k timeline rows; varies with machine load).
   Source the figures from `_goals/unknown-parent-child-inheritance/spawns/` reports 13, 14 and 21
   (read the exact lines; cite only what you find: 0.244 in 21-report, 0.828/0.869 export token in
   13/14-report, 0.327-0.329 on a quiet machine in 14-report). If a figure is not in those files, omit it.
3. **`.claude/skills/test-ladder/SKILL.md` (~line 75).** The impacted-test row for
   `billing/otel/attribute.py` lists `tests/test_attribute.py` plus `test_bill.py`, `test_invoice.py` (read
   the row). Add `tests/test_attribute_inheritance.py` to that row. Surgical: change only that row.
4. **tests/COVERAGE_MAP.md, the new section, Task 01 row 5.** It says tie-breaks are by `rowid`. As built,
   the final tie-break is `repo` (DESC for the as-of lookup, ASC for the first-row lookup) after `ts` and
   `seq`; `rowid` only identifies the single selected row. Correct the wording (read
   `billing/otel/attribute.py` ~lines 100-115 first). Keep the cited tests (they are correct).
5. **tests/COVERAGE_MAP.md, the new section, Task 02 row 1.** "136 tests at first PASS" is wrong. Replace
   with: 129 tests at first authoring, 136 after fix cycle 1, 196 at PASS (verified:
   `python -m pytest tests/test_attribute_inheritance.py --collect-only -q` gives 196).
6. **Optional wording (do it, 1 line):** README.md:153 says "...the folder of the session's real-repo
   timeline rows, and those rows name exactly one repo". Reword "the session's real-repo timeline rows" to
   "related real-repo timeline rows (same folder or below it)" so it cannot be read as requiring ALL of the
   session's real rows to sit below the folder. Keep everything else in that bullet unchanged.
Do NOT touch `deploy/` or `client-package/` docs (fenced by the goal; the orchestrator will report their
staleness to the user).

## Files to Read FIRST
- billing/otel/attribute.py; `_goals/unknown-parent-child-inheritance/spawns/13-report.md`, `14-report.md`, `21-report.md`
- README.md (the touched regions), tests/COVERAGE_MAP.md (the new section only), .claude/skills/test-ladder/SKILL.md

## Write fence
ONLY: `README.md`, `tests/COVERAGE_MAP.md`, `.claude/skills/test-ladder/SKILL.md`

## Model
requested: claude-sonnet-5 · tier: light · rotation: fix cycle 1 (normal, resumed)

## Rules
- Docs-only: do NOT run any test suite (the single-file collect-only in item 5 is allowed).
- If the only accurate fix would require a code change, STOP and report.

## Output
Report: each edit (file, location, before -> after summary, the source you verified against), anything
you omitted because unsourced, `git status --short`, `git diff --stat` for the three files, and a
`### Footprint` block (`files_read: <N> (~<C> chars)`).
