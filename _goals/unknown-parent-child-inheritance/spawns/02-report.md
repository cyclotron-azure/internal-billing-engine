## Verdict: NEEDS REVISION
**Score**: 3/5
**Model (self-reported)**: claude-opus-5-5 (Opus 5.5). The context package asked for claude-opus-5; the harness reports Opus 5.5.
**failure_class:** implementation. The task files need an ordinary revision. The criteria are mostly sound, and no destructive, security or infra issue was found.

Revision 1 fixes 12 of my 13 findings outright. The one partial is #11, the temporary write-fence exception: it is now recorded, but the check meant to prove the mutants were reverted cannot work (new finding N1).

I transcribed the blocklist into SQLite and ran every REQUIRED example. All 14 BLOCKED and all 5 ALLOWED paths behave exactly as task 01 lists.

One new major stops a PASS: the `git status --short` acceptance criteria introduced by fix #8 cannot be satisfied on this branch. Because of that, the write-fence exception in task 02 also has no working revert proof. The rest are minors.

### Prior findings: fixed / not fixed

| # | Prior finding | Status | Evidence |
|---|---|---|---|
| 1 | Root guard too narrow (`/mnt/c`, `/c`, UNC, `~`) | **Fixed** | 01:65-85. Live result: `/mnt/c`, `/c`, `\\srv\share`, `~`, `C:\`, `/` are all BLOCKED. Remaining gaps (`/mnt/data`, `/volumes/x`, `/media/x`, bare `//srv`) are listed as new minor N5. |
| 2 | GLOB required by one rule and forbidden by another | **Fixed** | 01:148-149 now allows a GLOB/LIKE whose pattern is a fixed literal. A wording remnant at 01:80 is new minor N3. |
| 3 | The named mutation disabled the rule instead of widening it | **Fixed (one claim wrong)** | 02:86 now lists mutants (a)-(e), each tied to a named test. Mutant (a) claims it also fails the wildcard tests; measured, it does not (new minor N4). |
| 4 | Today's behavior for a non-unknown effective row not pinned | **Fixed** | 01:42-45 and AC5 (01:121); task 02 Preservation (a)/(b)/(c) at 02:50-54. |
| 5 | NULL cwd claim false; NULL test unreachable | **Fixed** | `ifnull` added at 01:55; NULL-safety rule at 01:86-87; raw-`INSERT` seeding at 01:124 and 02:67-69. |
| 6 | No warning about writing a backslash in Python | **Fixed (but the example escape is wrong)** | Warning added at 01:56-58. The suggested `'\\\\'` is itself a bug in a normal Python string (new minor N6). |
| 7 | Effective row's repo and cwd could come from different rows | **Fixed** | 01:36-41: same row, read once; `rowid DESC` / `rowid ASC` tie-breaks. |
| 8 | `git diff --stat` cannot see untracked files | **Fixed, but the replacement criteria cannot be met** | 01:128 and 02:86/88 now use `git status --short`, with expected output that cannot occur (new major N1). |
| 9 | Performance gate under-specified | **Fixed** | 01:104-111: median of 3 on a warm DB, plus a heavy-tail session (≥300 timeline rows, ≥20k datapoints). |
| 10 | No acceptance criterion for alias safety | **Fixed** | AC9 (01:125); task 02 Alias test (02:77-78); goal.md:74. |
| 11 | Temporary mutation outside task 02's write fence | **Partially fixed** | Recorded in task 02's `writes` at 02:16, and allowed because 02 depends_on 01. The revert cannot be proven (part of N1). |
| 12 | Home folders as anchors needed user confirmation | **Fixed (user decided)** | goal.md:21-29: ancestor-only direction and project-level anchors. |
| 13 | ASCII-only `lower()` | **Fixed** | goal.md:48-49 guard (d); docstring requirement at 01:100-103. |

