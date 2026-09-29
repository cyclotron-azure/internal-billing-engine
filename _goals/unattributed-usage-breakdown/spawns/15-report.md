**Model (self-reported)**: claude-sonnet-5 (Sonnet 5.5)
## Test Task Complete

Everything is green: both rung-2 commands pass, no product behaviour contradicted the spec, and no fence escalation was needed.

### Files
- Created `C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\tests\test_project_label.py`: 210 tests, LF line endings.
- Created `C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\tests\test_export_unattributed.py`: 31 tests, LF line endings.
- Appended one section, `# Coverage map: unattributed-usage-breakdown`, to `C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\tests\COVERAGE_MAP.md`. `git diff --numstat` shows 58 additions and 0 deletions, so no other section changed.
- No product code, `conftest.py`, or existing test was touched. I ran no git command that changes the tree or index.

### Coverage map
| Unit under test | Tests written | Error/edge paths covered |
|---|---|---|
| `project_label.root_label` | All 38 worked examples as parametrized cases (39 ids, with 22a/22b). Also the deep-start, outer-container, no-SessionStart, case-insensitive ancestor and outside-visits cases. | Malformed inputs (12 strings x 4 event names, including `":"`, `"\\\\"`, `" "`, `"C:"`, NUL, and 10,000-character paths) never raise and never return a bare `local:`. Also None cells, whitespace-only cwds, and truncation at 99/100/101/150 characters. |
| `project_label.is_scratchpad`, `path_segments` | 11 Claude-internal cases (Windows and POSIX, `.claude`, `Temp\claude`, `/tmp/claude`, `T/claude`, with and without `scratchpad`), 5 negatives, 7 bare-root cases and 11 prefix-stripping cases. | Allowlist guard: username, slug, `-Users-`, dot-prefixed, OneDrive, embedded colon, bare `Users`. Whole-segment ruling checked (`users-api`, `Project.Users`, `homework` stay legal). |
| Privacy property | Every worked-example history plus extras and the malformed set: no `/`, `\`, extra `:`, `.claude`, OneDrive, `C--` or `-Users-` slug, bare `Users`/`home` segment, or username. | Usernames are re-derived independently in the test. |
| `load_session_labels` | Empty timeline gives `{}`. Multi-session grouping. Empty and blank labels omitted. `(ts, seq)` ordering with out-of-order inserts. | Exactly one SELECT (via `set_trace_callback`), no writes, no schema change, and recomputed on every call. |
| `export` headers | Field lists checked against hard-coded pre-change lists. CSV headers checked. The `main()` CLI path with `--no-enqueue`. | `--no-enqueue` leaves the fabric outbox empty. |
| `export.build`, attributed rows | Line and summary rows equal hard-coded pre-change baseline dicts (with `generated_at` and the two new columns stripped). CSV new cells are `""`. | An attributed session whose timeline cwd would label as `local:globex-api` still gets `""`. |
| `export.build`, unknown split | `timeline`/`local:Dashnoard`, `absent`/`""`, `no_remote`/`""` and `desktop-scratch`/`local:(scratchpad)` land in separate rows. The summary splits the same way. `attribution_source` matches `resolved_view()`, and `wrapper` never appears on unknown rows. | Merge of two sessions with the same class and label, with a combined span. Span per row equals min/max of its own datapoints. |
| Conservation and collision correction | Export totals equal the DB totals per (day, model, user). Collision store (NULL, `""` and `"unknown"` users; `claude-sonnet-5`, `[1m]` and dated models; blank and NULL models) sums instead of overwriting: user `unknown` gets 1270 tokens and 127.0 USD. Export per (repo, model) equals `invoice.gather` on both stores. | Hard-coded anchor totals guard against a bug in the DB-total helper. |
| Isolation and store rules | `repo_name_map` override of a real repo leaves the split unchanged. Mapping a real repo to the name `unknown` stays unsplit. Mapping the `unknown` key renames the bill but keeps the split. The label never appears in `repo` or `repo_key`. | `load_session_labels` is called once per `build()`, and `resolved_view` is called once each for `cost_usage` and `token_usage`. `build()` is read-only (SELECT/WITH only). A late timeline row relabels on the next build. |
| Privacy of exports | The two new columns and both full CSVs, on the main store and a hostile-cwd store. Seeded full paths are absent (forward-slash variants too), along with `Users`, OneDrive, `.claude`, drive letters, slugs and usernames. | Hostile cwds collapse to `local:(home)`, `local:(other)`, `local:(scratchpad)` and `local:payments` only. |
| `invoice.py` | Totals hard-coded and unchanged after `build_and_enqueue`. Billing names contain no label. | None. |

### Verification
- Rung 1: `python -m pytest tests/test_project_label.py tests/test_export_unattributed.py -q` gives **241 passed in 4.27s**.
- Rung 2: `python -m pytest tests/test_export.py tests/test_attribute.py tests/test_invoice.py -q` gives **25 passed in 3.96s**.
- `pytest --collect-only -q` collects **241 tests** across the two files: 210 in `test_project_label.py` and 31 in `test_export_unattributed.py`. All 31 export test ids are listed in that run. Of the project-label ids, I read the non-parametrized ones and the parametrized ids for the Claude-internal, allowlist-guard, truncation, `path_segments` and privacy extras; the 39 worked-example ids and the malformed-input ids were filtered out of what I viewed.
- I did not run the full suite, per the rung rule.

### Coverage-map section (summary)
- **Task 01, criteria 1–5:** mapped to node ids. Criterion 1's `python -c` print and import scan are marked GAP (partial), since they are command-output checks.
- **Task 02, criteria 1–3:** mapped to node ids. Criterion 2's literal `git show HEAD` scratch-copy diff is GAP (partial); hard-coded baselines stand in for it.
- **Task 02, criterion 4:** GAP, because the wall-clock timing ratio is a command-output measurement and a timing assertion would be flaky. The structural guarantees behind it are tested.
- **Task 02, criterion 5:** GAP, a command-output property of the neighbouring suites.
- **Task 03, criteria 1–3:** all GAP (doc review or command output).
- **Task 04:** its own three criteria are noted in the section.

### Product findings
None. Every worked example, the collision correction and the split behaved as specified.

### Gaps
- Task 02's timing ratios, the pre-change diff and the Task 03 README criteria are GAP by design, as listed above.
- The module docstring update in `export.py` is not asserted by any test.

### Footprint
files_read: 14 (~215,000 chars)
commands_run: 12
