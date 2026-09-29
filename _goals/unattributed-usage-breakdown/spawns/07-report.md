**Model (self-reported)**: claude-opus-5-5 (requested claude-opus-5, frontier tier; resumed)
## Verdict: PASS (with notes)
VERDICT: PASS (with notes)
**Score**: 4/5

Fix cycle 1 resolves both majors from my cycle-0 verdict and the optional minor. The code matches the amended spec clause by clause, all 38 worked examples hold, and AC1–AC5 pass on my re-run. The only issue left is a minor one about the comment-line limit (finding 1). I've also listed three non-blocking notes for the orchestrator.

### What I verified
I extended my earlier scratch script into `...\scratchpad\eval07.py` (in the session scratchpad; no repo files touched) and ran it from the repo root. It exited 0.

**AC2: all 38 worked examples** → ✅ Verified. Output: `AC2 failures: 0`.
- That covers #1–#38. I ran #22 as two histories (22a and 22b) and kept my extra 19b variant.
- I built the strings for #34 and #37 with `chr(92)` and `chr(0)`. The script printed them back as `'\\\\host\\Users\\bob'` and `'C:\\Cyclotron\\bad\x00name'`.
- New results:
  - #31 → `local:(home)`
  - #32 → `local:(home)`
  - #33 → `local:(other)`
  - #34 → `local:(other)`
  - #35 → `local:1`
  - #36 → `local:proj`
  - #37 → `local:(other)`
  - #38 → `local:users-api`

**Earlier probes, re-run** → ✅ Verified. Each result is what the amended spec produces when read literally.

| Input | Label |
|---|---|
| `C:\Users` | `local:(home)` |
| `/Users` | `local:(home)` |
| `/home` | `local:(home)` |
| `C:\home` | `local:(home)` |
| `D:\Code\Users` | `local:(other)` |
| `C:\Users\Derek\Code\Users\x` | `local:(other)` |
| `C:\Users\Derek\Code\home` | `local:(other)` |
| `\\host\Users\bob` | `local:(other)` |
| `\\host\home\bob` | `local:(other)` |
| `/1/Code/proj` | `local:1` |
| `/_/Code/proj` | `local:_` |
| `/mnt/1/Code/proj` | `local:1` (segments `['mnt','1','Code','proj']`, candidate b = 1) |
| `"\x00"` | `local:(other)` |

New probes:

| Input | Label |
|---|---|
| `/mnt/c/Users` | `local:(home)` |
| `/c/Users` | `local:(home)` |
| `~/Users` | `local:(home)` |
| `/Z/Code/proj` | `local:proj` |
| `/mnt/Z/Users/d/src/p` | `local:p` |
| a tab inside a segment | `local:(other)` |
| `/home/derek/Code/users` | `local:(other)` |
| `Project.Users` | `local:Project.Users` (allowed: step 6 compares whole segments, not substrings) |

- A username taken from a UNC path in another cwd of the same session is still caught: `(S C:\X\bob),(C \\h\Users\bob)` → `local:(other)`.
- Whitespace-only rows in both positions → `""`.

**AC1: interface and stdlib-only imports** → ✅ Verified.
- The `python -c` command prints `local: local:(home) local:(scratchpad) local:(other) ['code','dev','git','github','projects','repos','source','src','workspace']`.
- `CONTAINER_DIRS` is a `frozenset`.
- All four signatures are unchanged.
- An AST import scan finds `__future__`, `billing.otel.attribute`, `collections.abc`, `re` and `sqlite3`.

**AC3: malformed inputs** → ✅ Verified. `AC3 bad: 0` across 17 inputs × 2 events, plus odd history shapes.
- I included a real 12-character UNC string, which gives `local:(home)`.
- `" "` → `""`, and `"x"*10000` → a 106-character label.

**AC4: privacy over every example cwd** → ✅ Verified against the AC's literal token list.
- My script reported 3 hits. All three come from its own case-insensitive `users` substring check matching #38 `local:users-api`, a label the amended spec explicitly allows.
- AC4's literal token is `Users`, and `users-api` does not contain it (case-sensitive), so AC4 holds.
- Nothing else was flagged: no separators, no second colon, no OneDrive, `.claude`, slug or username.

