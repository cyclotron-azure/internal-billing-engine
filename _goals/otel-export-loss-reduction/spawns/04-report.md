MODEL: claude-sonnet-5
STATUS: completed

## Config (4 files)
- `deploy/managed-settings.json` -- `"OTEL_METRIC_EXPORT_INTERVAL"` changed from `"60000"`
  to `"10000"` (string preserved).
- `pilot-package/settings.json` -- same change, same string typing.
- `pilot-package/install.sh` -- heredoc value changed to `"10000"`, quoting/indentation of
  the emitted JSON block left byte-identical otherwise.
- `client-package/configure.py` -- defaults dict entry changed to `"10000"`; the
  `OWNED_ENV_KEYS` var-name list at lines 101-113 left untouched (only enumerates names).

## Docs (3 spots)
- `deploy/README.md` env-var table row -- value now `10000`, "Export once a minute"
  replaced with the real rationale (bounds usage a session can take with it before its
  first flush).
- `deploy/README.md` troubleshooting row -- no longer advises lowering an already-lowered
  value; now states the window is 10s and that a small split at that window is expected,
  not something to tighten further.
- `README.md` Network bullet -- `(60s)` -> `(10s)`. Recomputed: the neighbouring sentence
  "so give it a minute before checking" was arithmetic derived from the 60s interval;
  changed to "so give it a few seconds before checking" (README.md line 88). No other
  numeric load arithmetic exists in that bullet or its neighbours to recompute.

## Evidence (verbatim)

a) `grep -rn "OTEL_METRIC_EXPORT_INTERVAL" --include=*.json --include=*.sh --include=*.py .`
```
./client-package/configure.py:106:    "OTEL_METRIC_EXPORT_INTERVAL",
./client-package/configure.py:377:        "OTEL_METRIC_EXPORT_INTERVAL": "10000",
./deploy/dev-selftest.sh:24:export OTEL_METRIC_EXPORT_INTERVAL=5000        # 5s, so records show up fast (default 60s)
./deploy/managed-settings.json:7:    "OTEL_METRIC_EXPORT_INTERVAL": "10000",
./pilot-package/install.sh:57:    "OTEL_METRIC_EXPORT_INTERVAL": "10000",
./pilot-package/settings.json:8:    "OTEL_METRIC_EXPORT_INTERVAL": "10000",
```

b) corrected `deploy/README.md` troubleshooting row (line 255):
```
| Multi-repo session split looks wrong by a small amount | A repo switch inside one 10s export interval lands wholly on one side | Expected at the current window; a false split this small is not worth further tightening (more traffic) |
```

c) corrected `README.md` Network bullet (line 393):
```
- **Network** -- one POST per `OTEL_METRIC_EXPORT_INTERVAL` (10s) per active
```

## Verification
- `python -m pytest tests/ -q -k "config or settings or configure"` -> `32 passed,
  299 deselected` (rungs 1-2 only; full suite not run per instructions)
- `bash -n pilot-package/install.sh` -> exit 0
- Both JSON files parsed and printed: `deploy/managed-settings.json` -> `10000 <class
  'str'>`; `pilot-package/settings.json` -> `10000 <class 'str'>`. Also parsed
  `client-package/configure.py` via `ast` and confirmed the defaults dict resolves the key
  to `'10000'` (string). Simulated `install.sh`'s heredoc output separately and confirmed
  it parses as JSON with `"10000"` as a string.
- `grep -n "60000\|60s" README.md deploy/README.md` -> no matches.
- `git diff --stat` -> touches exactly the 6 write-fence files. Note: it also shows
  `_goals/reconcile-coverage-diagnostics/orchestration-log.md`, which was already modified
  in the working tree before this task started (pre-existing git status) -- not touched by
  this implementer.

## Any pre-existing test asserting the old value
None -- `grep -rn "60000" tests/` found no matches.

### Footprint
files_read: 7 (~52000 chars) / commands_run: 6
