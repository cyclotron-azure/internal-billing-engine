You are the implementer subagent (resumed, fix cycle 1). Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-28T23:55:00Z

## Task
Fix cycle 1 for task 03 `03-readme-columns`. The evaluator returned NEEDS FIXES (report:
`_goals/unattributed-usage-breakdown/spawns/12-report.md`). Apply the fixes below to
README.md (and fabric/README.md for item 2), surgically.

## Requirements (delta)
1. [major] Replace the sentence "The label is the first folder after that zone, so ..."
   with wording that matches `billing/otel/project_label.py` (around lines 129–146):
   when the outer zone includes a container folder, the label is the first folder after
   it (`...\Code\Dashnoard`, `...\Code\Dashnoard\OfficeDashboard\backend` →
   `local:Dashnoard`; `...\source\repos\proj` → `local:proj`); otherwise the label is
   the session's start folder, walked up only by the in-project-container rule and the
   shallower-visited-folder rule (e.g. `...\Documents\foo\bar` → `local:bar`;
   `C:\Cyclotron\Insights Agent\ai-presales-agent-main\ai-presales-agent-main` →
   `local:ai-presales-agent-main`). Keep the next bullet as those "rules below".
2. [minor] Say that `unattributed_project` is also blank on unknown rows whose session
   has no timeline (always for `no_remote` and `absent`), in README and in the
   fabric/README.md pointer sentence.
3. [minor] `local:(other)` list: add "starts with `.`" and "a bare `Users`/`home`
   folder", and say `OneDrive` anywhere in the name.
4. [minor] Describe WSL `/mnt/c/...` and Git Bash `/c/...` as drive prefixes that are
   stripped before the home check (`C:\Users\<name>`, `/home/<name>`, `/root`), not as
   home prefixes themselves.
Before finishing, run EVERY label example that appears in the README through
`billing.otel.project_label.root_label` (as a SessionStart history) in a scratch script
and confirm each stated label; include that output.

## Files to Read
- _goals/unattributed-usage-breakdown/spawns/12-report.md
- _goals/unattributed-usage-breakdown/01-project-label.md (Definitions + Root algorithm;
  read this time)
- billing/otel/project_label.py
- README.md, fabric/README.md (your edited sections)

## Write fence
- README.md
- fabric/README.md
Scratch scripts only in
C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\0ab35cbd-cb5c-4db5-9ffc-e0282cc3cab6\scratchpad

## Model
requested: claude-sonnet-5 · tier: light · rotation: cycle 1 (resume, same model)

## Rules
Same as your original package: docs only, targeted edits, no real usernames or paths,
no git command that changes the tree or index.

## Output
Report: files changed; the new README text for each fix; the example-check script
output (`example -> expected got OK/FAIL`); `git diff --stat`; `### Footprint`.
