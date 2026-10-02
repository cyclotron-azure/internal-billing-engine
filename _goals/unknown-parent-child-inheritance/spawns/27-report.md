**Model (self-reported)**: claude-opus-5-5

## Verdict: APPROVED
**Score**: 4/5

All 5 prior issues and the wording note are fixed in the actual files, and the edits added nothing new. Scope is exact and the tables are intact. The one remaining point is non-blocking: the README's dataset-size wording is slightly imprecise.

### Prior issues: fixed / not fixed
1. **[major] README `timeline` row: FIXED.** README.md:371 now opens the reason list with "no real-repo timeline row in the session at or below that folder (for example an unrelated sibling folder, or a session whose timeline rows are all `unknown`), an empty or missing cwd". The original reasons are kept.
   - This matches `attribute.py:200-210` (the `_x` filter, the `_x.n <> '' AND _m.n <> ''` guards, and `count>0 AND min=max`).
   - It is still one row: my column checker found 0 bad rows across the 6-row table.
2. **[major] README capacity figure: FIXED.** README.md:621-625 now gives a range plus the "not on production data" caveat. Every figure traces to a spawn report:
   - "about 0.24 s … plain `resolved_view` scan": `spawns/21-report.md` (my 0.244). ✅
   - "up to about 0.87 s … real export / bill statements": `spawns/14-report.md:53` ("0.869 and 0.626 s per 100k", the export `_scan` token and bill token statements under load) and `spawns/13-report.md:43` (0.828). ✅
   - "about 0.33 s on a quiet machine": `spawns/14-report.md:49-52` (0.327 / 0.329). ✅
   - "one statement per process": `spawns/14-report.md:46` and `spawns/13-report.md:43`. ✅
   - "~100k-130k datapoints and ~40k timeline rows": see the note below.
3. **[major] test-ladder SKILL.md: FIXED.** `git diff --numstat` shows `1 1`. The diff touches only line 75, which now reads `tests/test_attribute.py` and `tests/test_attribute_inheritance.py` **plus** `test_bill.py`, `test_invoice.py`. No other row changed.
4. **[minor] COVERAGE_MAP tie-break: FIXED.** tests/COVERAGE_MAP.md:500 now says the final tie-break is `repo`, DESC for as-of and ASC for first-row, after `ts` and `seq`, and that `rowid` only identifies the selected row. This matches `attribute.py:101-114`.
5. **[minor] COVERAGE_MAP test counts: FIXED.** tests/COVERAGE_MAP.md:513 now reads "129 at first authoring, 136 after fix cycle 1, 196 at PASS". Sources:
   - `spawns/15-report.md:78` gives 129 passed.
   - `spawns/17-report.md:34` gives 136 passed.
   - `spawns/20-report.md:19` gives 196 passed.
   - My `--collect-only` run collects 196.
   - The implementer's report says it confirmed 129 only from the brief. The figure is correct anyway (#15).
6. **Wording note (README:153): FIXED.** It now reads "the folder of related real-repo timeline rows (same folder or below it), and those rows name exactly one repo". The rest of the bullet is unchanged.

### Regression / scope checks
- `git status --short` shows exactly the six expected entries:
  - ` M .claude/skills/test-ladder/SKILL.md`
  - ` M README.md`
  - ` M billing/otel/attribute.py`
  - ` M tests/COVERAGE_MAP.md`
  - `?? _goals/unknown-parent-child-inheritance/`
  - `?? tests/test_attribute_inheritance.py`

  ✅ Verified
- The `attribute.py` hash is still `38d2db20fe79911ed9c9c6e49f714958ee527021`. ✅
- `git diff --numstat`: README `26 9` (35 lines), COVERAGE_MAP `58 0` (0 deleted lines), SKILL.md `1 1`. The diffs are surgical. ✅
- Tables and fences:
  - The checker found 0 malformed rows (28 COVERAGE_MAP rows and the 6-row README table).
  - Fences are balanced in both files.
  - The `#unattributed-usage-in-the-lake-tables` anchor still resolves (README:360, linked from :154 and :587).

  ✅
- The stale-marker sweep over in-scope tracked markdown (excluding `_goals/`, `_research/`, `deploy/`, `client-package/`) hits only `.claude/agents/evaluator.md:78` and `.claude/skills/feature/SKILL.md:90`. Both are still accurate, as in my prior audit. Nothing new in scope is stale. ✅
- The COVERAGE_MAP working copy is still LF under `core.autocrlf=true`. Git normalises it on commit, so there is no EOL diff. Unchanged from before; harmless.

### New findings
Blocking: none.

### Notes (non-blocking)
- **README.md:624 dataset-size wording is slightly imprecise.**
  - The 0.33-0.87 s figures come from the evaluator store in `spawns/06-report.md:26`: 129,600 token_usage rows, 126,600 cost_usage rows, 44,448 timeline rows.
  - The 0.24 s figure comes from the audit store in `spawns/21-report.md`: 100,000 datapoints, 40,300 timeline rows.
  - So "~100k-130k datapoints" is accurate, but "~40k timeline rows" understates the larger store's ~44k.
  - It is minor because the order of magnitude is right and the sentence is already caveated "synthetic … not on production data".
  - Optional tightening: "~40k-44k timeline rows".
  - Contrary to the implementer's flag, the ~130k figure *is* sourced (`06-report.md:26`).
- The README's "export / bill" leaves out reconcile, which was also measured (0.248-0.273 s per 100k, `spawns/13-report.md:43`). It falls under the stated maximum, so the range stays correct.

### What I verified (commands)
- `git status --short`, `git hash-object billing/otel/attribute.py`, `git diff --numstat` and `git diff -- .claude/skills/test-ladder/SKILL.md`: results as above.
- Greps of README.md:153, :371 and :618-626, and of tests/COVERAGE_MAP.md:500 and :513: the text quoted above.
- Greps of spawn reports 06, 13, 14, 15, 17 and 20 for every figure.
- Scratch `tblchk.py`: 0 bad rows, fences balanced.
- `python -m pytest tests/test_attribute_inheritance.py --collect-only -q`: 196 collected.
- Stale-marker sweep over in-scope markdown: results as above.

### Footprint
files_read: 6 (~22,000 chars)
commands_run: 4
