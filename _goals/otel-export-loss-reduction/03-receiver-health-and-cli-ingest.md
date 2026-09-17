# Task 03: receiver health route + CLI transcript acceptance

## Objective

The receiver answers `GET /healthz` — liveness to anyone, ingest-freshness to an
authorized caller — and `/v1/transcript-usage` accepts `cli` and `claude-vscode` records
in addition to `claude-desktop`, but only for sessions that have no OTLP rows and only
once they are old enough that a final flush cannot still be in flight. Desktop behavior is
untouched in every respect.

## Dependencies

- `02-store-reads` (both new methods are consumed here)

```yaml
# --- task ownership contract ---
writes:
  - billing/otel/receiver.py
  - billing/otel/transcript.py
reads:
  - billing/otel/otel_store.py       # task 02's two frozen signatures
depends_on:
  - "02-store-reads"
owner: implementer
rewrite_semantics: targeted-insertion
eval_depth: full
# full: this task decides whether a transcript row is billed. Its guard is the only thing
# standing between CLI backfill and double-billing a client, and task 04 is a consumer of
# the entrypoint contract it defines.
```

## Requirements (exhaustive — the evaluator verifies every item)

### Part A — `GET /healthz`

- [ ] Add a `do_GET` handler. `receiver.py` has none today, so every `GET` currently falls
      through to `BaseHTTPRequestHandler`'s default 501.
- [ ] `GET /healthz` (suffix-matched the same way `do_POST` matches its paths, so a path
      prefix in front of it still works) returns **200** with
      `Content-Type: application/json` and a JSON object.
- [ ] **Unauthenticated body** contains exactly `status` (`"ok"`) and `now` (UTC ISO8601).
      Nothing else. It must not include ingest times, row counts, session ids, emails,
      repo names, the token, any prefix or length of the token, or whether
      `RECEIVER_AUTH_TOKEN` is set. A prober on the public internet learns only that the
      process is answering.
- [ ] **Authorized body** additionally contains `last_ingest_at`,
      `last_otlp_ingest_at`, `stale_seconds` and `otlp_stale_seconds`. The detail gate is
      **`AUTH_TOKEN and self._authorized()`** -- both halves. `_authorized()` alone is NOT
      sufficient: it returns `True` when `RECEIVER_AUTH_TOKEN` is unset
      (`receiver.py:415`), which is the documented open-receiver rollout posture, so
      reusing it alone would hand freshness detail to any prober and would make the body's
      *shape* disclose whether a token is configured. Reuse `_authorized()` for the
      comparison itself -- do not re-implement or weaken it -- but require a non-empty
      `AUTH_TOKEN` as well. On an open receiver, detail is never served; that is intended.
      Do NOT change `do_POST`'s treatment of the unset-token case.
- [ ] `last_ingest_at` / `last_otlp_ingest_at` come from task 02's
      `last_ingest_at(usage_source=None)` and `last_ingest_at(usage_source="otlp")`. Both
      serialize as JSON `null` when the store returns `None`.
- [ ] `stale_seconds` is the whole number of seconds between that timestamp and now, and
      is JSON `null` — **not** `0`, and not a large sentinel — when the timestamp is
      `None`. "No rows ever" and "rows, zero seconds old" must be distinguishable.
- [ ] A negative computed staleness (clock skew, a row stamped slightly in the future) is
      clamped to `0` rather than reported negative.
- [ ] `GET` to any other path returns **404**, not 200. A health probe that passes on
      every path is not a health probe.
- [ ] The handler opens no new connection and starts no thread. It reads through the
      receiver's existing store/connection exactly as the POST paths do.
- [ ] A `sqlite3.Error` while reading freshness returns **503** with
      `{"status": "degraded"}` and no detail, rather than a traceback or a 200. A receiver
      that cannot read its own database is not healthy, and the error text may name file
      paths.
- [ ] `do_POST` and every existing POST path (`/v1/metrics`, `/v1/session-repo`,
      `/v1/transcript-usage` acks, `/v1/logs`, `/v1/traces`, the catch-all) are
      **byte-unmodified** except where Part B requires it.
- [ ] The startup banner line that lists accepted routes is extended to mention
      `GET /healthz`.

### Part B — CLI / VS Code transcript acceptance

- [ ] `transcript.py`'s single `ALLOWED_ENTRYPOINT = "claude-desktop"` becomes an allowed
      **set** containing exactly `claude-desktop`, `cli`, `claude-vscode`. Keep a
      module-level name for it and keep the server-side enforcement — an unknown
      entrypoint still rejects with the existing `invalid_entrypoint` reason and that
      reason string does not change.
