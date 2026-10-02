**Model (self-reported)**: claude-opus-5-5

## Verdict: APPROVED
**Score**: 4/5

The change meets every Success Criterion. The only exceptions are the deviations the user already decided (absolute performance gate, repo-based tie-break, single-LEFT-JOIN view, sanitised aliases, larger test scope). No auto-fail trigger fired and I found no blocking issue. I held back the fifth point for three reasons: the full-suite regression result (terminal spawn #22) has not reported yet, so I could not verify it; some non-blocking diagnostic drift remains (notes below); and a few residual inheritance paths need the user's explicit acceptance at delivery.

### Success Criteria (each checked with fresh evidence)

| # | Criterion | Evidence | Status |
|---|---|---|---|
| 1 | Nate inherits R, source `timeline` | Scratch store `audit.db`, via `resolved_view`: nate @09:59 (before the first row), @10:05 and @10:15 all give `github.com/acme/wealthspire-ticketing`, source `timeline`, in both token_usage and cost_usage. Also pinned by `test_nate_unknown_ancestor_inherits_real_child_repo` and `test_forward_only_datapoint_before_first_row_inherits`. | ✅ Verified |
| 2 | Reverse case (real parent, unknown child) stays unknown | `test_reverse_real_parent_unknown_child_stays_unknown[False/True]` passes. Code: `attribute.py:209-210` keeps only real rows at or below `u`. | ✅ Verified |
| 3 | Unrelated siblings stay unknown | Scratch Derek case (`...\Code\Dashnoard` unknown, alternating with `...\Code\src\orbit-local` real): @10:05 and @10:25 give `unknown`/`timeline`, @10:15 gives orbit. | ✅ Verified |
| 4 | Two distinct qualifying repos give unknown | `attribute.py:200-201` (`count>0 AND min=max`); `test_two_distinct_qualifying_repos_stay_unknown` passes. In the perf store, 3 sub-repos per session left 45% of rows unknown, as designed. | ✅ Verified |
| 5 | Non-unknown effective row keeps its own repo | `attribute.py:194-195`: a non-unknown row maps to its own repo. `test_preservation_a/b/c`, `test_no_unknown_rows_resolves_as_before_the_change` and `test_null_repo_effective_row_falls_back...` pass. | ✅ Verified |
| 6 | Home, container, outer, root and top-level anchors never inherit | `_blocked` at `attribute.py:149-176`; the blocklist parametrised tests, including all 19 container names one by one, pass. Scratch irfan case: `C:\Project_Burn` stays **unknown** (top-level anchor blocked). | ✅ Verified |
| 7 | No qualifying row stays unknown; desktop-scratch still wins | Scratch zane3 transcript session gives `unknown`/`desktop-scratch`; zane1 (launched in the `...\projects` container) stays unknown. Tests `test_only_unknown_session_stays_unknown` and `test_transcript_session_without_qualifying_real_row_is_desktop_scratch` pass. | ✅ Verified |
| 8 | Case, separator, trailing-slash and prefix-lookalike handling | `_norm` at `attribute.py:146` is a raw string, so the backslash reaches SQL as a single `'\'`. The normalisation, backslash, prefix-lookalike and wildcard-inert tests pass. Scratch zane2 (same-folder flake) inherits. | ✅ Verified |
| 9 | Empty/NULL cwd never relates; DirectoryAdded never anchors; sid `'unknown'` never inherits | `attribute.py:198` and `:206-208`; the empty/NULL-cwd, DirectoryAdded and session-id tests pass. | ✅ Verified |
| 10 | Works for token and cost usage via the unchanged `resolved_view`, any alias | Scratch run over both tables: row counts 20 = 20, and view equals the standalone `resolved_repo('q')`/`attribution_source('q')` on every row (0 mismatches). Alias and quoted-alias tests pass. | ✅ Verified |
| 11 | No regression; signatures unchanged | Rung-2 set plus the new file: **332 passed in 30.88s** (my run). Signatures at `attribute.py:229, 267, 293` are unchanged. The full `python -m pytest -q` is not verified (spawn #22 has no report; per instructions I did not duplicate it). | ✅ rung-2 / ⚠️ full suite |
| 12 | Perf gate (user deviation: absolute ≤ 1.0 s per 100k per statement) | My fresh synthetic store: 100,000 datapoints, 2,001 sessions, 40,300 timeline rows, one heavy session (300 timeline rows, 20,000 datapoints). `resolved_view` GROUP BY scan median of 3 runs: **0.244 s per 100k**. I did not re-measure the 3x ratio, because the user replaced it. | ✅ Verified (absolute) |
| 13 | Nothing persisted; query time only; stdlib only | The only import is `from __future__ import annotations` (`attribute.py:78`). The SQL is SELECT-only: no DDL, no writes, no registered functions. `git status` shows no other file changed. | ✅ Verified |

### Cross-task integration
- **Working tree** → ✅ Verified. `git status --short` shows exactly ` M billing/otel/attribute.py`, `?? _goals/unknown-parent-child-inheritance/` and `?? tests/test_attribute_inheritance.py`. `git hash-object billing/otel/attribute.py` = `38d2db20fe79911ed9c9c6e49f714958ee527021`, matching the hand-off hash. Nothing stray in the repo; my scratch DBs are in the scratchpad only.
- **Tests run against the as-built code** → ✅ Verified. The tests import `resolved_view`, `resolved_repo` and `attribution_source` directly, use a real temp `OtelStore`, and do not mock the SQL. No network or socket use: grep for `socket`, `urlopen`, `requests` and `http` finds nothing.
- **Consumers** → ✅ Verified. `bill.py`, `invoice.py`, `export.py`, `reconcile.py` and `deploy/unknown-report.py` all still call `resolved_view(table)` unchanged. `deploy/unknown-report.py --db <scratch audit.db>` ran, exit 0. It lists Dashnoard, Project_Burn, (home), the non-ASCII case and desktop-scratch as unknown, and the inherited sessions correctly drop out of the unknown report.
- **Cowork pipeline** → ✅ Verified unchanged. `cowork_attribute.py` has its own copies of the queries and imports nothing from `attribute.py`.
- **Hard constraints** → ✅ Verified:
  - No third-party import.
  - Single-connection SQLite untouched.
  - No secret in either file (grep).
  - No new table, column or index.
  - Attribution is not materialised.

### README statements Phase 6 must correct (README.md is ground truth and is currently stale)
1. **README.md:153 (`attribute.py` bullet).** It describes only the as-of join and the fallback chain. Add: the ancestor/same-folder inheritance for an unknown effective row; the single-repo rule; the anchor blocklist (roots, home, top-level, containers); the DirectoryAdded and session-id `'unknown'` exclusions; that `lower()` is ASCII-only; that resolution stays query-time only. Also extend the retroactivity sentence: a late *second* related repo can flip past inherited usage back to `unknown`. The `desktop-scratch → timeline → absent → no_remote → wrapper` order is still correct.
2. **README.md:289 (flow diagram, "as-of join: which repo was active per datapoint").** Should also mention inheritance.
3. **README.md:371 (`attribution_source` table, `timeline` row).** "The repo hook fired, but the folder it reported has no git remote" is now incomplete. `timeline` on an `unknown` row now also means one of: the folder could not inherit (blocked anchor, a child of a real repo, 2+ related repos, only a DirectoryAdded anchor, or session id `'unknown'`).
4. **README.md:364-365 and 378-412 (`unattributed_project` section).** This should say that sessions which start in a project-level ancestor folder and `cd` into one real repo no longer produce `unknown` rows, so they no longer get a `local:<folder>` label. Nate's `local:wealthspire` disappears from history after re-export.
5. **README.md:414-417 ("Accepted mislabels").** The statement that a real-repo start followed by a no-remote folder labels those `unknown` rows with the start folder's name is still true (the child stays unknown). It should be reconciled with the new rule so readers do not assume the reverse direction also stays unknown.
6. **README.md:508-510.** "Sessions must start inside a git repo with an `origin` remote (else `repo=unknown`)" is no longer strictly true: a project-level ancestor start is recovered once the session `cd`s into exactly one real repo below it.
7. **README.md:566-568 (captured→tagged is "the `unknown` bucket (sessions outside a git repo)").** The bucket shrinks, so the wording needs a small update.
8. **README.md:606-608 (Capacity checkpoint).** Add that every `resolved_view` statement now builds an inheritance table over the WHOLE `session_repo_timeline`, whatever the query's date window. Cost grows with total timeline rows; UserPromptSubmit re-tagging adds rows on every prompt.
9. **README.md:160 (`bill.py` bullet: "prints … every multi-repo session").** `multi_repo_sessions()` (`otel_store.py:718-731`) reads raw timeline repos, so an inherited session still prints as "usage split across repos: [R, unknown]" although it bills 100% to R. Phase 6 should document this or flag it.
10. **Outside README, flag only.**
    - `deploy/README.md:198-201` ("as-of join … usage splits across the repos") is also stale, but `deploy/` is fenced by goal.md, so the user must decide whether Phase 6 may touch it.
    - The `billing/otel/cowork_attribute.py:132` docstring ("Mirrors attribute.py's real fallback chain") is now inaccurate. Cowork is out of scope.
    - Task file AC5 uses `C:\mono` vs task 02's `C:\dev\mono` (Phase 3 note): results are identical, but the wording should be aligned.

### Delivery notes (listed, not decided)
- **irfan `C:\Project_Burn`:** confirmed it stays `unknown`, because a top-level folder under a drive is a blocked anchor. The same project one level deeper (`D:\work\Project_Burn`) does inherit (scratch result: `github.com/cyclotron/burn-app`).
- **Deny-list residuals that inherit** (scratch results):
  - `C:\Users\x\Acme` → inherits
  - `/media/u/disk/proj` → inherits
  - `~/proj` → inherits
  - `C:\Users\x\Desktop\proj` → inherits
- **Non-canonical paths inherit:**
  - relative `wealthspire` → inherits
  - trailing-dot `C:\dev\proj\.` → inherits
  - `C:\dev\proj\..` → inherits, although it really means `C:\dev`, a blocked container. Equality/substr comparison does not resolve `..`. Low practical risk, because the hook reports the process's absolute cwd, but it is a strict-rule gap.
- **ASCII-only `lower()`:** `C:\dev\Ärger` vs `C:\dev\ärger\sub` stays `unknown` (under-inherits, conservative).
- **Retroactive:** regenerating past invoices/exports re-resolves earlier `unknown` usage to the inherited repo. A late second related repo flips it back. Persisted invoices are not mutated, but a re-run differs from what was sent.
- **Cowork pipeline** stays on the old rule (separate attribution path, accepted inconsistency).
- **`deploy/unknown-report.py`** works against the new code (ran on the scratch store, exit 0).
- **The VM runs stale code.** Nothing is deployed; the `docker-compose.yml` merge conflict there is unresolved and out of scope.
- **DirectoryAdded rows:** the hook (`deploy/claude-repo-tag.py:84-100`) records the payload `cwd`, not the added directory. Excluding DirectoryAdded as an anchor is extra caution, not a correctness need. A DirectoryAdded row can still be the *effective* row, as before the change.
- **Subagent rows:** these share the session_id (`agent_id` is posted but not used here). A subagent working in a real child repo can therefore cause the main loop's unknown ancestor folder to inherit. This is consistent with the rule, but worth stating.

### Blocking issues
None.

### Notes (non-blocking)
1. **[minor] `tests/test_attribute_inheritance.py:484-487`.** `test_container_name_vocabulary_is_distinct_and_complete` asserts only on the test file's own literal list, never on `attribute._CONTAINER_NAMES`. It cannot fail because of a source change, and a name *added* to the source goes unguarded. It is minor because each of the 19 names has its own blocking test (lines 490-509), so removing a name from the source still fails the suite.
2. **[minor] `tests/test_attribute_inheritance.py:479`.** The `_win_case` docstring example says `'cloudstorage' -> 'CloudStorage'`, but the code produces `'CloudsTorage'`. Comment only; the test still exercises mixed case.
3. **[minor] `billing/otel/otel_store.py:718-731` via `bill.py:273-275`.** The MULTI-REPO SESSIONS diagnostic now over-reports inherited sessions as split. It is diagnostic output only (no billing amount affected) and outside the write fence, so it is minor; it is listed in README item 9.
4. **[minor] Full-suite regression (rung 3) not verified by me.** It waits on terminal spawn #22. The orchestrator must confirm that result before Phase 6/7. Rung-2 plus the new file is green (332 passed).

### What I verified (commands run)
- `git status --short` and `git hash-object billing/otel/attribute.py` → tree is exact, hash `38d2db20…`.
- `python -m pytest <rung-2 set> tests/test_attribute_inheritance.py -q` → `332 passed in 30.88s`.
- Scratch `audit_cases.py` (the motivating cases and residuals over token and cost usage, view vs standalone) → results in the tables above; 0 mismatches; view row count equals table row count (20/20).
- `python deploy/unknown-report.py --db <scratch>/audit.db` → exit 0, sensible unknown breakdown.
- Scratch `audit_perf.py` (100k datapoints, 2,001 sessions, 40,300 timeline rows, heavy tail) → median 0.244 s per 100k.
- Imports, consumers and secrets: grep for imports, `resolved_view` callers, `cowork_attribute` independence, and secret patterns → as stated above.

Scratch files are in the scratchpad directory only: `audit_cases.py`, `audit.db`, `audit_perf.py` and `audit_perf.db` under `C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\efecdfb4-de1b-4a6f-9f68-641f5525f749\scratchpad\`.

### Footprint
files_read: 13 (~100,000 chars)
commands_run: 17
