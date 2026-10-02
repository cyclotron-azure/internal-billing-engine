## Verdict: NEEDS REVISION
**Score**: 3/5
**Model (self-reported)**: claude-opus-5-5 (Opus 5.5). The context package asked for claude-opus-5; the harness reports Opus 5.5.
**failure_class:** implementation. The goal and task files need an ordinary revision pass. Nothing here needs arbitration, nothing is destructive or security-related, and there was no infra failure.

The goal is well structured. The SQL relation is sound when written correctly (checked live in SQLite 3.49.1), the ownership contract is clean, and the baseline suites are green. However, four major gaps let the strict no-misattribution rule or today's behavior change without any check failing. All four are wording or criterion fixes, so one revision cycle should be enough.

### What I verified
- Baseline suites from task 01 criterion 7 pass before any change → ✅ Verified. `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_invoice.py tests/test_reconcile.py tests/test_export.py tests/test_export_unattributed.py tests/test_integration_desktop.py -q` → `136 passed in 10.35s`.
- Full suite (the rung 3 baseline) is green → ✅ Verified. `python -m pytest -q` → `1006 passed in 37.47s`.
- Every file the tasks reference exists → ✅ Verified (`ls`): the 7 test files, `tests/conftest.py` (`tmp_db_path` at line 150, `seeded_otlp_db_path` at line 595), `.claude/skills/test-ladder`, `python-performance-optimization` and `python-testing-patterns`. `tests/test_attribute_inheritance.py` does not exist yet, as expected.
- The normalisation formula `N(c)=lower(rtrim(trim(replace(c,'\','/')),'/'))` behaves as specified → ✅ Verified with a script (`spec_check2.py` in the scratchpad):
  - `C:\DEV\WealthSpire\SRC\\` → `c:/dev/wealthspire/src`
  - `C:\` → `c:`, and `GLOB '[a-z]:'` matches it
  - `/`, `//` and `"  "` all become `''`
  - `\\srv\share` → `//srv/share`
- Operator precedence: `||` binds tighter than `=`, so `a = b || '/'` parses as intended → ✅ Verified. The lookalike `c:/dev/wealth` vs `c:/dev/wealthspire/x` gives 0; the real descendant gives 1.
- The relation gives the right answer for Nate, the reverse case, Derek, the lookalike, `C:\` vs `C:\x`, `''`, NULL, `C:\a_b` vs `C:\axb\c`, case mixing and separator mixing → ✅ Verified (all as expected).
- The NULL claim at 01:46 ("NULL/empty cwd normalises to empty") → ❌ Contradicted. `N(NULL)` is NULL, not `''`. If the guard is written as an exclusion (`CASE WHEN N(u)='' OR N(u) GLOB … THEN excluded ELSE inherit`), it returns `'INHERITS'` for NULL (measured).
- Drive roots in WSL, Git Bash and UNC form are not guarded → ❌ Contradicted against the guard's stated intent. Measured `related('/mnt/c','/mnt/c/dev/repo') = 1` and `related('/c','/c/dev/repo') = 1`. `//srv/share` and `~` are not drive roots under `GLOB '[a-z]:'` either.
- The mutation named in task 02 criterion 2 does not do what it says → ❌ Contradicted. Dropping `|| '/'` gives Nate descendant → 0 and lookalike → 0, so it switches inheritance off instead of widening it. Dropping both `+ 1` and `|| '/'` is what makes the lookalike match (→ 1).
- How easily the backslash literal gets lost in Python → ✅ Verified, by accident. My first scratch script wrote `'\'` inside a normal Python string. It produced the SQL `replace(?, '', '/')`, which silently does nothing (`trap result: ('C:\\dev\\x',)`).
- Every consumer goes through `resolved_view`, and none passes a non-default alias → ✅ Verified (grep): `bill.py:75,90,97`, `invoice.py:82,95`, `export.py:136`, `reconcile.py:109,192` (a subquery without a CTE), `deploy/unknown-report.py:72`. Today's inner alias is `r`, so the wrapping `WITH r AS (...)` compiles: the suite passes.
- Timeline `repo` is always the `normalize_remote` output and `cwd` is never NULL when it arrives through the receiver → ✅ Verified at `receiver.py:383-386` and `otel_store.py:714` (`cwd or ""`). NULL cwd can only arrive through direct SQL.
- The `cwd` column has been in the base schema since it was created (no `ALTER TABLE` migration) → ✅ Verified at `otel_store.py:74`, and the `ALTER` statements at lines 268-278 do not touch the timeline.
- Ownership contract → ✅ Verified. Task 01 writes only `billing/otel/attribute.py` and task 02 writes only `tests/test_attribute_inheritance.py`, so the sets are disjoint. 02 depends_on 01, which is a valid DAG. Owners are implementer and test-writer, `rewrite_semantics` is set, and no placeholder values remain.
- eval_depth → ✅ Verified. Task 01 is `full`, with the reason stated (interface consumers). Task 02 is `light` and is a test-only task, which is correct.
- `ladder: escalate` is declared at goal.md:81, and README is an orchestrator-owned Phase 6 surface → ✅ Verified (`align-docs` SKILL.md:47).
- Every acceptance criterion names a verification method → ✅ Verified (01 AC 1-9, 02 AC 1-4).
- Each Discovery Summary decision appears in a task → ✅ Verified, except the gaps listed below.

