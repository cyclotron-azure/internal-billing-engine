# Model Map

Model IDs are **configuration, not constants**. This file is the single place they are
defined; re-run `/setup` (or edit here and re-emit) when providers rotate model names.

Installed harness: **Claude Code only**. Columns for Cursor, Copilot, and Codex were
removed at setup time — re-run `/setup` and target those harnesses to restore them.

## Tier assignments

| Tier | Roles | Rationale |
|------|-------|-----------|
| `frontier` | orchestrator (main session), `evaluator`, `qa-evaluator`, `diagnostician` | Delegation and evaluation have a capability floor — don't cheap out on the roles that decide and verify; continuation-ladder diagnosis needs frontier-tier reasoning |
| `light` | `implementer`, `test-writer`, `terminal` | Checklist-driven execution and compact command running retain most quality at a fraction of the cost when the plan and the verification are strong |

## Resolved models

| Tier | Claude Code |
|------|-------------|
| `frontier` | `claude-opus-5` |
| `light` | `claude-sonnet-5` |

Reasoning-effort pins: evaluators `high`, workers `medium` — set as Claude Code
`effort:` frontmatter in each agent file.

## Fallback chains

| Tier | Chain (first available wins) |
|------|------------------------------|
| `frontier` | `claude-opus-5` -> `claude-sonnet-5` -> (omit pin — harness default) |
| `light` | `claude-sonnet-5` -> `claude-haiku-4-5-20251001` -> (omit pin — harness default) |

Rules (adapted from bradygaster/squad's model selector):

- **Never fall back UP a tier** — a light role must never silently land on a frontier
  model, and a frontier role never degrades below the standard rung of its chain.
- Fallbacks are silent to the user but **logged in the orchestration log**.
- Max 3 fallback attempts, then omit the model pin and take the harness default.
- Apply at most **one** complexity adjustment per spawn — no cascading bumps.
- **Cost ceiling policy**: an EXPLICIT human model choice above a plan/admin ceiling ->
  warn loudly and honor it; an implicit (auto-selected) choice -> downgrade to the
  ceiling; no compliant model at all -> fail loud — never silently substitute.
- **Prompts are executable — treat like code**: tasks that author or edit agent, skill,
  or prompt files use the frontier tier, never the docs/light tier.

### Loop fallback chain

| Chain (first available wins) | Resolves |
|-------------------------------|----------|
| `claude-sonnet-5` -> `claude-haiku-4-5-20251001` -> (omit pin — harness default) | `claude-sonnet-5,claude-haiku-4-5-20251001` |

Light-tier by default — the loop's iterations are implementer/test-writer-shaped work,
same as the `light` row above. Ends with the same omit-the-pin rule as the tables
above: a trip past the last chain entry clears the model pin and the harness default
takes over (no hardcoded model IDs outside this file).

## Fix-cycle rotation (after evaluator rejections)

A model blind to its own class of mistake rarely fixes it on retry. Rotate:

| Fix cycle | Implementer model |
|-----------|-------------------|
| 1 | `claude-sonnet-5` (normal) |
| 2 | `claude-fable-5-1` — a different model **line** at comparable tier (analytical diversity) |
| 3 | `claude-opus-5` |

### After cycle 3 — continuation ladder pins

When fix cycles 1–3 exhaust, the continuation ladder (see ORCHESTRATION.md) applies:

| Ladder step | Model pin |
|-------------|-----------|
| Diagnosis-driven implementation attempt (rung 4) | `claude-opus-5` |
| Evaluator arbitration mode (rung 5) | `claude-fable-5-1` — a different model **line** from the primary evaluator (analytical diversity at the capability floor) |

> **Single-provider caveat.** The kit's rotation rules ask for a different model
> *family* at cycles 2 and 5. On a Claude Code-only install every available model is
> an Anthropic model, so "family" degrades to a different model **line** —
> `claude-fable-5-1` against the Opus/Sonnet line. That still buys real analytical
> diversity (different training run, different failure modes), but less than a
> cross-provider rotation would. If a second provider ever becomes available in this
> harness, re-point these two rows at it.

## Harness caveats that shape tiering

- **Claude Code env overrides**: `CLAUDE_CODE_SUBAGENT_MODEL` and
  `CLAUDE_CODE_EFFORT_LEVEL` override frontmatter; org `availableModels` allowlists can
  cause pins to be ignored. This repo sits under Cyclotron org policy, so a pin that
  appears to be silently ignored is worth checking against the org allowlist before
  assuming a typo.
- **Model IDs rotate.** Verify every ID above against the live model list before
  trusting a stale map; a rotated-out ID is the most common cause of an agent running
  on an unexpected model.
