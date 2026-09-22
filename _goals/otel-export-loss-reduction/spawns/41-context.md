You are the implementer subagent, executing a Phase 6 fix cycle per
`.claude/skills/align-docs/SKILL.md`. Read that skill file first.

CURRENT_DATETIME: 2026-09-21T15:00-04:00

## Fix 1 — naming inconsistency between the two client-package docs

A previous pass renamed `claude-transcript-usage.py` in `client-package/ADMIN.md:38` to
"The transcript-recovery hook that gets installed (desktop, CLI, VS Code)" but left
`client-package/INSTRUCTIONS.md:82` and `:97` calling the same file "the desktop-usage
hook." Read both files' surrounding context. Update `INSTRUCTIONS.md`'s two mentions to
use consistent naming with `ADMIN.md` — you don't need identical wording, but the two
docs should not name the same file two different ways for a reader moving between them.
Keep each file's own voice (INSTRUCTIONS.md is casual/developer-facing; ADMIN.md is
terse/table-dense).

Also check `client-package/INSTRUCTIONS.md:75` — "for desktop-app usage specifically,
that it came from the desktop app" — read this sentence's full context. It's describing
a wire-schema field (which entrypoint a record came from), not the hook's overall scope,
so it may already be accurate as a narrower claim. If, after reading it in context, it
still reads as implying desktop is the only entrypoint the schema tracks, adjust it
briefly; if it's genuinely fine as a narrower statement, leave it and say why in your
report.

## Fix 2 — `client-package/ADMIN.md:198, 212` reference a deleted directory

`## Fixed relative to \`pilot-package/\`` and "`pilot-package/settings.json` set it"
both reference `pilot-package/`, which was deleted from this repo (2026-09-21). Read
`README.md`'s own already-corrected wording for this same fact — it says "the earlier,
now-removed pilot package." Match that framing here: these are legitimate historical
comparison points (explaining why `client-package/` is built the way it is), not a claim
that the directory currently exists — so don't delete the content, just make clear it's
historical. Do not touch `client-package/build.py` or any code.

## Write fence

```
client-package/INSTRUCTIONS.md
client-package/ADMIN.md
```

Nothing else.

## Rules

- Read both files in full context around each cited spot before editing.
- Preserve accurate historical content; just fix the present-tense implication.
- Do not delete the `pilot-package/` comparison — it's legitimate design-decision context.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Fix 1 (verbatim, before/after for both INSTRUCTIONS.md spots, and your ruling on :75)
## Fix 2 (verbatim, before/after for both ADMIN.md spots)

### Footprint
files_read: <N> (~<C> chars)
```
