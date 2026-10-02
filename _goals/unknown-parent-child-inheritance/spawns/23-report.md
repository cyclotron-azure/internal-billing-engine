**Model (self-reported)**: claude-sonnet-5-5
## Task Complete: README alignment for unknown-parent-child-inheritance (docs-only)

### Edits (all in README.md; verified against billing/otel/attribute.py docstrings, _blocked/_norm/_inherit_table, resolved_repo/resolved_view, otel_store.py:718 and bill.py:273-278)
1. `attribute.py` bullet (~l.153): appended an "Ancestor inheritance" description. It covers: effective row (as-of, else first) is unknown; project-level same-or-ancestor folder; exactly one related real repo; ancestor-only; before-or-after rows count; 2+ repos stay unknown; DirectoryAdded never an anchor; session id `unknown` never inherits; blocked anchors (roots, home, top-level, generic containers, onedrive*, visual studio *); case-insensitive and separator-insensitive comparison; ASCII-only lower(); query-time only; a late second related repo can flip usage back to unknown; inherited rows report `attribution_source = timeline`. The fallback-chain sentence is untouched.
2. Flow diagram (~l.289): added "an `unknown` row may inherit one related real repo".
3. `attribution_source` table, `timeline` row: now also covers unknown usage that could not inherit (blocked anchor, child of a real repo, 2+ related repos, only a DirectoryAdded anchor, or session id `unknown`).
4. `unattributed_project` section: added a short paragraph after the "`wrapper` is not expected..." line. Ancestor-start sessions that later enter exactly one real repo no longer produce unknown rows or a `local:<folder>` label, and history relabels after re-export.
5. "Accepted mislabels": reworded "no-remote folder" to "no-remote child folder". Added a clause that inheritance is ancestor-only, so that direction stays unknown, while an unknown ancestor start followed by one real repo below it now inherits.
6. Developer-cost section (~l.508): softened "else repo=unknown" with an exception for ancestor starts that later enter exactly one real repo (recovered at query time).
7. Pilot "captured->tagged" bullet: the unknown bucket "shrinks as ancestor-start sessions that later enter one real repo are recovered".
8. Capacity checkpoint: every `resolved_view` builds the inheritance lookup over the whole `session_repo_timeline` regardless of the date window. Cost grows with total timeline rows, and UserPromptSubmit adds rows on every prompt. Measured about 0.24 s per 100,000 datapoints on a synthetic store (100k datapoints, 40,300 timeline rows), stated as not production data. Source: `_goals/.../spawns/21-report.md` lines 23 and 86.
9. `bill.py` bullet: the multi-repo list is diagnostic only. `multi_repo_sessions()` uses raw timeline repos, so an inheriting session still prints as split while billing wholly to the real repo. Amounts are unaffected. Verified against otel_store.py:718-731 (raw `session_repo_timeline` repos) and bill.py:273-278.

### Beyond the nine items
- `bill.py` bullet: "flags `unknown` usage (sessions with no git remote)" became "(sessions with no git remote that did not inherit a real repo)".
- Left unchanged: `bill.py` still prints "'no_remote' = ran outside a git repo" (code, not README). I did not edit any other README statements.

### Omitted
- The task brief cited "0.25-0.87 s per 100k". I found only 0.244 s in 21-report.md, so I omitted the 0.87 figure and cited 0.24 s only.

### Verification
- `git status --short` → ` M README.md`, ` M billing/otel/attribute.py`, `?? _goals/unknown-parent-child-inheritance/`, `?? tests/test_attribute_inheritance.py`. Only README.md was edited by me.
- `git diff --stat -- README.md` → 1 file changed, 24 insertions(+), 9 deletions(-).
- Line endings: no CR characters in the diff, so LF is preserved.
- Nothing under `_goals/` or `_research/` was written, and no git state-changing commands were run.

### Footprint
files_read: 7 (~75000 chars)
commands_run: 1
