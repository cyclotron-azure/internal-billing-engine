# Golden baseline: `cowork_isolation_baseline.txt`

## What this is

`cowork_isolation_baseline.txt` is captured output from three pieces of the **CURRENT,
unmodified** `claude_code` pipeline, captured by task 00 of the `cowork-telemetry-ingest`
goal **before any production file in that goal was touched**:

1. `billing.otel.bill.run()`'s stdout, against a fixture `otel.db` (the
   seeded-OTLP-rows fixture — `tests/conftest.py`'s `seed_otlp_rows()` /
   `seeded_otlp_db_path`).
2. `billing/reconcile.py`'s `run()` stdout, against the SAME fixture db, with
   `AnalyticsClient` mocked/monkeypatched to a fixed, deterministic stand-in that never
   makes a live network call.
3. `billing.otel.receiver.ingest_metrics_payload(...)`'s returned dict (not stdout) for
   THREE synthetic Cowork-shaped payloads — one with `service.name="claude-code"`
   (the CLI's real, hyphenated value), one with `service.name` absent entirely, and one
   with `service.name="cowork"`.

It answers one question for the rest of that goal: *does adding a brand-new, wholly
separate Cowork ingestion pipeline change ANY of the existing `claude_code` pipeline's
behavior, at all?* It must not, per the goal's own hard isolation constraint ("No file,
table, schema, process, or behavior belonging to the existing pipeline may change in any
way").

Piece 3 is the important one: it deliberately proves and records that the **existing**
`receiver.py` has **no `service.name` filter today**, and stores a `"cowork"`-tagged
payload's datapoints exactly as if they were ordinary `claude_code` usage. This is **not**
a bug this goal fixes — the goal explicitly leaves `receiver.py` untouched — it is the
existing, unmodified behavior task 05 (this goal's integration/closer task) must prove
stays unmodified. All three `service.name` variants below show identical
`{"token_inserted": 2, "cost_inserted": 1, "duplicate": 0}` results, which is exactly the
point: the existing receiver cannot and does not tell them apart.

It encodes **PRE-goal behavior only**. It is not a spec for what any of these three should
do — it is a snapshot of what they did, on fixed, synthetic data, at the moment this task
ran.

## File encoding — LF-only, never newline-translated

**`cowork_isolation_baseline.txt` is LF-only** (verified: no `\r\n` sequences, checked
byte-for-byte). It must stay that way, and any comparison against it must be
newline-safe, for two reasons — both required, either alone leaves a sharp edge:

1. **`.gitattributes` already pins `tests/golden/** -text`** (added by the
   `desktop-usage-capture` goal's own task 00 for `bill_otlp_baseline.txt` — verified by
   inspection before this file was added; no new line is needed here, since the existing
   glob already covers this path). Without that pin, `git` would apply this repo's
   `core.autocrlf=true` on checkout and a Windows clone would get a CRLF-corrupted file.
2. **Any future replay comparison must itself normalize newlines** — read both sides as
   bytes and normalize, or open with `newline=""` (universal-newlines translation OFF) —
   rather than assuming the checked-out file's line endings match whatever the comparison
   process produces. Even with the `.gitattributes` pin in place, a byte-for-byte
   comparison written without `newline=""` will still reintroduce CRLF on the *write* side
   on Windows and fail for a reason that has nothing to do with the pipeline.

Do not "fix" a future diff failure by regenerating this file with different line
endings — regenerating changes the bytes this baseline exists to freeze. Fix the
comparison or the `.gitattributes` pin instead.

## How it was captured

- Fixture (pieces 1 and 2): the **seeded-OTLP-rows fixture** — `tests/conftest.py`'s
  `seed_otlp_rows()` — built fresh into its own `otel.db`-shaped SQLite file via the real,
  unmodified `OtelStore`/`SCHEMA` insert path. Same fixture `tests/golden/
  bill_otlp_baseline.txt` (the `desktop-usage-capture` goal's own precedent) is built
  from, and for the identical reason: it is migrated normally by the real schema/insert
  path, so it stays a valid comparison target even if a later, unrelated goal alters
  `otel_store.py`'s schema.
- Fixture (piece 3): the synthetic Cowork OTLP/JSON payload —
  `tests/conftest.py`'s `build_cowork_metrics_payload()` — with `service_name` swapped
  across the three required values (`"claude-code"`, `None`, `"cowork"`). Every id,
  timestamp, and token/cost amount in it is a fixed literal — no wall-clock, no random
  ids.
- Invocation: produced by `tests/conftest.py`'s own `capture_cowork_isolation_baseline()`
  (exposed at module level, not only inside a test, so a later task — 05 — can import and
  re-run the identical capture for its replay comparison without duplicating this logic):

  ```python
  import contextlib, io
  from pathlib import Path

  import pytest

  from tests.conftest import capture_cowork_isolation_baseline

  monkeypatch = pytest.MonkeyPatch()
  try:
      text = capture_cowork_isolation_baseline(Path(some_fresh_tmp_dir), monkeypatch)
  finally:
      monkeypatch.undo()

  # Write LF-only, byte-exact -- newline="" disables universal-newlines
  # translation, which on Windows would otherwise turn every "\n" the
  # captured pieces print into "\r\n" and silently corrupt the LF-only
  # guarantee above.
  with open("tests/golden/cowork_isolation_baseline.txt", "w",
            encoding="utf-8", newline="") as f:
      f.write(text)
  ```

  Internally, `capture_cowork_isolation_baseline()` does exactly what
  `tests/golden/README.md`'s own precedent does for pieces 1 and 2 — calls
  `bill.run()` / `reconcile.run()` directly via `contextlib.redirect_stdout`, never the
  bare CLI — and for piece 3 calls `receiver.ingest_metrics_payload(payload, store)`
  directly and records its **returned dict** (JSON-dumped with `sort_keys=True` for a
  deterministic key order), since that endpoint has no stdout output of its own.

  **CLI-equivalence caveat, inherited verbatim from `tests/golden/README.md`:** printing
  this capture's text at an interactive Windows console fails with `UnicodeEncodeError`
  against the `⚠` character piece 1 prints (`sys.stdout.encoding` defaults to the console
  codepage, measured `cp1252` on this machine) — this was reproduced while generating this
  very file. The capture script must write directly to the file (as above), or force
  `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8` before printing anything to a console.

- **Two determinism traps closed, both found in Phase 3 review of this goal:**
  1. `OtelStore.insert_datapoint` / `insert_cost_datapoint` call `_ensure_dedupe_epoch()`,
     which writes the WALL-CLOCK value of `otel_store._now()` into the store's `meta`
     table the first time either is called — and `reconcile.py`'s `DEDUPE DROPS` section
     prints that value. `capture_cowork_isolation_baseline()` freezes
     `otel_store._now` via `monkeypatch.setattr(otel_store, "_now", lambda: "2026-01-01T00:00:00Z")`
     for the **entire** capture — piece 1, piece 2, AND all three piece-3 captures — not
     merely for the reconcile call. This is the actual, sole reason two runs of the same
     capture could otherwise differ.
  2. Each of the three `ingest_metrics_payload` captures (piece 3) runs against its **OWN
     fresh, empty `OtelStore`** — never against the shared bill/reconcile fixture db, and
     never against each other's store. `token_usage`/`cost_usage`'s `dp_key` does **not**
     include `service.name`, so running the `"cowork"`-tagged payload against a store that
     already held the `"claude-code"`-tagged payload's rows would produce
     `inserted: 0, duplicate: N` for it — silently hiding the exact leak piece 3 exists to
     record, because the dedupe key can't tell the two payloads apart. With separate
     stores, all three captures show `token_inserted: 2, cost_inserted: 1, duplicate: 0`
     — a genuine insert, never a duplicate. `capture_cowork_isolation_baseline()` asserts
     this loudly (raises rather than silently recording a worthless capture) before
     formatting each piece-3 result.
- No other wall-clock dependence; every value pinned or seeded. `reconcile.run()`'s
  Analytics "truth" side is all zeros (the mocked `AnalyticsClient.usage_report` yields no
  rows), which is why the funnel prints `0` for `analytics(truth)` and a negative "gap" —
  that is the expected, deterministic shape of a fully-mocked truth side, not a defect.

## Determinism

Two guarantees are checked, by two different tests in `tests/test_conftest.py`, and they
cover different failure modes:

- **Same-process determinism**: `test_golden_baseline_capture_is_deterministic_across_two_fresh_runs`
  captures twice, back to back, in two separate temporary directories (two separate fresh
  database builds from the same fixtures, `otel_store._now` frozen the same way both
  times), within a single interpreter process, and asserts the two captures are
  byte-identical by direct string comparison. This runs on every test run, but because
  both captures share a process, it cannot by itself catch drift that only shows up across
  process boundaries (import order, hash-seed effects, etc.).
- **Cross-process / cross-run determinism**: `test_golden_baseline_capture_matches_the_committed_file`
  regenerates the capture in its own fresh call and diffs it against
  `cowork_isolation_baseline.txt` as committed to the repo — i.e. against a capture from a
  genuinely separate prior run. This is what actually guards against drift between runs,
  machines, or process invocations.

A non-deterministic baseline would be **worse than no baseline at all** — it would fail this
goal's later replay checks for reasons unrelated to any code change, so every value that
could vary (timestamps, ids, model names, markup, basis, the mocked Analytics response) is
pinned in the fixtures rather than left to wall-clock time or default arguments.

## When it is legitimate to regenerate this file

Regenerating `cowork_isolation_baseline.txt` is legitimate **ONLY** when the change is to
`bill.py`'s, `reconcile.py`'s, or `receiver.py`'s output/behavior **on purpose, by design,
and with explicit sign-off that the goal's isolation constraint no longer applies** — none
of which this goal (`cowork-telemetry-ingest`) is permitted to do, per its own hard
constraint that the existing pipeline changes in no way. In practice, for the lifetime of
this goal, this file should never need to be regenerated at all.

It is **never** legitimate to regenerate this file merely because a later task's change
(e.g. task 05's integration work) makes the old capture fail to replay. That failure is the
signal this baseline exists to produce: the `claude_code` pipeline's behavior must be
completely unaffected by adding the new, separate Cowork pipeline. If a later task's change
makes this replay differ, the fix is to correct that change so the existing pipeline is
unaffected, not to regenerate this file to match the regression.

To regenerate for a legitimate, explicitly-approved reason: rebuild both fixtures from
`tests/conftest.py` (`seed_otlp_rows()` / `seeded_otlp_db_path` for pieces 1–2,
`build_cowork_metrics_payload()` for piece 3), call
`capture_cowork_isolation_baseline()` twice into two separate fresh directories, confirm
the two captures are byte-identical via direct string comparison, write the result with
`open(..., "w", encoding="utf-8", newline="")` (a plain `open(f, "w").write(...)` on
Windows reintroduces CRLF and violates the LF-only requirement above), and only then
overwrite this file — recording in the same change why the old baseline no longer applies.
