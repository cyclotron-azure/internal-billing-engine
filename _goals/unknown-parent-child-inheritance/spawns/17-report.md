**Model (self-reported)**: claude-sonnet-5-5 (Sonnet 5.5)
## Test Task Complete (fix cycle 1)

File: C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\tests\test_attribute_inheritance.py (136 tests, all green). The 129-test first-cycle report stands, except for the changes below.

### Changes this cycle
- `test_blocklist_top_level_folders_under_a_root` now has non-container top-level cases with a real descendant: `/mnt/c/Cyclotron`, `/media/x/Cyclotron`, `/volumes/disk/Cyclotron`, `/c/Cyclotron`.
- `/mnt/c/dev` moved to `test_blocklist_generic_containers`, because only the container name makes it `unknown`.
- New `test_blocklist_bare_users_home_parent_below_depth_one`: `C:\data\Users` and `/srv/home`, each with a real descendant.
- New `test_empty_cwd_unknown_row_with_posix_real_row_stays_unknown`: empty-cwd unknown row plus a real row at `/srv/app/x`.
- Positive controls were already in the file and still pass: `/mnt/c/dev/wealthspire`, `/c/dev/wealthspire` and the other allowed project-level folders inherit.
- `test_export_build_bills_nate_session_to_the_real_repo` now passes `allowed_domains=("cyclotron.com",)` to `export.build`.
- `test_null_repo_effective_row_falls_back_to_first_row_then_wrapper` now asserts the source as well as the repo: `(REAL, "timeline")` and `(WRAPPER, "wrapper")`.

### Mutation table
All mutants ran on a scratchpad COPY of the repo (`mut2\`; `billing.otel.attribute.__file__` resolved into the copy). I did not touch the repo's `attribute.py`, and no git checkout, restore, stash or reset was run. The copy's hash equalled H0 after every restore.

| Mutant | Named red tests |
|---|---|
| bl_mount_k2 (mount top-level `k <= 3` to `k <= 2`) | `test_blocklist_top_level_folders_under_a_root` (3 cases) |
| bl_gitbash_seg (`/[a-z]/*` plus `k = 2` rule removed) | `test_blocklist_top_level_folders_under_a_root` (`/c/Cyclotron` case) |
| z1 (`_HOME_PARENTS` dropped from the names list) | `test_blocklist_bare_users_home_parent_below_depth_one` (2 cases) |
| empty_guards (empty-path block and `_m.n <> ''` guard both removed) | `test_blocklist_slash_root`, `test_empty_cwd_unknown_row_with_posix_real_row_stays_unknown` |
| (a) widen | `test_prefix_lookalike_is_not_a_descendant` |
| (b) direction | `test_reverse_real_parent_unknown_child_stays_unknown`, `test_preservation_b_real_effective_row_with_related_unknown_keeps_repo` |
| (g) direction, alternate form | same tests as (b) |
| (c) blocklist removed | 32 cases across the `test_blocklist_*` tests, including the new bare-home-parent test; `test_blocklist_slash_root` is not among them |
| (d) distinct | `test_two_distinct_qualifying_repos_stay_unknown` |
| (e) unknown-only | `test_preservation_a_real_effective_rows_keep_own_repo`, `test_no_unknown_rows_resolves_as_before_the_change` |
| (f) wildcard | `test_wildcards_in_paths_are_inert` |
| (h) `_fmt` raw alias (crude, 90 red) | includes `test_view_alias_variants_same_values_and_exact_column_list`, `test_view_equals_standalone_expressions` |

### Verification
- Rung 1: `python -m pytest tests/test_attribute_inheritance.py -v` gave 136 passed.
- Rung 2: `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_export_unattributed.py tests/test_invoice.py tests/test_reconcile.py -q` gave 116 passed.
- H0 before and after: 38d2db20fe79911ed9c9c6e49f714958ee527021
- `git status --short`:
```
 M billing/otel/attribute.py
?? _goals/unknown-parent-child-inheritance/
?? tests/test_attribute_inheritance.py
```

### Gaps
- None. No defect found in task 01.

### Footprint
files_read: 3 (~25000 chars)
commands_run: 6
