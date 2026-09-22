You are the implementer subagent, executing a Phase 6 fix cycle per
`.claude/skills/align-docs/SKILL.md`. Read that skill file first.

CURRENT_DATETIME: 2026-09-21T15:00-04:00

## Fix 1 — `fabric/README.md:51-56`, understated billing-accuracy warning

Currently the estimated-vs-actual cost warning says only: "Desktop-app usage (captured
via the `desktop-usage-capture` goal) is billed from a placeholder rate card." Read
`billing/otel/transcript.py` yourself: `COST_SOURCE = "rate_card"` (line ~185) is applied
unconditionally by `map_record` (line ~581) to **every** transcript-sourced row, and
`ALLOWED_ENTRYPOINTS` (line ~158) now includes `cli` and `claude-vscode` alongside
`claude-desktop`. So every backfilled CLI/VS-Code transcript row also lands
rate-card-estimated dollars, not just desktop-app rows. This is a billing-accuracy
warning — understating its scope is the wrong direction to be wrong in. Extend the
sentence to cover all transcript-sourced usage, not desktop only. Read the surrounding
paragraph first so your edit fits its structure.

## Fix 2 — `deploy/README.md:371`, stale parenthetical

A previous pass extended most of this file's framing but missed one spot: "the
transcript hook's batched `POST /v1/transcript-usage` (desktop-app usage)". Update the
parenthetical to match the rest of the file's now-corrected framing (desktop, CLI, and
VS Code) — brief, matching the surrounding table/list style.

## Fix 3 — `deploy/README.md`, two imprecise citations in section 3a

A previous pass's new paragraph in `## 3a. claude-transcript-usage.py` cites:
- `deploy/claude-transcript-usage.py:102-119` for "the one-time historical replay" —
  read the file yourself: that range is module **docstring prose**, not the
  implementation. The actual replay logic is around line 783 and line 866 (confirm the
  real line numbers by reading the file — don't trust these approximate ones either).
- `deploy/claude-transcript-usage.py:810-811` for "per-run tallies" — that's the
  zero-file early-return branch, not where the real tally write happens (around line
  978 — again, confirm by reading, don't just trust this number).

Both underlying claims are true; only the citations are imprecise. Update them to point
at the actual implementation lines. Read the file yourself to find the correct line
numbers — do not guess or extrapolate from the approximate numbers given here.

## Fix 4 — `deploy/README.md`, `GET /healthz` operator-facing documentation gap

Neither the "### Verify on a machine" section nor the troubleshooting table anywhere in
this file mentions `GET /healthz`, despite it being a new operator-facing liveness/
freshness check. Read `billing/otel/receiver.py`'s `do_GET` handler yourself to confirm
its behavior (unauthenticated: `{"status","now"}`; authenticated with a matching bearer
token: adds `last_ingest_at`, `last_otlp_ingest_at`, `stale_seconds`,
`otlp_stale_seconds`; unknown path 404s; store-read failure 503s). Add one short verify
example (a `curl` line is fine, matching the existing verify-command style in this file)
showing an operator can check receiver liveness this way. Keep it brief — this is not
the place for exhaustive field documentation, just enough for an operator to know the
route exists and what it's for.

## Write fence

```
fabric/README.md
deploy/README.md
```

Nothing else.

## Rules

- Read the actual source file for every fact and cite file:line, confirming you read it
  this run (not from this package's approximate line numbers).
- Preserve existing accurate prose; extend surgically.
- Match each file's existing voice and formatting conventions.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Fix 1 (verbatim, before/after)
## Fix 2 (verbatim, before/after)
## Fix 3 (the corrected line numbers, verified by your own read, and the updated text)
## Fix 4 (verbatim, the new verify example)

## Facts cited (file:line for each, confirming you read it this run)

### Footprint
files_read: <N> (~<C> chars)
```
