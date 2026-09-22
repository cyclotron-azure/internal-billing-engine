You are the evaluator subagent, in **audit mode**. Read: .claude/agents/evaluator.md

Fresh spawn. CURRENT_DATETIME: 2026-09-21T15:30-04:00

## Task

Phase 6.5 final docs audit, **cycle 2** (cycle 1 returned ISSUES with 4 blocking, 6
non-blocking findings — see `_goals/otel-export-loss-reduction/orchestration-log.md`
entries around spawn #38 for the full list, and spawns #39-#41's outcomes for what was
fixed). Verdict: **APPROVED** or **ISSUES**. If ISSUES, this is cycle 2 of 3 max before
escalation, per this goal's established pattern.

## What was fixed since cycle 1

**Blocking:**
1. `README.md:95` self-contradiction (said "desktop-app usage" while `:147` said
   "desktop-app, CLI, and VS Code usage") — now both say the same thing.
2. `fabric/README.md:51-56` rate-card warning understated scope — now cites
   `COST_SOURCE`/`ALLOWED_ENTRYPOINTS` and covers all transcript-sourced usage.
3. `README.md:181-186`, `:507-508`, `:532` transcript-hook description never extended —
   now extended at all three spots.
4. `README.md:88` interval regression (a previous pass's own fix said "~10 seconds" for
   a sentence covering two mechanisms with different intervals) — now distinguishes
   "10s normally (5s if you used `dev-selftest.sh`)".

**Non-blocking, also addressed:**
5. `deploy/README.md:371` stale parenthetical — fixed.
6. `client-package/INSTRUCTIONS.md` vs `ADMIN.md` naming inconsistency — both now say
   "transcript-recovery hook".
7. `client-package/ADMIN.md:198,212` present-tense `pilot-package/` references — now
   framed as historical, matching `README.md`'s own wording.
8. `GET /healthz` undocumented — added to `README.md` §1 and to `deploy/README.md`
   section 4 as a curl example.
9. Two imprecise citations in `deploy/README.md` §3a — independently re-derived to the
   real implementation lines (`deploy/claude-transcript-usage.py:783-867` for the replay,
   `:978-983` for the tallies) rather than the docstring/early-return branch cited before.
10. `README.md:453` residual desktop-only framing — extended.

**Deliberately not touched, ruled correct on inspection both times:**
- `README.md:75` in `client-package/INSTRUCTIONS.md`-equivalent — a wire-schema field
  description, not a scope claim; left as narrower-but-accurate.
- `README.md:406` (now ~404) — "the one surface with no OTLP exporter of its own is the
  desktop app" is a distinct, still-true claim from the hook's broader recovery scope;
  not a contradiction.

Full suite orchestrator-confirmed unaffected: **432 passed** (docs-only changes).

## What to verify

1. **Re-check the four blocking findings are actually closed** — read each spot
   yourself, don't trust the fix reports' own "before/after" quotes as sufficient.
2. **Coverage, again.** Cycle 1's discovery missed several things on the first pass —
   don't assume this fix cycle caught everything either. Re-sweep `README.md`,
   `deploy/README.md`, `fabric/README.md`, `client-package/INSTRUCTIONS.md`,
   `client-package/ADMIN.md` for any remaining "desktop-app usage"-only phrasing that
   should now read as desktop+CLI+VS-Code, and re-check the surface map's other named
   docs (`docs/`, `.claude/ORCHESTRATION.md`) for anything neither pass touched.
3. **Did any fix introduce a new inconsistency?** In particular: `README.md:88`'s new
   parenthetical phrasing — does it read cleanly, and is "10s normally" actually
   accurate (cross-check `deploy/managed-settings.json` and `client-package/configure.py`
   both say `"10000"`)? The two re-derived citations in `deploy/README.md` — confirm the
   new line numbers actually point at what they claim by reading
   `deploy/claude-transcript-usage.py` yourself.
4. **Scope** — `git status` should show only markdown files changed since cycle 1 (plus
   the orchestration log / `_goals` ledger, which is expected and out of this skill's
   jurisdiction to flag).
5. **Anti-invention** — spot-check at least 3 claims against source, not against the fix
   reports.

## Rules

Evaluate only — **no repository writes**. Model: claude-opus-5 · tier: frontier.
Keep the report compact.

## Output

```
VERDICT: APPROVED | ISSUES
MODEL: <model>

## The four blocking findings
[One line each: closed / not, how verified.]

## Coverage sweep
[Anything still missed, or "none found".]

## New issues from the fixes themselves
[Any, or "none".]

## Scope & anti-invention
[git status confirmation; 3+ spot-checks against source.]

## Findings
[BLOCKING / NON-BLOCKING, or "none".]

### Footprint
files_read: <N> (~<C> chars)
```
