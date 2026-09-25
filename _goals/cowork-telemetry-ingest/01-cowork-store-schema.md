# Task 01: Cowork store schema + read-only repo-attribution lookup

## Objective

A new, fully separate SQLite store exists for Cowork usage — `billing/otel/cowork_store.py`
— with its own database file, its own `token_usage`/`cost_usage`-shaped tables, and
dedupe/insert methods mirroring `otel_store.py`'s conventions closely enough that tasks 02–04
can consume them without re-deriving the pattern. A second, small module provides a
**read-only** lookup against the EXISTING `otel.db`'s `session_repo_timeline` table, for
resolving which repo a Cowork session belongs to — without ever opening that database
read-write, and without changing anything in `otel_store.py`.

This is the contract task for the whole goal: every other task depends on the schema, insert
signatures, and lookup function frozen here.

## Dependencies

- 00-test-scaffold

```yaml
# --- task ownership contract ---
writes:
  - billing/otel/cowork_store.py
  - billing/otel/cowork_attribute.py
  - tests/test_cowork_store.py
  - tests/test_cowork_attribute.py
reads:
  - billing/otel/otel_store.py
  - billing/otel/attribute.py
  - billing/otel/normalize.py
  - tests/conftest.py
depends_on:
  - "00-test-scaffold"
owner: implementer
rewrite_semantics: whole-file
eval_depth: full   # reason: this is the goal's contract task — every later task consumes its
                    # frozen schema, insert signatures, and resolve_repo/otel_db_reachable
                    # contracts without re-checking them; a defect here propagates silently
                    # into every consumer.
```

## Requirements (exhaustive — the evaluator verifies every item)

- [ ] `billing/otel/cowork_store.py` defines a `CoworkStore` class, structurally independent
      of `OtelStore` (no shared base class, no shared schema string) — copy the pattern, do
      not couple to it, so a future change to `otel_store.py`'s schema can never ripple into
      this file by accident.
- [ ] Its own module-level default: `DEFAULT_COWORK_DB = os.environ.get("COWORK_DB",
      "./data/cowork.db")` — a distinct path and a distinct env var from `OTEL_DB`/
      `DEFAULT_DB` in `otel_store.py`.
- [ ] Schema, in this new database only:
      - `cowork_token_usage` — columns: `dp_key` PK, `ts`, `session_id`, `repo`, `repo_raw`,
        `user_email`, `user_id`, `org_id`, `model`, `token_type`, `query_source`, `tokens`,
        `ingested_at`. `repo`/`repo_raw` are stored as empty strings (`""`), never `NULL`, at
        insert time. `repo_raw=""` DOES match `receiver.py`'s own `"repo_raw": repo_raw or ""`
        convention; `repo=""` does NOT match `otel_store.py`'s convention there, which stores
        the resolved literal `'unknown'` when there's no git remote (verified by reading
        `normalize_remote`) — the two columns are handled differently on purpose here, because
        Cowork's cloud-VM sessions carry no wrapper-stamped `repo=` resource attribute at all,
        so there is no wrapper-level value to record, resolved or otherwise. `repo=""` means
        "no signal captured at ingest time, resolve at report time" — a different, Cowork-
        specific meaning from `otel_store.py`'s `'unknown'`, which means "resolved, and the
        answer is unknown." This store never resolves attribution itself; it stores the raw
        session id and lets a report resolve it via `cowork_attribute.py` at read time
        (query-time resolution, same invariant as `attribute.py`).
      - `cowork_cost_usage` — mirrors `cost_usage` (`dp_key` PK, `ts`, `session_id`, `repo`,
        `repo_raw`, `user_email`, `user_id`, `org_id`, `model`, `query_source`, `cost_usd`,
        `ingested_at`).
      - Both tables dedupe on `dp_key` via `INSERT OR IGNORE`, same discipline as
        `otel_store.py`.
      - No `session_repo_timeline`, `repo_name_map`, `invoices`, or `fabric_outbox` tables —
        those are explicitly out of scope; this store only ever holds raw Cowork usage rows.
- [ ] `CoworkStore.insert_datapoint(...)` / `insert_cost_datapoint(...)`: keyword-only
      signatures, EXACTLY these fields (no more, no fewer — `OtelStore`'s equivalents ALSO take
      `usage_source`/`entrypoint`/`request_id`, which this schema has no column for; do not add
      them here just because `OtelStore` has them):
      `insert_datapoint(*, session_id, repo, repo_raw, user_email, user_id, org_id, model,
      token_type, query_source, tokens, time_unix_nano)` and `insert_cost_datapoint(*,
      session_id, repo, repo_raw, user_email, user_id, org_id, model, query_source, cost_usd,
      time_unix_nano)` — matching `receiver.py`'s `ingest_metrics_payload`'s own call-site
      shape for the fields that DO overlap, so task 02's row dicts map onto these with no
      renaming. Both return `True` on a new insert and `False` on a deduped replay.