### Issues found
1. **[major]** `01-attribute-inheritance.md:48-50`: the root guard is narrower than the project's own definition of a bare root.
   - Only `N GLOB '[a-z]:'` (Windows drive) and `/` (which becomes empty) are excluded.
   - README.md:389-390 and `project_label.path_segments` (tests/test_project_label.py:246, 259) already treat WSL `/mnt/c`, Git Bash `/c/`, UNC `\\host\share` and `~` as drive-style roots. The task's guard misses all of them.
   - Measured: an unknown row at `/mnt/c` relates to a real row at `/mnt/c/dev/repo`.
   - So a WSL session that starts at `/mnt/c` and visits one repo bills all of its drive-root work to that repo. That breaks guard (a) at goal.md:36-37 and the strict rule.
   - Fix: extend the anchor exclusion to `N` equal to `/mnt/<letter>`, `/<letter>`, `~`, and a bare `//host/share`. Do the checks with `length`/`substr`/equality, and add matching cases to task 02.
2. **[major]** `01-attribute-inheritance.md:49` contradicts `01-attribute-inheritance.md:109`.
   - The requirement mandates `N(..) GLOB '[a-z]:'` on the normalised path.
   - The Must-NOT forbids using "`LIKE`/`GLOB` on path text".
   - Read literally, the two cannot both be satisfied, and the task evaluator could fail either implementation.
   - Fix: reword the Must-NOT so it bans path text used as the pattern (the right-hand side), or swap the GLOB for `length(N)=2 AND substr(N,2,1)=':' AND substr(N,1,1) BETWEEN 'a' AND 'z'`.
3. **[major]** `02-tests.md:66-67`: the example mutation in criterion 2 is wrong (checked in SQLite).
   - Dropping `|| '/'` turns `substr(N(x),1,len+1) = N(u)` into something that can never be true for a real descendant. It switches inheritance off rather than "match[ing] unrelated siblings".
   - The Nate test would fail, so the criterion would pass, but it would prove nothing about the lookalike or sibling guards. Those guards are the strict no-misattribution properties.
   - Fix: give the widening mutant explicitly (drop both `+ 1` and `|| '/'`, then show that the prefix-lookalike and wildcard tests fail). Add at least two more mutants: one that removes the root guard, and one that replaces "exactly one distinct repo" with `MIN(repo)`/`LIMIT 1`. Each must turn ≥1 named test red.
