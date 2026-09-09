---
name: qa-criteria
description: Criteria the qa-evaluator applies to user-facing behavioral evidence for internal-billing-engine. Reference skill — not invoked directly.
disable-model-invocation: true
---

# QA Evaluation Criteria

Evaluate observed behavior from the user's perspective. Evidence not provided = behavior
not tested = an issue.

**Hard-threshold rule**: the criteria below are gates, not averages — one failing
surface **or cross-cutting check** caps the verdict at ISSUES FOUND no matter how clean
the rest are. A secrets leak, for example, caps the verdict on its own, regardless of how
clean every surface is.

## Per-surface criteria

This project has three user-facing surfaces: CLI modules, the receiver's HTTP
endpoints, and the generated billing artifacts. There is no web UI — a QA report
claiming to have checked one is itself a defect.

### CLI / command surfaces
- Exact invocation shown; output is what a user would expect and understand.
- Failure modes produce actionable messages (no raw tracebacks) and correct exit codes.
- Applies to every `python -m billing.*` entry point: `bill`, `invoice`, `records`,
  `repos`, `reconcile`, `ingest`, `report`, `fabric_sync`, `scheduler`,
  `sample_payload`.
- Date-windowed commands (`invoice`, `reconcile`, `ingest`) must distinguish "no rows
  in this window" from "the run failed" — an empty result reported as success with no
  explanation is the documented confusion in this repo, not an acceptable outcome.
- Windows console safety: output must not raise `UnicodeEncodeError` under cp1252.

### API surfaces (the receiver)
- `POST /v1/metrics` and `POST /v1/session-repo` both respond; neither 5xx's under
  normal input.
- With `RECEIVER_AUTH_TOKEN` set, an unauthenticated or wrong-token POST gets 401 —
  a 200 there is a billing-integrity failure, not a minor issue.
- A malformed body gets 400, not a traceback and not a 500.
- gzip and chunked request bodies are still handled after any receiver change.
- Dedupe holds: replaying an identical payload must not create duplicate datapoints.

### Generated billing artifacts
- `invoices/*.txt`, `summary.csv`, `line_items.csv`, `claudeusagesummary.csv`, and
  `claudeusagelineitems.csv` land at their documented paths.
- The UTC date columns are present and correct: `usage_date_utc`,
  `first_usage_at_utc`, `last_usage_at_utc`, `period_start`, `period_end`,
  `generated_at`.
- Regeneration overwrites in full rather than appending duplicates; row counts
  reconcile against the store.
- No secret, token, or credential appears in any generated artifact.

### Web UI surfaces
- Screenshots show the affected views rendering correctly.
- Browser console is free of errors; network log shows no failed requests.

## Cross-cutting checks

- **Effect verification**: an operation that reports success demonstrably had its effect.
- **No secrets** in any output, log, or screenshot.
- **Consistency**: the same information reported by two surfaces agrees.

## Verdicts

- **PASS**: all affected surfaces evidenced and clean.
- **ISSUES FOUND**: numbered issues, each with observed vs expected and exact repro
  steps — these become fix tasks for implementer.
- **REJECT**: an auto-fail trigger fired (see `.claude/agents/qa-evaluator.md`) or the
  evidence shows the feature fundamentally doesn't work.
