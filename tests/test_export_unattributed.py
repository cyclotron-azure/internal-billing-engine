"""Tests for the `unknown`-row split in billing/otel/export.py.

Covers tasks 02/03 of the `unattributed-usage-breakdown` goal: both lake CSVs gain
trailing `attribution_source` and `unattributed_project` columns; rows billed to a real
repo keep their grain; `unknown` rows split by attribution class and session project
label with totals conserved; usage that collapses onto one export key after model /
user normalization is now SUMMED (collision correction) so the export equals the
database and `invoice.py`.

Every store is an OtelStore under `tmp_path`; nothing touches the network, ADLS or
`data/otel.db`. Seeding is local to this file (conftest.py is not touched).
"""

from __future__ import annotations

import csv
import os
import re
import sys
from datetime import datetime, timezone
from unittest import mock

import pytest

from billing.otel import export, invoice
from billing.otel.otel_store import OtelStore

MARKUP = 1.5
NEW_COLUMNS = ["attribution_source", "unattributed_project"]

# The header lists as they were BEFORE the change (hard-coded on purpose).
PRE_CHANGE_SUMMARY_FIELDS = [
    "usage_date_utc", "period_start", "period_end", "repo", "user_email", "tokens",
    "actual_cost_usd", "markup", "total_billed_usd", "first_usage_at_utc",
    "last_usage_at_utc", "generated_at"]
PRE_CHANGE_LINE_FIELDS = [
    "usage_date_utc", "period_start", "period_end", "repo", "repo_key", "model",
    "user_email", "tokens", "actual_cost_usd", "billed_usd", "first_usage_at_utc",
    "last_usage_at_utc", "generated_at"]

ACME = "github.com/cyclotron/acme-web"
ACME_RAW = "git@github.com:Cyclotron/Acme-Web.git"
GLOBEX = "github.com/cyclotron/globex-api"
GLOBEX_RAW = "https://github.com/Cyclotron/Globex-Api.git"

DEREK_DEEP = ("C:\\Users\\DerekMcConnell\\OneDrive - Cyclotron Inc\\Code\\Dashnoard"
              "\\OfficeDashboard\\backend")
DEREK_ROOT = "C:\\Users\\DerekMcConnell\\OneDrive - Cyclotron Inc\\Code\\Dashnoard"
SCRATCH_CWD = "C:\\Users\\Bob\\.claude\\projects\\C--Users-Bob-proj\\scratchpad"
GLOBEX_CWD = "C:\\Cyclotron\\globex-api"

# Every full path seeded into any store below; none may reach either CSV.
SEEDED_PATHS = [
    DEREK_DEEP, DEREK_ROOT, SCRATCH_CWD, GLOBEX_CWD,
    "C:\\Users\\DerekMcConnell", "C:\\Users\\Alice\\OneDrive - Contoso\\Code\\Alice",
    "/home/carol/.claude/projects/-home-carol-proj", "C:\\Users\\Dave\\Code\\payments",
    "C:\\Cyclotron\\newproj",
]
SEEDED_USERNAMES = ["DerekMcConnell", "Bob", "Alice", "carol", "Dave"]


# ---------------------------------------------------------------------------
# seeding helpers
# ---------------------------------------------------------------------------

def _nano(iso: str) -> int:
    dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return int(dt.timestamp()) * 10**9


def _tok(store, *, session, repo, repo_raw, email, model, ttype, n, when,
         transcript_req=None):
    kw = {}
    if transcript_req:
        kw = dict(usage_source="transcript", entrypoint="claude-desktop",
                  request_id=transcript_req)
    assert store.insert_datapoint(
        session_id=session, repo=repo, repo_raw=repo_raw, user_email=email,
        user_id="u", org_id="o", model=model, token_type=ttype, query_source="main",
        tokens=n, time_unix_nano=_nano(when), **kw)


def _cost(store, *, session, repo, repo_raw, email, model, usd, when,
          transcript_req=None):
    kw = {}
    if transcript_req:
        kw = dict(usage_source="transcript", cost_source="rate_card",
                  request_id=transcript_req)
    assert store.insert_cost_datapoint(
        session_id=session, repo=repo, repo_raw=repo_raw, user_email=email,
        user_id="u", org_id="o", model=model, query_source="main", cost_usd=usd,
        time_unix_nano=_nano(when), **kw)


def _timeline(store, session, ts, seq, event, cwd, repo="unknown"):
    store.insert_session_repo(session_id=session, ts=ts, seq=seq, repo=repo,
                              repo_raw="", cwd=cwd, event=event)


