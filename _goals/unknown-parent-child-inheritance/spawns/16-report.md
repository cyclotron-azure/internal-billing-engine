**Model (self-reported)**: claude-opus-5-5 (Opus 5.5). The package requested claude-opus-5.

## Verdict: NEEDS FIXES
**Score**: 3/5
**failure_class:** implementation

The file is strong. Every Requirement bullet in 02-tests.md has a named test that passes, and all 8 required mutants (a)–(h) turn named tests red. It still needs fixes: three blocklist rules from task 01 (the top-level folder under a Git-Bash drive, the top-level folder under a mount root, and the bare `…/users` / `…/home` parents) have no test that can fail. One parametrize case labelled "top-level" is `unknown` for a different reason (it is a container name). That is exactly the vacuity the package asked me to flag. I proved all three gaps with mutants that survive and with concrete paths that get misattributed.

### What I verified
- **Rung 1** → ✅ I ran `python -m pytest tests/test_attribute_inheritance.py -q` in the repo: `129 passed in 14.54s`. A second run with `-p no:randomly`: `129 passed in 15.32s`. pytest-randomly is not installed.
- **Rung 2** → ✅ `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_export_unattributed.py tests/test_invoice.py tests/test_reconcile.py -q`: `116 passed in 11.99s`.
- **AC4 tree and fence** → ✅ `git status --short` shows exactly ` M billing/otel/attribute.py`, `?? _goals/unknown-parent-child-inheritance/`, `?? tests/test_attribute_inheritance.py`. I checked at the start and again after all mutation work.
  - `git hash-object billing/otel/attribute.py` = `38d2db20fe79911ed9c9c6e49f714958ee527021` (H0) both times.
  - The test file hash is `e00ff353…`.
  - export.py and test_attribute.py are not modified.
- **AC2 hashes** → ✅ The final hash equals H0. I could not see the test-writer's own mutation history; their table matches my independent re-run (below).
- **Mutation safety** → ✅ All mutants ran on copies at `scratchpad\ev16` and `scratchpad\ev16b`.
  - Under pytest, `billing.otel.attribute.__file__` resolves to `...scratchpad\ev16\billing\otel\attribute.py`. The baseline in the copy was 129 passed.
  - I never edited the repo and ran no git checkout, restore, stash or reset.
  - The first driver (`ev16_mut.py`) hit its background time limit after `bl_mount`. I ran the remaining blocklist mutants on `ev16b`, then copied the repo's file back over both scratch copies (hash = H0).
- **Windows path escapes** → ✅ Every backslash path is a raw string or properly escaped (`"C:\\dev\\proj\\"`, `"C:\\"`). `python -W error` compile of the file: no invalid-escape warning.
- **Both tables** → ✅ `expect()` (tests/test_attribute_inheritance.py:100-104) asserts every case on both `token_usage` and `cost_usage`. `inherits()` (:121-123) asserts the two tables agree. `dp()` (:83-84) inserts into both.
- **Consumer smoke** → ✅ `test_export_build_bills_nate_session_to_the_real_repo` really calls `export.build`. Export mutant y1 (export.py ignores `resolved_view` and uses the raw repo) turns it red.
- **Determinism** → ✅ Fixed `BASE` datetime, `tmp_db_path`, no network, no ordering on dicts or sets (results are keyed by ts or ordered by `dp_key`). Two caveats are in Notes.
- **NULL cwd uses a raw INSERT** → ✅ :469-481, and the test asserts one row with `cwd IS NULL` exists.
- **Requirements walk** (✅ = present and passing; sensitivity is from the mutation table):

| Requirement | Test(s) | Status |
|---|---|---|
| Nate | `test_nate_unknown_ancestor_inherits_real_child_repo` :130 | ✅ |
| Forward-only | `test_forward_only_datapoint_before_first_row_inherits` :139 (red under x12) | ✅ |
| Reverse stays unknown | `test_reverse_real_parent_unknown_child_stays_unknown[2]` :148; `gen` is not blocked | ✅ |
| Derek | `test_derek_unrelated_sibling_stays_unknown` :164, plus positive control :174 | ✅ |
| Distinct / same repo | :183, :192 | ✅ |
| Session scope | :202, :210 (red under x14) | ✅ |
| Preservation (a)/(b)/(c) | :231 (`C:\dev\mono`), :243, :254, :260 | ✅ |
| Normalisation | :313, :317, :321, :325, :329 | ✅ |
| Prefix lookalike | :335 | ✅ |
| Wildcards inert, plus literal-match controls | :346 (5 cases), :351 | ✅ |
| Same folder | :355 (red under z7) | ✅ |
| Blocklist, one named test per class plus ALLOWED set | :377-454; the full 01 BLOCKED/ALLOWED example list is covered, including `/mnt/c/dev/wealthspire` and `/c/dev/wealthspire` | ✅ for the listed examples; see Issue 1 |
| Empty / NULL cwd | :461, :469 | ✅ (see Notes) |
| DirectoryAdded vs CwdChanged | :503, :510 | ✅ |
| session_id `'unknown'` | :220 | ✅ |
| desktop-scratch | :521, :529 | ✅ |
| Alias `x` | :702 | ✅ |
| As-built additions: view == standalone, cardinality, alias + column list (16 aliases including quoted, bracketed, backticked), no-behavior-change, repo-based tie-breaks | :653, :681, :720, :267, :544-595 | ✅ |