4. **[major]** `01-attribute-inheritance.md:33-38` (requirement) and `02-tests.md:35-61` (test list): no criterion pins today's behavior for a non-unknown effective row that has related rows naming other repos.
   - Example: a real row at `C:\mono` (repo M) and a nested real row at `C:\mono\sub` (repo S). A datapoint whose effective row is M must still bill M.
   - Suppose an implementation applies the inheritance or ">1 distinct → unknown" logic to every row instead of only `'unknown'` effective rows. It would return `unknown` here, and none of task 01's AC 1-6 nor any test in task 02 would catch it. The existing test_attribute fixtures only use sibling folders.
   - The orchestrator's brief names this as the case that "could silently change".
   - Fix: add it to 01 AC 1-6 and to 02 as a named test. Also add the inverse: a real effective row plus an unknown related row keeps the real repo.
5. **[minor]** `01-attribute-inheritance.md:46` and `02-tests.md:51-52`: the NULL claim does not hold.
   - The formula is not NULL-to-empty (measured), and an exclusion-style CASE lets NULL through to "inherit".
   - The task 02 NULL-cwd test cannot be seeded through the mandated `insert_session_repo`, because it stores `cwd or ""` (otel_store.py:714). A test-writer passing `cwd=None` would silently test `''` a second time.
   - Minor because the receiver never writes NULL, so it is defensive only.
   - Fix: specify `N(c) = lower(rtrim(trim(replace(ifnull(c,''), …))))`, and say the NULL case must be seeded with a raw `INSERT`.
6. **[minor]** `01-attribute-inheritance.md:46`: no warning that `'\'` must be written as `'\\'`, or in a raw string, in Python source.
   - A plain string collapses it to `replace(c,'','/')`, which does nothing (I reproduced this by accident).
   - That would under-inherit rather than misattribute, and the task 02 separator tests would catch it. Minor.
7. **[minor]** `01-attribute-inheritance.md:33-35`: the spec does not require the effective row's `repo` and `cwd` to come from the same row.
   - `ORDER BY ts DESC, seq DESC` has no unique tie-break. The PK includes `repo`, and `seq` defaults to 0 (receiver.py:384), so same-second events from older hooks tie.
   - Two separate subqueries could pair the 'unknown' repo from row A with the real-repo cwd from row B. Row B's own folder then "inherits" itself.
   - Minor because ties are already coin-flips today.
   - Fix: require a single-row fetch or a deterministic tie-break.
8. **[minor]** `01-attribute-inheritance.md:90` and `02-tests.md:68`: `git diff --stat` cannot see untracked files.
   - A baseline copy of the original `attribute.py`, or a benchmark script, left in the repo would not show up.
   - Fix: use `git status --short` (task 02 AC4 already does).
9. **[minor]** `01-attribute-inheritance.md:71-76`: the performance gate is measurable, and its escalation (STOP, then report, then the precompute fallback) is clear, but it is under-specified.
   - It does not say how many runs or how to aggregate them (e.g. median of 3, same warm DB file).
   - Every session is uniform at about 20 timeline rows. The new subquery is O(timeline rows per session) per datapoint, so a heavy-tail session (hundreds of CwdChanged rows and tens of thousands of datapoints) is not represented.
   - Fix: add one heavy-tail session and a repetition rule.
10. **[minor]** `01-attribute-inheritance.md:63-65`: no acceptance criterion checks alias safety.
    - All current consumers use the default `t`.
    - Fix: add an AC that compiles and compares `resolved_view('token_usage', alias='x')` inside `WITH r AS (...)`.
11. **[minor]** `02-tests.md:16-17` and `02-tests.md:84`: the criterion 2 mutation temporarily edits `billing/otel/attribute.py`, which is outside task 02's `writes` fence.
    - The constraint text allows it, but the ownership block does not record it, so the evaluator's "work outside writes fence" auto-fail could fire.
    - Fix: record it as a temporary, restored exception inside the ownership block.
12. **[minor]** `goal.md:38-40`: treating home and container folders as parents is the orchestrator's reading of the "literal rule", and it is only to be flagged at delivery.
    - It is the largest misattribution exposure that remains. A session started in `C:\Users\x` that briefly visits one repo bills all of its home-folder work to that repo.
    - That is a "likely estimate", which the user explicitly rejected.
    - Fix: confirm with the user before task 01 runs, not after.
