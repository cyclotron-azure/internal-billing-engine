**Model (self-reported)**: claude-sonnet-5-5
## Task Complete: 01-project-label

### Requirements checklist
- [x] Frozen interface (LOCAL_PREFIX, HOME_LABEL, SCRATCHPAD_LABEL, OTHER_LABEL, CONTAINER_DIRS, path_segments, is_scratchpad, root_label, load_session_labels) with stdlib-only imports: billing/otel/project_label.py
- [x] Definitions and root algorithm steps 1-7 implemented as written (`_label`, `_outer_zone`, `_usernames`).
- [x] `root_label` never raises (wrapped) and never returns a bare "local:" (AC3 output below).
- [x] `load_session_labels` runs one SELECT using `TIMELINE_TABLE`, groups in Python, and omits empty labels. It returns {} on an empty timeline and never writes or commits.

### Files changed
- C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\billing\otel\project_label.py (new, whole file). Nothing else in the repo was touched. The scratch check script is at `<scratchpad>\check01.py`.

### Verification
**AC1**: `python -c "import billing.otel.project_label as p; print(...)"` and an import scan of the file.
```
local: local:(home) local:(scratchpad) local:(other) ['code', 'dev', 'git', 'github', 'projects', 'repos', 'source', 'src', 'workspace']
```
Import scan (`grep -nE "^(import|from) "`): `__future__.annotations`, `re`, `sqlite3`, `collections.abc.Sequence`, `billing.otel.attribute.TIMELINE_TABLE`. No third-party imports.

**AC2**: every line is `#n expected got OK/FAIL`. All 30 examples pass, 0 failures. #22 was run as two histories, 22a (`[]`) and 22b (`[("CwdChanged","")]`).
```
#1 'local:Dashnoard' 'local:Dashnoard' OK
#2 'local:Dashnoard' 'local:Dashnoard' OK
#3 'local:Dashnoard' 'local:Dashnoard' OK
#4 'local:ai-presales-agent-main' 'local:ai-presales-agent-main' OK
#5 'local:(scratchpad)' 'local:(scratchpad)' OK
#6 'local:(scratchpad)' 'local:(scratchpad)' OK
#7 'local:(scratchpad)' 'local:(scratchpad)' OK
#8 'local:(scratchpad)' 'local:(scratchpad)' OK
#9 'local:(home)' 'local:(home)' OK
#10 'local:(home)' 'local:(home)' OK
#11 'local:orbit' 'local:orbit' OK
#12 'local:orbit-wt' 'local:orbit-wt' OK
#13 'local:proj' 'local:proj' OK
#14 'local:proj' 'local:proj' OK
#15 'local:orbit' 'local:orbit' OK
#16 'local:Cyclotron Inc' 'local:Cyclotron Inc' OK
#17 'local:proj' 'local:proj' OK
#18 'local:(home)' 'local:(home)' OK
#19 'local:ai-presales-agent-main' 'local:ai-presales-agent-main' OK
#20 'local:(other)' 'local:(other)' OK
#21 'local:proj' 'local:proj' OK
#22a '' '' OK
#22b '' '' OK
#23 'local:internal-billing-engine' 'local:internal-billing-engine' OK
#24 'local:Foo' 'local:Foo' OK
#25 'local:proj' 'local:proj' OK
#26 'local:(home)' 'local:(home)' OK
#27 'local:proj' 'local:proj' OK
#28 'local:(home)' 'local:(home)' OK
#29 'local:proj' 'local:proj' OK
#30 'local:(scratchpad)' 'local:(scratchpad)' OK
failures: 0
```

**AC3**: malformed inputs run as both SessionStart and CwdChanged. The cwd column shows the input, truncated to 12 characters, with its length. The result column is the label, truncated to 30 characters, with its length.

| cwd | length | result |
|---|---|---|
| `":"` | 1 | `local:(other)` |
| `"\\\\"` | 2 | `local:(home)` |
| `" "` | 1 | `""` |
| `"C:"` | 2 | `local:(home)` |
| `"x"*10000` | 10000 | `local:xxxx...` (length 106, so the label is cut to 100 characters after the prefix) |
| `"/"` | 1 | `local:(home)` |
| `"~"` | 1 | `local:(home)` |
| `//` | 2 | `local:(home)` |
| `\\h\s` (UNC host and share) | 4 | `local:s` |

The script printed `no raise/bare prefix OK`. That means none of these inputs raised or returned a bare `local:`.

The `\\h\s` case gives `local:s` because the tool call mangled my escaping, so the string that ran was a single-backslash `\h\s`, not a true UNC path. In effect that is a relative path with two segments, `h` and `s`. Example #21 covers the real UNC form.

**AC4**: for every cwd in the examples, each run on its own and as the full history, the label body contains none of `:`, `/`, `\`, `Users`, `OneDrive`, `.claude`, a `C--` slug or `-Users-`. The script printed `leaks: 0`. A separate check that no label equals a username taken from that cwd found none (no `USERNAME LEAK` lines).

**AC5**: run against a temporary `OtelStore` in a temp directory, with `set_trace_callback` counting statements.
```
empty: {} stmts: ['SELECT session_id, event, cwd FROM session_repo_timeline ORDER BY session_id, ts, seq']
{'s1': 'local:Dash', 's3': 'local:(scratchpad)'} stmts: [same single SELECT]
```
I inserted four sessions. `s2` has an empty cwd and is omitted from the result. The script asserted exactly one statement, that it starts with SELECT, and that `db.in_transaction` is false.

The script then hit a Windows `PermissionError` deleting the temp `o.db`, because my script kept the store open. This is a cleanup failure in the scratch script and not in the module. All assertions had already passed.

**Rung 2**: `python -m pytest tests/test_attribute.py -q` → 12 passed. I did not run rung 3.

### Notes for the evaluator
No deviations from the spec. I made three judgement calls where the spec is silent or ambiguous:
- **Claude-internal `claude` segment.** The spec says a `claude` segment "appears after" `Temp`, `tmp` or `T`. I implemented that literally: any `claude` segment after a `Temp`, `tmp` or `T` segment counts. It does not have to be the immediately next segment. Both worked examples have it directly after.
- **Bare `C:\Users` or `/home`.** A cwd with `Users` or `home` as its last segment has no home prefix, because the spec requires a segment 1. It therefore produces `local:Users`. The spec does not cover this and the step 6 guard does not catch it, so I left it as written. Tell me if you want it mapped to `HOME_LABEL` instead.
- **Non-string inputs.** `root_label` wraps its body in `try/except Exception` and returns `""`, to keep the never-raises guarantee for odd inputs. It also coerces `None` events and cwds to `""`.

### Footprint
files_read: 6 (~50000 chars)
commands_run: 4
