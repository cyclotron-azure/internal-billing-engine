"""Tests for the ancestor-of-real-repo inheritance in billing/otel/attribute.py.

Rule under test (see attribute.py module docstring): when a datapoint's
effective timeline row (as-of, else the session's first) is repo='unknown', it
inherits a real repo only if that row's cwd is a project-level folder that is
the SAME as, or an ANCESTOR of, the cwd of qualifying real-repo rows in the same
session which name exactly ONE repo. Everything else keeps its old behaviour.

Every test seeds a real temp SQLite store (no mocks of the SQL), inserts
timeline rows and datapoints into BOTH token_usage and cost_usage, and reads the
result through `resolved_view` (and, where stated, the standalone
`resolved_repo()` / `attribution_source()` expressions).

Windows paths are raw strings (or explicit "\\\\"-escaped) throughout: a bare
'\\d' / '\\U' in a normal string literal would be a bug in the TEST.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from billing.otel import export
from billing.otel.attribute import (
    attribution_source,
    resolved_repo,
    resolved_view,
)
from billing.otel.otel_store import OtelStore

SID = "sess-inherit"
REAL = "github.com/acme/real"
OTHER = "github.com/acme/other"
WRAPPER = "github.com/wrapper/tag"
BASE = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
TABLES = ("token_usage", "cost_usage")

NATE_U = r"C:\dev\wealthspire"
NATE_R = r"C:\dev\wealthspire\src\Ticketing.Frontend"
ONEDRIVE = r"C:\Users\x\OneDrive - Cyclotron Inc"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def T(minute: int) -> str:
    """Timeline-style ts string, `minute` minutes after BASE (may be negative)."""
    return (BASE + timedelta(minutes=minute)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _nano(minute: int) -> int:
    return int((BASE + timedelta(minutes=minute)).timestamp()) * 1_000_000_000


@pytest.fixture
def store(tmp_db_path):
    s = OtelStore(tmp_db_path)
    yield s
    s.close()


def tl(store, minute, repo, cwd, event="CwdChanged", seq=0, sid=SID):
    store.insert_session_repo(
        session_id=sid, ts=T(minute), seq=seq, repo=repo, repo_raw="",
        cwd=cwd, event=event)


def dp(store, minute, sid=SID, usage_source="otlp", repo=WRAPPER,
       repo_raw="git@wrapper:tag.git", model="claude-sonnet-5", tokens=10):
    """One token datapoint AND one cost datapoint at `minute`."""
    extra = {}
    cost_extra = {}
    if usage_source != "otlp":
        rid = f"{sid}-{minute}-{model}"
        extra = {"request_id": rid}
        cost_extra = {"request_id": rid, "cost_source": "rate_card"}
    common = dict(session_id=sid, repo=repo, repo_raw=repo_raw,
                  user_email="dev@cyclotron.com", user_id="u-dev",
                  org_id="org-cyclotron", model=model, query_source="main",
                  time_unix_nano=_nano(minute), usage_source=usage_source)
    store.insert_datapoint(token_type="input", tokens=tokens, **common, **extra)
    store.insert_cost_datapoint(cost_usd=tokens / 100.0, **common, **cost_extra)


def resolve(store, table, sid=SID):
    """{ts -> (resolved_repo, attribution_source)} for one session, via the view."""
    rows = store.db.execute(
        f"WITH r AS ({resolved_view(table)}) "
        "SELECT ts, resolved_repo, attribution_source FROM r "
        "WHERE session_id = ?", (sid,)).fetchall()
    out = {}
    for r in rows:
        val = (r["resolved_repo"], r["attribution_source"])
        assert out.setdefault(r["ts"], val) == val, f"disagreeing rows at {r['ts']}"
    return out


def expect(store, minute, repo, source="timeline", sid=SID):
    """Assert the datapoint at `minute` resolves to (repo, source) in BOTH tables."""
    for table in TABLES:
        got = resolve(store, table, sid)[T(minute)]
        assert got == (repo, source), f"{table}@{minute}: {got} != {(repo, source)}"


def nate(store, u=NATE_U, r=NATE_R, repo=REAL, sid=SID, event="CwdChanged"):
    """unknown row at t=0, real row at t=10 (u is the ancestor of r)."""
    tl(store, 0, "unknown", u, event="SessionStart", sid=sid)
    tl(store, 10, repo, r, event=event, sid=sid)
    store.commit()


def inherits(store, u, r, sid=SID):
    """Seed unknown `u` @0, real descendant `r` @10, datapoint @5; return what
    the t=5 datapoint resolves to in both tables (asserting they agree)."""
    tl(store, 0, "unknown", u, event="SessionStart", sid=sid)
    tl(store, 10, REAL, r, sid=sid)
    dp(store, 5, sid=sid)
    store.commit()
    got = {t: resolve(store, t, sid)[T(5)] for t in TABLES}
    assert got["token_usage"] == got["cost_usage"]
    return got["token_usage"][0]


# ---------------------------------------------------------------------------
# Nate / forward-only / reverse / Derek
# ---------------------------------------------------------------------------

def test_nate_unknown_ancestor_inherits_real_child_repo(store):
    nate(store)
    dp(store, 5)      # effective row = the unknown row
    dp(store, 15)     # effective row = the real child row
    store.commit()
    expect(store, 5, REAL, "timeline")
    expect(store, 15, REAL, "timeline")


def test_forward_only_datapoint_before_first_row_inherits(store):
    """ts precedes the first timeline row: effective row is the FIRST (unknown)
    row, and a qualifying real row later still lends its repo."""
    nate(store)
    dp(store, -5)
    store.commit()
    expect(store, -5, REAL, "timeline")


@pytest.mark.parametrize("unknown_first", [False, True])
def test_reverse_real_parent_unknown_child_stays_unknown(store, unknown_first):
    parent = r"C:\dev\repoR"
    child = r"C:\dev\repoR\tools\gen"
    if unknown_first:
        tl(store, 0, "unknown", child, event="SessionStart")
        tl(store, 10, REAL, parent)
        dp(store, 5)
    else:
        tl(store, 0, REAL, parent, event="SessionStart")
        tl(store, 10, "unknown", child)
        dp(store, 15)
    store.commit()
    expect(store, 5 if unknown_first else 15, "unknown", "timeline")


def test_derek_unrelated_sibling_stays_unknown(store):
    u = r"C:\Users\derek\OneDrive - Cyclotron Inc\Code\Dashnoard"
    r = r"C:\Users\derek\OneDrive - Cyclotron Inc\Code\src\orbit-local"
    tl(store, 0, "unknown", u, event="SessionStart")
    tl(store, 10, REAL, r)
    dp(store, 5)
    store.commit()
    expect(store, 5, "unknown", "timeline")


def test_derek_dashnoard_with_real_descendant_inherits(store):
    u = r"C:\Users\derek\OneDrive - Cyclotron Inc\Code\Dashnoard"
    assert inherits(store, u, u + r"\src\app") == REAL


# ---------------------------------------------------------------------------
# distinct repos / session scope
# ---------------------------------------------------------------------------

def test_two_distinct_qualifying_repos_stay_unknown(store):
    tl(store, 0, "unknown", NATE_U, event="SessionStart")
    tl(store, 10, REAL, NATE_U + r"\a")
    tl(store, 20, OTHER, NATE_U + r"\b")
    dp(store, 5)
    store.commit()
    expect(store, 5, "unknown", "timeline")


def test_same_repo_qualifying_twice_inherits(store):
    tl(store, 0, "unknown", NATE_U, event="SessionStart")
    tl(store, 10, REAL, NATE_U + r"\a")
    tl(store, 20, REAL, NATE_U + r"\b")
    tl(store, 30, REAL, NATE_U + r"\a")
    dp(store, 5)
    store.commit()
    expect(store, 5, REAL, "timeline")


def test_only_unknown_session_stays_unknown(store):
    tl(store, 0, "unknown", NATE_U, event="SessionStart")
    tl(store, 10, "unknown", NATE_U + r"\a")
    dp(store, 5)
    store.commit()
    expect(store, 5, "unknown", "timeline")


def test_real_row_in_another_session_never_leaks(store):
    tl(store, 0, "unknown", NATE_U, event="SessionStart", sid="s-a")
    tl(store, 10, REAL, NATE_R, sid="s-b")
    dp(store, 5, sid="s-a")
    dp(store, 15, sid="s-b")
    store.commit()
    expect(store, 5, "unknown", "timeline", sid="s-a")
    expect(store, 15, REAL, "timeline", sid="s-b")


def test_session_id_literal_unknown_never_inherits(store):
    nate(store, sid="unknown")
    dp(store, 5, sid="unknown")
    store.commit()
    expect(store, 5, "unknown", "timeline", sid="unknown")


# ---------------------------------------------------------------------------
# Preservation
# ---------------------------------------------------------------------------

def test_preservation_a_real_effective_rows_keep_own_repo(store):
    """M at C:\\dev\\mono (project-level), S (other repo) at C:\\dev\\mono\\sub:
    each effective row resolves to its own repo; no distinct-repo collapse."""
    tl(store, 0, REAL, r"C:\dev\mono", event="SessionStart")
    tl(store, 10, OTHER, r"C:\dev\mono\sub")
    dp(store, 5)
    dp(store, 15)
    store.commit()
    expect(store, 5, REAL, "timeline")
    expect(store, 15, OTHER, "timeline")


def test_preservation_b_real_effective_row_with_related_unknown_keeps_repo(store):
    tl(store, 0, "unknown", r"C:\dev\proj", event="SessionStart")
    tl(store, 10, REAL, r"C:\dev\proj\a")
    tl(store, 20, "unknown", r"C:\dev\proj\a\gen")
    dp(store, 15)   # effective row = the real row
    dp(store, 25)   # effective row = unknown CHILD of the real row
    store.commit()
    expect(store, 15, REAL, "timeline")
    expect(store, 25, "unknown", "timeline")


def test_preservation_c_no_timeline_uses_wrapper_tag(store):
    dp(store, 5, repo=REAL, repo_raw="git@x:real.git")
    store.commit()
    expect(store, 5, REAL, "wrapper")


def test_preservation_c_unknown_row_never_falls_back_to_wrapper_tag(store):
    tl(store, 0, "unknown", r"C:\dev\scratchy", event="SessionStart")
    dp(store, 5, repo=REAL, repo_raw="git@x:real.git")
    store.commit()
    expect(store, 5, "unknown", "timeline")


def test_no_unknown_rows_resolves_as_before_the_change(store):
    """No 'unknown' row anywhere: as-of row's repo, else the first row's,
    else the wrapper tag -- even with nested/related cwds."""
    tl(store, 0, REAL, r"C:\dev\mono", event="SessionStart")
    tl(store, 10, OTHER, r"C:\dev\mono\sub")
    tl(store, 20, REAL, r"C:\dev\mono")
    tl(store, 0, OTHER, r"C:\dev\solo", event="SessionStart", sid="s-b")
    dp(store, -5)                 # before first -> first row
    dp(store, 5)                  # as-of row 0
    dp(store, 15)                 # as-of row 10
    dp(store, 25)                 # as-of row 20
    dp(store, 5, sid="s-b")
    dp(store, 5, sid="s-c", repo=OTHER, repo_raw="git@x:o.git")  # no timeline
    store.commit()
    expect(store, -5, REAL)
    expect(store, 5, REAL)
    expect(store, 15, OTHER)
    expect(store, 25, REAL)
    expect(store, 5, OTHER, sid="s-b")
    expect(store, 5, OTHER, "wrapper", sid="s-c")


def test_null_repo_effective_row_falls_back_to_first_row_then_wrapper(store):
    """Unreachable via ingest; seeded raw. As-of row with NULL repo falls back
    to the first row's repo, then to the wrapper tag (original COALESCE chain)."""
    tl(store, 0, REAL, r"C:\dev\proj", event="SessionStart", sid="s-a")
    store.db.execute(
        "INSERT INTO session_repo_timeline (session_id, ts, seq, repo, repo_raw, "
        "cwd, event, ingested_at) VALUES ('s-a', ?, 0, NULL, '', ?, 'CwdChanged', 'x')",
        (T(10), r"C:\dev\other"))
    store.db.execute(
        "INSERT INTO session_repo_timeline (session_id, ts, seq, repo, repo_raw, "
        "cwd, event, ingested_at) VALUES ('s-b', ?, 0, NULL, '', ?, 'SessionStart', 'x')",
        (T(0), r"C:\dev\other"))
    dp(store, 15, sid="s-a")
    dp(store, 15, sid="s-b")
    store.commit()
    for table in TABLES:
        assert resolve(store, table, "s-a")[T(15)] == (REAL, "timeline")
        assert resolve(store, table, "s-b")[T(15)] == (WRAPPER, "wrapper")


