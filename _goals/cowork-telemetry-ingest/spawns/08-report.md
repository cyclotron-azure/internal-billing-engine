Fix cycle 1 for task 01. All 6 coordinator items addressed:

1. F-string SQL removed from cowork_attribute.py -- _AS_OF_SQL/_FIRST_SQL/_TABLE_PROBE_SQL now
   plain literals; TIMELINE_TABLE kept as documentation-only constant.
2. As-of isolation tests added (test_cowork_attribute.py:79-142) using a real multi-entry
   timeline via OtelStore.insert_session_repo. Implementer verified by hand: removing the
   as-of query or flipping its sort both break 2 of the 3 new tests.
3. Write-fail tests tightened to pytest.raises(sqlite3.OperationalError, match="readonly"),
   plus a stray-file-absence assertion on the #-path test. Implementer verified: re-injecting
   the naive f-string URI makes the #-path test fail with the exact "no such table" mismatch.
4. Two new last_ingest_at cross-table tests added (token-only, token-newer-than-cost).
5. _connect_ro callers widened to catch (sqlite3.Error, ValueError, OSError); NUL-byte-path
   tests added for both otel_db_reachable and resolve_repo.
6. Line-number citations re-verified live via grep before this report was written.

python -m pytest tests/test_cowork_store.py tests/test_cowork_attribute.py -v -> 25 passed
python -m pytest tests/ -q (full suite) -> 469 passed, no regressions
git diff -- billing/otel/otel_store.py billing/otel/attribute.py -> empty

Full corrected report in the completion notification for the resumed implementer
(a761198d09f100016).
