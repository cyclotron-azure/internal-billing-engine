# Task 04: tests

> Revised after Phase 3 cycles 1 and 2. Cycle 1: `rewrite_semantics` stated per file; the
> Analytics mocking seam pinned (the previous "monkeypatch `AnalyticsClient`" rule named a
> seam that cannot work); `seed_otlp_rows` corrected to a plain function; commit hashes
> corrected; the COVERAGE_MAP preamble contradiction resolved; tautological
> default-equivalence tests dropped. Cycle 2: the per-file map moved back under the
> canonical `rewrite_semantics:` key, the task-01 criterion range corrected (criterion 15
> is a command, not a unit test), and tests added for the cycle-2 fixes.

## Objective

`tests/test_reconcile.py` and `tests/test_dedupe_counter.py` exist and verify every
acceptance criterion from tasks 01–03, plus regression coverage for the `--email` and
org-wide `run()` paths that ship today with no tests at all. `tests/COVERAGE_MAP.md`
gains a section mapping each criterion to its node id.

## Dependencies

- 01-store-dedupe-counter
- 02-reconcile-aggregation
- 03-reconcile-output

```yaml
# --- task ownership contract ---
writes:
  - tests/test_reconcile.py
  - tests/test_dedupe_counter.py
  - tests/COVERAGE_MAP.md
reads:
  - billing/reconcile.py
  - billing/otel/otel_store.py
  - billing/store.py
  - billing/analytics_client.py
  - tests/conftest.py
  - tests/test_otel_store.py
depends_on:
  - "01-store-dedupe-counter"
  - "02-reconcile-aggregation"
  - "03-reconcile-output"
owner: test-writer
eval_depth: light
rewrite_semantics:                           # per owned path
  tests/test_reconcile.py: whole-file        # new file
  tests/test_dedupe_counter.py: whole-file   # new file
  tests/COVERAGE_MAP.md: targeted-insertion  # existing shared document
```

## Requirements (exhaustive — the evaluator verifies every item)

### The Analytics mocking seam (pinned — read before writing any test)

`billing.reconcile`'s org-wide truth path constructs its own client, and
`AnalyticsClient.__init__` raises `AnalyticsError` when no token is in the environment.
Consequences you must design around:

- Patching `AnalyticsClient.usage_report` **alone never reaches it** — the constructor
  raises first.
- A test that merely asserts `AnalyticsError` is raised **passes whether or not the code
  under test is correct**, because the constructor raises on its own.
- On a host that *does* have a token in `.env` (`config.load_env()` runs at import), an
  unpatched path reaches the **live Analytics API**.

Use exactly one of these two seams, and say which in a comment on each test:

- **Seam A (function-level)** — `monkeypatch.setattr` on the module-level
  `billing.reconcile.analytics_claude_code_daily` (and `analytics_claude_code_totals`
  where relevant). Use for every output/behavior test.
- **Seam B (client-level)** — `monkeypatch.setenv("ANTHROPIC_ANALYTICS_TOKEN",
  "test-token")` **plus** `monkeypatch.setattr(AnalyticsClient, "usage_report", fake)`.
  Required whenever the assertion is about the client itself: call counts, eager
  evaluation, or the origin of a raise. **The `setenv` is mandatory.**

- [ ] No test makes a live network call under either seam.
- [ ] The `AnalyticsError` test uses Seam B with a fake token set, so the raise provably
      originates in `usage_report` and not in construction.

### Hard rules for every test in both files

- [ ] **Every `run()` call passes an explicit `db=<tmp_path fixture>`, without
      exception.** `run()` with no `db=` opens `OtelStore()`'s real default
      `./data/otel.db` and creates the file and schema on first use — that writes into the
      repo's live data directory during a test run. The same applies to `analytics_db=`:
      never pass an OTEL path as `analytics_db` or an analytics path as `db`.
- [ ] No test depends on execution order or another test's fixture state.
- [ ] Use `tmp_path` for every database. Never read or write `data/otel.db` or
      `data/analytics.db`.
- [ ] Reuse `tests/conftest.py`'s helpers where they fit: the `tmp_db_path`,
      `legacy_schema_db_path`, and `seeded_otlp_db_path` **fixtures**, and
      `seed_otlp_rows`, which is a plain module-level **function**, not a fixture — call
      it, do not request it as a test argument. If nothing fits, define a **local**
      fixture in the test file; do **not** edit `tests/conftest.py` (outside this fence).

### `tests/test_dedupe_counter.py` — task 01's criteria