# ---------------------------------------------------------------------------
# Path normalisation and comparison
# ---------------------------------------------------------------------------

def test_normalisation_is_case_insensitive(store):
    assert inherits(store, r"C:\DEV\WealthSpire", r"c:\dev\wealthspire\SRC") == REAL


def test_normalisation_mixed_separators(store):
    assert inherits(store, r"C:\dev\x", "C:/dev/x/sub") == REAL


def test_normalisation_trailing_separators(store):
    assert inherits(store, "C:\\dev\\proj\\", "C:\\dev\\proj\\sub\\") == REAL


def test_normalisation_trailing_forward_slash_and_whitespace(store):
    assert inherits(store, "  C:/dev/proj/  ", "C:/dev/proj/sub//") == REAL


def test_backslash_separator_handling_is_active(store):
    """Guards the escaping of the backslash literal in the SQL: if it were an
    empty/doubled literal, backslash and slash spellings would not compare."""
    assert inherits(store, r"C:\dev\sepcheck", "c:/dev/sepcheck/x") == REAL


def test_prefix_lookalike_is_not_a_descendant(store):
    assert inherits(store, r"C:\dev\wealth", r"C:\dev\wealthspire\x") == "unknown"


@pytest.mark.parametrize("u, r", [
    (r"C:\proj\a_b", r"C:\proj\axb\c"),
    (r"C:\proj\a%", r"C:\proj\abc\c"),
    (r"C:\proj\a[bc]", r"C:\proj\ab\c"),
    (r"C:\proj\a?", r"C:\proj\ab\c"),
    (r"C:\proj\a*", r"C:\proj\abc\c"),
])
def test_wildcards_in_paths_are_inert(store, u, r):
    assert inherits(store, u, r) == "unknown"


