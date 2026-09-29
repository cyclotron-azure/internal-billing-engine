"""Tests for the work-domain email filter in billing/otel/export.py.

Covers task 02 of the `lake-work-email-filter` goal (task 01 acceptance criteria):
personal / lookalike-domain rows are absent from BOTH lake CSVs, `unknown`/NULL/empty
users and allowed-domain users are kept unchanged, ALLOWED_EMAIL_DOMAINS overrides the
default at call time, `build(stats=...)` reports distinct excluded groups and domains,
the raw store is untouched, and every export path prints the excluded line.

Every store is an OtelStore under `tmp_path`; no network, no ADLS, never data/otel.db and
never the repo's real `.env` (main() runs in a subprocess or in-process with cwd=tmp_path).
"""

from __future__ import annotations

import csv
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import billing.config
from billing.otel import export
from billing.otel.otel_store import OtelStore

MARKUP = 1.5
REPO_ROOT = str(Path(__file__).resolve().parents[1])
ACME = "github.com/cyclotron/acme-web"
ACME_RAW = "git@github.com:Cyclotron/Acme-Web.git"
MODEL = "claude-sonnet-5"
MODEL2 = "claude-opus-4-8"
GMAIL = "veltariumsoftware@gmail.com"
LOOKALIKES = ["x@cyclotron.com.au", "x@evil.cyclotron.com", "cyclotron.com@gmail.com"]
RAW_TABLES = ("token_usage", "cost_usage", "session_repo_timeline")


def _nano(iso):
    dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return int(dt.timestamp()) * 10**9


def _add(store, *, email, usd, tokens, when, session=None, model=MODEL,
         repo=ACME, repo_raw=ACME_RAW):
    session = session or f"sess-{email}-{model}-{when}-{repo}"
    assert store.insert_cost_datapoint(
        session_id=session, repo=repo, repo_raw=repo_raw, user_email=email,
        user_id="u", org_id="o", model=model, query_source="main", cost_usd=usd,
        time_unix_nano=_nano(when))
    assert store.insert_datapoint(
        session_id=session, repo=repo, repo_raw=repo_raw, user_email=email,
        user_id="u", org_id="o", model=model, token_type="input",
        query_source="main", tokens=tokens, time_unix_nano=_nano(when))


def _seed_work(store):
    """Rows that must survive the default filter (raw email is the export key)."""
    _add(store, email="alice@cyclotron.com", usd=10.0, tokens=1000, when="2026-01-01T10:00:00Z")
    _add(store, email="Y@CYCLOTRON.COM", usd=2.0, tokens=200, when="2026-01-01T11:00:00Z")
    _add(store, email=None, usd=3.0, tokens=300, when="2026-01-02T10:00:00Z")
    _add(store, email="", usd=4.0, tokens=400, when="2026-01-02T11:00:00Z")
    _add(store, email="unknown", usd=5.0, tokens=500, when="2026-01-03T10:00:00Z")


def _seed_personal(store):
    """Rows the default filter must drop. Gmail appears in both tables (cost+tokens)
    on one day/model -> ONE group; a second model on the same day -> a second group."""
    _add(store, email=GMAIL, usd=7.0, tokens=700, when="2026-01-01T12:00:00Z")
    _add(store, email=GMAIL, usd=1.5, tokens=150, when="2026-01-01T13:00:00Z", model=MODEL2)
    for i, addr in enumerate(LOOKALIKES):
        _add(store, email=addr, usd=1.0, tokens=100, when=f"2026-01-0{i + 4}T09:00:00Z")


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("ALLOWED_EMAIL_DOMAINS", raising=False)


@pytest.fixture
def store(tmp_path):
    s = OtelStore(str(tmp_path / "otel.db"))
    yield s
    s.close()


@pytest.fixture
def mixed_store(store):
    _seed_work(store)
    _seed_personal(store)
    store.commit()
    return store


@pytest.fixture
def work_only_store(tmp_path):
    s = OtelStore(str(tmp_path / "work_only.db"))
    _seed_work(s)
    s.commit()
    yield s
    s.close()


