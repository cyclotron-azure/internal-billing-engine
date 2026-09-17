"""SQLite store for OTEL-ingested Claude Code token usage + optional repo-name map.

Claude Code exports token metrics with DELTA temporality by default: each data
point is an increment. To accumulate correctly and stay idempotent across
re-sends, we store one row per data point keyed by a dp_key that includes the
data point's timestamp; INSERT OR IGNORE dedupes identical points. Billing then
just SUMs `tokens` over rows.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timezone

DEFAULT_DB = os.environ.get("OTEL_DB", "./data/otel.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS token_usage (
  dp_key TEXT PRIMARY KEY,          -- dedupe key (dims + timestamp)
  ts TEXT,                          -- data point time (UTC)
  session_id TEXT,
  repo TEXT,                        -- normalized repo key (attribution unit)
  repo_raw TEXT,                    -- original OTEL_RESOURCE_ATTRIBUTES repo value
  user_email TEXT,
  user_id TEXT,
  org_id TEXT,
  model TEXT,
  token_type TEXT,                  -- input | output | cacheRead | cacheCreation
  query_source TEXT,                -- main | subagent | auxiliary
  tokens INTEGER,
  ingested_at TEXT,
  usage_source TEXT NOT NULL DEFAULT 'otlp',  -- 'otlp' | 'transcript' (desktop-sourced)
  entrypoint TEXT                   -- claude-desktop | cli | claude-vscode | ... (transcript rows only)
);
CREATE INDEX IF NOT EXISTS ix_token_repo ON token_usage(repo);

CREATE TABLE IF NOT EXISTS cost_usage (
  dp_key TEXT PRIMARY KEY,          -- dedupe key (dims + timestamp)
  ts TEXT,
  session_id TEXT,
  repo TEXT,
  repo_raw TEXT,
  user_email TEXT,
  user_id TEXT,
  org_id TEXT,
  model TEXT,
  query_source TEXT,
  cost_usd REAL,                    -- Anthropic's actual USD for this datapoint
  ingested_at TEXT,
  usage_source TEXT NOT NULL DEFAULT 'otlp',  -- 'otlp' | 'transcript'. MANDATORY here,
                                    -- not just on token_usage: attribute.py's
                                    -- resolved_view() is applied to cost_usage at
                                    -- bill.py:57 and export.py:78, and task 04 adds an
                                    -- attribution_source branch that references
                                    -- usage_source -- omitting it here would make that
                                    -- SQL fail to prepare and kill bill.py / the lake
                                    -- export outright for the existing OTLP-only fleet.
  cost_source TEXT NOT NULL DEFAULT 'actual'  -- 'actual' (OTLP claude_code.cost.usage) |
                                    -- 'rate_card' (desktop transcripts carry no cost
                                    -- metric, so a rate-card estimate stands in)
);
CREATE INDEX IF NOT EXISTS ix_cost_repo ON cost_usage(repo);

CREATE TABLE IF NOT EXISTS session_repo_timeline (
  session_id TEXT,                  -- joins to token_usage.session_id / cost_usage.session_id
  ts TEXT,                          -- UTC second when this repo became active
                                    -- (SAME format as token_usage.ts so the
                                    --  as-of join can compare lexicographically)
  seq INTEGER,                      -- ms-within-second, orders events inside one second
  repo TEXT,                        -- normalized repo key ('unknown' if no remote)
  repo_raw TEXT,                    -- original git remote URL
  cwd TEXT,                         -- working directory that produced it
  event TEXT,                       -- SessionStart | CwdChanged | DirectoryAdded | SessionEnd
  ingested_at TEXT,
  PRIMARY KEY (session_id, ts, seq, repo)   -- a byte-identical replay of one
                                            -- POST is a no-op; separate hook
                                            -- firings carry distinct seq and
                                            -- are kept as separate entries
);
CREATE INDEX IF NOT EXISTS ix_timeline_session ON session_repo_timeline(session_id, ts);

CREATE TABLE IF NOT EXISTS repo_name_map (
  repo TEXT PRIMARY KEY,            -- normalized repo key
  bill_name TEXT,                   -- OPTIONAL override billing name
                                    -- (defaults to the short repo name if absent)
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS invoices (
  invoice_number TEXT PRIMARY KEY,
  bill_name TEXT,                  -- billing entity: the repo name (or its override)
  period_start TEXT,
  period_end TEXT,
  currency TEXT,
  actual_cost REAL,                -- summed claude_code.cost.usage for the period
  markup REAL,
  total_billed REAL,               -- actual_cost * markup
  tokens INTEGER,
  status TEXT,                     -- draft | issued
  generated_at TEXT
);
CREATE TABLE IF NOT EXISTS invoice_line_items (
  invoice_number TEXT,
  repo TEXT,
  model TEXT,
  tokens INTEGER,
  actual_cost REAL,
  billed_amount REAL
);
CREATE INDEX IF NOT EXISTS ix_lineitem_inv ON invoice_line_items(invoice_number);

-- Durable outbox for asynchronous delivery of invoice CSVs to Fabric OneLake.
-- invoice.py enqueues a 'pending' row per file; billing.otel.fabric_sync ships
-- it with retry/backoff and flips it to 'sent'. Nothing is lost on a crash.
CREATE TABLE IF NOT EXISTS fabric_outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT,                       -- 'summary' | 'line_items'
  period_start TEXT,
  period_end TEXT,
  local_path TEXT,                 -- source CSV on disk
  onelake_path TEXT,               -- destination path under the Lakehouse's Files/
  table_name TEXT,                 -- optional Delta table to load into ('' = files only)
  status TEXT,                     -- pending | sent | failed
  attempts INTEGER DEFAULT 0,
  next_attempt_at TEXT,            -- earliest UTC time to (re)try
  last_error TEXT,
  enqueued_at TEXT,
  sent_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_outbox_status ON fabric_outbox(status, next_attempt_at);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

-- Per-(day, token_type, usage_source) count of datapoints rejected as
-- duplicates by INSERT OR IGNORE in insert_datapoint / insert_cost_datapoint.
-- `day` is derived from the DROPPED datapoint's own timestamp (never
-- wall-clock now) so a replayed old export counts against the day it
-- describes -- the same day reconcile.py queries for. Cost-row drops use the
-- literal token_type sentinel '__cost__', matching dp_key's existing cost
-- sentinel. See DEDUPE_EPOCH_META_KEY below for the companion counting-start
-- epoch that says whether a window's absence of rows here is real or just
-- never measured.
CREATE TABLE IF NOT EXISTS dedupe_drops (
  day TEXT NOT NULL,            -- UTC YYYY-MM-DD, from the dropped datapoint's own ts
  token_type TEXT NOT NULL,     -- input|output|cacheRead|cacheCreation|__cost__
  usage_source TEXT NOT NULL,   -- 'otlp' | 'transcript'
  drops INTEGER NOT NULL DEFAULT 0,
  first_seen TEXT,              -- UTC ISO8601 when this bucket's first drop was counted
  last_seen TEXT,                -- UTC ISO8601 when its most recent drop was counted
  PRIMARY KEY (day, token_type, usage_source)
);
"""

