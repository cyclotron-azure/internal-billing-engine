**Model (self-reported)**: claude-sonnet-5-5
## Task Complete: 01-project-label, fix cycle 1

### Requirements checklist
- [x] R1: WSL `mnt` plus letter and Git Bash leading letter now require a single ASCII letter (new `_LETTER` regex). #25-#27 still hold, and #35 `/1/Code/proj` gives `local:1`.
- [x] R2: a bare `Users` or `home` is a 1-segment home prefix (`_home_len`). #31 and #32 give `local:(home)`.
- [x] R3: usernames are scanned from the raw split of each cwd (new `_raw_segments` helper, used by `_usernames`). #34 `\\host\Users\bob` gives `local:(other)`.
- [x] R4: the guard now also catches a segment equal to `Users` or `home` (case-insensitive) and any control character (code point below 32). #33 and #37 give `local:(other)`. #38 `users-api` is kept because the check is equality, not substring.
- [x] R5: a whitespace-only cwd is treated as empty. Behaviour is unchanged and #36 passes.
- [x] R6: no docstring change was needed. It already says Users/home never appear.
- [x] R7: #1-#30 and AC1-AC5 still hold.

### Files changed
- C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\billing\otel\project_label.py (targeted edits). Nothing else in the repo changed.
- The scratch script is `<scratchpad>\check02.py`, and it builds the UNC and control-character strings from `chr(92)` and `\x00`.

### Verification
All 38 worked examples pass (0 failures, `failures: 0`). Example 22 is run as two histories, 22a and 22b, so the script prints 39 lines, all `OK`. Each line has the form `#n expected got OK`; here the expected and got columns are identical, so I list each once.
- #1 to #4: `local:Dashnoard`, `local:Dashnoard`, `local:Dashnoard`, `local:ai-presales-agent-main`.
- #5 to #8: `local:(scratchpad)` for all four.
- #9 and #10: `local:(home)` for both.
- #11 to #14: `local:orbit`, `local:orbit-wt`, `local:proj`, `local:proj`.
- #15 to #17: `local:orbit`, `local:Cyclotron Inc`, `local:proj`.
- #18: `local:(home)`.
- #19: `local:ai-presales-agent-main`.
- #20: `local:(other)`.
- #21: `local:proj`.
- #22a and #22b: `''` for both.
- #23 and #24: `local:internal-billing-engine`, `local:Foo`.
- #25: `local:proj`.
- #26: `local:(home)`.
- #27: `local:proj`.
- #28: `local:(home)`.
- #29: `local:proj`.
- #30: `local:(scratchpad)`.
- #31 and #32: `local:(home)` for both (new).
- #33 and #34: `local:(other)` for both (new).
- #35: `local:1` (new).
- #36: `local:proj` (new).
- #37: `local:(other)` (new).
- #38: `local:users-api` (new).

**AC1:** `local: local:(home) local:(scratchpad) local:(other) ['code', 'dev', 'git', 'github', 'projects', 'repos', 'source', 'src', 'workspace']`. The imports in the file are `__future__`, `re`, `sqlite3`, `collections.abc.Sequence`, and `billing.otel.attribute.TIMELINE_TABLE`.

**AC3:** None of the inputs raised or returned a bare `local:`. Results for the cwd values I tried, each run as both SessionStart and CwdChanged:

| cwd | result |
|---|---|
| `":"` | `local:(other)` |
| two backslashes | `local:(home)` |
| `" "` | `''` |
| `"C:"` | `local:(home)` |
| 10,000-character path | `local:xxx...` (106 characters, so cut to 100 after the prefix) |
| `"/"` | `local:(home)` |
| `"~"` | `local:(home)` |
| `\\h\s` (a real UNC host and share this time) | `local:(home)` |
| `"//"` | `local:(home)` |
| `"\x00"` | `local:(other)` |
| `C:\Users` | `local:(home)` |

**AC4:** `leaks: 0`. I ran every cwd in the table on its own and as its full history. The check covers `/`, `\`, `:`, `Users`, `OneDrive`, `.claude`, `C--`, `-Users-`, and label-equals-username. Example #38's `users-api` is excluded from the substring check because the amended spec allows it.

**AC5:** a temporary `OtelStore` in a temp directory:
- Empty timeline: `{}` from 1 statement (the SELECT itself).
- Three sessions: `{'s1': 'local:Dash', 's3': 'local:(scratchpad)'}`. The session with an empty cwd is omitted.
- Exactly one statement, `SELECT session_id, event, cwd FROM session_repo_timeline ORDER BY session_id, ts, seq`.
- No open transaction.
- The store was closed before the temp directory was removed, so there was no lock error this time.

**Rung 2:** `python -m pytest tests/test_attribute.py -q` gave 12 passed.

### Notes for the evaluator
- No deviations from the amended spec.
- The "bare `C:\Users` gives `local:Users`" behaviour I flagged in the first report is now fixed (#31).

### Footprint
files_read: 4 (~30000 chars)
commands_run: 3
