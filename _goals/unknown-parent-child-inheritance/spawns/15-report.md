**Model (self-reported)**: claude-sonnet-5-5 (Sonnet 5.5)
## Test Task Complete

Created `C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\tests\test_attribute_inheritance.py`. It has 129 test cases (parametrized), all green, using real temp SQLite stores via `tmp_db_path`. The tests insert into both `token_usage` and `cost_usage`, and every `expect()` call asserts both tables. No defect in task 01 was found.

### Test names by requirement
- **Nate / forward-only / reverse / Derek**
  - `test_nate_unknown_ancestor_inherits_real_child_repo`
  - `test_forward_only_datapoint_before_first_row_inherits`
  - `test_reverse_real_parent_unknown_child_stays_unknown[unknown_first False/True]`
  - `test_derek_unrelated_sibling_stays_unknown`
  - `test_derek_dashnoard_with_real_descendant_inherits`
- **Distinct / scope**
  - `test_two_distinct_qualifying_repos_stay_unknown`
  - `test_same_repo_qualifying_twice_inherits`
  - `test_only_unknown_session_stays_unknown`
  - `test_real_row_in_another_session_never_leaks`
  - `test_session_id_literal_unknown_never_inherits`
- **Preservation**
  - `test_preservation_a_real_effective_rows_keep_own_repo` (uses `C:\dev\mono` and `C:\dev\mono\sub`)
  - `test_preservation_b_real_effective_row_with_related_unknown_keeps_repo`
  - `test_preservation_c_no_timeline_uses_wrapper_tag`
  - `test_preservation_c_unknown_row_never_falls_back_to_wrapper_tag`
  - `test_no_unknown_rows_resolves_as_before_the_change` (additional test 4)
  - `test_null_repo_effective_row_falls_back_to_first_row_then_wrapper` (raw INSERT)
- **Normalisation / lookalike / wildcards / same folder**
  - `test_normalisation_is_case_insensitive`
  - `test_normalisation_mixed_separators`
  - `test_normalisation_trailing_separators`
  - `test_normalisation_trailing_forward_slash_and_whitespace`
  - `test_backslash_separator_handling_is_active`
  - `test_prefix_lookalike_is_not_a_descendant`
  - `test_wildcards_in_paths_are_inert[5 paths: _ % [ ? *]`
  - `test_wildcard_characters_match_literally`
  - `test_same_folder_unknown_and_real_inherits`
- **Anchor blocklist**
  - `test_blocklist_drive_root`
  - `test_blocklist_slash_root`
  - `test_blocklist_tilde`
  - `test_blocklist_mount_roots`
  - `test_blocklist_git_bash_drive_root`
  - `test_blocklist_unc_host_and_share`
  - `test_blocklist_home_folders`
  - `test_blocklist_top_level_folders_under_a_root`
  - `test_blocklist_generic_containers`
  - `test_blocklist_allowed_project_folders_inherit`, which includes `/mnt/c/dev/wealthspire` and `/c/dev/wealthspire`
- **Empty / NULL / DirectoryAdded**
  - `test_empty_cwd_unknown_row_stays_unknown`
  - `test_null_cwd_unknown_row_stays_unknown` (raw INSERT)
  - `test_null_cwd_or_event_real_rows_never_raise_or_mis_inherit`
  - `test_directory_added_real_row_does_not_anchor`
  - `test_cwd_changed_real_row_anchors`
- **desktop-scratch**
  - `test_transcript_session_without_qualifying_real_row_is_desktop_scratch`
  - `test_transcript_session_that_inherits_reports_timeline`
- **Tie-breaks (repo-based, both insertion orders)**
  - `test_as_of_exact_tie_real_repo_sorting_above_unknown_wins`
  - `test_as_of_tie_unknown_wins_and_inherits_via_its_own_cwd`
  - `test_unknown_winning_tie_does_not_borrow_real_rows_cwd`
  - `test_first_row_exact_tie_is_resolved_deterministically`
  - `test_first_row_tie_unknown_does_not_borrow_real_rows_cwd`
- **View == standalone (additional test 1)**
  - `test_view_equals_standalone_expressions[token_usage/cost_usage]`
  - `test_standalone_expressions_inherit_nate`
  - `test_standalone_expressions_accept_alias_variants`
