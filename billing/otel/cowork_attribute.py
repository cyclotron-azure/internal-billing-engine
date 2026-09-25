"""Read-only repo-attribution lookup for Cowork sessions, against the
EXISTING otel.db's session_repo_timeline table.

This is part of a deliberately SEPARATE pipeline from
billing/otel/attribute.py / billing/otel/otel_store.py: Cowork usage is
stored in its own database (billing/otel/cowork_store.py) with no repo
resolved at ingest time. To bill a Cowork session to a repo, this module
opens the CLI wrapper's existing otel.db strictly READ-ONLY and joins the
session id against that database's session_repo_timeline table -- the same
hook-fed timeline billing/otel/attribute.py already uses for the OTLP
pipeline. Do NOT merge this with attribute.py without a dedicated follow-up
goal; the two stay apart on purpose.

Never opens otel.db read-write, and never creates it. If the file is
missing, unreadable, or the query fails for any reason, `resolve_repo`
returns a safe ("unknown", "absent") fallback rather than raising --
resolution here is used only by reporting, never by ingestion, and must
never crash a report run over one bad session id.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from billing.otel import otel_store as _otel_store

# TIMELINE_TABLE mirrors attribute.py's own constant -- documents the table
# name this module reads, in the SAME existing database, read-only, through
# this pipeline's own connection helper. NOT used to build any SQL string
# below (every statement here is a plain literal, per the "no f-string/
# format-string SQL" requirement) -- it exists purely for readers who want
# the name in one place.
TIMELINE_TABLE = "session_repo_timeline"

# As-of match: the repo active at-or-before `ts`, for this session. Mirrors
# attribute.py's _AS_OF query shape. A plain string literal -- no f-string,
# no .format() -- per this module's "no f-string/format-string SQL" rule.
_AS_OF_SQL = """
    SELECT repo FROM session_repo_timeline
    WHERE session_id = ? AND ts <= ?
    ORDER BY ts DESC, seq DESC LIMIT 1
"""

# Earliest-timeline-entry fallback: covers a datapoint whose ts slightly
# precedes the session's first hook event (export-interval rounding, small
# clock skew). Mirrors attribute.py's _FIRST query shape -- Cowork's OTLP
# export timing has no reason to be exempt from that same clock-skew case.
_FIRST_SQL = """
    SELECT repo FROM session_repo_timeline
    WHERE session_id = ?
    ORDER BY ts ASC, seq ASC LIMIT 1
