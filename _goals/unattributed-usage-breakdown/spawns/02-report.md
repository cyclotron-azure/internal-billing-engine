**Model (self-reported)**: claude-opus-5-5 (Opus 5.5). The context package requested claude-opus-5.

VERDICT: NEEDS REVISION
**Score**: 3/5
**failure_class:** implementation (goal and task authoring)

All 12 findings from the first review are fixed, except the `D:\derek` case you chose to accept. All 22 worked examples give the stated labels under the rewritten algorithm. The rewrite introduced two new label defects on common real-world paths, one of which leaks a username. The new ≤2× timing criterion is under-specified and, as far as I can measure, not met by the approach the task prescribes.

### What I verified
- **All 22 worked examples in 01-project-label.md:121-142 → ✅ Verified.** I wrote a stdin-only prototype of Definitions (01:52-70) and Root algorithm steps 1–7 (01:74-99), with no files written. Result: `mismatches: 0` on every row, including 22a (`[]`) and 22b (`[("CwdChanged","")]`). The two task 04 extra cases also come out right: an `OfficeDashboard` ancestor gives `local:Dashnoard`, and a history containing the outer `...\Code` gives `local:Dashnoard`.
- **Malformed inputs from 01:107-109 → ✅ Verified.** `":"` gives `local:(other)`. `"\\\\"`, `" "` and `"C:"` give `local:(home)`. A 10,000-character path is truncated to 100 characters. None of them raise, and none return a bare `local:`.
- **Previous findings, now fixed:**
  - 1: slug leak (examples #6-8) → ✅
  - 2: OneDrive variants (#17, #18, guard at 01:90-93) → ✅
  - 3: zero-segment paths (#10, #19, 01:97-99) → ✅
  - 4: in-project `src` (#13, #14) → ✅
  - 5: success criterion narrowed (goal.md:83-85) → ✅
  - 6: `generated_at` excluded, and the pre-change method is now given (02:39-41, 02:83-87) → ✅
  - 7: class wording now matches attribute.py:28-45 and 88-94 (03:36-49) → ✅
  - 8: per-file `rewrite_semantics` (04:31-34) → ✅
  - 9: task 03 owns the drift fix (goal.md:62-65, 03:63-66) → ✅
  - 12: risks and rollback section (goal.md:110-123) → ✅
  - 11: 8.3 short names are now covered by position (01:55-57) → ✅. `D:\derek` is accepted, as the delta notes.
- **Previous finding 10 (export cost) → the fix is applied, but the new criterion has problems (see finding 3).** I timed the prescribed CASE-guarded GROUP BY against the current query on an in-memory store with 20,000 datapoints (SQLite 3.49.1). Best of 3 runs, SQL step only:

  | Unknown share of datapoints | new/old | `AS MATERIALIZED` CTE/old |
  |---|---|---|
  | none | 1.55× | 1.63× |
  | 1/10 | 2.10× | 1.53× |
  | 1/4 | 2.74× | 2.65× |
  | 1/2 | 3.12× | 3.06× |

- **Nothing else broken:** ownership blocks, dependency graph and eval_depth are unchanged and still pass. `OTHER_LABEL` was added to the frozen interface and to acceptance criterion 1 (01:35, 01:153) → ✅

### Findings
1. **[major] Visual Studio's default layout collapses to `local:repos`.** Location: 01-project-label.md:59-63.
   - The outer zone takes "at most one" container. So `C:\Users\Zane\source\repos\internal-billing-engine` gives `local:repos` (prototype output). Every project in Visual Studio's default `source\repos` folder, a very common Windows layout, then shares one label. That defeats the goal's "what project" purpose (goal.md:9-11).
   - Related: `...\Documents\Visual Studio 2022\Projects\Foo` gives `local:Visual Studio 2022`.
   - This is new in the rewrite; the previous skip-deeper rule gave the project name. None of the 22 examples covers it.
   - **Fix:** let the outer zone take a run of consecutive container segments (or special-case `source\repos`). Add worked examples `C:\Users\X\source\repos\proj` → `local:proj` and the `Visual Studio 20xx\Projects` shape.
2. **[major, privacy] WSL paths into Windows home folders leak the username.** Location: 01-project-label.md:55-58, 64-65 and 90-93.
   - The home prefix is only recognised at segment 0. The prototype gives:
     - `/mnt/c/Users/Derek/src/proj` → `local:Derek`
     - `/mnt/c/Users/Derek/source/repos/proj` → `local:Derek`
     - `/mnt/c/Users/Derek` → `local:Derek`
   - Cause: `src` counts as an in-project container, which points to its parent, and the parent here is the username. The guard misses it because usernames are also only collected at segment 0.
   - This contradicts success criterion 5 (goal.md:83-84, "a username"). It is not the accepted `D:\derek` case: here the username sits under a `Users` segment.
   - **Fix:** recognise the `Users`/`home` + next-segment pattern at any position, or drop a leading `mnt/<letter>` and a single-letter `/c/` segment as drive prefixes. Add WSL worked examples.
3. **[major] The ≤2× timing criterion does not fix the data mix, and the prescribed method missed it in my test.** Location: 02-export-breakdown.md:62-67 and acceptance criterion 4 at 02:90.
   - **Under-specified:** the unknown-row share of the seeded store is not specified. An implementer can pass by seeding almost no unknown rows.
   - **Unsatisfiable as prescribed:** with a realistic share (10-50% unknown), the prescribed `CASE WHEN resolved_repo='unknown' …` grouping measured 2.1-3.1× on the SQL step alone. Even with zero unknown rows it was 1.55×, because each CASE re-evaluates `resolved_repo`'s two correlated subqueries. An `AS MATERIALIZED` CTE only helps at low unknown shares. This is ⚠️ synthetic in-memory data, not production volume.
   - Left as written, task 02 will either game the criterion or loop through fix cycles into arbitration.
   - **Fix:**
     - Fix the seed mix, for example the production unknown share, or say at least 25%.
     - Set a bound that is achievable (measured ~3× for the SQL step), or allow a restructure that computes `resolved_repo` once per row.
4. **[minor] Can the outer zone start without a home prefix?** Location: 01-project-label.md:59-63.
   - The phrase "(0 if none of these match at the start)" and the Phase 3 decision (goal.md:43-44, "home / drive / OneDrive level") suggest a drive-level container counts. But the definition reads as "home prefix, followed by…".
   - `D:\Code` gives `local:(home)` under one reading and `local:Code` under the other. `D:\Code\proj` gives `local:proj` either way.
   - **Fix:** add a `D:\Code` / `D:\Code\proj` worked example.
5. **[minor] The Discovery privacy bullet is stale against the Phase 3 decisions.** Location: goal.md:37-41.
   - It still says a home folder or `OneDrive - <org>` root gives `local:(home)`. The Phase 3 decisions at goal.md:46-50 allow a home-child root (the sync-root org name) and send OneDrive / username roots to `local:(other)` (example #20).
   - Task 03 takes its rule wording from the Discovery Summary (03:83), so the README could end up documenting the stale rule.
   - **Fix:** mark 37-41 as superseded, or rewrite it.
6. **[minor] macOS temp directories are not treated as Claude-internal.** Location: 01-project-label.md:66-68.
   - Only `Temp`/`tmp` + `claude` counts. A macOS `$TMPDIR` path such as `/var/folders/ab/xyz/T/claude/-Users-derek-Code-proj/<id>/scratchpad` gives `local:scratchpad`. A start at `<id>` would give `local:<id>`.
   - The guard still catches a `-Users-` slug root, so nothing leaks; it only mislabels. Whether Claude Code uses `$TMPDIR` on macOS is ⚠️ Unverified.
   - **Fix:** also accept `T` (or any `claude` segment directly followed by a slug-shaped segment).
7. **[minor] "Drive letter" in acceptance criterion 4 is ambiguous.** Location: 01-project-label.md:159-161.
   - A naive `[A-Za-z]:` check matches the `l:` of `local:` on every label. Task 04:54-56 words it correctly ("`:` other than the prefix's").
   - **Fix:** use the same wording in acceptance criterion 4.

### Devil's Advocate (delta)
1. **Steelman alternative:** a denylist of known layouts will keep growing: `source\repos`, WSL, macOS `$TMPDIR`, `Visual Studio 20xx`. A single positive rule would be sturdier: take the deepest ancestor of the start folder that holds a project marker the client already reports. That would need a hook change, which is out of scope.
2. **Load-bearing assumption:** that every dev layout has one container level beneath home or drive. `source\repos` breaks that.
3. **Pre-mortem:** Power BI shows `local:repos` for most .NET developers, and `local:Derek` for the one WSL user. The nightly export time doubles or triples on real volume.
4. **Concrete alternative:** fold consecutive containers into the outer zone, and find the home prefix at any position.
5. **Accepted risks:** ancestor-visit mislabels and start-folder labels on mixed sessions (goal.md:118-121); a sync-root org name shown as a label (#16, a user decision).

### Footprint
files_read: 6 this round (~40,000 chars): 02-context.md, goal.md, and task files 01-04. goal-criteria SKILL.md was not re-read; it was already read earlier in this session.
commands_run: 4 (one failed on a string-escaping error and was rerun)
