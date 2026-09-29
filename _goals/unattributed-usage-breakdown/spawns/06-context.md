You are the implementer subagent (resumed, fix cycle 1). Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-28T22:35:00Z

## Task
Fix cycle 1 for task 01 `01-project-label`. The evaluator returned NEEDS FIXES (report:
`_goals/unattributed-usage-breakdown/spawns/05-report.md`). The spec in
`_goals/unattributed-usage-breakdown/01-project-label.md` has been AMENDED to close the
gaps; implement the amended spec. Re-read the Definitions, step 6, and worked examples
#31–#38.

## Requirements (delta)
1. `path_segments`: the WSL (`mnt` + letter) and Git Bash (leading letter when the path
   starts with `/`) prefixes require a single ASCII letter `[A-Za-z]`, not any single
   character. (#25–#27 must still hold; #35 `/1/Code/proj` → `local:1`.)
2. Home prefix: a bare `Users` / `home` with nothing after it is a 1-segment home prefix
   (#31 `C:\Users`, #32 `/home` → `local:(home)`).
3. Usernames: scan the RAW split of each cwd (before drive/UNC/WSL prefixes are
   dropped), so `\\host\Users\bob` contributes `bob` (#34 → `local:(other)`).
4. Step 6 guard additions: segment equal (case-insensitive) to `Users` or `home` →
   `OTHER_LABEL` (#33 `D:\Code\Users`); any control character (code point < 32) →
   `OTHER_LABEL` (#37). Segment equality, not substring (#38 `users-api` stays).
5. Whitespace-only cwd is empty everywhere (#36; your current behaviour — keep it).
6. Update the module docstring only if needed so it matches the behaviour.
7. Everything else (all other definitions, #1–#30, AC1–AC5) must still hold.

## Files to Read
- _goals/unattributed-usage-breakdown/01-project-label.md (amended spec)
- _goals/unattributed-usage-breakdown/spawns/05-report.md (evaluator findings)
- billing/otel/project_label.py (your file)

## Write fence
- billing/otel/project_label.py only. Scratch scripts only in
  C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\0ab35cbd-cb5c-4db5-9ffc-e0282cc3cab6\scratchpad
  (write test strings in a .py file there, not inline shell, to avoid the escaping
  problem you hit last time; build the UNC string as a Python literal).

## Model
requested: claude-sonnet-5 · tier: light · rotation: cycle 1 (resume, same model)

## Rules
Same as your original package: stdlib only; persist nothing; no filesystem path
resolution; no other file edits; no git command that changes the tree or index; do not
run the full suite (rung 2 `python -m pytest tests/test_attribute.py -q` is allowed).
Close the store before deleting temp files.

## Output
Report: files changed; all 38 examples as `#n expected got OK/FAIL`; AC1, AC3–AC5
re-run output; rung 2 result; any deviation; `### Footprint`.
