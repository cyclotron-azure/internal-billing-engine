**Model (self-reported)**: claude-sonnet-5-5
## Task Complete: Phase 6, add the `unknown-parent-child-inheritance` section to tests/COVERAGE_MAP.md

### Requirements checklist
- [x] Appended one new section at the end of `tests/COVERAGE_MAP.md`. It uses the neighbouring style: `# Coverage map: ...`, `## Task NN - ...` tables with `| Criterion | Test node id(s) |`, and a closing `## GAPs (explicit)`. Existing sections are untouched (`git diff --stat` shows 58 insertions, 0 deletions).
- [x] Task 01 criteria 1-9 are mapped to named tests. This includes the Nate, reverse, Derek, distinct/same-repo, preservation, prefix lookalike, blocklist classes, empty/NULL cwd, DirectoryAdded, session id `unknown`, desktop-scratch, alias plus column list, view==standalone, cardinality and consumer smoke tests.
- [x] Criterion 10 is recorded as a property of the rung-2 command, not one node id.
- [x] Criterion 11 (performance) is listed as a **GAP**, in the file's existing perf-GAP style. The reason given: it is a wall-clock measurement on a synthetic store, and a timing assertion would be flaky. The 1.0 s per 100,000 datapoints per consumer statement limit is stated, with a pointer to spawn reports 11/13/14/21.
- [x] Criterion 12 is recorded as a property of `git status --short` and `git hash-object`.
- [x] Task 02 criteria 1-4 are mapped:
  - Criterion 1 points to the test file itself (136 tests at first PASS, 196 at final).
  - Criterion 2 lists the mutant families and the named test intended to kill each.
  - Criterion 3 is a rung-2 command property.
  - Criterion 4 is a `git status --short` plus hash property.
- [x] A "Goal criteria" table covers the Success Criteria that no single task criterion covers. A closing "GAPs (explicit)" list follows it.
- [x] The test count 196 is confirmed by running `python -m pytest tests/test_attribute_inheritance.py -q`, which gave "196 passed".
- [x] Only `tests/COVERAGE_MAP.md` was written. No git state-changing commands were run. Nothing under `_goals/` or `_research/` was written.

### Files changed
- `C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\tests\COVERAGE_MAP.md` — added the new goal section (58 lines). The file stays LF with no CRs, as before.

### Verification
- `python -m pytest tests/test_attribute_inheritance.py --collect-only -q` -> 196 tests collected.
- `python -m pytest tests/test_attribute_inheritance.py -q` -> 196 passed.
- A script extracted every `test_*` identifier from the new section and checked each against `def <name>(` in the test file. All 70 identifiers exist. The only non-matches were file stems (`test_bill`, `test_attribute` and similar) and the `test_blocklist_` prefix wildcard.
- The new section cites tests mostly by function name and notes parametrized counts, as neighbouring sections do. I checked those counts against the collect-only list:
  - wildcards inert: 5
  - wildcard match literally: 3
  - allowed project folders: 9
  - alias variants: 16 aliases x 2 tables
  - reverse: 2
  - tie tests: 2 each
- I did not re-run the mutants. The pairings in Task 02 criterion 2 are the tests' design intent: widen -> `test_prefix_lookalike_is_not_a_descendant`, direction -> `test_reverse_real_parent_unknown_child_stays_unknown`, blocklist -> `test_blocklist_*`, with container names -> `..._posix_mid_depth` and `..._windows_mid_depth_mixed_case`, distinct -> `test_two_distinct_qualifying_repos_stay_unknown`, unknown-only -> `test_preservation_a_real_effective_rows_keep_own_repo`, wildcard -> `test_wildcards_in_paths_are_inert`. I read these tests and the logic fits. The map says the actual red/green outcomes live in the evaluator's mutation report, not in the suite.
- `git status --short`:
  ```
   M README.md
   M billing/otel/attribute.py
   M tests/COVERAGE_MAP.md
  ?? _goals/unknown-parent-child-inheritance/
  ?? tests/test_attribute_inheritance.py
  ```
- `git diff --stat -- tests/COVERAGE_MAP.md` -> `tests/COVERAGE_MAP.md | 58 +++++`, 1 file changed, 58 insertions(+). Git also prints the usual LF-to-CRLF warning.

### Notes for the evaluator
- `M README.md` is in the tree but I did not touch it. It was already modified, most likely by a parallel Phase 6 docs task.
- Task 02 criterion 2 is framed as "named test designed to kill each mutant". I did not re-execute the mutants, so the map does not claim a measured result.
- The "Goal criteria" table lists "nothing persisted / stdlib only" as a GAP, since it is a code-review property with no test.
- I added a non-GAP note on the deny-list residual. It cites `test_blocklist_container_name_shapes_plain_child_folder_inherits` as pinning the intended behavior for a non-vocabulary folder like `acme`.

### Footprint
files_read: 6 (~95,000 chars: COVERAGE_MAP.md, 01-attribute-inheritance.md, 02-tests.md, goal.md, partial reads of test_attribute_inheritance.py, 24-context.md)
commands_run: 4
