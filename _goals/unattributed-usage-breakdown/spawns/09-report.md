**Model (self-reported)**: claude-opus-5-5 (Opus 5.5; the package requested claude-opus-5, and the harness reports Opus 5.5)

VERDICT: NEEDS FIXES
## Verdict: NEEDS FIXES
**Score**: 3/5
**failure_class:** criteria-defect

The implementation is sound. On every input that has no collisions it meets every requirement and AC, and I checked each one myself. The single blocking item is the `+=` change. On one class of real inputs it changes attributed rows and billed dollars in Fabric. The task's criteria, read literally, forbid that change, yet the only way to meet them is to reproduce a pre-existing data-loss bug. The orchestrator should take this to the user. The implementer should not be re-run blindly.

### What I verified
- Write fence → ✅ Verified. `git status --short` shows ` M billing/otel/export.py`, ` M client-package.zip`, `?? _goals/...`, `?? billing/otel/project_label.py`. `git diff --stat` covers export.py (+42/-26) and client-package.zip. By mtime, client-package.zip was last written 2026-09-25 09:41, well before this task. project_label.py was written 11:42:03, which is task 01, before the 08-context at 11:45:52. export.py was written 11:46:34, inside spawn 08's window. The package carried a `## Write fence` section.
- attribute.py, invoice.py, bill.py, normalize.py, tests/ and README.md are untouched → ✅ Verified. `git diff --quiet HEAD -- <those>` gave exit 0.
- Stdlib only, single connection → ✅ Verified. The only new import is `from .project_label import load_session_labels` (export.py:36), and project_label imports only re, sqlite3 and collections.abc. All queries go through `store.db`. No threading, no `connect(`, no `check_same_thread` in the diff.
- Schema (AC1) → ✅ Verified. I ran `python -m billing.otel.export --db <tmp> --out-dir <tmp> --no-enqueue` and got rc 0. The summary header ends `...,generated_at,attribution_source,unattributed_project`, and the line header ends the same way. `new.SUMMARY_FIELDS[:-2] == old.SUMMARY_FIELDS` and `new.LINE_FIELDS[:-2] == old.LINE_FIELDS` are both True (export.py:41-48).
- AC2: attributed rows identical, unknown rows split → ✅ Verified on a store with no collisions. The pre-change module came from `git show HEAD:...` into the scratchpad as `ev09/export_old.py`, with imports rewritten to `billing.otel.*`. The seeded store has an attributed timeline session, an attributed wrapper session, an unknown session whose timeline starts in `C:\Users\dev\Code\Dashnoard\OfficeDashboard\backend`, an `absent` session and a `no_remote` session.
  - Summary: attributed old=2, new=2, identical=True. Line items: attributed old=2, new=2, identical=True. New cells are empty on attributed rows.
  - Unknown rows split into `timeline`/`local:Dashnoard` (500 tok, 5.0, 00:00:01–00:00:09), `absent`/"" (400, 4.0, 00:00:02) and `no_remote`/"" (40, 0.5, 00:00:03). The old single row was 940 tok, 9.5, 00:00:01–00:00:09, so the first/last span is correctly the min/max of each split row.
- AC3: totals conserved per (day, repo_key, model, user) → ✅ Verified on the collision-free store (old==new True; DB, old, new and summary all 1160 tok / 12.7). ❌ Contradicted on collision inputs, which is expected; see the `+=` ruling.
- `attribution_source` comes from the resolved_view column and is evaluated only for unknown rows → ✅ Verified. The SQL is at export.py:89-94. I also ran a direct count: in-process I wrapped `attribute.attribution_source` in a counting UDF and ran `build()`.
  - 0% unknown: 0 calls for 24,000 rows.
  - 25% unknown: 6,000 calls, equal to the 6,000 unknown rows.
  - 50% unknown: 12,000 calls, equal to the 12,000 unknown rows.
  - The 80k-row stores gave the same exact equality: 0, 20,000 and 40,000.
