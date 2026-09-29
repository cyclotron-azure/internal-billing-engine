**Model (self-reported)**: claude-opus-5-5 (Opus 5.5). The context package requested claude-opus-5.

VERDICT: PASS (with notes)
**Score**: 4/5

All seven cycle-2 findings are fixed. Every one of the 30 worked examples gives the stated label under the updated definitions, including #1–#22, so the run-based outer zone caused no regressions. I found no new blocker or major issue. The three notes below are minor, and **none of them should block Phase 4**.

### What I verified
- **All 30 worked examples (01-project-label.md:132-163) → ✅ Verified.** I rewrote the stdin-only prototype to match the updated rules: path splitting (01:52-61), the home prefix (01:62-65), usernames found at any position (01:66-67), the outer folder and run-based outer zone (01:68-75), Claude-internal folders including `T` (01:78-81), and root algorithm steps 1–7 (01:87-108). Output: `examples: 31 mismatches: 0` (31 rows because #22 has two parts, 22a and 22b).
  - #1–#22 give the same labels as in cycle 2.
  - #12 still gives `local:orbit-wt`: the run stops at `orbit-wt`.
  - #13 and #14 still give `local:proj`: no zone at `Cyclotron`.
- **Acceptance criterion 4's privacy check (01:180-183) → ✅ Verified.** I ran every cwd in the table on its own as a start folder. Result: `AC4 leaks: []`.
- **F1 (`source\repos`) → ✅.** #23 gives `local:internal-billing-engine` and #24 gives `local:Foo`. Probes: `C:\Users\Zane\source\repos` and `...\Documents\Visual Studio 2022\Projects` both give `local:(home)`. `C:\Users\Derek\Code\git\dev\proj` gives `local:proj`.
- **F2 (WSL and Git Bash) → ✅.** #25 gives `local:proj`, #26 gives `local:(home)` and #27 gives `local:proj`. Probes: `/mnt/c/Users/Derek/OneDrive - Cyclotron Inc/Code/proj` gives `local:proj`, and `/c/Users/Derek` and `/mnt/c` give `local:(home)`. Usernames are now collected at any position (01:66-67), which closes the leak I raised in cycle 2.
- **F4 (containers directly under a drive) → ✅.** #28 gives `local:(home)` and #29 gives `local:proj`. The rule is now stated at 01:72-73.
- **F5 → ✅.** The goal.md privacy bullet (37-46) now matches the final rules.
- **F6 → ✅.** #30 gives `local:(scratchpad)`.
- **F7 → ✅.** The wording is fixed at 01:181.
- **Example counts → ✅.** The count is updated to 30 in 01:176 and 01:212, 04:41, and goal.md:87.
- **Odd inputs → ✅.** `":"` gives `local:(other)`. `"\\\\"`, `" "` and `"C:"` give `local:(home)`. None of them raise, and none return a bare `local:`.
- **F3 (timing) → ✅ for how the criterion is written; ⚠️ my estimate is not a measurement.** The seed mix is now fixed at 25% unknown, half of those with timeline rows (02:68-71), and the gate is 3× the full `build()` time, best of 3. I seeded 20,000 in-memory datapoints (16,000 token rows and 4,000 cost rows, 400 sessions) and timed the current `export.build()` against the new SQL alone: the label SELECT plus both CASE-guarded GROUP BY queries.

  | Unknown share | New SQL alone vs current full `build()` | With `AS MATERIALIZED` |
  |---|---|---|
  | 0% | 1.67× | 2.01× |
  | 25% | 2.16× | 2.41× |
  | 50% | 2.68× | 2.96× |

  The extra Python rollup work is not included in these numbers. My estimate for the whole 25% build is about 2.2–2.8×, which is within the gate. The materialized option the task allows was slower here, not faster.
- **Nothing else changed.** The ownership blocks, dependency graph, eval_depth and acceptance-criteria sections of 01, 02 and 04 read the same as in cycle 2.

### Findings
1. **[minor] Success criterion 5 has a literal-wording edge case.** Location: goal.md:88-90.
   - It says no label cell may "contain `Users`". A project folder that is really named, say, `UsersPortal` becomes `local:UsersPortal`, because the guard (01:103-106) only blocks usernames, not the word `Users` in a name.
   - Why only minor: nothing leaks, since the label is one real folder name. Task 04's privacy test (04:54-56, 76-79) only checks seeded paths, so it will pass.
   - The final audit should read the criterion as "a `Users` path segment". It does not block Phase 4.
2. **[minor] The timing gate has headroom but is sensitive to noise.** Location: 02:68-71 and acceptance criterion 4 at 02:94-95.
   - My estimate for the gated 25% case is about 2.2–2.8× against a 3× limit.
   - At 20,000 datapoints the pre-change `build()` takes about 14 ms, so run-to-run jitter can move the ratio by a noticeable amount.
   - Suggestion: take the median of 5 runs, or use a larger store, if the first measurement lands near 3×. Non-blocking.
3. **[minor] The Phase 3 decision wording is slightly stale.** Location: goal.md:48-50.
   - It still says containers are outer "only directly under the home / drive / OneDrive level". The final rule absorbs a whole run of outer folders and containers (01:71-75), for example `Documents\Visual Studio 2022\Projects`.
   - Task 03 takes its wording from goal.md (03:83), but it also reads the shipped `project_label.py`, so the README should still come out right.
   - The Phase 6 docs pass should confirm the README describes runs. Non-blocking.

### Blocking statement
Nothing remaining blocks Phase 4. A fresh implementer can run task 01 from the file as written.

### Devil's Advocate (delta)
1. **Strongest alternative:** a positive project-marker signal from the client would still be sturdier than a list of known folder layouts, but it needs a hook change, which is out of scope.
2. **Load-bearing assumption:** that a folder named `Users` or `home` anywhere in a path is a profile folder. This over-triggers safely: `C:\work\home\stuff` gives `local:(other)`, which hides a name rather than leaking one.
3. **Pre-mortem:** the most likely remaining failure is an unusual layout that gives `local:(home)` or `local:(other)`. That is a mislabel, not a privacy leak.
4. **Alternative:** a small set of layout overrides the user can configure. That is not needed now.
5. **Accepted risks:** the mislabels listed in goal.md:118-121, the sync-root org name shown as a label (#16), and `D:\derek`-style homes (accepted in cycle 2).

### Footprint
files_read: 5 this round (~33,000 chars): 03-context.md, 01-project-label.md, 02-export-breakdown.md (lines 56-100), goal.md (lines 30-94), plus a grep of goal.md and 04-tests.md.
commands_run: 2 (the 30-example prototype with privacy check and probes; the timing estimate on the task 02 seed mix)