### Mutation table (my own re-run, on the scratch copy)
| Mutant | Red named tests |
|---|---|
| a widen | `test_prefix_lookalike_is_not_a_descendant` |
| b direction (ancestor `substr`) | `test_reverse_…[False/True]`, `test_preservation_b_…` |
| g direction (`instr`) | same 3 as (b) |
| c blocklist removed | 26 `test_blocklist_*` cases (not `slash_root`; `/` normalises to `''`, which the `_m.n <> ''` guard catches) |
| d distinct → min | `test_two_distinct_qualifying_repos_stay_unknown` |
| e unknown-only (two or more distinct descendant repos → unknown on real rows) | `test_preservation_a_…`, `test_no_unknown_rows_resolves_as_before_the_change` |
| f LIKE | `test_wildcards_in_paths_are_inert[a_b]`, `[a%]` |
| h `_fmt` raw alias (crude) | 83 tests, including `test_view_alias_variants_…[_i-*]` |
| h2 `_fmt` without sanitising (narrow) | `test_view_alias_variants_…["x y"/[sp ace]/`bq`/"T"]`, `test_standalone_expressions_accept_alias_variants["x y"/[sp ace]]` |
| x1 DirectoryAdded gate removed | `test_directory_added_real_row_does_not_anchor` |
| x2 session_id `'unknown'` guard removed | `test_session_id_literal_unknown_never_inherits` |
| x3 `ifnull(event,'')` → raw event | `test_null_cwd_or_event_real_rows_never_raise_or_mis_inherit` |
| x6 / x7 as-of / first tie-break flipped | `test_unknown_winning_tie_…[2]` / `test_first_row_tie_unknown_…[2]` |
| x8 `lower()` removed | `test_normalisation_is_case_insensitive`, plus 10 more |
| x9 trim removed / x10 rtrim `'/'` removed | `…trailing_forward_slash_and_whitespace` / plus `…trailing_separators` |
| x11 backslash replace disabled | `test_backslash_separator_handling_is_active`, plus 25 more |
| x12 / x13 first-row fallback removed (view / standalone) | forward-only and first-tie tests, `test_view_equals_standalone_expressions` / view == standalone |
| x14 session scope removed | `test_real_row_in_another_session_never_leaks` |
| x15 / z2 desktop-scratch keyed on raw repo (view / standalone) | `test_transcript_session_that_inherits_reports_timeline` / `test_view_equals_standalone_expressions` |
| z6 desktop-scratch branch moved second | `test_transcript_session_without_qualifying_real_row_is_desktop_scratch` |
| x16 LEFT JOIN → JOIN | cardinality, `preservation_c_no_timeline`, view == standalone |
| x17 cwd taken from a different tied row | `test_unknown_winning_tie_does_not_borrow_real_rows_cwd[2]` |
| x18 standalone without inheritance | `test_standalone_expressions_inherit_nate[2]` |
| z7 same-folder equality removed | `test_same_folder_unknown_and_real_inherits` |
| bl_tilde, bl_drive, bl_drive_seg, bl_slash_seg, bl_mount, bl_unc, bl_users, bl_home, bl_names, bl_onedrive, bl_vs | each red in its class test |
| combined: empty-block plus both empty guards removed | only `test_blocklist_slash_root` (see Notes) |
| **bl_gitbash_seg** (`/<letter>/seg` rule removed) | **NOT CAUGHT; non-equivalent** |
| **bl_mount_k2** (mount top-level `k<=3` → `k<=2`) | **NOT CAUGHT; non-equivalent** |
| **z1** `_HOME_PARENTS` dropped from the names list | **NOT CAUGHT; non-equivalent** |
| Not caught, equivalent (defence in depth): x4 `ifnull` removed from `_norm`, x5 empty guards, bl_empty alone, bl_root_home (`/root` is also `/seg`), z3 `count(*)>0`, z4 `sid IS NULL` | equivalent |
| z5 view `timeline` branch uses only the first row's raw repo | NOT CAUGHT; differs only with a NULL-repo first row, which ingest cannot produce |

