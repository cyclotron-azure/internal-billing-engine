You are the implementer subagent, executing Phase 6 (docs alignment) per
`.claude/skills/align-docs/SKILL.md`. Read that skill file first — its guardrails are
non-negotiable, especially: DOCS-ONLY (never touch code/tests/config), ANTI-INVENTION
(every claim traces to a file you read this run), SCOPE DISCIPLINE (surgical edits,
preserve accurate prose verbatim), and the HARD EXCLUSION of `_research/`/`_goals/`
(you may read them, never write).

CURRENT_DATETIME: 2026-09-21T14:00-04:00

## What shipped (facts, each traceable to the goal's own record)

- `OTEL_METRIC_EXPORT_INTERVAL` changed 60000 -> 10000 (already mostly documented).
- New `GET /healthz` route on the receiver: unauthenticated body is exactly
  `{"status": "ok", "now": <ISO8601>}`; with `RECEIVER_AUTH_TOKEN` set and a matching
  bearer token, the body additionally carries `last_ingest_at`, `last_otlp_ingest_at`,
  `stale_seconds`, `otlp_stale_seconds`. Any other GET path 404s. A store read failure
  returns 503 `{"status": "degraded"}`.
- `POST /v1/transcript-usage` now accepts `entrypoint` values `cli` and `claude-vscode`
  in addition to `claude-desktop` (verify: `billing/otel/transcript.py`'s
  `ALLOWED_ENTRYPOINTS`). A `cli`/`claude-vscode` record whose session already has an
  OTLP row is rejected `session_has_otlp`; one younger than a quarantine window is
  rejected `too_recent`; a non-`str` `session_id` is rejected `invalid_session_id`.
  `claude-desktop` records are exempt from both the OTLP-exclusion check and the
  quarantine (verify: `billing/otel/receiver.py`).

## Task — two small, surgical edits to `README.md`

**Edit 1 — `README.md` around line 88.** Current text: "Telemetry starts with the
**next** session, and exports every 10s — so give it a few seconds before checking."
"A few seconds" understates a 10-second interval — a reader who checks at 3 seconds sees
nothing and may conclude telemetry is broken. Change to state the actual window plainly
(e.g. "so give it ~10 seconds before checking" or similar — keep the sentence's existing
voice and structure, change only the vague quantity).

**Edit 2 — `README.md`'s `billing/otel/` module list, the `receiver.py` bullet** (search
for "minimal OTLP/JSON HTTP server"). Currently it describes `POST /v1/transcript-usage`
as "a batched endpoint for desktop-app usage recovered from on-disk transcripts" and does
not mention `GET /healthz` at all. Update to:
1. Add a clause noting `POST /v1/transcript-usage` also accepts CLI and VS Code usage
   recovered from on-disk transcripts, not desktop-app usage exclusively — keep it brief,
   this bullet already runs long; don't explain the exclusion/quarantine mechanics here,
   that belongs in `deploy/README.md`'s fuller treatment (a different implementer is
   updating that file in parallel — don't duplicate its content here beyond a one-clause
   mention).
2. Add a short mention of `GET /healthz` (liveness, plus authenticated freshness detail)
   — one clause is enough; this is a module-summary bullet, not a route reference.

Do not touch anything else in this file. In particular, the Network bullet and the
existing OTEL_METRIC_EXPORT_INTERVAL mentions elsewhere are already correct — verify by
reading them, but do not re-edit unless you find something else genuinely stale that
matches an above fact (if you do, note it in your report rather than silently expanding
scope).

## Write fence

```
README.md
```

Nothing else.

## Rules

- Preserve the file's existing terse voice and Markdown structure exactly.
- Every claim in your edit must trace to a file you read this run — cite it in your
  report.
- Do not invent route names, flags, or numbers beyond what's given above.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Edit 1 (verbatim, before/after)

## Edit 2 (verbatim, before/after)

## Anything else noticed but not touched
["None" is valid.]

### Footprint
files_read: <N> (~<C> chars)
```
