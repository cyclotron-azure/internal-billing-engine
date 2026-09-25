All 462 tests pass (full suite), no regressions, and `git diff` on `otel_store.py`/`attribute.py` is empty -- write fence respected.

**Model (self-reported)**: claude-sonnet-5

## Task Complete: 01-cowork-store-schema

### Requirements checklist
- [x] `CoworkStore` structurally independent of `OtelStore` (no shared base class/schema string) -- `billing/otel/cowork_store.py:110-118` defines its own `SCHEMA` string and class
- [x] `DEFAULT_COWORK_DB = os.environ.get("COWORK_DB", "./data/cowork.db")` -- distinct path/env var -- `billing/otel/cowork_store.py:31`
- [x] `cowork_token_usage`/`cowork_cost_usage` schema with documented columns, `repo`/`repo_raw` coalesced to `""` never `NULL`, no `session_repo_timeline`/`repo_name_map`/`invoices`/`fabric_outbox` -- `cowork_store.py:34-70`; verified by `test_schema_creates_both_tables_with_documented_columns` and `test_schema_has_no_otel_only_tables`
- [x] `insert_datapoint`/`insert_cost_datapoint` exact keyword-only signatures (no `usage_source`/`entrypoint`/`request_id`), return `True`/`False` on insert/dedupe -- `cowork_store.py:128-166`; verified by `test_insert_datapoint_dedupes_on_replay`, `test_insert_cost_datapoint_dedupes_on_replay`
- [x] `commit()`/`close()`, connection on public `self.db` -- `cowork_store.py:104,180-184`
- [x] `last_ingest_at() -> str | None` mirroring `OtelStore`'s query shape -- `cowork_store.py:168-177`; verified by `test_last_ingest_at_none_for_fresh_store`, `test_last_ingest_at_reflects_max_across_both_tables`
- [x] `dp_key` composition documented inline -- `cowork_store.py:87-99` (`cowork_dp_key`, sha256 of `cowork|session_id|model|token_type|query_source|time_unix_nano`)
- [x] `_connect_ro` seam + `resolve_repo` built on it, using `Path(path).resolve().as_uri() + "?mode=ro"` -- `cowork_attribute.py:59-79`; regression test with `#` in path -- `test_connect_ro_still_readonly_with_hash_in_path`
- [x] `otel_db_reachable` probes `SELECT 1 FROM session_repo_timeline LIMIT 1`, never bare `SELECT 1` -- `cowork_attribute.py:82-111`; verified by `test_otel_db_reachable_false_for_valid_db_without_timeline_table` (criterion 5d)
- [x] `resolve_repo` mirrors `attribute.py`'s `COALESCE(_AS_OF, _FIRST)` chain, `"timeline"`/`"absent"` two-bucket only, `"unknown"` repo on absent -- `cowork_attribute.py:114-165`
- [x] `resolve_repo` opens read-only, never raises, returns `("unknown","absent")` on missing file/bad query -- verified by `test_resolve_repo_against_nonexistent_db_returns_absent_without_raising`
- [x] `resolve_repo` takes `otel_db_path` param defaulting to `otel_store.DEFAULT_DB`'s value -- `cowork_attribute.py:26,139`
- [x] All SQL parameterized (`?` placeholders) in both new files
- [x] Docstrings state deliberate pipeline separation -- top of both new modules

### Files changed
- `billing/otel/cowork_store.py` -- new file, `CoworkStore` class
- `billing/otel/cowork_attribute.py` -- new file, `_connect_ro`/`resolve_repo`/`otel_db_reachable`
- `tests/test_cowork_store.py` -- new file, 8 tests
- `tests/test_cowork_attribute.py` -- new file, 10 tests

### Verification
- `python -m pytest tests/test_cowork_store.py tests/test_cowork_attribute.py -v` -> 18 passed
- `python -m pytest tests/ -q` -> 462 passed, no regressions
- `git diff -- billing/otel/otel_store.py billing/otel/attribute.py` -> empty (criterion 7)
- `git status --porcelain` -> confirms only the 4 fenced files were added by this task

### Notes for the evaluator
- Judgment call: for criterion 5b/5, wrote two separate `_connect_ro` write-attempt tests (INSERT and UPDATE) rather than one, for slightly broader coverage.
- Judgment call: `cowork_dp_key` is a wholly local implementation (not importing `otel_store.dp_key`) to satisfy "structurally independent... do not couple to it" as strictly as possible.
- Did not modify `tests/conftest.py` -- all needed fixtures already existed from task 00.

### Footprint
files_read: 5 (~55,000 chars)
commands_run: 2