- [ ] The server-side mapping currently **overwrites** the record's entrypoint with the
      constant (`row["entrypoint"] = ALLOWED_ENTRYPOINT`, around line 519). That must
      become "preserve the record's own validated entrypoint". Left as-is, every
      backfilled CLI row would be stored as `claude-desktop` and the per-surface
      breakdown from the previous goal would attribute CLI usage to the desktop app.
- [ ] `usage_source` stays `'transcript'` for all of them. It is the *ingest path*, not
      the surface; `entrypoint` is the surface.
- [ ] **OTLP exclusion.** For records whose entrypoint is `cli` or `claude-vscode`, call
      task 02's `sessions_with_otlp_rows` **once per batch** with the batch's distinct
      session ids — not once per record — and reject every record whose session is in the
      returned set with the new reason `session_has_otlp`. Rejected means **nothing is
      inserted** for that record, neither token rows nor its cost row.
- [ ] **Type-validate `session_id`, added after fix cycle 1.** `_validate_record` must
      reject a non-`str` `session_id` with a new reason string added to
      `transcript.REJECTION_REASONS` (follow the existing `invalid_ts` /
      `invalid_entrypoint` vocabulary; do not reuse or alter an existing string, and do not
      overload `missing_field:session_id`, which means absent rather than wrong-typed).
      Rationale: `session_id` is currently the **only** billing-critical field with no type
      check -- `ts` is checked at `transcript.py:339`, `request_id` at `:385`, token values
      at `:284-289`, `entrypoint` and `query_source` are enum-checked, and unknown fields
      fail closed. That single gap sits on the key the OTLP guard depends on, and Python
      `str()` vs SQLite TEXT affinity diverge for `true`/`false`/`1e20`. Validate in
      `transcript.py` (in fence); do **not** normalize in `otel_store.py`, which is out of
      fence and would alter `dp_key` inputs and re-bill history.
- [ ] **Preconditions on the guard call, added after task 02's evaluation.** Task 02's
      evaluator established two shapes that are spec-consistent in the store but dangerous
      here, because `set()` reads downstream as *no OTLP rows -> safe to insert* — the
      double-billing direction:
      (a) `sessions_with_otlp_rows(None)` returns `set()`. Never let a `None` reach it.
      Build the id collection explicitly and, if it comes out empty when you expected
      records, treat that as a bug rather than as "nothing to exclude".
      (b) Non-string ids normalize silently: `[123]` returns `{'123'}`, i.e. the **stored
      string**, so `123 in result` is `False` while that session really does have OTLP
      rows. Pass `str` session ids only, and compare against the returned strings.
      Both are preconditions this task owns; task 02 was correct not to guess at them.
- [ ] **Quarantine.** Reject a `cli` / `claude-vscode` record whose newest timestamp is
      within `BACKFILL_MIN_AGE_SECONDS` of now, with the new reason `too_recent`. Define
      `BACKFILL_MIN_AGE_SECONDS = 900` as a module constant — not an env var, not a CLI
      flag. **Placement matters:** define the constant and the two new reason strings in
      `transcript.py` (pure data), but perform the age **comparison** in `receiver.py`.
      `transcript.py` has no clock at all and `README.md:150` documents it as "Pure and
      stdlib-only -- no I/O, no store access"; putting a `now()` comparison there
      contradicts ground truth. Rationale to put in the comment: the `SessionEnd` hook and the exporter's
      shutdown flush race, so a session that ends *now* may still have OTLP rows arriving;
      15 minutes makes the exclusion check meaningful instead of a coin flip.
- [ ] **The clock must be patchable.** Every "now" this task introduces — the `/healthz`
      `now` field, `stale_seconds`, and the quarantine comparison — reads through a
      module-level helper (reuse the module's existing `_now()`-style helper if one
      exists; add one if not). Do **not** call `datetime.now()` / `time.time()` inline at
      the comparison site: task 05 has to freeze time to test a 15-minute boundary and a
      future-stamped row, and `sleep`-based tests are not acceptable.
- [ ] `claude-desktop` records are **exempt from both new checks**. The desktop app has no
      OTLP exporter, so `sessions_with_otlp_rows` would always answer "no" for it — the
      check is pure cost — and quarantining desktop records would delay or regress
      existing capture. This exemption is what keeps every existing desktop test passing
      untouched.
- [ ] Both new reasons appear in whatever reason enumeration/tuple `transcript.py` already
      maintains (there is an existing tuple of reason strings including
      `invalid_entrypoint`), so a caller can enumerate them.
- [ ] The rejected-record structure stays `{"index": int, "request_id": str|None,
      "reason": str}`. Field names, order of keys, and the response's existing top-level
      shape do not change — a client parses this.