def _seed_main(store):
    """Collision-free store: two attributed sessions and four unknown sessions
    (one per attribution class) sharing one day and one user."""
    # A1: wrapper-attributed acme-web, alice, 2026-01-01.
    a1 = dict(session="sess-attr-1", repo=ACME, repo_raw=ACME_RAW,
              email="alice@cyclotron.com", model="claude-sonnet-5")
    _cost(store, usd=10.0, when="2026-01-01T10:00:00Z", **a1)
    _tok(store, ttype="input", n=100000, when="2026-01-01T10:00:00Z", **a1)
    _tok(store, ttype="output", n=50000, when="2026-01-01T11:30:00Z", **a1)

    # A2: timeline-attributed globex-api, bob, 2026-01-02 (has a cwd -> would label).
    a2 = dict(session="sess-attr-2", repo=GLOBEX, repo_raw=GLOBEX_RAW,
              email="bob@cyclotron.com", model="claude-opus-4-8")
    _timeline(store, "sess-attr-2", "2026-01-02T08:59:00Z", 0, "SessionStart",
              GLOBEX_CWD, repo=GLOBEX)
    _cost(store, usd=20.0, when="2026-01-02T09:00:00Z", **a2)
    _tok(store, ttype="input", n=150000, when="2026-01-02T09:00:00Z", **a2)
    _tok(store, ttype="output", n=80000, when="2026-01-02T09:05:00Z", **a2)

    derek = dict(email="derek@cyclotron.com", model="claude-sonnet-5")

    # U1: Derek-shaped, timeline rows with repo 'unknown' -> timeline / local:Dashnoard.
    u1 = dict(session="sess-derek", repo="unknown", repo_raw="", **derek)
    _timeline(store, "sess-derek", "2026-01-03T07:00:00Z", 0, "SessionStart", DEREK_DEEP)
    _timeline(store, "sess-derek", "2026-01-03T07:30:00Z", 0, "CwdChanged", DEREK_ROOT)
    _cost(store, usd=4.0, when="2026-01-03T08:00:00Z", **u1)
    _cost(store, usd=1.0, when="2026-01-03T12:00:00Z", **u1)
    _tok(store, ttype="input", n=1000, when="2026-01-03T08:00:00Z", **u1)
    _tok(store, ttype="output", n=500, when="2026-01-03T12:00:00Z", **u1)

    # U2: no timeline, empty wrapper tag -> absent / "".
    u2 = dict(session="sess-nolink", repo="unknown", repo_raw="", **derek)
    _cost(store, usd=2.0, when="2026-01-03T15:00:00Z", **u2)
    _tok(store, ttype="input", n=700, when="2026-01-03T15:00:00Z", **u2)
    _tok(store, ttype="output", n=300, when="2026-01-03T16:30:00Z", **u2)

    # U3: no timeline, wrapper ran without a remote -> no_remote / "".
    u3 = dict(session="sess-noremote", repo="unknown", repo_raw="/srv/local/checkout",
              **derek)
    _cost(store, usd=0.5, when="2026-01-03T20:00:00Z", **u3)
    _tok(store, ttype="input", n=200, when="2026-01-03T20:00:00Z", **u3)

    # U4: desktop transcript session that never left a scratch dir.
    u4 = dict(session="sess-scratch", repo="unknown", repo_raw="", transcript_req="req-s1",
              **derek)
    _timeline(store, "sess-scratch", "2026-01-03T20:59:00Z", 0, "SessionStart", SCRATCH_CWD)
    _cost(store, usd=0.25, when="2026-01-03T21:00:00Z", **u4)
    _tok(store, ttype="input", n=100, when="2026-01-03T21:00:00Z", **u4)
    store.commit()


# Hard-coded pre-change expectations (collision-free store => identical before/after).
ATTRIBUTED_LINE_ROWS = [
    {"usage_date_utc": "2026-01-01", "period_start": "2026-01-01", "period_end": "2026-02-01",
     "repo": "acme-web", "repo_key": ACME, "model": "claude-sonnet-5",
     "user_email": "alice@cyclotron.com", "tokens": 150000, "actual_cost_usd": 10.0,
     "billed_usd": 15.0, "first_usage_at_utc": "2026-01-01T10:00:00Z",
     "last_usage_at_utc": "2026-01-01T11:30:00Z"},
    {"usage_date_utc": "2026-01-02", "period_start": "2026-01-01", "period_end": "2026-02-01",
     "repo": "globex-api", "repo_key": GLOBEX, "model": "claude-opus-4-8",
     "user_email": "bob@cyclotron.com", "tokens": 230000, "actual_cost_usd": 20.0,
     "billed_usd": 30.0, "first_usage_at_utc": "2026-01-02T09:00:00Z",
     "last_usage_at_utc": "2026-01-02T09:05:00Z"},
]
ATTRIBUTED_SUMMARY_ROWS = [
    {"usage_date_utc": "2026-01-01", "period_start": "2026-01-01", "period_end": "2026-02-01",
     "repo": "acme-web", "user_email": "alice@cyclotron.com", "tokens": 150000,
     "actual_cost_usd": 10.0, "markup": MARKUP, "total_billed_usd": 15.0,
     "first_usage_at_utc": "2026-01-01T10:00:00Z", "last_usage_at_utc": "2026-01-01T11:30:00Z"},
    {"usage_date_utc": "2026-01-02", "period_start": "2026-01-01", "period_end": "2026-02-01",
     "repo": "globex-api", "user_email": "bob@cyclotron.com", "tokens": 230000,
     "actual_cost_usd": 20.0, "markup": MARKUP, "total_billed_usd": 30.0,
     "first_usage_at_utc": "2026-01-02T09:00:00Z", "last_usage_at_utc": "2026-01-02T09:05:00Z"},
]
# (attribution_source, unattributed_project) -> (session, tokens, cost, first, last)
UNKNOWN_SPLIT = {
    ("timeline", "local:Dashnoard"):
        ("sess-derek", 1500, 5.0, "2026-01-03T08:00:00Z", "2026-01-03T12:00:00Z"),
    ("absent", ""):
        ("sess-nolink", 1000, 2.0, "2026-01-03T15:00:00Z", "2026-01-03T16:30:00Z"),
    ("no_remote", ""):
        ("sess-noremote", 200, 0.5, "2026-01-03T20:00:00Z", "2026-01-03T20:00:00Z"),
    ("desktop-scratch", "local:(scratchpad)"):
        ("sess-scratch", 100, 0.25, "2026-01-03T21:00:00Z", "2026-01-03T21:00:00Z"),
}