- [ ] One test per acceptance criterion **1–14** in `01-store-dedupe-counter.md`.
      Criterion 15 is a command-output criterion (`pytest tests/test_otel_store.py -q`
      exits 0), not a unit test — do not write a test for it and do not list it as a GAP.
- [ ] Criterion 7 is the load-bearing one: a store opened and migrated but never inserted
      into must have `dedupe_epoch() is None`. An implementation that writes the epoch
      from `_migrate()` must fail this test — write it so it would.
- [ ] Criteria 8–9: the epoch is set by the first insert attempt (successful *or*
      duplicate-only), is an ISO8601 timestamp, and is unchanged by later inserts across
      a reopen.
- [ ] Criterion 10 asserts the latch: insert once, `commit()`, then ten more inserts on the
      same instance issue **exactly one** `meta` lookup — the first, which finds the key and
      closes the latch. Do not assert zero; the flag is only set by a `SELECT` that found
      the key, so one lookup after the commit is correct behavior. Count by wrapping
      `db.execute`, not by inspecting internals you would have to guess at.
      Criterion 11 asserts recovery: insert,
      `rollback()`, assert `dedupe_epoch()` is `None`, insert again on the *same* store
      instance, `commit()`, assert the epoch is now set. Criterion 11 is the one that
      fails a latch-on-attempt implementation — write it so it would.
- [ ] Criteria 13–14: force `sqlite3.Error` on the **counter statement only** and on the
      **epoch write only** — not on the main insert — so each proves its guard rather
      than merely that errors propagate. Monkeypatch narrowly.
- [ ] Assert the increment adds **no** statement on the success path, by comparing
      `db.execute` call counts across a clean insert versus a duplicate insert — taken
      **after** the epoch is committed and the latch has closed, so the comparison
      isolates the counter rather than the epoch check. This is the constraint that keeps
      the receiver's serial hot path unaffected.

### Testability traps in task 01's shipped implementation (READ BEFORE WRITING)

Task 01 is implemented and PASSED evaluation 5/5 with all 15 criteria verified by direct
observation. The evaluator found three places where the **naive** test fails against the
**correct** implementation. Write around them; do not "fix" the code, which is out of
your fence and is right.

- [ ] **A failing counter `UPDATE` leaves a `drops = 0` residue row.** `_record_dedupe_drop`
      does `INSERT OR IGNORE` then `UPDATE`; if the `UPDATE` raises, the bucket row
      persists with `drops = 0`. This is benign — both public read methods filter falsy
      `drops`, so the row is invisible and the next real drop increments `0 → 1` correctly.
      Criterion 13's test must therefore assert `insert_datapoint(...) is False` and/or
      `dedupe_drops(...) == {}` **through the public methods**. Do **not** assert
      `SELECT COUNT(*) FROM dedupe_drops == 0` — that fails on correct code.
- [ ] **`last_seen` is second-granular.** It comes from the module's `_now()`
      (`%Y-%m-%dT%H:%M:%SZ`), as the task mandates. Three back-to-back duplicate inserts
      land in the same wall-clock second, so `last_seen == first_seen`. Criterion 3's test
      must `monkeypatch` `billing.otel.otel_store._now` to return controlled increasing
      values around the third insert (preferred — deterministic), or sleep > 1s (slow and
      flaky). A bare `assert row["last_seen"] > row["first_seen"]` fails on correct code.
- [ ] **`dedupe_epoch()` issues its own `SELECT ... FROM meta`.** The insert path issues
      exactly one such statement (verified), but criterion 10's counting test will see more
      than one if it calls `dedupe_epoch()` inside the counted window. Either do not call
      `dedupe_epoch()` between the `commit()` and the tenth insert, or match on the exact
      insert-path SQL `SELECT 1 FROM meta WHERE key=?` rather than on `FROM meta`.

### The shipped task-01 interface (build against this, not against the task file's prose)

Confirmed by the evaluator against the code, with no behavioral drift from task 01's spec:

```python
DEDUPE_EPOCH_META_KEY = "dedupe_counting_since"   # meta.value is UTC ISO8601 "%Y-%m-%dT%H:%M:%SZ"
OtelStore.dedupe_drops(start, end) -> dict          # {token_type: drops}, absent == no drops
OtelStore.dedupe_drops_by_day(start, end) -> dict   # {YYYY-MM-DD: {token_type: drops}}
OtelStore.dedupe_epoch() -> str | None              # None == counting has never run
```

Both read methods use a half-open `[start, end)` window, matching `reconcile.otel_totals`.
The epoch's latch is private (`self._dedupe_epoch_confirmed`) and `dedupe_epoch()`
deliberately ignores it, so a freshly opened store always reads committed truth.