# meta key holding the UTC ISO8601 timestamp of the first insert ATTEMPT ever
# made against this database by counter-aware (task-01+) code -- see the
# "Counting-start epoch" rationale in insert_datapoint/insert_cost_datapoint
# for why this is written from the insert path, never from _migrate(), and
# why the in-memory latch guarding it closes on a SELECT-confirmed read, not
# on the write attempt itself. Task 02 imports this constant rather than
# hardcoding the string.
DEDUPE_EPOCH_META_KEY = "dedupe_counting_since"

# Chunk size for sessions_with_otlp_rows' per-statement `VALUES` CTE.
#
# Invariant that must stay true (task 02, contract task -- do not change one
# side without the other): ids_per_chunk x arms_binding_them + literal_binds
# <= 999, where 999 is SQLITE_MAX_VARIABLE_NUMBER's default ceiling on
# older/unpinned sqlite3 builds. This repo's dev machine may report a much
# higher limit (observed: 32766), which makes a violation of this invariant
# INVISIBLE here and reproducible only on the unpinned production host.
#
# The chosen shape binds the id chunk exactly ONCE via a `VALUES` CTE that
# both table arms reference through `IN (SELECT x FROM ids)`, plus one
# `usage_source` parameter per arm (2 arms): 500 x 1 + 2 = 502 <= 999.
#
# If this is ever reverted to two separate `IN (...)` lists (one per arm,
# each repeating the full id list -- i.e. arms_binding_them=2 for the ids
# themselves), the chunk size must drop to 498 (498 x 2 + 2 = 998; 499 does
# not fit: 499 x 2 + 2 = 1000 > 999). 500 only fits the single-bind CTE form.
OTLP_MEMBERSHIP_CHUNK_SIZE = 500


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ns_to_iso(time_unix_nano) -> str:
    try:
        secs = int(time_unix_nano) / 1e9
        return datetime.fromtimestamp(secs, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return _now()


def dp_key(session_id, model, token_type, query_source, time_unix_nano) -> str:
    raw = f"{session_id}|{model}|{token_type}|{query_source}|{time_unix_nano}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# Transcript (desktop-sourced) dedupe / replay-guard key. Deliberately a
# SEPARATE function from dp_key above, not an overload of it -- do not fold
# these two back together.
#
# Composition: (session_id, request_id, token_type) -- and nothing else.
#
#   - request_id replaces dp_key's time_unix_nano as the disambiguator.
#     Task 02 emits second-granularity timestamps for transcript rows, so two
#     desktop assistant messages in the same session/model/second would
#     otherwise produce an IDENTICAL dp_key and INSERT OR IGNORE would
#     silently drop the second -- under-billing a paying client with no error
#     anywhere. Keying on request_id instead makes that collision structurally
#     impossible regardless of timestamp granularity.
#   - model is EXCLUDED (unlike dp_key) because a request_id already pins the
#     record to one API request, which used exactly one model.
#   - query_source is DELIBERATELY EXCLUDED, unlike dp_key which includes it.
#     A request_id belongs to exactly one API request, which lives in exactly
#     one on-disk transcript file, and therefore carries exactly one
#     query_source (main | subagent | auxiliary) -- measured at 0 collisions
#     across 314 real request groups. This is a recorded decision, not an
#     oversight: if that invariant ever breaks, a main-transcript row and a
#     sidechain row sharing one request_id would collide under this key and
#     the second insert would be silently dropped by INSERT OR IGNORE.
#   - This key is a REPLAY GUARD, not a semantic collapse. By the time a
#     record reaches insert_datapoint / insert_cost_datapoint, task 02 / task
#     06 have already collapsed each request to its single terminal block
#     (highest apiBlockIndex) -- so there is exactly one row per
#     (session_id, request_id, token_type) to begin with. This function only
#     stops that ONE record from being re-inserted on a re-run; it does not
#     and cannot choose the right snapshot among several duplicate-request
#     inserts -- INSERT OR IGNORE keeps whichever lands first (see
#     insert_datapoint's docstring for why callers must not rely on it for
#     that).
#   - The literal "transcript" prefix keeps this key's hash input shape (4
#     fields, no model, no timestamp) structurally distinct from dp_key's (5
#     fields, includes model + time_unix_nano) -- a transcript key can never
#     equal an OTLP dp_key for the same session_id/timestamp.
#
# The cost row for a transcript record reuses this same function with the
# sentinel token_type "__cost__" (identical sentinel to dp_key's OTLP cost
# key), which never collides with any of a record's four real token rows
# (input | output | cacheRead | cacheCreation).
def transcript_key(session_id, request_id, token_type) -> str:
    raw = f"transcript|{session_id}|{request_id}|{token_type}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _existing_columns(db, table: str) -> set:
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrate(db) -> None:
    """Additive, idempotent migration for pre-task-01 databases.

    Guarded per column by PRAGMA table_info so an already-migrated (or
    freshly-created, since SCHEMA now declares these columns itself) database
    is a no-op rather than an error -- a live billing database is in use, and
    a migration that raises on open takes the receiver down. Never drops,
    renames, or retypes a column; never rewrites an existing row. Existing
    rows read back with the column DEFAULT, i.e. usage_source='otlp' and
    (on cost_usage) cost_source='actual'.
    """
    tok_cols = _existing_columns(db, "token_usage")
    if "usage_source" not in tok_cols:
        db.execute(
            "ALTER TABLE token_usage ADD COLUMN usage_source TEXT NOT NULL DEFAULT 'otlp'")
    if "entrypoint" not in tok_cols:
        db.execute("ALTER TABLE token_usage ADD COLUMN entrypoint TEXT")

    cost_cols = _existing_columns(db, "cost_usage")
    if "usage_source" not in cost_cols:
        db.execute(
            "ALTER TABLE cost_usage ADD COLUMN usage_source TEXT NOT NULL DEFAULT 'otlp'")
    if "cost_source" not in cost_cols:
        db.execute(
            "ALTER TABLE cost_usage ADD COLUMN cost_source TEXT NOT NULL DEFAULT 'actual'")

    # Belt-and-braces: SCHEMA's CREATE TABLE IF NOT EXISTS already creates
    # dedupe_drops on both fresh and existing databases (executescript(SCHEMA)
    # runs before _migrate() in __init__), so this is a no-op in practice.
    # Kept anyway for consistency with how the columns above are handled.
    # Deliberately does NOT write DEDUPE_EPOCH_META_KEY -- see the
    # "Counting-start epoch" rationale on insert_datapoint /
    # insert_cost_datapoint for why that must come from the insert path only.
    db.execute("""
        CREATE TABLE IF NOT EXISTS dedupe_drops (
          day TEXT NOT NULL,
          token_type TEXT NOT NULL,
          usage_source TEXT NOT NULL,
          drops INTEGER NOT NULL DEFAULT 0,
          first_seen TEXT,
          last_seen TEXT,
          PRIMARY KEY (day, token_type, usage_source)
        )""")
    db.commit()


class OtelStore:
    def __init__(self, path: str = DEFAULT_DB):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        _migrate(self.db)
        # In-memory latch for the counting-start epoch (DEDUPE_EPOCH_META_KEY).
        # Deliberately per-INSTANCE, not persisted, and set ONLY when a SELECT
        # has confirmed the key is present in the database -- never merely
        # because this instance issued the INSERT. See
        # _ensure_dedupe_epoch's docstring for the full rationale (a defect
        # found in Phase 3 cycle 2: latching on the write attempt instead of
        # on confirmation would permanently strand dedupe_epoch() at None if
        # the first request of the process happened to roll back).
        self._dedupe_epoch_confirmed = False

    def _ensure_dedupe_epoch(self) -> None:
        """Write DEDUPE_EPOCH_META_KEY at most once, ever, called on every
        insert_datapoint / insert_cost_datapoint ATTEMPT (inserted or
        duplicate alike) so the epoch means "counter-aware code has run at
        least once" -- not "a collision has happened".

        Latches on CONFIRMATION, not on attempt: self._dedupe_epoch_confirmed
        is set ONLY by a SELECT that found the key already committed, never
        by this instance's own INSERT. Concretely: if the flag is unset,
        SELECT the key; if present, latch and do nothing else; if absent,
        write it and leave the flag UNSET so the next insert attempt
        re-checks.

        Why (Phase 3 cycle 2 defect): this write deliberately does not
        commit() -- it rides the caller's transaction, which receiver.py
        commits per request. If the first request of the process is rolled
        back (store.db.rollback(), an ordinary path for
        sqlite3.OperationalError on a single-host deployment), a
        latch-on-attempt flag would discard that write and never retry it for
        the process lifetime -- dedupe_epoch() would return None forever
        even as later successful requests commit real drops. Latching only
        on confirmation costs one primary-key SELECT per insert until the
        epoch is actually committed, and exactly zero thereafter.

        Never raises: a failure to record the epoch must not turn into a
        billing-ingest failure.
        """
        if self._dedupe_epoch_confirmed:
            return
        try:
            row = self.db.execute(
                "SELECT 1 FROM meta WHERE key=?", (DEDUPE_EPOCH_META_KEY,)).fetchone()
            if row is not None:
                self._dedupe_epoch_confirmed = True
            else:
                self.db.execute(
                    "INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)",
                    (DEDUPE_EPOCH_META_KEY, _now()))
                # Flag stays unset -- this instance issued the write but has
                # not yet seen it confirmed; the next attempt re-checks.
        except sqlite3.Error:
            pass

    def _record_dedupe_drop(self, *, day: str, token_type: str, usage_source: str) -> None:
        """Increment the dedupe_drops bucket for one collided insert attempt.

        Called ONLY from the `cur.rowcount == 0` (duplicate) branch of
        insert_datapoint / insert_cost_datapoint -- never on a successful
        insert. Uses the portable INSERT OR IGNORE + UPDATE pair (not
        `ON CONFLICT ... DO UPDATE`, which needs SQLite 3.24+ that this repo
        does not pin) so both statements are primary-key-targeted against a
        table holding at most a few rows per day -- bounded even though a
        retried OTLP export re-sends a whole batch and collides all at once.

        Never raises: losing a diagnostic count is acceptable, breaking
        billing ingest is not. Does not commit() -- rides the caller's
        transaction like everything else on this path.
        """
        try:
            now = _now()
            self.db.execute(
                """INSERT OR IGNORE INTO dedupe_drops
                   (day, token_type, usage_source, drops, first_seen, last_seen)
                   VALUES (?, ?, ?, 0, ?, ?)""",
                (day, token_type, usage_source, now, now))
            self.db.execute(
                """UPDATE dedupe_drops SET drops = drops + 1, last_seen = ?
                   WHERE day=? AND token_type=? AND usage_source=?""",
                (now, day, token_type, usage_source))
        except sqlite3.Error:
            pass

    def insert_datapoint(self, *, session_id, repo, repo_raw, user_email, user_id,
                         org_id, model, token_type, query_source, tokens,
                         time_unix_nano, usage_source: str = "otlp",
                         entrypoint=None, request_id=None) -> bool:
        """Returns True if inserted, False if it was a duplicate.

        `usage_source`, `entrypoint`, and `request_id` are new, keyword-only,
        and all default to existing OTLP behavior -- every existing caller
        (billing.otel.receiver) keeps working unchanged.

        Keying: `usage_source == "otlp"` (the default) keys on the unchanged
        `dp_key(session_id, model, token_type, query_source, time_unix_nano)`.
        Any other `usage_source` (transcript/desktop-sourced) keys on
        `transcript_key(session_id, request_id, token_type)` instead -- see
        that function's docstring for why a separate key is required and how
        it's composed.

        `request_id` is REQUIRED (raises ValueError if falsy, and the literal
        string "None" is rejected too -- a client that stringifies a missing
        id would otherwise collide identically to a true None) whenever
        `usage_source != "otlp"`. A default of None keying on
        transcript_key(session_id, None, token_type) would collapse every
        request in the session to one row per token_type and silently
        under-bill, with no column anywhere recording the loss -- this is not
        a hypothetical, it reproduces end to end. Conversely, `usage_source ==
        "otlp"` REJECTS a non-None `request_id`: a caller that forgets to also
        pass `usage_source="transcript"` would otherwise still be silently
        routed onto the timestamp-based dp_key, reintroducing the exact
        second-granularity collision this task exists to prevent. Raising
        surfaces that wiring bug immediately instead of a few tokens later
        under-billing a client.
        """
        if usage_source == "otlp":
            if request_id is not None:
                raise ValueError(
                    "request_id must not be passed when usage_source='otlp' -- "
                    "otlp rows key on dp_key(...,time_unix_nano), not request_id; "
                    "a non-None request_id here usually means the caller meant to "
                    "also pass usage_source='transcript', and would otherwise "
                    "silently key on the timestamp-based dp_key, reintroducing the "
                    "second-granularity collision this task exists to prevent")
            key = dp_key(session_id, model, token_type, query_source, time_unix_nano)
        else:
            # .strip() BEFORE the falsy check and the "None" comparison:
            # whitespace-only request_id ("  ") would otherwise pass the
            # falsy check and collapse every request in a session onto one
            # key, exactly the original defect just harder to reach; and
            # inconsistent padding (" req-1 " vs "req-1") would otherwise key
            # differently and double-insert. Stripping first also catches
            # " None " under the "None" comparison.
            stripped_request_id = str(request_id).strip() if request_id is not None else request_id
            if not stripped_request_id or stripped_request_id == "None":
                raise ValueError(
                    "request_id is required when usage_source != 'otlp' -- keying "
                    "on None (or a blank/whitespace-only string) collapses every "
                    "request in the session to one row per token_type and silently "
                    "under-bills")
            key = transcript_key(session_id, stripped_request_id, token_type)
        cur = self.db.execute(
            """INSERT OR IGNORE INTO token_usage
               (dp_key, ts, session_id, repo, repo_raw, user_email, user_id,
                org_id, model, token_type, query_source, tokens, ingested_at,
                usage_source, entrypoint)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (key, _ns_to_iso(time_unix_nano), session_id, repo, repo_raw,
             user_email, user_id, org_id, model, token_type, query_source,
             int(tokens or 0), _now(), usage_source, entrypoint))
        self._ensure_dedupe_epoch()
        if cur.rowcount == 0:
            self._record_dedupe_drop(
                day=_ns_to_iso(time_unix_nano)[:10], token_type=token_type,
                usage_source=usage_source)
        return cur.rowcount > 0

    def insert_cost_datapoint(self, *, session_id, repo, repo_raw, user_email,
                              user_id, org_id, model, query_source, cost_usd,
                              time_unix_nano, usage_source: str = "otlp",
                              cost_source: str = "actual", request_id=None) -> bool:
        """Returns True if inserted, False if it was a duplicate.

        `usage_source`, `cost_source`, and `request_id` are new, keyword-only,
        and all default to existing OTLP behavior -- every existing caller
        keeps working unchanged.

        Keying mirrors insert_datapoint: `usage_source == "otlp"` keys on the
        unchanged `dp_key(session_id, model, "__cost__", query_source,
        time_unix_nano)`; any other `usage_source` keys on
        `transcript_key(session_id, request_id, "__cost__")` -- the same
        sentinel token_type dp_key uses for OTLP cost rows, so a record's cost
        row never collides with any of its four token rows under either key
        function.

        `request_id` validation mirrors insert_datapoint exactly (required and
        non-"None"-string for non-otlp calls; rejected for otlp calls) -- see
        that method's docstring for why both directions raise.
        """
        if usage_source == "otlp":
            if request_id is not None:
                raise ValueError(
                    "request_id must not be passed when usage_source='otlp' -- "
                    "otlp rows key on dp_key(...,time_unix_nano), not request_id; "
                    "a non-None request_id here usually means the caller meant to "
                    "also pass usage_source='transcript', and would otherwise "
                    "silently key on the timestamp-based dp_key, reintroducing the "
                    "second-granularity collision this task exists to prevent")
            key = dp_key(session_id, model, "__cost__", query_source, time_unix_nano)
        else:
            # See insert_datapoint for why .strip() runs before the falsy /
            # "None" check (whitespace-only ids and inconsistent padding).
            stripped_request_id = str(request_id).strip() if request_id is not None else request_id
            if not stripped_request_id or stripped_request_id == "None":
                raise ValueError(
                    "request_id is required when usage_source != 'otlp' -- keying "
                    "on None (or a blank/whitespace-only string) collapses every "
                    "request in the session to one row per token_type and silently "
                    "under-bills")
            key = transcript_key(session_id, stripped_request_id, "__cost__")
        cur = self.db.execute(
            """INSERT OR IGNORE INTO cost_usage
               (dp_key, ts, session_id, repo, repo_raw, user_email, user_id,
                org_id, model, query_source, cost_usd, ingested_at,
                usage_source, cost_source)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (key, _ns_to_iso(time_unix_nano), session_id, repo, repo_raw,
             user_email, user_id, org_id, model, query_source,
             float(cost_usd or 0), _now(), usage_source, cost_source))
        self._ensure_dedupe_epoch()
        if cur.rowcount == 0:
            self._record_dedupe_drop(
                day=_ns_to_iso(time_unix_nano)[:10], token_type="__cost__",
                usage_source=usage_source)
        return cur.rowcount > 0

    # ---- dedupe-drop diagnostics (frozen read interface for task 02) ----
    def dedupe_drops(self, start: str, end: str) -> dict:
        """Total drops per token_type for day >= start AND day < end
        (half-open, same convention as reconcile.otel_totals), summed across
        usage_source. Token types with zero drops are ABSENT from the dict,
        never present with 0."""
        rows = self.db.execute(
            """SELECT token_type, SUM(drops) AS drops FROM dedupe_drops
               WHERE day >= ? AND day < ?
               GROUP BY token_type""", (start, end)).fetchall()
        return {r["token_type"]: r["drops"] for r in rows if r["drops"]}

    def dedupe_drops_by_day(self, start: str, end: str) -> dict:
        """{day: {token_type: drops}} over the same half-open window as
        dedupe_drops. Days with no drops are absent."""
        rows = self.db.execute(
            """SELECT day, token_type, SUM(drops) AS drops FROM dedupe_drops
               WHERE day >= ? AND day < ?
               GROUP BY day, token_type""", (start, end)).fetchall()
        out: dict = {}
        for r in rows:
            if not r["drops"]:
                continue
            out.setdefault(r["day"], {})[r["token_type"]] = r["drops"]
        return out

    def dedupe_epoch(self):
        """The UTC ISO8601 counting-start timestamp, or None if no insert has
        ever been attempted against this database by counter-aware code.
        A plain read -- does not touch or depend on the in-memory latch used
        by _ensure_dedupe_epoch on the insert path."""
        row = self.db.execute(
            "SELECT value FROM meta WHERE key=?", (DEDUPE_EPOCH_META_KEY,)).fetchone()
        return row["value"] if row else None

    # ---- ingest-freshness + OTLP-membership reads (task 02, frozen contract
    # for tasks 03's health route / ingest guard) ------------------------
    def last_ingest_at(self, usage_source: str | None = None) -> str | None:
        """Greatest `ingested_at` -- the UTC ISO8601 time THIS RECEIVER STORED
        the row -- across BOTH token_usage and cost_usage. Deliberately reads
        `ingested_at`, never `ts` (the time the data point was RECORDED
        upstream): a replayed export carries old `ts` values but proves the
        receiver is alive right now via a fresh `ingested_at`. Reading `ts`
        instead would report a live receiver as stale the moment anyone
        replays a backlog.

        Spans both tables for the same reason `sessions_with_otlp_rows` does:
        the receiver's token and cost branches are independent
        (receiver.py:163 for claude_code.token.usage, :176 for
        claude_code.cost.usage), so a single payload can carry cost
        datapoints and no token datapoints (or vice versa). A reader scoped to
        only one table would report a live receiver as stale whenever the
        freshest traffic happened to land in the other one.

        usage_source=None (default) considers every row in both tables. A
        non-None value filters to that usage_source EXACTLY -- no LIKE, no
        case folding, no normalization -- so pass the stored value verbatim
        (e.g. "otlp").

        Returns None -- never "", 0, or a sentinel date -- when no row
        matches, so callers can distinguish an empty database from a stalled
        receiver.

        Read-only (no INSERT/UPDATE/DELETE/CREATE, no commit()) and uses the
        existing self.db connection; no new connection, no WAL pragma, no
        pool.
        """
        if usage_source is None:
            row = self.db.execute(
                """SELECT MAX(m) AS m FROM (
                       SELECT MAX(ingested_at) AS m FROM token_usage
                       UNION ALL
                       SELECT MAX(ingested_at) AS m FROM cost_usage
                   )""").fetchone()
        else:
            row = self.db.execute(
                """SELECT MAX(m) AS m FROM (
                       SELECT MAX(ingested_at) AS m FROM token_usage
                       WHERE usage_source = ?
                       UNION ALL
                       SELECT MAX(ingested_at) AS m FROM cost_usage
                       WHERE usage_source = ?
                   )""", (usage_source, usage_source)).fetchone()
        return row["m"] if row and row["m"] is not None else None

    def sessions_with_otlp_rows(self, session_ids) -> set:
        """Subset of `session_ids` that has at least one usage_source='otlp'
        row in token_usage OR cost_usage.

        BOTH TABLES -- this is the safety-critical part of the contract, not
        an implementation detail. A transcript record inserts a cost row
        alongside its token rows, and invoice.py sums
        `actual_cost + estimated_cost` into total_billed, so the cost side is
        billed. Because the receiver's token and cost branches are
        independent (receiver.py:163 / :176), a partial flush can leave a
        session with OTLP rows in cost_usage and NONE in token_usage. A
        token_usage-only guard would pass that session, let its transcript be
        accepted, and land a cost_source='rate_card' row beside the existing
        cost_source='actual' row -- billing the client twice.
        `transcript_key` cannot catch this after the fact: it and `dp_key`
        are deliberately designed to never collide.

        Filters on usage_source='otlp' ONLY -- never additionally on
        `entrypoint`. OTLP rows carry a NULL entrypoint (per the token_usage
        schema comment, that column is transcript-rows-only), so adding an
        entrypoint predicate would match zero OTLP rows and turn this guard
        into a permanent no-op that waves every session through.

        Empty/falsy `session_ids` (None, [], "", or an iterable that yields
        nothing) returns set() WITHOUT issuing any query. This is deliberate,
        not an optimization: a bare `IN ()` is a syntax error in SQLite, and
        a query built to produce `IN (NULL)` instead would silently match no
        rows and be read by the caller as "no OTLP rows exist yet -- safe to
        insert" -- which is exactly the double-billing direction this method
        exists to prevent.

        Chunking and binding: the deduplicated id list is split into chunks
        of OTLP_MEMBERSHIP_CHUNK_SIZE (500) ids, one statement per chunk,
        results unioned across chunks. Each chunk is bound to a `VALUES` CTE
        EXACTLY ONCE; both table arms reference that CTE via
        `IN (SELECT x FROM ids)` rather than each arm carrying its own
        repeated `IN (...)` list. Two arms each repeating the full `IN` list
        would bind every id TWICE -- for a 500-id chunk, 500 x 2 arms + 2
        usage_source binds = 1002 parameters, which exceeds the 999
        SQLITE_MAX_VARIABLE_NUMBER cap on older/unpinned sqlite3 builds and
        raises `OperationalError: too many SQL variables`. This machine's
        cap may be far higher (e.g. 32766), which makes that regression
        invisible in development and reproducible only in production -- see
        OTLP_MEMBERSHIP_CHUNK_SIZE's module-level comment for the exact
        invariant (ids_per_chunk x arms_binding_them + literal_binds <= 999)
        this chunk size and statement shape must jointly satisfy. Chunking
        itself is exercised even though production hands this method at most
        one chunk's worth of ids at a time (MAX_BATCH_SIZE caps a POST at
        500 records) -- the method's public contract accepts an unbounded
        iterable, so the multi-chunk path must be correct regardless.

        The input is deduplicated before chunking, so N copies of one id
        issue one statement, not N/chunk_size.

        Every id is bound as a `?` parameter -- never string-interpolated --
        because session ids arrive from a client-posted payload.

        Does not swallow sqlite3.Error. Unlike the dedupe_drops diagnostic
        counter (where a failed count must never become a billing
        rejection), a failed membership test here must propagate: the
        caller's only safe fallback on an unanswered "does this session
        already have OTLP rows" question is to refuse the insert, and
        silently returning an empty set would look identical to "verified,
        no OTLP rows" -- again, the double-billing direction.

        Read-only (no INSERT/UPDATE/DELETE/CREATE, no commit()), uses the
        existing self.db connection, and never caches or memoizes: this
        guard is consulted during ingest, and a stale "no OTLP rows" answer
        double-bills just as surely as a wrong one.
        """
        if not session_ids:
            return set()
        ids = list(dict.fromkeys(session_ids))
        if not ids:
            return set()

        found: set = set()
        chunk_size = OTLP_MEMBERSHIP_CHUNK_SIZE
        for start in range(0, len(ids), chunk_size):
            chunk = ids[start:start + chunk_size]
            values_sql = ",".join("(?)" for _ in chunk)
            sql = (
                f"WITH ids(x) AS (VALUES {values_sql}) "
                "SELECT session_id FROM token_usage "
                "WHERE usage_source = ? AND session_id IN (SELECT x FROM ids) "
                "UNION "
                "SELECT session_id FROM cost_usage "
                "WHERE usage_source = ? AND session_id IN (SELECT x FROM ids)"
            )
            params = list(chunk) + ["otlp", "otlp"]
            rows = self.db.execute(sql, params).fetchall()
            found.update(r["session_id"] for r in rows)
        return found

    # ---- session -> repo timeline (fed by the CwdChanged hook) ---------
    def insert_session_repo(self, *, session_id, ts, seq, repo, repo_raw, cwd,
                            event) -> bool:
        """Record that `session_id` was working in `repo` as of `ts`.

        Returns True if inserted, False if an identical entry already existed.
        Duplicate entries for the same repo+second are harmless — the as-of
        join reads the latest one and they all name the same repo.
        """
        cur = self.db.execute(
            """INSERT OR IGNORE INTO session_repo_timeline
               (session_id, ts, seq, repo, repo_raw, cwd, event, ingested_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (session_id, ts, int(seq or 0), repo, repo_raw or "", cwd or "",
             event or "", _now()))
        return cur.rowcount > 0

    def multi_repo_sessions(self) -> dict:
        """session_id -> sorted list of repos, for sessions whose timeline shows
        more than one repo. These are the sessions whose usage gets split across
        repos, so they're the ones worth eyeballing before invoicing."""
        rows = self.db.execute(
            """SELECT session_id, repo FROM session_repo_timeline
               WHERE session_id IN (
                   SELECT session_id FROM session_repo_timeline
                   GROUP BY session_id HAVING COUNT(DISTINCT repo) > 1)
               GROUP BY session_id, repo ORDER BY session_id, repo""").fetchall()
        out: dict = {}
        for r in rows:
            out.setdefault(r["session_id"], []).append(r["repo"])
        return out

    def timeline_counts(self) -> dict:
        row = self.db.execute(
            """SELECT COUNT(*) entries,
                      COUNT(DISTINCT session_id) sessions,
                      COUNT(DISTINCT repo) repos
               FROM session_repo_timeline""").fetchone()
        return {"entries": row["entries"], "sessions": row["sessions"],
                "repos": row["repos"]}

    # ---- repo -> billing-name override map (optional) ------------------
    def distinct_repos(self):
        return self.db.execute(
            """SELECT t.repo AS repo,
                      COALESCE(m.bill_name, '') AS bill_name,
                      SUM(t.tokens) AS tokens,
                      COUNT(DISTINCT t.user_email) AS users,
                      COUNT(DISTINCT t.session_id) AS sessions
               FROM token_usage t
               LEFT JOIN repo_name_map m ON m.repo = t.repo
               GROUP BY t.repo ORDER BY tokens DESC""").fetchall()

    def set_mapping(self, repo: str, bill_name: str):
        self.db.execute(
            "INSERT OR REPLACE INTO repo_name_map(repo,bill_name,updated_at) VALUES(?,?,?)",
            (repo, bill_name, _now()))

    def get_mapping(self) -> dict:
        """repo -> override billing name (only rows that have been overridden)."""
        return {r["repo"]: r["bill_name"]
                for r in self.db.execute("SELECT repo, bill_name FROM repo_name_map")}

    # ---- Fabric delivery outbox (async) --------------------------------
    def fabric_enqueue(self, *, kind, period_start, period_end, local_path,
                       onelake_path, table_name=""):
        """Queue one file for delivery. Re-queues cleanly on re-run: any not-yet-
        sent row for the same (kind, period) is replaced so we never pile up
        duplicate pending deliveries."""
        self.db.execute(
            """DELETE FROM fabric_outbox
               WHERE kind=? AND period_start=? AND period_end=? AND status!='sent'""",
            (kind, period_start, period_end))
        self.db.execute(
            """INSERT INTO fabric_outbox
               (kind, period_start, period_end, local_path, onelake_path,
                table_name, status, attempts, next_attempt_at, enqueued_at)
               VALUES (?,?,?,?,?,?, 'pending', 0, ?, ?)""",
            (kind, period_start, period_end, local_path, onelake_path,
             table_name, _now(), _now()))
        self.db.commit()

    def fabric_pending(self, now_iso: str, max_attempts: int = 5):
        """Rows due for a delivery attempt now (pending and not backing off,
        under the attempt ceiling)."""
        return self.db.execute(
            """SELECT * FROM fabric_outbox
               WHERE status='pending' AND attempts < ?
                 AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
               ORDER BY id""", (max_attempts, now_iso)).fetchall()

    def fabric_mark_sent(self, row_id: int):
        self.db.execute(
            "UPDATE fabric_outbox SET status='sent', sent_at=?, last_error=NULL "
            "WHERE id=?", (_now(), row_id))
        self.db.commit()

    def fabric_mark_retry(self, row_id: int, error: str, next_attempt_at: str,
                          max_attempts: int = 5):
        """Record a failed attempt; keep 'pending' for another try, or flip to
        'failed' once the attempt ceiling is reached."""
        self.db.execute(
            """UPDATE fabric_outbox
               SET attempts = attempts + 1,
                   last_error = ?,
                   next_attempt_at = ?,
                   status = CASE WHEN attempts + 1 >= ? THEN 'failed' ELSE 'pending' END
               WHERE id=?""",
            (error[:2000], next_attempt_at, max_attempts, row_id))
        self.db.commit()

    def fabric_outbox_counts(self) -> dict:
        return {r["status"]: r["n"] for r in self.db.execute(
            "SELECT status, COUNT(*) n FROM fabric_outbox GROUP BY status")}

    def commit(self):
        self.db.commit()

    def close(self):
        self.db.commit()
        self.db.close()
