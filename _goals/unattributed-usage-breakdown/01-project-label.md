# Task 01: Project-root label derivation (contract + implementation)

## Objective

A new stdlib-only module `billing/otel/project_label.py` exists. Given the cwd history
that `session_repo_timeline` already stores, it returns one privacy-safe label per
session naming the project's root folder (e.g. `local:Dashnoard`), or `""` when there is
nothing to label. It exposes a frozen interface that task 02 consumes. It never writes to
the database, never touches the filesystem, and never touches billing identity.

## Dependencies

- none

```yaml
# --- task ownership contract ---
writes:
  - billing/otel/project_label.py
reads:
  - billing/otel/attribute.py        # TIMELINE_TABLE name and style; not edited
  - billing/otel/otel_store.py       # session_repo_timeline schema; not edited
depends_on: []
owner: implementer
rewrite_semantics: whole-file
eval_depth: full
# full: contract task. Its public interface is consumed by task 02 (export.py).
```

## Interface (frozen by this task)

```python
LOCAL_PREFIX = "local:"
HOME_LABEL = "local:(home)"
SCRATCHPAD_LABEL = "local:(scratchpad)"
OTHER_LABEL = "local:(other)"
CONTAINER_DIRS: frozenset[str]   # lower-case: code, src, source, repos, projects, dev, git, github, workspace

def path_segments(cwd: str) -> list[str]
def is_scratchpad(cwd: str) -> bool          # true for any Claude-internal directory
def root_label(history: Sequence[tuple[str, str]]) -> str
    # history = [(event, cwd), ...] for ONE session, in (ts, seq) order
def load_session_labels(db: sqlite3.Connection) -> dict[str, str]
    # one SELECT over session_repo_timeline; returns {session_id: label} for sessions
    # whose label is non-empty
```

The implementer may add private helpers (leading underscore) but must not change these
names, signatures, or return types.

## Definitions