13. **[minor]** `01-attribute-inheritance.md:46`: SQLite `lower()` is ASCII-only. Measured: `c:/users/zoë` ≠ `c:/users/zoË`.
    - This is conservative (under-inherits, never misattributes). It should be noted in the docstring or README.

### Devil's Advocate
1. **Strongest alternative:** a deterministic Python precompute.
   - At query time, build a TEMP `(session_id, cwd_norm) → inherited_repo` map from `session_repo_timeline` in one ordered pass, and join it into `resolved_view`.
   - It is O(timeline rows) instead of O(datapoints × session rows). Path logic could reuse `project_label.path_segments`, which already knows every root form this goal misses (issue 1).
   - Nothing is persisted beyond the connection, so staleness is not a concern.
   - The cost is a signature or lifecycle change for `resolved_view` (it needs the connection), which the user rejected for valid reasons.
2. **Load-bearing assumptions:**
   - The hook's `cwd` is the session's real working directory. A `DirectoryAdded` row is an extra directory, not a `cd`, yet it can act as an inheritance anchor.
   - `session_id` is unique per real session. The receiver maps a missing OTLP id to the literal `"unknown"` (receiver.py:317), so any timeline row ever filed under that id would pool unrelated users.
   - About 20 timeline rows per session is representative.
   - An unknown child of a real repo folder is the same project. In git terms it can only be a separate nested no-remote repo or a lookup flake, because git walks up to the parent's remote.
3. **30-day pre-mortem:**
   - A WSL user starting at `/mnt/c` (issue 1) shows 100% of their drive-root work on one client's invoice.
   - Separately, a regenerated September draft invoice no longer matches the one already sent, because inheritance is retroactive and invoices are regenerated by `DELETE + INSERT OR REPLACE`.
   - Or the unknown report on the VM disagrees with the new bills, because the VM is still on stale code.
4. **Concrete alternative sketch:** "descendant-only" inheritance, where only an unknown ancestor inherits from its real child (the Nate shape).
   - The reverse case (a real parent with an unknown child) can only come from a separate nested no-remote repo or a git-lookup flake. Excluding it removes a class of plausible-but-unproven attribution at very little recovery cost.
5. **Risks the goal accepts:**
   - Retroactive re-billing of closed periods, in both directions: a late second related repo can flip an inherited row back to `unknown`.
   - Home and container folders as anchors.
   - Cowork attribution (`cowork_attribute.py`) staying on the old rule, so the two pipelines are inconsistent.
   - ASCII-only case folding.
   - Up to 3x query slowdown.

### Required fixes (NEEDS REVISION)
- [ ] Extend the root guard to `/mnt/<letter>`, `/<letter>`, `~` and a bare UNC `//host/share`, consistent with README.md:389-390. Add tests for each in task 02.
- [ ] Resolve the GLOB contradiction between 01:49 and 01:109: reword the Must-NOT, or replace the GLOB with a `substr`/`length` check.
- [ ] Rewrite the task 02 criterion 2 mutants: a widening mutant (drop both `+ 1` and `|| '/'`), root-guard removal, and a distinct-count mutant. Each must turn a named test red.
- [ ] Add an acceptance criterion in 01 and a named test in 02: a non-unknown effective row with related rows naming other repos keeps its own repo, plus the inverse case.
- [ ] Specify `ifnull(c,'')` in `N`, and require the NULL-cwd test to seed with a raw `INSERT`.
- [ ] Recommended minors: the backslash-escaping note; same-row fetch or deterministic tie-break for repo and cwd; `git status --short` instead of `git diff --stat`; repetition and heavy-tail session in the performance gate; an alias acceptance criterion; recording the temporary mutation in the fence; confirming home-folder anchors with the user before execution.

### Footprint
files_read: 13 (~80000 chars)
commands_run: 7
