You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-28T23:35:00Z

## Task
Execute task 03 of goal `unattributed-usage-breakdown`: document the new lake columns in
`README.md` and `fabric/README.md` with surgical (targeted-insertion) edits. The spec is
`_goals/unattributed-usage-breakdown/03-readme-columns.md`. Implement it as written.

## Requirements
Every checkbox and Acceptance Criterion in 03-readme-columns.md. Also, from evaluator
notes carried forward:
- Describe the label rule as it is actually implemented in
  `billing/otel/project_label.py` (read the code and the task 01 spec's Definitions):
  the outer zone is the home prefix followed by a RUN of outer folders (OneDrive*,
  Desktop, Documents, Downloads, Library, CloudStorage, `Visual Studio *`) and container
  folders (Code, src, source, repos, projects, dev, git, GitHub, workspace); in-project
  containers point to their parent; WSL / Git Bash prefixes are recognised; the special
  values `local:(home)`, `local:(scratchpad)`, `local:(other)`. Plain language, a few
  examples (Dashnoard, ai-presales-agent-main, source\repos\proj), no exhaustive spec.
- The collision correction (goal.md Success Criteria / Discovery Summary): the export now
  sums usage that collapses onto one row after model normalization (`[1m]`, dated
  snapshots) or user-email coalescing; totals now match `invoice.py`; some historical
  Fabric totals rise on the next sync.
- The Power BI filter `repo = 'unknown' AND attribution_source <> ''`, and that a real
  repo whose bill name is `unknown` stays unsplit with a blank class.
- Grain lines: `unknown` rows are additionally grained by the two new columns.
- `fabric/README.md` "Result" column lists must equal `export.SUMMARY_FIELDS` /
  `export.LINE_FIELDS` exactly, in order (fixing the pre-existing `bill_name` drift).

## Files to Read
- _goals/unattributed-usage-breakdown/03-readme-columns.md (spec)
- _goals/unattributed-usage-breakdown/goal.md (Discovery Summary, Success Criteria,
  Risks and rollback)
- _goals/unattributed-usage-breakdown/01-project-label.md (Definitions, for accurate
  wording only)
- README.md (sections around lines 140–170 module bullets and 285–335 lake tables)
- fabric/README.md
- billing/otel/export.py, billing/otel/project_label.py, billing/otel/attribute.py
- .claude/skills/test-ladder/SKILL.md

## Write fence
- README.md
- fabric/README.md
(the ONLY paths you may modify; targeted insertions only, leave unrelated lines
untouched)

## Model
requested: claude-sonnet-5 · tier: light · rotation: n/a (cycle 1)

## Rules
- Docs only: no code, no tests, no `_goals/`, no `_research/`, no other doc.
- Keep the README's voice and heading structure; do not describe out-of-scope
  follow-ups (hook scratchpad fix, orbit undercount, cost_source) as done. You may name
  them as known gaps if it helps a reader.
- No git command that changes the working tree or index.
- Never put a real person's full path or username into the docs. Use the example
  folder names above, or generic ones like `C:\Users\<name>\...`.

## Output
Report: files changed; for AC1 print both export field lists and the matching README
lines; for AC2 the grep output; for AC3 `git diff --stat` and the full
`git diff README.md fabric/README.md`; any deviation; `### Footprint`.