@pytest.mark.parametrize("u", [r"C:\proj\a_b", r"C:\proj\a%", r"C:\proj\a[bc]"])
def test_wildcard_characters_match_literally(store, u):
    assert inherits(store, u, u + r"\c") == REAL


def test_same_folder_unknown_and_real_inherits(store):
    assert inherits(store, NATE_U, NATE_U) == REAL


# ---------------------------------------------------------------------------
# Anchor blocklist: one named test per class (real descendant present, so the
# block is the only reason for 'unknown').
# ---------------------------------------------------------------------------

def _blocked(store, u, r):
    assert inherits(store, u, r) == "unknown"


def _allowed(store, u, r):
    assert inherits(store, u, r) == REAL


@pytest.mark.parametrize("u, r", [
    ("C:\\", r"C:\dev\wealthspire"),
    ("C:/", r"C:\dev\wealthspire"),
    ("c:", r"C:\dev\wealthspire"),
])
def test_blocklist_drive_root(store, u, r):
    _blocked(store, u, r)


def test_blocklist_slash_root(store):
    _blocked(store, "/", "/srv/app/x")


def test_blocklist_tilde(store):
    _blocked(store, "~", "~/proj")


@pytest.mark.parametrize("u, r", [
    ("/mnt/c", "/mnt/c/dev/wealthspire"),
    ("/mnt/data", "/mnt/data/proj/x"),
    ("/media/x", "/media/x/proj/y"),
    ("/volumes/disk", "/volumes/disk/proj/y"),
])
def test_blocklist_mount_roots(store, u, r):
    _blocked(store, u, r)


