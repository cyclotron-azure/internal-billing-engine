**Model (self-reported)**: claude-sonnet-5-5
## Task 03 fix cycle 1 complete

### Files changed
- README.md (section "Unattributed usage in the lake tables")
- fabric/README.md (pointer sentence)

### New text per fix
1. [major] Outer-zone bullet rewritten. The zone is the home prefix (`C:\Users\<name>`, `/home/<name>`, `/root`) plus the run of outer/container folders. A drive, UNC host and share, `~`, WSL `/mnt/c/...` and Git Bash `/c/...` are described as drive-style prefixes stripped before the home check (this covers fix 4). Then: "When that zone includes a container folder, the label is the first folder after it, so `...\Code\Dashnoard` and `...\Code\Dashnoard\OfficeDashboard\backend` both give `local:Dashnoard`, and `...\source\repos\proj` gives `local:proj`. Otherwise the label is the session's start folder, walked up only by the two rules below (so `...\Documents\foo\bar` gives `local:bar`, and `C:\Cyclotron\Insights Agent\ai-presales-agent-main\ai-presales-agent-main` gives `local:ai-presales-agent-main`)." The next bullet (in-project containers to parent, shallower visited folder is the root) is unchanged.
2. [minor] README, after "filled only on unknown rows": "`unattributed_project` is also blank on `unknown` rows whose session has no timeline (always for `no_remote` and `absent`)." fabric/README.md pointer now says the same in parentheses.
3. [minor] `local:(other)` now lists: would still look like a path or contains a path separator or `:`, starts with `.`, is a `C--` project slug, contains `OneDrive` anywhere in the name, is a bare `Users`/`home` folder, or is the username.
4. [minor] Covered in fix 1 (drive-style prefixes, plus `/root` as a home form).

### Example check
I ran every label example in the README through `root_label`, using a placeholder user `zz`. The script is in the scratchpad and I ran it with `PYTHONPATH=.`.

The first attempt failed with `ModuleNotFoundError: No module named 'billing'` because I forgot `PYTHONPATH`. The rerun, whose output is below, shows every case matching. The script's own OK/FAIL column read OK for all 17.
```
Code\Dashnoard -> local:Dashnoard OK
Code\Dashnoard\OfficeDashboard\backend -> local:Dashnoard OK
OneDrive - Org\source\repos\proj -> local:proj OK
Documents\foo\bar -> local:bar OK
C:\Cyclotron\Insights Agent\ai-presales-agent-main\ai-presales-agent-main -> local:ai-presales-agent-main OK
C:\Cyclotron\proj\src\components -> local:proj OK
Users\zz\orbit -> local:orbit OK
C:\Cyclotron\proj\sub (+ visit C:\Cyclotron\proj) -> local:proj OK
C:\Cyclotron\proj (+ visit C:\Cyclotron) -> local:Cyclotron OK
OneDrive - Org -> local:(home) OK
.claude\projects\x -> local:(scratchpad) OK
Temp\claude\x -> local:(scratchpad) OK
Users\zz\zz (username) -> local:(other) OK
Users\zz\.hidden -> local:(other) OK
Users\zz\My OneDrive Stuff -> local:(other) OK
/mnt/c/Users/zz/Code/Dashnoard -> local:Dashnoard OK
/c/Users/zz/Code/Dashnoard -> local:Dashnoard OK
```

### git diff --stat
```
 README.md        | 83 +++
 fabric/README.md |  9 ++--
 2 files changed, 87 insertions(+), 5 deletions(-)
```
The deletion count is still 5; the cycle-1 edits added only insertions.

### Footprint
files_read: 5 (~45000 chars: 13-context.md, 12-report.md, 01-project-label.md (Definitions section), README.md (section), project_label.py earlier)
commands_run: 2
