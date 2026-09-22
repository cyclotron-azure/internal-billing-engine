You are the implementer subagent. This is a Phase 6 doc-accuracy fix, with one narrow
exception to the usual markdown-only fence — explained below.

CURRENT_DATETIME: 2026-09-21T17:30-04:00

## The finding, verified

`client-package/claude-repo-tag.py:82` sends `"cwd": cwd` (the developer's local working
directory) to `POST /v1/session-repo` on every one of its five registered events.
`billing/otel/receiver.py:386` stores it (`cwd=payload.get("cwd") or ""`), and
`billing/otel/otel_store.py:74` persists it in `session_repo_timeline.cwd` — a plain
`TEXT` column, "working directory that produced it".

Both of these currently claim otherwise:
- `client-package/INSTRUCTIONS.md:79` — "It does **not** collect your prompts, your
  code, file contents, **or file paths**."
- `client-package/configure.py:150` — the `COLLECTION_NOTICE` string constant, which the
  installer **prints and requires a keystroke to acknowledge before installing anything**
  — "Not collected: your prompts, your code, file contents, or file paths."

Both are false for the one hook this package actually ships. This is a consent-notice
accuracy problem, not routine staleness.

## Fix — add `cwd` to what's disclosed as collected, in both places

Do not simply delete "or file paths" from either sentence — that would leave an
ambiguous non-denial rather than an accurate disclosure. Instead, add the working
directory to the **collected** list in both places, worded plainly (e.g. "the working
directory path of the repo you're in" or similarly clear phrasing — match each string's
existing terseness). The two texts must not drift from each other in substance.

**`client-package/INSTRUCTIONS.md:73-80`** — add a bullet to the "What is collected"
list (or extend an existing one) naming the working-directory path, and correct the
"not collected" sentence to drop the now-false "or file paths" claim, replacing it with
something narrower and still true if you want to keep a boundary statement (e.g. "your
prompts, your code, or file *contents*" — read the surrounding sentence and decide
whether to keep a not-collected clause at all or let the collected list stand on its
own; either is fine as long as nothing false remains).

**`client-package/configure.py:150`, the `COLLECTION_NOTICE` string literal only** —
same correction, matching that notice's existing one-line-per-field style. **This is the
only line in this file you may touch.** Do not modify any code, any other string, any
logic. This is a text-only edit to a user-facing notice, not a behavior change — verify
after editing that `git diff client-package/configure.py` shows changes confined to
within the `COLLECTION_NOTICE = """..."""` block and nothing else.

## Fix 2 (small, same spawn) — `configure.py`'s docstring still speaks of `pilot-package/` in present tense

Read `client-package/configure.py`'s module docstring (~lines 30-32) for a `pilot-package/settings.json`
reference. `client-package/ADMIN.md` already updated the equivalent framing to
"the earlier, now-removed pilot package" — match that tense here. This is a comment,
not executable code; still keep the edit confined to that comment block.

## Write fence

```
client-package/INSTRUCTIONS.md
client-package/configure.py    (ONLY the COLLECTION_NOTICE string and the module
                                 docstring's pilot-package reference — nothing else
                                 in this file)
```

## Rules

- Read every cited line yourself before editing.
- `client-package/configure.py`: confirm via `git diff` that your change is confined to
  the two named spots (the notice string, the docstring comment) and touches zero
  executable logic.
- The two disclosures (INSTRUCTIONS.md and COLLECTION_NOTICE) must agree in substance
  after your edit.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Fix 1 (verbatim, INSTRUCTIONS.md before/after)
## Fix 2 (verbatim, COLLECTION_NOTICE before/after)
## Fix 3 (verbatim, docstring before/after)

## Confinement check
[git diff client-package/configure.py -- confirm no executable line changed.]

### Footprint
files_read: <N> (~<C> chars)
```
