# Task 03: Standalone Cowork receiver process

## Objective

A brand-new, standalone HTTP server, `billing/otel/cowork_receiver.py`, runnable as
`python -m billing.otel.cowork_receiver`, that accepts OTLP/JSON on its own port, with its
own auth token, and writes to `CoworkStore` — structurally parallel to `receiver.py` but a
completely separate process, sharing no port, token, or database file with it.

**This second process is a deliberate, user-approved exception to README.md's/CLAUDE.md's
"one receiver process" hard constraint** (see `goal.md`'s explicit note and
`_goals/cowork-telemetry-ingest/orchestration-log.md`'s recorded confirmation): the exception
is scoped narrowly to "one receiver process per SQLite store," never to relaxing SQLite's
single-connection safety within EITHER store. This task's evaluator should treat a second
receiver process as expected and approved for this goal, not as a violation to flag.

## Dependencies

- 00-test-scaffold
- 01-cowork-store-schema
- 02-cowork-ingest-payload

```yaml
# --- task ownership contract ---
writes:
  - billing/otel/cowork_receiver.py
  - tests/test_cowork_receiver.py
  - .env.example
depends_on:
  - "00-test-scaffold"
  - "01-cowork-store-schema"
  - "02-cowork-ingest-payload"
owner: implementer
rewrite_semantics: whole-file
# NOTE: `.env.example` is the one exception to `whole-file` above — this task only APPENDS
# three new placeholder lines to it (COWORK_RECEIVER_AUTH_TOKEN, COWORK_DB,
# COWORK_RECEIVER_LOG); it must never rewrite or reorder the file's existing content.
eval_depth: full   # reason: the live ingress point for real Cowork traffic — a defect here
                    # (auth bypass, a crash on malformed input, or accidentally touching the
                    # existing receiver's port/token/db) is the exact failure class this whole
                    # goal exists to avoid.
reads:
  - billing/otel/receiver.py
  - billing/otel/cowork_store.py
  - billing/otel/cowork_ingest.py
  - billing/otel/cowork_attribute.py
  - billing/config.py
  - README.md
  - .env.example
```

## Requirements (exhaustive — the evaluator verifies every item)

- [ ] `python -m billing.otel.cowork_receiver` starts an `http.server.HTTPServer` (same
      single-connection, no-threading discipline as `receiver.py` — this project's SQLite
      constraint applies equally to the new store), with its own CLI: `--host` (default
      `127.0.0.1`), `--port` (default distinct from `4318` — use `4319`), `--db` (defaults to
      `cowork_store.DEFAULT_COWORK_DB`), `--require-auth`.
- [ ] Auth is gated by a NEW, distinct environment variable — `COWORK_RECEIVER_AUTH_TOKEN` —
      never `RECEIVER_AUTH_TOKEN`. Reuse `receiver.py`'s constant-time comparison approach
      (`hmac.compare_digest`) and its `X-Billing-Token` / `Authorization: Bearer` header
      convention for consistency, but read the new env var. `--require-auth` refuses to start
      without it set, mirroring `receiver.py`'s `serve()` guard.
      **Loading it from `.env`, resolved:** call `from billing.config import load_env;
      load_env()` at module import time. This is `billing.config` — a small `.env` reader used
      by several modules in this repo (`analytics_client.py` among them), NOT
      `billing.otel.receiver` — so calling it does not violate the "never import
      `billing.otel.receiver`" rule. Precisely, and correcting an overstatement from an earlier
      revision: `load_env()` DOES write every `.env` key (including `RECEIVER_AUTH_TOKEN`, if
      present) into `os.environ` via `setdefault` — it is not side-effect-free in the abstract,
      it is simply the ordinary, shared, repo-wide way `.env` gets loaded, and every other
      module that calls it already accepts that same environment-wide effect. What actually
      matters for this task's isolation requirement is narrower and still holds: THIS FILE
      never reads or references `RECEIVER_AUTH_TOKEN` — it reads ONLY
      `os.environ.get("COWORK_RECEIVER_AUTH_TOKEN", "")`, so the existing receiver's token
      value is never consulted or compared against here, even though it may sit in the
      environment alongside the Cowork one. A test for this must reset `billing.config._LOADED`
      (a module-level guard that makes a second `load_env()` call a no-op) and clear any
      real `COWORK_RECEIVER_AUTH_TOKEN` from the test environment before asserting a temp
      `.env` file's value was picked up.
- [ ] `POST /v1/metrics` reads the body (DUPLICATE `receiver.py`'s `_read_body` chunked/gzip
      handling as a local function — do NOT `import` anything from `billing.otel.receiver`;
      that module runs `load_env()` and populates an `AUTH_TOKEN` global at import time, which
      would silently couple this process's behavior to the existing pipeline's environment.
      Same rule as task 02's `cowork_ingest.py`), parses JSON, calls
      `cowork_ingest.parse_cowork_payload`, and stores every accepted row via
      `CoworkStore.insert_datapoint`/`insert_cost_datapoint`, then `store.commit()`. Responds
      200 with a JSON body reporting inserted/duplicate/rejected counts (mirror the shape of
      `receiver.py`'s existing responses where it makes sense). A malformed body (bad JSON,
      non-dict envelope) responds 400 — log ONLY the error and byte count, never
      `raw[:120]`/request content, mirroring `receiver.py`'s OWN deliberate divergence on its
      `/v1/transcript-usage` 400 path (its comment explains why: echoing raw bytes on that
      endpoint would leak payload content into a log file, which this receiver must avoid too).
      **Each accepted-for-storage record is wrapped in its own try/except** catching data-shape
      errors (mirror `receiver.py`'s own `_RECORD_DATA_ERRORS` tuple and its documented
      reasoning — a malformed field that passes `cowork_ingest.py`'s validation but still
      raises at the store-insert boundary, e.g. an unbindable SQLite parameter type, must
      become a per-record rejection, not a dropped connection with no response) so one bad
      record never costs the rest of the batch its insert. `store.commit()` and the per-record
      loop both live inside one guarded region whose `except` calls `store.db.rollback()`
      before re-raising on any error NOT in that data-shape tuple (e.g. `sqlite3.
      OperationalError` — a genuine operational failure) — this is the same "leave the
      connection clean, never let uncommitted rows survive for the next request's commit to
      silently pick up" discipline `receiver.py`'s `ingest_transcript_usage_payload` already
      documents and this task must not skip merely because it's a smaller receiver.
- [ ] Every rejection `parse_cowork_payload` returns (see task 02's `rejections` list) is
      written, one line per rejection, to this receiver's OWN request log (see the log-file
      requirement below) — the reason string and the minimal identifiers needed to debug it
      (e.g. `session_id`, metric name), NEVER raw request bytes or full payload content. This
      is what "fail closed... and logged" (goal.md) actually requires; a rejection that is
      silently swallowed with no log line does not satisfy it.
- [ ] `GET /healthz` returns liveness (`{"status": "ok", "now": <iso ts>}`) unauthenticated;
      with a valid token AND a non-empty auth token configured, additionally reports
      `last_ingest_at` — call `store.last_ingest_at()` (task 01's frozen contract method)
      directly — mirror `receiver.py`'s `_healthz` gating logic (both conditions required, not
      `_authorized()` alone) since that logic exists specifically to avoid disclosing whether a
      token is configured to an unauthenticated caller.
- [ ] Any other POST path (`/v1/logs`, `/v1/traces`, unknown paths) is acknowledged with 200
      and an EMPTY JSON body (`{}`) — matching `receiver.py`'s actual catch-all behavior
      exactly (`receiver.py`'s `_ok()`/`do_POST` fallthrough) — a Cowork OTLP client may send
      log/trace exports this receiver doesn't need to store. A GET to any path other than
      `/healthz` returns 404, again matching `receiver.py`'s real `do_GET` behavior (do not
      invent a different convention for GET vs POST than the one the existing receiver uses).
- [ ] Its own request log, e.g. `data/cowork_receiver.log` (env-overridable, e.g.
      `COWORK_RECEIVER_LOG`) — never appends to `receiver.log`.
- [ ] Starting this server prints its own auth state banner (ENABLED/DISABLED) the same way
      `receiver.py` does, including the loud warning when unset.
- [ ] Append three new placeholder lines to `.env.example` (read it first — append only, don't
      reorder or rewrite existing content, don't remove the trailing newline convention it
      already uses): `COWORK_RECEIVER_AUTH_TOKEN`, `COWORK_DB`, `COWORK_RECEIVER_LOG`, each with
      a one-line comment analogous to the existing `RECEIVER_AUTH_TOKEN` entry's style. Never a
      real value — placeholder only, same discipline as the rest of `.env.example`.
- [ ] `serve()` / `main()` structured so tests can call the Handler's request-handling logic
      directly, **without binding a real network socket** — this repo's test suite has an
      established, load-bearing convention for exactly this (`tests/test_receiver.py`'s
      "In-process HTTP harness -- a connected socketpair, not a bound port" helper, and its
      explicit comment "real requirement: never bind a real port in a test"). Reuse that same
      `socket.socketpair()`-based pattern for this receiver's tests rather than inventing a
      second harness style or binding a real port — the latter is a real requirement of this
      test suite, not a style preference.

## Acceptance Criteria

1. `POST /v1/metrics` with a valid Cowork payload (per task 02's fixture) and the correct
   token returns 200 and the row appears in `CoworkStore` — verification: integration test
   using the `socket.socketpair()` in-process harness (mirroring `tests/test_receiver.py`),
   never a real bound port.
2. The same request with a missing/wrong token returns 401 when `COWORK_RECEIVER_AUTH_TOKEN`
   is set — verification: unit/integration test, same harness.
3. `--require-auth` with no token set refuses to start (raises/exits) — verification: unit
   test.
4. A payload with `service.name="claude-code"` (not cowork) posted to THIS receiver is
   rejected (0 rows stored) but still returns 200 with the rejection reflected in the response
   body — never a crash — verification: integration test, same harness.
5. `GET /healthz` with no token configured never includes `last_ingest_at` in its body —
   verification: unit test.
6. Starting this server never READS OR REFERENCES `RECEIVER_AUTH_TOKEN` (only
   `COWORK_RECEIVER_AUTH_TOKEN`), never opens `data/otel.db`, and never defaults to port `4318`
   — verification: test asserting the default `--db`/`--port`/env-var names used are the new,
   distinct ones, and a grep/AST check that the string `RECEIVER_AUTH_TOKEN` (as a distinct
   token, not a substring of `COWORK_RECEIVER_AUTH_TOKEN`) does not appear in
   `cowork_receiver.py`. A token set in `.env` as `COWORK_RECEIVER_AUTH_TOKEN=...` IS honored
   (loaded via `billing.config.load_env`) — verification: unit test using a temp `.env` file.
7. Every rejected record from a test payload produces a corresponding line in this receiver's
   own log file (not `receiver.log`), containing the rejection reason but no raw request
   bytes — verification: unit test reading the log file after a rejected POST.
8. `git diff -- billing/otel/receiver.py` is empty after this task — verification: command
   output.
9. No test in `tests/test_cowork_receiver.py` binds a real network socket (`socket.bind`,
   `HTTPServer(...).serve_forever()` against a real port, etc.) — verification: read the test
   file; every request goes through the socketpair harness.
10. A payload record that passes `cowork_ingest.py`'s own validation but fails at
    `CoworkStore.insert_datapoint` (simulate by injecting a value the store rejects, e.g. an
    unbindable type) is caught, produces a per-record rejection, and every OTHER valid record
    in the same batch still inserts — verification: unit test.
11. Simulating a `sqlite3.OperationalError` mid-commit (monkeypatch `store.commit` to raise)
    results in `store.db.rollback()` being called before the exception propagates, and no
    partial state is left committed — verification: unit test.
12. A 400 response's log line contains no substring of the raw request body beyond an error
    message and byte count — verification: unit test reading the log file.

## Files to Read

- `billing/otel/receiver.py` — the structural pattern to DUPLICATE, never import (see
  Requirements — `load_env()` import-time side effect): Handler class shape, `_read_body`,
  `_authorized`/`_unauthorized`, `_healthz`, `serve`/`main`. Read-only.
- `billing/otel/cowork_store.py`, `billing/otel/cowork_ingest.py`,
  `billing/otel/cowork_attribute.py` — the frozen contracts this task wires together.
- `README.md` §"1: Receiving telemetry data" and the "Config & secrets" section — the
  existing auth/token conventions this task deliberately parallels but does not share.
- `tests/test_receiver.py` — its `socket.socketpair()` in-process HTTP harness, which this
  task's own tests must reuse the same approach as (not the same code — a separate,
  analogous harness in the new test file).

## Files to Create / Change

- `billing/otel/cowork_receiver.py`
- `tests/test_cowork_receiver.py`
- `.env.example` — append-only, three new placeholder lines.

## Constraints

- Must: use a distinct port, env var, and log file from every value `receiver.py` uses.
- Must: single-connection SQLite discipline, no threading, matching the existing constraint.
- Must: test via `socket.socketpair()`, never a real bound port.
- Must: log every rejection (reason + minimal identifiers, no raw bytes) to this receiver's
  own log file.
- Must NOT: modify `billing/otel/receiver.py`.
- Must NOT: import `billing.otel.receiver`.
- Must NOT: default to the same port as the existing receiver (`4318`).
- Must NOT: add any dependency beyond the standard library.

## Verification

- Targeted test command: `python -m pytest tests/test_cowork_receiver.py -q`
