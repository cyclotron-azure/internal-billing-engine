"""Tests for billing/otel/project_label.py -- the privacy-safe project-root label.

Covers task 01 of the `unattributed-usage-breakdown` goal: the 38 worked examples,
the extra walk-up / guard / truncation / malformed-input cases from task 04, the
privacy property over every path used here, and `load_session_labels`.

Every path is a Python literal (backslash, UNC and NUL strings are never built via a
shell). The only database is an OtelStore under `tmp_path`.
"""

from __future__ import annotations

import re

import pytest

from billing.otel import project_label as pl
from billing.otel.otel_store import OtelStore
from billing.otel.project_label import (
    HOME_LABEL,
    OTHER_LABEL,
    SCRATCHPAD_LABEL,
    is_scratchpad,
    load_session_labels,
    path_segments,
    root_label,
)

SS = "SessionStart"
CC = "CwdChanged"

# --- paths shared by several examples ---------------------------------------------
DEREK_ROOT = "C:\\Users\\DerekMcConnell\\OneDrive - Cyclotron Inc\\Code\\Dashnoard"
DEREK_DEEP = DEREK_ROOT + "\\OfficeDashboard\\backend"
SUMIT = "C:\\Cyclotron\\Insights Agent\\ai-presales-agent-main"
SUMIT_INNER = SUMIT + "\\ai-presales-agent-main"

# (id, history, expected label) -- the 38 worked examples of task 01, 22 as a/b.
EXAMPLES = [
    ("ex01", [(SS, DEREK_ROOT)], "local:Dashnoard"),
    ("ex02", [(SS, DEREK_DEEP)], "local:Dashnoard"),
    ("ex03", [(SS, DEREK_ROOT),
              (CC, "C:\\Users\\DerekMcConnell\\src\\orbit-local"),
              (CC, "C:\\Users\\DerekMcConnell\\src\\orbit-wt\\google\\apps\\api")],
     "local:Dashnoard"),
    ("ex04", [(SS, SUMIT), (CC, SUMIT_INNER)], "local:ai-presales-agent-main"),
    ("ex05", [(SS, "C:\\Users\\SumitBhatia\\.claude\\projects\\"
                   "C--Cyclotron-Insights-Agent-ai-presales-agent-main\\scratchpad")],
     SCRATCHPAD_LABEL),
    ("ex06", [(SS, "C:\\Users\\SumitBhatia\\.claude\\projects\\"
                   "C--Users-SumitBhatia-OneDrive---Cyclotron-Inc-proj")],
     SCRATCHPAD_LABEL),
    ("ex07", [(SS, "C:\\Users\\ZANECH~1\\AppData\\Local\\Temp\\claude\\C--Users-x\\"
                   "0ab35cbd-cb5c-4db5-9ffc-e0282cc3cab6")],
     SCRATCHPAD_LABEL),
    ("ex08", [(SS, "C:\\Users\\ZANECH~1\\AppData\\Local\\Temp\\claude\\C--Users-x")],
     SCRATCHPAD_LABEL),
    ("ex09", [(SS, "C:\\Users\\DerekMcConnell")], HOME_LABEL),
    ("ex10", [(SS, "C:\\")], HOME_LABEL),
    ("ex11", [(SS, "/home/derek/src/orbit/apps/web")], "local:orbit"),
    ("ex12", [(SS, "C:\\Users\\DerekMcConnell\\src\\orbit-wt\\google\\apps\\api\\src\\connectors")],
     "local:orbit-wt"),
    ("ex13", [(SS, "C:\\Cyclotron\\proj\\src")], "local:proj"),
    ("ex14", [(SS, "C:\\Cyclotron\\proj\\src\\components\\ui")], "local:proj"),
    ("ex15", [(SS, "C:\\Users\\Derek\\orbit")], "local:orbit"),
    ("ex16", [(SS, "C:\\Users\\Derek\\Cyclotron Inc")], "local:Cyclotron Inc"),
    ("ex17", [(SS, "/Users/derek/Library/CloudStorage/OneDrive-CyclotronInc/Code/proj")],
     "local:proj"),
    ("ex18", [(SS, "/Users/derek/Library/CloudStorage/OneDrive-CyclotronInc")], HOME_LABEL),
    ("ex19", [(SS, SUMIT), (CC, "C:\\"), (CC, "C:\\Users\\SumitBhatia")],
     "local:ai-presales-agent-main"),
    ("ex20", [(SS, "C:\\Users\\derek\\projects\\derek")], OTHER_LABEL),
    ("ex21", [(SS, "\\\\fileserver\\share\\team\\proj")], "local:proj"),
    ("ex22a", [], ""),
    ("ex22b", [(CC, "")], ""),
    ("ex23", [(SS, "C:\\Users\\Zane\\source\\repos\\internal-billing-engine")],
     "local:internal-billing-engine"),
    ("ex24", [(SS, "C:\\Users\\Derek\\Documents\\Visual Studio 2022\\Projects\\Foo\\Foo")],
     "local:Foo"),
    ("ex25", [(SS, "/mnt/c/Users/Derek/src/proj")], "local:proj"),
    ("ex26", [(SS, "/mnt/c/Users/Derek")], HOME_LABEL),
    ("ex27", [(SS, "/c/Users/Derek/source/repos/proj/src/lib")], "local:proj"),
    ("ex28", [(SS, "D:\\Code")], HOME_LABEL),
    ("ex29", [(SS, "D:\\Code\\proj")], "local:proj"),
    ("ex30", [(SS, "/var/folders/ab/xyz/T/claude/-Users-derek-Code-proj/abc123/scratchpad")],
     SCRATCHPAD_LABEL),
    ("ex31", [(SS, "C:\\Users")], HOME_LABEL),
    ("ex32", [(SS, "/home")], HOME_LABEL),
    ("ex33", [(SS, "D:\\Code\\Users")], OTHER_LABEL),
    ("ex34", [(SS, "\\\\host\\Users\\bob")], OTHER_LABEL),
    ("ex35", [(SS, "/1/Code/proj")], "local:1"),
    ("ex36", [(SS, "  "), (CC, "C:\\Y\\proj")], "local:proj"),
    ("ex37", [(SS, "C:\\Cyclotron\\bad\x00name")], OTHER_LABEL),
    ("ex38", [(SS, "/home/derek/Code/users-api")], "local:users-api"),
]


