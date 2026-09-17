You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-16T16:05-04:00

## Task

Task 01 of the `otel-export-loss-reduction` goal: move
`OTEL_METRIC_EXPORT_INTERVAL` from 60s to 10s across every config source, and correct the
two documented citations of the old value.

**Read `_goals/otel-export-loss-reduction/01-export-interval.md` in full and follow it
exactly.** It holds your requirements (10 items), your 7 acceptance criteria, the files to
read, and the constraints. Nothing here supersedes it.

Context worth having: this is the single largest recoverable slice of a measured coverage
gap. The OTLP exporter keeps datapoints in an in-memory queue with no disk spool, so a
session that exits before its first flush contributes nothing, ever. At 60s a 15-second
session is invisible; at 10s it is not.

## Write fence

```
deploy/managed-settings.json
pilot-package/settings.json
pilot-package/install.sh
client-package/configure.py
deploy/README.md
README.md
```

Nothing else. In particular **not** `deploy/dev-selftest.sh` (its 5s value is deliberate
and its "(default 60s)" comment refers to Claude Code's own default, which is unchanged —
we override it), and not anything under `tests/` or `billing/`.

## Model

requested: claude-sonnet-5 · tier: light · rotation: n/a

## Rules

- Keep the value a JSON **string** everywhere it is one today. A bare integer is not the
  same thing to Claude Code's settings loader.
- Do not introduce a shared constant to DRY the four literals. Four greppable values is
  the existing, intentional pattern.
- `client-package/configure.py`'s var-**name** list around line 102-106 enumerates names,
  not values. Leave it alone.
- Do not add a changelog, a migration note, or an env var.
- `README.md` is ground truth per `CLAUDE.md`. Where a sentence's arithmetic was derived
  from 60s, recompute it rather than leaving it stale.
- If any existing test asserts `60000`, that is a genuine finding: **report it, do not edit
  the test.** Tests belong to task 05.
- Climb test-ladder rungs 1-2 only. Do not run the full suite.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Config (4 files)
[One line each.]

## Docs (3 spots: deploy/README.md env row, deploy/README.md troubleshooting row, README.md Network bullet)
[One line each. Say explicitly what you recomputed in the Network bullet.]

## Evidence (verbatim)
a) `grep -rn "OTEL_METRIC_EXPORT_INTERVAL" --include=*.json --include=*.sh --include=*.py .`
b) the corrected deploy/README.md troubleshooting row
c) the corrected README.md Network bullet

## Verification
[`python -m pytest tests/ -q -k "config or settings or configure"` -> result]
[`bash -n pilot-package/install.sh` -> exit code]
[Both JSON files parsed, value + type printed]

## Any pre-existing test asserting the old value
["None" is valid.]

### Footprint
files_read: <N> (~<C> chars)
```
