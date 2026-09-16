MODEL: claude-sonnet-5 (reported)
STATUS: completed

> **Stub, not verbatim.** From this spawn onward the ledger stores a condensed verdict
> rather than the full agent report, at the user's request to reduce token spend. Full
> report text is in the session transcript.

## What changed (billing/reconcile.py only)

- Dropped the dead `DEDUPE_EPOCH_META_KEY` import; fixed the falsy-epoch guard to
  `if not epoch or epoch_day >= end:` (the two carried-over task-02 cleanups).
- Added `--by-surface`, `--daily`, `--detail` (implies both).
- `run()` gained keyword-only `by_surface` / `daily`; existing call shapes unaffected.
- New `_pair()` helper: exact thousands-separated integer beside every `ftok()` figure.
- New `RULE_WIDTH = 108` constant (sized to the widest `--daily` row) + `_wrap()` for prose.
- `UNMAPPED TOKEN TYPES` and `DEDUPE DROPS` print unconditionally with the funnel.
  `DEDUPE DROPS` counts render independently of measurement state — states 1-3 can show a
  non-empty `by_type` (the criteria 7b/7c requirement).
- `--by-surface` header states "share of captured, NOT coverage"; each sub-block ends with
  a `TOTAL` row at `100.00%`.
- No-analytics-rows branch and `AnalyticsError` branch untouched; `store.close()` still
  fires on every return path.

## Verification claimed

- `python -m pytest tests/test_otel_store.py -q` -> `27 passed in 2.70s` (rungs 1-2 only).
- Claims all 6 required output scenarios were captured and that every rule line is exactly
  108 chars with no line exceeding it, verified programmatically.

## ORCHESTRATOR NOTE — report format deviation

The agent returned a **summary instead of the required verbatim output paste**. The
context package (`08-context.md`) required the full stdout of six invocation scenarios,
stating "This output IS the deliverable. Paste it, do not summarize it." It did not.

Consequence: the central claim of this task — that the rendered output is correct and
legible — is **unevidenced in the ledger**. Rather than re-spawn (token cost), the task-03
evaluator is instructed to capture all six scenarios itself and judge the real output.
Every rendering criterion is therefore verified by the evaluator, not by this report.

Also flagged by the agent, not a defect: a pre-existing em dash in the synthetic-data note
renders mangled on this Windows console codepage. Display artifact, outside the fence.