def _seed_collisions(store):
    """Attributed usage whose raw models collapse under normalize_model and whose
    users collapse across NULL / '' / 'unknown'; plus a colliding unknown session."""
    entries = [
        (None, "claude-sonnet-5", 1.0, 10),
        (None, "claude-sonnet-5[1m]", 2.0, 20),
        (None, "claude-sonnet-5-20251001", 4.0, 40),
        ("", "claude-sonnet-5", 8.0, 80),
        ("", "claude-sonnet-5[1m]", 16.0, 160),
        ("", "claude-sonnet-5-20251001", 32.0, 320),
        ("unknown", "claude-sonnet-5", 64.0, 640),
        ("alice@cyclotron.com", "claude-sonnet-5", 0.5, 5),
        ("alice@cyclotron.com", "claude-sonnet-5[1m]", 0.25, 3),
    ]
    for i, (email, model, usd, n) in enumerate(entries):
        when = f"2026-01-05T10:{i:02d}:00Z"
        base = dict(session="sess-coll", repo=ACME, repo_raw=ACME_RAW, email=email,
                    model=model)
        _cost(store, usd=usd, when=when, **base)
        _tok(store, ttype="input", n=n, when=when, **base)

    unk = [("claude-haiku-4-5", 1.0, 7), ("claude-haiku-4-5-20251001", 2.0, 9),
           ("", 0.125, 1), (None, 0.125, 1)]
    for i, (model, usd, n) in enumerate(unk):
        when = f"2026-01-05T11:{i:02d}:00Z"
        base = dict(session="sess-coll-unk", repo="unknown", repo_raw="",
                    email="u@cyclotron.com", model=model)
        _cost(store, usd=usd, when=when, **base)
        _tok(store, ttype="input", n=n, when=when, **base)
    store.commit()


def _seed_hostile(store):
    """Unknown sessions whose cwds are packed with things that must never leak."""
    cwds = {
        "h-home": "C:\\Users\\DerekMcConnell",
        "h-oneshare": "C:\\Users\\Alice\\OneDrive - Contoso\\Code\\Alice",
        "h-claude": "/home/carol/.claude/projects/-home-carol-proj",
        "h-clean": "C:\\Users\\Dave\\Code\\payments",
    }
    for i, (sid, cwd) in enumerate(cwds.items()):
        _timeline(store, sid, "2026-01-04T00:00:00Z", 0, "SessionStart", cwd)
        base = dict(session=sid, repo="unknown", repo_raw="", email="h@cyclotron.com",
                    model="claude-sonnet-5")
        _cost(store, usd=1.0, when=f"2026-01-04T01:0{i}:00Z", **base)
        _tok(store, ttype="input", n=10, when=f"2026-01-04T01:0{i}:00Z", **base)
    store.commit()


def _open(tmp_path, name, seeder):
    store = OtelStore(str(tmp_path / name))
    seeder(store)
    return store


@pytest.fixture
def main_store(tmp_path):
    store = _open(tmp_path, "main.db", _seed_main)
    try:
        yield store
    finally:
        store.close()


@pytest.fixture
def collision_store(tmp_path):
    store = _open(tmp_path, "coll.db", _seed_collisions)
    try:
        yield store
    finally:
        store.close()


@pytest.fixture
def hostile_store(tmp_path):
    store = _open(tmp_path, "hostile.db", _seed_hostile)
    try:
        yield store
    finally:
        store.close()


# ---------------------------------------------------------------------------
# reading / summarising helpers
# ---------------------------------------------------------------------------

def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        return reader.fieldnames, rows


def _write_and_read(store, out_dir):
    export.build_and_enqueue(store, MARKUP, str(out_dir))
    s_path = os.path.join(str(out_dir), f"{export.SUMMARY_TABLE}.csv")
    l_path = os.path.join(str(out_dir), f"{export.LINEITEMS_TABLE}.csv")
    return _read_csv(s_path), _read_csv(l_path), (s_path, l_path)


