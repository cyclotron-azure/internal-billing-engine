# Task 01: export interval 60s -> 10s

## Objective

Every config source that provisions a Claude Code client sets
`OTEL_METRIC_EXPORT_INTERVAL` to `10000`, and the two documented citations of the old
value say 10s. When this lands, a session that exits after 15 seconds has flushed at
least one export interval instead of none — the single largest recoverable slice of the
coverage gap, and the only change in this goal that needs no new code.

## Dependencies

- none (deliberately independent of tasks 02-04 so it can ship on its own)

```yaml
# --- task ownership contract ---
writes:
  - deploy/managed-settings.json
  - pilot-package/settings.json
  - pilot-package/install.sh
  - client-package/configure.py
  - deploy/README.md
  - README.md
reads:
  - deploy/dev-selftest.sh          # the 5s precedent; do NOT change it
depends_on: []
owner: implementer
rewrite_semantics: targeted-insertion
eval_depth: light
```

## Requirements (exhaustive — the evaluator verifies every item)

- [ ] `deploy/managed-settings.json` — `"OTEL_METRIC_EXPORT_INTERVAL"` becomes `"10000"`.
      It stays a **string**, matching every other value in that env block; a bare integer
      is not the same thing to Claude Code's settings loader.
- [ ] `pilot-package/settings.json` — same change, same string typing.
- [ ] `pilot-package/install.sh` — same change. This file writes a settings block; keep
      its quoting and indentation byte-consistent with the rest of the heredoc/JSON it
      emits.
- [ ] `client-package/configure.py` — the `"OTEL_METRIC_EXPORT_INTERVAL": "60000"` entry
      in the defaults dict becomes `"10000"`.
- [ ] `client-package/configure.py`'s var-name list (around line 102-106) is **not**
      touched. It enumerates names, not values.
- [ ] `deploy/README.md` — the `OTEL_METRIC_EXPORT_INTERVAL=60000` table row becomes
      `10000`, and its description stops saying "Export once a minute". Replace the
      rationale with the real one: a 10s interval bounds how much usage a session can take
      with it when it exits before a flush. Keep the row's existing table shape and terse
      voice.
- [ ] `deploy/README.md` — the troubleshooting row that currently advises "Lower
      `OTEL_METRIC_EXPORT_INTERVAL` to tighten the window (more traffic)" against a 60s
      window must be re-read and corrected so it does not advise lowering a value that is
      already lowered. State the new window.
- [ ] `README.md` — the Network bullet's "one POST per `OTEL_METRIC_EXPORT_INTERVAL`
      (60s) per active" becomes 10s, and any load arithmetic in that bullet or its
      neighbours that was derived from 60s is recomputed rather than left stale.
- [ ] `deploy/dev-selftest.sh` is **not** modified. Its 5s value is deliberate and its
      inline comment says "(default 60s)" about Claude Code's own default, which is still
      true — Claude Code's default is unchanged; we are overriding it.
- [ ] No other value in any touched file changes. In particular
      `OTEL_METRIC_EXPORT_TIMEOUT` (if present) is untouched — a timeout longer than the
      interval is fine and is not this task's problem.

## Acceptance Criteria

1. `grep -rn "OTEL_METRIC_EXPORT_INTERVAL" --include=*.json --include=*.sh --include=*.py .`
   shows `10000` in all four config sources and `5000` only in `dev-selftest.sh`; no
   config source still carries `60000` — verification: command output
2. `python -c "import json;print(json.load(open('deploy/managed-settings.json'))['env']['OTEL_METRIC_EXPORT_INTERVAL'])"`
   prints `10000` as a string, and the same for `pilot-package/settings.json` (adjust the
   key path to that file's actual shape) — verification: command output
3. `python -c "import ast,sys; ast.parse(open('client-package/configure.py').read())"`
   exits 0, and the defaults dict resolves `OTEL_METRIC_EXPORT_INTERVAL` to `"10000"` —
   verification: command output
4. `bash -n pilot-package/install.sh` exits 0, and the settings block it emits parses as
   JSON with the new value — verification: command output
5. No occurrence of the literal string `60s` or `60000` remains in `deploy/README.md` or
   `README.md` in a sentence that describes the *current* export interval. Historical or
   unrelated uses of `60` (timeouts, retry backoff, minutes-in-an-hour arithmetic) are
   fine and must be left alone — verification: command output
6. `git diff --stat` touches exactly the six files in the write set — verification:
   command output
7. The existing test suite is unchanged and still green; if any test asserts `60000`, it
   is a genuine finding — report it, do not edit the test (tests belong to task 05) —
   verification: unit test

## Files to Read

- `deploy/managed-settings.json` — the fleet-managed source of truth
- `pilot-package/settings.json`, `pilot-package/install.sh` — the pilot pair
- `client-package/configure.py` — the per-developer configurator
- `deploy/README.md` — the env-var table and the troubleshooting table
- `README.md` — the Network bullet
- `deploy/dev-selftest.sh` — read-only precedent for the 5s rate

## Files to Create / Change

- `deploy/managed-settings.json` — interval value
- `pilot-package/settings.json` — interval value
- `pilot-package/install.sh` — interval value
- `client-package/configure.py` — interval value in the defaults dict
- `deploy/README.md` — env-var table row + troubleshooting row
- `README.md` — Network bullet

## Constraints

- Must: keep the value a JSON **string** everywhere it is one today.
- Must: leave `dev-selftest.sh` alone.
- Must NOT: add a new env var, make the interval configurable, or introduce a constant to
  share the value across files — four literal values that a grep can verify is the
  existing pattern and is intentional here.
- Must NOT: touch `billing/`, `tests/`, or `client-package/claude-transcript-usage.py`.
- Must NOT: add a changelog entry or a migration note.

## Verification

- `python -m pytest tests/ -q -k "config or settings or configure"` -> passing
- Capture the `grep -rn "OTEL_METRIC_EXPORT_INTERVAL"` output verbatim in the report.
- Capture the corrected `deploy/README.md` troubleshooting row verbatim.
