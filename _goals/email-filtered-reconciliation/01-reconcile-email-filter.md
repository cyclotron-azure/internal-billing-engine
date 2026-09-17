# Task 01: reconcile-email-filter

## Objective

`billing/reconcile.py` gains an optional, repeatable `--email` CLI flag. When one or
more emails are given, the reconciliation funnel (truth → captured → tagged) is scoped
to those users instead of the org-wide totals: the truth side sums
`billing/store.py`'s `user_cc_usage` table filtered by
`LOWER(TRIM(email)) IN (...)`, and the captured/tagged side filters `otel.db`'s
`token_usage` by `LOWER(TRIM(user_email)) IN (...)` (both sides match
case/whitespace-insensitively — see Requirements). With
no `--email`, output is unchanged from today. The new filtering logic lives in
reusable, importable functions (not inlined in `argparse`/`main()`), since a future
dashboard task will call them directly.

## Dependencies

- none

```yaml
# --- task ownership contract ---
writes:
  - billing/reconcile.py
  - billing/store.py
reads:
  - billing/otel/otel_store.py
  - billing/analytics_client.py
  - billing/ingest.py
  - README.md
depends_on: []
owner: implementer
rewrite_semantics: whole-file
eval_depth: full
# full: this task defines the functions a future dashboard goal will import directly
# (per goal.md's "Priority / future consumer" — real external consumer, not just
# mirroring/testing), so the interface shape needs full evaluation now.
```

## Requirements (exhaustive — the evaluator verifies every item)

**Parameter naming — read this before touching `run()`.** Today, `run(start, end, db)`
uses `db` to mean the **OTEL** database path (`OtelStore(db)`). That meaning does
**not** change. The analytics-side database gets its **own**, separate, new parameter
named `analytics_db` everywhere below — never reuse `db` for it. This applies to
`analytics_user_totals`, `run()`, and the new `--analytics-db` CLI flag.

- [ ] Add `--email` to `billing/reconcile.py`'s `argparse` setup in `main()`, as a
      repeatable flag: `ap.add_argument("--email", action="append", default=None)`.
      Also add `ap.add_argument("--analytics-db", default=None)` (optional override of
      the analytics database path; when omitted, `analytics_user_totals` opens
      `billing.store.Store` on its own default path exactly as `Store()` does today).