def _strip(rows, drop=("generated_at", "attribution_source", "unattributed_project")):
    return [{k: v for k, v in r.items() if k not in drop} for r in rows]


def _norm_model(m):
    """Independent restatement of the billing model identity."""
    if not m:
        return "unknown"
    m = re.sub(r"\[[^\]]*\]", "", m)
    m = re.sub(r"-\d{8}$", "", m)
    return m.strip() or "unknown"


def _db_totals(store):
    """{(day, normalized model, user): [tokens, cost]} straight from the raw tables."""
    tot = {}
    for r in store.db.execute(
            "SELECT substr(ts,1,10) d, model, user_email, SUM(tokens) t "
            "FROM token_usage GROUP BY 1,2,3"):
        k = (r["d"], _norm_model(r["model"]), r["user_email"] or "unknown")
        tot.setdefault(k, [0, 0.0])[0] += r["t"]
    for r in store.db.execute(
            "SELECT substr(ts,1,10) d, model, user_email, SUM(cost_usd) c "
            "FROM cost_usage GROUP BY 1,2,3"):
        k = (r["d"], _norm_model(r["model"]), r["user_email"] or "unknown")
        tot.setdefault(k, [0, 0.0])[1] += r["c"]
    return tot


def _export_totals(line_rows):
    tot = {}
    for r in line_rows:
        k = (r["usage_date_utc"], r["model"], r["user_email"])
        cur = tot.setdefault(k, [0, 0.0])
        cur[0] += int(r["tokens"])
        cur[1] += float(r["actual_cost_usd"])
    return tot


def _assert_totals_equal(a, b):
    assert set(a) == set(b)
    for k in a:
        assert a[k][0] == b[k][0], k
        assert a[k][1] == pytest.approx(b[k][1], abs=1e-6), k


def _invoice_flat(store):
    ents = invoice.gather(store, "2026-01-01", "2026-02-01")
    flat = {}
    for items in ents.values():
        for (repo, model), v in items.items():
            flat[(repo, model)] = (v["tokens"], v["actual_cost"], v["estimated_cost"])
    return flat


# ---------------------------------------------------------------------------
# schema / headers
# ---------------------------------------------------------------------------

def test_field_lists_append_the_two_new_columns_after_the_pre_change_lists():
    assert export.SUMMARY_FIELDS == PRE_CHANGE_SUMMARY_FIELDS + NEW_COLUMNS
    assert export.LINE_FIELDS == PRE_CHANGE_LINE_FIELDS + NEW_COLUMNS
    assert export.SUMMARY_FIELDS[-3] == "generated_at"
    assert export.LINE_FIELDS[-3] == "generated_at"


def test_csv_headers_end_with_new_columns_and_keep_earlier_order(main_store, tmp_path):
    (s_head, _), (l_head, _), _ = _write_and_read(main_store, tmp_path / "out")
    assert s_head == PRE_CHANGE_SUMMARY_FIELDS + NEW_COLUMNS
    assert l_head == PRE_CHANGE_LINE_FIELDS + NEW_COLUMNS
    assert s_head[-2:] == l_head[-2:] == NEW_COLUMNS


def test_cli_main_no_enqueue_writes_headers_and_queues_nothing(tmp_path, monkeypatch, capsys):
    db = str(tmp_path / "cli.db")
    store = _open(tmp_path, "cli.db", _seed_main)
    store.close()
    out = str(tmp_path / "cli_out")
    monkeypatch.setattr(sys, "argv", ["export", "--db", db, "--out-dir", out,
                                      "--no-enqueue"])
    export.main()

    printed = capsys.readouterr().out
    s_head, s_rows = _read_csv(os.path.join(out, "claudeusagesummary.csv"))
    l_head, l_rows = _read_csv(os.path.join(out, "claudeusagelineitems.csv"))
    assert s_head[-2:] == l_head[-2:] == NEW_COLUMNS
    assert f"{len(s_rows)} row(s)" in printed and f"{len(l_rows)} row(s)" in printed
    reopened = OtelStore(db)
    try:
        assert reopened.fabric_outbox_counts() == {}
    finally:
        reopened.close()


# ---------------------------------------------------------------------------
# attributed rows unchanged
# ---------------------------------------------------------------------------

def test_attributed_line_rows_match_hard_coded_pre_change_baseline(main_store):
    _, line_rows = export.build(main_store, MARKUP)
    attributed = [r for r in line_rows if r["repo_key"] != "unknown"]
    assert _strip(attributed) == ATTRIBUTED_LINE_ROWS
    for r in attributed:
        assert r["attribution_source"] == ""
        assert r["unattributed_project"] == ""


def test_attributed_summary_rows_match_hard_coded_pre_change_baseline(main_store):
    summary_rows, _ = export.build(main_store, MARKUP)
    attributed = [r for r in summary_rows if r["repo"] != "unknown"]
    assert _strip(attributed) == ATTRIBUTED_SUMMARY_ROWS
    for r in attributed:
        assert r["attribution_source"] == "" and r["unattributed_project"] == ""