def test_blocklist_git_bash_drive_root(store):
    _blocked(store, "/c", "/c/dev/wealthspire")


@pytest.mark.parametrize("u, r", [
    (r"\\srv", r"\\srv\share\team\proj"),
    (r"\\srv\share", r"\\srv\share\team\proj"),
])
def test_blocklist_unc_host_and_share(store, u, r):
    _blocked(store, u, r)


@pytest.mark.parametrize("u, r", [
    (r"C:\Users\x", r"C:\Users\x\proj"),
    ("/home/x", "/home/x/proj"),
    ("/root", "/root/proj"),
])
def test_blocklist_home_folders(store, u, r):
    _blocked(store, u, r)


@pytest.mark.parametrize("u, r", [
    (r"C:\data\Users", r"C:\data\Users\proj"),
    ("/srv/home", "/srv/home/proj"),
])
def test_blocklist_bare_users_home_parent_below_depth_one(store, u, r):
    _blocked(store, u, r)


@pytest.mark.parametrize("u, r", [
    (r"C:\Cyclotron", r"C:\Cyclotron\repo"),
    # Nate's container. Blocked by this rule AND the `dev` container name, so
    # it guards neither alone; the per-name tests below guard `dev` by itself.
    (r"C:\dev", r"C:\dev\wealthspire"),
    (r"\\srv\share\team", r"\\srv\share\team\proj"),
    ("/srv", "/srv/app/x"),
    ("/mnt/c/Cyclotron", "/mnt/c/Cyclotron/repo"),
    ("/media/x/Cyclotron", "/media/x/Cyclotron/repo"),
    ("/volumes/disk/Cyclotron", "/volumes/disk/Cyclotron/repo"),
    ("/c/Cyclotron", "/c/Cyclotron/repo"),
])
def test_blocklist_top_level_folders_under_a_root(store, u, r):
    _blocked(store, u, r)


@pytest.mark.parametrize("u, r", [
    # Depth 4 under a mount: the mount top-level rule (k <= 3) does not apply,
    # so the `dev` container name is the only reason this stays unknown.
    ("/mnt/c/x/dev", "/mnt/c/x/dev/wealthspire"),
    ("/home/x/projects", "/home/x/projects/app"),
    (r"C:\Users\x\clients", r"C:\Users\x\clients\acme"),
    (r"C:\Users\x\Work", r"C:\Users\x\Work\acme"),
    (r"C:\Users\x\AppData\Local\Temp", r"C:\Users\x\AppData\Local\Temp\proj"),
    (ONEDRIVE, ONEDRIVE + r"\Code\Dashnoard"),
    (ONEDRIVE + r"\Desktop", ONEDRIVE + r"\Desktop\proj"),
    (r"C:\Users\x\Visual Studio 2022", r"C:\Users\x\Visual Studio 2022\proj"),
])
def test_blocklist_generic_containers(store, u, r):
    _blocked(store, u, r)


