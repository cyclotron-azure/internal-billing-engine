**Model (self-reported)**: claude-opus-5-5 (Opus 5.5). The context package requested claude-opus-5.

VERDICT: NEEDS REVISION
**Score**: 3/5
**failure_class:** implementation (the goal and task authoring is sound in structure, but task 01's label spec has privacy and edge-case gaps)

The structure holds up: every Discovery decision maps to a task, the write sets are disjoint, the dependencies form a linear DAG (01→02→03→04), eval_depth choices are justified, the contract comes first, and every acceptance criterion names a verification method. The claims about the real code check out. But task 01's label algorithm, followed exactly, still lets a scratchpad slug, a username and a OneDrive org name into `unattributed_project`. That contradicts goal.md:39-41 and success criterion 5 (goal.md:70-71). It also has undefined behaviour for zero-segment cwds, which could crash the whole lake export.

### What I verified
- `attribute.resolved_view()` exposes an `attribution_source` column that export can group on → ✅ Verified. See attribute.py:107-109. I also built the real `SCHEMA` in an in-memory sqlite3 database and ran `WITH r AS (resolved_view('cost_usage')) … GROUP BY d,resolved_repo,model,user_email,attribution_source,session_id`. It returned separate rows `absent`/s1/1.0 and `timeline`/s2/2.0.
- Appending the new fields after `generated_at` keeps tests/test_export.py passing → ✅ Verified by reading. Every header assertion compares against the live `export.SUMMARY_FIELDS`/`LINE_FIELDS` (test_export.py:103,107,195-196,223-224), and nothing hardcodes a column count. The seeded unknown session (conftest.py:551-559) resolves to `absent` with no timeline, so it does not disturb the other assertions. Baseline run: `python -m pytest tests/test_export.py tests/test_attribute.py tests/test_invoice.py -q` → `25 passed in 3.13s`. I could not run the tests after the change because nothing is implemented yet (⚠️ for post-change).
- Task 01's worked examples come out as stated → ✅ Verified. I traced each one by hand and then with a prototype of the spec, run through python on stdin with no files written. All nine match: Dashnoard ×3, ai-presales-agent-main, scratchpad, home, orbit, `""` ×2.
- `cwd` is never NULL in the timeline → ✅ Verified. otel_store.py:714 stores `cwd or ""`, and deploy/claude-repo-tag.py:84-86 drops events with no cwd.
- The single ordered SELECT is index-backed → ✅ Verified (`ix_timeline_session(session_id, ts)`, otel_store.py:82).
- The Fabric notebook tolerates the appended columns → ✅ Verified. It uses `inferSchema` plus `overwriteSchema` (fabric/refresh_billing_tables.py:20-27).
- The scheduler uses the unchanged `build_and_enqueue` signature → ✅ Verified (scheduler.py:76).
- fabric/README.md is out of step with the real CSV headers → ✅ Verified. Line 42 says `bill_name` where the header is `repo`. Line 43 says `bill_name, repo` where the header is `repo, repo_key`, so the lineitems list is wrong in two places, not the one goal.md:51-52 describes. Task 03's "match exactly" requirement still covers both.
- Ownership: disjoint writes, DAG, single owner, contract-first, eval_depth → ✅ Verified from the ownership blocks in all four task files.
- Discovery coverage → ✅ Verified. Each item maps to 01, 02 or 03, or to a goal.md constraint or phase setting.
- Referenced skills and files exist (test-ladder, python-performance-optimization, python-testing-patterns, tests/COVERAGE_MAP.md), and project_label.py is correctly absent → ✅ Verified with `ls`.

### Issues found
1. **[major] Privacy: a scratchpad slug, username or org name can leak through Claude directories that have no `scratchpad` segment.** Location: 01-project-label.md:61, 84-88 and 69-74.
   - **What is wrong:**
     - The scratchpad test runs only on the start folder, and only when a literal `scratchpad` segment is present.
     - The hidden-segment rule only applies while skipping down from the chosen root. It never checks segments above the root.
     - Following the spec exactly (traced):
       - `C:\Users\SumitBhatia\.claude\projects\C--Users-SumitBhatia-OneDrive---Cyclotron-Inc-proj` → `local:C--Users-SumitBhatia-OneDrive---Cyclotron-Inc-proj`. `projects` counts as a container, so the slug becomes the root, leaking the username and the org folder.
       - `...\AppData\Local\Temp\claude\<slug>\<session-id>` → `local:<session-id>`.
       - `...\Temp\claude\<slug>` → `local:<slug>`.
   - **Why it matters:** this breaks goal.md:39-41 ("the slug never leaks") and success criterion 5. Acceptance criterion 4 (01:119-120) only checks the worked examples, so it would not catch this.
   - **Fix:**
     - Make `is_scratchpad` (or a new frozen rule) return true for any cwd with a `.claude` segment, or a `claude` segment under `Temp`/`tmp`, whether or not `scratchpad` is present.
     - Treat a hidden segment anywhere at or above the root as disqualifying.
     - Add these three paths as worked examples.
2. **[major] Privacy: OneDrive org-folder variants are not covered.** Location: 01-project-label.md:70-72.
   - **What is wrong:** the only matches are `OneDrive` exactly and the prefix `OneDrive - `.
     - The macOS layout `/Users/derek/Library/CloudStorage/OneDrive-CyclotronInc` → `local:OneDrive-CyclotronInc` (traced).
     - A SharePoint-synced library root `C:\Users\Derek\Cyclotron Inc` → `local:Cyclotron Inc`.
   - **Why it matters:** success criterion 5 (goal.md:70) says no cell contains `OneDrive`.
   - **Fix:**
     - Make any segment that starts with `onedrive` (case-insensitive) ineligible.
     - Add a final guard that returns `HOME_LABEL` if the label still contains `onedrive`.
     - Ask the user whether the SharePoint sync root (the segment directly after the username) should also be ineligible.
     - Add worked examples.
3. **[major] Zero-segment cwds are ambiguous and can crash the export.** Location: 01-project-label.md:59-64.
   - **What is wrong:** `path_segments` returns `[]` for `C:\`, `/`, `~` and `\\host\share`. The ancestor rule ("its last segment") is then undefined, both when such a cwd appears in history and when it is the start folder. A worker could resolve this in three ways:
     - raise `IndexError`, which would propagate through `load_session_labels` → `export.build()` and kill every lake sync;
     - return `HOME_LABEL`, which is the natural reading: my prototype gives `local:(home)` for a Sumit project session after one `cd C:\`;
     - ignore the row.
   - A single `cd C:\Cyclotron` likewise relabels the session as `local:Cyclotron`.
   - A whitespace-only segment gives a bare `local:` (01:77-79).
   - **Fix:**
     - Specify that zero-segment cwds are ignored by the ancestor rule, and that a zero-segment start folder gives `HOME_LABEL`.
     - Require that `root_label` never raises and never returns a bare prefix.
     - Add worked examples.
4. **[major] Projects that use a `src` folder get mislabelled.** Location: 01-project-label.md:65-74.
   - **What is wrong:**
     - `C:\Cyclotron\proj\src` gives `local:(home)`. `src` is the last segment, so there is no container candidate; the ancestor candidate `src` is ineligible, and skipping deeper runs past the start folder.
     - `C:\Cyclotron\proj\src\components\ui` gives `local:components`.
   - **Why it matters:** this follows goal.md:31-34 to the letter but defeats the goal's purpose (goal.md:10-11, "what project"). A real project reported as the home folder is actively misleading. A worker cannot fix it without departing from the spec, so it is a user decision.
   - **Fix:**
     - Add a fallback: when skipping deeper finds nothing eligible, walk up to the nearest eligible ancestor.
     - Or only treat a container segment as one when it sits at or above the home or drive level.
     - Confirm the choice with the user and add both shapes as worked examples.
5. **[minor] Success criterion 5 is broader than intended.** Location: goal.md:70-71 (inherited by 04-tests.md:71-72).
   - **What is wrong:** "No exported cell contains … `Users`, a username segment, `OneDrive`" would be broken by legitimate `repo`/`repo_key` values (for example `users-api`) and by `user_email`, which already carries the person's name.
   - **Why only minor:** the test writer controls the seed data. But the final audit applies success criteria literally.
   - **Fix:** limit the criterion to the `unattributed_project` and `attribution_source` cells.
6. **[minor] Parts of the before/after comparison cannot hold as written.** Location: 02-export-breakdown.md:76-81 and goal.md:60-62.
   - **What is wrong:**
     - `generated_at` differs between two runs (export.py:98), so "match exactly" / "identical" cannot hold.
     - A copy of the pre-change export.py in the scratchpad will not run as-is, because it uses relative imports (export.py:29-31).
   - **Fix:**
     - Say "excluding `generated_at`", or pin `_now_iso`.
     - Name the method: `git show HEAD:billing/otel/export.py` (HEAD matches the working tree) into a scratch package with absolute imports.
7. **[minor] Task 03's class meanings are imprecise against the code.** Location: 03-readme-columns.md:37-40.
   - **What is wrong:**
     - `no_remote` is described as "wrapper ran outside a git repo". Per attribute.py:38 it means the directory had no git remote, and a local repo with no remote counts too, which is exactly the Derek/Sumit case.
     - `desktop-scratch` is described as "desktop session". The branch actually keys on `usage_source='transcript'` (attribute.py:88), which also covers the cli and VS Code transcript backfill (fabric/README.md:51-57).
     - `wrapper` can never land on a split row. The wrapper branch needs `t.repo != 'unknown'` (attribute.py:93-94), and `resolved_repo` is then `t.repo` (attribute.py:69).
   - **Fix:** correct the wording, and say that `wrapper` is not expected on unknown rows.
8. **[minor] Task 04 does not state rewrite semantics per file.** Location: 04-tests.md:31-33.
   - **What is wrong:** the block declares `rewrite_semantics: whole-file`, and targeted-insertion for COVERAGE_MAP.md appears only in a comment. The criteria require a per-file statement.
   - **Fix:** use a per-file map.
9. **[minor] Task 03 and Phase 6 both claim the same docs work.** Location: 03-readme-columns.md:16-18, 51-52 and goal.md:51-52.
   - **What is wrong:** task 03 owns README.md and fabric/README.md, which are Phase 6 align-docs surfaces (align-docs SKILL.md:49). goal.md assigns the fabric drift fix to Phase 6, and task 03 also does it.
   - **Why only minor:** the work is serialized, so there is no concurrent write.
   - **Fix:** say who owns the drift fix, so Phase 6 does not redo it.
10. **[minor] Grouping by `attribution_source` adds query cost.** Location: 02-export-breakdown.md:59-62.
   - **What is wrong:** grouping by `attribution_source` makes SQLite evaluate the CASE expression (attribute.py:88-91: `resolved_repo`, `_AS_OF`, `_FIRST`) for every datapoint in both tables. Today the export does not reference that column, so only `resolved_repo` is evaluated. That adds roughly three correlated subqueries per row, and nothing in task 02 limits the cost.
   - **Fix:** use `CASE WHEN resolved_repo='unknown' THEN attribution_source END` and group by `session_id` only for unknown rows. Capture a timing comparison.
11. **[minor] The username guard misses some profile layouts.** Location: 01-project-label.md:80-81.
   - **What is wrong:** it misses 8.3 short-name profiles (`C:\Users\ZANECH~1\…`, visible in this environment's own scratchpad path) and home folders outside `Users`/`home` (`/root`, `D:\derek`).
   - **Why only minor:** low real-world impact.
12. **[minor] Risk coverage leaves two points unstated.** Location: goal.md:96-106.
   - **What is wrong:**
     - There is no rollback note. Reverting export.py is enough, because the notebook's `overwriteSchema` drops the columns on the next run.
     - The goal widens who sees folder-derived names: from billing admins (client-package/INSTRUCTIONS.md:78, configure.py:151) to Power BI audiences. The consent notice does cover cwd collection.
   - **Fix:** add one line for each to the goal.

### Required fixes
- [ ] 01: Return `SCRATCHPAD_LABEL` for any path under `.claude` or `Temp|tmp\claude`, with or without `scratchpad`. Treat a hidden segment at or above the root as disqualifying. Add worked examples for `.claude\projects\<slug>`, `Temp\claude\<slug>` and `Temp\claude\<slug>\<session-id>`.
- [ ] 01: Make any `OneDrive*` segment ineligible (case-insensitive), with a final `onedrive` guard. Get the user's decision on SharePoint sync roots. Add a macOS CloudStorage worked example.
- [ ] 01: Define behaviour for zero-segment cwds, both in history and as the start folder, and for whitespace-only segments. Require that `root_label` never raises. Add worked examples.
- [ ] 01: Get the user's decision on the in-project `src` shapes (`proj\src` → currently `local:(home)`, `proj\src\components\ui` → `local:components`). Encode it as a rule plus worked examples.
- [ ] 01: Extend acceptance criterion 4's privacy check beyond the worked examples to all the paths above.
- [ ] goal/04: Limit success criterion 5 and task 04's privacy test to the new-column cells.
- [ ] 02: Say "excluding `generated_at`" in acceptance criterion 2, and name the method for running the pre-change copy.
- [ ] 03: Correct the `no_remote`, `desktop-scratch` and `wrapper` wording.
- [ ] 04: State rewrite semantics per file. goal/03: state who owns the fabric drift fix.

### Devil's Advocate
1. **Steelman alternative:** export a salted hash of the session's start cwd, plus a whitelist of known-safe root names, instead of a heuristic walk-up. No path segment could leak, because nothing derived from a raw segment ever ships unless it has been vetted.
2. **Load-bearing assumptions:**
   - The container list (`src`, `projects`, `code`…) separates "outer" from "in-project" folders. It does not (finding 4).
   - The `scratchpad` segment is the only marker of a Claude-internal directory. It is not (finding 1).
   - "Per session root" is the right unit. A session that starts in a real repo and then works in a folder with no remote gets its unknown rows labelled with that repo's folder name. Discovery accepted this, but it can mislead Power BI readers.
3. **30-day pre-mortem:**
   - Power BI shows `local:C--Users-…-OneDrive---Cyclotron-Inc-…` and `local:OneDrive-CyclotronInc` rows to a wide audience.
   - A `cd C:\` makes a project session read `local:(home)`.
   - Someone's `proj\src` sessions all read `(home)`, and the "unknown" spike is again undiagnosable without SQL.
4. **Concrete alternative:** apply a label allowlist test to the final segment instead of an ineligible-segment denylist. Accept a segment only if it contains no `:`, does not start with `.`, `C--` or `-Users-`, does not start with `OneDrive`, and is not the username. Otherwise emit `local:(other)`.
5. **Risks accepted implicitly:**
   - Mis-labelling when a session visits an ancestor folder.
   - A real repo's name appearing as `local:<name>` on unknown rows.
   - Extra correlated-subquery cost in the nightly export.
   - Folder names reaching a wider audience than the consent notice's "whoever administers billing".

### Footprint
files_read: 19 (~106,000 chars)
commands_run: 3

Key paths:
- C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\_goals\unattributed-usage-breakdown\01-project-label.md
- C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\_goals\unattributed-usage-breakdown\goal.md
- C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\billing\otel\attribute.py
- C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\billing\otel\export.py