### `tests/test_reconcile.py` — tasks 02 and 03 criteria

- [ ] One test per acceptance criterion in `02-reconcile-aggregation.md` (1–16) and
      `03-reconcile-output.md` (1–16, including 7b and 7c).
- [ ] Criterion 02.16 and criteria 03.7b/03.7c cover the cycle-2 fix: a real drop count
      must be **printed** under measurement states 1, 2 and 3, not suppressed. Seed both
      reachable routes — drops dated before an epoch that starts after the window (the
      replayed-export route) and drops with the epoch meta key absent entirely (the
      interrupted-write route) — and assert both the exact count and the qualifier
      wording appear together.
- [ ] Criterion 02.4's fixture must include `otlp` + `transcript` rows, at least two
      `query_source` values, **one row with NULL `query_source`**, and at least two
      `entrypoint` values — and assert all four `captured_total` equalities.
- [ ] Criteria 02.6 and 02.7 are the Σdaily == period invariants. Write all three
      identities (captured, tagged, and both truth sides). These are the tests that catch
      a day-key mismatch, so do not collapse them into one weaker assertion.
- [ ] Criterion 02.8 pins the day-key literal: a fake `usage_report` yielding
      `"2026-07-14T00:00:00Z"` must produce the key `"2026-07-14"`, and that key must
      compare equal to `otel_daily`'s key for the same day. Seam B.
- [ ] Criterion 02.9's single-pass test uses a **call-counting fake**, not a mock library,
      and asserts the count is exactly 1. Seam B.
- [ ] Criterion 02.13 covers all five epoch placements (`None`, `>= end`, `< start`,
      `== start`, `start < epoch_day < end`).
- [ ] Criterion 02.14 is the query-time-attribution invariant: seed a `token_usage` row
      whose raw `repo` is `unknown` plus a later-arriving `session_repo_timeline` entry
      that resolves it, and assert `tagged` reflects the resolved repo. A regression here
      silently mis-bills clients.
- [ ] Output assertions must pin **specific strings and computed values** — section
      headers, the epoch timestamp, exact comma-formatted integers, specific coverage
      percentages for a known fixture, the literal `100.00%` per surface sub-block. Never
      a "looks similar" or substring-of-anything check. Criterion 03.2 requires literal
      expected lines including whitespace.
- [ ] Criterion 03.5 must assert the four `DEDUPE DROPS` outputs are **pairwise
      different**, not merely that each contains some phrase.
- [ ] Criterion 03.16 automates the width check: collect every line consisting solely of
      `=` or `-`, assert they are all equal length, and assert no output line is longer.
- [ ] Do **not** write byte-identical-stdout tests for declared defaults
      (`run(s,e,db=p)` vs `run(s,e,db=p,by_surface=False,daily=False)`, or `emails=None`
      vs omitting it). Both sides pass identical arguments to a deterministic function, so
      the test is tautological. Removed from the plan in cycle 1.

### Regression coverage for today's untested behavior

`tests/test_reconcile.py` does not exist today: the `email-filtered-reconciliation` goal
planned it, stalled at a Phase 3 escalation on 2026-09-14, and its code landed anyway
(commits `947a686` and `f5b76cc`). This task's changes touch those paths, so their
regression surface is in scope here. That goal's `02-tests.md` is **superseded** by this
task.

- [ ] Test: `analytics_user_totals` returns `None` when `user_cc_usage` has zero rows for
      the given emails/range.
- [ ] Test: `analytics_user_totals` returns `(totals, matched_emails)` with `totals` a
      pure `CANON`-shaped dict using the exact column mapping (`input`←`uncached_input`,
      `output`←`output`, `cacheRead`←`cache_read`,
      `cacheCreation`←`cache_creation_1h + cache_creation_5m`; never `total_tokens`),
      excluding rows for other emails and rows outside the range.
- [ ] Test: email matching is case/whitespace-insensitive — seed `"a@x.com"`, query
      `"A@X.com "`, assert `"a@x.com"` is in `matched_emails` and a never-seeded
      `"b@x.com"` is not, so the caller can derive it as unmatched.
- [ ] Test: `otel_totals(store, start, end, emails=[...])` scopes `captured`/`tagged` to
      those emails, excluding other emails in the same range.
- [ ] Test: the `--email` path where the analytics side is empty prints the
      `billing.ingest` hint and **no** `COVERAGE FUNNEL`.
- [ ] Test: the `--email` path where analytics has data and OTEL has zero matching rows
      prints a normal funnel with `captured`/`tagged` = 0 and no `SYNTHETIC` line.

### Coverage map

