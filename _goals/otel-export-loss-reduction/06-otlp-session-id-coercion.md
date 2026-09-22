# Task 06: coerce OTLP `session.id` to `str` at ingest

## Objective

The OTLP write path stores `session_id` as a `str` in every case, so the spelling SQLite
persists can no longer differ from the spelling the OTLP-exclusion guard builds. This
closes the last surviving instance of the normalization-asymmetry class that cost task 03
two fix cycles — this time entered from the `/v1/metrics` end rather than the transcript
end.

**Runs before task 05**, despite the filename prefix. `depends_on` is authoritative.

## Dependencies

- `03-receiver-health-and-cli-ingest` (this modifies what task 03 landed, and task 03's
  evaluator produced the reproduction below)

```yaml
# --- task ownership contract ---
writes:
  - billing/otel/receiver.py
reads:
  - billing/otel/otel_store.py       # dp_key's interpolation form
depends_on:
  - "03-receiver-health-and-cli-ingest"
owner: implementer
rewrite_semantics: targeted-insertion
eval_depth: full
# full: this edits the /v1/metrics ingest path, which every OTLP row in the billing
# database flows through, and the value being changed is an input to dp_key.
```

## Background — the reproduction, measured

Task 03's evaluator drove real OTLP `ExportMetricsServiceRequest` payloads through
`ingest_metrics_payload`, varying only which OTLP value wrapper carried `session.id`, then
posted a `cli` transcript record for the **same session** with a valid `str` id.
`_attr_value` (`receiver.py:164`) returns `str | int | float | bool | None` depending on the
wrapper, and `_common` (`:190`) binds the result straight into a TEXT column — so SQLite,
not Python, chooses the stored spelling:

| OTLP wrapper | SQLite stores | transcript `str` id | guard |
|---|---|---|---|
| `stringValue` UUID **(the real case)** | `'019a2f3c-…'` | same | excluded ✅ |
| `stringValue` padded | `' sess-pad '` | same | excluded ✅ |
| `intValue "123"` | `'123'` | `'123'` | excluded ✅ |
| absent / unknown wrapper | `'unknown'` | `'unknown'` | excluded ✅ |
| `intValue "0123"` | `'123'` | `'0123'` | **double-billed** |
| `intValue "+123"` | `'123'` | `'+123'` | **double-billed** |
| `doubleValue 1e20` | `'1.0e+20'` | `'1e+20'` | **double-billed** |
| `doubleValue 42.0` | `'42.0'` | `'42'` | **double-billed** |
| `boolValue true` | `'1'` | `'True'` | **double-billed** |

Five reproduced double-bills, all `(1,0) → (5,1)`.

**Reachability, stated honestly.** Every failing row needs `session.id` encoded in a
numeric or boolean wrapper. Claude Code session ids are UUIDs, which cannot be
`intValue`/`doubleValue`/`boolValue`, so this is **unreachable in production today**. It is
being fixed because the receiver accepts payloads from the network, the exporter's encoding
is not under our control, and the same class has now produced three separate defects.

## The `dp_key` question, already settled

The evaluator flagged a possible `dp_key` backfill as the reason this needed its own task.
It does not apply. `dp_key` interpolates with an f-string, which is `str()`:

```python
raw = f"{session_id}|{model}|{token_type}|{query_source}|{time_unix_nano}"
```

Measured: `dp_key(raw) == dp_key(str(v))` for `True`, `1e20`, `123`, `42.0` and `'sess'` —
**identical in every case**. So coercing at `_common` changes **no** `dp_key`, creates no
duplicate rows, re-bills no history, and needs no backfill. The stored column merely starts
agreeing with the spelling `dp_key` has always hashed. This is a consistency repair.

## Requirements (exhaustive — the evaluator verifies every item)

- [ ] `_common` coerces the session id to `str` **after** the existing
      `or "unknown"` fallback, so the fallback's falsy semantics are untouched. The
      resulting value is a `str` in every code path.
- [ ] **Coerce, do not reject.** Unlike the transcript path — where task 03 rejects a
      non-`str` `session_id` because a rejected record is simply not billed — an OTLP
      datapoint carries real usage that must still be recorded. Dropping it would convert a
      double-billing bug into a data-loss bug.
