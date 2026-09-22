You are the implementer subagent, executing a Phase 6 fix cycle per
`.claude/skills/align-docs/SKILL.md`. Read that skill file first.

CURRENT_DATETIME: 2026-09-21T15:00-04:00

## Why this spawn exists

The previous pass on this file worked partly from a fact list rather than reading the
whole document, and left the file **self-contradicting**: line 147 (which that pass
correctly rewrote) says `/v1/transcript-usage` handles "desktop-app, CLI, and VS Code
usage," while line 95 still says it "ingests desktop-app usage" — same document, two
answers. It also introduced a new factual error by sharpening a vague sentence without
checking that the sentence covered two different mechanisms with different numbers.

**Do not repeat that failure mode.** Read every cited line's actual surrounding
paragraph in `README.md` yourself, and cross-check every fact against the source file
named below — not against this package's summary of it.

## Fix 1 — the self-contradiction, `README.md:95`

Currently: "It also accepts `POST /v1/transcript-usage` — a batched, authenticated
endpoint that ingests **desktop-app usage** recovered from on-disk Claude Code
transcripts by the `claude-transcript-usage.py` hook (see `billing/otel/transcript.py`)."

Read `billing/otel/transcript.py`'s `ALLOWED_ENTRYPOINTS` yourself to confirm it now
includes `claude-desktop`, `cli`, and `claude-vscode` (it does — but confirm it, don't
take this sentence's word for it). Update this line to match line 147's framing: usage
from desktop, CLI, and VS Code, not desktop only. Keep the sentence's existing structure
and brevity — this is a one-paragraph module overview, not the place for mechanism
detail (that lives in `deploy/README.md`).

## Fix 2 — the interval regression, `README.md:88`

Currently: "`.claude/settings.local.json` (gitignored) points this machine at a local
receiver, so a `claude` session in this repo produces real rows. `deploy/dev-selftest.sh`
does the same as a one-off launcher without changing your settings. Telemetry starts
with the **next** session, and exports every 10s — so give it ~10 seconds before
checking."

**This sentence covers two different mechanisms with two different export intervals.**
Read `deploy/dev-selftest.sh` yourself: `OTEL_METRIC_EXPORT_INTERVAL=5000` (5 seconds),
not 10. `.claude/settings.local.json` is gitignored and not readable here, but it points
at "a local receiver" using whatever the machine's real Claude Code settings carry —
which, per this repo's fleet config, is 10s (`deploy/managed-settings.json`,
`client-package/configure.py` — read at least one to confirm the value is `"10000"`).

Fix the sentence so it's accurate for **both** paths without inventing a false
precision. Do not just revert to "a few seconds" (that was the original vague wording
this task series was trying to improve) — instead, either split the sentence to give
each mechanism its own correct number, or phrase it so the reader understands the number
varies by which path they used (e.g. "10s normally, or 5s if you used
`dev-selftest.sh`"). Your call on exact phrasing; the requirement is that neither number
in the final text is wrong for the mechanism it's attached to.

## Fix 3 — the transcript-hook description never extended, `README.md:181-186`, `:507-508`, `:532`

Three more spots in this same file describe `claude-transcript-usage.py` / "the
transcript hook" as recovering desktop-app usage only, contradicting the line-147 fix a
previous pass already made:
- `:181-186` — the module bullet for the hook.
- `:507-508` — described as "what recovers desktop-app usage."
- `:532` — "Without the transcript hook, desktop-app usage simply never bills anyone."

Read all three in their surrounding context. Extend each to name the CLI/VS-Code
backfill role alongside desktop — brief additions, matching the brevity `deploy/README.md`
already established for the fuller explanation (don't duplicate mechanism detail here;
one clause per spot is enough, e.g. "...recovers desktop-app, CLI, and VS Code usage").
Keep the desktop-exporter rationale wherever it appears — you're extending scope, not
replacing the reason desktop needed this in the first place.

## Fix 4 — residual desktop-only framing, `README.md:453`

Listed as a truth→captured coverage-loss cause: "desktop-app sessions not yet swept."
This now understates the same loss category — a CLI/VS-Code session whose export never
flushed is also a truth→captured loss recovered by the same sweep, not just desktop.
Read the surrounding paragraph (this is in a coverage-funnel explanation) and extend the
phrase accordingly, briefly.

## Fix 5 (optional, small) — `GET /healthz` is undocumented in §1

`README.md` §"1: Receiving telemetry data" (around lines 93-97, the section you're
already editing for Fix 1) has no mention of `GET /healthz` at all, despite the surface
map in `align-docs/SKILL.md` routing receiver.py route changes here. Add one brief
sentence noting the receiver also exposes `GET /healthz` for liveness/freshness
checking — do not enumerate its response fields here, that's excessive detail for this
section; one clause is enough. Read `billing/otel/receiver.py`'s `do_GET` handler
yourself to confirm the route exists and its basic behavior before writing the sentence.

## Write fence

```
README.md
```

Nothing else.

## Rules

- Read the actual source file for every fact — `billing/otel/transcript.py`,
  `deploy/dev-selftest.sh`, `deploy/managed-settings.json` or `client-package/configure.py`,
  `billing/otel/receiver.py`. Cite file:line for each in your report.
- Preserve every already-accurate sentence's structure; extend, don't rewrite wholesale.
- Do not touch any other file.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Fix 1 (verbatim, before/after)
## Fix 2 (verbatim, before/after, and which phrasing approach you chose)
## Fix 3 (verbatim, all three before/after)
## Fix 4 (verbatim, before/after)
## Fix 5 (verbatim, the new sentence, or "skipped" + why)

## Facts cited (file:line for each, confirming YOU read it this run)

## Self-check: any other "desktop-app usage" phrase in this file describing
## /v1/transcript-usage or claude-transcript-usage.py that you found and either
## fixed or are reporting as out of scope
[List them. "None found beyond the five fixes above" is a valid answer if true.]

### Footprint
files_read: <N> (~<C> chars)
```