- **Segments.** `path_segments` splits on both `\` and `/`, strips whitespace from each
  segment, drops empty segments, then drops these leading prefixes:
  - a drive (`C:`);
  - a UNC host and share (`\\host\share`);
  - a leading `~`;
  - WSL: `mnt` followed by a single ASCII letter segment (`[A-Za-z]`, `/mnt/c/...`);
  - Git Bash / MSYS: a single ASCII letter first segment (`[A-Za-z]`) when the original
    path starts with `/` (`/c/Users/...`).

  A cwd that is empty or whitespace-only counts as empty everywhere (step 1 skips it).

  `C:\`, `/`, `~`, `\\host\share` and `/mnt/c` all give `[]`.
- **Home prefix.** If segment 0 is `Users` or `home` (case-insensitive) and a segment 1
  exists, segments 0–1 are the home prefix and segment 1 is the **username** (this covers
  8.3 names like `ZANECH~1` because it is positional). If segment 0 is `root`, or is a
  bare `Users` / `home` with nothing after it, segment 0 alone is the home prefix.
  Otherwise there is no home prefix.
- **Usernames (for the guard).** Every segment that directly follows a `Users` or `home`
  segment at ANY position in any of the session's cwds, scanning the raw split of each
  cwd (before any drive / UNC / WSL prefix is dropped), so a UNC share named `Users`
  still contributes the following segment.
- **Outer folder.** A segment that starts with `onedrive` or `visual studio `
  (case-insensitive), or equals (case-insensitive) `Desktop`, `Documents`, `Downloads`,
  `Library`, `CloudStorage`.
- **Outer zone.** The home prefix (if any), followed by the longest run of segments that
  are each an outer folder or a `CONTAINER_DIRS` segment, in any order. The zone may
  start at segment 0 with no home prefix (drive-level `D:\Code\...`). `outer_len` is the
  number of segments in the zone. The zone **has an outer container** if the run
  contains at least one `CONTAINER_DIRS` segment.
- **In-project container.** A `CONTAINER_DIRS` segment at an index greater than
  `outer_len`.
- **Claude-internal directory** (`is_scratchpad`): any segment equal to `.claude`
  (case-insensitive), or a segment equal to `claude` that appears after a `Temp`, `tmp`
  or `T` segment (the last covers macOS `$TMPDIR`). The literal word `scratchpad` is NOT
  required.
- **Ancestor.** A is an ancestor-or-self of B when A's segments are a case-insensitive
  prefix of B's segments.

## Root algorithm (per session)

1. **Start folder** = cwd of the first `SessionStart` row with a non-empty cwd; if none,
   the first row with a non-empty cwd. No such row → `""`.
2. Start is Claude-internal → `SCRATCHPAD_LABEL`.
3. Let `S = path_segments(start)`, `o = outer_len(S)`. If `len(S) <= o` (this includes
   `S == []`, e.g. `C:\`, `C:\Users\Derek`, `...\OneDrive - Cyclotron Inc`,
   `C:\Users\Derek\src`) → `HOME_LABEL`.
4. Candidate indices into `S`, each `>= o`:
   - **a. Outer-container candidate:** if the outer zone has an outer container,
     candidate `o` (the first folder after the zone).
   - **b. In-project container candidate:** for the first in-project container at index
     `i` (`i > o`), candidate `i - 1` (its parent).
   - **c. Ancestor candidate:** among the session's cwds that are non-empty,
     not Claude-internal, ancestors-or-self of the start folder, and longer than `o`
     segments, take the one with the fewest segments `L`; candidate `L - 1`. (The start
     folder itself always qualifies, so this candidate always exists.)
5. Root index = the smallest candidate. The chosen segment is `S[root]`, original case.
6. **Allowlist guard.** If the segment contains `:`, `/` or `\`; starts with `.`; matches
   `^[A-Za-z]--` or starts with `-Users-` (Claude project-slug shapes); contains
   `onedrive` (case-insensitive); equals (case-insensitive) `Users` or `home`; contains
   any control character (code point < 32); or equals (case-insensitive) any username
   found in any of the session's cwds → `OTHER_LABEL`. (Segment equality, not
   substring: `users-api` is an allowed label.)
7. Otherwise return `LOCAL_PREFIX + segment`, truncated to 100 characters after the
   prefix.

Visits outside the root (cwds that are not ancestors-or-self of the start folder) never
change the label. `root_label` must never raise for any input (any strings, any length,
empty history) and must never return a bare `LOCAL_PREFIX`.

## Requirements (exhaustive — the evaluator verifies every item)

- [ ] The frozen interface exists exactly as above; stdlib imports only.
- [ ] `path_segments`, the home prefix, outer zone, outer/in-project container,
      Claude-internal, and ancestor definitions are implemented as written.
- [ ] The root algorithm steps 1–7 are implemented as written.
- [ ] `root_label` never raises and never returns a bare prefix (checked against the
      worked examples plus malformed inputs: `None`-free but odd strings such as `":"`,
      `"\\\\"`, `" "`, `"C:"`, a 10,000-character path).
- [ ] `load_session_labels` runs exactly one query:
      `SELECT session_id, event, cwd FROM session_repo_timeline ORDER BY session_id, ts, seq`
      (the table name taken from `attribute.TIMELINE_TABLE`), groups in Python, calls
      `root_label` once per session, and omits sessions whose label is `""`.
- [ ] `load_session_labels` returns `{}` on an empty timeline, and never writes, commits,
      or opens another connection.

## Worked examples (must hold)

| # | history (event, cwd) | label |
|---|---|---|
| 1 | SessionStart `C:\Users\DerekMcConnell\OneDrive - Cyclotron Inc\Code\Dashnoard` | `local:Dashnoard` |
| 2 | SessionStart `C:\Users\DerekMcConnell\OneDrive - Cyclotron Inc\Code\Dashnoard\OfficeDashboard\backend` | `local:Dashnoard` |
| 3 | #1 start, then CwdChanged `C:\Users\DerekMcConnell\src\orbit-local` and `C:\Users\DerekMcConnell\src\orbit-wt\google\apps\api` | `local:Dashnoard` |
| 4 | SessionStart `C:\Cyclotron\Insights Agent\ai-presales-agent-main`, CwdChanged `...\ai-presales-agent-main\ai-presales-agent-main` | `local:ai-presales-agent-main` |
| 5 | SessionStart `C:\Users\SumitBhatia\.claude\projects\C--Cyclotron-Insights-Agent-ai-presales-agent-main\scratchpad` | `local:(scratchpad)` |
| 6 | SessionStart `C:\Users\SumitBhatia\.claude\projects\C--Users-SumitBhatia-OneDrive---Cyclotron-Inc-proj` | `local:(scratchpad)` |
| 7 | SessionStart `C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-x\0ab35cbd-cb5c-4db5-9ffc-e0282cc3cab6` | `local:(scratchpad)` |
| 8 | SessionStart `C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-x` | `local:(scratchpad)` |
| 9 | SessionStart `C:\Users\DerekMcConnell` | `local:(home)` |
| 10 | SessionStart `C:\` | `local:(home)` |
| 11 | SessionStart `/home/derek/src/orbit/apps/web` | `local:orbit` |
| 12 | SessionStart `C:\Users\DerekMcConnell\src\orbit-wt\google\apps\api\src\connectors` | `local:orbit-wt` |
| 13 | SessionStart `C:\Cyclotron\proj\src` | `local:proj` |
| 14 | SessionStart `C:\Cyclotron\proj\src\components\ui` | `local:proj` |
| 15 | SessionStart `C:\Users\Derek\orbit` | `local:orbit` |
| 16 | SessionStart `C:\Users\Derek\Cyclotron Inc` | `local:Cyclotron Inc` |
| 17 | SessionStart `/Users/derek/Library/CloudStorage/OneDrive-CyclotronInc/Code/proj` | `local:proj` |
| 18 | SessionStart `/Users/derek/Library/CloudStorage/OneDrive-CyclotronInc` | `local:(home)` |
| 19 | #4 start, then CwdChanged `C:\` and `C:\Users\SumitBhatia` | `local:ai-presales-agent-main` |
| 20 | SessionStart `C:\Users\derek\projects\derek` | `local:(other)` |
| 21 | SessionStart `\\fileserver\share\team\proj` | `local:proj` |
| 22 | `[]` and `[("CwdChanged", "")]` | `""` |
| 23 | SessionStart `C:\Users\Zane\source\repos\internal-billing-engine` | `local:internal-billing-engine` |
| 24 | SessionStart `C:\Users\Derek\Documents\Visual Studio 2022\Projects\Foo\Foo` | `local:Foo` |
| 25 | SessionStart `/mnt/c/Users/Derek/src/proj` | `local:proj` |
| 26 | SessionStart `/mnt/c/Users/Derek` | `local:(home)` |
| 27 | SessionStart `/c/Users/Derek/source/repos/proj/src/lib` | `local:proj` |
| 28 | SessionStart `D:\Code` | `local:(home)` |
| 29 | SessionStart `D:\Code\proj` | `local:proj` |
| 30 | SessionStart `/var/folders/ab/xyz/T/claude/-Users-derek-Code-proj/abc123/scratchpad` | `local:(scratchpad)` |
| 31 | SessionStart `C:\Users` | `local:(home)` |
| 32 | SessionStart `/home` | `local:(home)` |
| 33 | SessionStart `D:\Code\Users` | `local:(other)` |
| 34 | SessionStart `\\host\Users\bob` | `local:(other)` |
| 35 | SessionStart `/1/Code/proj` | `local:1` |
| 36 | SessionStart `"  "`, then CwdChanged `C:\Y\proj` | `local:proj` |
| 37 | SessionStart, Python literal `"C:\\Cyclotron\\bad\x00name"` (segments `Cyclotron`, `bad<NUL>name`) | `local:(other)` |
| 38 | SessionStart `/home/derek/Code/users-api` | `local:users-api` |

Note for #19: zero-segment and outer-zone cwds are not "longer than `o`", so they never
become the ancestor candidate. Known accepted behaviour (documented, not a defect): a
session that visits a real ancestor outside the outer zone (e.g. `C:\Cyclotron`) takes
that ancestor as its root.

## Acceptance Criteria

1. `billing/otel/project_label.py` exposes exactly the frozen interface, with no import
   outside the standard library — verification: command output
   (`python -c "import billing.otel.project_label as p; print(p.LOCAL_PREFIX, p.HOME_LABEL, p.SCRATCHPAD_LABEL, p.OTHER_LABEL, sorted(p.CONTAINER_DIRS))"`
   plus an import scan of the file).
2. All 38 worked examples return the stated label — verification: command output (a
   one-off `python` script run by the implementer; the permanent tests land in task 04).
3. `root_label` does not raise and never returns a bare `local:` for the malformed inputs
   listed in Requirements — verification: command output.
4. For every cwd string in the worked-examples table (not just their outputs), the label
   produced never contains `/`, `\`, a `:` other than the one in the `local:` prefix,
   `Users`, `OneDrive`, `.claude`, a `C--` or `-Users-` slug, or a username —
   verification: command output.
5. `load_session_labels` issues one SELECT, returns `{}` on an empty timeline, and omits
   sessions with an empty label — verification: command output against a temporary
   `OtelStore` in a temp directory (use `sqlite3.Connection.set_trace_callback` to count
   statements).

## Files to Read

- `CLAUDE.md` — hard constraints (stdlib only; attribution resolved at query time)
- `README.md` — the `attribute.py` and `normalize.py` bullets (around lines 150–170)
- `billing/otel/attribute.py` — `TIMELINE_TABLE`, module style
- `billing/otel/otel_store.py` lines 60–95 — `session_repo_timeline` schema and index
- `.claude/skills/test-ladder/SKILL.md` — rungs 1–2

## Files to Create / Change

- `billing/otel/project_label.py` — new module, whole file.

## Constraints

- Must: stdlib only (`re`, `sqlite3`, `typing` / `collections.abc` at most); pure
  functions apart from `load_session_labels`; at most one short comment line where the
  why is non-obvious.
- Must NOT: edit `attribute.py`, `otel_store.py`, or any other file; persist anything;
  touch the filesystem to resolve paths; import from `billing/` modules other than
  `attribute` (for `TIMELINE_TABLE`).

## Verification

- A one-off `python` script covering the 38 worked examples, the malformed inputs, the
  privacy check and `load_session_labels` against a temp `OtelStore`.
- Rung 2: `python -m pytest tests/test_attribute.py -q` still passes.
