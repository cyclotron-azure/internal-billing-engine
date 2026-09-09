# Task 03: Receiver endpoint — POST /v1/transcript-usage

## Objective

`billing/otel/receiver.py` accepts `POST /v1/transcript-usage`: an authenticated, batched endpoint that
validates a payload through `billing/otel/transcript.py`, writes the resulting `token_usage` and
`cost_usage` rows **including identity**, and reports insert/duplicate counts — matching the two
existing endpoints for auth, transactions, and error codes.

## Dependencies

- 00 (fixtures), 01 (columns, insert signatures), 02 (payload contract, validation, mapping)

```yaml
# --- task ownership contract ---
writes:
  - billing/otel/receiver.py
  - tests/test_receiver.py
reads:
  - billing/otel/transcript.py
  - billing/otel/otel_store.py
  - tests/conftest.py
depends_on:
  - "00-test-scaffold"
  - "01-store-schema"
  - "02-transcript-payload"
owner: implementer
rewrite_semantics: targeted-insertion
eval_depth: full
```

## Requirements (exhaustive — the evaluator verifies every item)

- [ ] `POST /v1/transcript-usage` is routed in `do_POST` using the same `path.endswith(...)` convention
      as the existing endpoints.
- [ ] Authentication uses the **existing** `_authorized()` path — rejected with 401 before the body is
      read or parsed, exactly as today. Do not add a second auth mechanism.
- [ ] A malformed body returns 400 through the same `except (ValueError, KeyError)` shape.
- [ ] A valid batch inserts rows and returns 200 with a JSON body reporting inserted, duplicate, and
      **rejected** counts.
- [ ] **Per-record rejection, not all-or-nothing.** A batch mixing valid and invalid records inserts the
      valid ones and returns 200 with the invalid ones counted as rejected. Only an unusable envelope
      (not a list, oversized) returns 400. Rationale: the hook drops a batch after its retry bound, so
      whole-batch rejection means one malformed record silently discards a full batch of billable
      records.
- [ ] **A store `ValueError` must NOT escape the per-record loop.** Task 01 froze a contract where
      `insert_datapoint` / `insert_cost_datapoint` RAISE `ValueError` when `request_id` is missing on a
      non-OTLP call, or when `request_id` is passed on an OTLP call. Both are wiring-bug guards, and
      raising is deliberate — it converts a silent 90.5% under-bill into a loud failure. But an escaped
      raise inside your per-record loop would abort the whole batch and return 400, discarding the valid
      records alongside the bad one and violating AC 3b directly. Catch it per record, count it as a
      rejection with its reason, and continue.
      **Catch `ValueError` around BOTH `map_record` AND the store insert, per record — not only the
      store.** An earlier draft of this requirement claimed the store guard was "unreachable from client
      data because `transcript.py` rejects the record first". That claim was FALSE when written and is
      recorded here as a correction: task 02's validator did not parse `ts`, so a record with
      `ts="garbage"` passed validation and `map_record`'s `datetime.fromisoformat` raised instead. Task
      02 has since added `invalid_ts` per-record validation, which closes that specific hole — but do
      not rebuild this requirement on the assumption that validation is exhaustive. Any raise escaping
      your per-record loop reaches `receiver.py:261`/`:274`'s `except (ValueError, KeyError)` and
      returns **400 for the whole batch**; task 06 then retries, exhausts its bound, and drops a full
      batch of valid billable records. That is the batch-poisoning path per-record rejection exists to
      prevent, and it defeats AC 3b.
      Verified: `receiver.py:261` and `:274` already catch `(ValueError, KeyError)` and answer 400, so a
      raise lands on the existing 400 path rather than a 500 — the problem is the BLAST RADIUS, not the
      status code.
- [ ] The 200 body's reject entries identify records by `request_id` and reason — never by echoing
      record content.
- [ ] **Identity is persisted.** `user_email`, `user_id`, and `org_id` from each record are passed
      through to `insert_datapoint` / `insert_cost_datapoint`. Passing empty strings while the payload
      carried real values silently discards the Phase 1 identity decision and empties the lake CSVs'
      `user_email` grain for all desktop usage.
- [ ] **`query_source` is persisted**, carrying the record's `main` or `subagent` value through to both
      insert methods — it is a required keyword on each (`otel_store.py:151,166`) and is part of
      `dp_key`. Defaulting it to `main` for a sidechain record would both mislabel the row and collide
      its key with the parent's.