### What I verified (this round)
- REQUIRED BLOCKED examples (01:81-83) → ✅ Verified live (`blocklist_check.py`). Each path is listed with the class that blocked it:
  - root: `C:\`, `/`, `~`, `/mnt/c`, `/c`, `\\srv\share`
  - home: `C:\Users\x`, `/home/x`, `/root`
  - top-level: `C:\dev`, `C:\Cyclotron`
  - container: `/home/x/projects`, the OneDrive root, OneDrive `\Desktop`
  - All 14 are BLOCKED.
- REQUIRED ALLOWED examples (01:84-85) → ✅ Verified live. `C:\dev\wealthspire`, OneDrive `...\Code\Dashnoard`, `C:\Users\x\proj`, `/home/x/proj` and `/srv/app/x` are all allowed.
- Top-level class for the non-Windows roots → ✅ Verified as probes (none of these are in the required list): `/mnt/c/Cyclotron`, `/c/Cyclotron`, `/opt` and `\\srv\share\team` are all BLOCKED.
- The blocklist vocabulary matches `project_label` → ✅ Verified. `project_label.py:26-30` has CONTAINER_DIRS (9 names) plus `_OUTER_NAMES` (5), and line 72 has the `onedrive` / `visual studio ` prefixes.
- Mutant (a) "widen" → ✅ Verified. The lookalike `c:/dev/wealth` vs `c:/dev/wealthspire/x` becomes 1, so its test goes red. The wildcard pairs `a_b`/`axb` and `a%`/`abc` stay 0.
- A LIKE-pattern mutant (`x LIKE u || '/%'`) on the same wildcard pairs → ✅ Verified = 1, so it would turn the wildcard tests red.
- Descends written exactly as the prose reads, without brackets (01:59-60) → ✅ Verified = 1 for `u=''`, `x='/home/x/proj'`. AND binds tighter than OR. Today the "empty" root block (01:67) hides this.
- `'\\\\'` in a normal Python string → ✅ Verified (`escape_check.py`). The SQL gets two backslashes and the path comes back unchanged (`'C:\\dev\\x'`). `'\\'` and a raw string both give `'C:/dev/x'`.
- Current tree → ✅ Verified. `git status --short` shows `?? _goals/unknown-parent-child-inheritance/`, and `_goals/` is not gitignored (`git check-ignore` printed nothing).
- Commit policy → ✅ Verified. ORCHESTRATION.md:657-681 commits once per story in the auto-loop only. Nothing commits between task 01 and task 02 in the `/feature` flow (Phase 7 PR = NO).
- Mutants (b)-(e) → 🔍 Reasoned, not run (there is no implementation yet):
  - (b) direction: kills the Reverse test if the child path is not itself blocked.
  - (c) blocklist removed: kills the blocklist tests.
  - (d) MIN / LIMIT 1: kills the distinct-repos test.
  - (e) unknown-only removed: with the natural "else `'unknown'`" form, kills Preservation (a). The effective M at `C:\mono` is blocked as top-level (measured: `top=1`), or its descendant set {M, S} has two distinct repos.
  - A "COALESCE(inherited, own repo)" form of (e) is an equivalent mutant: the effective row's own folder always qualifies (same folder), so its repo is always in the set. That form cannot be killed, so it should not be the mutant used.

### New findings
1. **N1 [major]** The `git status` criteria cannot be met, so task 02's revert proof does not work. Affects 01:128, 02:86 and 02:88.
   - Task 01 AC12 expects only `M billing/otel/attribute.py`. The tree already shows `?? _goals/unknown-parent-child-inheritance/`, and that is not ignored.
   - Task 02 AC2 and AC4 expect only `?? tests/test_attribute_inheritance.py`. Since nothing commits between tasks, task 01's `M billing/otel/attribute.py` will still be present, plus the `_goals/` line.
   - Because `attribute.py` is already `M`, `git status` cannot show whether a task 02 mutant was left behind or the file was edited permanently. Task 02 now has a recorded write exception (02:16) that cannot be audited, which undermines the evaluator's fence rule.
   - Fix: phrase the criteria against a baseline.
     - Task 01: no paths outside `billing/otel/attribute.py` and `_goals/` are changed.
     - Task 02: record `git hash-object billing/otel/attribute.py` before the first mutant and require the same hash after the last revert. Also require no other changed paths besides the new test file and `_goals/`.
2. **N2 [minor]** The blocklist is a deny-list, so folders named outside its vocabulary still inherit, and the goal does not disclose this.
   - Measured as allowed anchors: `C:\Users\x\Cyclotron`, `C:\Users\x\clients`, `C:\Users\x\Work` and `C:\Users\x\AppData\Local\Temp`.
   - A session started in `C:\Users\x\clients` that visits one client repo bills all of its clients-folder work to that client. That is a "likely estimate".
   - Some residual is unavoidable with a deny-list, and the user chose this scope. Add it to goal.md's flag-at-delivery list (lines 42-49) so the user knowingly accepts it. Optionally add `work`, `clients`, `temp`, `tmp`, `appdata` to the vocabulary.
3. **N3 [minor]** 01:80 is inconsistent with what an implementation needs.
   - It says all checks use only `length`/`substr`/`instr`/equality/`IN`.
   - Constraint 01:148-149 also allows fixed-literal GLOB/LIKE, and `N` itself uses `rtrim`/`replace`.
   - Taking the last segment and the parent segment of a path of any depth (for the home rule and the `onedrive`/`visual studio` prefix rule) needs the `rtrim(n, replace(n,'/',''))` trick or a recursive CTE. My transcription needed it.
   - Fix: widen the list to include fixed-pattern GLOB/LIKE, `rtrim` and `replace`. Otherwise the task 01 evaluator could fail a correct implementation.
4. **N4 [minor]** 02:86, mutant (a), says it fails "prefix-lookalike and wildcard tests". Measured, the wildcard tests stay green under it.
   - The criterion's "at least one named test" is still met by the lookalike test, but the wildcard tests have no mutant that can kill them.
   - Fix: drop "and wildcard" from (a) and add (f), a LIKE-pattern mutant (`N(x) LIKE N(u) || '/%'`), which turns the wildcard tests red (measured = 1).
   - Also state that mutant (e) is the "else `'unknown'`" form, since the COALESCE-to-own-repo form is equivalent and cannot be killed.
5. **N5 [minor]** Root anchors beyond the required set are still allowed (measured): `/mnt/data`, `/volumes/disk` (macOS external drive), `/media/x` and a bare `//srv`.
   - These are the same kind of drive or mount root that finding #1 was about.
   - Fix: block `/mnt/<anything>`, `/media/<x>` and `/volumes/<x>` as roots, and block a UNC host with only one segment.
