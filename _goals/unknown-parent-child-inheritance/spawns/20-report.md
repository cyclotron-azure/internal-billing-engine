**Model (self-reported)**: claude-opus-5-5 (Opus 5.5). The package requested claude-opus-5.

## Verdict: PASS (with notes)
**Score**: 4/5

The last open issue is fixed. Each of the 19 container names, removed on its own, now turns two named tests red: one POSIX case and one mixed-case Windows case. The replaced `/mnt/c/x/dev` case is now blocked only by the `dev` name rule, and the comment on `C:\dev` is accurate.

I re-ran every mutant from cycles 1 and 2 on three fresh scratch copies: required (a)–(h), the earlier survivors, the sibling blocklist mutants and my own extra mutants. Not one survives, apart from the equivalent mutants and z5 the package already lists as known. Rungs 1 and 2 pass and the write fence is intact. What remains is two non-blocking notes.

### Prior issues: fixed or not
- **Cycle 2, Issue 1a** — 14 of 19 container names had no killing test → **FIXED**. All 19 single-name mutants are caught (table below).
- **Cycle 2, Issue 1b** — the `/mnt/c/dev` case was blocked by two rules and the report's rationale was ❌ → **FIXED**.
  - tests/test_attribute_inheritance.py:447 is now `("/mnt/c/x/dev", "/mnt/c/x/dev/wealthspire")`. The comment at :445-446 is true: `s_name_dev` turns `generic_containers[/mnt/c/x/dev]` red.
  - The `C:\dev` comment at :430-431 is true. `C:\dev` goes red under neither `bl_drive_seg` (only `[C:\Cyclotron]` went red) nor `s_name_dev`. It is blocked by two rules and correctly labelled as guarding neither alone.
- **Cycle 1, Issue 1** (bl_mount_k2, bl_gitbash_seg, z1) → **still fixed**; all red again.
- **Cycle 1 notes** (POSIX empty-cwd variant, `allowed_domains` in the export test, NULL-repo source assertion) → **still fixed**; the combined empty-guard and y1 mutants are red.

### What I verified
- **Rung 1, run twice** → ✅ `python -m pytest tests/test_attribute_inheritance.py -q`: `196 passed in 32.64s`, then `196 passed in 36.13s`.
- **Rung 2** → ✅ `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_export_unattributed.py tests/test_invoice.py tests/test_reconcile.py -q`: `116 passed in 16.86s`.
- **Escapes** → ✅ `python -W error` compile of the test file: `escapes ok`.
- **Write fence** → ✅ `git status --short` shows exactly ` M billing/otel/attribute.py`, `?? _goals/unknown-parent-child-inheritance/`, `?? tests/test_attribute_inheritance.py`.
  - `git hash-object billing/otel/attribute.py` = `38d2db20fe79911ed9c9c6e49f714958ee527021` (H0), before and after.
  - The test file is `08b8cfed6ff433d68337228484c3dc0fa61c2a36`, which matches 19-report.
- **Mutation safety** → ✅ I made three FRESH copies of the working tree: `scratchpad\ev20a`, `ev20b`, `ev20c`.
  - The driver asserts the copy's original `attribute.py` hashes to H0 and that its root is in the scratchpad.
  - All three copies were restored to H0 afterwards.
  - The repo was never mutated, and I ran no git checkout, restore, stash or reset.
  - The test-writer ran my drivers in its own copy (`tw19`). I checked the drivers' mutant definitions, then re-ran everything myself.
- **`CONTAINER_NAMES` is a literal list equal to the source vocabulary** → ✅ An AST check shows the literal at :463-467 equals `attribute._CONTAINER_NAMES`, in the same order (19 names). It is not imported.
- **Each per-name case is blocked by exactly the name rule** → ✅ Removing a single name flips both `posix_mid_depth[<name>]` (`/opt/team/<name>`, k=3) and `windows_mid_depth_mixed_case[<name>]` (`D:\work2\<MiXed>`, k=2) to the real repo, so no second rule blocks them.
  - The Windows mixed-case forms really are mixed: `CoDe`, `SrC`, `DeV`, `GitHub`, `CloudsTorage`, `AppdAta`, …
  - The positive control `test_blocklist_container_name_shapes_plain_child_folder_inherits[<name>]` (:502-509, `/opt/team/<name>/acme` and `D:\work2\<Name>\acme`) passes for all 19 under H0.
- **New allowed controls** `/media/x/team/proj` and `/volumes/disk/team/proj` (:519-520) → ✅ pass under H0.