def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _strip_gen(rows):
    return [{k: v for k, v in r.items() if k != "generated_at"} for r in rows]


def _raw_dump(store):
    return {t: [tuple(r) for r in store.db.execute(f"SELECT * FROM {t} ORDER BY 1, 2, 3")]
            for t in RAW_TABLES}


def _emails(rows):
    return {r["user_email"] for r in rows}


# ---------------------------------------------------------------------------
# allowed_domains()
# ---------------------------------------------------------------------------

def test_allowed_domains_default_when_unset(clean_env):
    assert export.allowed_domains() == ("cyclotron.com",)
    assert export.DEFAULT_ALLOWED_DOMAINS == ("cyclotron.com",)


@pytest.mark.parametrize("raw", ["", "   ", ",", " , ,", "@", " @ , "])
def test_allowed_domains_blank_or_empty_falls_back_to_default(monkeypatch, raw):
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", raw)
    assert export.allowed_domains() == ("cyclotron.com",)


def test_allowed_domains_parses_strips_lowers_and_drops_at(monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "a.com, Cyclotron.com ,, @B.ORG")
    assert export.allowed_domains() == ("a.com", "cyclotron.com", "b.org")


def test_allowed_domains_read_at_call_time(monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "one.com")
    assert export.allowed_domains() == ("one.com",)
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "two.com")
    assert export.allowed_domains() == ("two.com",)
    monkeypatch.delenv("ALLOWED_EMAIL_DOMAINS")
    assert export.allowed_domains() == ("cyclotron.com",)


# ---------------------------------------------------------------------------
# is_allowed_user()
# ---------------------------------------------------------------------------

DOM = ("cyclotron.com",)


@pytest.mark.parametrize("email", [None, "", "   ", "\t", "unknown", "UNKNOWN", " Unknown "])
def test_is_allowed_user_keeps_missing_and_unknown(email):
    assert export.is_allowed_user(email, DOM) is True


@pytest.mark.parametrize("email", [
    "alice@cyclotron.com", "Y@CYCLOTRON.COM", "  bob@Cyclotron.Com  "])
def test_is_allowed_user_keeps_allowed_domain_case_insensitive(email):
    assert export.is_allowed_user(email, DOM) is True


@pytest.mark.parametrize("email", [GMAIL, *LOOKALIKES, "noatsign", "cyclotron.com"])
def test_is_allowed_user_excludes_personal_lookalike_and_no_at(email):
    assert export.is_allowed_user(email, DOM) is False


def test_is_allowed_user_uses_domain_after_last_at():
    assert export.is_allowed_user("weird@gmail.com@cyclotron.com", DOM) is True
    assert export.is_allowed_user("a@cyclotron.com@gmail.com", DOM) is False


def test_is_allowed_user_multiple_domains():
    doms = ("a.com", "cyclotron.com")
    assert export.is_allowed_user("x@a.com", doms) is True
    assert export.is_allowed_user("x@cyclotron.com", doms) is True
    assert export.is_allowed_user("x@b.com", doms) is False


# ---------------------------------------------------------------------------
# build() / both CSVs via build_and_enqueue
# ---------------------------------------------------------------------------

def test_both_csvs_exclude_personal_and_lookalikes_keep_cyclotron(
        clean_env, mixed_store, tmp_path, capsys):
    out = tmp_path / "out"
    export.build_and_enqueue(mixed_store, MARKUP, str(out))
    for name in (export.SUMMARY_TABLE, export.LINEITEMS_TABLE):
        rows = _read_csv(out / f"{name}.csv")
        emails = _emails(rows)
        assert GMAIL not in emails
        assert not (emails & set(LOOKALIKES))
        assert "alice@cyclotron.com" in emails


def test_unknown_null_and_empty_users_retained_as_unknown(
        clean_env, mixed_store, tmp_path, capsys):
    out = tmp_path / "out"
    export.build_and_enqueue(mixed_store, MARKUP, str(out))
    for name in (export.SUMMARY_TABLE, export.LINEITEMS_TABLE):
        rows = _read_csv(out / f"{name}.csv")
        unk = [r for r in rows if r["user_email"] == "unknown"]
        # NULL (300), "" (400) and literal unknown (500) all key to `unknown`.
        assert sum(int(r["tokens"]) for r in unk) == 300 + 400 + 500
        assert round(sum(float(r["actual_cost_usd"]) for r in unk), 6) == 12.0


