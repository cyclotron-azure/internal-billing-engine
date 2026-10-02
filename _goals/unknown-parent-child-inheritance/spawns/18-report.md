**Model (self-reported)**: claude-opus-5-5 (Opus 5.5). The package requested claude-opus-5.

## Verdict: NEEDS FIXES
**Score**: 3/5
**failure_class:** implementation

Everything I flagged in cycle 1 is fixed. All three mutants that survived last time now turn named tests red, and so does the combined empty-guard mutant.

The fix created one new problem, and one coverage gap remains that I did not test for in cycle 1. The report says the `/mnt/c/dev` case was moved to the containers test "because only the container name makes it `unknown`". That is ❌ Contradicted: `/mnt/c/dev` is also blocked by the top-level-under-mount rule (`k <= 3`), so removing the `dev` name does not turn it red. On top of that, 13 of the 19 container names have no test that fails when the name is removed. I proved the misattribution with concrete paths below. A ❌ claim caps the verdict at NEEDS FIXES.

### Prior issues: fixed or not
- Issue 1, part a: bl_mount_k2 survived → **FIXED**. Now red: `test_blocklist_top_level_folders_under_a_root[/mnt/c/Cyclotron]`, `[/media/x/Cyclotron]`, `[/volumes/disk/Cyclotron]` (tests/test_attribute_inheritance.py:432-434).
- Issue 1, part b: bl_gitbash_seg survived → **FIXED**. Now red: `…[/c/Cyclotron]` (:435).
- Issue 1, part c: z1 (`_HOME_PARENTS` dropped) survived → **FIXED**. Now red: both cases of `test_blocklist_bare_users_home_parent_below_depth_one` (:420-425).
- Recommended POSIX empty-cwd variant → **FIXED**. `test_empty_cwd_unknown_row_with_posix_real_row_stays_unknown` (:481) and `test_blocklist_slash_root` both go red under both combined empty-guard mutants.
- Note: export test depended on the environment → **FIXED**. :786 passes `allowed_domains=("cyclotron.com",)`. I confirmed it passes with `ALLOWED_EMAIL_DOMAINS=contoso.com` set: `1 passed`.
- Note: NULL-repo test did not assert the source → **FIXED**. :305-306 now assert `(REAL, "timeline")` and `(WRAPPER, "wrapper")`.
- The moved `/mnt/c/dev` case → **NOT FIXED in substance**. See Issue 1.

### What I verified
- **Rung 1, run twice** → ✅ `python -m pytest tests/test_attribute_inheritance.py -q`: `136 passed in 21.20s`, then `136 passed in 20.15s`.
- **Rung 2** → ✅ `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_export_unattributed.py tests/test_invoice.py tests/test_reconcile.py -q`: `116 passed in 15.51s`.
- **Escapes** → ✅ `python -W error` compile of the test file: `escapes ok`.
- **Write fence** → ✅ `git status --short` shows exactly ` M billing/otel/attribute.py`, `?? _goals/unknown-parent-child-inheritance/`, `?? tests/test_attribute_inheritance.py`. I checked at the start and after all mutation work.
  - `git hash-object billing/otel/attribute.py` = `38d2db20fe79911ed9c9c6e49f714958ee527021` (H0).
  - The test file is now `9c6eb369…`.
- **Mutation safety** → ✅ All mutants ran on fresh copies `scratchpad\ev18a` and `scratchpad\ev18b`. The probe asserts `billing.otel.attribute.__file__` is inside the scratchpad. I never edited the repo and ran no git checkout, restore, stash or reset. Both copies were restored to H0 after every mutant.
- **New top-level cases use the non-container name `Cyclotron`, each with a real descendant** → ✅ :429-435. Each is killed by its own rule's mutant (table below).
- **Positive controls for the same shapes** → ✅ for `/mnt/c/dev/wealthspire` and `/c/dev/wealthspire` (:462-463). ⚠️ None for `/volumes/<x>/<a>/<b>` (see Notes).
- **Claim that `/mnt/c/dev` is blocked only by the container name** (17-report.md:8) → ❌ Contradicted. Mutant `s_name_dev` turns nothing red: 136 passed. Probe: under H0, `/mnt/c/dev` with a real `/mnt/c/dev/x/y` row resolves to `unknown`. With only `dev` removed it is still `unknown`. Only with `dev` removed AND mount `k<=2` does it resolve to `github.com/a/real`. It is blocked twice over.