@pytest.mark.parametrize("history,expected", [pytest.param(h, e, id=i) for i, h, e in EXAMPLES])
def test_worked_example(history, expected):
    assert root_label(history) == expected


def test_all_38_worked_examples_are_present():
    """Guard against silently dropping an example from the table above."""
    numbers = {re.match(r"ex(\d+)", i).group(1) for i, _, _ in EXAMPLES}
    assert numbers == {f"{n:02d}" for n in range(1, 39)}
    assert {"ex22a", "ex22b"} <= {i for i, _, _ in EXAMPLES}


# --- extra walk-up cases (task 04 list) ------------------------------------------

def test_deep_start_with_intermediate_history_still_resolves_to_project_root():
    history = [(SS, DEREK_DEEP), (CC, DEREK_ROOT + "\\OfficeDashboard")]
    assert root_label(history) == "local:Dashnoard"


def test_history_containing_outer_container_itself_still_resolves_to_project_root():
    outer = "C:\\Users\\DerekMcConnell\\OneDrive - Cyclotron Inc\\Code"
    history = [(SS, DEREK_DEEP), (CC, outer), (CC, DEREK_ROOT + "\\OfficeDashboard")]
    assert root_label(history) == "local:Dashnoard"


def test_no_session_start_uses_first_non_empty_cwd():
    history = [(CC, ""), (CC, "   "), (CC, "C:\\Y\\proj"), (CC, "C:\\Z\\other")]
    assert root_label(history) == "local:proj"


def test_session_start_wins_over_earlier_cwd_changed():
    history = [(CC, "C:\\A\\other"), (SS, "C:\\B\\proj")]
    assert root_label(history) == "local:proj"


def test_ancestor_match_is_case_insensitive_and_keeps_start_folder_case():
    start = "C:\\Cyclotron\\Insights Agent\\ai-presales-agent-main\\Sub\\deep"
    lower_ancestor = "c:\\cyclotron\\insights agent\\AI-PRESALES-AGENT-MAIN"
    assert root_label([(SS, start)]) == "local:deep"  # control: no ancestor visited
    assert root_label([(SS, start), (CC, lower_ancestor)]) == "local:ai-presales-agent-main"


def test_visits_outside_the_root_never_change_the_label():
    history = [(SS, "C:\\Cyclotron\\proj\\src"), (CC, "C:\\Cyclotron\\other-repo"),
               (CC, "D:\\elsewhere\\thing")]
    assert root_label(history) == "local:proj"


