# Task 02: Wire payload contract, validation, and row mapping

## Objective

A new module `billing/otel/transcript.py` **defines the wire payload contract** for transcript usage,
validates an incoming batch against it, and maps each record into the store rows it becomes: up to four
`token_usage` rows plus one rate-derived `cost_usage` row. Pure and stdlib-only — no network, no
filesystem. This module is the contract owner for the payload; task 06's hook produces exactly what is
frozen here.

## Dependencies

- 00 (test scaffold), 01 (columns, insert signatures, transcript key composition)

```yaml
# --- task ownership contract ---
writes:
  - billing/otel/transcript.py
  - tests/test_transcript.py
reads:
  - billing/otel/otel_store.py
  - billing/otel/rating.py
  - billing/otel/normalize.py
  - billing/otel/bill.py
  - tests/conftest.py
depends_on:
  - "00-test-scaffold"
  - "01-store-schema"
owner: implementer
rewrite_semantics: whole-file
eval_depth: full
```

## Requirements (exhaustive — the evaluator verifies every item)

**The payload contract — freeze it here, in code**

- [ ] The module declares the wire payload schema explicitly (a documented constant plus the validator
      that enforces it), because THREE tasks depend on it: 02 validates it, 03 routes it, 06 produces it.
      A field named differently on either side means desktop rows land in `unknown` and never invoice.
- [ ] The record schema is exactly these fields, and the module documents each one:
      `session_id`, `ts`, `request_id`, `model`, `input_tokens`, `output_tokens`,
      `cache_read_input_tokens`, `cache_creation_input_tokens`, `repo_raw`, `entrypoint`,
      `query_source`, `user_email`, `user_id`, `org_id`.
- [ ] **`query_source` is a required field** carrying `main` or `subagent` — the value the hook derives
      from whether the record came from the main transcript or an `agent-*.jsonl` sidechain file. Both
      `insert_datapoint` and `insert_cost_datapoint` take `query_source` as a required keyword
      (`otel_store.py:151,166`) and `dp_key` includes it, so leaving it unspecified would be an
      unstated contract between this task and task 03. Validate it against the enum
      `otel_store.py:31` documents (`main | subagent | auxiliary`) and reject any other value
      per-record.
- [ ] **`cwd` is deliberately NOT in the schema.** The opt-in consent notice at
      `client-package/configure.py:109` and `client-package/INSTRUCTIONS.md:76` both state: "Not
      collected: your prompts, your code, file contents, or **file paths**." A desktop `cwd` is a file
      path (`C:\Users\...\AppData\Roaming\Claude\scratch-workspaces\...`), so transmitting it would make
      a consent notice shown to developers false. It is also unnecessary: `repo_raw` carries everything
      attribution needs, and no task defines a column to store `cwd` in. If a future change needs it,
      the consent notice must be revised first, in the same change.
- [ ] **`repo_raw` carries the raw git remote URL** resolved client-side, exactly as
      `claude-repo-tag.py` posts it today. The server normalizes it — the client never does. An empty
      string means "no remote", which is the scratch-workspace case and must be accepted, not rejected.
- [ ] The schema contains NO field capable of carrying message content. Adding one later requires
      revisiting the Phase 1 privacy decision.

**Validation**

- [ ] **Validation is PER RECORD, not all-or-nothing.** The validator partitions a batch into accepted
      records and rejected ones (each with a reason), and returns both. A batch is rejected outright
      only when the envelope itself is unusable — not a list, or larger than the maximum batch size.
      Rationale: task 06 drops a batch after its retry bound, so whole-batch rejection means a single
      malformed record silently discards up to a full batch of valid, billable records. One bad record
      must not cost a client's whole session.
- [ ] A batch whose envelope is unusable raises `ValueError`, so the receiver answers 400 through its
      existing path.
- [ ] Rejects any record whose `entrypoint` is not `claude-desktop`. Enforced **server-side as well as
      client-side** — the receiver must never trust the hook to have filtered.
- [ ] Rejects, as PER-RECORD rejections: a record missing `session_id`, `ts`, `request_id`, or `model`;
      token counts that are non-numeric or negative; an unknown field (fail closed, so a renamed field
      surfaces as a rejection instead of silently defaulting). Rejects the whole batch only for an
      unusable envelope: not a list, or over the size limit.
- [ ] **Rejects a record carrying a `cwd` field**, since `cwd` is deliberately absent from the schema
      and the unknown-field rule is fail-closed. This makes the consent guarantee enforceable at the
      server boundary rather than resting on the client behaving.
- [ ] Enforces a maximum batch size, exported as a module constant so task 06 can batch to it, and
      rejects anything larger — one client must not be able to stall the single-threaded receiver.

**Mapping**

- [ ] Maps one record to `token_usage` rows using the existing vocabulary exactly: `input`, `output`,
      `cacheRead`, `cacheCreation` — from `input_tokens`, `output_tokens`, `cache_read_input_tokens`,
      `cache_creation_input_tokens` respectively.
- [ ] Omits a token row whose count is zero or absent rather than writing a zero row.
- [ ] **Carries `user_email`, `user_id`, and `org_id` from the payload onto every emitted row.** The
      Phase 1 identity decision is only honored if identity survives ingest; a mapping that drops it
      leaves the lake CSVs' `user_email` grain empty for all desktop usage while every stated
      requirement still appears satisfied.