**AC5: `load_session_labels`** → ✅ Verified.
- Empty timeline: returns `{}`, and the trace shows exactly one statement, `SELECT session_id, event, cwd FROM session_repo_timeline ORDER BY session_id, ts, seq`. `in_transaction` is False.
- Six sessions inserted, including one with an empty cwd and one with a NULL cwd. Result: `{'s1':'local:Dash','s3':'local:(scratchpad)','s4':'local:(home)'}`.
- One statement, `total_changes` delta 0, and it also works on a plain connection without a `Row` factory.

**Amended spec vs code** → ✅ Verified line by line.

| Spec clause | Code |
|---|---|
| Single ASCII letter for WSL/MSYS | `_LETTER` project_label.py:35, used at :51 and :53 |
| Whitespace-only cwd counts as empty | :113, :115, :126 |
| Bare `Users`/`home` is a one-segment home prefix | `_home_len` :75-81 |
| Usernames scanned from the raw split | `_raw_segments` :38-39, `_usernames` :98-104 |
| Guard: `Users`/`home` equality | :154 |
| Guard: control characters (code point < 32) | :155 |

- The earlier guards (:149-153 and :156) are unchanged.
- The module docstring claim at :9-10 now holds for every probe.

**No regressions** → ✅ Verified. The original 30 examples, all cycle-0 probes and the ancestor, start-preference and case-insensitive probes give the same results as before, except the cases the fix was meant to change.

**Rung 2** → ✅ Verified. `python -m pytest tests/test_attribute.py -q` → `12 passed in 1.82s`.

**Write fence** → ✅ Verified.
- `git status --short` → ` M client-package.zip`, `?? _goals/unattributed-usage-breakdown/`, `?? billing/otel/project_label.py`.
- `client-package.zip` mtime is 2026-09-25, so it predates this goal.
- `project_label.py` was modified at 11:42:03. That is after the orchestrator amended the task file (11:41:41) and before the 06-report (11:43:03).

**Auto-fail triggers** → none fired.
- Standard library only, no secrets.
- It uses the caller's connection only: no `connect` call and no threads.
- Nothing is persisted, and no live service is called.
- `root_label` is still wrapped so it never raises.

### Issues found
1. **[minor] project_label.py:46 and :100: two comment lines, where the Constraints section allows "at most one short comment line".**
   - Cycle 1 added the second one: `# raw: a UNC share may itself be \`Users\``.
   - Why I rate it minor under the task-criteria rule: it is comment text, it changes no behaviour or output, and the limit sits in the Constraints section, not in Requirements or Acceptance Criteria.
   - Exact fix: delete the trailing comment on :46 (`# UNC host and share`), since the `startswith(("\\\\", "//"))` check on :45 already says it, and keep :100.

### Notes (non-blocking)
- **Criteria wording, for the orchestrator.** Step 6 now compares whole segments, so a folder named `/home/derek/Code/Users-api` produces `local:Users-api`, which I confirmed. That label literally contains the string `Users`. The task follows the amended spec and AC4 still passes, because no example cwd has that shape. But goal.md success criterion 5 and AC4 still say "contains `Users`". Task 04's tests and the final audit need to use the whole-segment reading, or success criterion 5 should be reworded to "a `Users`/`home` path segment". Otherwise a later evaluator could fail a spec-conformant label.
- **Control characters.** The guard stops at code point 32, as the spec says. DEL (0x7F) and the C1 range (0x80–0x9F) pass through: `x\x7fy` → `local:x\x7fy`. This conforms to the spec. Widen it only if you want CSV cells free of every control character.
- **Non-letter first segments are now kept, as the amended spec says.** For example, `/_/Code/proj` → `local:_` and `/mnt/1/Code/proj` → `local:1`. These are unusual labels but they match the amended spec (#35).

### Footprint
files_read: 4 this cycle (~25000 chars): 07-context, amended 01-project-label.md (two reads), 06-report.md, project_label.py
commands_run: 4 tool invocations (~10 shell commands): script build and run (first attempt failed on a non-UTF-8 character in my own script and was re-run), the eval07 run, rung-2 pytest, git status and diff, mtime stats, and a case-sensitive probe plus comment count