Concrete proof that the three bold mutants are not equivalent (`scratchpad\ev16_probe.py`): under H0, `/c/Cyclotron`, `/mnt/c/Cyclotron` and `C:\data\Users`, each with a real descendant row, resolve to `unknown`. With the mutants applied, all three resolve to `github.com/a/real`.

### Issues found
1. **[major]** tests/test_attribute_inheritance.py:424 and :399-454 — blocklist rules with no test that can kill them.
   - The case `("/mnt/c/dev", "/mnt/c/dev/wealthspire")` in `test_blocklist_top_level_folders_under_a_root` is `unknown` because `dev` is a container name, not because of the top-level-under-mount rule it is listed under. It cannot fail if that rule regresses (bl_mount_k2 survives).
   - No test covers a top-level folder under a Git-Bash drive (`/<letter>/seg`; bl_gitbash_seg survives).
   - No test covers a bare `…/users` / `…/home` parent below depth 1 (z1 survives).
   - Why it matters: these are task 01 BLOCKED rules 2 and 3 (01-attribute-inheritance.md:75-79). A regression would silently bill a WSL or Git-Bash `Cyclotron` top-level folder (the same class as `C:\Cyclotron`) to whichever single client repo sits under it. That breaks the strict no-misattribution rule.

### Notes (non-blocking)
- `test_empty_cwd_unknown_row_stays_unknown` (:461) seeds a Windows real path (`NATE_R`). If both the empty-path block and the `_m.n <> ''` guard were removed, an empty unknown cwd would inherit from any POSIX `/…` real row, and this test would stay green. Only `test_blocklist_slash_root` catches that. A POSIX real-row variant would make the empty-cwd test meaningful by itself.
- `test_blocklist_slash_root` passes because `/` normalises to `''` (empty-path rule), not because of a separate `/` rule. That is acceptable as an outcome test.
- `test_export_build_bills_nate_session_to_the_real_repo` reads `ALLOWED_EMAIL_DOMAINS` from the process environment because it does not pass `allowed_domains=`. A developer env without `cyclotron.com` makes it fail (loudly, not as a false pass). Also, `export.build` stamps `generated_at` from the real clock, which is not asserted.
- `test_null_repo_effective_row_falls_back_to_first_row_then_wrapper` asserts only `resolved_repo`, not `attribution_source`, so z5 survives. That path cannot occur via ingest.
- The test-writer's mutant (h) is crude (83 red). My narrower h2 confirms the quoted-alias tests are sensitive on their own.
- The report's "26 failed" for mutant (c) leaves out `slash_root` without saying why. The reason is the empty-guard redundancy above.

### Required fixes (if NEEDS FIXES)
- [ ] In `test_blocklist_top_level_folders_under_a_root`, replace or add to `("/mnt/c/dev", …)` with a non-container top-level folder under a mount, e.g. `("/mnt/c/Cyclotron", "/mnt/c/Cyclotron/repo")`. It must go red under the `k <= 3` → `k <= 2` mutant.
- [ ] Add a Git-Bash top-level case, e.g. `("/c/Cyclotron", "/c/Cyclotron/repo")`. It must go red when the `/[a-z]/*` and `k = 2` part is removed.
- [ ] Add a bare home-parent case below depth 1, e.g. `(r"C:\data\Users", r"C:\data\Users\proj")` or `("/srv/home", "/srv/home/proj")`. It must go red when `_HOME_PARENTS` is dropped from the names list.
- [ ] (Recommended) Add a POSIX-real-row variant of the empty-cwd test, e.g. unknown `''` with real `/srv/app/x`.
- [ ] Re-run rung 1 and rung 2, record the three new mutants turning named tests red (on a scratch copy), and confirm `git hash-object billing/otel/attribute.py` is still H0.

### Footprint
files_read: 9 (~95000 chars)
commands_run: 14

Files: `C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\tests\test_attribute_inheritance.py`. My mutation drivers and probe are `ev16_mut.py`, `ev16b_mut.py` and `ev16_probe.py` in `C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\efecdfb4-de1b-4a6f-9f68-641f5525f749\scratchpad\`. The scratch copies `ev16\` and `ev16b\` have been restored to H0.
