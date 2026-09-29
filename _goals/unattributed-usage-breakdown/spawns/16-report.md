**Model (self-reported)**: claude-opus-5-5 (Opus 5.5). The package asked for claude-opus-5, so this is a substitution or alias; I am reporting it as the harness gave it.
## Verdict: PASS (with notes)
VERDICT: PASS (with notes)
**Score**: 4/5

### What I verified
- AC1, new tests pass: ✅ Verified. `python -m pytest tests/test_project_label.py tests/test_export_unattributed.py -q` gave **241 passed in 3.39s**.
- AC3, neighbouring suites pass: ✅ Verified. `python -m pytest tests/test_export.py tests/test_attribute.py tests/test_invoice.py -q` gave **25 passed in 3.58s**.
- AC2, every coverage-map node id exists: ✅ Verified. I ran `pytest --collect-only -q` on the two files and cross-checked all 37 distinct `file::test` ids and all bare test names in the new section. None is missing.
- All 38 worked examples, with the exact labels: ✅ Verified. `test_project_label.py:39-95` checks all 38 against 01-project-label.md:141-178, including #3, #19 and #36 histories, the NUL literal in #37, and #22 as a/b. `test_all_38_worked_examples_are_present` guards the id set.
- Extra walk-up, no-SessionStart, case-insensitive ancestor, Claude-internal (Windows, POSIX, `~/.claude`, `/tmp/claude`, `T/claude`, with and without `scratchpad`), allowlist guard (username, `C--`, `-Users-`, `.`-prefixed → other, `.claude` → scratchpad), truncation at 99/100/101/150, malformed inputs (`":"`, `"\\\\"`, `" "`, `"C:"`, a 10,000-char path, and more): ✅ Verified by reading lines 112-241 and by mutation (below).
- Privacy uses the whole-segment reading: ✅ Verified. `_assert_label_is_private` (test_project_label.py:292-308) and `_assert_private_cells` (test_export_unattributed.py:757-774) compare `Users`/`home` and usernames by segment equality, check slugs, OneDrive, `.claude` and drive letters, and check that no seeded full path (backslash or forward-slash form) appears anywhere in either CSV.
- `load_session_labels`: ✅ Verified. Tests cover the empty timeline, grouping, omission of empty and blank labels, `(ts, seq)` ordering, and exactly one statement via `set_trace_callback`, with no writes or schema change.
- Collision correction is checked against the database AND `invoice.py`: ✅ Verified. `test_collision_store_export_equals_database` compares to `_db_totals`, which reads raw SQL and has an independent `_norm_model`. `test_collision_store_matches_invoice_per_repo_model` compares to `invoice.gather`. There are hard-coded anchors (1270 tokens / 127.0 USD for user `unknown`). No test compares the export to itself.
- The hard-coded pre-change baselines are genuinely pre-change: ✅ Verified. I ran `git show HEAD:billing/otel/export.py` from a scratch copy (imports rewritten) on the test's `_seed_main` store. Line baseline equal: True. Summary baseline equal: True. The old unknown row was (2026-01-03, 2800, 7.75), which matches the conservation anchor. The old headers equal `PRE_CHANGE_*_FIELDS`.
- Tests fail when the product regresses: ✅ Verified with 34 mutations on a scratch copy (repo untouched). The copy was re-verified at 241 passed afterwards.
  - Killed:
    - removing truncation
    - removing the username guard
    - a case-sensitive ancestor match
    - dropping the in-project candidate
    - dropping the outer-container candidate
    - dropping the SessionStart preference
    - requiring a literal `scratchpad`
    - not omitting empty labels
    - a second query
    - removing the slug guard
    - removing the Users/home guard
    - a substring Users guard
    - a 1-segment home prefix
    - not dropping WSL `mnt`
    - overwriting instead of summing cost or tokens
    - never setting the label
    - never setting the source
    - the label reaching attributed rows (non-equivalent form)
    - the source reaching attributed rows
    - unknown decided by bill name
    - span using only `lo`
    - the label leaking into `repo`
    - the summary not split
    - swapped field order
    - labels loaded twice
    - dropped user coalescing
    - dropped unlabelled unknown rows
    - a raw cwd leaking as the label (the privacy test fails on both stores)
    - wrong markup on unknown rows
  - Survived:
    - one equivalent mutant (`sid` is NULL for attributed rows in the SQL)
    - removing only the `try/except` in `root_label`. See the notes.
- No network or ADLS, temp dirs only: ✅ Verified. A grep of both files finds no socket, urllib, requests or azure import. Every store is under `tmp_path`, and `build_and_enqueue` only writes local CSVs and an outbox row.
- Coverage map is append-only and every task 01–03 criterion is present, with GAP reasons: ✅ Verified. `git diff HEAD -- tests/COVERAGE_MAP.md` shows 58 insertions, 0 deletions and one hunk after line 388. Task 01 AC1–5, task 02 AC1–5 and task 03 AC1–3 are all present. The GAPs (02-AC4 timing, 02-AC5, 03-AC1..3, and partial GAPs for 01-AC1 and 02-AC2) each give a reason.
- Write fence: ✅ Verified.
  - `git status --short` shows only `tests/COVERAGE_MAP.md` (M) and the two new test files beyond the pre-existing dirty set.
  - `git diff --quiet HEAD -- tests/conftest.py tests/test_export.py tests/test_attribute.py tests/test_invoice.py` returned exit 0.
  - For the pre-dirty product files, git cannot show whether this task touched them, so I checked mtimes. The task-04 window runs from 13:33:23 (15-context) to 13:41:18 (15-report). Only the three fenced files fall in that window. `project_label.py` (11:42), `export.py` (11:46), both READMEs (13:30) and `conftest.py` (09-24) are all older.
  - Fence delivery: 15-context.md:56-59 carries `## Write fence`, and it matches orchestration-log.md:133.
- Auto-fail triggers: none fired. No third-party import (the tests use pytest and the stdlib only). No secrets. No live service. No change to SQLite or product code.

### Issues found
None at major or blocker level. The minor items are below.

### Notes (non-blocking)
- `root_label`'s `try/except` safety net is not tested on its own. Removing only the `try/except` survives because no input the spec lists actually raises. If the `str()` coercion is removed as well, `test_root_label_never_raises_on_non_string_cells` catches it. Minor: every requirement is met as written, and adding an input that forces a raise would only harden the test.
- The invoice comparison uses one period only (January 2026). The requirement, "per (repo, model, period) equal to invoice.py", holds for the seeded store because every row is in that period. A second month would also cover the period boundary. This is an observation, not a gap in the requirement.
- `test_export_touches_no_network_or_storage_targets` promises more than it checks. It asserts local outputs and outbox state; it does not install a socket guard. The absence of network access rests on the code reading above. Minor because it concerns the test name only.
- The map covers task 01–03 acceptance criteria, as required. Some task-01 requirement-level tests are not cited in it: the `path_segments`, truncation, and walk-up tests. The mandate does not require them. Minor.

### Required fixes (if NEEDS FIXES)
- None.

### Footprint
files_read: 13 (~127,000 chars)
commands_run: 11

Scratch artifacts (outside the repo): `C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\0ab35cbd-cb5c-4db5-9ffc-e0282cc3cab6\scratchpad\mutate.py`, `mutate2.py`, `mutate3.py`, `mut\`.
