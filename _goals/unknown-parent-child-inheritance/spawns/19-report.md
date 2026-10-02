**Model (self-reported)**: claude-fable-5-1 (Fable 5.1)
## Test Task Complete (fix cycle 2, task 02)

File changed (only write): `C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\tests\test_attribute_inheritance.py` (now `08b8cfed…`, still untracked). `billing/otel/attribute.py` in the repo was never touched; no git checkout/restore/stash/reset was run.

### Tests added / changed
Added (60 new cases, 136 -> 196):
- `CONTAINER_NAMES` literal list of the 19 names (not imported), `POSIX_CONTAINER_SHAPE = "/opt/team/{}"`, `WIN_CONTAINER_SHAPE = "D:\\work2\\{}"`, `_win_case()` mixed-case helper.
- `test_container_name_vocabulary_is_distinct_and_complete` (19 distinct lower-case names).
- `test_blocklist_container_name_posix_mid_depth[<name>]` x19: `/opt/team/<name>` with real `/opt/team/<name>/app` -> unknown (k=3, no mount prefix, no other rule applies).
- `test_blocklist_container_name_windows_mid_depth_mixed_case[<name>]` x19: `D:\work2\<MixedCase>` with real `…\acme` -> unknown (k=2, not drive top-level).
- `test_blocklist_container_name_shapes_plain_child_folder_inherits[<name>]` x19: positive control, `/opt/team/<name>/acme` and `D:\work2\<Name>\acme` with real descendants -> REAL.
Changed:
- `test_blocklist_generic_containers`: the vacuous `("/mnt/c/dev", …)` replaced by `("/mnt/c/x/dev", "/mnt/c/x/dev/wealthspire")` (depth 4, mount k<=3 rule does not apply; comment states the single rationale). `C:\dev` moved out of this test into `test_blocklist_top_level_folders_under_a_root` with a comment that it is blocked by both the top-level rule and the `dev` name, so it guards neither alone.
- `test_blocklist_allowed_project_folders_inherit`: added positive controls `("/media/x/team/proj", …)` and `("/volumes/disk/team/proj", …)` (requirement 3).

### Mutation table (all on scratch copy `scratchpad\tw19`, driver `ev18_mut.py` + `ev18_extra.py` with `EVROOT=tw19`; copy's `billing.otel.attribute.__file__` verified inside the scratchpad; copy restored to H0 after the run)
Per-name (each removed alone; every one caught):
| mutant | red named test(s) |
|---|---|
| s_name_code | `container_name_posix_mid_depth[code]`, `container_name_windows_mid_depth_mixed_case[code]` |
| s_name_src | `…posix[src]`, `…windows[src]` |
| s_name_source | `…posix[source]`, `…windows[source]` |
| s_name_repos | `…posix[repos]`, `…windows[repos]` |
| s_name_projects | `…posix[projects]`, `…windows[projects]`, `generic_containers[/home/x/projects]` |
| s_name_dev | `…posix[dev]`, `…windows[dev]`, `generic_containers[/mnt/c/x/dev]` |
| s_name_git | `…posix[git]`, `…windows[git]` |
| s_name_github | `…posix[github]`, `…windows[github]` |
| s_name_workspace | `…posix[workspace]`, `…windows[workspace]` |
| s_name_desktop | `…posix[desktop]`, `…windows[desktop]`, `generic_containers[OneDrive…\Desktop]` |
| s_name_documents | `…posix[documents]`, `…windows[documents]` |
| s_name_downloads | `…posix[downloads]`, `…windows[downloads]` |
| s_name_library | `…posix[library]`, `…windows[library]` |
| s_name_cloudstorage | `…posix[cloudstorage]`, `…windows[cloudstorage]` |
| s_name_work | `…posix[work]`, `…windows[work]`, `generic_containers[C:\Users\x\Work]` |
| s_name_clients | `…posix[clients]`, `…windows[clients]`, `generic_containers[C:\Users\x\clients]` |
| s_name_temp | `…posix[temp]`, `…windows[temp]`, `generic_containers[…\AppData\Local\Temp]` |
| s_name_tmp | `…posix[tmp]`, `…windows[tmp]` |
| s_name_appdata | `…posix[appdata]`, `…windows[appdata]` |

Other mutants re-run:
| mutant | red named test(s) |
|---|---|
| a_widen | `test_prefix_lookalike_is_not_a_descendant` |
| b_direction / g_direction_instr | `test_reverse_real_parent_unknown_child_stays_unknown[False/True]`, `test_preservation_b_…` |
| c_blocklist | 70 `test_blocklist_*` cases (incl. all 38 new per-name cases) |
| d_distinct_min | `test_two_distinct_qualifying_repos_stay_unknown` |
| e_unknown_only | `test_preservation_a_…`, `test_no_unknown_rows_resolves_as_before_the_change` |
| f_like | `test_wildcards_in_paths_are_inert[a_b]`, `[a%]` |
| h_fmt_raw_alias | 128 red, incl. alias-variant tests |
| bl_mount_k2 | `top_level…[/mnt/c/Cyclotron]`, `[/media/x/Cyclotron]`, `[/volumes/disk/Cyclotron]` |
| bl_gitbash_seg | `top_level…[/c/Cyclotron]` |
| z1_no_home_parents | `bare_users_home_parent…[C:\data\Users]`, `[/srv/home]` |
| combo_empty_unguarded (both forms) | `test_blocklist_slash_root`, `test_empty_cwd_unknown_row_with_posix_real_row_stays_unknown` |
| s_mnt_k2 / s_media_k2 / s_volumes_k2 | matching `top_level…` case each |
| s_volumes_dropped | `mount_roots[/volumes/disk]`, `top_level…[/volumes/disk/Cyclotron]` |
| y1_export_raw_repo | `test_export_build_bills_nate_session_to_the_real_repo` |

Full raw output: `scratchpad\tw19_mut_out.txt`.

### Verification
- Rung 1: `python -m pytest tests/test_attribute_inheritance.py -q` -> 196 passed in 21.91s
- Rung 2: `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_export_unattributed.py tests/test_invoice.py tests/test_reconcile.py -q` -> 116 passed in 11.53s
- `python -W error` compile of the test file -> escapes ok
- H0 before: `38d2db20fe79911ed9c9c6e49f714958ee527021`; H0 after: `38d2db20fe79911ed9c9c6e49f714958ee527021` (unchanged)
- `git status --short`: ` M billing/otel/attribute.py`, `?? _goals/unknown-parent-child-inheritance/`, `?? tests/test_attribute_inheritance.py`

### Gaps / notes
- No defects found in task 01; all 19 names behave as the rule states, in both POSIX and mixed-case Windows shapes.
- The new scratch copy `scratchpad\tw19` (billing/ + tests/) was left in place (restored to H0); older copies `ev16*`, `ev18a/b` untouched.
- Not done: nothing required was skipped.

### Footprint
files_read: 6 (~72000 chars) — 19-context.md, 18-report.md, attribute.py, test_attribute_inheritance.py, ev18_mut.py, ev18_extra.py (plus grep of conftest.py and head of ev18_probe.py)
commands_run: 9