- [ ] Do **not** attempt to reproduce SQLite's TEXT-affinity conversion rules in Python.
      The point is to stop *two* conversions existing, not to add a third.
- [ ] `dp_key`, `transcript_key`, `SCHEMA`, `_migrate`, and everything in `otel_store.py`
      are untouched. `otel_store.py` is not in the fence.
- [ ] No other field's handling changes. `repo`, `repo_raw`, `user_email`, `user_id`,
      `org_id`, `model`, `query_source`, `type` and `time_unix_nano` keep their current
      treatment exactly, including `user_email={"a":1}` still reaching
      `_RECORD_DATA_ERRORS` as `store_error:ProgrammingError` — there is a pre-existing test
      pinning that and it must keep passing.
- [ ] `/v1/session-repo`, `/v1/transcript-usage`, `GET /healthz`, the 404 and 503 paths, and
      the `do_POST` dispatch are unmodified.
- [ ] **State BOTH residuals in a comment.** (i) This fix prevents *future* mis-spelled
      rows; any row already stored under a non-`str`-derived spelling keeps it. (ii) It
      closes only the divergences SQLite caused. Three of the five reproduced cases --
      `intValue "0123"`, `intValue "+123"`, `doubleValue 42.0` -- survive, because
      `_attr_value`'s `int()`/float parse discards the original spelling before SQLite
      sees it. Name that root cause explicitly so nobody reads this fix as complete.
      For (i): none are expected in production (UUIDs) and a backfill is deliberately out
      of scope, but the comment must say so rather than imply the fix is retroactive.
