**Model (self-reported)**: claude-opus-5-5 (requested claude-opus-5, frontier tier)

VERDICT: APPROVED

## Verdict: PASS (with notes)
**Score**: 4/5

The folded Phase 6.3 checks (coverage, scope, anti-invention) pass. README.md and fabric/README.md match `project_label.py`, `export.py` and `attribute.py`, and agree with each other. There are no blockers or majors, and no auto-fail trigger fired. Four minor notes are listed below; none is dropped.

### Edit-list criteria (6.3, folded)
- **Coverage → PASS.** I listed every markdown file outside `_research/` and `_goals/` with `git ls-files -co --exclude-standard '*.md'` (about 95 files) and grepped them for all the listed identifiers, plus a separate grep for `unknown`.
  - `deploy/README.md:254` is about the `wrapper` class in the bill.py breakdown and is unaffected. Confirmed. Lines 24, 110 and 179 ("unknown bucket is flagged, never silently mis-billed") are also still accurate.
  - `tests/golden/README.md:53-55` describes the attribution classes of the golden fixtures. It has no export or CSV content. Confirmed unaffected.
  - `.claude/ORCHESTRATION.md` (lines 422, 758) only mentions file paths and routing. Confirmed unaffected.
  - The `.claude/skills/*` hits (`feature/SKILL.md:92`, `align-docs/SKILL.md:49`, `qa-criteria/SKILL.md:44-45`) are file paths and routing only. The setup-template "one row per" hits are unrelated. Confirmed unaffected.
  - `.claude/agents/qa-evaluator.md:48` only lists CSV paths. Confirmed unaffected.
  - Missed by the grep: `README.md:100` misspells the table as `claudeuseagesummary`. This dates from commit acc004fe (2026-07-29), so it predates this goal. See minor note 1.
  - Not stale, but worth deciding on: `client-package/INSTRUCTIONS.md:87` and `:107`. See minor note 2.
- **Scope → PASS.** Only `README.md` changed after Phase 6.4 started. Its modification time is 13:59:01, after `19-context.md` at 13:58:32. Every code and test file is older: `export.py` 11:46, `project_label.py` 11:42, `test_export_unattributed.py` 13:38, `COVERAGE_MAP.md` 13:40. `fabric/README.md` (13:30) was changed in task 03. `client-package.zip` was last modified 2026-09-25, before this goal. `git diff HEAD --name-only` shows only the goal's audited files plus the two READMEs and the zip. Nothing under `client-package/`, `deploy/`, `.claude/` or `CLAUDE.md` changed.
- **Anti-invention → PASS.** Each of the three Phase 6.4 edits traces to code:
  - Edit 1: the `-Users-` and control-character guards match `project_label.py:152` and `:155`.
  - Edit 2: the anchor resolves to `README.md:337`, and the column names match `export.py:44` and `:48`.
  - Edit 3: I checked the "class lookup for `unknown` rows only" claim by running it (see below). "One read of the session timeline per build" matches `export.py:85` and `project_label.py:172`.

### What I verified
- Column lists in fabric/README.md:42-43 equal `SUMMARY_FIELDS` and `LINE_FIELDS` (`export.py:41-48`), in order, with the two new columns last. ✅ Verified (compared by hand).
- The two new columns are filled only on `unknown` rows and blank on attributed rows. ✅ Verified at `export.py:91-99`, and my scratch build printed `attributed line rows blank: True`.
- The class values and their meanings in the README table (`timeline`, `no_remote`, `absent`, `desktop-scratch`), and "`wrapper` not expected on unknown rows". ✅ Verified against the CASE order in `attribute.py:87-94`. My scratch build returned exactly the four classes for unknown rows and never `wrapper`.
- `unattributed_project` is blank when the session has no timeline, which is always the case for `no_remote`/`absent`. ✅ Verified. Those two classes are reached only when the `_AS_OF` and `_FIRST` lookups are both NULL (no timeline rows), and labels are keyed on session ids from the timeline. My build gave `('absent','')` and `('no_remote','')`.
- The walk-up rule, the special labels and the privacy guard. ✅ Verified by running `root_label` on every README example and some extra cases, all of which matched:
  - `...\Code\Dashnoard` and its `...\OfficeDashboard\backend` subfolder → `local:Dashnoard`
  - `...\source\repos\proj` → `local:proj`
  - `...\Documents\foo\bar` → `local:bar`
  - the Sumit shape → `local:ai-presales-agent-main`
  - `C:\Cyclotron\proj\src\components` → `local:proj`
  - `C:\Users\d\orbit` → `local:orbit`
  - `/home/<name>`, `/root`, `/mnt/c`, `/c/`, `~` and UNC prefixes (UNC re-run with exact backslashes via `chr(92)`, because the bash heredoc collapsed `\\`) all resolve as described
  - a shallower visited folder wins (`local:foo`); cwds outside the session root keep the session's label
  - `local:(home)`, `local:(scratchpad)` for `.claude` and `Temp\claude`, and `local:(other)` for a leading `.`, `C--`, `-Users-`, `OneDrive` inside a name, a bare `Users`, and the username