- [ ] Sets `usage_source='transcript'` and `entrypoint='claude-desktop'` on every token row, and
      `usage_source='transcript'`, `cost_source='rate_card'` on the cost row.
- [ ] Carries the record's `query_source` onto every emitted token and cost row unchanged, so a
      subagent's spend stays distinguishable from its parent's in the store.
- [ ] Derives the repo key by passing `repo_raw` through `normalize.py`; an empty `repo_raw` yields the
      same `unknown` key the rest of the system uses.
- [ ] Computes cost through `RatingService` at **raw, pre-markup** cost. `bill.py:96` derives its
      rate-card estimate as `rates.billed(...) / markup`; match that convention so desktop cost is never
      double-marked-up when `bill.py` later applies `base * markup`.
- [ ] **Expects exactly one record per API request.** Task 06 collapses cumulative streaming blocks
      client-side before sending. This module therefore treats each record as a complete request total
      and must NOT sum, merge, or otherwise combine records sharing a `request_id`. If two records in
      one batch share `(session_id, request_id)`, that is a client defect: reject the later one
      per-record rather than summing them, since summing cumulative snapshots over-bills by ~2.28x.
- [ ] Produces exactly one `cost_usage` row per record.
- [ ] Uses the transcript key composition frozen by task 01 — keyed on `request_id`, not on timestamp.
- [ ] Emits `ts` in the exact UTC-second string format the store uses for the `ts` column, so
      `attribute.py`'s lexicographic as-of join works. This is the `ts` COLUMN format and is unrelated
      to the transcript key, which no longer depends on time.
- [ ] Contains no network access, no file I/O, and no third-party import.
- [ ] Never reads, logs, or propagates message content.

## Acceptance Criteria

1. A well-formed single-record batch maps to exactly the expected token rows and one cost row, with
   correct types and counts — verification: unit test asserting the produced rows.
2. `entrypoint` of `cli` or `claude-vscode` is rejected — verification: unit test per value.
3. Zero `output_tokens` produces no `output` row — verification: unit test.
4. Envelope malformations (not a list, oversized batch) raise `ValueError`; record-level malformations
   (missing each required field, negative tokens, unknown field, a `cwd` field) are returned as
   per-record rejections while the valid records in the same batch are still accepted — verification:
   unit test per case, plus one mixed batch asserting the good records survive alongside a bad one.
4b. A batch containing two records sharing `(session_id, request_id)` accepts one and rejects the other
   rather than summing — verification: unit test asserting the accepted total is the single record's
   value, not the sum.
5. Computed cost equals `RatingService`'s raw pre-markup value for a known model — verification: unit
   test comparing directly against `RatingService`.
6. **Identity round-trips**: a payload carrying `user_email` / `user_id` / `org_id` produces rows whose
   corresponding fields hold those exact values — verification: unit test. Regression test for the
   identity-dropped-at-ingest gap.
6b. `query_source` round-trips onto every emitted row, `subagent` and `main` are both accepted, and any
   other value is rejected per-record — verification: unit test per case.
7. A record with `repo_raw=''` maps to the `unknown` repo key and is NOT rejected — verification: unit
   test. This is the scratch-workspace path and must survive ingest to reach the `desktop-scratch` bucket.
8. Two ssh/https spellings of one remote map to the same repo key — verification: unit test, proving
   normalization is server-side and double-billing by spelling is closed.
9. Emitted `ts` matches the store's `ts` column format — verification: unit test asserting the exact string shape.

## Files to Read

- `billing/otel/otel_store.py` — the frozen column contract and transcript key composition from task 01; the `ts` column format.
- `billing/otel/rating.py` — `RatingService.raw_cost` / `.billed`; `DEFAULT_RATE` catches unknown models such as `claude-opus-5`.
- `billing/otel/bill.py` line 96 — the `/markup` convention to match.
- `billing/otel/normalize.py` — canonical repo keying. Never re-implement it.
- `billing/otel/receiver.py` — how existing ingest functions signal bad input (`ValueError`/`KeyError` → 400).
- `deploy/claude-repo-tag.py` — how the raw remote is posted today; the payload mirrors that convention.
- `tests/conftest.py` — fixtures from task 00.
- `.claude/skills/test-ladder/SKILL.md`

## Files to Create / Change

- `billing/otel/transcript.py` — payload schema constant, validator, desktop-only enforcement, row mapping, rating, exported max batch size.
- `tests/test_transcript.py` — the nine acceptance criteria above.

## Constraints

- Must: reuse `RatingService` and `normalize.py`; never re-implement pricing or repo canonicalization.
- Must: raise `ValueError` on malformed input; fail closed on unknown fields.
- Must: stay pure — testable with no database, no network, no filesystem.
- Must NOT: add a third-party import; perform I/O; trust the client's filtering; write to the store.
- Must NOT: apply markup. `bill.py` owns markup; store raw cost.
- Must NOT: add any payload field capable of carrying message content.

## Verification

- Targeted test command: `python -m pytest tests/test_transcript.py -v`