- Each table passes through `resolved_view()` once, and `load_session_labels` runs once per build → ✅ Verified by monkeypatch count: resolved_view was called with `['cost_usage','token_usage']` and load_session_labels once. The trace callback shows exactly 4 SELECT statements (repo_name_map, timeline, 2 × resolved scans).
- No writes to otel.db → ✅ Verified. After build(), `total_changes: 0` and `in_transaction: False`, and sqlite_master has 22 entries both before and after.
- The "is unknown" test uses the resolved repo → ✅ Verified at export.py:95. Test: I mapped `github.com/cyclotron/globex` to bill name `unknown`. The globex rows stay unsplit, with `src=""`, and the line items for attributed rows are identical to old.
- `unattributed_project` never goes through `name_of`, `repo_name` or `repo_name_map` → ✅ Verified. `bn = name_of(repo_key)` at export.py:120, and the label comes only from `labels.get(r["sid"], "")` at export.py:99.
- AC4 timing, my own measurement (≥20k datapoints; half of the unknown sessions have timeline rows, half have none; 5 runs after warmup) → ✅ Verified within 3×.
  - 24,000 datapoints, 25% (gated): old best 0.059 s / median 0.084 s, new 0.127 / 0.156. Ratio best 2.14, median 1.85; best-of-first-3 2.53.
  - 24,000 datapoints, 0%: best 1.40, median 1.63. 50%: best 2.89, median 2.06.
  - 80,000 datapoints (less noise): 25% best 1.82 / median 1.69; 0% 1.63 / 1.55; 50% 2.07 / 1.97.
- AC5 → ✅ Verified. `python -m pytest tests/test_export.py tests/test_attribute.py tests/test_invoice.py -q` gave `25 passed in 2.72s`.
- Module docstring updated → ✅ Verified at export.py:18-21 (one sentence plus a clause).
- `build()`, `build_and_enqueue()` and `main()` signatures and return shapes are unchanged → ✅ Verified by reading the diff.

### The `+=` ruling
**(a) Which inputs now produce a different attributed row.** Any two or more SQL groups that collapse onto the same export key within one (day, resolved_repo, coalesced user):
1. Raw models that `normalize_model` collapses: context variants (`claude-sonnet-5[1m]` and `claude-sonnet-5`), dated snapshots (`-20251001`), and NULL / `""` / `"unknown"` / whitespace-only models, which all become `unknown`.
2. User emails that coalesce to `UNKNOWN_USER`: NULL, `""` and a literal `"unknown"` (export.py:97).

The pre-change code let the last group in SQLite's GROUP BY order overwrite cost and tokens separately. `_span` still merged min/max across all groups, so an old row's timestamps also covered usage whose dollars it had dropped.

Evidence: a seeded collision store with DB truth 7193 tok / $73.03. The old export gave 6081 / $60.81, losing 15.5% of tokens and 16.7% of cost. The new export and summary both give 7193 / $73.03.
- Attributed line row: old 1000 tok / $10.00 / billed $15.00, new 1150 / $12.50 / $18.75.
- NULL+"" user row: old 11 / $0.11, new 33 / $0.33.

This is realistic. `receiver.py:324` stores the raw model, and normalize.py:23-35 says it exists for exactly the `[1m]` case. NULL user_email is legacy-only, since receiver.py:321 and transcript.py:552 write `""`. I could not check whether production has collisions: there is no local `data/otel.db` and I have no VM access (⚠️ Unverified).

**(b) Does invoice.py already sum?** Yes. invoice.py:86-90 uses `cost_actual[key] += ...` and `cost_estimated[key] += ...` keyed by `(resolved_repo, normalize_model(model))`, and :99 uses `toks[...] += ...`. bill.py:132, 144 and 153 also use `+=`. Before this change, export.py was the only aggregator that overwrote. After it, export totals agree with invoice.py per (repo, normalized model) over a period. invoice.py has no user key, so user collisions never affected it.

**(c) Does any existing fixture exercise it?** No. SEEDED_SESSIONS (conftest.py:530-560) uses a distinct model per session, and its single `""` user sits in one unknown session with no NULL. The desktop fixture in test_export.py uses one model and one user. A grep of tests/ finds no `[1m]`, no dated model and no `user_email=None`. Both old and new code pass all 25 tests.

