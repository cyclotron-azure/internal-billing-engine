# internal-billing-engine

## Orchestration
Feature work runs through the orchestrator/worker/evaluator system — see
[.claude/ORCHESTRATION.md](.claude/ORCHESTRATION.md). Start features with /feature.

## Hard constraints
- **Runtime is standard-library only.** No third-party import may enter `billing/`.
  `pytest` under `tests/` is the single permitted dev dependency.
- **SQLite is single-host, single-connection.** One receiver process, one host, one
  persistent disk. No threading the receiver, no connection pool, no autoscale.
- **Repo attribution is resolved at query time**, never persisted — a late or corrected
  session→repo timeline must retroactively fix past bills.
- **Never commit a secret.** `RECEIVER_AUTH_TOKEN`, `ANTHROPIC_ANALYTICS_TOKEN`, the
  fleet billing token, and every `AZURE_*`/`ADLS_*` value live in `.env` only.
- `README.md` is ground truth. When code and README disagree, correct the README.
## Orchestration
Feature work runs through the orchestrator/worker/evaluator system — see
.claude/ORCHESTRATION.md. Start features with /feature.
<!-- orchestration-kit:pointer -->