- [ ] Add a new function `analytics_user_totals(emails: list[str], start: str, end: str,
      analytics_db: str | None = None) -> tuple[dict, list[str]] | None` in
      `billing/reconcile.py` that:
  - Opens `billing.store.Store(analytics_db) if analytics_db else billing.store.Store()`
    (reuse `Store` — do not hand-roll a second sqlite connection helper).
  - Normalizes emails for matching on **both sides**: lower-case and strip whitespace
    from every value in the caller-supplied `emails` list in Python, and match against
    `LOWER(TRIM(email))` in SQL (still fully parameterized with `?` placeholders — never
    string-interpolate the values themselves). Queries `user_cc_usage` for rows where
    `day >= start AND day < end AND LOWER(TRIM(email)) IN (...)`.
  - Sums the token fields into the same `CANON` bucket shape using this exact mapping
    (mirrors `analytics_claude_code_totals`'s existing mapping in `reconcile.py`):
    `input` ← `uncached_input`, `output` ← `output`, `cacheRead` ← `cache_read`,
    `cacheCreation` ← `cache_creation_1h + cache_creation_5m`. Do **not** use
    `user_cc_usage.total_tokens` for any bucket.
  - Returns `None` (not a tuple) if there are zero matching rows across ALL supplied
    emails (this is the "ingest wasn't run for this range" signal — the caller decides
    what to print, this function just signals emptiness, it does not print anything
    itself). When the return is `None`, no email matched — the caller's "run ingest
    first" message covers that case fully.
  - Otherwise returns exactly `(totals, matched_emails)`: `totals` is the pure
    `CANON`-shaped dict (only the four keys `input`/`output`/`cacheRead`/
    `cacheCreation` — never a `matched_emails` key mixed into this dict, since
    `billing/reconcile.py:108`'s existing `sum(truth.values())` would then try to sum
    a list into an int) and `matched_emails` is a `list[str]` of the caller-supplied
    (normalized) emails that matched at least one row. The caller computes the
    unmatched set as `set(normalized_input_emails) - set(matched_emails)` to report
    which supplied emails matched nothing.
- [ ] Modify `otel_totals(store, start, end, emails: list[str] | None = None) -> dict`
      to add an optional `emails` parameter: when provided, normalize the same way
      (lower/strip in Python, `LOWER(TRIM(user_email))` in SQL, `?` placeholders) and
      add that condition to the existing `token_usage` query. When `emails` is `None`
      (the default), behavior and the generated SQL are unchanged from today.
- [ ] `analytics_claude_code_totals(start, end)` (the existing org-wide function) is
      left untouched in behavior and signature.
- [ ] Update `run(start, end, db=None, emails: list[str] | None = None, analytics_db:
      str | None = None)` so that:
  - When `emails` is `None`/empty: identical control flow and output to today (calls
    `analytics_claude_code_totals` + `otel_totals(store, start, end)`); `analytics_db`
    is accepted but ignored on this path (unfiltered reconciliation has never used the
    local analytics store).
  - When `emails` is non-empty: calls `analytics_user_totals(emails, start, end,
    analytics_db)` for the truth side. If it returns `None` (no analytics rows for
    those emails/range), print a clear message telling the user to run `python -m
    billing.ingest --start <start> --end <end>` first, and **return without printing
    the funnel table** (do not print a 0/n/a funnel — that would misleadingly look like
    a real coverage number).
  - Otherwise it returns `(truth, matched_emails)`; compute
    `unmatched = set(normalized_emails) - set(matched_emails)` and, if non-empty,
    print an explicit line naming those emails (e.g. `"no analytics rows matched:
    b@x.com"`) — this is the signal that catches a spelling/casing mismatch between
    the Analytics API's `actor.email` and the OTEL side's resource attribute, rather
    than that mismatch silently reading as the (valid) OTEL-side-zero case below. Use
    `truth` (the pure `CANON` dict) as the truth side of the funnel exactly as
    `analytics_claude_code_totals`'s return is used today.
  - Then calls `otel_totals(store, start, end, emails=emails)` and prints the normal
    funnel — even if the OTEL side comes back all zeros for every matched email (that's
    a valid "dev hasn't used Claude Code yet" result, not an error condition).
  - When `emails` is non-empty, suppress the existing `if C < A * 0.99: print(...
    SYNTHETIC ...)` heuristic block entirely (`billing/reconcile.py`'s current
    behavior) — that message is about the org-wide sample-payload scenario and is
    actively misleading on a filtered, low-volume, real-user view.
  - The printed header/labels make clear when a filter is active (e.g. include the
    filtered email list in the "RECONCILIATION" banner line) so filtered vs org-wide
    output is visually distinguishable.
- [ ] `main()` passes the parsed `--email` list and `--analytics-db` through to
      `run(...)`.
- [ ] No third-party imports introduced anywhere in `billing/`.
- [ ] `billing/store.py` is touched only if a query helper is needed there (e.g. a
      `Store` method to fetch `user_cc_usage` rows by email+range) — if the query is
      simple enough to inline in `reconcile.py` using `Store().db.execute(...)`
      directly (matching how `reconcile.py` already uses `OtelStore.db.execute(...)`
      for `otel_totals`), leave `store.py` untouched. Prefer the no-touch option unless
      it meaningfully improves reuse for the dashboard consumer.

## Acceptance Criteria

1. With `billing.reconcile.analytics_claude_code_totals` monkeypatched to a fixed,
   known dict and `otel_totals` fed a fixed, known seeded `token_usage` fixture (so no
   live network call occurs and `db=<tmp otel path>` is passed explicitly — never the
   real `./data/otel.db`), `run(start, end, db=<tmp otel path>)` prints stdout
   containing `"BY TOKEN TYPE"`, `"COVERAGE FUNNEL"`, `"BILLABLE COVERAGE"`, and the
   exact percentage string computed from those fixed inputs (regression content —
   this is what actually catches a change to the unfiltered formatting/math), AND
   produces byte-identical stdout whether called as `run(start, end, db=...)` or
   `run(start, end, db=..., emails=None)` (the declared-default equivalence) —
   verification: unit test using `monkeypatch` + `capsys` (fully offline,
   deterministic; no manual comparison, no live API call, no real-database write).
2. `analytics_user_totals(["a@x.com"], start, end, analytics_db=<tmp path>)` returns
   `None` when `user_cc_usage` has zero rows for that email/range, and otherwise
   returns exactly `(totals, matched_emails)` where `totals` is a pure `CANON`-shaped
   dict (only the four keys, sums matching the exact mapping specified above —
   `input`/`output`/`cacheRead`/`cacheCreation`, never `total_tokens`, never a
   `matched_emails` key mixed in) and `matched_emails` is a `list[str]` — verification:
   unit test with a temp SQLite db.
3. `analytics_user_totals(["A@X.com ", "b@x.com"], ...)` matches rows stored as
   `"a@x.com"` (case/whitespace-insensitive) and includes `"a@x.com"` in
   `matched_emails`; `"b@x.com"` does NOT appear in `matched_emails` when
   `user_cc_usage` has no row for it (caller derives the unmatched set) —
   verification: unit test with a temp SQLite db seeded with mixed-case/whitespace
   email values.
4. `otel_totals(store, start, end, emails=["a@x.com"])` returns captured/tagged dicts
   summed only over rows whose (normalized) `user_email` is in the given list, and is
   unaffected by rows for other emails in the same range — verification: unit test
   with a temp SQLite db seeded with rows for multiple emails.
5. `otel_totals(store, start, end)` (no `emails` arg) is unaffected by the new
   parameter — verification: unit test asserting identical output to a pinned
   pre-task-01 fixture/expectation.
6. Running `run(start, end, emails=["a@x.com"], analytics_db=<tmp path>)` against a
   fixture where the analytics side is empty for that email prints the "run ingest
   first" message and does not print a `COVERAGE FUNNEL` section — verification: unit
   test capturing stdout via `capsys`.
7. Running `run(start, end, emails=["a@x.com"], analytics_db=<tmp path>)` where the
   analytics side has data but the OTEL side is empty prints a normal funnel with
   `captured`/`tagged` = 0, and does **not** print the "SYNTHETIC" heuristic line —
   verification: unit test capturing stdout via `capsys`.
8. Against a seeded temp fixture pair (analytics + OTEL dbs), `run(start, end,
   emails=["x@cyclotron.com", "y@cyclotron.com"], db=<otel tmp path>,
   analytics_db=<analytics tmp path>)` exits without raising, and its stdout contains
   both `"COVERAGE FUNNEL"` and the filtered email list in the banner line —
   verification: unit test capturing stdout via `capsys` (no live `data/` dependency,
   no escape hatch to a real/live database).

## Files to Read

- `billing/reconcile.py` — the module being extended; match its existing style exactly.
- `billing/store.py` — `Store` class, `user_cc_usage` schema, `DEFAULT_DB` env var
  pattern (`BILLING_DB`).
- `billing/otel/otel_store.py` — `OtelStore` class, `token_usage` schema
  (`user_email` column already exists), `DEFAULT_DB` env var pattern (`OTEL_DB`).
- `README.md` — §"Typical OTEL flow" and the `reconcile.py` bullet under "Analytics
  path (per-user)", for the existing documented CLI usage and the single-host SQLite
  constraint under "The constraint that shapes everything".
- `billing/ingest.py` — how `user_cc_usage` gets populated (`user_usage_report`), so
  the "run ingest first" message references the right command shape.

## Files to Create / Change

- `billing/reconcile.py` — add `--email` flag, `analytics_user_totals()`, extend
  `otel_totals()` and `run()` as specified above.
- `billing/store.py` — only if a reusable query helper is added there (see last
  requirement bullet); otherwise leave untouched.

## Constraints

- Must: reuse `billing.store.Store` and `billing.otel.otel_store.OtelStore`; use
  parameterized SQL (`?` placeholders) exactly as the existing code does — never
  string-format email values into SQL.
- Must: keep `CANON` bucket shape (`input`/`output`/`cacheRead`/`cacheCreation`) as the
  common interchange shape between org-wide and filtered truth dicts.
- Must NOT: change `analytics_claude_code_totals`'s or the unfiltered `otel_totals`
  call's behavior/signature in a way existing callers would notice.
- Must NOT: introduce any third-party import.
- Must NOT: touch `billing/ingest.py`, `billing/otel/receiver.py`, `billing/bill.py`,
  `billing/invoice.py`, or anything under `deploy/`/`client-package/`.

## Verification

- **Task 01's own targeted check** (run at this task's turn — `tests/test_reconcile.py`
  is task 02's file and does not exist yet): write a throwaway script under the
  session's scratchpad directory (not committed, not under `writes:` above) that:
  1. builds a `tmp` OTEL fixture db and a `tmp` analytics fixture db (using
     `OtelStore(path)` / `billing.store.Store(path)` against explicit temp paths —
     never the real `./data/otel.db` / `./data/analytics.db`),
  2. seeds each with rows covering ACs 2, 3, 4, 6, 7, 8 (multi-email, mixed
     case/whitespace, an empty-analytics-side case, an empty-OTEL-side case),
  3. calls `analytics_user_totals`, `otel_totals`, and `run(..., db=<tmp otel path>,
     analytics_db=<tmp analytics path>)` for each scenario and prints/asserts the
     results,
  4. monkeypatches `billing.reconcile.analytics_claude_code_totals` for AC 1's
     scenario (never a live call).
  Capture that script's output as evidence for the evaluator. `pytest
  tests/test_reconcile.py -q` (task 02's file, once it lands) is the permanent,
  pinned version of these same checks — task 01 is not blocked on it existing yet.
- Every `run()` invocation anywhere in this task's verification passes an explicit
  `db=` pointing at a temp fixture path — `run()` called with no `db=` opens
  `OtelStore()`'s default `./data/otel.db` and would create/write the real file.
