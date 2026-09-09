# Golden baseline: `bill_otlp_baseline.txt`

## What this is

`bill_otlp_baseline.txt` is captured stdout from `billing.otel.bill.run()` **as it
existed before any file in the `desktop-usage-capture` goal was modified** — task 00
of that goal captured it, before task 01 touched `otel_store.py`. It answers one
question at every later stage of that goal: *does adding desktop/transcript capture
change the bill for an OTLP-only store, at all?* It must not, per the goal's own
constraint ("Existing OTLP rows must keep billing exactly as they do today").

It encodes **PRE-change behavior only**. It is not a spec for what `bill.py` should
do — it is a snapshot of what it did, on a fixed, synthetic dataset, at the moment
this task ran.

## File encoding — LF-only, never newline-translated

**`bill_otlp_baseline.txt` is LF-only** (verified: 2000 bytes, zero `\r\n` sequences).
It must stay that way, and any comparison against it must be newline-safe, for two
reasons that are both required — either alone leaves a sharp edge:

1. **`.gitattributes` must pin this file `-text`** (routed to task 06, since
   `.gitattributes` is outside this task's write fence). Without that pin, `git`
   applies this repo's `core.autocrlf=true` on checkout and a Windows clone gets a
   2045-byte CRLF file — corrupting the exact bytes this baseline is supposed to
   freeze, for a reason that has nothing to do with billing.
2. **Task 05's replay comparison must itself normalize newlines** — read both sides
   as bytes and normalize, or open with `newline=""` (universal-newlines translation
   OFF) — rather than assuming the checked-out file's line endings match whatever the
   comparison process produces. Even with the `.gitattributes` pin in place, a
   byte-for-byte comparison written without `newline=""` will still reintroduce CRLF
   on the *write* side on Windows (see the Python snippet below) and fail for the same
   unrelated reason.

Do not "fix" a future diff failure by regenerating this file with different line
endings — regenerating changes the bytes this baseline exists to freeze. Fix the
comparison or the `.gitattributes` pin instead.

## How it was captured

- Fixture: the **seeded-OTLP-rows fixture** — `tests/conftest.py`'s
  `seed_otlp_rows()` / `seeded_otlp_db_path` — built on the **CURRENT** (not the
  frozen legacy) `SCHEMA` in `billing/otel/otel_store.py`. This is deliberate: the
  frozen legacy-schema fixture (`LEGACY_SCHEMA` / `legacy_schema_db_path`) must NOT
  back this baseline. Once task 04 added a `usage_source` branch to `bill.py`'s
  queries, replaying a legacy-schema database would raise
  `OperationalError: no such column: usage_source` instead of comparing output — the
  golden gate would fail for a reason that has nothing to do with billing
  correctness. The seeded-OTLP-rows fixture is migrated normally by task 01's
  `ALTER TABLE`, so it stayed a valid comparison target for the life of the goal.
- Data: three sessions seeded via `OtelStore.insert_datapoint` /
  `insert_cost_datapoint` / `insert_session_repo` — one with a `session_repo_timeline`
  entry (exercises `attribution_source='timeline'`), one with a wrapper-only repo tag
  (`attribution_source='wrapper'`), and one with an empty `repo_raw` / `repo='unknown'`
  (`attribution_source='absent'`). Every id, timestamp, and token/cost amount is a
  fixed literal in `tests/conftest.py` — no wall-clock time, no random ids, no
  environment- or locale-dependent value.
- Invocation: produced by a short generation script that calls this code path
  directly (this is the ACTUAL invocation, not merely an equivalent one — see the
  CLI caveat below):

  ```python
  import contextlib, io

  from billing.otel.otel_store import OtelStore
  from billing.otel import bill

  store = OtelStore(db_path)      # db_path built from the seeded-OTLP-rows fixture
  # ... seed_otlp_rows(store) ...
  store.close()

  buf = io.StringIO()
  with contextlib.redirect_stdout(buf):
      bill.run(db=db_path, markup=1.50, basis="actual")

  # Write LF-only, byte-exact -- newline="" disables universal-newlines
  # translation, which on Windows would otherwise turn every "\n" bill.py
  # prints into "\r\n" and silently corrupt the LF-only guarantee above.
  with open("tests/golden/bill_otlp_baseline.txt", "w", encoding="utf-8", newline="") as f:
      f.write(buf.getvalue())
  ```

  **CLI-equivalence caveat, recorded because it does not hold verbatim on this
  machine:** running `python -m billing.otel.bill --db <seeded_otlp.db> --markup 1.50
  --basis actual` at an interactive Windows console **fails** — `sys.stdout.encoding`
  defaults to the console codepage (measured: `cp1252` on this machine), which cannot
  encode the `⚠` character `bill.py` prints in its multi-repo/unattributed warnings,
  and the process exits 1 with `UnicodeEncodeError` after producing truncated,
  CRLF-translated output instead of this file's 2000 bytes. The CLI form is only
  equivalent to the capture above when BOTH of the following hold, and both must be
  stated together or the command is not reproducible:
  - the process's stdout encoding is forced to UTF-8 — `PYTHONUTF8=1` or
    `PYTHONIOENCODING=utf-8` in the environment — so the `⚠` character encodes; and
  - the output stream is written/redirected without newline translation (e.g.
    redirecting to a file opened or post-processed with `newline=""`, not a plain
    shell `>` redirect on Windows, which still goes through the console's
    text-mode translation and reintroduces CRLF).

  Given both conditions, the CLI form is: `PYTHONUTF8=1 python -m billing.otel.bill
  --db <seeded_otlp.db> --markup 1.50 --basis actual`, with its output captured
  through a newline-safe writer rather than a bare shell redirect.
- Markup is pinned at **1.50** (matches both `bill.py`'s and `RatingService`'s
  default), and `basis` is left to resolve to `"actual"` naturally, since the fixture
  seeds cost rows (`have_cost` is true).
- The first line of the captured basis block reads:

  ```
  basis: ACTUAL cost from claude_code.cost.usage  x1.50 markup
  ```

## Determinism

Captured twice, back to back, in separate temporary databases built from the same
fixture; the two captures were byte-identical (confirmed by direct string comparison,
not just visual inspection). A non-deterministic baseline would be **worse than no
baseline at all** — it would fail this goal's replay checks for reasons unrelated to
any code change, so every value that could vary (timestamps, ids, model names, markup,
basis) is pinned in the fixture rather than left to wall-clock time or default
arguments.

## When it is legitimate to regenerate this file

Regenerating `bill_otlp_baseline.txt` is legitimate ONLY when the change is to
`bill.py`'s OTLP-only output format or content **on purpose and by design** — e.g. a
deliberate, reviewed change to the report's layout, wording, or the fields it prints
for an OTLP-only store — and the new output has itself been re-verified (by hand, and
against the fixture's known-correct totals) to be right, not merely different.

It is **never** legitimate to regenerate this file merely because a later task's
change makes the old capture fail to replay. That failure is the signal this baseline
exists to produce: `bill.py`'s behavior against an OTLP-only store must be unchanged
by adding desktop/transcript capture. If a later task's change makes this replay
differ, the fix is to correct that change so OTLP-only billing is unaffected, not to
regenerate this file to match the regression.

To regenerate for a legitimate reason: rebuild the seeded-OTLP-rows fixture's database
from `tests/conftest.py`'s `seed_otlp_rows()`, run `billing.otel.bill.run()` against it
at `markup=1.50, basis="actual"` with stdout captured via `contextlib.redirect_stdout`
(as in the invocation above — NOT the bare CLI form, per the encoding caveat above),
capture it twice, confirm the two captures are byte-identical via direct string
comparison, write the result with `open(..., "w", encoding="utf-8", newline="")` (a
plain `open(f, "w").write(...)` on Windows reintroduces CRLF and violates the LF-only
requirement above), and only then overwrite this file — recording in the same change
why the old baseline no longer applies.