def test_attributed_csv_cells_for_new_columns_are_empty_strings(main_store, tmp_path):
    (_, s_rows), (_, l_rows), _ = _write_and_read(main_store, tmp_path / "out")
    attributed_l = [r for r in l_rows if r["repo_key"] != "unknown"]
    attributed_s = [r for r in s_rows if r["repo"] != "unknown"]
    assert len(attributed_l) == 2 and len(attributed_s) == 2
    for r in attributed_l + attributed_s:
        assert r["attribution_source"] == "" and r["unattributed_project"] == ""


def test_attributed_session_with_a_cwd_never_receives_a_label(main_store):
    """sess-attr-2 has a timeline cwd that WOULD label as local:globex-api."""
    _, line_rows = export.build(main_store, MARKUP)
    globex = [r for r in line_rows if r["repo_key"] == GLOBEX]
    assert len(globex) == 1 and globex[0]["unattributed_project"] == ""


# ---------------------------------------------------------------------------
# unknown split
# ---------------------------------------------------------------------------

def _unknown(rows, key="repo_key"):
    return [r for r in rows if r[key] == "unknown"]


def test_unknown_rows_split_into_one_row_per_class_and_label(main_store):
    _, line_rows = export.build(main_store, MARKUP)
    unknown = _unknown(line_rows)
    assert {(r["attribution_source"], r["unattributed_project"]) for r in unknown} == set(
        UNKNOWN_SPLIT)
    assert len(unknown) == len(UNKNOWN_SPLIT)      # one row per split, none merged/duplicated
    for r in unknown:
        session, tokens, cost, first, last = UNKNOWN_SPLIT[
            (r["attribution_source"], r["unattributed_project"])]
        assert r["usage_date_utc"] == "2026-01-03"
        assert r["repo"] == "unknown" and r["repo_key"] == "unknown"
        assert r["model"] == "claude-sonnet-5"
        assert r["user_email"] == "derek@cyclotron.com"
        assert r["tokens"] == tokens, session
        assert r["actual_cost_usd"] == pytest.approx(cost)
        assert r["billed_usd"] == pytest.approx(cost * MARKUP)
        assert r["first_usage_at_utc"] == first, session
        assert r["last_usage_at_utc"] == last, session


def test_derek_shaped_session_and_no_timeline_session_are_separate_rows(main_store):
    _, line_rows = export.build(main_store, MARKUP)
    by = {(r["attribution_source"], r["unattributed_project"]): r
          for r in _unknown(line_rows)}
    derek = by[("timeline", "local:Dashnoard")]
    nolink = by[("absent", "")]
    assert derek is not nolink
    assert (derek["usage_date_utc"], derek["user_email"], derek["model"]) == (
        nolink["usage_date_utc"], nolink["user_email"], nolink["model"])
    assert (derek["tokens"], nolink["tokens"]) == (1500, 1000)
    # no_remote also stays unlabelled but is a distinct class
    assert by[("no_remote", "")]["tokens"] == 200


def test_summary_unknown_rows_split_the_same_way(main_store):
    summary_rows, _ = export.build(main_store, MARKUP)
    unknown = _unknown(summary_rows, key="repo")
    assert len(unknown) == len(UNKNOWN_SPLIT)
    for r in unknown:
        _, tokens, cost, first, last = UNKNOWN_SPLIT[
            (r["attribution_source"], r["unattributed_project"])]
        assert r["tokens"] == tokens
        assert r["actual_cost_usd"] == pytest.approx(cost)
        assert r["total_billed_usd"] == pytest.approx(cost * MARKUP)
        assert r["markup"] == MARKUP
        assert (r["first_usage_at_utc"], r["last_usage_at_utc"]) == (first, last)


def test_attribution_source_comes_from_resolved_view_and_wrapper_never_appears(main_store):
    from billing.otel.attribute import resolved_view
    expected = {}
    for table in ("token_usage", "cost_usage"):
        for r in main_store.db.execute(
                f"WITH r AS ({resolved_view(table)}) "
                "SELECT DISTINCT session_id, attribution_source FROM r "
                "WHERE resolved_repo = 'unknown'"):
            expected[r["session_id"]] = r["attribution_source"]
    _, line_rows = export.build(main_store, MARKUP)
    got = {UNKNOWN_SPLIT[(r["attribution_source"], r["unattributed_project"])][0]:
           r["attribution_source"] for r in _unknown(line_rows)}
    assert got == expected
    assert "wrapper" not in {r["attribution_source"] for r in _unknown(line_rows)}


