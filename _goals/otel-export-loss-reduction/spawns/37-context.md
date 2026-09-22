You are the implementer subagent, executing Phase 6 (docs alignment) per
`.claude/skills/align-docs/SKILL.md`. Read that skill file first.

CURRENT_DATETIME: 2026-09-21T14:00-04:00

## What shipped (fact)

`pilot-package/` and `pilot-package.zip` were deleted from this repo (user decision,
2026-09-21; `pilot-package/` had no `build.py` of its own — verify by checking
`client-package/build.py` for any `pilot` reference, there is none).

## Task

`.claude/skills/align-docs/SKILL.md` itself (lines ~29-31) states:

> **DISTRIBUTABLE ARCHIVES ARE NOT DOCS.** `client-package.zip` and `pilot-package.zip`
> are build outputs of `client-package/build.py`, not documentation.

This claim was **already inaccurate before the deletion** — `client-package/build.py`
only ever built `client-package.zip`; it never referenced `pilot-package.zip` (confirm
this yourself by reading `client-package/build.py` in full). Now that `pilot-package/`
and `pilot-package.zip` don't exist at all, the sentence is doubly wrong.

Fix: remove the `pilot-package.zip` mention from this sentence, leaving the correct
claim about `client-package.zip`. Do not describe what happened to `pilot-package.zip` —
this file's job is stating what's true now, not a changelog.

Search the rest of `.claude/skills/align-docs/SKILL.md` for any other `pilot-package`
or `pilot_package` reference and fix each on the same principle if found.

**Separately, note but do not fix:** `orchestration-kit.manifest.json` contains the same
stale text (search it for "pilot-package" to confirm) — but it is a generated JSON
artifact (not markdown), so it is outside this skill's stated scope
("In scope: everything markdown EXCEPT..."). State plainly in your report that this file
also needs correcting, likely by re-running whatever `setup`/kit-compile step generates
it from the skill source, rather than by hand-editing the JSON directly. Do not edit it.

## Write fence

```
.claude/skills/align-docs/SKILL.md
```

Nothing else — in particular, not `orchestration-kit.manifest.json`.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Edit (verbatim, before/after)

## Manifest note
[Confirm the manifest.json reference exists and that you left it untouched.]

### Footprint
files_read: <N> (~<C> chars)
```