# The container vocabulary, copied LITERALLY from attribute._CONTAINER_NAMES
# (deliberately not imported: a name silently dropped from the source must
# turn its case here red, not shrink this list with it).
CONTAINER_NAMES = [
    "code", "src", "source", "repos", "projects", "dev", "git", "github",
    "workspace", "desktop", "documents", "downloads", "library", "cloudstorage",
    "work", "clients", "temp", "tmp", "appdata",
]

# Shapes at a depth where NO other blocklist rule applies (not a root, not a
# home folder, not a top-level folder under a drive / '/' / mount / UNC share):
# the container NAME is the only reason the unknown row stays unknown.
#   POSIX    /opt/team/<name>              (k = 3, not under a mount prefix)
#   Windows  D:\work2\<Name>  (mixed case) (k = 2 after normalisation)
POSIX_CONTAINER_SHAPE = "/opt/team/{}"
WIN_CONTAINER_SHAPE = "D:\\work2\\{}"


def _win_case(name: str) -> str:
    """Mixed case for the Windows shape, e.g. 'cloudstorage' -> 'CloudStorage'."""
    half = (len(name) + 1) // 2
    return name[:half].capitalize() + name[half:].capitalize()


def test_container_name_vocabulary_is_distinct_and_complete():
    assert len(CONTAINER_NAMES) == 19
    assert len(set(CONTAINER_NAMES)) == 19
    assert all(n == n.lower() for n in CONTAINER_NAMES)


@pytest.mark.parametrize("name", CONTAINER_NAMES)
def test_blocklist_container_name_posix_mid_depth(store, name):
    u = POSIX_CONTAINER_SHAPE.format(name)
    _blocked(store, u, u + "/app")


@pytest.mark.parametrize("name", CONTAINER_NAMES)
def test_blocklist_container_name_windows_mid_depth_mixed_case(store, name):
    u = WIN_CONTAINER_SHAPE.format(_win_case(name))
    _blocked(store, u, u + r"\acme")


@pytest.mark.parametrize("name", CONTAINER_NAMES)
def test_blocklist_container_name_shapes_plain_child_folder_inherits(store, name):
    """Positive control: the same shapes with a non-vocabulary folder (`acme`)
    one level deeper are project-level and DO inherit."""
    u_posix = POSIX_CONTAINER_SHAPE.format(name) + "/acme"
    _allowed(store, u_posix, u_posix + "/app")
    u_win = WIN_CONTAINER_SHAPE.format(_win_case(name)) + r"\acme"
    _allowed(store, u_win, u_win + r"\src")


@pytest.mark.parametrize("u, r", [
    (r"C:\dev\wealthspire", r"C:\dev\wealthspire\src\Ticketing.Frontend"),
    (ONEDRIVE + r"\Code\Dashnoard", ONEDRIVE + r"\Code\Dashnoard\src\app"),
    (r"C:\Users\x\proj", r"C:\Users\x\proj\app"),
    ("/home/x/proj", "/home/x/proj/app"),
    ("/srv/app/x", "/srv/app/x/sub"),
    ("/mnt/c/dev/wealthspire", "/mnt/c/dev/wealthspire/src/app"),
    ("/media/x/team/proj", "/media/x/team/proj/app"),
    ("/volumes/disk/team/proj", "/volumes/disk/team/proj/app"),
    ("/c/dev/wealthspire", "/c/dev/wealthspire/src/app"),
])
def test_blocklist_allowed_project_folders_inherit(store, u, r):
    _allowed(store, u, r)


# ---------------------------------------------------------------------------
# Empty / NULL cwd, DirectoryAdded
# ---------------------------------------------------------------------------

def test_empty_cwd_unknown_row_stays_unknown(store):
    tl(store, 0, "unknown", "", event="SessionStart")
    tl(store, 10, REAL, NATE_R)
    dp(store, 5)
    store.commit()
    expect(store, 5, "unknown", "timeline")


def test_empty_cwd_unknown_row_with_posix_real_row_stays_unknown(store):
    tl(store, 0, "unknown", "", event="SessionStart")
    tl(store, 10, REAL, "/srv/app/x")
    dp(store, 5)
    store.commit()
    expect(store, 5, "unknown", "timeline")


def test_null_cwd_unknown_row_stays_unknown(store):
    """The store helper coerces None to ''; seed NULL with a raw INSERT."""
    store.db.execute(
        "INSERT INTO session_repo_timeline (session_id, ts, seq, repo, repo_raw, "
        "cwd, event, ingested_at) VALUES (?, ?, 0, 'unknown', '', NULL, 'SessionStart', 'x')",
        (SID, T(0)))
    tl(store, 10, REAL, NATE_R)
    dp(store, 5)
    store.commit()
    assert store.db.execute(
        "SELECT count(*) FROM session_repo_timeline WHERE cwd IS NULL"
    ).fetchone()[0] == 1
    expect(store, 5, "unknown", "timeline")