**(d) Ruling.** Partly necessary, not an implementation defect, and **must be escalated to the user**.
- For unknown rows, `+=` is required. The SQL now groups per `sid`, so several SQL rows map to one split key, and without summing, conservation would fail even with no collisions.
- For attributed rows, `+=` is not strictly required. `sid` and `src` are NULL there, so `=` would have reproduced the old output exactly. The implementer chose to fix a pre-existing under-reporting bug on attributed rows.
- On collision inputs, that change raises `tokens`, `actual_cost_usd`, `billed_usd` and `total_billed_usd` in the Fabric/Power BI tables for real repos. The task requirement says those rows must be "identical to the current implementation", and goal.md says "tokens, costs ... are unaffected".
- The criteria cannot be met sensibly on those inputs. Requirement "sum to exactly what the single pre-change unknown row held" and AC3 can only hold on collision stores by re-implementing "last raw-model group wins" across sessions, which means deliberately dropping usage. That is a criteria defect (unsatisfiable-in-intent when a collision is present; the orchestrator can arbitrate on the exact type).
- Reverting to `=` for attributed rows is not the answer either. It would keep export below invoice.py and bill.py, which is the "silently dropped usage" class of bug.
- The user must decide:
  - **Option A, recommended:** accept the correction, amend the task and goal wording to "identical except where the pre-change export dropped colliding groups", document it in README (task 03), and pin it in task 04 tests.
  - **Option B:** keep attributed rows byte-identical, meaning `=` on attributed keys only. The pre-existing under-report stays, and conservation for unknown rows has to be restated against the DB rather than the old export.

### Issues found
1. **[major]** billing/otel/export.py:104,109. `+=` on attributed keys changes attributed rows and billed dollars in Fabric for normalize_model / user-coalescing collisions. That contradicts the Requirement "identical to the current implementation" and goal.md's "costs unaffected". It is a user decision, not a code fix; see the ruling. ❌ Contradicted on collision inputs.
2. **[major, criteria]** 02-export-breakdown.md Requirements "sum to exactly what the single pre-change unknown row held" and AC3. On collision inputs these can only be met by reproducing the old data loss. The criteria need amending by the orchestrator or user, not the implementer.

### Notes (non-blocking)
- **[minor]** export.py:6-7. The docstring grain lines still say "one row per (usage date, repo, user_email)" and "(usage date, repo, model, user_email)". Lines 18-21 add the split, but lines 6-7 now understate the grain for unknown rows. README:305-306 has the same gap, which is task 03's job. Minor because it is prose and changes no output.
- **[minor, spec-mandated]** A real repo whose bill name is `unknown` stays unsplit, whether through a repo_name_map override or a key ending `/unknown`, per the spec's resolved-repo rule. The summary then carries a `repo=unknown` row with blank `attribution_source` next to the split rows, where the old export merged them into one row. That is correct per the Requirement, but task 03 should document it so Power BI filters `repo = unknown AND attribution_source <> ''`. Minor because the task explicitly requires this behaviour.
- **[minor]** The CASE guards re-evaluate the correlated `resolved_repo` expression, which costs 1.4–1.6× even at 0% unknown. It is inside the gate. An `AS MATERIALIZED` CTE is the permitted optimisation if this ever matters.
- **[minor]** The 08-report cites `export.py:36-44` for the field lists, but they are at :41-48. Report accuracy only.

### Required fixes
- [ ] Orchestrator: escalate the `+=` ruling (d) to the user with Option A or B. Do not dispatch a blind implementer retry.
- [ ] Once the user decides, the orchestrator or user (not the evaluator) amends the Requirement and AC3 wording in 02-export-breakdown.md and goal.md's Success Criteria to match.
- [ ] Under Option A: task 03 documents the correction in README §lake exports, and task 04 adds a test for collisions on both `[1m]` and dated-snapshot models and on NULL/"" users, asserting export totals equal the DB and invoice.py.
- [ ] Under Option B: the implementer restores `=` semantics for attributed keys only (keeping `+=` for unknown keys), and the unknown-row conservation criterion is restated against DB totals.

### Footprint
files_read: 12 (~112000 chars)
commands_run: 10

Scratch files (evaluation only, no repo edits) are in C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\0ab35cbd-cb5c-4db5-9ffc-e0282cc3cab6\scratchpad\ev09\ (export_old.py, check.py, timing.py, timing_big.py, calls.py).
