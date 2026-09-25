# Task 00: Test scaffold + pre-change isolation baseline

## Objective

Shared test fixtures exist for the Cowork ingestion pipeline, AND the current, unmodified
behavior of the `claude_code` pipeline is captured as a golden baseline before any file in
this goal is written. This goal's central constraint is that the existing pipeline must not
change in any way — that claim is only provable if "before" is captured now, from
unmodified code, and compared again at the end (task 05).

## Dependencies

- none. **This task runs FIRST, before any production file in this goal is touched.**

```yaml
# --- task ownership contract ---
writes:
  - tests/conftest.py
  - tests/test_conftest.py
  - tests/golden/cowork_isolation_baseline.txt
  - tests/golden/cowork_isolation_README.md
reads:
  - billing/otel/otel_store.py
  - billing/otel/receiver.py
  - billing/otel/bill.py
  - billing/reconcile.py
depends_on: []
owner: test-writer
rewrite_semantics: targeted-insertion
eval_depth: full   # reason: this task's baseline is the sole evidence for the goal's
                    # central isolation claim (Success Criteria); a defect here (e.g. the
                    # wall-clock/shared-store traps found in Phase 3 review) silently
                    # invalidates task 05's replay without either task failing loudly.
```

**`tests/conftest.py` and `tests/test_conftest.py` already exist in this repo** (prior goals
built real fixtures here, including `seed_otlp_rows`/`seeded_otlp_db_path`, and
`tests/test_bill.py:82` already has its own `bill.py` golden byte-match). `rewrite_semantics`
is `targeted-insertion` for exactly this reason: this task ADDS to both files — new fixtures
for the Cowork payload and the read-only existing-`otel.db` fixture, and tests for those new
fixtures in `test_conftest.py` — and must not remove or restructure anything already there.
Read both files fully before writing a single line.

## Requirements (exhaustive — the evaluator verifies every item)

- [ ] Read the existing `tests/conftest.py` and `tests/test_conftest.py` in full before
      writing anything. Reuse existing fixtures (e.g. `seed_otlp_rows`/`seeded_otlp_db_path`)
      rather than building a parallel, near-duplicate one — add only what's genuinely new:
      the Cowork payload fixture and, if the existing fixtures don't already provide one, a
      `session_repo_timeline`-seeded variant.
- [ ] A fixture returning a temporary path for the new, separate Cowork database (e.g. under
      `tmp_path`) — distinct from any existing `otel.db` fixture. No fixture may touch
      `data/otel.db` or `data/cowork.db` on the real filesystem.
- [ ] A read-only-lookup fixture: a small, deterministic `otel.db`-shaped database (built via
      the real, unmodified `otel_store.py` schema/insert path — reuse the existing seeding
      fixture rather than hand-rolling `INSERT` statements) with at least one
      `session_repo_timeline` row and a matching `token_usage`/`cost_usage` row for the SAME
      `session_id`. This is the database later tasks open **read-only** to resolve Cowork repo
      attribution, and it doubles as the fixture the isolation baseline below is captured
      against.
- [ ] A fixture building a synthetic Cowork-shaped OTLP/JSON payload (an
      `ExportMetricsServiceRequest`-style dict, same wire shape `receiver.py` already parses)
      with `resource.attributes` including `service.name="cowork"`,
      `terminal.type="non_interactive"`, a `session.id` (use one matching the timeline fixture
      above, so downstream attribution tests have something to resolve), `user.email`, and
      datapoints for both `claude_code.token.usage` and `claude_code.cost.usage`. Parameterize
      it so a test can swap in `service.name="claude-code"` (the CLI's real, hyphenated value —
      see `billing/otel/sample_payload.py`), an absent `service.name`, or an unrecognized
      metric name.
