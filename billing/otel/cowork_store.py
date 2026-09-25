"""SQLite store for Cowork usage -- a deliberately SEPARATE pipeline from
billing/otel/otel_store.py.

This module is part of the `cowork-telemetry-ingest` goal's isolation
constraint: Cowork usage lives in its own database file, its own schema, its
own env var, and its own `CoworkStore` class with no shared base class and no
shared schema string with `OtelStore`. Do NOT merge this with otel_store.py
without a dedicated follow-up goal -- the two are kept apart on purpose so a
future change to one schema can never silently ripple into the other.

Like otel_store.py, Claude Code (and Cowork) export token metrics with DELTA
temporality: each data point is an increment. To accumulate correctly and
stay idempotent across re-sends, we store one row per data point keyed by a
dp_key that includes the data point's timestamp; INSERT OR IGNORE dedupes
identical points.

Repo attribution is NEVER resolved here. Cowork's cloud-VM sessions carry no
wrapper-stamped `repo=` resource attribute at all (unlike the CLI wrapper
otel_store.py serves), so there is no wrapper-level value to record, resolved
or otherwise. `repo`/`repo_raw` are stored verbatim (coalesced to "" instead
of NULL) and resolution happens later, at report time, via
billing/otel/cowork_attribute.py's `resolve_repo` -- the same query-time-only
invariant billing/otel/attribute.py uses for the OTEL pipeline.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timezone

DEFAULT_COWORK_DB = os.environ.get("COWORK_DB", "./data/cowork.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS cowork_token_usage (
  dp_key TEXT PRIMARY KEY,          -- dedupe key (dims + timestamp)
  ts TEXT,                          -- data point time (UTC)
  session_id TEXT,
  repo TEXT,                        -- "" == no signal captured at ingest time;
                                    -- resolve at report time via cowork_attribute.py
  repo_raw TEXT,                    -- "" == no wrapper-stamped repo attribute
  user_email TEXT,
  user_id TEXT,
  org_id TEXT,
  model TEXT,
  token_type TEXT,                  -- input | output | cacheRead | cacheCreation
  query_source TEXT,                -- main | subagent | auxiliary
  tokens INTEGER,
  ingested_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_cowork_token_repo ON cowork_token_usage(repo);

CREATE TABLE IF NOT EXISTS cowork_cost_usage (
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
  cost_usd REAL,
  ingested_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_cowork_cost_repo ON cowork_cost_usage(repo);
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


# dp_key composition (deliberately a LOCAL, independent implementation -- not
# imported from otel_store.dp_key -- so this module never couples to that
# module's internals, per this task's structural-independence requirement):
#
#   sha256("cowork|{session_id}|{model}|{token_type}|{query_source}|{time_unix_nano}")[:32]
#
# Dims + timestamp, same idea as otel_store.dp_key: session_id/model/
# token_type/query_source pin the row to one specific measurement, and
# time_unix_nano (the OTLP data point's own timestamp, not receipt time)
# disambiguates repeated exports of the same interval. The literal "cowork"
# prefix keeps this key's hash input shape/namespace distinct from
# otel_store.dp_key's, so a cowork_dp_key can never collide with an
# otel_store dp_key even if every other field happened to match.
def cowork_dp_key(session_id, model, token_type, query_source, time_unix_nano) -> str:
    raw = f"cowork|{session_id}|{model}|{token_type}|{query_source}|{time_unix_nano}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class CoworkStore:
    """A fully separate SQLite store for Cowork usage.

    Structurally independent of `OtelStore`: no shared base class, no shared
    schema string. See this module's docstring for why.
    """

    def __init__(self, path: str = DEFAULT_COWORK_DB):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    def insert_datapoint(self, *, session_id, repo, repo_raw, user_email, user_id,
                         org_id, model, token_type, query_source, tokens,
                         time_unix_nano) -> bool:
        """Returns True if inserted, False if it was a duplicate.

        `repo`/`repo_raw` are coalesced to "" (never NULL) -- this store
        never resolves attribution itself; a report resolves it later via
        cowork_attribute.resolve_repo.
        """
        key = cowork_dp_key(session_id, model, token_type, query_source, time_unix_nano)
        cur = self.db.execute(
            """INSERT OR IGNORE INTO cowork_token_usage
               (dp_key, ts, session_id, repo, repo_raw, user_email, user_id,
                org_id, model, token_type, query_source, tokens, ingested_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (key, _ns_to_iso(time_unix_nano), session_id, repo or "", repo_raw or "",
             user_email, user_id, org_id, model, token_type, query_source,
             int(tokens or 0), _now()))
        return cur.rowcount > 0

    def insert_cost_datapoint(self, *, session_id, repo, repo_raw, user_email,
                              user_id, org_id, model, query_source, cost_usd,
                              time_unix_nano) -> bool:
        """Returns True if inserted, False if it was a duplicate.

        Keying mirrors insert_datapoint, using the "__cost__" sentinel
        token_type so a record's cost row never collides with any of its
        token rows.
        """
        key = cowork_dp_key(session_id, model, "__cost__", query_source, time_unix_nano)
        cur = self.db.execute(
            """INSERT OR IGNORE INTO cowork_cost_usage
               (dp_key, ts, session_id, repo, repo_raw, user_email, user_id,
                org_id, model, query_source, cost_usd, ingested_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (key, _ns_to_iso(time_unix_nano), session_id, repo or "", repo_raw or "",
             user_email, user_id, org_id, model, query_source,
             float(cost_usd or 0), _now()))
        return cur.rowcount > 0

    def last_ingest_at(self) -> str | None:
        """Greatest `ingested_at` across both cowork_token_usage and
        cowork_cost_usage, or None if both tables are empty. Mirrors
        OtelStore.last_ingest_at's query shape (task 03's /healthz endpoint
        calls this directly)."""
        row = self.db.execute(
            """SELECT MAX(m) AS m FROM (
                   SELECT MAX(ingested_at) AS m FROM cowork_token_usage
                   UNION ALL
                   SELECT MAX(ingested_at) AS m FROM cowork_cost_usage
               )""").fetchone()
        return row["m"] if row and row["m"] is not None else None

    def commit(self):
        self.db.commit()

    def close(self):
        self.db.commit()
        self.db.close()