6. **N6 [minor]** 01:57's escape guidance is wrong for a normal Python string. `'\\\\'` produces a two-backslash SQL literal, so the replace silently does nothing (measured).
   - Fix: say `r"... '\' ..."` (raw string) or `'\\'` (normal string). The separator tests would catch the bug, but the guidance points straight at it.
7. **N7 [minor]** The Descends prose at 01:59-60 has no brackets. Transcribed literally, an empty `u` "descends" to every POSIX absolute path (measured = 1). Only the empty-root block at 01:67 hides it.
   - Fix: write `nonempty(u) AND nonempty(x) AND (N(x)=N(u) OR substr(...) = N(u) || '/')`.
8. **N8 [minor]** Two task 02 test paths should be pinned so the mutants exercise the intended logic.
   - The Reverse test (02:43) should use a child path that is not blocked (e.g. `C:\dev\repoR\tools\gen`, not `...\src`). A blocked child would mask mutant (b).
   - Preservation (a) uses `C:\mono`, which is blocked as top-level (measured). Mutant (e) is then killed by the blocklist rather than by the distinct-repo logic. Use `C:\dev\mono` so the test checks what it is named for.

### Hunt checklist (02-context rules)
- **(a) Wording that lets an unrelated or container folder inherit:** only through words missing from the deny-list vocabulary (N2) and unlisted mount roots (N5). The direction (01:61-62), the DirectoryAdded exclusion (01:50) and the session-id guard (01:53-54) are sound.
- **(b) REQUIRED examples:** all correct when the rules are transcribed faithfully. The hazards are wording traps that would lead an implementer wrong: N3, N6, N7, and GLOB `*` matching across `/` (measured: `'//srv/share/team' GLOB '//[^/]*/[^/]*'` = 1). For that last one, the BLOCKED and ALLOWED example lists catch mistakes in both directions.
- **(c) Requirement vs acceptance-criteria contradictions:** N1 (git status), N3 (allowed functions) and N4 (wildcard claim).
- **(d) Mutants (a)-(e):** each plausibly turns a named test red. Exceptions: the wildcard part of (a), and the equivalent form of (e) (N4, N8).
- **(e) The task 02 fence exception vs the evaluator's fence rule:** declaring it is fine under single-owner, because 02 depends_on 01. It cannot be audited until N1 is fixed.

### Required fixes
- [ ] N1: rewrite 01 AC12 and 02 AC2/AC4 against a baseline (`_goals/` excluded). Prove the mutants were reverted with an `attribute.py` hash taken before and after.
- [ ] Recommended minors: N2 (add the deny-list residual to the delivery flags, optionally widen the vocabulary), N3 (widen the allowed-function wording), N4 (fix mutant (a)'s claim, add a LIKE mutant, pin the form of (e)), N5 (mount roots), N6 (correct escape example), N7 (brackets), N8 (pin the Reverse and Preservation paths).

### Footprint
files_read: 4 (~27000 chars). That is 02-context.md, goal.md, 01-attribute-inheritance.md and 02-tests.md; code facts were reused from round 1.
commands_run: 4. Git status, ignore and commit-policy checks; the blocklist and mutant probe script; and two runs of the escape check.
