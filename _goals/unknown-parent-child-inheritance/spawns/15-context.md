You are the test-writer subagent. Read: .claude/agents/test-writer.md

CURRENT_DATETIME: 2026-10-02T10:30:00-10:00

## Task
Execute task 02: `_goals/unknown-parent-child-inheritance/02-tests.md` - write
`tests/test_attribute_inheritance.py`, outcome-verifying tests (real temp SQLite stores, no mocks of
the SQL) for the ancestor-of-real-repo inheritance that task 01 implemented in
`billing/otel/attribute.py` (PASSED evaluation; hash 38d2db20fe79911ed9c9c6e49f714958ee527021, still
uncommitted in the working tree). Project root: C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine
Read the goal for context: `_goals/unknown-parent-child-inheritance/goal.md`.

## Requirements
The task file `02-tests.md` is authoritative and exhaustive: every bullet under Requirements and every
Acceptance Criterion 1-4 is verified by an evaluator. The implementation changed in shape while task 01
was iterated - these AS-BUILT facts override older wording in the task file:
- **Direction is ANCESTOR-ONLY** (real row at the same folder or BELOW the unknown folder). A real
  parent with an unknown CHILD stays `unknown`.
- **Anchor blocklist** (project-level folders only): BLOCKED = roots (`C:\`, `/`, `~`, any
  `/mnt/<x>`, `/media/<x>`, `/volumes/<x>`, `/<letter>`, UNC `\\srv` and `\\srv\share`), home folders
  (`C:\Users\x`, `/home/x`, `/root`), top-level folders under a root (`C:\Cyclotron`,
  `\\srv\share\team`), and containers whose last segment is in `code, src, source, repos, projects,
  dev, git, github, workspace, desktop, documents, downloads, library, cloudstorage, work, clients,
  temp, tmp, appdata` or starts with `onedrive` / `visual studio `. The exact BLOCKED/ALLOWED lists
  are in `01-attribute-inheritance.md`; use them, with a real descendant row so the block is the only
  reason for `unknown`. Also assert `/mnt/c/dev/wealthspire` and `/c/dev/wealthspire` ARE allowed.
- **Final tie-break is now `repo`-based**, not `rowid` (as-of: `repo DESC`; first: `repo ASC`), with
  repo and cwd always from the SAME row. Write tie tests against THAT rule (a real repo that sorts
  above `unknown` wins an exact (session, ts, seq) tie in both insertion orders; an `unknown` row at an
  unrelated cwd that wins a tie must not borrow a related real row's cwd).
- **`resolved_view` is a single LEFT JOIN query**; the standalone `resolved_repo(alias)` /
  `attribution_source(alias)` expressions are separate code paths that must agree with it.
- NULL repo as-of row: falls back to the first row's RAW repo, then the wrapper tag (same as the
  ORIGINAL attribute.py). Unreachable via ingest; seed with a raw INSERT.
- Preservation (a) uses `C:\dev\mono` / `C:\dev\mono\sub` (NOT `C:\mono`).
- ADDITIONAL tests required (orchestrator additions after the evaluation cycles; same write fence):
  1. **View == standalone:** on a representative multi-session store, evaluate the view
     (`WITH r AS (...)`) and `SELECT resolved_repo(), attribution_source()` -style standalone
     expressions per datapoint and assert identical results (token_usage and cost_usage).
  2. **Cardinality:** `SELECT count(*)` over `resolved_view(table)` equals the table's row count, with
     timeline rows sharing identical (session, ts, seq) and duplicate cwds (LEFT JOIN must not
     duplicate/drop datapoints).
  3. **Alias + column list:** for aliases `t` (default), `x`, `r`, `_i`, `_ar`, `rid`, `v`, and quoted
     `"x y"` / `[sp ace]`, the view returns the same resolved values as the default alias AND its
     `SELECT *` column list equals the table's columns + `resolved_repo` + `attribution_source` (no
     leaked helper columns). Quoted aliases must not raise.
  4. **No behavior change without unknown rows:** a store whose timeline has NO 'unknown' rows
     resolves exactly as the pre-change rule would (as-of row's repo, else first row's, else wrapper tag).
- Mutation check (task AC2) must target the AS-BUILT code. Find the matching spots in
  `billing/otel/attribute.py` (`_inherit_table`, `_blocked`, `_norm`, the descendant comparison, the
  distinct-repo requirement, the unknown-only gate, `_fmt`'s alias derivation). Mutants (a)-(f) from the
  task file, plus (g) direction (also accept real ANCESTORS) and (h) `_fmt` returning the raw alias
  for the inner names (breaks the `_i`/quoted-alias tests). Each must turn >= 1 NAMED test red.

## Files to Read
- _goals/unknown-parent-child-inheritance/02-tests.md (authoritative) and 01-attribute-inheritance.md (BLOCKED/ALLOWED lists)
- _goals/unknown-parent-child-inheritance/goal.md
- billing/otel/attribute.py (read fully), billing/otel/otel_store.py (insert_session_repo, insert_datapoint, insert_cost_datapoint, schema)
- tests/test_attribute.py (helper/fixture style, DESKTOP_NANO), tests/conftest.py (tmp_db_path)
- billing/otel/export.py (build) and billing/otel/bill.py for the one consumer smoke test
- .claude/skills/python-testing-patterns/SKILL.md, .claude/skills/test-ladder/SKILL.md
- Scratchpad hints (read-only, reuse ideas, do NOT import them): `eval06/func2.py` (scenario list),
  `eval06/alias_chk7.py`, `eval06/samerow2.py`

## Write fence
ONLY: `tests/test_attribute_inheritance.py` (create). TEMPORARY exception: `billing/otel/attribute.py`
for the mutation check only - every mutation MUST be reverted by restoring from your scratchpad backup
and the final `git hash-object billing/otel/attribute.py` MUST equal H0 =
38d2db20fe79911ed9c9c6e49f714958ee527021. Scratchpad dir:
C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\efecdfb4-de1b-4a6f-9f68-641f5525f749\scratchpad\

## Model
requested: claude-sonnet-5 · tier: light · rotation: cycle 1 (normal)

## Rules
- **CRITICAL - task 01's work is UNCOMMITTED.** NEVER run `git checkout`, `git restore`, `git stash`
  or `git reset` on ANY repo path: `git checkout -- billing/otel/attribute.py` would DESTROY the
  implementation (HEAD has the pre-feature file). BEFORE the first mutant, copy
  `billing/otel/attribute.py` to the scratchpad (`attribute_H0_38d2db2.py`), and after EVERY mutant
  restore by copying that file back; verify with `git hash-object` after each restore.
- Test ladder rungs 1-2 only. Rung 1 = `python -m pytest tests/test_attribute_inheritance.py -v`.
  Rung 2 = `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_export_unattributed.py tests/test_invoice.py tests/test_reconcile.py -q`. NEVER the full suite.
- pytest + stdlib only; no network; use `tmp_db_path`; nothing outside `tmp_path`. Windows paths in
  Python source MUST be raw strings or properly escaped (a bare `'\d'` / `'\U'` is a test bug).
- Tests must be deterministic and must FAIL if the behavior regresses (outcome assertions; never
  "no exception raised"). If a test exposes a defect in task 01, REPORT it - do not edit
  `attribute.py` permanently and do not weaken the assertion.
- Do not touch README, deploy/, client-package/, other tests, the VM; do not commit.

## Output
Report: the list of test names grouped by requirement, the rung 1 and rung 2 results, the mutation
table (mutant -> description -> named test(s) that went red -> restore verified by hash), H0 before
and after, `git status --short`, anything you could not do (state why), and a `### Footprint`
block (`files_read: <N> (~<C> chars)`).