- [ ] `tests/golden/cowork_isolation_baseline.txt` captures, verbatim, the CURRENT, pre-goal
      behavior of three things. Follow `tests/golden/README.md`'s established pattern exactly
      (it documents this repo's own prior golden-baseline goal and its hard-won gotchas — read
      it in full before writing the capture script): invoke `bill.run()`/`reconcile.run()`
      directly via `contextlib.redirect_stdout` (never the bare CLI — `tests/golden/
      README.md`'s own "CLI-equivalence caveat" section explains why the bare
      `python -m billing.otel.bill` form fails on this machine with `UnicodeEncodeError`
      against the `⚠` character on a `cp1252` console), and write the result with
      `open(..., "w", encoding="utf-8", newline="")` — never a plain `open(f, "w")`, which
      reintroduces CRLF on Windows and corrupts a byte-for-byte comparison.
      1. `billing.otel.bill.run()`'s stdout, at a pinned/deterministic markup, against the
         fixture `otel.db` built above.
      2. `billing/reconcile.py`'s output with `AnalyticsClient` mocked/monkeypatched to return
         a fixed, deterministic response — this baseline must never make a live network call.
      3. `receiver.py`'s `ingest_metrics_payload(...)` result (the returned dict, not stdout)
         for THREE payloads built from the Cowork fixture above: one with
         `service.name="claude-code"`, one with `service.name` absent, and — this is the
         important one — one with `service.name="cowork"`. Capture and record plainly that the
         existing receiver has no `service.name` filter today and stores the `"cowork"`
         payload's datapoints exactly as if they were ordinary `claude_code` usage. This is not
         a bug this goal fixes; it is the existing, unmodified behavior task 05 must prove
         stays unmodified.
      **Two determinism traps found in Phase 3 review, both must be closed:**
      - `OtelStore.insert_datapoint`/`insert_cost_datapoint` call `_ensure_dedupe_epoch()`,
        which writes the WALL-CLOCK value of `otel_store._now()` into the store's `meta` table
        the first time either is called — and `reconcile.py` prints that value. Freeze it:
        `monkeypatch.setattr(otel_store, "_now", lambda: "<fixed literal>")` for every capture
        in this task (bill, reconcile, AND all three ingest captures), not merely for the
        reconcile one — this is the actual, sole reason two runs of the same capture can differ.
      - Each of the three `ingest_metrics_payload` captures (item 3 above) MUST run against
        its OWN fresh, empty `OtelStore` — never against the shared bill/reconcile fixture, and
        never against each other's store. `token_usage`/`cost_usage`'s `dp_key` does NOT
        include `service.name` (verified in Phase 3 review by reading `otel_store.py`'s
        `dp_key` composition), so running the `"cowork"`-tagged payload against a store that
        already holds the `"claude-code"` payload's rows produces `inserted: 0, duplicate: N`
        — silently hiding the exact leak this capture exists to record, because the dedupe key
        can't tell the two payloads apart. Capture order does not matter once stores are
        separate, but each of the three MUST show `token_inserted > 0`/`cost_inserted > 0` (not
        `duplicate`), or the capture is worthless and must fail loudly rather than be recorded.
      No other wall-clock dependence; every value pinned or seeded.
- [ ] `tests/golden/cowork_isolation_README.md` mirrors `tests/golden/README.md`'s structure
      (What this is / File encoding — LF-only / How it was captured / Determinism / When it is
      legitimate to regenerate), stating what the baseline proves (that the existing pipeline's
      behavior — INCLUDING its lack of a `service.name` filter — is unchanged by this goal),
      the exact `_now()`-freezing + fresh-store-per-capture rules above, the exact
      calls used to capture it, that files are LF-only / written with `newline=""` and must be
      compared the same way, and that it must be regenerated ONLY if a future,
      explicitly-approved goal intentionally changes the `claude_code` pipeline — never as a
      side effect of this goal.
- [ ] Add a line pinning `tests/golden/cowork_isolation_baseline.txt` (and
      `cowork_isolation_README.md` if it also must stay LF-only) `-text` in `.gitattributes`,
      mirroring the existing `tests/golden/** -text` rule if one already covers this path —
      check first; if the existing rule already covers `tests/golden/**`, no new line is
      needed and this item is satisfied by inspection, state so in the report.
- [ ] No production file under `billing/` is modified. This task's write fence is tests only.
- [ ] No dependency beyond `pytest`. This project uses `uv`, not `pip` — `uv pip install pytest`
      if it's ever missing; do not invoke `pip` directly.

## Acceptance Criteria

1. `python -m pytest tests/ -q` runs and collects successfully with zero failures —
   verification: command output.