- Capacity claim: the class expression is evaluated only for `unknown` rows. ✅ Verified. I wrapped `attribute.attribution_source` in a counting SQL function inside a scratch script (no repo edits) and ran `export.build` on the `_seed_main` store: `ticks during build: 11`, `total rows: 17`, `unknown rows: 11`.
- Collision correction and the "Totals now match invoice.py" note. ✅ Verified. `export.py:104` and `:109` sum instead of overwrite, and the targeted suites pass: `pytest tests/test_project_label.py tests/test_export_unattributed.py tests/test_export.py tests/test_attribute.py tests/test_invoice.py -q` → `266 passed in 6.02s`.
- The Power BI caveat that "a real repo whose bill name happens to be `unknown` stays unsplit". ✅ Verified: `unknown` is tested on `resolved_repo` (the key, `export.py:95`) while the `repo` column is `name_of(key)` (`export.py:120`).
- The Fabric notebook overwrites the schema, so the new columns land on the next sync. ✅ Verified: `fabric/refresh_billing_tables.py:25-26` uses `.mode("overwrite")` with `overwriteSchema`.
- Anchors and links resolve. ✅ Verified. The single heading "Unattributed usage in the lake tables" (`README.md:337`) is linked from lines 154 and 547, and `../README.md` from fabric/README.md exists.
- `client-package.zip` staleness. ✅ Verified not stale from this phase: no `client-package/*.md` edits, and the zip (containing INSTRUCTIONS.md and ADMIN.md) was last modified 2026-09-25.
- Blank CSV cells probably load as NULL in Delta (Spark's CSV reader default), so the README's "blank" means NULL in Fabric. ⚠️ Unverified: I can't run Spark here. The documented filter `attribution_source <> ''` still works either way.

### Issues found
1. **[minor]** `README.md:100` says `claudeuseagesummary`, which should be `claudeusagesummary`. It predates this goal, but it is a misspelling of this feature's identifier, which is why the coverage grep missed it. Rated minor because it is a one-token typo in narrative text with no wrong behaviour described.
2. **[minor, needs a user decision]** `client-package/INSTRUCTIONS.md:87` says usage "is visible to whoever administers billing". After this goal, project root folder names also reach whoever reads the Fabric tables or the Power BI report. `:107` ("cannot be attributed to any project") is still true for billing but ignores the new diagnostic label. Rated minor for three reasons:
   - goal.md "Risks and rollback" records this wider audience as a known, accepted risk.
   - goal.md forbids any `client-package/` change.
   - INSTRUCTIONS.md ships inside `client-package.zip`, so editing it would make the zip stale and need a rebuild plus a `client-package/VERSION` bump, which this phase must not do.
   The orchestrator should put this to the user rather than fix it silently.
3. **[minor]** `README.md:578` is an unwrapped 127-character line from edit 3, in a section that is otherwise wrapped at about 85 characters. It renders fine; this is formatting only.
4. **[minor]** The link at `fabric/README.md:47-48` goes to `../README.md` with no anchor. It could use `../README.md#unattributed-usage-in-the-lake-tables`. The link works, so this is a convenience only.

### Notes (non-blocking)
- Minors 1–4 above.
- On the outer zone, `README.md:362-366` reads as if the home prefix is required. In the code it is optional (`_home_len` can return 0), so `C:\Code\p\x` → `local:p`, which matches goal.md's "home / drive / OneDrive level". The drive-stripping sentence partly covers this. It's an ambiguity, not an error.
- The Power BI filter `repo = 'unknown' AND attribution_source <> ''` would miss unknown rows if an admin ever mapped the key `unknown` to another bill name through `repo_name_map`. `attribution_source <> ''` (or `IS NOT NULL` in Delta) on its own is more robust. ⚠️ I did not check whether `repos export` lists `unknown`.
- The Phase 6.4 implementer did not read `align-docs/SKILL.md` or `goal.md` (they said so in their report). Their edits still hold up against the code.

### Required fixes (if NEEDS FIXES)
- None required. Optional surgical fixes, if the orchestrator wants them:
  - [ ] `README.md:100`: change `claudeuseagesummary` to `claudeusagesummary`.
  - [ ] `README.md:577-578`: re-wrap the edit-3 sentence to the section's width.
  - [ ] `fabric/README.md:48`: change `[`README.md`](../README.md)` to `[`README.md`](../README.md#unattributed-usage-in-the-lake-tables)`.
  - [ ] Ask the user about the `client-package/INSTRUCTIONS.md:87` audience wording. Any edit there needs a zip rebuild and a VERSION bump outside this phase.

### Docs changed (this goal)
- `README.md`: the `project_label.py` and `export.py` module bullets, the table grain lines, the new section "Unattributed usage in the lake tables", the pilot `unknown`-rate pointer, and the capacity checkpoint sentence.
- `fabric/README.md`: the corrected column lists (`repo` / `repo, repo_key` instead of `bill_name`), the two new columns, and the note on when they are filled.
- `tests/COVERAGE_MAP.md` also changed. It is a test artifact, already audited in Phase 5, and not a Phase 6 doc edit.

No markdown linter is configured that I could find, and none was run.

### Footprint
files_read: 11 (~72000 chars)
commands_run: 15