def test_sessions_sharing_a_class_and_label_merge_into_one_row_with_combined_span(tmp_path):
    store = OtelStore(str(tmp_path / "merge.db"))
    try:
        for sid, hh in (("m1", "05"), ("m2", "18")):
            base = dict(session=sid, repo="unknown", repo_raw="", email="d@cyclotron.com",
                        model="claude-sonnet-5")
            _timeline(store, sid, f"2026-01-06T{hh}:00:00Z", 0, "SessionStart", DEREK_ROOT)
            _cost(store, usd=1.0, when=f"2026-01-06T{hh}:10:00Z", **base)
            _tok(store, ttype="input", n=100, when=f"2026-01-06T{hh}:10:00Z", **base)
        # a third session with no timeline stays a separate row
        base = dict(session="m3", repo="unknown", repo_raw="", email="d@cyclotron.com",
                    model="claude-sonnet-5")
        _cost(store, usd=9.0, when="2026-01-06T12:00:00Z", **base)
        _tok(store, ttype="input", n=900, when="2026-01-06T12:00:00Z", **base)
        store.commit()

        _, line_rows = export.build(store, MARKUP)
    finally:
        store.close()
    by = {(r["attribution_source"], r["unattributed_project"]): r for r in line_rows}
    assert set(by) == {("timeline", "local:Dashnoard"), ("absent", "")}
    merged = by[("timeline", "local:Dashnoard")]
    assert merged["tokens"] == 200 and merged["actual_cost_usd"] == pytest.approx(2.0)
    assert merged["first_usage_at_utc"] == "2026-01-06T05:10:00Z"
    assert merged["last_usage_at_utc"] == "2026-01-06T18:10:00Z"
    assert by[("absent", "")]["tokens"] == 900


def test_span_of_each_split_row_is_min_max_of_its_own_datapoints(main_store):
    _, line_rows = export.build(main_store, MARKUP)
    for r in _unknown(line_rows):
        session = UNKNOWN_SPLIT[(r["attribution_source"], r["unattributed_project"])][0]
        stamps = [x[0] for x in main_store.db.execute(
            "SELECT ts FROM token_usage WHERE session_id=? "
            "UNION ALL SELECT ts FROM cost_usage WHERE session_id=?", (session, session))]
        assert r["first_usage_at_utc"] == min(stamps)
        assert r["last_usage_at_utc"] == max(stamps)


# ---------------------------------------------------------------------------
# conservation and collision correction
# ---------------------------------------------------------------------------

def test_split_rows_conserve_tokens_and_cost_against_the_database(main_store):
    summary_rows, line_rows = export.build(main_store, MARKUP)
    db = _db_totals(main_store)
    _assert_totals_equal(_export_totals(line_rows), db)
    # hard-coded anchor so a DB-helper bug cannot hide a regression
    assert db[("2026-01-03", "claude-sonnet-5", "derek@cyclotron.com")][0] == 2800
    assert db[("2026-01-03", "claude-sonnet-5", "derek@cyclotron.com")][1] == pytest.approx(7.75)
    # summary conserves per (day, user) too
    want, got = {}, {}
    for (d, _m, u), (t, c) in db.items():
        cur = want.setdefault((d, u), [0, 0.0])
        cur[0] += t
        cur[1] += c
    for r in summary_rows:
        cur = got.setdefault((r["usage_date_utc"], r["user_email"]), [0, 0.0])
        cur[0] += r["tokens"]
        cur[1] += r["actual_cost_usd"]
    _assert_totals_equal(got, want)


def test_collision_store_export_equals_database(collision_store):
    summary_rows, line_rows = export.build(collision_store, MARKUP)
    db = _db_totals(collision_store)
    _assert_totals_equal(_export_totals(line_rows), db)

    unknown_user = next(r for r in line_rows
                        if r["repo_key"] == ACME and r["user_email"] == "unknown")
    assert unknown_user["model"] == "claude-sonnet-5"
    assert unknown_user["tokens"] == 10 + 20 + 40 + 80 + 160 + 320 + 640 == 1270
    assert unknown_user["actual_cost_usd"] == pytest.approx(127.0)
    alice = next(r for r in line_rows
                 if r["repo_key"] == ACME and r["user_email"] == "alice@cyclotron.com")
    assert alice["tokens"] == 8 and alice["actual_cost_usd"] == pytest.approx(0.75)

    # exactly one row per (repo, model, user) for the attributed repo: nothing overwritten
    keys = [(r["usage_date_utc"], r["repo_key"], r["model"], r["user_email"])
            for r in line_rows if r["repo_key"] == ACME]
    assert len(keys) == len(set(keys)) == 2

    # the summary equals the database as well
    assert sum(r["tokens"] for r in summary_rows) == sum(t for t, _ in db.values())
    assert sum(r["actual_cost_usd"] for r in summary_rows) == pytest.approx(
        sum(c for _, c in db.values()), abs=1e-6)


def test_collision_store_colliding_unknown_models_are_summed_not_overwritten(collision_store):
    _, line_rows = export.build(collision_store, MARKUP)
    unk = {r["model"]: r for r in _unknown(line_rows)}
    assert set(unk) == {"claude-haiku-4-5", "unknown"}
    assert unk["claude-haiku-4-5"]["tokens"] == 16
    assert unk["claude-haiku-4-5"]["actual_cost_usd"] == pytest.approx(3.0)
    assert unk["unknown"]["tokens"] == 2                    # '' and NULL models both collapse
    assert unk["unknown"]["actual_cost_usd"] == pytest.approx(0.25)
    for r in unk.values():
        assert (r["attribution_source"], r["unattributed_project"]) == ("absent", "")