"""

# Existence probe for otel_db_reachable -- deliberately NOT a bare `SELECT 1`
# (see that function's docstring for why a bare SELECT 1 succeeds against ANY
# valid SQLite file, including this goal's own cowork.db).
_TABLE_PROBE_SQL = "SELECT 1 FROM session_repo_timeline LIMIT 1"


def _connect_ro(path: str) -> sqlite3.Connection:
    """Open `path` as a genuinely read-only SQLite connection.

    Built as `Path(path).resolve().as_uri() + "?mode=ro"` -- NEVER
    `f"file:{path}?mode=ro"` with the raw path string. The naive f-string
    form opens the database READ-WRITE (and can CREATE a new file) whenever
    `path` contains a `#` or `?` character, because SQLite's URI parser
    treats everything after those characters as the fragment/query rather
    than part of the path. `Path.as_uri()`'s own percent-encoding closes
    this hole.

    This is a first-class, independently testable seam (rather than being
    inlined into resolve_repo) specifically so a test can open a connection
    through it directly and assert a write against that connection raises --
    resolve_repo alone (a function returning a plain tuple) gives a test no
    connection object to exercise.

    Raises whatever sqlite3 raises (e.g. if the file doesn't exist), and can
    also raise ValueError (e.g. `Path.resolve()` on a NUL-byte path raises
    "embedded null character in path") or OSError from the underlying path
    resolution -- callers that need a safe, never-raising path (resolve_repo,
    otel_db_reachable) catch `(sqlite3.Error, ValueError, OSError)` around
    this.
    """
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def otel_db_reachable(otel_db_path: str | None = None) -> bool:
    """True only when `otel_db_path` (default: otel_store.DEFAULT_DB) can be
    opened read-only AND its session_repo_timeline table is confirmed
    present. False on ANY failure (missing file, locked db, corrupt file, or
    a valid-but-wrong SQLite file with no such table) -- never raises.

    Deliberately probes for the session_repo_timeline table specifically
    (SELECT 1 FROM session_repo_timeline LIMIT 1), never a bare `SELECT 1`:
    a bare SELECT 1 succeeds against ANY valid SQLite file, including this
    goal's own cowork.db sitting right next to otel.db -- the single most
    likely wrong-path mistake, given the two files' proximity -- which would
    make this return True while every subsequent resolve_repo call still
    silently fails with "no such table" and falls through to
    ("unknown", "absent"), exactly the failure this function exists to
    catch.

    This exists so a caller (task 04's report) can distinguish "the existing
    otel.db could not be reached at all" from "it was reached, and this
    particular session simply has no timeline rows".
    """
    path = otel_db_path if otel_db_path is not None else _otel_store.DEFAULT_DB
    try:
        conn = _connect_ro(path)
    except (sqlite3.Error, ValueError, OSError):
        # ValueError/OSError: Path(path).resolve() raises ValueError on a
        # NUL-byte path ("embedded null character in path") and can raise
        # OSError on other malformed/unresolvable paths -- both must be
        # caught here, not just sqlite3.Error, to honor "never raises".
        return False
    try:
        conn.execute(_TABLE_PROBE_SQL)
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def resolve_repo(session_id: str, ts: str, otel_db_path: str | None = None) -> tuple[str, str]:
    """Resolve which repo a Cowork session bills to, via the EXISTING
    otel.db's session_repo_timeline table -- read-only, query-time only,
    never persisted.

    Mirrors attribute.py's real fallback chain (not a simplified one):
    COALESCE(as-of match, earliest-timeline-entry match). `attribution_source`
    is "timeline" whenever EITHER query matches (the session has at least
    one relevant timeline row), and "absent" only when the session has NO
    session_repo_timeline rows at all. No third bucket is invented here.

    When attribution_source is "absent", repo is the string "unknown" --
    matching attribute.py's own convention that no_remote/absent/
    desktop-scratch all normalize to 'unknown' -- never the literal string
    "absent" doing double duty as both the repo value and the source label.

    `otel_db_path` defaults to `otel_store.DEFAULT_DB`'s VALUE (imported
    read-only for that value, not its behavior) so tests can point this at a
    fixture instead of a real file.

    Opens the existing otel.db strictly read-only via `_connect_ro`. If the
    file doesn't exist, or the query fails for any reason, returns
    ("unknown", "absent") rather than raising -- this lookup is used only by
    reporting, never by ingestion, but must never be able to create or
    modify otel.db as a side effect of a missing-file open, and must never
    crash a report run over one bad session id.

    Use `otel_db_reachable` (above) for the caller-visible distinction
    between "genuinely absent" and "couldn't reach the db at all" --
    resolve_repo itself stays a simple, always-safe two-bucket function.
    """
    path = otel_db_path if otel_db_path is not None else _otel_store.DEFAULT_DB
    try:
        conn = _connect_ro(path)
    except (sqlite3.Error, ValueError, OSError):
        # See otel_db_reachable's matching except clause: Path.resolve() can
        # raise ValueError (NUL-byte path) or OSError, not just sqlite3.Error.
        return ("unknown", "absent")
    try:
        row = conn.execute(_AS_OF_SQL, (session_id, ts)).fetchone()
        if row is None:
            row = conn.execute(_FIRST_SQL, (session_id,)).fetchone()
        if row is not None:
            return (row[0], "timeline")
        return ("unknown", "absent")
    except sqlite3.Error:
        return ("unknown", "absent")
    finally:
        conn.close()
