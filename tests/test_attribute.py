"""Tests for billing/otel/attribute.py -- the desktop-scratch bucket (task 04).

Covers the seven acceptance criteria in
_goals/desktop-usage-capture/04-attribution.md:

  1. transcript row, no billable repo, WITH a timeline row (repo='unknown')
     -> 'desktop-scratch', not 'timeline'.
  2. transcript row that DOES resolve to a real repo -> 'timeline'.
  3. every existing OTLP classification (timeline / wrapper / no_remote /
     absent) unchanged.
  4. resolved_repo() unchanged for every seeded OTLP row.
  5. resolved_view('cost_usage') still compiles and returns the same rows.
  6. bill.py and export.py both still run (exit 0) against an OTLP-only store.
  7. resolved_view('token_usage') still yields resolved_repo /
     attribution_source and includes the new store columns.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from billing.otel.attribute import resolved_repo, resolved_view
from billing.otel.otel_store import OtelStore

from conftest import SEEDED_SESSIONS, seed_otlp_rows

DESKTOP_NANO = 1_767_312_000_000_000_000  # arbitrary fixed instant, distinct from BASE_NANO


def _sole_value_per_session(rows, col: str) -> dict[str, str]:
    """Collapse per-row (session_id, col) tuples down to one value per
    session_id -- but LOUDLY, via assertion, if two rows of the same session
    ever disagree on `col`. A plain dict-comprehension keyed on session_id
    would silently keep only the last row and hide a divergent one; grouping
    by session_id into a `set` of the column's values and asserting there is
    only ever one member means a future fixture where rows within one
    session diverge on `col` fails instead of passing on stale confidence."""
    by_session: dict[str, set] = {}
    for r in rows:
        by_session.setdefault(r["session_id"], set()).add(r[col])
    result = {}
    for sid, values in by_session.items():
        assert len(values) == 1, f"{sid}: rows disagree on {col}: {values}"
        result[sid] = next(iter(values))
    return result


def _fetch_sources(store: OtelStore, table: str) -> dict[str, str]:
    """session_id -> attribution_source, asserting every row of a session
    agrees (see _sole_value_per_session)."""
    rows = store.db.execute(
        f"WITH r AS ({resolved_view(table)}) "
        "SELECT session_id, attribution_source FROM r").fetchall()
    return _sole_value_per_session(rows, "attribution_source")


def _fetch_repos(store: OtelStore, table: str) -> dict[str, str]:
    """session_id -> resolved_repo, asserting every row of a session agrees
    (see _sole_value_per_session)."""
    rows = store.db.execute(
        f"WITH r AS ({resolved_view(table)}) "
        "SELECT session_id, resolved_repo FROM r").fetchall()
    return _sole_value_per_session(rows, "resolved_repo")


# ---------------------------------------------------------------------------
# AC1 / AC2 -- desktop (transcript) sessions
# ---------------------------------------------------------------------------

def test_desktop_scratch_fires_despite_unknown_timeline_row(tmp_db_path):
    """A transcript row for a desktop session with no billable repo classifies
    as 'desktop-scratch' even though the session has a timeline row carrying
    repo='unknown' (claude-repo-tag.py fires SessionStart even in a scratch
    dir) -- the naive CASE order would let the timeline branch claim it first.
    """
    store = OtelStore(tmp_db_path)
    sid = "sess-desktop-scratch"
    store.insert_datapoint(
        session_id=sid, repo="unknown", repo_raw="",
        user_email="dev@cyclotron.com", user_id="u-dev", org_id="org-cyclotron",
        model="claude-sonnet-5", token_type="input", query_source="main",
        tokens=100, time_unix_nano=DESKTOP_NANO,
        usage_source="transcript", entrypoint="claude-desktop", request_id="req-scratch-1",
    )
    store.insert_session_repo(
        session_id=sid, ts="2026-01-02T00:00:00Z", seq=0,
        repo="unknown", repo_raw="", cwd="/home/dev/scratch",
        event="SessionStart",
    )
    store.commit()

    sources = _fetch_sources(store, "token_usage")
    repos = _fetch_repos(store, "token_usage")
    assert sources[sid] == "desktop-scratch"
    assert repos[sid] == "unknown"  # resolved_repo() unchanged: still the 'unknown' key
    store.close()


def test_desktop_session_resolving_to_real_repo_still_reports_timeline(tmp_db_path):
    """A desktop session whose timeline DOES resolve to a real repo must
    still classify 'timeline', not 'desktop-scratch'."""
    store = OtelStore(tmp_db_path)
    sid = "sess-desktop-real-repo"
    store.insert_datapoint(
        session_id=sid, repo="github.com/cyclotron/acme-web", repo_raw="",
        user_email="dev@cyclotron.com", user_id="u-dev", org_id="org-cyclotron",
        model="claude-sonnet-5", token_type="input", query_source="main",
        tokens=100, time_unix_nano=DESKTOP_NANO,
        usage_source="transcript", entrypoint="claude-desktop", request_id="req-real-1",
    )
    store.insert_session_repo(
        session_id=sid, ts="2026-01-02T00:00:00Z", seq=0,
        repo="github.com/cyclotron/acme-web", repo_raw="git@github.com:Cyclotron/Acme-Web.git",
        cwd="/home/dev/acme-web", event="SessionStart",
    )
    store.commit()

    sources = _fetch_sources(store, "token_usage")
    repos = _fetch_repos(store, "token_usage")
    assert sources[sid] == "timeline"
    assert repos[sid] == "github.com/cyclotron/acme-web"
    store.close()


# ---------------------------------------------------------------------------
# AC3 / AC4 -- every existing OTLP classification, and resolved_repo(),
# unchanged.
# ---------------------------------------------------------------------------

# Expected classification per seeded session, keyed to SEEDED_SESSIONS in
# conftest.py: session 001 carries a timeline event -> 'timeline'; session 002
# has a real repo/repo_raw but no timeline -> 'wrapper'; session 003 has
# repo='unknown' and repo_raw='' -> 'absent'.
EXPECTED_SEEDED_SOURCES = {
    "sess-otlp-001": "timeline",
    "sess-otlp-002": "wrapper",
    "sess-otlp-003": "absent",
}
EXPECTED_SEEDED_REPOS = {s["session_id"]: s["repo"] for s in SEEDED_SESSIONS}


@pytest.fixture
def seeded_store(tmp_db_path):
    store = OtelStore(tmp_db_path)
    seed_otlp_rows(store)
    # An extra OTLP row exercising 'no_remote': repo='unknown' with a
    # non-empty repo_raw, and no timeline entry for the session.
    store.insert_datapoint(
        session_id="sess-otlp-no-remote", repo="unknown", repo_raw="/home/dev/no-remote-dir",
        user_email="carol@cyclotron.com", user_id="u-carol", org_id="org-cyclotron",
        model="claude-sonnet-5", token_type="input", query_source="main",
        tokens=42, time_unix_nano=1_767_225_600_000_000_000 + 99_000_000_000,
    )
    store.insert_cost_datapoint(
        session_id="sess-otlp-no-remote", repo="unknown", repo_raw="/home/dev/no-remote-dir",
        user_email="carol@cyclotron.com", user_id="u-carol", org_id="org-cyclotron",
        model="claude-sonnet-5", query_source="main", cost_usd=1.0,
        time_unix_nano=1_767_225_600_000_000_000 + 99_000_000_000,
    )
    store.commit()
    yield store
    store.close()


def test_every_existing_otlp_classification_unchanged(seeded_store):
    sources = _fetch_sources(seeded_store, "token_usage")
    for sid, expected in EXPECTED_SEEDED_SOURCES.items():
        assert sources[sid] == expected, f"{sid}: expected {expected}, got {sources[sid]}"
    assert sources["sess-otlp-no-remote"] == "no_remote"

    cost_sources = _fetch_sources(seeded_store, "cost_usage")
    assert cost_sources["sess-otlp-no-remote"] == "no_remote"


def test_resolved_repo_unchanged_for_every_seeded_otlp_row(seeded_store):
    repos = _fetch_repos(seeded_store, "token_usage")
    for sid, expected in EXPECTED_SEEDED_REPOS.items():
        assert repos[sid] == expected, f"{sid}: expected {expected}, got {repos[sid]}"
    assert repos["sess-otlp-no-remote"] == "unknown"


# ---------------------------------------------------------------------------
# AC5 -- resolved_view('cost_usage') compiles and returns the same rows.
# ---------------------------------------------------------------------------

def test_resolved_view_cost_usage_compiles_and_matches(seeded_store):
    rows = seeded_store.db.execute(
        f"WITH r AS ({resolved_view('cost_usage')}) "
        "SELECT session_id, resolved_repo, attribution_source, cost_usd FROM r "
        "ORDER BY session_id").fetchall()
    got = {r["session_id"]: (r["resolved_repo"], r["attribution_source"]) for r in rows}
    for s in SEEDED_SESSIONS:
        assert got[s["session_id"]][0] == s["repo"]
    assert got["sess-otlp-001"][1] == "timeline"
    assert got["sess-otlp-002"][1] == "wrapper"
    assert got["sess-otlp-003"][1] == "absent"
    assert got["sess-otlp-no-remote"] == ("unknown", "no_remote")
    # 4 seeded cost rows + 1 extra no_remote row.
    assert len(rows) == len(SEEDED_SESSIONS) + 1


# ---------------------------------------------------------------------------
# AC6 -- bill.py and export.py both still run against an OTLP-only store.
# ---------------------------------------------------------------------------

def test_bill_py_runs_against_otlp_only_store(seeded_otlp_db_path):
    # PYTHONIOENCODING=utf-8: bill.py's own console output uses a unicode
    # warning glyph unrelated to this task's change; the subprocess's stdout
    # is not a real console under pytest and Windows defaults to cp1252,
    # which cannot encode it. Forcing utf-8 here is a test-harness detail,
    # not a change to bill.py's behavior.
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "billing.otel.bill", "--db", seeded_otlp_db_path],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "PER-REPO BILL" in result.stdout


def test_export_py_runs_against_otlp_only_store(seeded_otlp_db_path, tmp_path):
    out_dir = str(tmp_path / "exports")
    result = subprocess.run(
        [sys.executable, "-m", "billing.otel.export", "--db", seeded_otlp_db_path,
         "--out-dir", out_dir, "--no-enqueue"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "claudeusagesummary.csv" in result.stdout


# ---------------------------------------------------------------------------
# AC7 -- resolved_view('token_usage') column shape.
# ---------------------------------------------------------------------------

def test_resolved_view_token_usage_includes_new_columns(seeded_store):
    cur = seeded_store.db.execute(f"SELECT * FROM ({resolved_view('token_usage')}) LIMIT 1")
    names = {d[0] for d in cur.description}
    assert "resolved_repo" in names
    assert "attribution_source" in names
    assert "usage_source" in names
    assert "entrypoint" in names


# ---------------------------------------------------------------------------
# Mutation-resistance checks -- these encode the exact failure modes flagged
# in the task's history: branch order, the usage_source predicate, and the
# returned literal each independently matter. Kept as ordinary assertions (not
# a mutation-testing harness) so they run green here and go red if any of
# those three properties regresses.
# ---------------------------------------------------------------------------

def test_branch_order_matters_scratch_beats_timeline(tmp_db_path):
    """If the timeline branch were checked first, this session (transcript,
    timeline row present but repo='unknown') would misreport 'timeline'."""
    store = OtelStore(tmp_db_path)
    sid = "sess-order-check"
    store.insert_datapoint(
        session_id=sid, repo="unknown", repo_raw="",
        user_email="", user_id="", org_id="",
        model="claude-sonnet-5", token_type="input", query_source="main",
        tokens=1, time_unix_nano=DESKTOP_NANO,
        usage_source="transcript", entrypoint="claude-desktop", request_id="req-order-1",
    )
    store.insert_session_repo(
        session_id=sid, ts="2026-01-02T00:00:00Z", seq=0,
        repo="unknown", repo_raw="", cwd="/scratch", event="SessionStart",
    )
    store.commit()
    sources = _fetch_sources(store, "token_usage")
    assert sources[sid] != "timeline"
    assert sources[sid] == "desktop-scratch"
    store.close()


def test_resolved_repo_not_stored_repo_scratch_launch_cd_into_real_repo(tmp_db_path):
    """The branch must key on the RESOLVED repo, not the stored one. Session
    launched (stored repo='unknown') then cd'd INTO a real repo mid-session:
    the timeline's as-of pick for this datapoint is the real repo, so the row
    must classify 'timeline' and resolve to that real repo -- even though the
    row's own stored `repo` column still reads 'unknown'.

    Replacing `resolved_repo(alias)` with `{alias}.repo` at attribute.py:89
    would instead see the STORED 'unknown' and misclassify this as
    'desktop-scratch', with `resolved_repo` unaffected (it comes from a
    separate expression) -- so this assertion on attribution_source is what
    catches that mutation; see the module-level RED proof in this file's
    history for the mutation actually being run and reverted.
    """
    store = OtelStore(tmp_db_path)
    sid = "sess-cd-into-real-repo"
    real_repo = "github.com/cyclotron/acme-web"
    # TWO timeline entries, genuinely ordered before the datapoint's own ts
    # (DESKTOP_NANO = 2026-01-02T00:00:00Z), and DIFFERENT from each other --
    # not one entry restated at two timestamps. This is what actually pins
    # the branch to _AS_OF (the LATEST entry <= the datapoint's ts) rather
    # than _FIRST (the EARLIEST entry): with only one entry, as the previous
    # revision of this test had, _AS_OF and _FIRST always agree regardless of
    # ordering, and a mutant that disables _AS_OF (falls back to _FIRST)
    # survives undetected. Here they disagree: _AS_OF picks the launch
    # entry (SessionStart, 'unknown') for the FIRST case below and the
    # CwdChanged entry (real_repo) for THIS case, exactly the opposite of
    # what _FIRST alone would pick.
    store.insert_session_repo(
        session_id=sid, ts="2026-01-01T22:00:00Z", seq=0,
        repo="unknown", repo_raw="", cwd="/home/dev/scratch", event="SessionStart",
    )
    store.insert_session_repo(
        session_id=sid, ts="2026-01-01T23:00:00Z", seq=0,
        repo=real_repo, repo_raw="git@github.com:Cyclotron/Acme-Web.git",
        cwd="/home/dev/acme-web", event="CwdChanged",
    )
    store.insert_datapoint(
        session_id=sid, repo="unknown", repo_raw="",  # STORED value: scratch at launch
        user_email="dev@cyclotron.com", user_id="u-dev", org_id="org-cyclotron",
        model="claude-sonnet-5", token_type="input", query_source="main",
        tokens=100, time_unix_nano=DESKTOP_NANO,  # strictly after both timeline entries
        usage_source="transcript", entrypoint="claude-desktop", request_id="req-cd-into-1",
    )
    store.commit()

    sources = _fetch_sources(store, "token_usage")
    repos = _fetch_repos(store, "token_usage")
    assert sources[sid] == "timeline"
    assert repos[sid] == real_repo  # the AS-OF (latest) entry, not the FIRST (earliest) one
    store.close()


def test_resolved_repo_not_stored_repo_real_launch_cd_into_scratch(tmp_db_path):
    """Mirror case: session launched in a real repo (stored `repo` and
    non-empty `repo_raw` both carry it), then cd'd OUT to a scratch
    directory -- the timeline's as-of pick for this datapoint is 'unknown',
    so the row must classify 'desktop-scratch' and resolve to 'unknown',
    even though the row's own stored `repo` column still reads the real repo.

    Replacing `resolved_repo(alias)` with `{alias}.repo` at attribute.py:89
    would instead see the STORED real repo and never enter this branch,
    falling through to 'timeline' (since the timeline row IS non-null) --
    exactly the opposite misclassification from the mirror test above.
    """
    store = OtelStore(tmp_db_path)
    sid = "sess-cd-into-scratch"
    real_repo = "github.com/cyclotron/acme-web"
    # TWO timeline entries (see the mirror test above for why a single entry
    # cannot pin this to _AS_OF vs _FIRST): launch entry carries the real
    # repo, the later CwdChanged entry carries 'unknown' -- so _AS_OF (latest
    # <= the datapoint's ts) picks 'unknown' while _FIRST (earliest) would
    # pick the real repo, the opposite answer.
    store.insert_session_repo(
        session_id=sid, ts="2026-01-01T22:00:00Z", seq=0,
        repo=real_repo, repo_raw="git@github.com:Cyclotron/Acme-Web.git",
        cwd="/home/dev/acme-web", event="SessionStart",
    )
    store.insert_session_repo(
        session_id=sid, ts="2026-01-01T23:00:00Z", seq=0,
        repo="unknown", repo_raw="",
        cwd="/home/dev/scratch", event="CwdChanged",
    )
    store.insert_datapoint(
        session_id=sid, repo=real_repo, repo_raw="git@github.com:Cyclotron/Acme-Web.git",
        user_email="dev@cyclotron.com", user_id="u-dev", org_id="org-cyclotron",
        model="claude-sonnet-5", token_type="input", query_source="main",
        tokens=100, time_unix_nano=DESKTOP_NANO,  # strictly after both timeline entries
        usage_source="transcript", entrypoint="claude-desktop", request_id="req-cd-into-2",
    )
    store.commit()

    sources = _fetch_sources(store, "token_usage")
    repos = _fetch_repos(store, "token_usage")
    assert sources[sid] == "desktop-scratch"
    assert repos[sid] == "unknown"  # the AS-OF (latest) entry, not the FIRST (earliest) one
    store.close()


def test_usage_source_predicate_matters_otlp_unknown_stays_no_remote(seeded_store):
    """An OTLP row (usage_source='otlp') resolving to 'unknown' must classify
    'no_remote', never 'desktop-scratch' -- proves the branch is gated on
    usage_source='transcript' and not merely on resolved_repo()='unknown'."""
    sources = _fetch_sources(seeded_store, "token_usage")
    assert sources["sess-otlp-no-remote"] == "no_remote"
    assert sources["sess-otlp-003"] == "absent"