def test_null_cwd_or_event_real_rows_never_raise_or_mis_inherit(store):
    """A real row with NULL cwd cannot anchor; one with NULL event still can."""
    store.db.execute(
        "INSERT INTO session_repo_timeline (session_id, ts, seq, repo, repo_raw, "
        "cwd, event, ingested_at) VALUES (?, ?, 0, ?, '', NULL, 'CwdChanged', 'x')",
        ("s-a", T(10), REAL))
    store.db.execute(
        "INSERT INTO session_repo_timeline (session_id, ts, seq, repo, repo_raw, "
        "cwd, event, ingested_at) VALUES (?, ?, 0, ?, '', ?, NULL, 'x')",
        ("s-b", T(10), REAL, NATE_R))
    tl(store, 0, "unknown", NATE_U, event="SessionStart", sid="s-a")
    tl(store, 0, "unknown", NATE_U, event="SessionStart", sid="s-b")
    dp(store, 5, sid="s-a")
    dp(store, 5, sid="s-b")
    store.commit()
    expect(store, 5, "unknown", "timeline", sid="s-a")
    expect(store, 5, REAL, "timeline", sid="s-b")


def test_directory_added_real_row_does_not_anchor(store):
    nate(store, event="DirectoryAdded")
    dp(store, 5)
    store.commit()
    expect(store, 5, "unknown", "timeline")


def test_cwd_changed_real_row_anchors(store):
    nate(store, event="CwdChanged")
    dp(store, 5)
    store.commit()
    expect(store, 5, REAL, "timeline")


# ---------------------------------------------------------------------------
# desktop-scratch (transcript sessions)
# ---------------------------------------------------------------------------

def test_transcript_session_without_qualifying_real_row_is_desktop_scratch(store):
    tl(store, 0, "unknown", r"C:\dev\scratchy", event="SessionStart")
    tl(store, 10, REAL, r"C:\dev\elsewhere")
    dp(store, 5, usage_source="transcript", repo="unknown", repo_raw="")
    store.commit()
    expect(store, 5, "unknown", "desktop-scratch")


def test_transcript_session_that_inherits_reports_timeline(store):
    nate(store)
    dp(store, 5, usage_source="transcript", repo="unknown", repo_raw="")
    store.commit()
    expect(store, 5, REAL, "timeline")


# ---------------------------------------------------------------------------
# Tie-breaks (final order is repo-based; repo and cwd from the SAME row)
# ---------------------------------------------------------------------------

TIE_REAL = "zz.example/acme/real"   # sorts ABOVE 'unknown'
LOW_REAL = "aa.example/acme/real"   # sorts BELOW 'unknown'


@pytest.mark.parametrize("real_first", [True, False])
def test_as_of_exact_tie_real_repo_sorting_above_unknown_wins(store, real_first):
    rows = [(TIE_REAL, r"C:\dev\a\x"), ("unknown", r"C:\dev\a")]
    for repo, cwd in (rows if real_first else rows[::-1]):
        tl(store, 0, repo, cwd, event="SessionStart", seq=3)
    dp(store, 5)
    store.commit()
    expect(store, 5, TIE_REAL, "timeline")


@pytest.mark.parametrize("real_first", [True, False])
def test_as_of_tie_unknown_wins_and_inherits_via_its_own_cwd(store, real_first):
    """'unknown' sorts above LOW_REAL so the unknown row is effective; it
    inherits LOW_REAL because ITS cwd is the ancestor of the real row's."""
    rows = [(LOW_REAL, r"C:\dev\a\x"), ("unknown", r"C:\dev\a")]
    for repo, cwd in (rows if real_first else rows[::-1]):
        tl(store, 0, repo, cwd, event="SessionStart", seq=3)
    dp(store, 5)
    store.commit()
    expect(store, 5, LOW_REAL, "timeline")


@pytest.mark.parametrize("real_first", [True, False])
def test_unknown_winning_tie_does_not_borrow_real_rows_cwd(store, real_first):
    rows = [(LOW_REAL, r"C:\dev\a\x"), ("unknown", r"C:\dev\other")]
    for repo, cwd in (rows if real_first else rows[::-1]):
        tl(store, 0, repo, cwd, event="SessionStart", seq=3)
    dp(store, 5)
    store.commit()
    expect(store, 5, "unknown", "timeline")