def test_collision_store_matches_invoice_per_repo_model(collision_store):
    _, line_rows = export.build(collision_store, MARKUP)
    exp = {}
    for r in line_rows:
        cur = exp.setdefault((r["repo_key"], r["model"]), [0, 0.0])
        cur[0] += int(r["tokens"])
        cur[1] += float(r["actual_cost_usd"])
    inv = {k: (t, a + e) for k, (t, a, e) in _invoice_flat(collision_store).items()}
    assert set(exp) == set(inv)
    for k, (t, c) in inv.items():
        assert exp[k][0] == t, k
        assert exp[k][1] == pytest.approx(c, abs=1e-6), k


def test_main_store_matches_invoice_per_repo_model_including_the_split_unknown(main_store):
    _, line_rows = export.build(main_store, MARKUP)
    exp = {}
    for r in line_rows:
        cur = exp.setdefault((r["repo_key"], r["model"]), [0, 0.0])
        cur[0] += r["tokens"]
        cur[1] += r["actual_cost_usd"]
    inv = {k: (t, a + e) for k, (t, a, e) in _invoice_flat(main_store).items()}
    assert set(exp) == set(inv)
    for k, (t, c) in inv.items():
        assert exp[k][0] == t and exp[k][1] == pytest.approx(c, abs=1e-6), k


# ---------------------------------------------------------------------------
# invoice.py untouched by the export
# ---------------------------------------------------------------------------

def test_invoice_totals_are_unchanged_by_the_export(main_store, tmp_path):
    before = _invoice_flat(main_store)
    assert before == {
        (ACME, "claude-sonnet-5"): (150000, 10.0, 0.0),
        (GLOBEX, "claude-opus-4-8"): (230000, 20.0, 0.0),
        ("unknown", "claude-sonnet-5"): (2800, 7.5, 0.25),
    }
    export.build_and_enqueue(main_store, MARKUP, str(tmp_path / "out"))
    assert _invoice_flat(main_store) == before


def test_invoice_billing_names_do_not_include_any_label(main_store):
    ents = invoice.gather(main_store, "2026-01-01", "2026-02-01")
    assert set(ents) == {"acme-web", "globex-api", "unknown"}


# ---------------------------------------------------------------------------
# diagnostic isolation: repo_name_map, repo / repo_key
# ---------------------------------------------------------------------------

def _split_signature(rows):
    return sorted((r["attribution_source"], r["unattributed_project"],
                   r["tokens"], round(float(r["actual_cost_usd"]), 6))
                  for r in rows if r["attribution_source"] != "")


def test_repo_name_map_override_of_a_real_repo_does_not_change_the_split(main_store):
    _, base = export.build(main_store, MARKUP)
    main_store.set_mapping(ACME, "Acme Client")
    main_store.commit()
    _, mapped = export.build(main_store, MARKUP)

    assert _split_signature(mapped) == _split_signature(base)
    renamed = [r for r in mapped if r["repo_key"] == ACME]
    assert len(renamed) == 1 and renamed[0]["repo"] == "Acme Client"
    assert renamed[0]["attribution_source"] == "" and renamed[0]["unattributed_project"] == ""
    assert len(mapped) == len(base)


def test_mapping_a_real_repo_to_the_name_unknown_stays_unsplit_with_blank_class(main_store):
    main_store.set_mapping(ACME, "unknown")
    main_store.commit()
    summary_rows, line_rows = export.build(main_store, MARKUP)

    acme = [r for r in line_rows if r["repo_key"] == ACME]
    assert len(acme) == 1
    assert acme[0]["repo"] == "unknown"
    assert acme[0]["attribution_source"] == "" and acme[0]["unattributed_project"] == ""
    # the genuine unknown rows are still split, unaffected by the bill-name collision
    genuine = [r for r in line_rows if r["repo_key"] == "unknown"]
    assert {(r["attribution_source"], r["unattributed_project"]) for r in genuine} == set(
        UNKNOWN_SPLIT)
    # the summary keys on bill name, but the blank-class row is not merged into a split row
    acme_summary = [r for r in summary_rows if r["user_email"] == "alice@cyclotron.com"]
    assert len(acme_summary) == 1 and acme_summary[0]["attribution_source"] == ""


def test_mapping_the_unknown_key_renames_the_bill_but_keeps_the_split(main_store):
    main_store.set_mapping("unknown", "Misc")
    main_store.commit()
    summary_rows, line_rows = export.build(main_store, MARKUP)
    misc = [r for r in line_rows if r["repo_key"] == "unknown"]
    assert len(misc) == len(UNKNOWN_SPLIT)
    assert {r["repo"] for r in misc} == {"Misc"}
    assert {(r["attribution_source"], r["unattributed_project"]) for r in misc} == set(
        UNKNOWN_SPLIT)
    assert len([r for r in summary_rows if r["repo"] == "Misc"]) == len(UNKNOWN_SPLIT)