- [ ] `CoworkStore.commit()` / `.close()` mirroring `OtelStore`. The connection is stored on a
      PUBLIC attribute named exactly `self.db` (matching `OtelStore`'s own attribute name) —
      task 03 needs to call `store.db.rollback()` directly for its commit-region error handling,
      and freezing this name here is what makes that legal without task 03 reaching into an
      undocumented internal.
- [ ] `CoworkStore.last_ingest_at() -> str | None`: returns the MAX `ingested_at` across both
      `cowork_token_usage` and `cowork_cost_usage` (mirror `OtelStore.last_ingest_at`'s query
      shape), or `None` if both tables are empty. Task 03's `/healthz` endpoint calls this
      directly — it is part of this task's frozen contract, not something task 03 may assume
      exists without it being specified here.
- [ ] A `dp_key` composition documented inline (dims + timestamp, same idea as
      `otel_store.py`'s docstring) — deterministic and collision-safe for the fields this
      table stores.
- [ ] `billing/otel/cowork_attribute.py` provides a `_connect_ro(path: str) ->
      sqlite3.Connection` seam and a public `resolve_repo(session_id: str, ts: str,
      otel_db_path: str | None = None) -> tuple[str, str]` built on top of it. `_connect_ro` is
      a first-class, independently testable seam specifically so a test can open a connection
      through it and assert a write against that connection raises — `resolve_repo` alone (a
      function returning a plain tuple) gives a test no connection object to exercise.
      **Build the read-only URI as `Path(path).resolve().as_uri() + "?mode=ro"`, NEVER
      `f"file:{path}?mode=ro"` with the raw path string.** Phase 3 review found the naive
      f-string form opens the database READ-WRITE (and can CREATE a new file) whenever `path`
      contains a `#` or `?` character, because SQLite's URI parser treats everything after
      those characters as the fragment/query rather than part of the path —
      `Path.as_uri()`'s own percent-encoding closes this. Add a regression test with a `#` in
      the fixture db's path/filename asserting the connection is still genuinely read-only.
- [ ] `cowork_attribute.py` also provides `otel_db_reachable(otel_db_path: str | None = None)
      -> bool`: attempts `_connect_ro` and then queries SPECIFICALLY for the
      `session_repo_timeline` table's existence (e.g. `SELECT 1 FROM session_repo_timeline
      LIMIT 1`, or a `sqlite_master` check for that table name) — NEVER a bare `SELECT 1`.
      Phase 3 review (cycle 3) found by running it that a bare `SELECT 1` succeeds against ANY
      valid SQLite file, including this goal's own `cowork.db` sitting right next to `otel.db`
      — the single most likely wrong-path mistake, given the two files' proximity — which
      would make `otel_db_reachable` return `True` while every subsequent `resolve_repo` call
      still silently fails with "no such table" and falls through to `("unknown", "absent")`,
      exactly the failure this function exists to catch. Returns `True` only when the table is
      confirmed present, `False` on ANY failure (missing file, locked db, corrupt file, wrong
      file with no such table) — never raises. This exists so a caller (task 04's report) can
      distinguish "the existing `otel.db` could not be reached at all" from "it was reached, and
      this particular session simply has no timeline rows" — Phase 3 review found that without
      this distinction, `resolve_repo`'s fail-safe `("unknown", "absent")` return makes a wrong
      `--otel-db` path or a missing file look EXACTLY like a normal, resolved absence, silently
      undermining the goal's own stated
      "does Cowork even produce timeline entries?" verification question.
- [ ] `resolve_repo`'s query mirrors `attribute.py`'s real fallback chain, not a simplified
      one: `COALESCE(as-of match, earliest-timeline-entry match)` — i.e. both the `_AS_OF` and
      `_FIRST` queries `attribute.py` defines (the `_FIRST` fallback exists there specifically
      to cover a datapoint whose timestamp slightly precedes the session's first hook event;
      Cowork's OTLP export timing has no reason to be exempt from that same clock-skew case).
      `attribution_source` is `"timeline"` whenever EITHER query matches (the session has at
      least one relevant timeline row), and `"absent"` only when the session has NO
      `session_repo_timeline` rows at all. Do not invent a third bucket; if real Cowork data
      later reveals a need for one (e.g. an equivalent of `attribute.py`'s `desktop-scratch`),
      that's for a follow-up goal, not a guess here. When `attribution_source` is `"absent"`,
      `repo` is the string `"unknown"` — matching `attribute.py`'s own convention that
      `no_remote`/`absent`/`desktop-scratch` all normalize to `'unknown'` — never the literal
      string `"absent"` doing double duty as both the repo value and the source label.
- [ ] `resolve_repo` (via `_connect_ro`) opens the existing `otel.db` **strictly read-only**.
      If the file doesn't exist, or the query fails for any reason, return
      `("unknown", "absent")` rather than raising — this lookup is used only by reporting
      (task 04), never by ingestion, but must still never be able to create or modify `otel.db`
      as a side effect of a missing-file open, and must never crash a report run over one bad
      session id. (Use `otel_db_reachable`, above, for the caller-visible distinction between
      "genuinely absent" and "couldn't reach the db at all" — `resolve_repo` itself stays a
      simple, always-safe two-bucket function.)
- [ ] `resolve_repo` takes the existing db path as a parameter (defaulting to
      `otel_store.DEFAULT_DB` imported READ-ONLY for its value, not its behavior) so tests can
      point it at a fixture instead of a real file.
- [ ] Every new SQL statement in both new files is parameterized (`?` placeholders) — no
      f-string/format-string SQL, matching the existing codebase's convention.
- [ ] Docstrings on both new modules state plainly: these files are part of a deliberately
      separate pipeline from `otel_store.py`/`attribute.py`; do not merge without a dedicated
      follow-up goal.

## Acceptance Criteria

1. `CoworkStore(tmp_path / "cowork.db")` creates `cowork_token_usage` and `cowork_cost_usage`
   with the documented columns — verification: unit test via `PRAGMA table_info`.
2. Inserting the same token datapoint twice returns `True` then `False`, and the table holds
   exactly one row — verification: unit test.
3. `resolve_repo` returns `("<repo>", "timeline")` for a session id present in a fixture
   `otel.db`'s `session_repo_timeline` at-or-before the given `ts`, and `("unknown", "absent")`
   for a session id with no timeline rows at all — verification: unit test against the task 00
   fixture db.
3b. `resolve_repo` called with a `ts` slightly BEFORE a session's earliest timeline entry still
   returns `("<repo>", "timeline")` via the `_FIRST`-equivalent fallback, not `("unknown",
   "absent")` — verification: unit test, mirroring `attribute.py`'s own clock-skew case.
4. `resolve_repo` against a nonexistent db path returns `("unknown", "absent")` without
   raising and without creating a file at that path — verification: unit test asserting both
   the return value and that no file was created.
5. Opening the fixture `otel.db` via `_connect_ro` directly and then attempting a write
   through that returned connection raises (proving the connection really is read-only, not
   merely convention) — verification: unit test calling `_connect_ro` and executing an
   `INSERT`/`UPDATE` against it.
5b. `_connect_ro` against a fixture db copied to a path containing a `#` character still opens
   strictly read-only (a write through it still raises) — verification: unit test reproducing
   the exact edge case found in Phase 3 review.
5c. `otel_db_reachable` returns `True` against the fixture `otel.db` (which has a
   `session_repo_timeline` table) and `False` against a nonexistent path — verification: unit
   test. Never raises in either case.
5d. `otel_db_reachable` returns `False` against a DIFFERENT, valid SQLite file that has no
   `session_repo_timeline` table (e.g. a fresh empty `CoworkStore` db, or any other valid
   `.db` file) — verification: unit test. This is the case a bare `SELECT 1` probe would get
   wrong (Phase 3, cycle 3 review); it must be tested explicitly, not merely implied by 5c.
6. `CoworkStore.last_ingest_at()` returns `None` for a freshly created store and the correct
   `MAX(ingested_at)` after inserting rows into either table — verification: unit test.
7. `git diff -- billing/otel/otel_store.py billing/otel/attribute.py` is empty after this
   task — verification: command output.

## Files to Read

- `billing/otel/otel_store.py` — the pattern to mirror (schema shape, `dp_key` discipline,
  insert/dedupe return contract). Read-only.
- `billing/otel/attribute.py` — the as-of join logic and `attribution_source` concept to
  mirror for `resolve_repo`'s two-bucket fallback. Read-only.
- `billing/otel/normalize.py` — `normalize_remote`, reusable as-is for canonicalizing any
  `repo_raw` this task's tests construct.
- `tests/conftest.py` — the task 00 fixtures (existing-otel.db fixture, Cowork payload
  fixture) this task's tests build on.

## Files to Create / Change

- `billing/otel/cowork_store.py` — new, separate store.
- `billing/otel/cowork_attribute.py` — read-only repo-attribution lookup against the
  existing `otel.db`.
- `tests/test_cowork_store.py`
- `tests/test_cowork_attribute.py`

## Constraints

- Must: keep this store's schema, file, and env var completely separate from
  `otel_store.py`'s.
- Must: open the existing `otel.db` strictly read-only from `cowork_attribute.py`.
- Must: resolve attribution at query/report time only — never persist a resolved repo into
  `cowork_token_usage`/`cowork_cost_usage`.
- Must NOT: modify `billing/otel/otel_store.py` or `billing/otel/attribute.py` in any way.
- Must NOT: add any dependency beyond the standard library (runtime) / `pytest` (tests).

## Verification

- Targeted test command: `python -m pytest tests/test_cowork_store.py tests/test_cowork_attribute.py -q`
