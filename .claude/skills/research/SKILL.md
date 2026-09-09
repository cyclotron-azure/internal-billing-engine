---
name: research
description: Research → Plan workflow for internal-billing-engine topics needing external investigation — produces a research prompt, ingests the report, and yields an evaluated goal/task structure.
---

# Research (Deep Research → Plan Orchestrator)

For domain topics an external research agent must investigate **without codebase
access**. You coordinate four phases; the output feeds `feature` Phase 4.

## Phase 1 — Generate the research prompt

Write `_research/prompts/[topic].md` from `templates/research-prompt.md`. The prompt must
be self-contained (the researcher cannot see this repo): include the relevant facts from
README.md and the domain skill, the exact questions to answer, and the
required report structure. The user copy-pastes it to their external research tool.

## Phase 2 — Ingest the report

Save the returned report as `_research/[topic]/report.md` (structure per
`templates/research-report.md`). Read it critically: flag claims that contradict
README.md or the codebase, and list open questions back to the user.
Promote durable findings into README.md; `_research/` stays scratch.

## Phase 3 — High-level plan

Collaborative planning with the user (use Plan Mode if available): approach options with
tradeoffs, chosen direction, affected layers (Store & schema → Ingest → Attribution & normalization → Rating & billing → Export & lake sync → Client rollout).

## Phase 4 — Low-level tasks

Create `_goals/[goal-name]/` using the `feature` skill's `goal.md`/`task.md`
templates, then hand off: the goal enters the `feature` skill at its Phase 3 (goal
evaluation) — it still must PASS the evaluator before execution.
