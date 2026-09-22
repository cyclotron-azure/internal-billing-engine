You are the implementer subagent, executing Phase 6 (docs alignment) per
`.claude/skills/align-docs/SKILL.md`. Read that skill file first — DOCS-ONLY,
ANTI-INVENTION, SCOPE DISCIPLINE, HARD EXCLUSION of `_research/`/`_goals/`.

CURRENT_DATETIME: 2026-09-21T14:00-04:00

## What shipped (facts)

Same underlying change as the parallel `deploy/README.md` edit: the transcript-recovery
hook (`claude-transcript-usage.py`) that these two docs describe now ships `cli` and
`claude-vscode` transcript records in addition to `claude-desktop` ones. Read
`billing/otel/transcript.py`'s `ALLOWED_ENTRYPOINTS` to confirm. The desktop-only framing
in both files below predates this and is now incomplete, not wrong about desktop.

## Task

**`client-package/INSTRUCTIONS.md`** — find the sentences describing "the desktop-usage
hook" (search for "desktop-usage hook" and "for desktop-app usage specifically" around
lines 75-95). These currently describe the hook's job as capturing desktop-app usage
only. Add a brief clause noting it also recovers CLI and VS Code Claude Code sessions
whose telemetry export didn't reach the receiver before the session ended — keep this
short; this is a developer-facing install doc, not a design document, and the deeper
mechanics (quarantine windows, exclusion checks, the historical replay) belong in
`deploy/README.md`, which a parallel implementer is updating — don't duplicate that
content here.

**`client-package/ADMIN.md`** — find the table row `| \`claude-transcript-usage.py\` |
The desktop-usage hook that gets installed |` (around line 38). Update the description
cell to reflect the broader scope, matching the brevity of the existing table (one short
phrase, not a paragraph).

Read both files in full before editing — if either has other passages that assume
desktop-only scope and would now read as incomplete or misleading, note them in your
report; only edit the two specific spots named above unless something else is clearly
part of the same claim (e.g. a second sentence immediately continuing the same
description) — don't go hunting the whole file for tangential mentions.

## Write fence

```
client-package/INSTRUCTIONS.md
client-package/ADMIN.md
```

Nothing else. Do not touch `deploy/README.md`, `README.md`, or anything under `_goals/`.

## Rules

- Preserve existing accurate content verbatim; add, don't rewrite.
- Every claim must trace to a file you read this run — cite it.
- Match each doc's existing voice (INSTRUCTIONS.md is developer-facing and casual; ADMIN.md
  is table-dense and terse).

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## INSTRUCTIONS.md edit (verbatim, before/after)

## ADMIN.md edit (verbatim, before/after)

## Other passages noticed (not edited, per scope)
["None" is valid.]

### Footprint
files_read: <N> (~<C> chars)
```
