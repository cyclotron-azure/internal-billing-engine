"""Tests for billing/otel/cowork_attribute.py -- the read-only
repo-attribution lookup against the EXISTING otel.db (task 01 of the
cowork-telemetry-ingest goal).

Uses `seeded_otlp_db_path` / `COWORK_LOOKUP_SESSION_ID` / `cowork_db_path`
from tests/conftest.py (task 00's fixtures) rather than hand-rolling
equivalents. `seeded_otlp_db_path` seeds SEEDED_SESSIONS[0] (session id
COWORK_LOOKUP_SESSION_ID) with a session_repo_timeline row at ts
"2026-01-01T00:00:00Z" and repo "github.com/cyclotron/acme-web";
SEEDED_SESSIONS[1] ("sess-otlp-002") carries token/cost rows but NO timeline
row.
"""

from __future__ import annotations

import shutil
import sqlite3

import pytest

from billing.otel.cowork_attribute import (
    _connect_ro,
    otel_db_reachable,
    resolve_repo,
)
from billing.otel.cowork_store import CoworkStore
from billing.otel.otel_store import OtelStore
from tests.conftest import COWORK_LOOKUP_SESSION_ID, SEEDED_SESSIONS

_NO_TIMELINE_SESSION_ID = SEEDED_SESSIONS[1]["session_id"]
_EXPECTED_REPO = SEEDED_SESSIONS[0]["repo"]

# A write through a genuinely read-only sqlite3 connection raises
# OperationalError with this substring -- matching on it (rather than
# accepting any sqlite3.Error) makes these tests discriminate the real
# read-only guarantee from an unrelated failure (e.g. "no such table" from a
# connection that opened read-write against the wrong/truncated path).
_READONLY_MSG = "readonly"


# --- Acceptance Criterion 3: as-of / no-timeline-rows ------------------------

def test_resolve_repo_returns_timeline_for_session_with_timeline_row(seeded_otlp_db_path):
    repo, source = resolve_repo(
        COWORK_LOOKUP_SESSION_ID, "2026-01-01T00:00:00Z", seeded_otlp_db_path)
    assert repo == _EXPECTED_REPO
    assert source == "timeline"


def test_resolve_repo_returns_absent_for_session_with_no_timeline_rows(seeded_otlp_db_path):
    repo, source = resolve_repo(
        _NO_TIMELINE_SESSION_ID, "2026-01-01T00:00:00Z", seeded_otlp_db_path)
    assert repo == "unknown"
    assert source == "absent"


# --- Acceptance Criterion 3b: clock-skew / _FIRST fallback -------------------

def test_resolve_repo_falls_back_to_first_entry_when_ts_precedes_timeline(seeded_otlp_db_path):
    repo, source = resolve_repo(
        COWORK_LOOKUP_SESSION_ID, "2025-12-31T00:00:00Z", seeded_otlp_db_path)
    assert repo == _EXPECTED_REPO
    assert source == "timeline"


# --- As-of lookup, isolated from the _FIRST fallback -------------------------
#
# seeded_otlp_db_path's session carries only ONE timeline row, so a test that
# only exercises that fixture can pass even if the as-of query (_AS_OF_SQL)
# is deleted entirely or its sort order is flipped (ts DESC -> ts ASC) --
# _FIRST_SQL alone would still return the single row either way. This test
# builds its own otel.db with a session that has TWO distinct repo windows
# plus a same-second pair distinguished only by `seq`, so the as-of query's
# own behavior (both its WHERE ts <= ? filter and its DESC/DESC ordering) is
# actually exercised and can fail independently of the _FIRST fallback.

