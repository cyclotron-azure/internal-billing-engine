You are the implementer subagent, running Phase 6.4 (align docs). Read: .claude/agents/implementer.md
and .claude/skills/align-docs/SKILL.md (guardrails section).

CURRENT_DATETIME: 2026-09-29T01:10:00Z

## Task
Phase 6.4 for goal `unattributed-usage-breakdown`: surgical doc alignment of
`README.md` after the feature shipped. Edit list has ONE doc (README.md), three edits.

## Guardrails (NON-NEGOTIABLE)
1. Never create, edit or delete anything under `_research/` or `_goals/` (read only).
2. DOCS ONLY: never modify code, tests, config, infra, or `client-package.zip`.
3. ANTI-INVENTION: every claim must trace to a file you read this run. If unconfirmed,
   omit it. No measured timing numbers in the README.
4. SCOPE: update only the stale/missing content listed; preserve every other line
   verbatim. A justified no-op for an item is allowed if you find it already accurate.
5. The README's "standard library only" runtime claim vs pytest-for-tests distinction
   must not be flattened (not expected to be touched here).

## Edit list (README.md only)
1. Section "Unattributed usage in the lake tables", the `local:(other)` special-values
   bullet (around lines 380–384): add the two guard triggers it omits, a `-Users-` slug
   prefix and control characters, so the list matches `billing/otel/project_label.py`
   (the allowlist guard, around lines 148–157). Source: project_label.py.
2. "Phase 2"/pilot metrics bullet "**The `unknown` rate** — flagged by `bill.py`…"
   (around line 543): add one short clause pointing out that the lake tables now break
   `unknown` down by `attribution_source` and `unattributed_project`, linking to
   [Unattributed usage in the lake tables](#unattributed-usage-in-the-lake-tables).
   Keep the existing sentence. Sources: export.py, the README section itself.
3. "Capacity checkpoint" (around line 571, `export.py` rebuilds all history …): add one
   short sentence that the `unknown` breakdown adds a per-datapoint class lookup for
   `unknown` rows only, plus one read of the session timeline per build. Source:
   export.py (the CASE-guarded GROUP BY and the single `load_session_labels` call).
   No numbers.

## Files to Read
- README.md (the three sections above, plus surrounding context)
- billing/otel/project_label.py, billing/otel/export.py
- .claude/skills/align-docs/SKILL.md
- _goals/unattributed-usage-breakdown/goal.md (read only, for what shipped)

## Write fence
- README.md only.

## Model
requested: claude-sonnet-5 · tier: light · rotation: n/a

## Rules
Surgical edits, existing voice; no git command that changes the tree or index; no real
usernames or full paths.

## Output
Report: the before/after text of each edit (or the no-op justification); the source
file:line each claim traces to; `git diff --stat README.md`; `### Footprint`.