- [ ] Re-POSTing an identical batch inserts nothing and reports the records as duplicates.
- [ ] `store.commit()` is called once per request, not per row, matching the existing endpoints.
- [ ] The `serve()` startup banner lists the new endpoint alongside `/v1/metrics` and `/v1/session-repo`.
- [ ] Reuses the existing `_read_body` helper, so gzip and chunked bodies keep working.
- [ ] A record with a non-desktop `entrypoint` is rejected per-record and counted in the 200 response;
      it is never inserted. The desktop-only filter must hold server-side regardless of what the client
      sends.
- [ ] **The 400 log line for this endpoint contains no raw body bytes.** The existing malformed-payload
      log format echoes `first120={raw[:120]!r}`, which on this endpoint would write conversation-adjacent
      request content into `receiver.log` — directly contrary to the Phase 1 payload decision. This
      endpoint logs the error and counts/identifiers only. This is a deliberate, documented divergence
      from the other endpoints' format; note it in a comment so a future reader does not "restore
      consistency".
- [ ] No third-party import is added; the receiver stays single-threaded `HTTPServer` with one connection.

## Acceptance Criteria

1. An authenticated POST of a valid batch returns 200 and the expected rows exist — verification:
   in-process handler test against a `tmp_path` database.
2. An unauthenticated POST with `RECEIVER_AUTH_TOKEN` set returns 401 and writes nothing — verification:
   unit test asserting status and an empty store. Note `AUTH_TOKEN` is read at import
   (`receiver.py:52`), so the test must patch the module attribute rather than only the environment.
3. An unusable envelope (not a list, oversized) returns 400 and writes nothing — verification: unit test.
3b. A batch mixing one invalid record with several valid ones returns 200, inserts the valid records,
   and reports the invalid one as rejected — verification: unit test asserting both the response counts
   and the stored rows. Regression test for the batch-poisoning path.
4. Re-POSTing the same batch returns 200 with zero new inserts — verification: unit test asserting the
   row count is unchanged.
5. A record with `entrypoint='cli'` is rejected and not inserted — verification: unit test.
6. **Identity round-trips end to end**: a POSTed record's `user_email` / `user_id` / `org_id` are
   readable from the stored rows — verification: unit test querying the store after the POST.
6b. A batch containing one `query_source='main'` and one `query_source='subagent'` record for the same
   `session_id` stores both, with the values preserved and distinct `dp_key`s — verification: unit test.
   Regression test for subagent rows being mislabelled or key-colliding with their parent.
7. **The log line written after a malformed POST to this endpoint contains none of the request body's
   bytes** — verification: unit test capturing the log output and asserting a distinctive string seeded
   in the malformed body does not appear. Note `LOG_PATH` is read at import and defaults to the
   repo-relative `data/receiver.log`; the test must patch it as a module attribute pointing into
   `tmp_path`, or it will write into the repo.
8. The startup banner names `/v1/transcript-usage` — verification: unit test on the banner string.

## Files to Read

- `billing/otel/receiver.py` — `do_POST` routing, `_authorized`, `_unauthorized`, `_read_body`, `_log`,
  the `serve()` banner, `AUTH_TOKEN` at line 52, and the existing 400 log format this endpoint must diverge from.
- `billing/otel/transcript.py` — the validation/mapping API and payload contract from task 02.
- `billing/otel/otel_store.py` — insert signatures and `commit()` from task 01.
- `tests/conftest.py` — fixtures from task 00.
- `README.md` — "1: Receiving telemetry data"; the auth contract under "Config & secrets".
- `.claude/skills/test-ladder/SKILL.md`

## Files to Create / Change

- `billing/otel/receiver.py` — the route, an ingest function following the existing `ingest_*_payload`
  pattern, identity passthrough, a content-free 400 log path, and the updated banner.
- `tests/test_receiver.py` — the eight acceptance criteria above.

## Constraints

- Must: reuse `_authorized`, `_read_body`, and the existing 400/401 helpers.
- Must: follow the structure of `ingest_metrics_payload` / `ingest_session_repo_payload`.
- Must: keep the receiver single-threaded and single-connection — the SQLite constraint is architectural.
- Must NOT: add a third-party import; add a second auth mechanism; bypass `transcript.py` validation;
  log any request body bytes on this endpoint; accept a non-desktop record.
- Must NOT: modify `transcript.py` or `otel_store.py` — tasks 02 and 01 own them.

## Verification

- Targeted test command: `python -m pytest tests/test_receiver.py -v`
- Drive the handler in-process against a temporary database. Never bind a real port in a test.
