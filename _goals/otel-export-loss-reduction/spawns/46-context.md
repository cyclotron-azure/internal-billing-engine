You are the implementer subagent, executing a Phase 6 fix cycle per
`.claude/skills/align-docs/SKILL.md`. Read that skill file first.

CURRENT_DATETIME: 2026-09-21T17:00-04:00

## Fix 1 — `client-package/INSTRUCTIONS.md`, the "What is collected" list still promises a retired field

Around line 75-76, one bullet says: "for desktop-app usage specifically, that it came
from the desktop app, and whether the record came from a **subagent**".

The subagent half is true (`query_source`, read from OTLP attributes, always collected).
The desktop-app half is false for this package: it describes the `entrypoint` column,
which is populated **only** by `claude-transcript-usage.py` — the hook this package does
not ship (retired 2026-09-10). Confirm yourself: `billing/otel/otel_store.py:35`'s
schema comment says `entrypoint` is "transcript rows only", and
`billing/otel/receiver.py`'s OTLP ingest path (`insert_datapoint` call, ~line 346-352)
never passes `entrypoint` at all — it defaults to `NULL`. So the receiver never records
"that it came from the desktop app" for anything the CLI/VS-Code entrypoint (what this
package actually installs) sends.

Fix: remove the desktop-app half of the bullet, keeping the subagent half (which is
true and applies to what this package ships). This section already lists only the CLI
and VS Code extension as captured surfaces elsewhere in the same file (~lines 108-110) —
match that scope here too, don't introduce a new inconsistency.

## Fix 2 (optional, small) — the duplicate hook file is undocumented

`client-package/claude-transcript-usage.py` physically exists in this directory
(byte-identical to `deploy/claude-transcript-usage.py` — confirm with a diff if you
want) even though `build.py` correctly excludes it from the shipped zip. `ADMIN.md`'s
"What's in the package" table enumerates other non-shipped repo contents (e.g.
`build.py`, `.gitattributes`) but omits this file. Add one row noting it's present in
the source tree but not packaged (same non-inclusion reasoning as the row you removed in
the previous fix cycle) — or fold a clause into the existing non-inclusion note added
last cycle, whichever fits the document's structure better without duplicating that
note's content. Your call; skip this fix entirely if you judge the existing note already
covers it clearly enough — say which you chose.

## Write fence

```
client-package/INSTRUCTIONS.md
client-package/ADMIN.md
```

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Fix 1 (verbatim, before/after)
## Fix 2 (what you did, or why you judged it unnecessary)

### Footprint
files_read: <N> (~<C> chars)
```