- [ ] Append a new top-level section `# Coverage map: reconcile-coverage-diagnostics` to
      `tests/COVERAGE_MAP.md`.
- [ ] **You may also generalize the file's H1 and opening paragraph into an index** — it
      currently reads `# Coverage map: desktop-usage-capture` and claims to map that one
      goal's criteria, which a second goal's section makes false. Retitle it (e.g.
      `# Coverage maps`) and rewrite the preamble to say it indexes one section per goal,
      keeping the existing legend and the existing per-goal content intact. This is the
      **only** permitted edit to pre-existing lines in this file; every criterion row
      already there stays byte-for-byte as-is.
- [ ] One sub-table per task (01–03) mapping each acceptance criterion to its pytest node
      id(s), in the same `file::test_name` format the existing file uses.
- [ ] A criterion with no test is listed as a **GAP**, never omitted. Do not write `TBD`.

## Acceptance Criteria

1. Both test files exist and every requirement above has a corresponding test —
   verification: code review against this checklist.
2. `python -m pytest tests/test_reconcile.py tests/test_dedupe_counter.py -q` exits 0 —
   verification: command output.
3. `python -m pytest tests/test_otel_store.py -q` still exits 0 and
   `tests/test_otel_store.py` is unmodified — verification: command output plus
   `git diff --stat tests/test_otel_store.py` being empty.
4. No test touches `data/otel.db` or `data/analytics.db`, and none makes a live network
   call — verification: grep every `run(` call for an explicit `db=`; confirm every
   `AnalyticsClient` / `analytics_claude_code_*` reference sits behind Seam A or Seam B
   (and that every Seam B use includes the `setenv`); confirm every database path is under
   `tmp_path`.
5. `tests/COVERAGE_MAP.md` has the new section, every criterion from tasks 01–03 is mapped
   or explicitly marked GAP, and the only pre-existing lines changed are the H1 and the
   opening paragraph — verification: `git diff tests/COVERAGE_MAP.md` review.

## Files to Read

- `_goals/reconcile-coverage-diagnostics/01-store-dedupe-counter.md`,
  `02-reconcile-aggregation.md`, `03-reconcile-output.md` — the acceptance criteria you
  are writing tests for. Read all three; they are the specification. Note each one's
  revision header, which lists what changed in cycle 1.
- `billing/reconcile.py` — the functions under test, post-task-03.
- `billing/otel/otel_store.py` — the `dedupe_drops` schema, the three read helpers, the
  epoch constant and its insert-path semantics, and the
  `token_usage`/`session_repo_timeline` schemas for seeding.
- `billing/store.py` — the `user_cc_usage` schema for seeding the analytics side.
- `billing/analytics_client.py` — `__init__`'s no-token raise and `usage_report`'s yield
  shape, so your Seam B fakes match the real signature.
- `tests/conftest.py` — fixtures to reuse and seeding patterns to follow. Note
  `seed_otlp_rows` is a plain function.
- `tests/test_otel_store.py` — house style for store tests (read-only; do not edit).
- `tests/COVERAGE_MAP.md` — the existing format you are appending to.
- `.claude/skills/python-testing-patterns/SKILL.md` — fixtures, mocking, TDD shape.
- `.claude/skills/test-ladder/SKILL.md` — rungs 1–2 only. Do NOT run
  `python -m pytest -q` (rung 3); that is the orchestrator's call at cycle end.

## Files to Create / Change

- `tests/test_reconcile.py` — new; tasks 02 + 03 criteria plus the regression coverage.
- `tests/test_dedupe_counter.py` — new; task 01 criteria.
- `tests/COVERAGE_MAP.md` — append one new section; generalize H1 + preamble only.

## Constraints

- Must: `tmp_path`-backed SQLite for every fixture; explicit `db=` on every `run()` call;
  Seam A or Seam B for every Analytics touch, with `setenv` on every Seam B use.
- Must: assert on specific values and strings, not shapes or substrings-of-anything.
- Must NOT: modify `tests/conftest.py`, `tests/test_otel_store.py`, any other existing
  test, or anything under `billing/`.
- Must NOT: fix a bug you find in tasks 01–03. Report it in the completion report and
  leave the failing test in place — that is the signal the orchestrator needs.
- Must NOT: weaken or delete an assertion to make a test pass.
- Must NOT: add a third-party test dependency. `pytest` is the only one permitted.

## Verification

- Targeted test command:
  `python -m pytest tests/test_reconcile.py tests/test_dedupe_counter.py -q`
- Also report: the count of tests added per task, and any criterion you could not cover
  with an automated test, named explicitly as a GAP with the reason.