def test_kept_key_is_raw_email_not_case_coalesced(clean_env, mixed_store):
    summary, lines = export.build(mixed_store, MARKUP)
    assert "Y@CYCLOTRON.COM" in _emails(summary)
    assert "y@cyclotron.com" not in _emails(summary)
    assert "Y@CYCLOTRON.COM" in _emails(lines)


def test_kept_rows_equal_store_without_personal_rows(
        clean_env, mixed_store, work_only_store):
    s1, l1 = export.build(mixed_store, MARKUP)
    s2, l2 = export.build(work_only_store, MARKUP)
    assert _strip_gen(s1) == _strip_gen(s2)
    assert _strip_gen(l1) == _strip_gen(l2)
    assert len(s1) > 0 and len(l1) > 0
    assert sum(r["tokens"] for r in l1) == 1000 + 200 + 300 + 400 + 500
    assert round(sum(r["actual_cost_usd"] for r in l1), 6) == 24.0


def test_explicit_allowed_domains_argument_overrides_env(monkeypatch, mixed_store):
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "cyclotron.com")
    summary, _ = export.build(mixed_store, MARKUP, allowed_domains=("gmail.com",))
    emails = _emails(summary)
    assert GMAIL in emails
    assert "cyclotron.com@gmail.com" in emails
    assert "alice@cyclotron.com" not in emails
    assert "unknown" in emails  # unknown still kept


def test_env_override_multiple_domains_call_time(monkeypatch, mixed_store):
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "gmail.com, Cyclotron.com")
    summary, lines = export.build(mixed_store, MARKUP)
    assert GMAIL in _emails(summary) and GMAIL in _emails(lines)
    assert "alice@cyclotron.com" in _emails(summary)
    assert "x@evil.cyclotron.com" not in _emails(summary)
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "evil.cyclotron.com")
    summary, _ = export.build(mixed_store, MARKUP)
    assert _emails(summary) - {"unknown"} == {"x@evil.cyclotron.com"}


def test_blank_env_uses_default(monkeypatch, mixed_store):
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "  ")
    summary, _ = export.build(mixed_store, MARKUP)
    assert GMAIL not in _emails(summary)
    assert "alice@cyclotron.com" in _emails(summary)


def test_filter_does_not_change_attribution_of_kept_rows(clean_env, store):
    _add(store, email="alice@cyclotron.com", usd=1.0, tokens=10, when="2026-01-01T10:00:00Z",
         repo="unknown", repo_raw="", session="s-unk")
    _add(store, email=GMAIL, usd=9.0, tokens=90, when="2026-01-01T10:00:00Z",
         repo="unknown", repo_raw="", session="s-unk2")
    _add(store, email="bob@cyclotron.com", usd=2.0, tokens=20, when="2026-01-01T10:00:00Z")
    store.commit()
    _, lines = export.build(store, MARKUP)
    assert sorted((r["user_email"], r["repo_key"]) for r in lines) == [
        ("alice@cyclotron.com", "unknown"), ("bob@cyclotron.com", ACME)]


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

def test_stats_counts_distinct_groups_once_across_tables(clean_env, mixed_store):
    stats = {}
    result = export.build(mixed_store, MARKUP, stats=stats)
    # gmail: 2 models on one day (each seen in cost+token tables, counted once) = 2
    # groups, plus 3 lookalike groups.
    assert stats["excluded_groups"] == 5
    assert stats["excluded_domains"] == sorted(
        {"gmail.com", "cyclotron.com.au", "evil.cyclotron.com"})
    assert isinstance(result, tuple) and len(result) == 2


def test_stats_never_contains_full_emails(clean_env, mixed_store):
    stats = {}
    export.build(mixed_store, MARKUP, stats=stats)
    assert not any("@" in d for d in stats["excluded_domains"])
    assert GMAIL not in repr(stats)