@pytest.mark.parametrize("real_first", [True, False])
def test_first_row_exact_tie_is_resolved_deterministically(store, real_first):
    """Datapoint precedes both tied first rows: repo ASC picks 'unknown', whose
    own cwd (ancestor of the real row) inherits the real repo."""
    rows = [(TIE_REAL, r"C:\dev\a\x"), ("unknown", r"C:\dev\a")]
    for repo, cwd in (rows if real_first else rows[::-1]):
        tl(store, 0, repo, cwd, event="SessionStart", seq=3)
    dp(store, -5)
    store.commit()
    expect(store, -5, TIE_REAL, "timeline")


@pytest.mark.parametrize("real_first", [True, False])
def test_first_row_tie_unknown_does_not_borrow_real_rows_cwd(store, real_first):
    rows = [(TIE_REAL, r"C:\dev\a\x"), ("unknown", r"C:\dev\other")]
    for repo, cwd in (rows if real_first else rows[::-1]):
        tl(store, 0, repo, cwd, event="SessionStart", seq=3)
    dp(store, -5)
    store.commit()
    expect(store, -5, "unknown", "timeline")


# ---------------------------------------------------------------------------
# Alias safety / view == standalone / cardinality
# ---------------------------------------------------------------------------

def _mixed(store):
    """A representative multi-session store covering every resolution class."""
    # s-nate: inherit (before, at, after the child row, and before first row)
    nate(store, sid="s-nate")
    for m in (-5, 5, 15):
        dp(store, m, sid="s-nate")
    # s-derek: unrelated -> unknown
    tl(store, 0, "unknown", ONEDRIVE + r"\Code\Dashnoard", event="SessionStart", sid="s-derek")
    tl(store, 10, REAL, ONEDRIVE + r"\Code\src\orbit-local", sid="s-derek")
    for m in (5, 15):
        dp(store, m, sid="s-derek")
    # s-two: two distinct repos -> unknown
    tl(store, 0, "unknown", NATE_U, event="SessionStart", sid="s-two")
    tl(store, 10, REAL, NATE_U + r"\a", sid="s-two")
    tl(store, 20, OTHER, NATE_U + r"\b", sid="s-two")
    dp(store, 5, sid="s-two")
    dp(store, 25, sid="s-two")
    # s-mono: preservation
    tl(store, 0, REAL, r"C:\dev\mono", event="SessionStart", sid="s-mono")
    tl(store, 10, OTHER, r"C:\dev\mono\sub", sid="s-mono")
    for m in (5, 15):
        dp(store, m, sid="s-mono")
    # s-wrap: no timeline
    dp(store, 5, sid="s-wrap", repo=OTHER, repo_raw="git@x:o.git")
    dp(store, 6, sid="s-wrap", repo="unknown", repo_raw="")
    dp(store, 7, sid="s-wrap", repo="unknown", repo_raw="git@x:o.git")
    # transcript sessions: scratch and inherited
    tl(store, 0, "unknown", r"C:\dev\scratchy", event="SessionStart", sid="s-scratch")
    dp(store, 5, sid="s-scratch", usage_source="transcript", repo="unknown", repo_raw="")
    nate(store, sid="s-tr-nate")
    dp(store, 5, sid="s-tr-nate", usage_source="transcript", repo="unknown", repo_raw="")
    # placeholder session id
    nate(store, sid="unknown")
    dp(store, 5, sid="unknown")
    # exact ties
    tl(store, 0, TIE_REAL, r"C:\dev\a\x", event="SessionStart", seq=2, sid="s-tie")
    tl(store, 0, "unknown", r"C:\dev\a", event="SessionStart", seq=2, sid="s-tie")
    tl(store, 0, "unknown", r"C:\dev\a", event="SessionStart", seq=2, sid="s-tie")  # dup no-op
    dp(store, -5, sid="s-tie")
    dp(store, 5, sid="s-tie")
    store.commit()


def _view_rows(store, table, alias="t"):
    return store.db.execute(
        f"WITH r AS ({resolved_view(table, alias=alias)}) "
        "SELECT dp_key, resolved_repo, attribution_source FROM r ORDER BY dp_key"
    ).fetchall()


@pytest.mark.parametrize("table", TABLES)
def test_view_equals_standalone_expressions(store, table):
    _mixed(store)
    standalone = store.db.execute(
        f"SELECT t.dp_key AS dp_key, {resolved_repo()} AS resolved_repo, "
        f"{attribution_source()} AS attribution_source "
        f"FROM {table} t ORDER BY t.dp_key").fetchall()
    view = _view_rows(store, table)
    assert len(view) == len(standalone) > 10
    assert [tuple(r) for r in view] == [tuple(r) for r in standalone]
    # The store really exercises several classes (not a trivially uniform set).
    outcomes = {(r["resolved_repo"], r["attribution_source"]) for r in view}
    assert {(REAL, "timeline"), ("unknown", "timeline"), (OTHER, "timeline"),
            (OTHER, "wrapper"), ("unknown", "desktop-scratch"),
            ("unknown", "absent"), ("unknown", "no_remote")} <= outcomes