# --- Claude-internal folders --------------------------------------------------------

@pytest.mark.parametrize("cwd", [
    "C:\\Users\\Bob\\.claude\\projects\\x",                       # no `scratchpad` segment
    "C:\\Users\\Bob\\.claude\\projects\\x\\scratchpad",
    "C:\\Users\\Bob\\AppData\\Local\\Temp\\claude\\abc",          # no `scratchpad` segment
    "C:\\Users\\Bob\\AppData\\Local\\Temp\\claude\\abc\\scratchpad",
    "/home/bob/.claude/projects/foo",
    "/home/bob/.claude/projects/foo/scratchpad",
    "/tmp/claude/abc",
    "/tmp/claude/abc/scratchpad",
    "~/.claude/projects/foo",
    "/var/folders/ab/xyz/T/claude/abc",
    "D:\\.CLAUDE",
])
def test_claude_internal_folders_are_scratchpad(cwd):
    assert is_scratchpad(cwd) is True
    assert root_label([(SS, cwd)]) == SCRATCHPAD_LABEL


@pytest.mark.parametrize("cwd", [
    "C:\\Cyclotron\\claude",            # `claude` not under a Temp/tmp/T segment
    "/home/bob/claude-tools",
    "C:\\Users\\Bob\\Code\\proj",
    "/tmp/other/proj",
    "",
])
def test_ordinary_folders_are_not_scratchpad(cwd):
    assert is_scratchpad(cwd) is False


# --- allowlist guard ----------------------------------------------------------------

@pytest.mark.parametrize("history,expected", [
    pytest.param([(SS, "/home/alice/alice")], OTHER_LABEL, id="root-equals-username"),
    pytest.param([(SS, "D:\\work\\bob"), (CC, "C:\\Users\\Bob")], OTHER_LABEL,
                 id="username-from-another-cwd-case-insensitive"),
    pytest.param([(SS, "D:\\C--Cyclotron-x")], OTHER_LABEL, id="drive-slug-prefix"),
    pytest.param([(SS, "D:\\c--foo")], OTHER_LABEL, id="drive-slug-lowercase"),
    pytest.param([(SS, "D:\\-Users-x")], OTHER_LABEL, id="users-slug-prefix"),
    pytest.param([(SS, "D:\\.config")], OTHER_LABEL, id="dot-prefixed"),
    pytest.param([(SS, "D:\\.claude")], SCRATCHPAD_LABEL, id="dot-claude-is-scratchpad"),
    pytest.param([(SS, "D:\\MyOneDrive")], OTHER_LABEL, id="contains-onedrive"),
    pytest.param([(SS, "D:\\a:b")], OTHER_LABEL, id="embedded-colon"),
    pytest.param([(SS, "D:\\proj\\Users")], OTHER_LABEL, id="bare-Users-root-is-other"),
])
def test_allowlist_guard(history, expected):
    assert root_label(history) == expected


def test_guard_is_whole_segment_not_substring():
    assert root_label([(SS, "/home/derek/Code/users-api")]) == "local:users-api"
    assert root_label([(SS, "D:\\Code\\Project.Users")]) == "local:Project.Users"
    assert root_label([(SS, "D:\\Code\\homework")]) == "local:homework"


# --- truncation ---------------------------------------------------------------------

@pytest.mark.parametrize("n,expected_len", [(99, 99), (100, 100), (101, 100), (150, 100)])
def test_label_body_is_truncated_at_100_characters(n, expected_len):
    label = root_label([(SS, "C:\\Cyclotron\\" + "x" * n)])
    assert label == "local:" + "x" * expected_len
    assert len(label) == len("local:") + expected_len


# --- malformed input ----------------------------------------------------------------

MALFORMED = [
    ":", "\\\\", " ", "C:", "\x00", "//", "C:\\\\\\", "~", "\t\n",
    "C:\\" + "a" * 10000,
    "\\".join(["seg"] * 5000),
    "/" + "/".join(["Users"] * 2000),
]


@pytest.mark.parametrize("cwd", MALFORMED, ids=lambda c: f"len{len(c)}-{c[:8]!r}")
@pytest.mark.parametrize("event", [SS, CC, "", "Bogus"])
def test_malformed_inputs_never_raise_and_never_return_bare_prefix(cwd, event):
    label = root_label([(event, cwd)])
    assert isinstance(label, str)
    assert label == "" or (label.startswith("local:") and label != "local:")