- [ ] The deliberate divergence in `/v1/transcript-usage`'s error handling relative to
      `/v1/metrics` and `/v1/session-repo` (there is an explanatory comment at the
      dispatch site) is preserved. Do not "harmonize" it.
- [ ] `transcript_key` is not redefined, not given a field, and not merged with `dp_key`.
- [ ] Two records in one batch for the same session — one `cli`, one `claude-desktop` — are
      judged independently. The desktop one is never rejected because of the CLI one.
- [ ] Standard library only.

## Acceptance Criteria

1. Unauthenticated `GET /healthz` returns 200 and a body whose key set is exactly
   `{"status", "now"}` — assert the key set, not just that the keys are present, so an
   added field fails — verification: integration test
2. Authorized `GET /healthz` returns 200 and a body containing all four detail fields with
   correct values against a seeded store — verification: integration test
3. With `RECEIVER_AUTH_TOKEN` set and a **wrong** bearer token, the body is the
   unauthenticated key set and the status is still 200 — liveness must not require auth —
   verification: integration test
4. The unauthenticated body contains no substring of the configured token, for a token
   chosen so that a naive prefix leak would be detectable — verification: integration test
5. On an empty store, the authorized body has `last_ingest_at: null` **and**
   `stale_seconds: null`, not `0` — verification: integration test
6. A row whose `ingested_at` is 3 hours old yields `stale_seconds` within 5 of 10800;
   a row stamped 60s in the future yields `0`, not a negative number — verification:
   integration test
7. `last_otlp_ingest_at` ignores a newer transcript row while `last_ingest_at` reflects it,
   in one fixture — verification: integration test
8. `GET /v1/metrics`, `GET /`, and `GET /healthzz` each return 404 — verification:
   integration test
9. A store read raising `sqlite3.Error` yields 503 with body `{"status": "degraded"}` and
   the exception text appears nowhere in the response — verification: integration test
10. A `cli` record for a session with an existing OTLP row is rejected with reason
    `session_has_otlp`, and `SELECT COUNT(*)` over **both** `token_usage` and
    `cost_usage` is **identical** before and after the request. Run it **twice**: once
    where the session's OTLP rows are in `token_usage`, and once where its only OTLP row
    is in `cost_usage` (built via `insert_cost_datapoint` alone, as a partial flush
    leaves it). The second case is the double-billing path — verification: integration test
11. A `cli` record for a session with no OTLP row, timestamped 2 hours ago, is inserted
    with `usage_source='transcript'` and `entrypoint='cli'` — asserting the stored
    `entrypoint` value, which is what fails if the overwrite is left in place —
    verification: integration test
12. A `claude-vscode` record behaves as 11 does, storing `entrypoint='claude-vscode'` —
    verification: integration test
13. A `cli` record timestamped 60 seconds ago is rejected with reason `too_recent` and
    inserts nothing; the same record timestamped 2 hours ago is accepted — one test, both
    halves, so the boundary is proven to be the age and not the record — verification:
    integration test
14. A `claude-desktop` record for a session that *does* have an OTLP row is **accepted**,
    and a `claude-desktop` record timestamped 60 seconds ago is **accepted** — the two
    exemptions, asserted positively — verification: integration test
15. An entrypoint outside the allowed set still rejects with the unchanged reason string
    `invalid_entrypoint` — verification: integration test
16. A 40-record batch of `cli` records across 40 distinct sessions calls
    `sessions_with_otlp_rows` exactly **once**, proven by a call-counting spy on the store
    method. The same spy must also capture the argument and assert it is **not `None`** and
    that **every element is a `str`** — those are the two preconditions from task 02's
    evaluation, and both fail in the double-billing direction (`None` and a non-matching
    id type each yield "no OTLP rows") — verification: integration test
17. A mixed batch with one `cli` record whose session has OTLP rows and one
    `claude-desktop` record in the same session: the CLI record is rejected, the desktop
    record is inserted — verification: integration test
18. Every pre-existing test in `tests/test_receiver.py`, `tests/test_transcript.py`,
    `tests/test_transcript_hook.py` and `tests/test_integration_desktop.py` passes with no
    edit **except** the four assertions that pin `cli`/`claude-vscode` as *rejected*, which
    this behavior change deliberately inverts and which **task 05 owns**:
    `tests/test_transcript.py:134-139` (parametrized over `["cli","claude-vscode"]`,
    asserts `invalid_entrypoint`), `tests/test_transcript.py:369-381` (rejected indices
    `[1,2,4,5]`, where `req-2` is `cli`), `tests/test_receiver.py:278-287`, and
    `tests/test_integration_desktop.py:393-399`. Do not edit them yourself. Instead, list
    every pre-existing test your change breaks in your report, with file:line, so task 05
    inverts exactly that set and nothing more. A break you do not report is a defect --
    verification: unit test