def test_stats_zero_when_nothing_excluded(clean_env, work_only_store):
    stats = {}
    export.build(work_only_store, MARKUP, stats=stats)
    assert stats == {"excluded_groups": 0, "excluded_domains": []}


def test_stats_no_at_address_excluded_but_adds_no_domain(clean_env, store):
    _add(store, email="noatsign", usd=1.0, tokens=1, when="2026-01-01T10:00:00Z")
    _add(store, email="ok@cyclotron.com", usd=1.0, tokens=1, when="2026-01-01T10:00:00Z")
    store.commit()
    stats = {}
    summary, _ = export.build(store, MARKUP, stats=stats)
    assert stats["excluded_groups"] == 1
    assert stats["excluded_domains"] == []
    assert _emails(summary) == {"ok@cyclotron.com"}


def test_stats_group_counts_raw_email_case_variants_separately(clean_env, store):
    _add(store, email="a@Gmail.com", usd=1.0, tokens=1, when="2026-01-01T10:00:00Z")
    _add(store, email="a@gmail.com", usd=1.0, tokens=1, when="2026-01-01T10:00:00Z")
    store.commit()
    stats = {}
    export.build(store, MARKUP, stats=stats)
    assert stats["excluded_groups"] == 2
    assert stats["excluded_domains"] == ["gmail.com"]


def test_stats_group_split_by_day_and_repo(clean_env, store):
    _add(store, email=GMAIL, usd=1, tokens=1, when="2026-01-01T10:00:00Z")
    _add(store, email=GMAIL, usd=1, tokens=1, when="2026-01-02T10:00:00Z")
    _add(store, email=GMAIL, usd=1, tokens=1, when="2026-01-02T10:00:00Z",
         repo="github.com/cyclotron/other", repo_raw="git@github.com:Cyclotron/Other.git")
    store.commit()
    stats = {}
    export.build(store, MARKUP, stats=stats)
    assert stats["excluded_groups"] == 3


def test_build_without_stats_still_returns_rows(clean_env, mixed_store):
    summary, lines = export.build(mixed_store, MARKUP)
    assert summary and lines


# ---------------------------------------------------------------------------
# raw store untouched
# ---------------------------------------------------------------------------

def test_raw_tables_unchanged_by_export(clean_env, mixed_store, tmp_path, capsys):
    store = mixed_store
    store.insert_session_repo(session_id="sess-tl", ts="2026-01-01T09:00:00Z", seq=0,
                              repo=ACME, repo_raw=ACME_RAW, cwd="C:\\x", event="SessionStart")
    store.commit()
    counts = {t: store.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in RAW_TABLES}
    assert counts["token_usage"] > 0 and counts["cost_usage"] > 0
    assert counts["session_repo_timeline"] == 1
    before = _raw_dump(store)
    export.build_and_enqueue(store, MARKUP, str(tmp_path / "out"))
    store.commit()
    assert _raw_dump(store) == before
    assert {t: store.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in RAW_TABLES} == counts
    # personal rows are still physically present in the raw store
    assert store.db.execute(
        "SELECT COUNT(*) FROM cost_usage WHERE user_email=?", (GMAIL,)).fetchone()[0] == 2


# ---------------------------------------------------------------------------
# build_and_enqueue: printed line and return value
# ---------------------------------------------------------------------------

def test_build_and_enqueue_prints_excluded_line_and_returns_counts(
        clean_env, mixed_store, tmp_path, capsys):
    ns, nl = export.build_and_enqueue(mixed_store, MARKUP, str(tmp_path / "out"))
    out = capsys.readouterr().out
    assert "[export] excluded 5 group(s) outside cyclotron.com" in out.splitlines()
    assert "@" not in out
    summary = _read_csv(tmp_path / "out" / "claudeusagesummary.csv")
    lines = _read_csv(tmp_path / "out" / "claudeusagelineitems.csv")
    assert (ns, nl) == (len(summary), len(lines))
    assert ns > 0 and nl > 0


def test_build_and_enqueue_prints_zero_line_when_nothing_excluded(
        clean_env, work_only_store, tmp_path, capsys):
    export.build_and_enqueue(work_only_store, MARKUP, str(tmp_path / "out"))
    assert ("[export] excluded 0 group(s) outside cyclotron.com"
            in capsys.readouterr().out.splitlines())