_ASOF_SESSION_ID = "sess-asof-isolation"
_ASOF_REPO_A = "github.com/cyclotron/repo-a"
_ASOF_REPO_B = "github.com/cyclotron/repo-b"
_ASOF_REPO_LOW_SEQ = "github.com/cyclotron/repo-low-seq"
_ASOF_REPO_HIGH_SEQ = "github.com/cyclotron/repo-high-seq"
_T0 = "2026-02-01T00:00:00Z"
_T1 = "2026-02-01T00:10:00Z"
_T2 = "2026-02-01T00:20:00Z"  # same-second pair lives here


@pytest.fixture
def asof_otel_db_path(tmp_path) -> str:
    path = str(tmp_path / "asof_otel.db")
    store = OtelStore(path)
    try:
        store.insert_session_repo(
            session_id=_ASOF_SESSION_ID, ts=_T0, seq=0,
            repo=_ASOF_REPO_A, repo_raw="git@github.com:Cyclotron/repo-a.git",
            cwd="/home/dev/repo-a", event="SessionStart")
        store.insert_session_repo(
            session_id=_ASOF_SESSION_ID, ts=_T1, seq=0,
            repo=_ASOF_REPO_B, repo_raw="git@github.com:Cyclotron/repo-b.git",
            cwd="/home/dev/repo-b", event="CwdChanged")
        # Same-second pair: identical ts, distinct seq -- only the ordering's
        # `seq DESC` tiebreak can tell them apart.
        store.insert_session_repo(
            session_id=_ASOF_SESSION_ID, ts=_T2, seq=0,
            repo=_ASOF_REPO_LOW_SEQ, repo_raw="", cwd="/tmp/low",
            event="CwdChanged")
        store.insert_session_repo(
            session_id=_ASOF_SESSION_ID, ts=_T2, seq=1,
            repo=_ASOF_REPO_HIGH_SEQ, repo_raw="", cwd="/tmp/high",
            event="CwdChanged")
        store.commit()
    finally:
        store.close()
    return path


def test_resolve_repo_as_of_window_before_second_entry(asof_otel_db_path):
    # Strictly between T0 and T1 -- must resolve to repo A (the entry active
    # at that moment), not repo B (which hasn't happened yet) and not merely
    # "whichever row is earliest" (which _FIRST_SQL would also return here,
    # so this alone doesn't isolate the as-of query -- see the next test for
    # the discriminating case).
    repo, source = resolve_repo(_ASOF_SESSION_ID, "2026-02-01T00:05:00Z", asof_otel_db_path)
    assert repo == _ASOF_REPO_A
    assert source == "timeline"


def test_resolve_repo_as_of_window_after_second_entry(asof_otel_db_path):
    # At-or-after T1 (but before T2) must resolve to repo B. _FIRST_SQL would
    # incorrectly return repo A here -- this is the case that actually fails
    # if the as-of query is deleted or the fixture only had one row.
    repo, source = resolve_repo(_ASOF_SESSION_ID, "2026-02-01T00:15:00Z", asof_otel_db_path)
    assert repo == _ASOF_REPO_B
    assert source == "timeline"


def test_resolve_repo_as_of_same_second_pair_higher_seq_wins(asof_otel_db_path):
    # ts == T2 exactly: two rows share that ts, differing only by seq. The
    # as-of ORDER BY is `ts DESC, seq DESC` -- the higher seq must win. This
    # fails if that ordering is ever flipped to `seq ASC`.
    repo, source = resolve_repo(_ASOF_SESSION_ID, _T2, asof_otel_db_path)
    assert repo == _ASOF_REPO_HIGH_SEQ
    assert source == "timeline"


# --- Acceptance Criterion 4: nonexistent db path -----------------------------

def test_resolve_repo_against_nonexistent_db_returns_absent_without_raising(tmp_path):
    missing_path = tmp_path / "does_not_exist.db"
    repo, source = resolve_repo("any-session", "2026-01-01T00:00:00Z", str(missing_path))
    assert (repo, source) == ("unknown", "absent")
    assert not missing_path.exists()


# --- Acceptance Criterion 5: _connect_ro is genuinely read-only -------------

