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
"""


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
    db.commit()


class OtelStore:
    def __init__(self, path: str = DEFAULT_DB):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        _migrate(self.db)

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
        return cur.rowcount > 0

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