def test_label_never_appears_in_repo_or_repo_key(main_store, tmp_path):
    main_store.set_mapping(ACME, "Acme Client")
    main_store.commit()
    (_, s_rows), (_, l_rows), _ = _write_and_read(main_store, tmp_path / "out")
    labels = {r["unattributed_project"] for r in l_rows if r["unattributed_project"]}
    assert labels == {"local:Dashnoard", "local:(scratchpad)"}
    for r in l_rows:
        assert "local:" not in r["repo"] and "local:" not in r["repo_key"]
        assert not ({r["repo"], r["repo_key"]} & labels)
    for r in s_rows:
        assert "local:" not in r["repo"] and r["repo"] not in labels


# ---------------------------------------------------------------------------
# store rules: once-per-build, read-only
# ---------------------------------------------------------------------------

def test_build_loads_labels_once_and_scans_each_table_once(main_store):
    with mock.patch.object(export, "load_session_labels",
                           wraps=export.load_session_labels) as labels, \
            mock.patch.object(export, "resolved_view", wraps=export.resolved_view) as view:
        export.build(main_store, MARKUP)
    assert labels.call_count == 1
    assert sorted(c.args[0] for c in view.call_args_list) == ["cost_usage", "token_usage"]


def test_build_is_read_only_single_connection(main_store):
    tables_before = {r[0] for r in main_store.db.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','index')")}
    changes_before = main_store.db.total_changes
    statements: list[str] = []
    main_store.db.set_trace_callback(statements.append)
    try:
        export.build(main_store, MARKUP)
    finally:
        main_store.db.set_trace_callback(None)

    assert statements
    for stmt in statements:
        assert stmt.lstrip().upper().startswith(("SELECT", "WITH")), stmt
    assert main_store.db.total_changes == changes_before
    assert not main_store.db.in_transaction
    assert {r[0] for r in main_store.db.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','index')")} == tables_before


def test_labels_are_recomputed_at_query_time_from_the_timeline(main_store):
    """A late / corrected timeline retroactively relabels past usage; nothing is persisted."""
    _, before = export.build(main_store, MARKUP)
    assert ("absent", "") in {(r["attribution_source"], r["unattributed_project"])
                              for r in _unknown(before)}

    _timeline(main_store, "sess-nolink", "2026-01-03T14:00:00Z", 0, "SessionStart",
              "C:\\Cyclotron\\newproj")
    main_store.commit()
    _, after = export.build(main_store, MARKUP)
    keys = {(r["attribution_source"], r["unattributed_project"]) for r in _unknown(after)}
    assert ("timeline", "local:newproj") in keys
    assert ("absent", "") not in keys
    # totals still conserved after the relabel
    _assert_totals_equal(_export_totals(after), _db_totals(main_store))


# ---------------------------------------------------------------------------
# privacy
# ---------------------------------------------------------------------------

def _assert_private_cells(rows):
    for r in rows:
        for col in NEW_COLUMNS:
            cell = r[col]
            low = cell.lower()
            assert "/" not in cell and "\\" not in cell, cell
            assert not re.search(r"[A-Za-z]:", cell.replace("local:", "", 1)), cell
            assert re.search(r"(^|[^a-z])[a-z]:[\\/]", low) is None, cell
            assert "onedrive" not in low and ".claude" not in low, cell
            assert not re.search(r"(^|[^a-z0-9])[a-z]--", low), cell
            assert "-users-" not in low, cell
            body = cell[len("local:"):] if cell.startswith("local:") else cell
            assert body.lower() not in ("users", "home"), cell
            for name in SEEDED_USERNAMES:
                assert name.lower() != body.lower(), cell
                assert name.lower() not in low, cell
            for path in SEEDED_PATHS:
                assert path not in cell, cell


@pytest.mark.parametrize("fixture_name", ["main_store", "hostile_store"])
def test_new_columns_and_both_csvs_never_leak_paths_or_identity(
        fixture_name, request, tmp_path):
    store = request.getfixturevalue(fixture_name)
    (_, s_rows), (_, l_rows), paths = _write_and_read(store, tmp_path / "out")
    _assert_private_cells(s_rows)
    _assert_private_cells(l_rows)
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            text = fh.read()
        for path in SEEDED_PATHS:
            assert path not in text, (p, path)
            assert path.replace("\\", "/") not in text, (p, path)


def test_hostile_cwds_collapse_to_safe_labels_only(hostile_store):
    _, line_rows = export.build(hostile_store, MARKUP)
    labels = {r["unattributed_project"] for r in _unknown(line_rows)}
    assert labels == {"local:(home)", "local:(other)", "local:(scratchpad)",
                      "local:payments"}
    for r in _unknown(line_rows):
        assert r["attribution_source"] == "timeline"


def test_export_touches_no_network_or_storage_targets(main_store, tmp_path):
    """build_and_enqueue only writes local CSVs and a local outbox row."""
    export.build_and_enqueue(main_store, MARKUP, str(tmp_path / "out"))
    assert main_store.fabric_outbox_counts() == {"pending": 2}
    assert sorted(os.listdir(tmp_path / "out")) == [
        "claudeusagelineitems.csv", "claudeusagesummary.csv"]