def test_build_and_enqueue_line_lists_configured_domains(
        monkeypatch, mixed_store, tmp_path, capsys):
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "Cyclotron.com, a.com")
    export.build_and_enqueue(mixed_store, MARKUP, str(tmp_path / "out"))
    assert "outside cyclotron.com,a.com" in capsys.readouterr().out


def test_build_and_enqueue_line_surfaces_typo_domain(
        monkeypatch, mixed_store, tmp_path, capsys):
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "cyclotorn.com")
    export.build_and_enqueue(mixed_store, MARKUP, str(tmp_path / "out"))
    out = capsys.readouterr().out
    assert "outside cyclotorn.com" in out
    excluded = int(out.split("[export] excluded ")[1].split(" ")[0])
    assert excluded > 5  # cyclotron users are excluded too: the visible symptom


def test_build_and_enqueue_enqueues_both_tables(clean_env, mixed_store, tmp_path, capsys):
    export.build_and_enqueue(mixed_store, MARKUP, str(tmp_path / "out"))
    kinds = {r[0] for r in mixed_store.db.execute("SELECT kind FROM fabric_outbox")}
    assert kinds == {export.SUMMARY_TABLE, export.LINEITEMS_TABLE}


# ---------------------------------------------------------------------------
# main(): in-process
# ---------------------------------------------------------------------------

def _run_main_inprocess(monkeypatch, tmp_path, argv):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(billing.config, "_LOADED", False)
    # setenv+delenv records the original so teardown removes anything load_env sets
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "x")
    monkeypatch.delenv("ALLOWED_EMAIL_DOMAINS")
    monkeypatch.setattr(sys, "argv", ["export", *argv])
    export.main()


def _seed_db(path):
    s = OtelStore(str(path))
    _seed_work(s)
    _seed_personal(s)
    s.commit()
    s.close()


def test_main_no_enqueue_writes_filtered_csvs_and_prints_line(monkeypatch, tmp_path, capsys):
    db = tmp_path / "m.db"
    _seed_db(db)
    out = tmp_path / "o"
    _run_main_inprocess(monkeypatch, tmp_path,
                        ["--db", str(db), "--no-enqueue", "--out-dir", str(out)])
    text = capsys.readouterr().out
    assert "[export] excluded 5 group(s) outside cyclotron.com" in text
    assert GMAIL not in text
    for name in (export.SUMMARY_TABLE, export.LINEITEMS_TABLE):
        rows = _read_csv(out / f"{name}.csv")
        assert GMAIL not in _emails(rows)
        assert not (_emails(rows) & set(LOOKALIKES))
        assert "alice@cyclotron.com" in _emails(rows)
    s = OtelStore(str(db))
    assert s.db.execute("SELECT COUNT(*) FROM fabric_outbox").fetchone()[0] == 0
    s.close()


def test_main_enqueue_path_prints_line_once(monkeypatch, tmp_path, capsys):
    db = tmp_path / "m.db"
    _seed_db(db)
    _run_main_inprocess(monkeypatch, tmp_path,
                        ["--db", str(db), "--out-dir", str(tmp_path / "o")])
    text = capsys.readouterr().out
    assert text.count("[export] excluded ") == 1
    assert "excluded 5 group(s)" in text
    s = OtelStore(str(db))
    assert s.db.execute("SELECT COUNT(*) FROM fabric_outbox").fetchone()[0] == 2
    s.close()


def test_main_honors_dotenv_written_in_tmp_cwd(monkeypatch, tmp_path, capsys):
    db = tmp_path / "m.db"
    _seed_db(db)
    (tmp_path / ".env").write_text("ALLOWED_EMAIL_DOMAINS=gmail.com\n", encoding="utf-8")
    out = tmp_path / "o"
    _run_main_inprocess(monkeypatch, tmp_path,
                        ["--db", str(db), "--no-enqueue", "--out-dir", str(out)])
    assert "outside gmail.com" in capsys.readouterr().out
    emails = _emails(_read_csv(out / "claudeusagesummary.csv"))
    assert GMAIL in emails and "alice@cyclotron.com" not in emails