@pytest.mark.parametrize("table", TABLES)
def test_standalone_expressions_inherit_nate(store, table):
    nate(store)
    dp(store, 5)
    store.commit()
    row = store.db.execute(
        f"SELECT {resolved_repo()} AS rr, {attribution_source()} AS src "
        f"FROM {table} t").fetchone()
    assert (row["rr"], row["src"]) == (REAL, "timeline")


@pytest.mark.parametrize("table", TABLES)
def test_view_cardinality_with_tied_and_duplicate_timeline_rows(store, table):
    """LEFT JOIN must neither duplicate nor drop datapoints, even with timeline
    rows sharing (session, ts, seq) and duplicate cwds."""
    _mixed(store)
    for sid in ("s-nate", "s-tie"):
        tl(store, 10, OTHER, NATE_R, seq=0, sid=sid)       # same (ts, seq), other repo
        tl(store, 10, REAL, NATE_R, seq=0, sid=sid)
        tl(store, 10, "unknown", NATE_U, seq=0, sid=sid)   # duplicate cwd, unknown
        tl(store, 11, "unknown", NATE_U, seq=0, sid=sid)
    store.commit()
    base = store.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    assert base > 10
    n = store.db.execute(
        f"SELECT count(*) FROM ({resolved_view(table)})").fetchone()[0]
    assert n == base
    per_key = store.db.execute(
        f"WITH r AS ({resolved_view(table)}) "
        "SELECT dp_key, count(*) c FROM r GROUP BY dp_key HAVING c > 1").fetchall()
    assert per_key == []


def test_view_alias_x_matches_default_on_nate_fixture(store):
    nate(store)
    dp(store, 5)
    dp(store, 15)
    store.commit()
    for table in TABLES:
        default = _view_rows(store, table)
        assert [r["resolved_repo"] for r in default] == [REAL, REAL]
        assert [tuple(r) for r in _view_rows(store, table, "x")] == \
               [tuple(r) for r in default]


ALIASES = ["t", "x", "r", "_i", "_ar", "rid", "v", "i", "ar", "_t__i",
           "_t__ar", '"x y"', "[sp ace]", "`bq`", '"T"', "TOKEN_USAGE"]


@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize("alias", ALIASES)
def test_view_alias_variants_same_values_and_exact_column_list(store, table, alias):
    _mixed(store)
    expected_rows = [tuple(r) for r in _view_rows(store, table)]
    assert [tuple(r) for r in _view_rows(store, table, alias)] == expected_rows

    cols = [r["name"] for r in store.db.execute(f"PRAGMA table_info({table})")]
    cur = store.db.execute(resolved_view(table, alias=alias))
    assert [d[0] for d in cur.description] == \
        cols + ["resolved_repo", "attribution_source"]


@pytest.mark.parametrize("alias", ["x", '"x y"', "[sp ace]", "r", "_i"])
def test_standalone_expressions_accept_alias_variants(store, alias):
    _mixed(store)
    for table in TABLES:
        default = store.db.execute(
            f"SELECT t.dp_key, {resolved_repo()}, {attribution_source()} "
            f"FROM {table} t ORDER BY 1").fetchall()
        other = store.db.execute(
            f"SELECT {alias}.dp_key, {resolved_repo(alias)}, "
            f"{attribution_source(alias)} FROM {table} {alias} ORDER BY 1"
        ).fetchall()
        assert [tuple(r) for r in other] == [tuple(r) for r in default]


def test_view_embeds_as_subquery_with_outer_alias_collision(store):
    """The consumer shape used by reconcile: the view as a subquery under
    names that collide with the helper aliases."""
    nate(store)
    dp(store, 5)
    store.commit()
    row = store.db.execute(
        f"SELECT v.resolved_repo FROM ({resolved_view('token_usage', alias='v')}) v"
    ).fetchone()
    assert row[0] == REAL


# ---------------------------------------------------------------------------
# Consumer smoke test
# ---------------------------------------------------------------------------

def test_export_build_bills_nate_session_to_the_real_repo(store):
    nate(store)
    dp(store, 5, tokens=100)    # effective row = unknown ancestor row
    dp(store, 15, tokens=50)    # effective row = real child row
    store.commit()
    _summary, lines = export.build(store, markup=1.5, allowed_domains=("cyclotron.com",))
    by_repo = {}
    for ln in lines:
        agg = by_repo.setdefault(ln["repo_key"], [0, 0.0])
        agg[0] += ln["tokens"]
        agg[1] += ln["actual_cost_usd"]
    assert set(by_repo) == {REAL}
    assert by_repo[REAL][0] == 150
    assert by_repo[REAL][1] == pytest.approx(1.5)
    assert all(ln["attribution_source"] in (None, "") for ln in lines)