19. `GET /healthz` served while a POST is in flight does not require a second connection:
    assert the store object identity / connection count is unchanged, or assert no
    `sqlite3.connect` call occurs during the request — verification: integration test
20. **The whitespace regression, added after fix cycle 1.** An OTLP row and a `cli` record
    sharing a **whitespace-padded** `session_id` (e.g. `" sess-ws-777 "`) must reject with
    `session_has_otlp` and leave `SELECT COUNT(*)` over **both** `token_usage` and
    `cost_usage` unchanged. Background: the store persists `session_id` **verbatim** —
    `insert_datapoint`'s `.strip()` applies only to `request_id` — so any normalization
    applied to the guard's lookup key that is not also applied by the store makes the query
    miss and the guard return `set()`, which reads as "safe to insert". Verified
    empirically: stored `' sess-ws-777 '`, stripped lookup returned `set()`, verbatim
    lookup returned the session. This criterion fails if normalization is reintroduced at
    either the build site or the lookup site — verification: integration test
21. **The type-conversion class, added after fix cycle 1.** A `cli` record whose JSON
    `session_id` is `true` or `1e20`, with an OTLP row pre-seeded for that same session,
    must insert **nothing** -- `SELECT COUNT(*)` over both `token_usage` and `cost_usage`
    unchanged -- and must reject with the new reason string. Background, verified
    empirically: Python's `str()` and SQLite's TEXT-affinity conversion **disagree**, so a
    non-`str` id makes the guard's key diverge from the stored value even when build and
    lookup sites agree with each other:

    | JSON value | `str(x)` | SQLite stores |
    |---|---|---|
    | `true` | `'True'` | `'1'` |
    | `false` | `'False'` | `'0'` |
    | `1e20` | `'1e+20'` | `'1.0e+20'` |
    | `123` | `'123'` | `'123'` (agrees -- which is why the `123` example alone was not enough) |

    This criterion pins the **class**, not the instance. Criterion 20 pins whitespace;
    this one pins type. Both exist because criteria 10 and 16 passed while the guard was
    defeated -- verification: integration test

## Files to Read

- `billing/otel/receiver.py` — the whole module: `_authorized()`, the `do_POST` dispatch
  and its per-path message formats, the unset-token posture, the startup banner, and the
  transcript ingest function
- `billing/otel/transcript.py` — the payload contract, `ALLOWED_ENTRYPOINT`, the reason
  tuple, the validator, and the mapping function that overwrites `entrypoint`
- `billing/otel/otel_store.py` — task 02's two signatures (read-only here)
- `tests/test_receiver.py`, `tests/test_integration_desktop.py` — the existing desktop
  expectations this task must not disturb (read-only; task 05 writes tests)
- `README.md` §"1: Receiving telemetry data" and the "Config & secrets" auth contract

## Files to Create / Change

- `billing/otel/receiver.py` — `do_GET` + `/healthz`, banner line, batch OTLP-exclusion
  and quarantine wiring in the transcript ingest path
- `billing/otel/transcript.py` -- allowed-entrypoint set, preserve-entrypoint fix, two
  new reason codes, and the `BACKFILL_MIN_AGE_SECONDS` constant (data only; the age
  comparison itself belongs in `receiver.py`)

## Constraints

- Must: gate detail on `AUTH_TOKEN and self._authorized()`, reusing `_authorized()`
  for the comparison without altering it.
- Must: call `sessions_with_otlp_rows` once per batch.
- Must: keep `claude-desktop` exempt from both new checks.
- Must NOT: thread the receiver, add a connection pool, set WAL, or pass
  `check_same_thread`.
- Must NOT: change `dp_key`, `transcript_key`, the `token_usage`/`cost_usage` schema, or
  add a column or table. If this task appears to need one, stop and escalate.
- Must NOT: change any existing reason string, the rejected-record shape, or the
  `/v1/metrics` and `/v1/session-repo` behaviors.
- Must NOT: edit any file under `tests/`, `billing/reconcile.py`, or `client-package/`.
- Must NOT: let the health route echo configuration. When in doubt about a field, leave it
  out — a field can be added later, a leak cannot be withdrawn.

## Verification

- `python -m pytest tests/test_receiver.py tests/test_transcript.py tests/test_transcript_hook.py tests/test_integration_desktop.py tests/test_otel_store.py -q`
  -> passing, unchanged counts
- Capture verbatim: the unauthenticated `/healthz` body, the authorized body against a
  seeded store, and the rejected-records list from a mixed batch exercising
  `session_has_otlp`, `too_recent` and `invalid_entrypoint` together.