- [ ] **Added after Phase 5 final audit — the fifth double-billing path.** The
      `or "unknown"` fallback conflates "attribute truly absent" with "attribute present
      but falsy". `_attr_value` can legitimately return `0`, `False`, `0.0` or `""` for a
      real (if degenerate) `session.id` -- Python's `or` treats all of those as missing and
      collapses them into the single shared key `'unknown'`. Measured: a `cli` transcript
      record for session `'0'` is accepted even though an OTLP row for that same session
      already exists, because the OTLP row was mis-filed under `'unknown'` and the guard
      never finds it -- `(1,0) -> (3,1)`, double-billed. Fix: distinguish `None` (the
      attribute is genuinely absent, or `_attr_value` couldn't parse it) from any other
      falsy value. Only `None` maps to `"unknown"`; `0`, `False`, `0.0` and `""` keep their
      own `str()` spelling. Compute the raw value once (`a.get("session.id")`) into a local
      before the `return` dict, rather than calling `.get` twice inside the dict literal.
      **The genuinely-absent case is unaffected and is not a defect**: multiple truly
      attribute-less datapoints still share `'unknown'`, and that residual is the same
      class as the goal's other accepted residual -- partially-lost sessions have no safe
      unit of comparison. Do not try to give every anonymous datapoint a unique key; that
      is a much larger change and out of scope here.
- [ ] Standard library only.

## Acceptance Criteria

1. **The two cases coercion actually fixes** now exclude correctly: `doubleValue 1e20`
   (stored `'1.0e+20'` -> `'1e+20'`) and `boolValue true` (stored `'1'` -> `'True'`). For
   each, an OTLP datapoint then a `cli` transcript record for the same session -> rejected
   `session_has_otlp`, with `SELECT COUNT(*)` over **both** `token_usage` and `cost_usage`
   unchanged. Drive real OTLP JSON payloads, not Python-constructed dicts.
   **Criterion corrected by the orchestrator after implementation.** The original wording
   claimed all five reproduced cases would be fixed. That was wrong, measured:

   | wrapper | stored after fix | transcript id | match |
   |---|---|---|---|
   | `doubleValue 1e20` | `'1e+20'` | `'1e+20'` | yes |
   | `boolValue true` | `'True'` | `'True'` | yes |
   | `intValue "0123"` | `'123'` | `'0123'` | **no** |
   | `intValue "+123"` | `'123'` | `'+123'` | **no** |
   | `doubleValue 42.0` | `'42.0'` | `'42'` | **no** |

   **A fourth, unrelated-to-SQLite defect was found by the Phase 5 audit and closed in a follow-up fix cycle** -- see criterion 11.

   The three that remain have a **different root cause**, and they are not all the same
   root cause either:

   - The two `intValue` cases lose their spelling in `_attr_value`, which does
     `int(v["intValue"])` -- `'0123'` becomes `123` in **Python**, before SQLite is
     involved. Closing them would mean returning the raw string from `_attr_value`,
     which changes that function for every attribute and is out of scope here.
   - **`doubleValue 42.0` cannot be closed by changing `_attr_value` at all.** Verified:
     `json.loads` has already turned the wire text into a Python `float` before
     `_attr_value` runs, and `_attr_value` returns it untouched. Recovering `'42'` would
     need `json.loads(..., parse_float=str)` at the body-parse site, which would change
     `asDouble` cost values and `timeUnixNano` globally. Arguably it is not a defect at
     all: if the producer sent the number `42.0`, `'42.0'` is the faithful spelling and
     a transcript claiming `'42'` is asserting a different id.

   Corrected by the orchestrator after task 06's evaluation, which established the
   `json.loads` point -- the original note credited `_attr_value` for all three --
   verification: integration test
2. The four already-correct wrappers stay correct: `stringValue` UUID, `stringValue`
   padded, `intValue "123"`, and the absent/unknown case — verification: integration test
3. `typeof(session_id)` is `'text'` and the stored value equals `str(<python value>)` for
   each of the nine wrappers in the table — verification: integration test
4. **`dp_key` is unchanged by the coercion.** For a datapoint whose `session.id` arrives as
   `boolValue true`, the `dp_key` written after the fix equals the `dp_key` written before
   it. Assert the literal key, and assert that re-ingesting the same datapoint twice still
   yields exactly one row (the dedupe path is intact) — verification: unit test
5. An ordinary `stringValue` UUID session's stored `session_id` is **byte-identical** to
   the pre-fix value — the coercion is a no-op on the real case — verification: unit test
6. A datapoint with no `session.id` attribute still stores `'unknown'`, and one whose
   `session.id` is falsy (`0`, `false`, `""`) also stores `'unknown'` — the `or` fallback's
   behavior is unchanged — verification: unit test
7. `user_email={"a":1}` still produces `store_error:ProgrammingError`. **Corrected by the
   orchestrator:** the original wording said "the pre-existing test asserting it still
   passes unmodified", but no test under `tests/` covers this case -- the only test
   asserting that reason string is `test_receiver.py:532`, which is about `session_id`
   and is one of the known reds owned by task 05. So this criterion needs a **new**
   test, which task 05 writes as it does for every criterion -- verification: unit test
8. The targeted five-file selection is **8 failed, 166 passed** (orchestrator-measured
   after task 04's fix cycle 1; the earlier "6 failed, 168 passed" in this criterion was
   stale because tasks 04 and 06 ran concurrently against a shared suite). The eight,
   all owned by task 05: `test_receiver.py::test_non_desktop_entrypoint_is_rejected`,
   `::test_wrong_typed_session_id_field_is_rejected_not_escaped`,
   `test_transcript.py::test_ac2_non_desktop_entrypoint_rejected[cli]`,
   `[claude-vscode]`,
   `::test_rejection_index_is_original_batch_position_in_larger_mixed_batch`,
   `test_transcript_hook.py::test_ac1_only_desktop_entrypoint_ships`,
   `::test_ac6_running_twice_ships_each_record_once`, and
   `test_integration_desktop.py::test_systemic_alarm_silent_for_pure_validation_rejections`.
   A ninth is a finding to report, not to fix -- verification: command output
9. `git diff billing/otel/receiver.py` for this task shows a change confined to `_common`
   plus comments; `do_POST`, `_authorized`, `_presented_token`, `_read_body`, `_attr_value`,
   `_attrs`, `ingest_session_repo_payload`, `ingest_transcript_usage_payload` and the
   `/healthz` handler are byte-identical to their state at the end of task 03 —
   verification: command output
10. **The None-vs-falsy fix, added after Phase 5.** For `intValue "0"`, `boolValue false`,
    and `doubleValue 0.0`: the OTLP row stores `'0'`, `'False'`, `'0.0'` respectively (not
    `'unknown'`). A `cli` transcript record posted for that same string id is then
    correctly excluded (`session_has_otlp`), with `SELECT COUNT(*)` over both tables
    unchanged. Drive real OTLP JSON payloads -- verification: integration test
11. **The genuinely-absent case is unchanged.** An OTLP datapoint with no `session.id`
    attribute at all still stores `'unknown'`, exactly as before. This is the assertion
    that fails if someone "fixes" the residual by inventing a per-datapoint unique
    placeholder -- verification: unit test

12. **Added after Phase 5 cycle-2 audit -- the sixth double-billing path, merge-level.**
    An OTLP resource carries a real UUID `session.id`; the same datapoint's own
    `session.id` attribute uses an unrecognized wrapper (`arrayValue`, `kvlistValue`,
    `bytesValue`, or an empty `{}`) -- `_attr_value` returns `None` for these. Before this
    fix, `_common`'s `a.update(_attrs(...))` let that `None` clobber the valid
    resource-level value (`dict.update` cannot distinguish "key absent" from "key present
    with value None"), storing `'unknown'` for a session that had a perfectly good real
    id -- more dangerous than criteria 10/11's falsy-scalar case because it hits the
    goal's own "real case" (a genuine UUID session), not a contrived edge value. Fixed by
    filtering `None`-valued datapoint attributes out of the merge before it overwrites
    anything, closing this for every field the function merges, not only `session_id`.
    Verify end-to-end through the real ingest path (not by calling `_common` with
    hand-built dicts alone): an OTLP metrics POST with a resource-level UUID and a
    datapoint-level unparseable `session.id` wrapper stores the resource UUID, not
    `'unknown'`; a subsequent `cli` transcript record for that same UUID is then rejected
    `session_has_otlp` with row counts over both tables unchanged -- verification:
    integration test

13. **Added after Phase 5 cycle-3 audit -- the seventh instance, one level upstream of
    criterion 12's fix.** `_attrs` collapses duplicate attribute keys within a single
    attribute list last-wins (it's a plain dict comprehension). If a `session.id` key
    appears twice in one list and the second occurrence uses an unrecognized wrapper,
    `_attrs` hands back `{"session.id": None}` **before** `_common`'s merge-level filter
    (criterion 12) ever runs -- so the filter can't help, because by the time `_common`
    sees it, there was never a valid value to protect. Reproduced identically to criterion
    12: a real UUID `session.id` followed in the same list by any of
    `arrayValue`/`kvlistValue`/`bytesValue`/`{}` for the same key collapses to `'unknown'`,
    `(1,0) -> (5,1)` double-billed. Fixed at the true producer: `_attrs` itself drops a key
    whose parsed value is `None` rather than ever returning it, so no downstream consumer
    -- not `_common`'s merge, not any future caller -- can receive a spurious `None` for an
    attribute that had *any* valid occurrence in the same list. This is what makes the fix
    convergent rather than another instance of the pattern: the guard now lives at the one
    place values are produced, not at each place they're consumed. `_common`'s existing
    merge-level filter (criterion 12) may be simplified once this lands, or kept as
    defense-in-depth -- implementer's call, documented either way -- verification:
    integration test

## Files to Read

- `billing/otel/receiver.py` — `_attr_value` (`:164`), `_common` (`:190`),
  `ingest_metrics_payload`, and `_RECORD_DATA_ERRORS` (`:268-283`)
- `billing/otel/otel_store.py` — `dp_key`'s interpolation form; `insert_datapoint`'s
  binding (read-only)
- `tests/test_receiver.py` — the `user_email={"a":1}` test that must keep passing
  (read-only; task 05 owns test edits)

## Files to Create / Change

- `billing/otel/receiver.py` — the coercion in `_common`, plus the residual comment

## Constraints

- Must: coerce after the `or "unknown"` fallback.
- Must NOT: touch `otel_store.py`, `transcript.py`, or anything under `tests/`.
- Must NOT: change `dp_key`, the schema, or any other field's handling.
- Must NOT: add a backfill, a migration, or a one-time repair pass. The residual is
  documented, not fixed.
- Must NOT: reject or drop an OTLP datapoint.

## Verification

- `python -m pytest tests/test_receiver.py tests/test_transcript.py tests/test_transcript_hook.py tests/test_integration_desktop.py tests/test_otel_store.py -q`
  -> expect 6 failed, 168 passed; report the names
- Capture verbatim: the nine-wrapper stored-value table, and the before/after `dp_key` for
  the `boolValue true` case.
