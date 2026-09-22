You are the implementer subagent, executing a Phase 6 fix cycle per
`.claude/skills/align-docs/SKILL.md`. Read that skill file first.

CURRENT_DATETIME: 2026-09-21T16:05-04:00

## Context

A parallel spawn is correcting `client-package/INSTRUCTIONS.md` and
`client-package/ADMIN.md`, which is where the bulk of a newly-discovered issue lives
(`client-package` no longer ships `claude-transcript-usage.py` at all — a separate,
already-committed change, unrelated to your fence). You don't need those details for
this spawn; your two fixes are independent.

## Fix 1 — `README.md`, "same hook" (singular) is now inaccurate

Two spots (search for "same hook" and "install the same"):
- Around line 125 — "They install the **same hook**"
- Around line 204 — "same receiver, same hook"

Both describe the MDM track (`deploy/`) and the opt-in track (`client-package/`) as
installing identical hooks. Read `client-package/build.py`'s `PACKAGE_FILES` yourself
to confirm: the opt-in track ships only `claude-repo-tag.py`; `claude-transcript-usage.py`
is deliberately excluded from it (see the comment above the `PACKAGE_FILES` tuple, ~line
57). The MDM track (`deploy/managed-settings.json`) still registers both hooks. So the
two tracks no longer install the same set. Correct both sentences to reflect this — brief
edits, keep the surrounding sentence structure; don't explain the full reason here, one
clause noting the sets now differ is enough (e.g. "the same repo-tag hook" instead of
"the same hook", if that's accurate — verify the exact wording holds before using it).

## Fix 2 — `README.md:88`, the "10s normally" claim is unverifiable for its own subject

Current text (added by a previous fix in this same series): "...exports every 10s
normally (5s if you used `dev-selftest.sh`) — so give it ~10 seconds before checking."

The sentence's actual subject is `.claude/settings.local.json` (gitignored, not readable
in this repo) and `deploy/dev-selftest.sh` (readable, confirmed `5000` at line 24). The
"10s normally" claim asserts a value for the **gitignored file**, which cannot be
verified from the repo — and `deploy/dev-selftest.sh:24`'s own inline comment notes
Claude Code's own **default** is 60s, so a reader whose local settings file doesn't
override the interval would actually wait 60s, not 10.

Fix: stop asserting a specific number for `.claude/settings.local.json`'s content, since
it can't be verified and may not even be true. Rephrase so the sentence only makes claims
you can verify from files in this repo — e.g. state the `dev-selftest.sh` number
concretely (5s, confirmed), and either omit the settings.local.json number entirely or
phrase it as "whatever your local settings configure" rather than asserting "10s". Keep
the sentence brief; this is a "how to test locally" aside, not a spec.

## Fix 3 — `.claude/skills/align-docs/SKILL.md`, duplicated paragraph

Search for "In scope: everything markdown EXCEPT" — it appears twice, near-verbatim,
close together. Remove the duplicate, keeping one copy. Read the surrounding context
first to confirm which copy (if either) has additional content the other lacks, and
preserve whichever has more/is positioned better in the document's flow.

## Write fence

```
README.md
.claude/skills/align-docs/SKILL.md
```

Nothing else.

## Rules

- Read the actual current text at each spot before editing — don't assume it matches
  this package's quotes exactly (earlier fixes in this series may have shifted line
  numbers slightly).
- Verify every fact against the source file, not against this package's summary.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Fix 1 (verbatim, both before/after)
## Fix 2 (verbatim, before/after)
## Fix 3 (verbatim, before/after — confirm which duplicate was kept and why)

### Footprint
files_read: <N> (~<C> chars)
```