def test_ten_thousand_character_path_yields_truncated_label():
    assert root_label([(SS, "C:\\" + "a" * 10000)]) == "local:" + "a" * 100


def test_whitespace_only_cwd_is_empty():
    assert root_label([(SS, " ")]) == ""
    assert root_label([(SS, "\t\n"), (CC, " ")]) == ""


def test_root_label_never_raises_on_non_string_cells():
    # A NULL cwd/event coming out of SQLite must not crash the export.
    assert root_label([(None, None), (SS, None)]) == ""
    assert root_label([(None, "C:\\Y\\proj")]) == "local:proj"


# --- path_segments ------------------------------------------------------------------

@pytest.mark.parametrize("cwd", ["C:\\", "/", "~", "\\\\host\\share", "/mnt/c", "", "  "])
def test_path_segments_empty_for_bare_roots(cwd):
    assert path_segments(cwd) == []


@pytest.mark.parametrize("cwd,expected", [
    ("C:\\Users\\Bob", ["Users", "Bob"]),
    ("C:/Users/Bob/", ["Users", "Bob"]),
    ("/home/bob/src", ["home", "bob", "src"]),
    ("\\\\host\\share\\a\\b", ["a", "b"]),
    ("//host/share/a", ["a"]),
    ("~/code/x", ["code", "x"]),
    ("/mnt/d/Work/x", ["Work", "x"]),
    ("/c/Users/Derek", ["Users", "Derek"]),
    ("/1/Code/proj", ["1", "Code", "proj"]),        # only an ASCII LETTER is a drive stand-in
    (" C:\\ a \\ b ", ["a", "b"]),
    ("relative\\path", ["relative", "path"]),
])
def test_path_segments_drops_only_root_prefixes(cwd, expected):
    assert path_segments(cwd) == expected


def test_interface_constants_are_frozen():
    assert pl.LOCAL_PREFIX == "local:"
    assert pl.HOME_LABEL == "local:(home)"
    assert pl.SCRATCHPAD_LABEL == "local:(scratchpad)"
    assert pl.OTHER_LABEL == "local:(other)"
    assert pl.CONTAINER_DIRS == frozenset(
        {"code", "src", "source", "repos", "projects", "dev", "git", "github", "workspace"})


# --- privacy property ---------------------------------------------------------------

def _usernames(history):
    """Independent re-derivation: every segment following Users/home in any cwd."""
    names = set()
    for _, cwd in history:
        parts = [p.strip() for p in re.split(r"[\\/]", cwd) if p.strip()]
        names.update(parts[i + 1].lower() for i in range(len(parts) - 1)
                     if parts[i].lower() in ("users", "home"))
    return names


SEEDED_NAME_FRAGMENTS = ("derekmcconnell", "sumitbhatia", "zanech")


def _assert_label_is_private(label, history):
    if label == "":
        return
    assert label.startswith("local:"), label
    body = label[len("local:"):]
    low = body.lower()
    assert body, label
    assert "/" not in body and "\\" not in body, label
    assert ":" not in body, label
    assert ".claude" not in low, label
    assert "onedrive" not in low, label
    assert not re.match(r"^[a-z]--", low), label
    assert not low.startswith("-users-"), label
    assert low not in ("users", "home"), label          # whole-segment reading
    assert low not in _usernames(history), label
    assert not any(frag in low for frag in SEEDED_NAME_FRAGMENTS), label
    assert all(ord(ch) >= 32 for ch in body), label


PRIVACY_CASES = [pytest.param(h, id=i) for i, h, _ in EXAMPLES] + [
    pytest.param([(SS, DEREK_DEEP), (CC, DEREK_ROOT + "\\OfficeDashboard")], id="deep-history"),
    pytest.param([(SS, "/home/alice/alice")], id="root-equals-username"),
    pytest.param([(SS, "D:\\work\\bob"), (CC, "C:\\Users\\Bob")], id="username-elsewhere"),
    pytest.param([(SS, "D:\\C--Cyclotron-x")], id="slug"),
    pytest.param([(SS, "D:\\MyOneDrive")], id="onedrive-root"),
    pytest.param([(SS, "C:\\Users\\Bob\\.claude\\projects\\x")], id="claude-internal"),
    pytest.param([(SS, "C:\\Users\\Bob\\Users")], id="users-under-user"),
] + [pytest.param([(SS, c)], id=f"malformed-{n}") for n, c in enumerate(MALFORMED)]