def test_main_real_environment_beats_dotenv(monkeypatch, tmp_path, capsys):
    db = tmp_path / "m.db"
    _seed_db(db)
    (tmp_path / ".env").write_text("ALLOWED_EMAIL_DOMAINS=gmail.com\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(billing.config, "_LOADED", False)
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "cyclotron.com")
    monkeypatch.setattr(sys, "argv", ["export", "--db", str(db), "--no-enqueue",
                                      "--out-dir", str(tmp_path / "o")])
    export.main()
    assert "outside cyclotron.com" in capsys.readouterr().out
    assert GMAIL not in _emails(_read_csv(tmp_path / "o" / "claudeusagesummary.csv"))


# ---------------------------------------------------------------------------
# main(): subprocess, controlled env, cwd=tmp_path
# ---------------------------------------------------------------------------

def _subprocess_env():
    env = {"PYTHONPATH": REPO_ROOT}
    for k in ("SystemRoot", "PATH", "TEMP", "TMP", "HOME", "USERPROFILE"):
        if k in os.environ:
            env[k] = os.environ[k]
    return env


def _run_module(tmp_path, *args, extra_env=None):
    env = _subprocess_env()
    env.update(extra_env or {})
    return subprocess.run([sys.executable, "-m", "billing.otel.export", *args],
                          cwd=str(tmp_path), env=env, capture_output=True, text=True,
                          timeout=60)


def test_subprocess_no_enqueue_honors_dotenv_and_prints_line(tmp_path):
    db = tmp_path / "s.db"
    _seed_db(db)
    (tmp_path / ".env").write_text("ALLOWED_EMAIL_DOMAINS=a.com, Gmail.com\n",
                                   encoding="utf-8")
    out = tmp_path / "o"
    r = _run_module(tmp_path, "--db", str(db), "--no-enqueue", "--out-dir", str(out))
    assert r.returncode == 0, r.stderr
    assert "[export] excluded " in r.stdout
    assert "outside a.com,gmail.com" in r.stdout
    emails = _emails(_read_csv(out / "claudeusagesummary.csv"))
    assert GMAIL in emails
    assert "alice@cyclotron.com" not in emails


def test_subprocess_default_without_dotenv_excludes_personal(tmp_path):
    db = tmp_path / "s.db"
    _seed_db(db)
    out = tmp_path / "o"
    r = _run_module(tmp_path, "--db", str(db), "--no-enqueue", "--out-dir", str(out))
    assert r.returncode == 0, r.stderr
    assert "[export] excluded 5 group(s) outside cyclotron.com" in r.stdout
    for name in (export.SUMMARY_TABLE, export.LINEITEMS_TABLE):
        rows = _read_csv(out / f"{name}.csv")
        assert GMAIL not in _emails(rows)
        assert "alice@cyclotron.com" in _emails(rows)
    assert f"{export.SUMMARY_TABLE}.csv" in r.stdout


def test_subprocess_enqueue_path_prints_line(tmp_path):
    db = tmp_path / "s.db"
    _seed_db(db)
    r = _run_module(tmp_path, "--db", str(db), "--out-dir", str(tmp_path / "o"))
    assert r.returncode == 0, r.stderr
    assert r.stdout.count("[export] excluded 5 group(s)") == 1


def test_subprocess_process_env_beats_dotenv(tmp_path):
    db = tmp_path / "s.db"
    _seed_db(db)
    (tmp_path / ".env").write_text("ALLOWED_EMAIL_DOMAINS=gmail.com\n", encoding="utf-8")
    r = _run_module(tmp_path, "--db", str(db), "--no-enqueue",
                    "--out-dir", str(tmp_path / "o"),
                    extra_env={"ALLOWED_EMAIL_DOMAINS": "cyclotron.com"})
    assert r.returncode == 0, r.stderr
    assert "outside cyclotron.com" in r.stdout
    assert GMAIL not in _emails(_read_csv(tmp_path / "o" / "claudeusagesummary.csv"))
