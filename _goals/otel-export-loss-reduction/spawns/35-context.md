You are the implementer subagent, executing Phase 6 (docs alignment) per
`.claude/skills/align-docs/SKILL.md`. Read that skill file first — same guardrails as
always: DOCS-ONLY, ANTI-INVENTION (cite the file you read for every claim), SCOPE
DISCIPLINE (surgical, preserve accurate prose), HARD EXCLUSION of `_research/`/`_goals/`.

CURRENT_DATETIME: 2026-09-21T14:00-04:00

## What shipped (facts)

`claude-transcript-usage.py` (both copies — `deploy/` and `client-package/`, kept
byte-identical) used to ship only `claude-desktop` transcript records. It now **also**
ships `cli` and `claude-vscode` records — read `billing/otel/transcript.py`'s
`ALLOWED_ENTRYPOINTS` and `deploy/claude-transcript-usage.py` to confirm. Specifically:

- The desktop-app rationale in this doc's existing section 3a is **still entirely
  correct and must not be removed or weakened** — the desktop app genuinely has no OTLP
  exporter, full stop. That is one of two reasons this hook exists now, not the only one.
- The **second** reason, now also true: a CLI or VS Code session's OTLP export can fail
  to flush before the session ends (the receiver's export interval is 10s, but a very
  short session can still exit first). Read `billing/otel/receiver.py`'s
  `BACKFILL_MIN_AGE_SECONDS` (server-side quarantine, 900 seconds) and
  `deploy/claude-transcript-usage.py`'s own quarantine constant (client-side, 1800
  seconds — deliberately double the server's, so a record that clears the client gate
  can't still fail the server's) to get the numbers right; cite the exact file:line you
  read them from.
- A `cli`/`claude-vscode` record whose session already has a matching OTLP row is
  rejected server-side with reason `session_has_otlp` — this is a safety check, not a
  bug: it exists specifically to prevent double-billing a session whose OTLP export
  *did* eventually arrive.
- There is a **one-time historical replay**: on first run of the upgraded hook, it makes
  previously-skipped on-disk transcript history eligible for shipping (not just future
  sessions). It deliberately does **not** reach further back than the machine's original
  install date — pre-installation usage stays excluded, because that usage was never
  captured by OTLP either and billing it now would expand a client's invoice
  retroactively rather than recover lost telemetry. Read
  `deploy/claude-transcript-usage.py`'s replay-flag logic (`cli_backfill_replay_at`) to
  confirm this framing before writing it.
- The hook now reports per-run tallies in its local state (shipped, rejected-by-reason,
  deferred) — mention this exists as a troubleshooting/verification aid; do not enumerate
  every state key, this doc doesn't need that level of detail.

## Task — update `deploy/README.md`

**Edit 1 — line ~255, the troubleshooting table.** The row "Multi-repo session split
looks wrong by a small amount" ends with a dangling `(more traffic)` fragment left over
from an earlier version of the remedy column that advised lowering the interval — that
advice was removed, but the parenthetical modifying it wasn't. Remove the dangling
fragment (or reword the sentence so nothing dangles); read the current row before editing
so you don't disturb its otherwise-correct content.

**Edit 2 — the top-of-file "Four artifacts" framing (~lines 8-30).**
- The intro sentence "one recovers desktop-app usage the other three can't see at all" —
  extend it to also name the CLI/VS-Code backfill role, briefly.
- The table row `claude-transcript-usage.py | Ship desktop-app usage recovered from
  on-disk transcripts (hook) |` — reword the "Job" cell to reflect the broader scope.
- The "No transcript hook →" consequence bullet — currently says only desktop usage is
  lost. Add that CLI/VS-Code sessions whose export never flushed are *also* only
  recoverable through this hook now.

**Edit 3 — section header and opening of "## 3a. claude-transcript-usage.py (desktop-app
usage)" (~line 259 onward).**
- Retitle the section to reflect both roles (e.g. "claude-transcript-usage.py
  (desktop-app usage, plus CLI/VS Code backfill)" or similarly worded — match the doc's
  existing heading style).
- After the existing desktop-exporter paragraph (keep it verbatim — it's still correct),
  add a new paragraph explaining the second role: recovering CLI/VS Code sessions whose
  OTLP export didn't flush in time, gated by the quarantine and the `session_has_otlp`
  exclusion described above, plus the one-time historical replay and its
  install-date boundary.
- Do not rewrite the "Ships no message content..." privacy paragraph, the "### Install"
  steps, or the "### Verify on a machine" command block unless something in them is
  now factually wrong (read them first; if you find something, fix it and say so — don't
  invent additions beyond what's listed above).

## Write fence

```
deploy/README.md
```

Nothing else. In particular, do not touch `client-package/INSTRUCTIONS.md` or
`client-package/ADMIN.md` — a parallel implementer is updating those.

## Rules

- Preserve the desktop-exporter rationale exactly; you're adding a second reason, not
  replacing the first.
- Every number and mechanism you cite must trace to a file you actually read this run —
  put the file:line in your report.
- Match the doc's existing terse, technical voice. Don't over-explain.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Edit 1 (verbatim, before/after)

## Edit 2 (verbatim, before/after for the three spots)

## Edit 3 (verbatim, the new section header + the new paragraph)

## Facts cited (file:line for each number/mechanism used)

## Anything else noticed but not touched
["None" is valid.]

### Footprint
files_read: <N> (~<C> chars)
```
