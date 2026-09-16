"""Tests for tasks 02 and 03: `billing/reconcile.py`'s aggregation layer and
output rendering, plus regression coverage for the `--email` / org-wide
`run()` paths that shipped (commits `947a686`, `f5b76cc`, `f5b76cc`-adjacent,
`946293a`) with no committed test at all.

Analytics mocking seam (see `_goals/reconcile-coverage-diagnostics/04-tests.md`):
`billing.reconcile`'s org-wide truth path constructs its own `AnalyticsClient`
inside `analytics_claude_code_daily`, and `AnalyticsClient.__init__` raises
`AnalyticsError` when no token is in the environment -- so patching
`AnalyticsClient.usage_report` alone never reaches the client, and a bare
`pytest.raises(AnalyticsError)` test would pass whether or not the code under
test is correct. Two seams, used as task 02/03's own acceptance criteria pin
them, and each test below says in a comment which one it uses:

  * Seam A (function-level): `monkeypatch.setattr` on the module-level
    `billing.reconcile.analytics_claude_code_daily`. Used for every task-03
    output/behavior test and most task-02 tests.
  * Seam B (client-level): `monkeypatch.setenv("ANTHROPIC_ANALYTICS_TOKEN",
    "test-token")` **plus** `monkeypatch.setattr(AnalyticsClient,
    "usage_report", fake)`. Required whenever the assertion is about the
    client itself (call counts, eager evaluation, raise origin) -- task 02
    criteria 7-12. The `setenv` is mandatory: without it the constructor
    raises before the fake is ever reached.

No test makes a live network call under either seam. Every `run()` call below
passes an explicit `db=` (and `analytics_db=` where relevant) pointing at a
`tmp_path` file -- never `./data/otel.db` / `./data/analytics.db`.
"""

from __future__ import annotations

import io
import contextlib
from datetime import datetime, timezone

import pytest

import billing.reconcile as R
from billing.analytics_client import AnalyticsClient, AnalyticsError
from billing.otel.otel_store import DEDUPE_EPOCH_META_KEY, OtelStore
from billing.reconcile import (
    CANON, FT_COL, PAIR_W, PCT_COL,
    analytics_claude_code_daily, analytics_claude_code_totals,
    analytics_user_daily, analytics_user_totals, dedupe_drop_report,
    otel_by_surface, otel_daily, otel_totals, run,
)
from billing.store import Store
from tests.conftest import seed_otlp_rows


# ---------------------------------------------------------------------------
# Shared helpers -- local to this file (tests/conftest.py is out of the write
# fence). No mocking library; everything below is plain functions +
# unittest.mock-free monkeypatching via pytest's own `monkeypatch` fixture.
# ---------------------------------------------------------------------------

def _nano(iso_date: str) -> int:
    dt = datetime.strptime(iso_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1_000_000_000)


@pytest.fixture
def analytics_db_path(tmp_path) -> str:
    """A tmp_path-backed analytics.db path -- mirrors conftest's tmp_db_path
    but for the OTHER store (billing.store.Store), which reconcile.py's
    --email path opens separately from the OTEL store. Never
    ./data/analytics.db."""
    return str(tmp_path / "analytics.db")


def _seed_otel_row(store: OtelStore, *, session_id, day, token_type, tokens,
                    repo="github.com/cyclotron/acme-web", email="alice@cyclotron.com",
                    query_source="main", entrypoint=None, usage_source="otlp",
                    request_id=None):
    kwargs = dict(
        session_id=session_id, repo=repo, repo_raw=repo, user_email=email,
        user_id=email, org_id="org-cyclotron", model="claude-sonnet-5",
        token_type=token_type, query_source=query_source, tokens=tokens,
        time_unix_nano=_nano(day), usage_source=usage_source, entrypoint=entrypoint,
    )
    if usage_source != "otlp":
        kwargs["request_id"] = request_id or f"req-{session_id}-{token_type}"
    store.insert_datapoint(**kwargs)


def _seed_timeline(store: OtelStore, *, session_id, day, repo):
    store.insert_session_repo(
        session_id=session_id, ts=f"{day}T00:00:00Z", seq=0, repo=repo, repo_raw=repo,
        cwd="/home/dev", event="SessionStart")


def _set_epoch(store: OtelStore, value: str | None):
    if value is None:
        store.db.execute("DELETE FROM meta WHERE key=?", (DEDUPE_EPOCH_META_KEY,))
    else:
        store.db.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (DEDUPE_EPOCH_META_KEY, value))
    store.commit()


def _seed_drop(store: OtelStore, *, day, token_type="input", usage_source="otlp",
                session_id=None):
    """Seed exactly one dedupe_drops count via a genuine duplicate insert."""
    session_id = session_id or f"sess-drop-{day}-{token_type}-{usage_source}"
    kwargs = dict(
        session_id=session_id, repo="github.com/cyclotron/acme-web",
        repo_raw="github.com/cyclotron/acme-web", user_email="alice@cyclotron.com",
        user_id="alice@cyclotron.com", org_id="org-cyclotron", model="claude-sonnet-5",
        token_type=token_type, query_source="main", tokens=1,
        time_unix_nano=_nano(day), usage_source=usage_source,
    )
    if usage_source != "otlp":
        kwargs["request_id"] = f"req-{session_id}"
        kwargs["entrypoint"] = "claude-desktop"
    store.insert_datapoint(**kwargs)
    store.insert_datapoint(**kwargs)
    store.commit()