### Mutation table (cycle 2, my own runs)
| Mutant | Red named tests |
|---|---|
| a widen | `test_prefix_lookalike_is_not_a_descendant` |
| b / g direction | `test_reverse_…[False/True]`, `test_preservation_b_…` |
| c blocklist removed | 32 `test_blocklist_*` cases, including the new top-level and bare-parent cases |
| d distinct | `test_two_distinct_qualifying_repos_stay_unknown` |
| e unknown-only | `test_preservation_a_…`, `test_no_unknown_rows_resolves_as_before_the_change` |
| f LIKE | `test_wildcards_in_paths_are_inert[a_b]`, `[a%]` |
| h raw alias / h2 no sanitise | 90 red / 10 red, including the quoted, bracketed and backticked alias tests |
| bl_mount_k2 | `top_level…[/mnt/c/Cyclotron]`, `[/media/x/Cyclotron]`, `[/volumes/disk/Cyclotron]` |
| bl_gitbash_seg | `top_level…[/c/Cyclotron]` |
| z1 `_HOME_PARENTS` dropped | `bare_users_home_parent…[C:\data\Users]`, `[/srv/home]` |
| combined empty guards (both forms) | `test_blocklist_slash_root`, `test_empty_cwd_unknown_row_with_posix_real_row_stays_unknown` |
| s_unc_k3 (UNC top-level `k<=4` → `k<=3`) | `top_level…[\\srv\share\team]` |
| s_mnt_k2 / s_media_k2 / s_volumes_k2 (each prefix separately) | `top_level…[/mnt/c/Cyclotron]` / `[/media/x/Cyclotron]` / `[/volumes/disk/Cyclotron]` |
| s_mnt / s_media / s_volumes prefix dropped | the matching `mount_roots` cases plus the matching top-level case |
| `users` parent only dropped / `home` parent only dropped | `bare…[C:\data\Users]` / `bare…[/srv/home]` |
| onedrive prefix → exact match / visual studio prefix → exact match | `generic_containers[OneDrive…]` / `generic_containers[Visual Studio 2022]` |
| y1 export ignores `resolved_view` | `test_export_build_bills_nate_session_to_the_real_repo` |
| container names `projects` / `desktop` / `work` / `clients` / `temp`, each removed alone | the matching `generic_containers` case |
| **container names `code`, `src`, `source`, `repos`, `dev`, `git`, `github`, `workspace`, `documents`, `downloads`, `library`, `cloudstorage`, `tmp`, `appdata`, each removed alone** | **NOT CAUGHT (136 passed each). Not equivalent:** with the names removed, `C:\Users\x\dev`, `/home/x/dev`, `C:\Users\x\OneDrive - Cyclotron Inc\Code` (the Derek container), `/home/x/src` and `/home/x/repos` each resolve to `github.com/a/real` instead of `unknown` (probes `ev18_probe2.py`, `ev18_probe.py`). `C:\dev` (:442) does not guard `dev` because the `x:/seg` top-level rule also blocks it. |
| z5 view timeline branch uses only the first row's raw repo | NOT CAUGHT; the package lists it as known and unreachable by ingest |

### Issues found
1. **[major]** tests/test_attribute_inheritance.py:441-453 — the container rule is guarded only by `projects`, `desktop`, `work`, `clients`, `temp` and the two prefix rules. Fourteen of the 19 names in `_CONTAINER_NAMES` (`billing/otel/attribute.py:86-90`) can be deleted with the suite still green. That includes `dev` and `code`, the containers in the motivating Nate path (`C:\dev`) and Derek path (`…\OneDrive\Code`).
   - The moved `("/mnt/c/dev", …)` case at :443 is still the same vacuity I flagged in cycle 1: it is blocked by two rules at once, so it cannot fail for the reason it is listed under. The report's rationale for the move (17-report.md:8) is contradicted.
   - Why it matters: deleting a name from the list (for example during a "too strict" tuning pass) would silently bill a `~/dev`, `~/src`, `~/repos` or `OneDrive\Code` container that holds many client repos to whichever single repo appears beneath it. That breaks the strict no-misattribution rule.
   - I did not run per-name mutants in cycle 1, so this gap was already present then and I am reporting it late. The `/mnt/c/dev` contradiction is new in this cycle.

### Notes (non-blocking)
- No positive control for the `/volumes/<x>/<a>/<b>` shape (`/mnt` and `/c` have one at :462-463). An over-blocking `/volumes` regression would go unseen. Not named by any requirement.
- Equivalent mutants (defence in depth, not test gaps): removing `ifnull` from `_norm`, the empty guards alone, the empty-path block alone, the `/root` rule (also covered by `/seg`), `count(*)>0`, and `sid IS NULL`.
- Known non-blocking items, per the package: `/media/<u>/<disk>/proj`, AC5 wording, deny-list residuals, z5.

### Required fixes (if NEEDS FIXES)
- [ ] Add a container test parametrized over every name in `_CONTAINER_NAMES`, written as a literal list in the test rather than imported. Each case should sit at a depth where only the name rule applies, e.g. `("/home/x/<name>", "/home/x/<name>/app")` and/or `(r"C:\Users\x\<Name>", r"C:\Users\x\<Name>\acme")` with mixed case. Each name-removal mutant must turn its case red.
- [ ] Make the `/mnt/c/dev` case block for a single reason. Either move it back under top-level, or replace the container case with a deeper path such as `("/mnt/c/x/dev", "/mnt/c/x/dev/app")`, which only the name rule blocks. Correct the rationale in the report.
- [ ] Re-run rung 1 and rung 2. Record the per-name mutants plus bl_mount_k2, bl_gitbash_seg, z1 and the empty-guard combination, all on a scratch copy, and confirm `git hash-object billing/otel/attribute.py` is still H0.

### Footprint
files_read: 5 (~22000 chars) this cycle, plus 16-context-era files already in context
commands_run: 10

Files: `C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\tests\test_attribute_inheritance.py`. Drivers and probes are `ev18_mut.py`, `ev18_extra.py`, `ev18_probe.py` and `ev18_probe2.py` in `C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\efecdfb4-de1b-4a6f-9f68-641f5525f749\scratchpad\`. The copies `ev18a\` and `ev18b\` have been restored to H0. The old `ev16\` and `ev16b\` copies are still in the scratchpad; I did not remove them (a recursive delete was refused by a safety check, and they are scratch-only).
