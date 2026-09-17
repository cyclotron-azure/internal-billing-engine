MODEL: claude-sonnet-5
STATUS: completed

## Signatures (verbatim)
```
def last_ingest_at(self, usage_source: str | None = None) -> str | None:
def sessions_with_otlp_rows(self, session_ids) -> set:
OTLP_MEMBERSHIP_CHUNK_SIZE = 500   # module-level constant
```

## SQL (verbatim)

last_ingest_at (usage_source=None):
```sql
SELECT MAX(m) AS m FROM (
    SELECT MAX(ingested_at) AS m FROM token_usage
    UNION ALL
    SELECT MAX(ingested_at) AS m FROM cost_usage
)
```

last_ingest_at (usage_source given):
```sql
SELECT MAX(m) AS m FROM (
    SELECT MAX(ingested_at) AS m FROM token_usage WHERE usage_source = ?
    UNION ALL
    SELECT MAX(ingested_at) AS m FROM cost_usage WHERE usage_source = ?
)
```

sessions_with_otlp_rows (per chunk):
```sql
WITH ids(x) AS (VALUES (?),(?),...)
SELECT session_id FROM token_usage
  WHERE usage_source = ? AND session_id IN (SELECT x FROM ids)
UNION
SELECT session_id FROM cost_usage
  WHERE usage_source = ? AND session_id IN (SELECT x FROM ids)
-- params = chunk_ids + ["otlp", "otlp"]
```

## Parameter arithmetic
500 ids_per_chunk x 1 arm_binding_them (single VALUES CTE, referenced by both arms via
`IN (SELECT x FROM ids)`) + 2 literal_binds (usage_source bound once per arm) = **502**
<= 999.
Reverted-to-two-IN-lists case: 498 x 2 + 2 = 998 <= 999; 499 x 2 + 2 = 1000 > 999.

## Requirements
- **last_ingest_at**: spans token_usage + cost_usage via UNION ALL / MAX(MAX()), reads
  `ingested_at` (never `ts`), filters `usage_source` exactly with no normalization when
  given, returns None (not "", 0, or a sentinel) when no row matches, uses `self.db` only,
  issues no writes. Verified by tests/test_otel_store.py (27 passed) plus manual reasoning
  against criteria 1-4, 14.
- **sessions_with_otlp_rows**: covers token_usage OR cost_usage in one statement per chunk
  via a single-bind VALUES CTE; empty/falsy input short-circuits before any query; dedupes
  input before chunking; chunks at 500; binds every id as `?`; filters
  `usage_source='otlp'` only (no entrypoint predicate); never swallows sqlite3.Error; no
  caching. Verified against criteria 5-13, 15 via manual scratchpad script (500-id chunk
  under setlimit(999), and the cost_usage-only C1 case) -- both passed.
- **Both**: standard library only (no new imports added -- module already imports
  hashlib/os/sqlite3/datetime); neither method touches the `repo` column; all frozen
  symbols (dp_key, transcript_key, SCHEMA, _migrate, insert_datapoint,
  insert_cost_datapoint, dedupe_drops counter) byte-unmodified per git diff below;
  docstrings state the ingested_at-vs-ts distinction, the IN() hazard, and the
  parameter-cap arithmetic.

## Verification
- `python -m pytest tests/test_otel_store.py -q` -> **27 passed in 1.77s** -- unchanged
  from before (task 05 will add tests for these two methods; this count reflects the
  existing suite only, undisturbed).
- `git diff --stat billing/otel/otel_store.py` -> **1 file changed, 163 insertions(+)** --
  0 deletions.
- Manual 999-cap check (scratchpad, temp DB, never data/): built a temp OtelStore, called
  `store.db.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)`, inserted an
  `insert_cost_datapoint(..., usage_source="otlp")` row for one of 500 session ids with NO
  corresponding token_usage row (the partial-flush / C1 scenario), then called
  `sessions_with_otlp_rows` over all 500 ids. Result: `{'sess-3'}` -- the cost-only session
  was found, no OperationalError, chunk succeeded in one statement.

## Anything you could not satisfy
None.

### Footprint
files_read: 3 (~35000 chars)
