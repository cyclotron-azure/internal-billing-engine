You are the test-writer subagent (RESUMED, fix cycle 1 for task 02). Read: .claude/agents/test-writer.md

CURRENT_DATETIME: 2026-10-02T13:30:00-10:00

## Task
Fix the gaps the evaluator found in `tests/test_attribute_inheritance.py`
(task file `_goals/unknown-parent-child-inheritance/02-tests.md`). Evaluator report:
`_goals/unknown-parent-child-inheritance/spawns/16-report.md` (read the Issues and Required fixes).
Project root: C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine

## Requirements
1. **Add killing tests for three non-equivalent surviving mutants** (all in the blocklist tests):
   - Top-level folder under a MOUNT root must be blocked for a NON-container name: add
     `("/mnt/c/Cyclotron", "/mnt/c/Cyclotron/repo")` (and, if the code has the same rule for the other
     mount prefixes, one case each for `/media/x/Cyclotron` and `/volumes/disk/Cyclotron`). The existing
     case `("/mnt/c/dev", ...)` is `unknown` only because `dev` is a container name; either relabel it
     as a container case or keep it but do NOT rely on it for the mount rule. Must go RED under the
     mutant "mount top-level `k <= 3` -> `k <= 2`" (bl_mount_k2).
   - Top-level folder under a Git-Bash drive: `("/c/Cyclotron", "/c/Cyclotron/repo")`. Must go RED
     when the `/[a-z]/*` + `k = 2` part of the top-level rule is removed (bl_gitbash_seg).
   - A bare `users` / `home` parent BELOW depth 1: `(r"C:\data\Users", r"C:\data\Users\proj")` and
     `("/srv/home", "/srv/home/proj")`. Must go RED when `_HOME_PARENTS` is dropped from the blocked
     names list (z1).
   Each new case needs a real descendant row so the block is the only reason for `unknown`; also keep
   a positive control proving the same shapes with a project-level folder DO inherit (e.g.
   `/mnt/c/dev/wealthspire`, `/c/dev/wealthspire`, `C:\data\proj\x` already exist - reuse).
2. **Recommended (do it):** a POSIX-real-row variant of the empty-cwd test: unknown row with cwd `''`
   plus real row `/srv/app/x` -> still `unknown` (the existing test seeds a Windows real path, so it
   cannot catch removal of the empty-path guards).
3. **Optional, cheap:** make `test_export_build_bills_nate_session_to_the_real_repo` independent of the
   process environment by passing `allowed_domains=` explicitly (the user email domain used in the
   fixture) to `export.build`, if its signature allows; otherwise `monkeypatch.setenv` the env var.
   Also assert `attribution_source` (not just `resolved_repo`) in the NULL-repo effective-row test.
4. **Re-prove with a MUTATION CHECK on a SCRATCHPAD COPY of the repo** (not the repo itself - see
   Rules): the 3 mutants above plus the empty-guard mutant for item 2 (remove the `_m.n <> ''` guard AND
   the empty-path block together) must each turn >= 1 NAMED test red; re-run the original 8 mutants
   (a)-(h) too. Report a table: mutant -> named red tests.
5. Rung 1 (`python -m pytest tests/test_attribute_inheritance.py -v`) and rung 2
   (`python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_export_unattributed.py tests/test_invoice.py tests/test_reconcile.py -q`) must pass.

## Files to Read
- _goals/unknown-parent-child-inheritance/spawns/16-report.md (evaluator findings, its mutation table)
- tests/test_attribute_inheritance.py (your file), billing/otel/attribute.py (`_blocked`, `_HOME_PARENTS`, mount/top-level rules, `_norm`)
- scratchpad (read-only, reuse): `ev16_mut.py`, `ev16b_mut.py`, `ev16_probe.py` (the evaluator's mutation drivers/probe) and your own `mutate.py`

## Write fence
ONLY: `tests/test_attribute_inheritance.py`. For mutation checks use a COPY of the working tree in the
scratchpad (exclude `.git`, `_goals`, caches), mutate and run tests THERE; confirm `billing.__file__`
points into the copy. Do NOT edit `billing/otel/attribute.py` in the repo at all this cycle.
Scratchpad dir: C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\efecdfb4-de1b-4a6f-9f68-641f5525f749\scratchpad\

## Model
requested: claude-sonnet-5 · tier: light · rotation: fix cycle 1 (normal, resumed)

## Rules
- **CRITICAL - task 01's work is UNCOMMITTED.** NEVER run `git checkout`, `git restore`, `git stash` or
  `git reset` on ANY repo path (it would destroy `billing/otel/attribute.py`). The repo's
  `attribute.py` hash must still equal H0 = 38d2db20fe79911ed9c9c6e49f714958ee527021 when you finish.
- Test ladder rungs 1-2 only; never the full suite. pytest + stdlib only; raw strings for Windows paths.
- Tests must be deterministic and must FAIL if behavior regresses; never weaken an assertion. If a
  test exposes a defect in task 01, REPORT it.
- Do not commit; do not touch README, deploy/, other tests, the VM.

## Output
Report: what you added/changed (test names), the mutation table (mutant -> named red tests), rung 1
and rung 2 results, H0 before/after, `git status --short`, anything you could not do, and a
`### Footprint` block (`files_read: <N> (~<C> chars)`).
