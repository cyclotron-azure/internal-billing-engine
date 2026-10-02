You are the test-writer subagent. Read: .claude/agents/test-writer.md

CURRENT_DATETIME: 2026-10-02T16:00:00-10:00

## Task
FIX CYCLE 2 for task 02 (`_goals/unknown-parent-child-inheritance/02-tests.md`), fresh context.
`tests/test_attribute_inheritance.py` (136 tests, untracked) tests the inheritance rule implemented in
`billing/otel/attribute.py` (task 01, PASSED; hash H0 = 38d2db20fe79911ed9c9c6e49f714958ee527021, UNCOMMITTED).
The evaluator found ONE remaining gap: 14 of the 19 names in `_CONTAINER_NAMES` can be deleted from
`billing/otel/attribute.py` with the suite staying green, and one case is vacuous. Report:
`_goals/unknown-parent-child-inheritance/spawns/18-report.md` (read Issues + Required fixes + its mutation table).
Project root: C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine

## Requirements
1. **Per-name container test.** Add a test parametrized over EVERY name in the container vocabulary,
   written as a LITERAL list in the test (do not import `_CONTAINER_NAMES`; copy the 19 names by reading
   `billing/otel/attribute.py` lines ~86-90 now: code, src, source, repos, projects, dev, git, github,
   workspace, desktop, documents, downloads, library, cloudstorage, work, clients, temp, tmp, appdata -
   verify against the file). Each case: an unknown timeline row at a depth where ONLY the name rule
   applies (not home, not top-level, not root, not mount): e.g. POSIX `/srv/data/<name>` and Windows
   `C:\Users\x\<Name>\...`-style paths are NOT suitable if another rule also blocks them - verify
   each path is blocked by exactly the name rule by checking that a mutant removing JUST that name
   makes it resolve to the real repo. Suggested shapes (confirm by experiment): `/opt/team/<name>` with a
   real descendant `/opt/team/<name>/app`, and `D:\work2\<Name>` ... / `C:\Projects2\clients\<Name>`
   style paths at depth >= 3 under a drive, in mixed case. Each case needs a real descendant row so the
   name rule is the only reason for `unknown`. Add the matching positive control: the same shape
   with a non-vocabulary folder name (`acme`) one level deeper DOES inherit.
2. **Fix the vacuous `/mnt/c/dev` case.** It is blocked twice over (container name `dev` AND the
   mount top-level rule), so it cannot fail for the reason it is listed under. Move it back under the
   top-level test OR replace it in the container test by a deeper path that only the name rule
   blocks, e.g. `("/mnt/c/x/dev", "/mnt/c/x/dev/app")`. Fix any comment/docstring that gives the
   wrong rationale.
3. **Optional, cheap:** a positive control for the mount shape `/volumes/disk/<a>/<b>` -> inherits.
4. **Mutation re-proof on a SCRATCHPAD COPY** (see Rules): remove EACH of the 19 names from the
   vocabulary ALONE (19 mutants) - every one must turn >= 1 NAMED test red; re-run the earlier
   mutants: bl_mount_k2, bl_gitbash_seg, z1 (`_HOME_PARENTS` dropped), the combined empty-guard
   mutant, a (widen), b/g (direction), c (blocklist removed), d (distinct), e (unknown-only), f (LIKE),
   h (raw alias). Report a compact table (mutant -> a red named test). The evaluator's drivers and
   probes in the scratchpad (`ev18_mut.py`, `ev18_extra.py`, `ev18_probe.py`, `ev18_probe2.py`,
   `ev16_*`) show how to mutate a copy; reuse them as a starting point.
5. Rung 1 `python -m pytest tests/test_attribute_inheritance.py -v` and rung 2
   `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_export_unattributed.py tests/test_invoice.py tests/test_reconcile.py -q` must pass.

## Files to Read
- _goals/unknown-parent-child-inheritance/spawns/18-report.md; 02-tests.md; 01-attribute-inheritance.md (BLOCKED/ALLOWED lists)
- tests/test_attribute_inheritance.py (all), billing/otel/attribute.py (`_CONTAINER_NAMES`, `_blocked`, `_norm`)
- scratchpad drivers named above (read-only reuse)

## Write fence
ONLY: `tests/test_attribute_inheritance.py`. Do NOT edit `billing/otel/attribute.py` in the repo at all.
Mutate a COPY of the working tree in the scratchpad (exclude `.git`, `_goals`, caches); confirm
`billing.__file__` / `billing.otel.attribute.__file__` points into the copy before trusting results.
Scratchpad dir: C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\efecdfb4-de1b-4a6f-9f68-641f5525f749\scratchpad\

## Model
requested: claude-fable-5-1 · tier: light role, rotated to a different model line · rotation: fix cycle 2

## Rules
- **CRITICAL - task 01's work is UNCOMMITTED.** NEVER run `git checkout`, `git restore`, `git stash` or
  `git reset` on ANY repo path. The repo's `attribute.py` hash MUST still equal H0 when you finish.
- Test ladder rungs 1-2 only; never the full suite. pytest + stdlib only; Windows paths as raw strings.
- Tests must be deterministic and FAIL if behavior regresses; never weaken an assertion. If a test
  exposes a defect in task 01, REPORT it.
- Do not commit; do not touch README, deploy/, other tests, the VM.

## Output
Report: the tests added/changed (names), a 19-row per-name mutation table plus the other mutants
(mutant -> red named test), rung 1 and rung 2 results, H0 before/after, `git status --short`,
anything you could not do, and a `### Footprint` block (`files_read: <N> (~<C> chars)`).