### Mutation table (cycle 3, my runs on fresh copies)
| Mutant | Red named tests |
|---|---|
| Each of the 19 names removed alone: `code`, `src`, `source`, `repos`, `dev`, `git`, `github`, `workspace`, `documents`, `downloads`, `library`, `cloudstorage`, `tmp`, `appdata`, `projects`, `desktop`, `work`, `clients`, `temp` | `test_blocklist_container_name_posix_mid_depth[<name>]` and `test_blocklist_container_name_windows_mid_depth_mixed_case[<name>]` for every name. Also `generic_containers[/mnt/c/x/dev]` for `dev`, `[/home/x/projects]` for `projects`, `[OneDrive…\Desktop]` for `desktop`, `[C:\Users\x\Work]` for `work`, `[C:\Users\x\clients]` for `clients`, `[…\AppData\Local\Temp]` for `temp` |
| bl_names (whole names rule) | 46 cases |
| onedrive prefix → exact match; onedrive rule removed | `generic_containers[OneDrive…]` |
| visual studio prefix → exact match; visual studio rule removed | `generic_containers[Visual Studio 2022]` |
| a widen | `test_prefix_lookalike_is_not_a_descendant` |
| b / g direction | `test_reverse_…[False/True]`, `test_preservation_b_…` |
| c blocklist removed | 70 `test_blocklist_*` cases |
| d distinct | `test_two_distinct_qualifying_repos_stay_unknown` |
| e unknown-only | `test_preservation_a_…`, `test_no_unknown_rows_resolves_as_before_the_change` |
| f LIKE | `test_wildcards_in_paths_are_inert[a_b]`, `[a%]` |
| h raw alias / h2 no sanitise | 128 red / 10 red (the quoted, bracketed and backticked alias tests) |
| bl_mount_k2 | `top_level…[/mnt/c/Cyclotron]`, `[/media/x/Cyclotron]`, `[/volumes/disk/Cyclotron]` |
| bl_gitbash_seg | `top_level…[/c/Cyclotron]` |
| z1, plus `users` dropped alone / `home` dropped alone | `bare_users_home_parent…[C:\data\Users]`, `[/srv/home]`; each half separately |
| combined empty guards (both forms) | `test_blocklist_slash_root`, `test_empty_cwd_unknown_row_with_posix_real_row_stays_unknown` |
| s_unc_k3 | `top_level…[\\srv\share\team]` |
| `/mnt`, `/media`, `/volumes`, each top-level depth tightened separately | the matching `top_level…[*/Cyclotron]` case each |
| `/mnt`, `/media`, `/volumes`, each prefix dropped separately | the matching `mount_roots` case(s) plus the matching top-level case |
| x1 DirectoryAdded / x2 session_id `'unknown'` / x3 NULL event | the matching named test, each |
| x6 / x7 tie-breaks, x17 cwd from a different row | the tie tests |
| x8 / x9 / x10 / x11 normalisation | case-insensitive, trailing-whitespace, trailing-separator and backslash tests (x8 also turns all 19 Windows mixed-case cases red) |
| x12 / x13 first-row fallback, x16 inner join, x18 standalone, z2 / z6 / x15 desktop-scratch, z7 same folder, x14 session scope | the matching named tests (same as cycle 1) |
| bl_tilde, bl_drive, bl_drive_seg, bl_slash_seg, bl_mount, bl_unc, bl_users, bl_home | each class test |
| y1 export ignores `resolved_view` | `test_export_build_bills_nate_session_to_the_real_repo` |
| **NOT CAUGHT** | none among the mutants run (`grep -c "NOT CAUGHT"` over all three outputs = 0) |

I did not re-run the equivalent mutants (x4, x5, the empty-path block alone, the `/root` rule, z3, z4) or z5, which the package lists as known non-blocking.

### Issues found
None blocking.

### Notes (non-blocking)
- The bonus check is absent. `test_container_name_vocabulary_is_distinct_and_complete` (:484-487) checks the literal list (count 19, distinct, lower-case) but never compares it with `attribute._CONTAINER_NAMES`. A name ADDED to the source vocabulary would get no test and nothing would fail. The package already rates this non-blocking. It is minor because no requirement or acceptance criterion names it and it changes no behavior.
- The `_win_case` docstring example at :479 says `'cloudstorage' -> 'CloudStorage'`, but the function returns `'CloudsTorage'`. That is comment text only and changes no behavior, so it is minor. The output is still mixed case, which is what the test needs.
- Known non-blocking items, per the package: AC5 wording, `/media/<u>/<disk>/proj`, deny-list residuals, z5.

### Footprint
files_read: 4 this cycle (~16000 chars): 20-context.md, 19-report.md, the test-file region :426-525, ev18_extra.py. Earlier files are already in context.
commands_run: 9

Files: `C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\tests\test_attribute_inheritance.py`. Mutation outputs are `ev20a_out.txt`, `ev20b_out.txt` and `ev20c_out.txt` in `C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\efecdfb4-de1b-4a6f-9f68-641f5525f749\scratchpad\`. The copies `ev20a\`, `ev20b\` and `ev20c\` are restored to H0. Older scratch copies (`ev16*`, `ev18*`, `tw19`) are left in place.