2. The existing-`otel.db` fixture's schema matches `otel_store.py`'s real `SCHEMA` exactly
   (built by importing/executing it, not hand-copied) — verification: unit test comparing
   `PRAGMA table_info` output against what a fresh `OtelStore` produces.
3. The synthetic Cowork payload fixture, run through `receiver.py`'s own `_attrs`/
   `_datapoints` helpers, produces EXACTLY these values: `_attrs(resource.attributes) ==
   {"service.name": "cowork", "terminal.type": "non_interactive", "session.id": <the fixture's
   literal session id>, "user.email": <the fixture's literal email>}` (or a superset with no
   other keys asserted, if the fixture legitimately carries more), and the token/cost
   datapoints' `asInt`/`asDouble` values equal the exact literals the fixture was built with —
   proving it is a realistic, correctly-shaped OTLP payload, not merely that parsing didn't
   crash — verification: unit test asserting these exact values, not "is not None"/"is
   truthy".
4. `tests/golden/cowork_isolation_baseline.txt` is non-empty, LF-only (no `\r\n`), and contains
   all three captured pieces (bill.py output, mocked-reconcile output, and the three
   `ingest_metrics_payload` results — including the one showing the existing receiver accepts
   a `"cowork"`-tagged payload as ordinary usage) — verification: command output showing the
   captured file's contents and a byte-level check for `\r\n`.
5. Re-running the entire baseline-capture script twice, in two separate temp directories (two
   separate fresh `otel.db` builds from the same fixture, `otel_store._now` frozen the same
   way both times), produces byte-identical output — verification: run twice, diff, no
   differences. A capture that is only deterministic when run once in the same process (e.g.
   because a module-level cache survives between the two calls) does not satisfy this.
6. Each of the three `ingest_metrics_payload` captures shows BOTH `token_inserted > 0` AND
   `cost_inserted > 0` (never any `duplicate > 0` for a fresh store) — verification: read the
   captured values directly; a capture showing all-duplicate, or a zero on either count, is a
   fixture bug, not a valid baseline.

## Files to Read

- `billing/otel/otel_store.py` — the current, real `SCHEMA` to build the fixture db from.
- `billing/otel/receiver.py` — `_attrs`/`_attr_value`/`_datapoints`/`_common`, and
  `ingest_metrics_payload`'s OTLP/JSON shape, so the synthetic Cowork payload fixture is
  wire-realistic. Read-only — nothing here is ever modified by this goal.
- `billing/otel/bill.py` — how to invoke it and what its output looks like, for the baseline.
- `billing/reconcile.py` — confirm it is unaffected by this goal (it queries `otel_store`/
  Analytics data directly; a new, separate Cowork db cannot appear in its output regardless,
  but the baseline should demonstrate that rather than assert it).
- `tests/conftest.py` and `tests/test_conftest.py` — existing fixtures/tests to extend, not
  duplicate.
- `tests/golden/README.md` and `tests/golden/bill_otlp_baseline.txt` — the EXACT precedent for
  this task's golden capture: the `_now()`-freezing idea generalizes from that goal's own
  determinism write-up, the `redirect_stdout`/`newline=""` invocation pattern, and the
  CLI-equivalence caveat about `cp1252`/`⚠` are all to be followed verbatim, not reinvented.
- `.gitattributes` — check whether `tests/golden/** -text` already covers the new files.
- `.claude/skills/test-ladder/SKILL.md` — convention map and rung rules.
- `.claude/agents/test-writer.md` — mocking boundaries and dependency budget.

## Files to Create / Change

- `tests/conftest.py` — shared fixtures: tmp Cowork-db path, existing-otel.db fixture,
  synthetic Cowork OTLP payload fixture.
- `tests/test_conftest.py` — tests for the new fixtures added above.
- `tests/golden/cowork_isolation_baseline.txt` — captured pre-change pipeline output.
- `tests/golden/cowork_isolation_README.md` — what the baseline is, and when it may change.

## Constraints

- Must: run before any production file in this goal is written; capture the baseline from
  unmodified code.
- Must: keep fixtures deterministic and isolated to `tmp_path`.
- Must NOT: modify any file under `billing/`, `deploy/`, or `client-package/` — tests only.
- Must NOT: add any dependency beyond `pytest`.

## Verification

- Targeted test command: `python -m pytest tests/ -q`
- Baseline determinism: capture twice and diff.