def _seed_user_usage(analytics_db_path: str, *, day, email, uncached_input=0, output=0,
                      cache_read=0, cache_creation_1h=0, cache_creation_5m=0):
    store = Store(analytics_db_path)
    total = uncached_input + output + cache_read + cache_creation_1h + cache_creation_5m
    store.db.execute(
        """INSERT OR REPLACE INTO user_cc_usage
           (day, user_id, email, name, uncached_input, cache_creation_1h,
            cache_creation_5m, cache_read, output, total_tokens,
            web_search_requests, requests, ingested_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (day, email, email, email, uncached_input, cache_creation_1h, cache_creation_5m,
         cache_read, output, total, 0, 0, "2026-01-01T00:00:00Z"))
    store.commit()
    store.close()


def _analytics_row(*, uncached_input=0, output=0, cache_read=0,
                    cache_creation_1h=0, cache_creation_5m=0) -> dict:
    """One `usage_report` result row, in the API's own raw shape (nested
    cache_creation, `*_tokens` suffixes) -- matches `billing.store.tokens()`'s
    expected input exactly, since `analytics_claude_code_daily` reuses that
    same accessor via `billing.reconcile.analytics_tokens`."""
    return {
        "uncached_input_tokens": uncached_input,
        "output_tokens": output,
        "cache_read_input_tokens": cache_read,
        "cache_creation": {
            "ephemeral_1h_input_tokens": cache_creation_1h,
            "ephemeral_5m_input_tokens": cache_creation_5m,
        },
    }


def _make_usage_report_fake(rows):
    """Seam B fake for `AnalyticsClient.usage_report`. `rows` is a list of
    (starting_at, row_dict) pairs, matching the real generator's yield shape.
    The returned function's `.calls` counter increments on each CALL (not on
    iteration), so a test can prove a caller consumed it eagerly."""
    def fake(self, start, end, bucket_width="1d", group_by=None, products=None, limit=None):
        fake.calls += 1
        return iter(rows)
    fake.calls = 0
    return fake


def _make_raising_usage_report_fake(exc: Exception):
    def fake(self, start, end, bucket_width="1d", group_by=None, products=None, limit=None):
        raise exc
    return fake


def _run_capture(*args, **kwargs) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        run(*args, **kwargs)
    return buf.getvalue()


# ===========================================================================
# Task 02 -- aggregation layer
# ===========================================================================

# ---- Criterion 1: pre-change baseline pin ---------------------------------
# Baseline captured by running otel_totals(...) against conftest's
# seeded_otlp_db_path fixture on the current (post-task-02) code:
#   captured = {input:255000, output:132000, cacheRead:251000, cacheCreation:50500}
#   tagged   = {input:250000, output:130000, cacheRead:250000, cacheCreation:50000}
# (session 1: timeline-tagged; session 2: wrapper-tagged via non-'unknown'
# repo; session 3: repo='unknown', untagged.) Confirmed by direct execution
# before writing this assertion.

def test_02_1_baseline_captured_and_tagged_pinned(seeded_otlp_db_path):
    store = OtelStore(seeded_otlp_db_path)
    try:
        result = otel_totals(store, "2025-01-01", "2027-01-01")
        assert result["captured"] == {
            "input": 255000, "output": 132000, "cacheRead": 251000, "cacheCreation": 50500}
        assert result["tagged"] == {
            "input": 250000, "output": 130000, "cacheRead": 250000, "cacheCreation": 50000}
    finally:
        store.close()


# ---- Criterion 2: unmapped token type reported with correct total --------

def test_02_2_unmapped_token_type_reported_with_correct_total(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        _seed_otel_row(store, session_id="s1", day="2026-07-14",
                       token_type="cacheCreation5m", tokens=42)
        _seed_otel_row(store, session_id="s1", day="2026-07-14",
                       token_type="cacheCreation5m", tokens=8, request_id=None,
                       usage_source="otlp", query_source="subagent")
        store.commit()
        result = otel_totals(store, "2026-07-14", "2026-07-15")
        assert result["unmapped"]["cacheCreation5m"] == 50
        assert result["captured"] == {k: 0 for k in CANON}
    finally:
        store.close()


# ---- Criterion 3: NULL token_type -> "(none)" -----------------------------

def test_02_3_null_token_type_reported_as_none(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        _seed_otel_row(store, session_id="s1", day="2026-07-14",
                       token_type=None, tokens=7)
        store.commit()
        result = otel_totals(store, "2026-07-14", "2026-07-15")
        assert result["unmapped"] == {"(none)": 7}
    finally:
        store.close()


# ---- Criterion 4: otel_by_surface's dimensions sum to captured_total, ----
# equal to sum(otel_totals(...)["captured"].values()). Mixed otlp+transcript,
# 2 query_source values + 1 NULL row, 2+ entrypoint values.

def test_02_4_by_surface_dimensions_sum_to_captured_total(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        _seed_otel_row(store, session_id="s1", day="2026-07-14", token_type="input",
                       tokens=100, query_source="main", entrypoint=None)
        _seed_otel_row(store, session_id="s2", day="2026-07-14", token_type="output",
                       tokens=50, query_source="subagent", entrypoint=None)
        _seed_otel_row(store, session_id="s3", day="2026-07-14", token_type="cacheRead",
                       tokens=30, query_source=None, entrypoint="claude-desktop",
                       usage_source="transcript")
        _seed_otel_row(store, session_id="s4", day="2026-07-14", token_type="cacheCreation",
                       tokens=20, query_source="main", entrypoint="cli",
                       usage_source="transcript")
        store.commit()

        surf = otel_by_surface(store, "2026-07-14", "2026-07-15")
        totals = otel_totals(store, "2026-07-14", "2026-07-15")

        assert surf["captured_total"] == 200
        assert sum(surf["usage_source"].values()) == 200
        assert sum(surf["entrypoint"].values()) == 200
        assert sum(surf["query_source"].values()) == 200
        assert surf["captured_total"] == sum(totals["captured"].values())
    finally:
        store.close()


# ---- Criterion 5: OTLP NULL entrypoint -> "(none)"; NULL query_source ----
# -> "(none)".

def test_02_5_null_entrypoint_and_null_query_source_coalesce_to_none(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        _seed_otel_row(store, session_id="s1", day="2026-07-14", token_type="input",
                       tokens=100, query_source=None, entrypoint=None)
        store.commit()
        surf = otel_by_surface(store, "2026-07-14", "2026-07-15")
        assert surf["entrypoint"]["(none)"] == 100
        assert surf["query_source"]["(none)"] == 100
    finally:
        store.close()


# ---- Criterion 6: Sigma-daily == period, captured and tagged side --------

def test_02_6_daily_sums_equal_period_totals_captured_and_tagged(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        days = ["2026-07-01", "2026-07-02", "2026-07-03"]
        for i, day in enumerate(days):
            _seed_otel_row(store, session_id=f"tagged-{i}", day=day, token_type="input",
                           tokens=10 * (i + 1), repo="github.com/cyclotron/acme-web")
            _seed_otel_row(store, session_id=f"untagged-{i}", day=day, token_type="output",
                           tokens=5 * (i + 1), repo="unknown")
        store.commit()

        totals = otel_totals(store, "2026-07-01", "2026-07-04")
        daily = otel_daily(store, "2026-07-01", "2026-07-04")

        for k in CANON:
            captured_sum = sum(daily[d]["captured"][k] for d in daily)
            tagged_sum = sum(daily[d]["tagged"][k] for d in daily)
            assert captured_sum == totals["captured"][k]
            assert tagged_sum == totals["tagged"][k]
    finally:
        store.close()


# ---- Criterion 7: Sigma-daily == period, truth side (org-wide + user) ----

def test_02_7_daily_sums_equal_totals_org_wide(monkeypatch):
    # Seam B: assertion is about analytics_claude_code_daily/_totals
    # agreeing, a client-level identity.
    monkeypatch.setenv("ANTHROPIC_ANALYTICS_TOKEN", "test-token")
    rows = [
        ("2026-07-01T00:00:00Z", _analytics_row(uncached_input=10, output=5)),
        ("2026-07-02T00:00:00Z", _analytics_row(uncached_input=20, output=15, cache_read=3)),
        ("2026-07-03T00:00:00Z", _analytics_row(cache_creation_1h=7, cache_creation_5m=1)),
    ]
    fake = _make_usage_report_fake(rows)
    monkeypatch.setattr(AnalyticsClient, "usage_report", fake)

    daily = analytics_claude_code_daily("2026-07-01", "2026-07-04")
    totals = analytics_claude_code_totals("2026-07-01", "2026-07-04")
    for k in CANON:
        assert sum(daily[d][k] for d in daily) == totals[k]
    # `analytics_claude_code_totals` is a thin wrapper that SUMS
    # `analytics_claude_code_daily` (task 02's own design), so the identity
    # above is tautological -- it cannot fail even if cacheCreation_5m were
    # dropped at the source, since both sides would drop it together. Pin
    # the absolute per-day and period dicts too, so that specific defect
    # (day 3's cacheCreation is cache_creation_1h=7 + cache_creation_5m=1=8)
    # is actually caught.
    assert daily == {
        "2026-07-01": {"input": 10, "output": 5, "cacheRead": 0, "cacheCreation": 0},
        "2026-07-02": {"input": 20, "output": 15, "cacheRead": 3, "cacheCreation": 0},
        "2026-07-03": {"input": 0, "output": 0, "cacheRead": 0, "cacheCreation": 8},
    }
    assert totals == {"input": 30, "output": 20, "cacheRead": 3, "cacheCreation": 8}


def test_02_7_daily_sums_equal_totals_user_scoped(analytics_db_path):
    # No Analytics touch -- pure SQLite against user_cc_usage. Nonzero
    # cache_creation_5m on day 1 so a dropped-field defect in
    # analytics_user_daily/analytics_user_totals is actually caught by the
    # absolute assertion below, not just by the identity (which the fixture
    # alone previously let pass with cacheCreation permanently at 0).
    _seed_user_usage(analytics_db_path, day="2026-07-01", email="a@cyclotron.com",
                     uncached_input=10, output=5, cache_creation_5m=4)
    _seed_user_usage(analytics_db_path, day="2026-07-02", email="a@cyclotron.com",
                     uncached_input=20, cache_read=3, cache_creation_1h=2)
    result = analytics_user_totals(["a@cyclotron.com"], "2026-07-01", "2026-07-04",
                                   analytics_db=analytics_db_path)
    assert result is not None
    totals, _matched = result
    daily = analytics_user_daily(["a@cyclotron.com"], "2026-07-01", "2026-07-04",
                                 analytics_db=analytics_db_path)
    for k in CANON:
        assert sum(daily[d][k] for d in daily) == totals[k]
    assert totals == {"input": 30, "output": 5, "cacheRead": 3, "cacheCreation": 6}


# ---- Criterion 8: day-key literal, normalized and equal to otel_daily's --

def test_02_8_day_key_normalized_and_matches_otel_daily(tmp_db_path, monkeypatch):
    # Seam B.
    monkeypatch.setenv("ANTHROPIC_ANALYTICS_TOKEN", "test-token")
    rows = [("2026-07-14T00:00:00Z", _analytics_row(uncached_input=1))]
    monkeypatch.setattr(AnalyticsClient, "usage_report", _make_usage_report_fake(rows))

    truth_daily = analytics_claude_code_daily("2026-07-14", "2026-07-15")
    assert set(truth_daily.keys()) == {"2026-07-14"}

    store = OtelStore(tmp_db_path)
    try:
        _seed_otel_row(store, session_id="s1", day="2026-07-14", token_type="input", tokens=1)
        store.commit()
        cap_daily = otel_daily(store, "2026-07-14", "2026-07-15")
        assert set(cap_daily.keys()) == set(truth_daily.keys()) == {"2026-07-14"}
    finally:
        store.close()


# ---- Criterion 9: org-wide path makes exactly one usage_report call ------

def test_02_9_single_pass_call_count_is_exactly_one(tmp_db_path, monkeypatch):
    # Seam B.
    monkeypatch.setenv("ANTHROPIC_ANALYTICS_TOKEN", "test-token")
    fake = _make_usage_report_fake([("2026-07-14T00:00:00Z", _analytics_row(uncached_input=1))])
    monkeypatch.setattr(AnalyticsClient, "usage_report", fake)

    _run_capture("2026-07-14", "2026-07-15", db=tmp_db_path, daily=True)
    assert fake.calls == 1


# ---- Criterion 10: analytics_claude_code_totals sums the single pass -----

def test_02_10_totals_wrapper_sums_daily_for_fixed_fake_payload(monkeypatch):
    # Seam B.
    monkeypatch.setenv("ANTHROPIC_ANALYTICS_TOKEN", "test-token")
    rows = [
        ("2026-07-14T00:00:00Z", _analytics_row(uncached_input=10, output=5, cache_read=2)),
        ("2026-07-15T00:00:00Z", _analytics_row(uncached_input=1, cache_creation_1h=3)),
    ]
    monkeypatch.setattr(AnalyticsClient, "usage_report", _make_usage_report_fake(rows))
    totals = analytics_claude_code_totals("2026-07-14", "2026-07-16")
    assert totals == {"input": 11, "output": 5, "cacheRead": 2, "cacheCreation": 3}


# ---- Criterion 11: AnalyticsError from usage_report -> existing message --

def test_02_11_analytics_error_from_usage_report_produces_existing_message(
        tmp_db_path, monkeypatch):
    # Seam B, with a valid fake token set so the raise provably originates in
    # usage_report and not in AnalyticsClient's constructor.
    monkeypatch.setenv("ANTHROPIC_ANALYTICS_TOKEN", "test-token")
    monkeypatch.setattr(
        AnalyticsClient, "usage_report",
        _make_raising_usage_report_fake(AnalyticsError("revoked")))

    out = _run_capture("2026-07-14", "2026-07-15", db=tmp_db_path)
    assert "!! Could not reach Analytics API: revoked" in out
    assert "COVERAGE FUNNEL" not in out


# ---- Criterion 12: analytics_claude_code_daily returns a materialized dict

def test_02_12_daily_returns_materialized_dict_eagerly(monkeypatch):
    # Seam B.
    monkeypatch.setenv("ANTHROPIC_ANALYTICS_TOKEN", "test-token")
    fake = _make_usage_report_fake([("2026-07-14T00:00:00Z", _analytics_row(uncached_input=1))])
    monkeypatch.setattr(AnalyticsClient, "usage_report", fake)

    result = analytics_claude_code_daily("2026-07-14", "2026-07-15")
    assert isinstance(result, dict)
    assert fake.calls == 1  # the pass already happened by the time we got a return value


# ---- Criterion 13: 5 epoch placements -> measurement -----

@pytest.mark.parametrize("epoch,expected", [
    (None, "none"),
    ("2026-07-20T00:00:00Z", "none"),        # epoch_day == end
    ("2026-07-05T00:00:00Z", "full"),        # epoch_day < start
    ("2026-07-10T00:00:00Z", "partial"),     # epoch_day == start
    ("2026-07-15T00:00:00Z", "partial"),     # start < epoch_day < end
])
def test_02_13_measurement_states_for_five_epoch_placements(tmp_db_path, epoch, expected):
    store = OtelStore(tmp_db_path)
    try:
        _set_epoch(store, epoch)
        result = dedupe_drop_report(store, "2026-07-10", "2026-07-20")
        assert result["measurement"] == expected
    finally:
        store.close()


# ---- Criterion 14: otel_daily's tagged reflects the RESOLVED repo --------

def test_02_14_daily_tagged_reflects_resolved_repo(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        # Raw repo is 'unknown'; an earlier timeline entry resolves it.
        _seed_timeline(store, session_id="s1", day="2026-07-13", repo="github.com/cyclotron/acme-web")
        _seed_otel_row(store, session_id="s1", day="2026-07-14", token_type="input",
                       tokens=99, repo="unknown")
        store.commit()
        daily = otel_daily(store, "2026-07-14", "2026-07-15")
        assert daily["2026-07-14"]["tagged"]["input"] == 99
        assert daily["2026-07-14"]["captured"]["input"] == 99
    finally:
        store.close()


# ---- Criterion 15: no aggregation function prints anything ---------------

def test_02_15_aggregation_functions_print_nothing(tmp_db_path, capsys):
    store = OtelStore(tmp_db_path)
    try:
        _seed_otel_row(store, session_id="s1", day="2026-07-14", token_type="input", tokens=5)
        store.commit()
        otel_totals(store, "2026-07-14", "2026-07-15")
        otel_by_surface(store, "2026-07-14", "2026-07-15")
        otel_daily(store, "2026-07-14", "2026-07-15")
        dedupe_drop_report(store, "2026-07-14", "2026-07-15")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
    finally:
        store.close()


# ---- Criterion 16: counts_outside_measurement, both routes + full=False --

def test_02_16_counts_outside_measurement_true_replayed_export_route(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        # By design: a replayed old export is counted today, with drops
        # dated inside a window the epoch (set AFTER the window) says was
        # never measured.
        _set_epoch(store, "2026-08-01T00:00:00Z")
        _seed_drop(store, day="2026-07-14")
        result = dedupe_drop_report(store, "2026-07-10", "2026-07-20")
        assert result["measurement"] == "none"
        assert result["counts_outside_measurement"] is True
    finally:
        store.close()


def test_02_16_counts_outside_measurement_true_interrupted_write_route(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        # By interruption: epoch meta key absent entirely, drops from later
        # committed requests persist. _seed_drop's inserts run through the
        # real insert path, which writes the epoch itself -- delete it again
        # AFTER seeding to simulate the "never confirmed / rolled back" state
        # this route actually describes.
        _seed_drop(store, day="2026-07-14")
        _set_epoch(store, None)
        result = dedupe_drop_report(store, "2026-07-10", "2026-07-20")
        assert result["measurement"] == "none"
        assert result["epoch"] is None
        assert result["counts_outside_measurement"] is True
    finally:
        store.close()


def test_02_16_counts_outside_measurement_false_when_fully_counted(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        _set_epoch(store, "2026-07-01T00:00:00Z")  # epoch_day < start
        _seed_drop(store, day="2026-07-14")
        result = dedupe_drop_report(store, "2026-07-10", "2026-07-20")
        assert result["measurement"] == "full"
        assert result["counts_outside_measurement"] is False
    finally:
        store.close()


# ===========================================================================
# Task 03 -- output rendering + CLI flags
#
# Every criterion in this section uses Seam A (module-level monkeypatch of
# `billing.reconcile.analytics_claude_code_daily`), per task 03's own pinned
# note: patching AnalyticsClient.usage_report alone does not exercise these
# code paths at all (they never touch AnalyticsClient).
# ===========================================================================

def _patch_truth_daily(monkeypatch, daily: dict):
    monkeypatch.setattr(R, "analytics_claude_code_daily", lambda start, end: daily)


# ---- Criterion 1: default run prints exactly the 3 base sections ---------

def test_03_1_default_run_prints_only_base_sections(tmp_db_path, monkeypatch):
    _patch_truth_daily(monkeypatch, {"2026-07-14": {k: 0 for k in CANON}})
    out = _run_capture("2026-07-14", "2026-07-15", db=tmp_db_path)
    assert "BY TOKEN TYPE" in out
    assert "COVERAGE FUNNEL" in out
    assert "BILLABLE COVERAGE" in out
    assert "BY SURFACE" not in out
    assert "\nDAILY" not in out


# ---- Criterion 2: BY TOKEN TYPE rows + TOTAL pinned exactly, whitespace ---
# included. Fixture: fully-tagged captured rows day 2026-07-14, truth patched
# to a fixed dict. Lines below were captured from an actual run and are
# pinned verbatim (not reconstructed via the module's own formatting
# helpers, since the whole point is to catch a layout regression in the
# print statements themselves).

def test_03_2_by_token_type_rows_and_total_pinned_exactly(tmp_db_path, monkeypatch):
    store = OtelStore(tmp_db_path)
    try:
        for tt, tok in [("input", 800), ("output", 400), ("cacheRead", 300),
                        ("cacheCreation", 100)]:
            _seed_otel_row(store, session_id="s1", day="2026-07-14", token_type=tt, tokens=tok)
        store.commit()
    finally:
        store.close()

    _patch_truth_daily(monkeypatch, {
        "2026-07-14": {"input": 1000, "output": 500, "cacheRead": 300, "cacheCreation": 200}})
    out = _run_capture("2026-07-14", "2026-07-15", db=tmp_db_path)
    lines = out.splitlines()

    expected_rows = [
        "  input               1.0K           1,000       800             800   80.00%",
        "  output               500             500       400             400   80.00%",
        "  cacheRead            300             300       300             300  100.00%",
        "  cacheCreation        200             200       100             100   50.00%",
        "  TOTAL               2.0K           2,000      1.6K           1,600   80.00%",
    ]
    for row in expected_rows:
        assert row in lines, f"missing pinned row: {row!r}"


# ---- Criterion 3: unmapped section, with type + exact count, default ----

def test_03_3_unmapped_section_prints_type_and_count(tmp_db_path, monkeypatch):
    store = OtelStore(tmp_db_path)
    try:
        _seed_otel_row(store, session_id="s1", day="2026-07-14",
                       token_type="cacheCreation5m", tokens=1234)
        store.commit()
    finally:
        store.close()
    _patch_truth_daily(monkeypatch, {"2026-07-14": {k: 0 for k in CANON}})
    out = _run_capture("2026-07-14", "2026-07-15", db=tmp_db_path)
    assert "!! UNMAPPED TOKEN TYPES" in out
    assert "cacheCreation5m" in out
    assert "1,234" in out


# ---- Criterion 4: no unmapped types -> no section -------------------------

def test_03_4_no_unmapped_section_when_empty(tmp_db_path, monkeypatch):
    store = OtelStore(tmp_db_path)
    try:
        _seed_otel_row(store, session_id="s1", day="2026-07-14", token_type="input", tokens=5)
        store.commit()
    finally:
        store.close()
    _patch_truth_daily(monkeypatch, {"2026-07-14": {k: 0 for k in CANON}})
    out = _run_capture("2026-07-14", "2026-07-15", db=tmp_db_path)
    assert "UNMAPPED TOKEN TYPES" not in out


# ---- Criteria 5, 6, 7, 7b, 7c: DEDUPE DROPS rendering ---------------------
# Tested by calling the print helper directly against a hand-built
# dedupe_drop_report()-shaped dict -- these are pure rendering criteria, so a
# controlled dict is more precise than trying to land a real store on an
# exact epoch instant.

def _dd(*, epoch, measurement, by_type=None, by_day=None):
    by_type = by_type or {}
    return {
        "epoch": epoch,
        "epoch_day": epoch[:10] if epoch else None,
        "measurement": measurement,
        "counts_outside_measurement": bool(by_type) and measurement != "full",
        "by_type": by_type,
        "by_day": by_day or {},
    }


_STATE_1 = _dd(epoch=None, measurement="none")
_STATE_2 = _dd(epoch="2026-08-01T00:00:00Z", measurement="none")
_STATE_3 = _dd(epoch="2026-07-15T00:00:00Z", measurement="partial")
_STATE_4_ZERO = _dd(epoch="2026-07-01T00:00:00Z", measurement="full")
_STATE_4_NONZERO = _dd(epoch="2026-07-01T00:00:00Z", measurement="full", by_type={"input": 3})


def _print_dedupe_capture(dd: dict) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        R._print_dedupe(dd)
    return buf.getvalue()


def test_03_5_four_qualifiers_wording_and_no_bare_count_when_empty():
    out1 = _print_dedupe_capture(_STATE_1)
    out2 = _print_dedupe_capture(_STATE_2)
    out3 = _print_dedupe_capture(_STATE_3)
    out4 = _print_dedupe_capture(_STATE_4_ZERO)

    assert "Counting has never run against this database" in out1
    assert "Counting began after this window (at 2026-08-01T00:00:00Z)" in out2
    assert "Counting began during this window, at 2026-07-15T00:00:00Z" in out3
    assert "Window is fully counted (counting began at 2026-07-01T00:00:00Z)" in out4

    # No bare drop count -- states 1-3 have an empty by_type, so no CANON
    # label (which would only ever appear alongside a printed row) shows up.
    for out in (out1, out2, out3):
        for tt in CANON:
            assert tt not in out


def test_03_5_all_four_states_pairwise_different():
    outs = [_print_dedupe_capture(dd) for dd in (_STATE_1, _STATE_2, _STATE_3, _STATE_4_ZERO)]
    assert len(set(outs)) == 4


def test_03_6_partial_state_with_drops_names_epoch_and_says_lower_bound():
    state = _dd(epoch="2026-07-15T00:00:00Z", measurement="partial", by_type={"input": 5})
    out = _print_dedupe_capture(state)
    assert "2026-07-15T00:00:00Z" in out
    assert "LOWER BOUND" in out


def test_03_6_partial_state_with_empty_by_type_names_epoch_no_lower_bound():
    out = _print_dedupe_capture(_STATE_3)  # partial, by_type={}
    assert "2026-07-15T00:00:00Z" in out
    assert "LOWER BOUND" not in out
    # Distinctive phrase pinning the "measured zero, not unmeasured" wording
    # without pinning the whole sentence (Phase 5 may still reword around it).
    assert "were never counted" in out


def test_03_7_full_state_zero_drops_says_no_duplicates():
    out = _print_dedupe_capture(_STATE_4_ZERO)
    assert "no duplicate datapoints in this window" in out


def test_03_7_full_state_nonzero_drops_prints_exact_count():
    out = _print_dedupe_capture(_STATE_4_NONZERO)
    assert "input" in out
    assert f"{3:,}" in out


@pytest.mark.parametrize("state,label", [
    (_dd(epoch=None, measurement="none", by_type={"input": 5}), "state1"),
    (_dd(epoch="2026-08-01T00:00:00Z", measurement="none", by_type={"input": 7}), "state2"),
    (_dd(epoch="2026-07-15T00:00:00Z", measurement="partial", by_type={"input": 9}), "state3"),
])
def test_03_7b_nonempty_by_type_printed_under_states_1_2_3(state, label):
    out = _print_dedupe_capture(state)
    n = list(state["by_type"].values())[0]
    assert f"{n:,}" in out
    assert "input" in out
    # The qualifier for this state's measurement is present alongside the count.
    if state["measurement"] == "none" and not state["epoch"]:
        assert "Counting has never run against this database" in out
    elif state["measurement"] == "none":
        assert "Counting began after this window" in out
    else:
        assert "Counting began during this window" in out


def test_03_7c_counts_outside_measurement_names_count_and_epoch():
    state = _dd(epoch="2026-08-01T00:00:00Z", measurement="none", by_type={"input": 42})
    out = _print_dedupe_capture(state)
    normalized = " ".join(out.split())  # collapse _wrap()'s line breaks for substring matching
    assert "42" in out
    assert "2026-08-01T00:00:00Z" in out
    assert "drop(s) dated inside this window were recorded" in normalized


# ---- Criterion 8: --daily prints a truth-only day with a coverage pct ----

def test_03_8_daily_prints_truth_only_day_with_coverage_pct(tmp_db_path, monkeypatch):
    store = OtelStore(tmp_db_path)
    try:
        _seed_otel_row(store, session_id="s1", day="2026-07-01", token_type="input", tokens=10)
        _seed_otel_row(store, session_id="s2", day="2026-07-02", token_type="input", tokens=20)
        store.commit()
    finally:
        store.close()
    _patch_truth_daily(monkeypatch, {
        "2026-07-01": {"input": 10, "output": 0, "cacheRead": 0, "cacheCreation": 0},
        "2026-07-02": {"input": 20, "output": 0, "cacheRead": 0, "cacheCreation": 0},
        "2026-07-03": {"input": 30, "output": 0, "cacheRead": 0, "cacheCreation": 0},
    })
    out = _run_capture("2026-07-01", "2026-07-04", db=tmp_db_path, daily=True)
    lines = [l for l in out.splitlines() if l.strip().startswith("2026-07-03")]
    assert len(lines) == 1
    assert "0.00%" in lines[0]  # truth present, zero captured -> receiver-outage signal


# ---- Criterion 9: --daily rows sum to the period TOTAL --------------------

def test_03_9_daily_rows_sum_to_period_total(tmp_db_path, monkeypatch):
    store = OtelStore(tmp_db_path)
    try:
        for day, tok in [("2026-07-01", 100), ("2026-07-02", 200), ("2026-07-03", 300)]:
            _seed_otel_row(store, session_id=f"s-{day}", day=day, token_type="input", tokens=tok)
        store.commit()
    finally:
        store.close()
    _patch_truth_daily(monkeypatch, {
        "2026-07-01": {"input": 100, "output": 0, "cacheRead": 0, "cacheCreation": 0},
        "2026-07-02": {"input": 200, "output": 0, "cacheRead": 0, "cacheCreation": 0},
        "2026-07-03": {"input": 300, "output": 0, "cacheRead": 0, "cacheCreation": 0},
    })
    out = _run_capture("2026-07-01", "2026-07-04", db=tmp_db_path, daily=True)
    lines = out.splitlines()

    total_line = next(l for l in lines if l.strip().startswith("TOTAL"))
    total_truth = int(total_line[16:16 + PAIR_W][FT_COL + 1:].strip().replace(",", ""))
    total_captured = int(total_line[16 + PAIR_W:16 + 2 * PAIR_W][FT_COL + 1:].strip().replace(",", ""))

    # Anchor strictly to the DAILY section (printed last, after DEDUPE DROPS)
    # -- DEDUPE's "by day:" sub-table rows also start with a YYYY-MM-DD-like
    # token but at different column offsets, so a bare "looks like a date"
    # filter over the whole output would silently include (or, with drops
    # seeded, misparse) those rows too.
    daily_section = out[out.index("\nDAILY\n"):]
    day_lines = [l for l in daily_section.splitlines()
                 if l.strip()[:4].isdigit() and l.strip()[:10].count("-") == 2]
    daily_truth_sum = 0
    daily_captured_sum = 0
    for l in day_lines:
        daily_truth_sum += int(l[12:12 + PAIR_W][FT_COL + 1:].strip().replace(",", ""))
        daily_captured_sum += int(
            l[12 + PAIR_W:12 + 2 * PAIR_W][FT_COL + 1:].strip().replace(",", ""))

    assert daily_truth_sum == total_truth == 600
    assert daily_captured_sum == total_captured == 600


# ---- Criterion 10: --daily works in --email mode, renders tagged/billable

def test_03_10_daily_in_email_mode_renders_tagged_and_billable(
        tmp_db_path, analytics_db_path):
    # tagged (30) is deliberately LESS than captured (80) -- one row is
    # untagged (repo='unknown') -- so a mutation that forces tagged to 0, or
    # drops the tagged/billable columns entirely, changes an assertable
    # value instead of just the coverage % (which both mutations leave
    # alone).
    store = OtelStore(tmp_db_path)
    try:
        _seed_otel_row(store, session_id="s-untagged", day="2026-07-14", token_type="input",
                       tokens=50, email="alice@cyclotron.com", repo="unknown")
        _seed_otel_row(store, session_id="s-tagged", day="2026-07-14", token_type="input",
                       tokens=30, email="alice@cyclotron.com",
                       repo="github.com/cyclotron/acme-web")
        store.commit()
    finally:
        store.close()
    _seed_user_usage(analytics_db_path, day="2026-07-14", email="alice@cyclotron.com",
                     uncached_input=80)
    out = _run_capture("2026-07-14", "2026-07-15", db=tmp_db_path,
                       emails=["alice@cyclotron.com"], analytics_db=analytics_db_path,
                       daily=True)
    assert "DAILY" in out
    daily_section = out[out.index("\nDAILY\n"):]
    day_line = next(l for l in daily_section.splitlines() if l.strip().startswith("2026-07-14"))

    tagged_offset = 12 + 2 * PAIR_W + PCT_COL
    tagged = int(
        day_line[tagged_offset:tagged_offset + PAIR_W][FT_COL + 1:].strip().replace(",", ""))
    billable_pct = day_line[tagged_offset + PAIR_W:tagged_offset + PAIR_W + PCT_COL].strip()

    assert tagged == 30          # not 80 (captured) and not 0 (a forced-zero mutation)
    assert billable_pct == "37.50%"  # tagged(30) / truth(80), not coverage's 100.00%


# ---- Criterion 11: per-day dedupe sub-table renders under every state ----

def test_03_11_per_day_dedupe_subtable_renders_in_state_full():
    dd = _dd(epoch="2026-07-01T00:00:00Z", measurement="full",
             by_type={"input": 4}, by_day={"2026-07-14": {"input": 4}})
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        R._print_dedupe(dd, daily=True)
    out = buf.getvalue()
    assert "by day" in out
    assert "2026-07-14" in out


def test_03_11_per_day_dedupe_subtable_renders_in_state_none_with_epoch():
    dd = _dd(epoch="2026-08-01T00:00:00Z", measurement="none",
             by_type={"input": 6}, by_day={"2026-07-14": {"input": 6}})
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        R._print_dedupe(dd, daily=True)
    out = buf.getvalue()
    assert "by day" in out
    assert "2026-07-14" in out


# ---- Criterion 12: --by-surface header + 3 dims + (none) entrypoint row --

def test_03_12_by_surface_header_and_dimensions_and_none_entrypoint(tmp_db_path, monkeypatch):
    store = OtelStore(tmp_db_path)
    try:
        _seed_otel_row(store, session_id="s1", day="2026-07-14", token_type="input",
                       tokens=10)  # OTLP row -> entrypoint NULL -> "(none)"
        store.commit()
    finally:
        store.close()
    _patch_truth_daily(monkeypatch, {"2026-07-14": {k: 0 for k in CANON}})
    out = _run_capture("2026-07-14", "2026-07-15", db=tmp_db_path, by_surface=True)
    assert "share of captured" in out
    assert "NOT coverage" in out
    for dim in ("usage_source", "entrypoint", "query_source"):
        assert dim in out
    assert "(none)" in out


# ---- Criterion 13: each --by-surface sub-block TOTAL reads 100.00% -------

def test_03_13_by_surface_total_rows_read_100_percent(tmp_db_path, monkeypatch):
    store = OtelStore(tmp_db_path)
    try:
        _seed_otel_row(store, session_id="s1", day="2026-07-14", token_type="input", tokens=10,
                       query_source="main")
        # Different query_source AND usage_source/entrypoint so no single
        # dimension row happens to land on 100% by coincidence -- only the
        # three TOTAL rows should.
        _seed_otel_row(store, session_id="s2", day="2026-07-14", token_type="output", tokens=20,
                       usage_source="transcript", entrypoint="claude-desktop",
                       query_source="subagent")
        store.commit()
    finally:
        store.close()
    _patch_truth_daily(monkeypatch, {"2026-07-14": {k: 0 for k in CANON}})
    out = _run_capture("2026-07-14", "2026-07-15", db=tmp_db_path, by_surface=True)
    # Scope to the BY SURFACE section only -- COVERAGE FUNNEL's "Analytics
    # truth" row always prints a hardcoded "100.00%" regardless of fixture,
    # which is a different (and already-covered) part of the output.
    surface_text = out[out.index("BY SURFACE"):]
    # Anchor to the three TOTAL lines specifically, not a raw occurrence
    # count -- a realistic fixture can also read 100.00% on an ordinary data
    # row (e.g. a dimension with only one observed value), which would
    # inflate a bare `.count("100.00%")` past 3 without indicating a defect.
    total_lines = [l for l in surface_text.splitlines() if l.strip().startswith("TOTAL")]
    assert len(total_lines) == 3
    assert all(l.rstrip().endswith("100.00%") for l in total_lines)


# ---- Criterion 14: --detail contains both daily and surface headers -----

def test_03_14_detail_contains_daily_and_surface_headers(tmp_db_path, monkeypatch):
    store = OtelStore(tmp_db_path)
    try:
        _seed_otel_row(store, session_id="s1", day="2026-07-14", token_type="input", tokens=10)
        store.commit()
    finally:
        store.close()
    _patch_truth_daily(monkeypatch, {"2026-07-14": {k: 0 for k in CANON}})
    out = _run_capture("2026-07-14", "2026-07-15", db=tmp_db_path, by_surface=True, daily=True)
    assert "\nDAILY" in out
    assert "BY SURFACE" in out


def test_main_detail_implies_by_surface_and_daily(monkeypatch):
    """CLI-flag wiring: --detail alone must set by_surface=True and daily=True
    on the call into run()."""
    captured_kwargs = {}

    def fake_run(start, end, db=None, emails=None, analytics_db=None, *,
                 by_surface=False, daily=False):
        captured_kwargs["by_surface"] = by_surface
        captured_kwargs["daily"] = daily

    monkeypatch.setattr(R, "run", fake_run)
    monkeypatch.setattr(
        "sys.argv", ["reconcile", "--start", "2026-07-14", "--end", "2026-07-15", "--detail"])
    R.main()
    assert captured_kwargs == {"by_surface": True, "daily": True}


# ---- Criterion 15: no-analytics-rows path and AnalyticsError path --------

def test_03_15_no_analytics_rows_path_prints_hint_and_no_funnel(
        tmp_db_path, analytics_db_path):
    # analytics_db is a fresh, empty Store -- zero user_cc_usage rows.
    Store(analytics_db_path).close()
    out = _run_capture("2026-07-14", "2026-07-15", db=tmp_db_path,
                       emails=["nobody@cyclotron.com"], analytics_db=analytics_db_path)
    assert "!! No analytics rows for" in out
    assert "python -m billing.ingest --start 2026-07-14 --end 2026-07-15" in out
    assert "COVERAGE FUNNEL" not in out


def test_03_15_analytics_error_path_prints_existing_message_and_no_funnel(
        tmp_db_path, monkeypatch):
    # Seam A -- task 03 pins Seam A for every one of its criteria.
    def raiser(start, end):
        raise AnalyticsError("token revoked")
    monkeypatch.setattr(R, "analytics_claude_code_daily", raiser)
    out = _run_capture("2026-07-14", "2026-07-15", db=tmp_db_path)
    assert "!! Could not reach Analytics API: token revoked" in out
    assert "(Is the token in .env valid? It may have been revoked.)" in out
    assert "COVERAGE FUNNEL" not in out


# ---- Criterion 16: rule lines equal length, no line exceeds it ------------

def test_03_16_rule_lines_equal_length_and_no_line_exceeds_them(tmp_db_path, monkeypatch):
    store = OtelStore(tmp_db_path)
    try:
        _seed_otel_row(store, session_id="s1", day="2026-07-14", token_type="input", tokens=10,
                       entrypoint=None)
        _seed_otel_row(store, session_id="s2", day="2026-07-14", token_type="cacheCreation5m",
                       tokens=5)
        _seed_drop(store, day="2026-07-14")
        store.commit()
    finally:
        store.close()
    _patch_truth_daily(monkeypatch, {"2026-07-14": {k: 0 for k in CANON}})
    out = _run_capture("2026-07-14", "2026-07-15", db=tmp_db_path, by_surface=True, daily=True)
    lines = out.splitlines()
    rule_lines = [l for l in lines if l and set(l) <= {"="} or l and set(l) <= {"-"}]
    rule_lengths = {len(l) for l in rule_lines}
    assert len(rule_lengths) == 1
    max_len = max(len(l) for l in lines)
    assert max_len <= next(iter(rule_lengths))


# ===========================================================================
# Regression coverage: --email / org-wide run() paths shipped with no test.
# ===========================================================================

def test_regression_user_totals_none_when_zero_rows(analytics_db_path):
    Store(analytics_db_path).close()
    result = analytics_user_totals(["a@cyclotron.com"], "2026-07-14", "2026-07-15",
                                   analytics_db=analytics_db_path)
    assert result is None


def test_regression_user_totals_shape_and_scoping(analytics_db_path):
    _seed_user_usage(analytics_db_path, day="2026-07-14", email="a@cyclotron.com",
                     uncached_input=10, output=5, cache_read=3,
                     cache_creation_1h=2, cache_creation_5m=1)
    # Excluded: different email, and a day outside the range.
    _seed_user_usage(analytics_db_path, day="2026-07-14", email="b@cyclotron.com",
                     uncached_input=999)
    _seed_user_usage(analytics_db_path, day="2026-08-01", email="a@cyclotron.com",
                     uncached_input=999)

    result = analytics_user_totals(["a@cyclotron.com"], "2026-07-14", "2026-07-15",
                                   analytics_db=analytics_db_path)
    assert result is not None
    totals, matched = result
    assert totals == {"input": 10, "output": 5, "cacheRead": 3, "cacheCreation": 3}
    assert matched == ["a@cyclotron.com"]


def test_regression_email_matching_case_and_whitespace_insensitive(analytics_db_path):
    _seed_user_usage(analytics_db_path, day="2026-07-14", email="a@x.com", uncached_input=1)
    result = analytics_user_totals(["A@X.com ", "b@x.com"], "2026-07-14", "2026-07-15",
                                   analytics_db=analytics_db_path)
    assert result is not None
    _totals, matched = result
    assert "a@x.com" in matched
    assert "b@x.com" not in matched


def test_regression_otel_totals_scopes_by_email(tmp_db_path):
    store = OtelStore(tmp_db_path)
    try:
        _seed_otel_row(store, session_id="s1", day="2026-07-14", token_type="input",
                       tokens=100, email="alice@cyclotron.com")
        _seed_otel_row(store, session_id="s2", day="2026-07-14", token_type="input",
                       tokens=50, email="bob@cyclotron.com")
        store.commit()
        result = otel_totals(store, "2026-07-14", "2026-07-15", emails=["alice@cyclotron.com"])
        assert result["captured"]["input"] == 100
    finally:
        store.close()


def test_regression_email_path_empty_analytics_prints_hint_no_funnel(
        tmp_db_path, analytics_db_path):
    Store(analytics_db_path).close()
    out = _run_capture("2026-07-14", "2026-07-15", db=tmp_db_path,
                       emails=["nobody@cyclotron.com"], analytics_db=analytics_db_path)
    assert "!! No analytics rows for" in out
    assert "billing.ingest" in out
    assert "COVERAGE FUNNEL" not in out


def test_regression_email_path_zero_otel_rows_prints_normal_funnel_no_synthetic(
        tmp_db_path, analytics_db_path):
    _seed_user_usage(analytics_db_path, day="2026-07-14", email="alice@cyclotron.com",
                     uncached_input=100)
    # OTEL store has zero matching rows for this email.
    OtelStore(tmp_db_path).close()
    out = _run_capture("2026-07-14", "2026-07-15", db=tmp_db_path,
                       emails=["alice@cyclotron.com"], analytics_db=analytics_db_path)
    assert "COVERAGE FUNNEL" in out
    assert "0.00%" in out
    assert "SYNTHETIC" not in out