@pytest.mark.parametrize("history", PRIVACY_CASES)
def test_label_never_leaks_paths_or_identity(history):
    _assert_label_is_private(root_label(history), history)


# --- load_session_labels ------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    s = OtelStore(str(tmp_path / "labels.db"))
    try:
        yield s
    finally:
        s.close()


def _tl(store, session, ts, seq, event, cwd, repo="unknown"):
    store.insert_session_repo(session_id=session, ts=ts, seq=seq, repo=repo,
                              repo_raw="", cwd=cwd, event=event)


def test_load_session_labels_empty_timeline_returns_empty_dict(store):
    assert load_session_labels(store.db) == {}


def test_load_session_labels_groups_sessions_and_omits_empty_labels(store):
    _tl(store, "s-derek", "2026-01-01T07:00:00Z", 0, SS, DEREK_DEEP)
    _tl(store, "s-derek", "2026-01-01T07:30:00Z", 0, CC, DEREK_ROOT)
    _tl(store, "s-sumit", "2026-01-01T08:00:00Z", 0, SS, SUMIT)
    _tl(store, "s-sumit", "2026-01-01T08:05:00Z", 0, CC, SUMIT_INNER)
    _tl(store, "s-scratch", "2026-01-01T09:00:00Z", 0, SS,
        "C:\\Users\\Bob\\.claude\\projects\\x\\scratchpad")
    _tl(store, "s-home", "2026-01-01T09:30:00Z", 0, SS, "C:\\Users\\Bob")
    _tl(store, "s-empty", "2026-01-01T10:00:00Z", 0, CC, "")          # only an empty cwd
    _tl(store, "s-blank", "2026-01-01T10:00:00Z", 0, SS, "   ")       # only a blank cwd
    store.commit()

    assert load_session_labels(store.db) == {
        "s-derek": "local:Dashnoard",
        "s-sumit": "local:ai-presales-agent-main",
        "s-scratch": SCRATCHPAD_LABEL,
        "s-home": HOME_LABEL,
    }


def test_load_session_labels_orders_each_session_by_ts_then_seq(store):
    # Inserted out of order; the earliest (ts, seq) row is the start folder.
    _tl(store, "s-order", "2026-01-01T00:00:05Z", 0, CC, "C:\\Z\\late")
    _tl(store, "s-order", "2026-01-01T00:00:01Z", 7, CC, "C:\\Z\\second-in-second")
    _tl(store, "s-order", "2026-01-01T00:00:01Z", 3, CC, "C:\\Z\\early")
    store.commit()
    assert load_session_labels(store.db) == {"s-order": "local:early"}


def test_load_session_labels_issues_exactly_one_select_and_no_writes(store):
    _tl(store, "s1", "2026-01-01T00:00:00Z", 0, SS, "C:\\Y\\proj")
    _tl(store, "s2", "2026-01-01T00:00:00Z", 0, SS, "C:\\Y\\other")
    store.commit()
    changes_before = store.db.total_changes
    tables_before = {r[0] for r in store.db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}

    statements: list[str] = []
    store.db.set_trace_callback(statements.append)
    try:
        labels = load_session_labels(store.db)
    finally:
        store.db.set_trace_callback(None)

    assert labels == {"s1": "local:proj", "s2": "local:other"}
    assert len(statements) == 1, statements
    stmt = " ".join(statements[0].split())
    assert stmt == ("SELECT session_id, event, cwd FROM session_repo_timeline "
                    "ORDER BY session_id, ts, seq")
    assert store.db.total_changes == changes_before
    assert not store.db.in_transaction
    assert {r[0] for r in store.db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")} == tables_before


def test_load_session_labels_is_recomputed_from_the_timeline_each_call(store):
    _tl(store, "s1", "2026-01-01T00:00:00Z", 0, SS, "C:\\Y\\proj")
    store.commit()
    assert load_session_labels(store.db) == {"s1": "local:proj"}
    # A late / corrected timeline row must change the answer: nothing is cached.
    _tl(store, "s1", "2026-01-01T00:00:00Z", 1, CC, "C:\\Y")
    store.commit()
    assert load_session_labels(store.db) == {"s1": "local:Y"}