def test_connect_ro_write_raises(seeded_otlp_db_path):
    conn = _connect_ro(seeded_otlp_db_path)
    try:
        with pytest.raises(sqlite3.OperationalError, match=_READONLY_MSG):
            conn.execute(
                "INSERT INTO session_repo_timeline "
                "(session_id, ts, seq, repo, repo_raw, cwd, event, ingested_at) "
                "VALUES ('x','2026-01-01T00:00:00Z',0,'r','','','',''"
                ")")
    finally:
        conn.close()


def test_connect_ro_update_raises(seeded_otlp_db_path):
    conn = _connect_ro(seeded_otlp_db_path)
    try:
        with pytest.raises(sqlite3.OperationalError, match=_READONLY_MSG):
            conn.execute(
                "UPDATE session_repo_timeline SET repo = 'tampered' WHERE 1=1")
    finally:
        conn.close()


# --- Acceptance Criterion 5b: '#' in the path --------------------------------

def test_connect_ro_still_readonly_with_hash_in_path(tmp_path, seeded_otlp_db_path):
    hashed_dir = tmp_path / "weird#dir"
    hashed_dir.mkdir()
    hashed_path = hashed_dir / "otel#db.db"
    shutil.copyfile(seeded_otlp_db_path, hashed_path)

    conn = _connect_ro(str(hashed_path))
    try:
        with pytest.raises(sqlite3.OperationalError, match=_READONLY_MSG):
            conn.execute(
                "INSERT INTO session_repo_timeline "
                "(session_id, ts, seq, repo, repo_raw, cwd, event, ingested_at) "
                "VALUES ('x','2026-01-01T00:00:00Z',0,'r','','','','')")
    finally:
        conn.close()

    # The naive f"file:{path}?mode=ro" form would truncate at the FIRST '#',
    # producing the path "<tmp_path>/weird" (everything before '#' in
    # "weird#dir/otel#db.db") and opening/creating THAT read-write instead.
    # Assert no such stray file/entry exists -- proves the bug's other
    # symptom (silent file creation) isn't present either, not just that the
    # write raised.
    assert not (tmp_path / "weird").exists()

    # And resolve_repo against that same '#'-bearing path still resolves
    # correctly (proves the naive f-string bug is not present here).
    repo, source = resolve_repo(
        COWORK_LOOKUP_SESSION_ID, "2026-01-01T00:00:00Z", str(hashed_path))
    assert repo == _EXPECTED_REPO
    assert source == "timeline"


# --- Acceptance Criterion 5c: otel_db_reachable true/false, never raises ----

def test_otel_db_reachable_true_for_fixture_db(seeded_otlp_db_path):
    assert otel_db_reachable(seeded_otlp_db_path) is True


def test_otel_db_reachable_false_for_nonexistent_path(tmp_path):
    missing_path = tmp_path / "does_not_exist.db"
    assert otel_db_reachable(str(missing_path)) is False
    assert not missing_path.exists()


# --- Acceptance Criterion 5d: valid db with no session_repo_timeline table --

def test_otel_db_reachable_false_for_valid_db_without_timeline_table(cowork_db_path):
    # cowork.db is a genuinely valid SQLite file (built via the real
    # CoworkStore insert path) that has NO session_repo_timeline table -- the
    # case a bare `SELECT 1` probe would get wrong.
    store = CoworkStore(cowork_db_path)
    store.close()

    assert otel_db_reachable(cowork_db_path) is False


# --- NUL-byte path: _connect_ro's underlying Path.resolve() raises ValueError,
#     not sqlite3.Error -- both callers must still honor "never raises" ------

def test_otel_db_reachable_false_for_nul_byte_path():
    assert otel_db_reachable("\x00bad") is False


def test_resolve_repo_absent_for_nul_byte_path():
    repo, source = resolve_repo("any-session", "2026-01-01T00:00:00Z", "\x00bad")
    assert (repo, source) == ("unknown", "absent")
