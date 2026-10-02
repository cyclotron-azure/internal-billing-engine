You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-10-02T20:00:00-10:00

## Task
PHASE 6 (align docs) - edit ONE document: `README.md` (project root:
C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine). Bring it in sync with the
shipped change to `billing/otel/attribute.py` (goal `unknown-parent-child-inheritance`). README.md is
ground truth: when code and README disagree, the README is corrected. DOCS-ONLY.

## Core guardrails (NON-NEGOTIABLE)
1. NEVER write under `_goals/` or `_research/` (you may READ them).
2. DOCS-ONLY: never modify code, tests, config, `deploy/`, `client-package/` or any file but `README.md`.
3. ANTI-INVENTION: every documented claim must trace to a file you read THIS run (cite the file in your
   report). If a detail is unconfirmed, OMIT it. Do not invent flags, names, numbers or behavior.
4. SCOPE DISCIPLINE: update only STALE or MISSING content; preserve accurate prose VERBATIM; surgical
   edits (use the Edit tool on exact strings), no rewrites, no reformatting. Preserve the file's existing
   line endings and markdown style (headings, tables, bullet style).
5. Do not edit or regenerate `client-package.zip`.
6. Never run git checkout/restore/stash/reset/commit; the working tree has UNCOMMITTED code from this goal.

## What shipped (verify each fact in `billing/otel/attribute.py` - the module docstring and the
`resolved_repo` / `resolved_view` docstrings are the authoritative description; read them first)
- Resolution is still done at QUERY time and never persisted. `resolved_repo` / `attribution_source` /
  `resolved_view` keep their names, signatures and columns; consumers (bill, invoice, reconcile, export,
  `deploy/unknown-report.py`) are unchanged.
- NEW: when a datapoint's effective timeline row (the as-of row, else the session's first row) is
  `unknown`, it may INHERIT a real repo, under a strict rule: the unknown row's folder must be the SAME as
  or an ANCESTOR of the folder of real-repo timeline rows in the same session (real rows at the same
  folder or BELOW it); all qualifying real rows must name ONE repo (two or more distinct repos -> stays
  `unknown`); an unknown CHILD of a real repo's folder never inherits; real rows count whether they come
  before or after the datapoint; `DirectoryAdded` rows never serve as the real anchor; the literal session
  id `unknown` never inherits.
- The unknown folder must be project-level: roots, home folders, top-level folders directly under a root,
  and generic container folders (names listed in the code's `_CONTAINER_NAMES`, plus `onedrive*` and
  `visual studio *`) are blocked anchors. Paths are compared case-insensitively (SQLite `lower()` is
  ASCII-only) with `\` and `/` treated alike. Read the exact rules in `_blocked` / `_norm`.
- Rows resolved through inheritance report `attribution_source = 'timeline'`; `desktop-scratch` is still
  checked first and keys off `resolved_repo = 'unknown'`.
- A repo-based final tie-break (not rowid) picks between timeline rows with identical (session, ts, seq).
- Because resolution is query-time, a late or corrected timeline retroactively re-resolves history in
  BOTH directions (a late second related repo can flip previously inherited usage back to `unknown`).

## Required README edits (from the final audit; verify the line numbers, they may have shifted)
Locate by content, not just by number; the audit's references were: README.md:153 (`attribute.py`
bullet), :160 (`bill.py` bullet, "every multi-repo session"), :289 (flow diagram text "as-of join"),
:364-365 and :378-412 ("Unattributed usage in the lake tables" / `unattributed_project`), :371 (the
`timeline` row of the `attribution_source` table), :414-417 ("Accepted mislabels"), :508-510 (sessions must
start inside a git repo with an `origin` remote), :566-568 ("captured->tagged is the `unknown` bucket
(sessions outside a git repo)"), :606-608 (Capacity checkpoint).
1. `attribute.py` bullet: add the ancestor/same-folder inheritance rule, single-repo rule, blocked
   anchors summary, the DirectoryAdded and session-id exclusions, ASCII-only lower(), query-time only;
   extend the retroactivity sentence (late second related repo can flip it back). The fallback-chain
   order sentence stays correct - keep it.
2. Flow diagram / "Typical OTEL flow" text mentioning the as-of join: mention inheritance.
3. `attribution_source` table `timeline` row: also covers an unknown row that could NOT inherit (blocked
   anchor, a child of a real repo, 2+ related repos, only a DirectoryAdded anchor, or session id
   `unknown`) - not only "no git remote".
4. `unattributed_project` section: sessions that start in a project-level ancestor folder and later move
   into exactly one real repo below it no longer produce `unknown` rows, hence no `local:<folder>` label
   for that usage (history relabels after re-export).
5. "Accepted mislabels": reconcile with the new rule so readers do not assume the reverse direction also
   stays unknown (a real-repo start followed by a no-remote CHILD folder is still `unknown`; an unknown
   ANCESTOR start followed by a real repo below it now inherits).
6. Sessions "must start inside a git repo with an origin remote (else repo=unknown)" -> soften to the
   accurate statement (a project-level ancestor start is recovered if the session moves into exactly one
   real repo below it).
7. captured->tagged "the unknown bucket (sessions outside a git repo)" -> small wording update (the bucket
   shrinks as ancestor-start sessions are recovered).
8. Capacity checkpoint: every `resolved_view` statement builds an inheritance lookup over the WHOLE
   `session_repo_timeline` regardless of the query's date window; cost grows with total timeline rows
   (UserPromptSubmit re-tagging adds rows on every prompt). Only state numbers you can source: the
   goal's measured figures are in `_goals/unknown-parent-child-inheritance/spawns/21-report.md`
   (about 0.25-0.87 s per 100,000 datapoints on synthetic stores); cite them as measured on synthetic
   stores, or omit numbers.
9. `bill.py` bullet / MULTI-REPO SESSIONS: `multi_repo_sessions()` in `billing/otel/otel_store.py`
   (read it) uses raw timeline repos, so a session that inherits still prints as split across repos
   while billing wholly to the real repo. Document this accurately (diagnostic only; billing amounts
   unaffected) - verify against `bill.py` and `otel_store.py` first; if you cannot confirm, OMIT.
Also scan the rest of README.md for any other statement the shipped change makes untrue (grep for:
`as-of`, `timeline`, `unknown`, `session_repo_timeline`, `outside a git repo`, `no git remote`,
`desktop-scratch`) and fix it surgically; list anything you changed beyond the nine items.
Do NOT edit statements about `deploy/` or `client-package/` behavior unless README.md itself (not those
directories' own READMEs) states something untrue.

## Files to Read FIRST
- billing/otel/attribute.py (all), billing/otel/otel_store.py (`multi_repo_sessions`), billing/otel/bill.py (multi-repo output)
- _goals/unknown-parent-child-inheritance/goal.md, spawns/21-report.md (audit; README list + delivery notes)
- README.md (the sections listed above, and a grep sweep for the stale markers)

## Write fence
ONLY: `README.md`

## Model
requested: claude-sonnet-5 · tier: light · rotation: cycle 1

## Rules
- Test ladder: docs-only, no testable code - skip all rungs. Do NOT run the test suite.
- Fix the doc, never the code. If the only accurate fix would require a code change, STOP and report.

## Output
Report: a list of every edit (location, before -> after summary, the source file you verified it
against), anything you could not confirm and therefore omitted, any README statements you found stale
beyond the nine items, `git status --short`, `git diff --stat -- README.md`, and a `### Footprint` block
(`files_read: <N> (~<C> chars)`).
