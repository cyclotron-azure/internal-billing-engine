**Model (self-reported)**: claude-sonnet-5-5
## Docs fix cycle 1 complete

### Edits
1. README.md `timeline` table row: added "no real-repo timeline row in the session at or below that folder (for example an unrelated sibling folder, or a session whose timeline rows are all `unknown`), an empty or missing cwd" before the existing reasons, which are kept. The row is still a single line. Checked against attribute.py `_inherit_table`: the `_x` qualifying rows, the `n <> ''` guards, and the count>0 / min=max rule.
2. README.md Capacity checkpoint: replaced the single figure with a range. About 0.24 s per 100k datapoints for a plain `resolved_view` scan (21-report.md l.23/86). Up to about 0.87 s per 100k for the real export / bill statements (14-report.md l.53: "0.869 and 0.626 s per 100k" under load; 13-report.md l.43: 0.828). About 0.33 s on a quiet machine (14-report.md l.49/52). The "synthetic stores, not production data" caveat is kept.
   - Omitted: the "~130k datapoints / ~44k timeline rows" detail. I did not find it in 13/14-report, so the wording reads "~100k-130k datapoints and ~40k timeline rows". The 100k and 40,300 are from 21-report.md. The ~130k is from the coordinator's brief and I did not confirm it in the reports. Drop it if you want strict sourcing.
   - Omitted: the "reconcile" statement. Only export and bill were found in 13/14, so the README says "export / bill".
3. .claude/skills/test-ladder/SKILL.md l.75: the attribute.py row now reads `tests/test_attribute.py` and `tests/test_attribute_inheritance.py` **plus** `test_bill.py`, `test_invoice.py`. No other row changed.
4. tests/COVERAGE_MAP.md Task 01 row 5: the tie-break wording now says the final tie-break is `repo` (DESC as-of, ASC first-row) after `ts` and `seq`, and `rowid` only identifies the selected row. This matches attribute.py l.100-114 and the `resolved_repo` docstring. The cited tests are unchanged.
5. tests/COVERAGE_MAP.md Task 02 row 1: now "129 tests at first authoring, 136 after fix cycle 1, 196 at PASS". `pytest tests/test_attribute_inheritance.py --collect-only -q` gave 196. I confirmed 136 only as the rung-2 count in 14-report.md; 129 is from the brief.
6. README l.153 now reads "folder of related real-repo timeline rows (same folder or below it), and ...". The rest of the bullet is unchanged.

### Verification
- `git status --short`: M .claude/skills/test-ladder/SKILL.md, M README.md, M billing/otel/attribute.py, M tests/COVERAGE_MAP.md, ?? _goals/unknown-parent-child-inheritance/, ?? tests/test_attribute_inheritance.py. I edited only the three fenced files; attribute.py and the untracked files were already changed before I started.
- `git diff --stat` for the three files: SKILL.md 2 lines, README.md 35 lines (+ earlier cycle), COVERAGE_MAP.md +58, which includes the earlier-authored new section. Git warned that COVERAGE_MAP.md LF will become CRLF; I did not change its line endings.
- No test suites were run apart from the one collect-only. No git state-changing commands. deploy/, client-package/, _goals/ and _research/ are untouched.

### Footprint
files_read: 6 (~40000 chars)
commands_run: 3
