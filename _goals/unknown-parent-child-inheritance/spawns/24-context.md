You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-10-02T20:00:00-10:00

## Task
PHASE 6 (align docs) - edit ONE document: `tests/COVERAGE_MAP.md` (project root:
C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine). That file "indexes one
section per goal, mapping every acceptance criterion in that goal's task files to the pytest node id(s)
that verify it. A criterion with no test is listed as a GAP, not omitted." The goal
`unknown-parent-child-inheritance` has no section yet: add one. DOCS-ONLY.

## Core guardrails (NON-NEGOTIABLE)
1. NEVER write under `_goals/` or `_research/` (you may READ them).
2. DOCS-ONLY: never modify code, tests, config or any file but `tests/COVERAGE_MAP.md`.
3. ANTI-INVENTION: every node id you cite must exist - verify each by reading
   `tests/test_attribute_inheritance.py` (and `python -m pytest <node id> --collect-only -q` is allowed to
   confirm a node id collects; do NOT run the full suite). Never cite a test that does not exist; never
   claim coverage a test does not give. If a criterion has no test, list it as a **GAP** with the reason.
4. SCOPE DISCIPLINE: ADD one new section at the end of the file following the existing structure and
   formatting of the neighboring goal sections (heading style `# Coverage map: \`<goal>\``, per-task
   `## Task NN - \`<file>\`` tables with `| Criterion | Test node id(s) |`). Do not edit existing sections.
   Preserve the file's existing line endings and style. Use the Edit tool (append) rather than rewriting.
5. Never run git checkout/restore/stash/reset/commit (UNCOMMITTED work in the tree).

## What to map
Read these task files (READ-ONLY): `_goals/unknown-parent-child-inheritance/01-attribute-inheritance.md`
(Acceptance Criteria 1-12) and `.../02-tests.md` (Acceptance Criteria 1-4), plus `goal.md` Success
Criteria. Map:
- Task 01 criteria 1-9 (behavioral) to the named tests in `tests/test_attribute_inheritance.py`
  (Nate, reverse, Derek, distinct/same repo, preservation, prefix lookalike, blocklist classes,
  empty/NULL cwd, DirectoryAdded, session id `unknown`, desktop-scratch, alias + column list,
  view==standalone, cardinality, consumer smoke `test_export_build_bills_nate_session_to_the_real_repo`).
- Criterion 10 (existing suites unchanged-green): property of the rung-2 command shown in the task file
  (existing suites, see the command), not a single test.
- Criterion 11 (performance): **GAP** - a wall-clock gate is a command-output measurement on a synthetic
  store, not an assertion in the suite (the user replaced the 3x ratio with an absolute limit of
  1.0 s per 100,000 datapoints per real consumer statement; measured values are in
  `_goals/unknown-parent-child-inheritance/spawns/` reports 11/13/14/21; a timing assertion would be
  flaky). Say so in the same style the file uses for existing perf GAPs.
- Criterion 12 (tree/hash): a property of `git status --short` / `git hash-object` at evaluation time.
- Task 02 criteria 1-4: criterion 1 = the test file itself (136 tests at first PASS, 196 at final); 2 =
  mutation check (property of the evaluator's mutation runs - list the mutant families that are killed by
  named tests, e.g. widen -> `test_prefix_lookalike_is_not_a_descendant`, direction ->
  `test_reverse_real_parent_unknown_child_stays_unknown`, each container name ->
  `test_blocklist_container_name_posix_mid_depth` / `..._windows_mid_depth_mixed_case`, etc.; ONLY cite
  pairings you verify in the test file); 3 = existing suites green (rung 2 command); 4 = write fence
  (`git status --short`).
- Goal Success Criteria that no single task criterion covers: add a short "Goal criteria" table.
- End with a "GAPs (explicit)" list (perf gate; any criterion without a test).
Use the final test count (196) only if you confirm it by running
`python -m pytest tests/test_attribute_inheritance.py -q` (allowed: this single file only).

## Files to Read FIRST
- tests/COVERAGE_MAP.md (the last two goal sections for formatting; the intro)
- _goals/unknown-parent-child-inheritance/01-attribute-inheritance.md, 02-tests.md, goal.md
- tests/test_attribute_inheritance.py (all test names)

## Write fence
ONLY: `tests/COVERAGE_MAP.md`

## Model
requested: claude-sonnet-5 · tier: light · rotation: cycle 1

## Rules
- Test ladder: docs-only. Collecting/running the ONE new test file to confirm names/counts is allowed;
  never the full suite.
- Fix the doc, never the code or tests.

## Output
Report: the section you added (headings + a summary of each table), the node ids cited and how you
verified each exists, the GAPs listed, `git status --short`, `git diff --stat -- tests/COVERAGE_MAP.md`,
and a `### Footprint` block (`files_read: <N> (~<C> chars)`).