- **Cardinality (additional test 2)**
  - `test_view_cardinality_with_tied_and_duplicate_timeline_rows[both tables]`
- **Alias + column list (additional test 3)**
  - `test_view_alias_x_matches_default_on_nate_fixture`
  - `test_view_alias_variants_same_values_and_exact_column_list[16 aliases x 2 tables]`
  - The aliases are `t`, `x`, `r`, `_i`, `_ar`, `rid`, `v`, `i`, `ar`, `_t__i`, `_t__ar`, `"x y"`, `[sp ace]`, a backtick-quoted alias, `"T"` and `TOKEN_USAGE`.
  - These tests assert the same values as the default alias and a column list equal to the table's columns plus the two added.
  - `test_view_embeds_as_subquery_with_outer_alias_collision`
- **Consumer smoke**
  - `test_export_build_bills_nate_session_to_the_real_repo` (`export.build`: all tokens and cost land under the real repo, none under `unknown`)

### Verification
- Rung 1: `python -m pytest tests/test_attribute_inheritance.py -v` gave 129 passed.
- Rung 2: `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_export_unattributed.py tests/test_invoice.py tests/test_reconcile.py -q` gave 116 passed.

### Mutation table
H0 was `38d2db20fe79911ed9c9c6e49f714958ee527021` before the first mutant. The backup is `attribute_H0_38d2db2.py` in the scratchpad. The driver is `mutate.py` in the scratchpad, which restores by copying the backup back in a `finally` block.

| Mutant | Description | Named tests that went red | Restore hash == H0 |
|---|---|---|---|
| a widen | dropped `+ 1` and `\|\| '/'` in the descendant comparison | `test_prefix_lookalike_is_not_a_descendant` (1 failed) | yes |
| b direction | also accept real ANCESTORS (extra `substr` clause) | `test_reverse_real_parent_unknown_child_stays_unknown` (both params), `test_preservation_b_real_effective_row_with_related_unknown_keeps_repo` (3 failed) | yes |
| c blocklist | `OR {blocked}` replaced with `OR 0` | all `test_blocklist_*` blocked-class tests (26 failed): drive_root, tilde, mount_roots, git_bash_drive_root, unc_host_and_share, home_folders, top_level_folders_under_a_root, generic_containers | yes |
| d distinct | dropped `min(repo) = max(repo)`, so it returns `min(repo)` | `test_two_distinct_qualifying_repos_stay_unknown` (1 failed) | yes |
| e unknown-only | non-unknown effective row with 2 or more distinct descendant repos becomes `unknown` (the form the task file specifies) | `test_preservation_a_real_effective_rows_keep_own_repo`, `test_no_unknown_rows_resolves_as_before_the_change` (2 failed) | yes |
| f wildcard | `_x.n LIKE _m.n \|\| '/%'` instead of `substr` | `test_wildcards_in_paths_are_inert` (2 failed) | yes |
| g direction (alternate form) | `instr(_m.n, _x.n \|\| '/') = 1` added, which also accepts ancestors | same tests as (b) (3 failed) | yes |
| h `_fmt` raw alias | `_fmt` returns the raw alias for `ar` and `i` | 83 failed, including `test_view_alias_variants_same_values_and_exact_column_list`, `test_view_equals_standalone_expressions`, plus most scenario tests | yes |

Mutant (h) is crude. It breaks nearly everything, because the inner names then collide with the default alias `t`. It was not narrowed to break only the `_i` and quoted-alias tests.

### H0 and tree
- H0 before: `38d2db20fe79911ed9c9c6e49f714958ee527021`
- H0 after (after the last restore and after the final runs): `38d2db20fe79911ed9c9c6e49f714958ee527021`
- `git status --short`:
```
 M billing/otel/attribute.py
?? _goals/unknown-parent-child-inheritance/
?? tests/test_attribute_inheritance.py
```
- No `git checkout`, `restore`, `stash` or `reset` was run.

### Gaps
- Nothing in the task file was left untested. I did not add a test for `"\\\\"`-style double-backslash escaping beyond `test_backslash_separator_handling_is_active`, which would fail if the SQL literal were empty or doubled.
- Mutant (h) is the crude form described above.

### Footprint
files_read: 9 (~120000 chars)
commands_run: 7
