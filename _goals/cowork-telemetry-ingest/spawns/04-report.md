**Model (self-reported)**: claude-sonnet-5

## Test Task Complete

### Coverage map

| Unit under test | Tests written | Error/edge paths covered |
|---|---|---|
| `cowork_db_path` fixture | `test_cowork_db_path_is_under_tmp_path_and_distinct_from_other_db_fixtures` | under tmp_path, not pre-created, never `data/`, distinct from `tmp_db_path` |
| `seeded_otlp_db_path` reused as read-only-lookup fixture | `test_seeded_otlp_db_path_doubles_as_the_cowork_lookup_fixture` | same session_id carries timeline + token_usage + cost_usage rows |
| existing-otel.db schema == real `otel_store.SCHEMA` | `test_seeded_otlp_db_path_schema_matches_current_otel_store_schema_exactly` | compares `PRAGMA table_info` for every table against an independently-built fresh `OtelStore` |
| `build_cowork_metrics_payload` / `cowork_metrics_payload` fixture | `test_cowork_metrics_payload_attrs_and_datapoints_are_exact` | exact `_attrs()` dict, exact `asInt`/`asDouble` literals (AC3) |
| service.name parameterization | `test_cowork_payload_service_name_is_swappable` (parametrized: `"claude-code"`, `None`, unrecognized value) | present/absent/CLI-spelling/unrecognized |
| unrecognized metric name | `test_cowork_payload_unrecognized_metric_name_is_swappable` | swap leaves cost metric untouched |
| golden baseline file shape | `test_golden_baseline_file_is_non_empty_lf_only_and_has_all_three_pieces` | non-empty, LF-only, all 3 pieces present, 3x no-duplicate inserts (AC4/AC6) |
| golden baseline "cowork accepted as ordinary usage" | `test_golden_baseline_shows_cowork_payload_accepted_as_ordinary_usage` | all three service.name variants produce an identical result body |
| capture determinism | `test_golden_baseline_capture_is_deterministic_across_two_fresh_runs` | two fresh temp-dir runs byte-identical (AC5) |
| capture matches committed file | `test_golden_baseline_capture_matches_the_committed_file` | regenerated text == checked-in file, byte-for-byte |

### Verification

- Rung 1 (new): `python -m pytest tests/test_conftest.py -q` -> 33 passed (21 pre-existing + 12 new)
- Rung 2 (impacted, full `tests/`): `PYTHONUTF8=1 python -m pytest tests/ -q` -> 444 passed, run twice, plus in both file orderings to confirm no cross-test monkeypatch leakage remains.
- Baseline determinism verified independently at the process level (two separate Python invocations, two separate temp dirs): both captures byte-identical to each other and to the committed `tests/golden/cowork_isolation_baseline.txt`.
- Confirmed byte-level: no `\r\n` in either new golden file.
- Confirmed `git status --porcelain billing/ deploy/ client-package/` is empty -- no production file touched.

### Files changed

- `tests/conftest.py` -- added (targeted-insertion, nothing removed): `cowork_db_path` fixture, `COWORK_LOOKUP_SESSION_ID` (re-export of `SEEDED_SESSIONS[0]`), `build_cowork_metrics_payload()` + `cowork_metrics_payload` fixture, and `capture_cowork_isolation_baseline()` (exposed at module level for task 05's reuse) plus its `_FakeAnalyticsClient` mock and `_format_ingest_result` helper.
- `tests/test_conftest.py` -- added the 10 tests listed above.
- `tests/golden/cowork_isolation_baseline.txt` -- new golden file (4694 bytes, LF-only).
- `tests/golden/cowork_isolation_README.md` -- new, mirrors `tests/golden/README.md`'s structure.
- `.gitattributes` -- NOT modified: `tests/golden/** -text` already covers both new files (confirmed via `git check-attr`).

### Judgment calls

1. Reused `seeded_otlp_db_path` as the "read-only-lookup fixture" rather than building a parallel one -- `SEEDED_SESSIONS[0]` ("sess-otlp-001") already carries a timeline row and matching token/cost rows for the same session_id, satisfying the requirement exactly.
2. `capture_cowork_isolation_baseline` lives in `conftest.py`, not only inside `test_conftest.py`, so task 05 can `from tests.conftest import capture_cowork_isolation_baseline` and re-run the identical capture for its replay comparison without duplicating ~80 lines of logic. Justified by the existing precedent of `seed_otlp_rows` (a plain function, not a fixture) already living in conftest.py for the same reason.
3. Mocked `AnalyticsClient` by patching `billing.reconcile.AnalyticsClient` (the name bound in reconcile.py's own namespace via `from .analytics_client import AnalyticsClient`), not `billing.analytics_client.AnalyticsClient` itself.
4. Found and fixed a real bug during verification: an early draft of the determinism test created two `pytest.MonkeyPatch()` instances and called `.undo()` on both only at the end, leaking a fake `AnalyticsClient`/`_now` into later tests and breaking 6 unrelated tests in `tests/test_reconcile.py`. Fixed by fully creating-and-undoing each `MonkeyPatch` before starting the next capture. Caught by running the FULL `tests/` suite, not just the new file.
5. Also fixed: `Path.read_text()` doesn't accept `newline=` on Python 3.12 -- switched to `open(path, newline="")`; and `sqlite3.Row` vs tuple comparison normalized via `tuple(row)`.

### Footprint
files_read: 14 (~90,000 chars)
commands_run: 11
