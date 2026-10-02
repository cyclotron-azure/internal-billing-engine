**Model (self-reported)**: claude-opus-5-5

## Verdict: ISSUES
**Score**: 3/5
**failure_class:** implementation

Scope, line endings, table rendering and the COVERAGE_MAP node ids are all clean. I found three major problems: an incomplete reason list in the README `timeline` row, a capacity figure that picks the most favourable measurement, and one doc the shipped change made stale that is not on the edit list (`.claude/skills/test-ladder/SKILL.md`). There are also two small factual errors in COVERAGE_MAP. Every fix is a one-line wording change; none needs a design decision.

### Claims checked (claim -> source -> status)

| # | Doc claim | Source | Status |
|---|---|---|---|
| 1 | README:153 — an unknown effective row (the as-of row, else the session's first) inherits only if the folder is project-level and the same as or an ancestor of the real rows' folders | `attribute.py:198-211`, and `:259-264` / `:309-326` (the effective row is the as-of rowid, else the first rowid) | ✅ Verified |
| 2 | README:153 — "those rows name exactly one repo"; 2+ distinct related repos give `unknown` | `attribute.py:200-201` (`count>0 AND min=max`) | ✅ Verified, but the wording is ambiguous: "the session's real-repo timeline rows" can be read as *all* real rows, while the rule counts only *related* ones. The later "related" clause rescues it (see Notes). |
| 3 | README:153 — ancestor-only (an unknown child stays `unknown`) | `attribute.py:209-210`; test `test_reverse_real_parent_unknown_child_stays_unknown` | ✅ Verified |
| 4 | README:153 — real rows count before or after the datapoint | The `_x` subquery has no ts filter (`attribute.py:202-208`) | ✅ Verified |
| 5 | README:153 — `DirectoryAdded` never anchors; session id `unknown` never inherits | `attribute.py:206` and `:198` | ✅ Verified |
| 6 | README:153 — the blocked anchors and the names it lists (`code, src, repos, projects, dev, OneDrive*, Visual Studio *`) | `_CONTAINER_NAMES` at `attribute.py:86-90`; `_blocked` at `:149-176` | ✅ Verified (every listed name is in the vocabulary or a prefix rule) |
| 7 | README:153 — case-insensitive, `\` and `/` treated alike, ASCII-only `lower()` | `_norm` at `attribute.py:146`; my Phase 5 `Ärger` case stayed unknown | ✅ Verified |
| 8 | README:153 — query time only; a late second repo can flip usage back | No writes or DDL in `attribute.py`; follows from the min=max rule | ✅ Verified |
| 9 | README:153 — inherited rows report `timeline` | `attribute.py:319-321` (desktop-scratch fires only when rr is `unknown`); test `test_transcript_session_that_inherits_reports_timeline` | ✅ Verified |
| 10 | README:160 — `bill.py` multi-repo list reads the raw timeline, so an inherited session still prints as split; billing unaffected | `otel_store.py:718-731` (raw `COUNT(DISTINCT repo)`); `bill.py:273-275` prints "usage split across repos" | ✅ Verified |
| 11 | README:289 — flow diagram clause | Same as #1 | ✅ Verified |
| 12 | README:371 — `timeline` row: the usage "could not inherit a real repo: a blocked anchor…, an unknown child…, two or more related real repos, only a `DirectoryAdded` anchor, or the literal session id `unknown`" | `attribute.py:198-211` | ❌ **Incomplete**: the list after the colon leaves out the most common reason, *no real-repo row at or below the folder in the session*. That covers Derek's unrelated sibling (`Dashnoard` vs `src\orbit-local`) and only-unknown sessions. Empty/NULL cwd (`attribute.py:208`) is also missing. |
| 13 | README:378-381 — ancestor-start sessions no longer produce `unknown` rows and get no `local:` label; history relabels after re-export | Export regenerates all history (README:167); my Phase 5 unknown-report run showed inherited sessions drop out | ✅ Verified |
| 14 | README:419-424 — Accepted mislabels: the real-start, no-remote-child direction stays `unknown`; an unknown-ancestor start inherits | Same as #3 and #1 | ✅ Verified |
| 15 | README:515-519 — developer-cost caveat (ancestor start recovered at query time) | Same as #1 | ✅ Verified (it names a subset of the rule, which is accurate) |
| 16 | README:577-578 — pilot funnel: the `unknown` bucket shrinks | Follows from #1 | ✅ Verified |
| 17 | README:618-620 — every `resolved_view` statement builds the lookup over the WHOLE timeline, whatever the date window; `UserPromptSubmit` adds rows every prompt | `_inherit_table` has no filters (`attribute.py:193-226`); `deploy/claude-repo-tag.py:4` and `:91-101` (new ts/seq per firing) | ✅ Verified |
| 18 | README:621-623 — "measured at about 0.24 s per 100,000 datapoints on a synthetic store (100k datapoints, 40,300 timeline rows), not on production data" | My Phase 5 run: 0.244 s per 100k for a plain `GROUP BY` | ⚠️ **Traceable but optimistic.** It is the lowest figure on record. Real consumer statements (export `_scan`, bill, reconcile) measured 0.33-0.87 s per 100k on the harder evaluator store (`spawns/13-report.md:43`: export_scan_token 0.828; `spawns/14-report.md:53`: 0.869 under load). A capacity note that quotes only 0.24 understates the cost by up to about 3.5x. |
| 19 | COVERAGE_MAP — every cited node id exists | Every cited function id scripted against `pytest --collect-only` (196 collected): each one matches at least once | ✅ Verified |
| 20 | COVERAGE_MAP — parametrized counts: 2 cases (reverse), 5 (wildcards), 3 (literal), 9 (allowed), "16 aliases x 2 tables" | Collected: 2, 5, 3, 9, 32 | ✅ Verified |
| 21 | COVERAGE_MAP — "the container cases include the OneDrive root, OneDrive `Desktop` and `Visual Studio 2022`" | `test_attribute_inheritance.py:451-453` | ✅ Verified |
| 22 | COVERAGE_MAP Task 01 row 5 — "tie-breaks (`rowid`; …)" | As built: `repo DESC` / `repo ASC` after ts and seq (`attribute.py:104-114`). Rowid only identifies the selected row. | ❌ Contradicted (that wording is from the task file; deviation 2 replaced it). The cited tests are the right ones. |
| 23 | COVERAGE_MAP Task 02 row 1 — "136 tests at first PASS, 196 at final" | Log: #15 = 129 tests, #17 = 136 tests, then #18 NEEDS FIXES; the only PASS (#20) was at 196 | ❌ Contradicted: there was no PASS at 136 |
| 24 | COVERAGE_MAP — mutation outcomes framed as evaluator-measured | It says "recorded in the evaluator's mutation report, not re-provable from the suite" | ✅ Verified (honest framing) |
| 25 | COVERAGE_MAP — GAP entries (perf, tree/hash, nothing-persisted) | Accurate; spawn reports 11/13/14/21 exist and carry timings | ✅ Verified |
| 26 | COVERAGE_MAP — insertions only | `git diff --numstat` gives `58 0`; zero `-` lines | ✅ Verified |

### Scope and format
- `git status --short` matches the expected list exactly: ` M README.md`, ` M billing/otel/attribute.py`, ` M tests/COVERAGE_MAP.md`, `?? _goals/unknown-parent-child-inheritance/`, `?? tests/test_attribute_inheritance.py`. ✅ Verified
- `attribute.py` hash is still `38d2db20fe79911ed9c9c6e49f714958ee527021`. ✅ Verified
- Line endings: numstat is README `24 9` and COVERAGE_MAP `58 0`, which matches the content, so there is no whole-file churn. `git ls-files --eol` shows README `i/lf w/crlf` (normal for `core.autocrlf=true`). COVERAGE_MAP is `i/lf w/lf`: the working copy was rewritten with LF, so git warns "LF will be replaced by CRLF". It normalises to LF on commit, so the commit has no EOL diff. Harmless (see Notes). ✅
- Lint: there is no markdownlint config (no `.markdownlint*`, no `package.json`). My column-count script found 0 malformed rows across 28 new COVERAGE_MAP table rows and the 6-row README table; escaped `\|\|` is handled. Code fences are balanced in both files. The `#unattributed-usage-in-the-lake-tables` anchor still resolves to README:360. ✅

### Coverage findings (folded plan check)
I grepped all tracked markdown except `_goals/` and `_research/` for the stale markers.
- **Missing from the edit list (in scope, not fenced): `.claude/skills/test-ladder/SKILL.md:75`.** It maps `billing/otel/attribute.py` to `tests/test_attribute.py` plus `test_bill.py`, `test_invoice.py`. It does not list `tests/test_attribute_inheritance.py`, the 196-test guard for the no-misattribution rule. A future `attribute.py` change run at rung 1/2 by that table would skip it.
- No change needed:
  - `fabric/README.md:42-51`: accurate.
  - `tests/golden/README.md:52-55`: accurate.
  - `CLAUDE.md:12-13`: accurate.
  - `.claude/agents/evaluator.md:77-78` ("as-of join"): still true as the base mechanism; the persist-vs-resolve property is unchanged.
  - `.claude/skills/feature/SKILL.md:90`: accurate.

### Fenced-doc staleness (user decides; goal.md forbids touching `deploy/` and `client-package/`)
- `deploy/README.md:109-110`: "Sessions started outside a git repo tag as `repo=unknown` and surface in the `unknown` bucket". The wrapper tag is still `unknown`, but billing may now recover ancestor-start sessions.
- `deploy/README.md:179`: troubleshooting row "All usage lands in `repo=unknown` / Sessions started outside a git repo". Mostly still true, but incomplete.
- `deploy/README.md:200-201`: the "as-of" join so that "usage splits across the repos it was actually done in". Inheritance is missing.
- `deploy/README.md:245-247`: the ATTRIBUTION SOURCE list `timeline / wrapper / no_remote / absent` was already missing `desktop-scratch` before this change. Its "flags every multi-repo session" now over-reports inherited sessions.
- `client-package/INSTRUCTIONS.md:106-107`: "Without one, usage is recorded as `unknown` and cannot be attributed to any project". This now overclaims, since an ancestor-start session can be recovered.
- `client-package/INSTRUCTIONS.md:164`: troubleshooting row, same point.
- `client-package/ADMIN.md`: nothing stale found (its `unknown` hits at lines 133 and 175 are unrelated).
- `billing/otel/cowork_attribute.py:132` docstring ("Mirrors attribute.py's real fallback chain"): stale. It is code and out of scope.

### Issues found
1. **[major] README.md:371.** The new `timeline` reason list leaves out "no real-repo row at or below that folder in the session" (Derek's unrelated sibling, sessions with only unknown rows) and empty/NULL cwd. This table is what Power BI owners use to read `unknown` rows, and README is ground truth. As written, the commonest case reads as if it were not `timeline`.
2. **[major] README.md:621-623.** The capacity figure of 0.24 s per 100k is the most favourable measurement (plain `GROUP BY`, easier store). Real consumer statements measured up to 0.83-0.87 s per 100k (`spawns/13-report.md:43`, `spawns/14-report.md:53`). Quoting only the low number understates capacity cost in a planning section.
3. **[major] `.claude/skills/test-ladder/SKILL.md:75`.** This in-scope doc is missing from the edit list. Its `attribute.py` impacted-test row omits `tests/test_attribute_inheritance.py`, so ladder-driven verification of future `attribute.py` changes would skip the inheritance guard suite.
4. **[minor] tests/COVERAGE_MAP.md, Task 01 row 5.** "tie-breaks (`rowid`; …)" contradicts the repo-based tie-break as built (`attribute.py:101-114`). It is minor because the cited tests are correct and the map is an internal index, but it is ❌ Contradicted.
5. **[minor] tests/COVERAGE_MAP.md, Task 02 row 1.** "136 tests at first PASS" is wrong: 136 was the cycle-1 fix count, judged NEEDS FIXES at #18, and the only PASS was at 196. It is minor because it is a historical count with no behavioural impact.

### Required fixes
- [ ] README.md:371: add "no real-repo row in or below that folder in the session (for example an unrelated sibling folder), an empty cwd" to the reason list, or reword it so the list is clearly not exhaustive.
- [ ] README.md:621-623: give the measured range, about 0.24 s (plain view scan) to about 0.87 s per 100k (export/bill/reconcile statements, synthetic stores, varying load), and keep the "not production" caveat.
- [ ] `.claude/skills/test-ladder/SKILL.md:75`: add `tests/test_attribute_inheritance.py` to the `attribute.py` row. Surgical edit; the doc is in scope.
- [ ] tests/COVERAGE_MAP.md Task 01 row 5: replace "`rowid`" with "`repo` DESC / ASC after ts and seq; the row is selected once by rowid".
- [ ] tests/COVERAGE_MAP.md Task 02 row 1: replace "136 tests at first PASS" with "129 at first authoring, 136 after fix cycle 1, 196 at PASS".

### Notes (non-blocking)
- README.md:153 wording: change "the folder of the session's real-repo timeline rows, and those rows name exactly one repo" to "…of related real-repo rows…" so it cannot be read as requiring *all* of the session's real rows to sit below the folder.
- README.md:378-381 and 515-519 describe only the ancestor-start-then-`cd` direction. A session that starts in the real child and then `cd`s up into its no-remote parent also inherits, because real rows count before or after. The README:153 bullet covers this; the two narrower sentences are subsets, not errors.
- COVERAGE_MAP's working copy is LF under `core.autocrlf=true`. It normalises on commit and produces no EOL diff.
- Process note: while scripting the table check I accidentally ran a `cat >` with no input outside the repo. It created an empty file `C:\Users\ZANECH~1\AppData\Local\claude_tblchk.py`. I stopped the hung task and deleted that empty file (my own artifact, never in the repo). `git status` was unaffected.
- Items already carried: AC5 wording `C:\mono` vs `C:\dev\mono` in the read-only task file; the vocabulary-completeness test asserts only on its own literal; the `_win_case` docstring example; the fenced docs listed above.

### What I verified (commands)
- `git status --short`, `git hash-object billing/otel/attribute.py`, `git diff --stat` / `--numstat`, and `git diff -- README.md tests/COVERAGE_MAP.md`. Results as above.
- `python -m pytest tests/test_attribute_inheritance.py --collect-only -q` gives 196 collected. Cross-checking every node id cited in the COVERAGE_MAP diff found all present, with the parametrized counts listed.
- `git ls-files --eol` and `git config core.autocrlf`: results as above.
- A scratch table/fence checker (`scratchpad/tblchk.py`): 0 bad rows, balanced fences.
- Grep of all in-scope markdown for the stale markers: findings above.
- Reads of `otel_store.py:718-731`, `bill.py:273-275`, `deploy/claude-repo-tag.py`, and the perf lines in spawn reports 11/13/14.

### Footprint
files_read: 9 (~48,000 chars)
commands_run: 11
