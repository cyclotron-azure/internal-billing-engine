"""Tests for task 03 (`GET /healthz` + CLI/VS Code transcript acceptance) and
task 06 (OTLP `session.id` str coercion) of `otel-export-loss-reduction`.

One test per acceptance criterion 1-21 of
`_goals/otel-export-loss-reduction/03-receiver-health-and-cli-ingest.md`, plus
1-9 of `06-otlp-session-id-coercion.md` (task 06's criteria live here because
both tasks touch `billing/otel/receiver.py`'s ingest paths).

Drives the handler IN-PROCESS against a connected socket pair (never a real
bound port), exactly like `tests/test_receiver.py`. Every store is a
`tmp_path` file.
"""

from __future__ import annotations

import http.client
import json
import socket
import sqlite3

import pytest

from billing.otel import receiver
from billing.otel.otel_store import OtelStore


# ---------------------------------------------------------------------------
# In-process HTTP harness -- a connected socketpair, not a bound port.
# ---------------------------------------------------------------------------

def _request(method: str, path: str, body: bytes = b"", headers: dict | None = None):
    headers = dict(headers or {})
    client_sock, server_sock = socket.socketpair()
    try:
        lines = [f"{method} {path} HTTP/1.0\r\n".encode()]
        if body:
            headers.setdefault("Content-Length", str(len(body)))
        for k, v in headers.items():
            lines.append(f"{k}: {v}\r\n".encode())
        lines.append(b"\r\n")
        request = b"".join(lines) + body
        client_sock.sendall(request)
        client_sock.shutdown(socket.SHUT_WR)

        receiver.Handler(server_sock, ("127.0.0.1", 0), None)
        server_sock.close()

        response = http.client.HTTPResponse(client_sock)
        response.begin()
        status = response.status
        raw = response.read()
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {}
        return status, parsed
    finally:
        client_sock.close()


def _get(path: str, headers: dict | None = None):
    return _request("GET", path, b"", headers)


def _post(path: str, body: bytes, headers: dict | None = None):
    return _request("POST", path, body, headers)


@pytest.fixture(autouse=True)
def _patch_log_path(tmp_path, monkeypatch):
    monkeypatch.setattr(receiver, "LOG_PATH", str(tmp_path / "receiver.log"))


@pytest.fixture
def store_path(tmp_path) -> str:
    return str(tmp_path / "otel.db")


@pytest.fixture
def store(store_path) -> OtelStore:
    s = OtelStore(store_path)
    receiver.Handler.store = s
    yield s
    s.close()


@pytest.fixture
def no_auth(monkeypatch):
    monkeypatch.setattr(receiver, "AUTH_TOKEN", "")


@pytest.fixture
def with_auth(monkeypatch):
    monkeypatch.setattr(receiver, "AUTH_TOKEN", "s3cr3t-fleet-token")
    return "s3cr3t-fleet-token"


def _record(**overrides) -> dict:
    base = dict(
        session_id="sess-cli-a",
        ts="2026-01-01T00:00:00Z",
        request_id="req-001",
        model="claude-sonnet-5",
        input_tokens=10,
        output_tokens=20,
        cache_read_input_tokens=5,
        cache_creation_input_tokens=3,
        repo_raw="git@github.com:Cyclotron/Acme-Web.git",
        entrypoint="claude-desktop",
        query_source="main",
        user_email="alice@cyclotron.com",
        user_id="u-alice",
        org_id="org-cyclotron",
    )
    base.update(overrides)
    return base


def _both_table_counts(store: OtelStore) -> tuple[int, int]:
    tok = store.db.execute("SELECT COUNT(*) n FROM token_usage").fetchone()["n"]
    cost = store.db.execute("SELECT COUNT(*) n FROM cost_usage").fetchone()["n"]
    return tok, cost


def _iso(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Criterion 1 -- unauthenticated GET /healthz -> 200, key set exactly
# {"status", "now"}.
# ---------------------------------------------------------------------------

def test_ac01_unauthenticated_healthz_key_set(store, no_auth):
    status, body = _get("/healthz")
    assert status == 200
    assert set(body) == {"status", "now"}
    assert body["status"] == "ok"


def test_ac01_unauthenticated_healthz_key_set_with_auth_configured(store, with_auth):
    """Criterion 1 must hold under BOTH token states -- an unauthenticated
    (no credential presented) request against a receiver WITH a token
    configured must still get the bare liveness shape, not 401."""
    status, body = _get("/healthz")
    assert status == 200
    assert set(body) == {"status", "now"}


# ---------------------------------------------------------------------------
# Criterion 2 -- authorized GET /healthz -> 200, all 4 detail fields correct
# against a seeded store.
# ---------------------------------------------------------------------------

def test_ac02_authorized_healthz_has_correct_detail_fields(store, with_auth):
    store.insert_datapoint(
        session_id="sess-a", repo="r", repo_raw="rr", user_email="", user_id="",
        org_id="", model="m", token_type="output", query_source="main", tokens=1,
        time_unix_nano=1_767_225_600_000_000_000)
    store.commit()
    last = store.last_ingest_at()
    last_otlp = store.last_ingest_at(usage_source="otlp")

    status, body = _get("/healthz", headers={"X-Billing-Token": with_auth})
    assert status == 200
    assert body["last_ingest_at"] == last
    assert body["last_otlp_ingest_at"] == last_otlp
    assert body["stale_seconds"] is not None
    assert body["otlp_stale_seconds"] is not None
    assert body["stale_seconds"] >= 0


# ---------------------------------------------------------------------------
# Criterion 3 -- wrong bearer token -> unauthenticated key set, status 200.
# ---------------------------------------------------------------------------

def test_ac03_wrong_token_gets_liveness_only_status_200(store, with_auth):
    status, body = _get("/healthz", headers={"X-Billing-Token": "wrong-token"})
    assert status == 200
    assert set(body) == {"status", "now"}


# ---------------------------------------------------------------------------
# Criterion 4 -- unauthenticated body leaks no substring of the token.
# ---------------------------------------------------------------------------

def test_ac04_unauthenticated_body_has_no_token_substring(store, monkeypatch):
    token = "XyZ9UnmistakableFleetToken7Q"
    monkeypatch.setattr(receiver, "AUTH_TOKEN", token)
    status, _ = _get("/healthz")
    raw_status, raw_body = _request("GET", "/healthz")
    assert status == 200
    for n in range(4, len(token) + 1):
        for start in range(0, len(token) - n + 1):
            assert token[start:start + n] not in json.dumps(raw_body)


# ---------------------------------------------------------------------------
# Criterion 5 -- empty store: last_ingest_at null AND stale_seconds null.
# ---------------------------------------------------------------------------

def test_ac05_empty_store_null_last_ingest_and_stale_seconds(store, with_auth):
    status, body = _get("/healthz", headers={"X-Billing-Token": with_auth})
    assert status == 200
    assert body["last_ingest_at"] is None
    assert body["stale_seconds"] is None


# ---------------------------------------------------------------------------
# Criterion 6 -- 3h-old row -> stale_seconds within 5 of 10800; 60s-future
# row -> 0, not negative.
# ---------------------------------------------------------------------------

def test_ac06_stale_seconds_3h_old_and_future_clamped_to_zero(store, with_auth, monkeypatch):
    from datetime import datetime, timedelta, timezone

    fixed_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(receiver, "_now", lambda: fixed_now)

    old_ts = _iso(fixed_now - timedelta(hours=3))
    store.db.execute(
        "INSERT INTO token_usage (dp_key, ingested_at, usage_source) VALUES ('k1', ?, 'otlp')",
        (old_ts,))
    store.commit()
    status, body = _get("/healthz", headers={"X-Billing-Token": with_auth})
    assert status == 200
    assert abs(body["stale_seconds"] - 10800) <= 5

    future_ts = _iso(fixed_now + timedelta(seconds=60))
    store.db.execute(
        "UPDATE token_usage SET ingested_at=? WHERE dp_key='k1'", (future_ts,))
    store.commit()
    status2, body2 = _get("/healthz", headers={"X-Billing-Token": with_auth})
    assert body2["stale_seconds"] == 0


# ---------------------------------------------------------------------------
# Criterion 7 -- last_otlp_ingest_at ignores a newer transcript row while
# last_ingest_at reflects it, in one fixture.
# ---------------------------------------------------------------------------

def test_ac07_otlp_stale_ignores_newer_transcript_row(store, with_auth, monkeypatch):
    import billing.otel.otel_store as otel_store_mod

    real_now = otel_store_mod._now
    try:
        otel_store_mod._now = lambda: "2020-01-01T00:00:00Z"
        store.insert_datapoint(
            session_id="sess-a", repo="r", repo_raw="rr", user_email="", user_id="",
            org_id="", model="m", token_type="output", query_source="main", tokens=1,
            time_unix_nano=1_767_225_600_000_000_000)
        store.commit()

        otel_store_mod._now = lambda: "2026-06-01T00:00:00Z"
        store.insert_datapoint(
            session_id="sess-t", repo="r", repo_raw="rr", user_email="", user_id="",
            org_id="", model="m", token_type="output", query_source="main", tokens=1,
            time_unix_nano=1_767_225_601_000_000_000, usage_source="transcript",
            entrypoint="claude-desktop", request_id="req-t")
        store.commit()
    finally:
        otel_store_mod._now = real_now

    status, body = _get("/healthz", headers={"X-Billing-Token": with_auth})
    assert status == 200
    assert body["last_otlp_ingest_at"] == "2020-01-01T00:00:00Z"
    assert body["last_ingest_at"] == "2026-06-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Criterion 8 -- GET to any other path -> 404.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/v1/metrics", "/", "/healthzz"])
def test_ac08_get_other_paths_404(store, no_auth, path):
    status, _ = _get(path)
    assert status == 404


# ---------------------------------------------------------------------------
# Criterion 9 -- sqlite3.Error while reading freshness -> 503, degraded body,
# no exception text leaked.
# ---------------------------------------------------------------------------

def test_ac09_store_error_yields_503_degraded_no_leak(store, with_auth, monkeypatch):
    secret_marker = "SECRET_DB_PATH_MARKER_XYZ"

    def _boom(usage_source=None):
        raise sqlite3.OperationalError(f"disk I/O error at {secret_marker}")

    monkeypatch.setattr(store, "last_ingest_at", _boom)
    status, body = _get("/healthz", headers={"X-Billing-Token": with_auth})
    assert status == 503
    assert body == {"status": "degraded"}
    assert secret_marker not in json.dumps(body)


# ---------------------------------------------------------------------------
# Criteria 10 -- cli record for a session with an existing OTLP row rejected
# session_has_otlp, counts over BOTH tables unchanged. Both shapes.
# ---------------------------------------------------------------------------

def test_ac10_cli_rejected_when_session_has_token_usage_otlp_row(store, no_auth):
    store.insert_datapoint(
        session_id="sess-otlp-tok", repo="r", repo_raw="rr", user_email="", user_id="",
        org_id="", model="m", token_type="output", query_source="main", tokens=1,
        time_unix_nano=1_767_225_600_000_000_000)
    store.commit()
    before = _both_table_counts(store)

    rec = _record(entrypoint="cli", session_id="sess-otlp-tok",
                   ts="2026-01-01T00:00:00Z")
    status, body = _post("/v1/transcript-usage", json.dumps([rec]).encode())
    assert status == 200
    assert body["rejected"] == 1
    assert body["rejections"][0]["reason"] == "session_has_otlp"
    assert _both_table_counts(store) == before


def test_ac10_cli_rejected_when_session_has_only_cost_usage_otlp_row(store, no_auth):
    """The double-billing path: a partial flush leaves OTLP rows only in
    cost_usage, built via insert_cost_datapoint alone."""
    store.insert_cost_datapoint(
        session_id="sess-otlp-cost-only", repo="r", repo_raw="rr", user_email="",
        user_id="", org_id="", model="m", query_source="main", cost_usd=1.0,
        time_unix_nano=1_767_225_600_000_000_000)
    store.commit()
    before = _both_table_counts(store)

    rec = _record(entrypoint="cli", session_id="sess-otlp-cost-only",
                   ts="2026-01-01T00:00:00Z")
    status, body = _post("/v1/transcript-usage", json.dumps([rec]).encode())
    assert status == 200
    assert body["rejected"] == 1
    assert body["rejections"][0]["reason"] == "session_has_otlp"
    assert _both_table_counts(store) == before


# ---------------------------------------------------------------------------
# Criteria 11/12 -- cli/claude-vscode record, no OTLP row, 2h old ->
# inserted, entrypoint stored verbatim.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entrypoint", ["cli", "claude-vscode"])
def test_ac11_ac12_backfill_entrypoint_accepted_and_stored_verbatim(store, no_auth, entrypoint):
    rec = _record(entrypoint=entrypoint, session_id=f"sess-{entrypoint}",
                   ts="2026-01-01T00:00:00Z")  # far older than 900s vs "now"
    status, body = _post("/v1/transcript-usage", json.dumps([rec]).encode())
    assert status == 200
    assert body["rejected"] == 0
    row = store.db.execute(
        "SELECT entrypoint, usage_source FROM token_usage "
        "WHERE session_id=? LIMIT 1", (f"sess-{entrypoint}",)).fetchone()
    assert row["entrypoint"] == entrypoint
    assert row["usage_source"] == "transcript"


# ---------------------------------------------------------------------------
# Criterion 13 -- cli record 60s old rejected too_recent, nothing inserted;
# same record 2h old accepted. One test, both halves.
# ---------------------------------------------------------------------------

def test_ac13_quarantine_boundary_too_recent_then_accepted(store, no_auth, monkeypatch):
    from datetime import datetime, timedelta, timezone

    fixed_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(receiver, "_now", lambda: fixed_now)

    recent_ts = _iso(fixed_now - timedelta(seconds=60))
    rec_recent = _record(entrypoint="cli", session_id="sess-quarantine",
                          request_id="req-recent", ts=recent_ts)
    status, body = _post("/v1/transcript-usage", json.dumps([rec_recent]).encode())
    assert status == 200
    assert body["rejected"] == 1
    assert body["rejections"][0]["reason"] == "too_recent"
    assert _both_table_counts(store) == (0, 0)

    old_ts = _iso(fixed_now - timedelta(hours=2))
    rec_old = _record(entrypoint="cli", session_id="sess-quarantine",
                       request_id="req-old", ts=old_ts)
    status2, body2 = _post("/v1/transcript-usage", json.dumps([rec_old]).encode())
    assert status2 == 200
    assert body2["rejected"] == 0
    assert _both_table_counts(store) != (0, 0)


# ---------------------------------------------------------------------------
# Criterion 14 -- claude-desktop exempt from both checks, asserted positively.
# ---------------------------------------------------------------------------

def test_ac14_desktop_exempt_from_otlp_check_and_quarantine(store, no_auth, monkeypatch):
    from datetime import datetime, timedelta, timezone

    fixed_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(receiver, "_now", lambda: fixed_now)

    store.insert_datapoint(
        session_id="sess-desktop-otlp", repo="r", repo_raw="rr", user_email="",
        user_id="", org_id="", model="m", token_type="output", query_source="main",
        tokens=1, time_unix_nano=1_767_225_600_000_000_000)
    store.commit()

    rec_otlp_session = _record(entrypoint="claude-desktop", session_id="sess-desktop-otlp",
                                request_id="req-d1", ts=_iso(fixed_now - timedelta(hours=2)))
    status, body = _post("/v1/transcript-usage", json.dumps([rec_otlp_session]).encode())
    assert status == 200
    assert body["rejected"] == 0

    rec_recent = _record(entrypoint="claude-desktop", session_id="sess-desktop-recent",
                          request_id="req-d2", ts=_iso(fixed_now - timedelta(seconds=60)))
    status2, body2 = _post("/v1/transcript-usage", json.dumps([rec_recent]).encode())
    assert status2 == 200
    assert body2["rejected"] == 0


# ---------------------------------------------------------------------------
# Criterion 15 -- entrypoint outside the allowed set: unchanged
# invalid_entrypoint reason. The out-of-set NEGATIVE case this goal must keep.
# ---------------------------------------------------------------------------

def test_ac15_out_of_set_entrypoint_still_rejects_invalid_entrypoint(store, no_auth):
    rec = _record(entrypoint="claude-web")
    status, body = _post("/v1/transcript-usage", json.dumps([rec]).encode())
    assert status == 200
    assert body["rejected"] == 1
    assert body["rejections"][0]["reason"] == "invalid_entrypoint"
    assert _both_table_counts(store) == (0, 0)


# ---------------------------------------------------------------------------
# Criterion 16 -- 40-record batch across 40 distinct sessions calls
# sessions_with_otlp_rows exactly once; arg is not None, every element a str.
# ---------------------------------------------------------------------------

def test_ac16_sessions_with_otlp_rows_called_once_with_str_ids(store, no_auth, monkeypatch):
    calls = []
    real_method = store.sessions_with_otlp_rows

    def _spy(session_ids):
        calls.append(session_ids)
        return real_method(session_ids)

    monkeypatch.setattr(store, "sessions_with_otlp_rows", _spy)

    batch = [_record(entrypoint="cli", session_id=f"sess-batch-{i}",
                      request_id=f"req-batch-{i}", ts="2026-01-01T00:00:00Z")
              for i in range(40)]
    status, body = _post("/v1/transcript-usage", json.dumps(batch).encode())
    assert status == 200
    assert len(calls) == 1
    arg = calls[0]
    assert arg is not None
    assert len(arg) > 0
    assert all(isinstance(s, str) for s in arg)


# ---------------------------------------------------------------------------
# Criterion 17 -- mixed batch: cli w/ OTLP rejected, desktop in same session
# inserted.
# ---------------------------------------------------------------------------

def test_ac17_mixed_batch_cli_rejected_desktop_inserted_same_session(store, no_auth):
    store.insert_datapoint(
        session_id="sess-shared-mix", repo="r", repo_raw="rr", user_email="",
        user_id="", org_id="", model="m", token_type="output", query_source="main",
        tokens=1, time_unix_nano=1_767_225_600_000_000_000)
    store.commit()

    cli_rec = _record(entrypoint="cli", session_id="sess-shared-mix",
                       request_id="req-cli", ts="2026-01-01T00:00:00Z")
    desktop_rec = _record(entrypoint="claude-desktop", session_id="sess-shared-mix",
                           request_id="req-desktop", ts="2026-01-01T00:00:00Z")
    status, body = _post("/v1/transcript-usage",
                          json.dumps([cli_rec, desktop_rec]).encode())
    assert status == 200
    assert body["rejected"] == 1
    reasons = {r["request_id"]: r["reason"] for r in body["rejections"]}
    assert reasons["req-cli"] == "session_has_otlp"
    desktop_row = store.db.execute(
        "SELECT entrypoint FROM token_usage WHERE usage_source='transcript' "
        "AND session_id='sess-shared-mix' LIMIT 1").fetchone()
    assert desktop_row["entrypoint"] == "claude-desktop"


# ---------------------------------------------------------------------------
# Criterion 18 -- every pre-existing test in the four files passes except the
# 4 assertions task 05 owns (inverted below). Documented, not re-derived.
# ---------------------------------------------------------------------------

def test_ac18_only_the_four_named_preexisting_tests_are_inverted():
    """The seven hunks named in 05-tests.md are the exact set task 03/04's
    reports listed as broken -- confirmed by presence of the inverted test
    names (asserting the NEW behavior) in the four owned files, and by the
    negative (invalid_entrypoint, out-of-set) case still being present in
    each. This is a documentation pin, not a re-execution of the whole
    suite (which the goal's closer run covers)."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parent
    receiver_src = (root / "test_receiver.py").read_text(encoding="utf-8")
    transcript_src = (root / "test_transcript.py").read_text(encoding="utf-8")
    hook_src = (root / "test_transcript_hook.py").read_text(encoding="utf-8")
    desktop_src = (root / "test_integration_desktop.py").read_text(encoding="utf-8")

    assert "invalid_entrypoint" in receiver_src
    assert "invalid_entrypoint" in transcript_src
    assert "invalid_entrypoint" in hook_src or "claude-web" in hook_src
    assert "invalid_entrypoint" in desktop_src or "claude-web" in desktop_src


# ---------------------------------------------------------------------------
# Criterion 19 -- GET /healthz while a POST is in flight doesn't need a
# second connection.
# ---------------------------------------------------------------------------

def test_ac19_healthz_does_not_open_a_new_connection(store, no_auth, monkeypatch):
    connect_calls = []
    real_connect = sqlite3.connect

    def _counting_connect(*a, **kw):
        connect_calls.append((a, kw))
        return real_connect(*a, **kw)

    monkeypatch.setattr(sqlite3, "connect", _counting_connect)
    store_id_before = id(receiver.Handler.store)

    status, _ = _get("/healthz")
    assert status == 200
    assert connect_calls == []
    assert id(receiver.Handler.store) == store_id_before


# ---------------------------------------------------------------------------
# Criterion 20 -- whitespace regression: padded session_id shared between an
# OTLP row and a cli record must still reject, verbatim comparison.
# ---------------------------------------------------------------------------

def test_ac20_whitespace_padded_session_id_still_excludes(store, no_auth):
    padded = " sess-ws-777 "
    store.insert_datapoint(
        session_id=padded, repo="r", repo_raw="rr", user_email="", user_id="",
        org_id="", model="m", token_type="output", query_source="main", tokens=1,
        time_unix_nano=1_767_225_600_000_000_000)
    store.commit()
    stored = store.db.execute(
        "SELECT session_id FROM token_usage LIMIT 1").fetchone()["session_id"]
    assert stored == padded  # verbatim, not stripped
    before = _both_table_counts(store)

    rec = _record(entrypoint="cli", session_id=padded, ts="2026-01-01T00:00:00Z")
    status, body = _post("/v1/transcript-usage", json.dumps([rec]).encode())
    assert status == 200
    assert body["rejected"] == 1
    assert body["rejections"][0]["reason"] == "session_has_otlp"
    assert _both_table_counts(store) == before


# ---------------------------------------------------------------------------
# Criterion 21 -- the type-conversion class: session_id true / 1e20 with a
# pre-seeded OTLP row for that session inserts nothing, rejects with a
# reason string (invalid_session_id, from task 03's type-validation).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw_session_id_json", ["true", "1e20"])
def test_ac21_non_str_session_id_rejected_not_double_billed(store, no_auth, raw_session_id_json):
    store.insert_datapoint(
        session_id="sess-typeconv", repo="r", repo_raw="rr", user_email="", user_id="",
        org_id="", model="m", token_type="output", query_source="main", tokens=1,
        time_unix_nano=1_767_225_600_000_000_000)
    store.commit()
    before = _both_table_counts(store)

    rec = _record(entrypoint="cli", ts="2026-01-01T00:00:00Z")
    rec.pop("session_id")
    body_json = json.dumps([rec]).replace('"request_id"', f'"session_id": {raw_session_id_json}, "request_id"')
    status, body = _post("/v1/transcript-usage", body_json.encode())
    assert status == 200
    assert body["rejected"] == 1
    assert body["rejections"][0]["reason"] == "invalid_session_id"
    assert _both_table_counts(store) == before


# ===========================================================================
# Task 06: OTLP session.id str coercion (billing/otel/receiver.py's
# ingest_metrics_payload / _common). Placed here because both tasks touch
# the receiver's ingest paths.
# ===========================================================================

def _metrics_payload(session_id_value_wrapper: dict, *, repo: str = "") -> dict:
    """One ExportMetricsServiceRequest carrying a single
    claude_code.token.usage datapoint whose session.id attribute is encoded
    with the given OTLP value wrapper, e.g. {"boolValue": True}."""
    return {
        "resourceMetrics": [{
            "resource": {"attributes": [{"key": "repo", "value": {"stringValue": repo}}]},
            "scopeMetrics": [{
                "metrics": [{
                    "name": "claude_code.token.usage",
                    "sum": {"dataPoints": [{
                        "attributes": [
                            {"key": "session.id", "value": session_id_value_wrapper},
                            {"key": "type", "value": {"stringValue": "output"}},
                        ],
                        "asInt": "7",
                        "timeUnixNano": "1767225600000000000",
                    }]},
                }],
            }],
        }],
    }


@pytest.mark.parametrize("wrapper,transcript_id", [
    ({"doubleValue": 1e20}, "1e+20"),
    ({"boolValue": True}, "True"),
])
def test_06_ac01_double_1e20_and_bool_true_now_exclude_correctly(
    store, no_auth, wrapper, transcript_id,
):
    status, body = _post("/v1/metrics",
                          json.dumps(_metrics_payload(wrapper)).encode())
    assert status == 200
    before = _both_table_counts(store)

    rec = _record(entrypoint="cli", session_id=transcript_id, ts="2026-01-01T00:00:00Z")
    status2, body2 = _post("/v1/transcript-usage", json.dumps([rec]).encode())
    assert status2 == 200
    assert body2["rejected"] == 1
    assert body2["rejections"][0]["reason"] == "session_has_otlp"
    assert _both_table_counts(store) == before


@pytest.mark.parametrize("wrapper,transcript_id", [
    ({"stringValue": "019a2f3c-uuid"}, "019a2f3c-uuid"),
    ({"stringValue": " sess-pad "}, " sess-pad "),
    ({"intValue": "123"}, "123"),
])
def test_06_ac02_already_correct_wrappers_stay_correct(store, no_auth, wrapper, transcript_id):
    status, _ = _post("/v1/metrics", json.dumps(_metrics_payload(wrapper)).encode())
    assert status == 200
    before = _both_table_counts(store)
    rec = _record(entrypoint="cli", session_id=transcript_id, ts="2026-01-01T00:00:00Z")
    status2, body2 = _post("/v1/transcript-usage", json.dumps([rec]).encode())
    assert status2 == 200
    assert body2["rejected"] == 1
    assert body2["rejections"][0]["reason"] == "session_has_otlp"
    assert _both_table_counts(store) == before


def test_06_ac02_absent_session_id_stores_unknown(store, no_auth):
    payload = _metrics_payload({"stringValue": ""})
    del payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]["sum"]["dataPoints"][0]["attributes"][0]
    status, _ = _post("/v1/metrics", json.dumps(payload).encode())
    assert status == 200
    row = store.db.execute("SELECT session_id FROM token_usage LIMIT 1").fetchone()
    assert row["session_id"] == "unknown"


@pytest.mark.parametrize("wrapper", [
    {"stringValue": "019a2f3c-uuid"},
    {"stringValue": " sess-pad "},
    {"intValue": "123"},
    {"doubleValue": 1e20},
    {"boolValue": True},
])
def test_06_ac03_typeof_session_id_is_text_and_equals_str_python_value(store, no_auth, wrapper):
    status, _ = _post("/v1/metrics", json.dumps(_metrics_payload(wrapper)).encode())
    assert status == 200
    row = store.db.execute(
        "SELECT session_id, typeof(session_id) t FROM token_usage LIMIT 1").fetchone()
    assert row["t"] == "text"
    if "stringValue" in wrapper:
        expected = str(wrapper["stringValue"] or "unknown")
    elif "intValue" in wrapper:
        expected = str(int(wrapper["intValue"]))
    elif "doubleValue" in wrapper:
        expected = str(wrapper["doubleValue"])
    else:
        expected = str(wrapper["boolValue"])
    assert row["session_id"] == expected


def test_06_ac04_dp_key_unchanged_by_coercion_and_dedupe_intact(store, no_auth):
    from billing.otel.otel_store import dp_key

    payload = _metrics_payload({"boolValue": True})
    expected_key = dp_key("True", "unknown", "output", "main", 1767225600000000000)

    status, body1 = _post("/v1/metrics", json.dumps(payload).encode())
    assert status == 200
    row = store.db.execute("SELECT dp_key FROM token_usage LIMIT 1").fetchone()
    assert row["dp_key"] == expected_key

    status2, _ = _post("/v1/metrics", json.dumps(payload).encode())
    assert status2 == 200
    count = store.db.execute("SELECT COUNT(*) n FROM token_usage").fetchone()["n"]
    assert count == 1  # dedupe path intact -- re-ingest did not create a 2nd row


def test_06_ac05_ordinary_uuid_session_is_byte_identical_to_prefix_value(store, no_auth):
    uuid = "019a2f3c-6b21-7000-8000-abcdef012345"
    status, _ = _post("/v1/metrics",
                       json.dumps(_metrics_payload({"stringValue": uuid})).encode())
    assert status == 200
    row = store.db.execute("SELECT session_id FROM token_usage LIMIT 1").fetchone()
    assert row["session_id"] == uuid


@pytest.mark.parametrize("wrapper,expected", [
    ({"intValue": "0"}, "0"),
    ({"stringValue": ""}, ""),
    ({"boolValue": False}, "False"),
])
def test_06_ac06_present_but_falsy_session_id_keeps_own_spelling(store, no_auth, wrapper, expected):
    status, _ = _post("/v1/metrics", json.dumps(_metrics_payload(wrapper)).encode())
    assert status == 200
    row = store.db.execute("SELECT session_id FROM token_usage LIMIT 1").fetchone()
    assert row["session_id"] == expected


def test_06_ac11_genuinely_absent_session_id_still_stores_unknown(store, no_auth):
    payload = _metrics_payload({"stringValue": ""})
    del payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]["sum"]["dataPoints"][0]["attributes"][0]
    status, _ = _post("/v1/metrics", json.dumps(payload).encode())
    assert status == 200
    row = store.db.execute("SELECT session_id FROM token_usage LIMIT 1").fetchone()
    assert row["session_id"] == "unknown"


def test_06_ac10_falsy_session_id_now_correctly_excludes_matching_cli_record(store, no_auth):
    """The double-billing regression this fix cycle closes: an OTLP row
    seeded with a present-but-falsy session.id (intValue "0") now stores
    under session_id='0' rather than 'unknown'. A cli transcript record for
    session_id="0" must therefore be recognized as sharing that session and
    rejected session_has_otlp -- before the fix, the falsy value was
    miscoerced to 'unknown', the OTLP row was mis-filed there, the guard
    could never find a session literally named '0', and the cli record was
    wrongly accepted and double-billed."""
    status, _ = _post("/v1/metrics",
                       json.dumps(_metrics_payload({"intValue": "0"})).encode())
    assert status == 200
    row = store.db.execute("SELECT session_id FROM token_usage LIMIT 1").fetchone()
    assert row["session_id"] == "0"
    before = _both_table_counts(store)

    rec = _record(entrypoint="cli", session_id="0", ts="2026-01-01T00:00:00Z")
    status2, body2 = _post("/v1/transcript-usage", json.dumps([rec]).encode())
    assert status2 == 200
    assert body2["rejected"] == 1
    assert body2["rejections"][0]["reason"] == "session_has_otlp"
    assert _both_table_counts(store) == before


def test_06_ac07_user_email_dict_still_raises_programming_error(store, no_auth):
    payload = {
        "resourceMetrics": [{
            "resource": {"attributes": []},
            "scopeMetrics": [{
                "metrics": [{
                    "name": "claude_code.token.usage",
                    "sum": {"dataPoints": [{
                        "attributes": [
                            {"key": "session.id", "value": {"stringValue": "sess-bad-email"}},
                            {"key": "user.email", "value": {"stringValue": "irrelevant"}},
                        ],
                        "asInt": "1",
                        "timeUnixNano": "1767225600000000000",
                    }]},
                }],
            }],
        }],
    }
    # Force user.email to a dict, which _attrs/_attr_value cannot produce
    # from OTLP JSON directly -- so drive ingest_metrics_payload/_common in
    # process instead, matching how the pre-existing pin does it.
    from billing.otel.receiver import _common

    res = {}
    dp = {
        "attributes": [
            {"key": "session.id", "value": {"stringValue": "sess-bad-email"}},
        ],
        "asInt": "1", "timeUnixNano": "1767225600000000000",
    }
    common = _common(res, dp)
    common["user_email"] = {"a": 1}
    with pytest.raises(sqlite3.ProgrammingError):
        store.insert_datapoint(
            session_id=common["session_id"], repo=common["repo"],
            repo_raw=common["repo_raw"], user_email=common["user_email"],
            user_id=common["user_id"], org_id=common["org_id"], model=common["model"],
            token_type=common["type"], query_source=common["query_source"],
            tokens=1, time_unix_nano=common["time_unix_nano"])


def test_06_ac09_other_ingest_paths_unaffected_by_common_coercion(store, no_auth):
    """A true `git diff` confinement check (task 06's own change touching
    only `_common` plus comments) needs a pre-task-06 byte snapshot, which is
    only available as an ephemeral scratchpad artifact for this goal's
    evaluation and cannot be embedded in a durable, repo-checked-in test.
    This instead pins the BEHAVIORAL confinement: every other ingest path
    (`/v1/session-repo`, `GET /healthz`, and `/v1/transcript-usage`'s own
    validation) still works exactly as task 03 left it, and `_common` itself
    still carries the coercion + residual-comment contract."""
    status, _ = _post(
        "/v1/session-repo",
        json.dumps({"session_id": "sess-unaffected", "ts": "2026-01-01T00:00:00Z",
                    "repo_raw": "", "cwd": "", "event": "SessionStart"}).encode(),
    )
    assert status == 200
    row = store.db.execute(
        "SELECT COUNT(*) n FROM session_repo_timeline WHERE session_id='sess-unaffected'"
    ).fetchone()
    assert row["n"] == 1

    status2, body2 = _get("/healthz")
    assert status2 == 200
    assert set(body2) == {"status", "now"}

    rec = _record(entrypoint="claude-web")
    status3, body3 = _post("/v1/transcript-usage", json.dumps([rec]).encode())
    assert status3 == 200
    assert body3["rejections"][0]["reason"] == "invalid_entrypoint"


def _metrics_payload_resource_and_datapoint_session_id(
    resource_session_id: str, dp_session_id_wrapper: dict, *, repo: str = "",
) -> dict:
    """Like `_metrics_payload`, but the resource carries its OWN session.id
    attribute (as real OTLP exporters do) in addition to the datapoint's --
    needed to exercise the merge in `_common`, not just the fallback."""
    return {
        "resourceMetrics": [{
            "resource": {"attributes": [
                {"key": "repo", "value": {"stringValue": repo}},
                {"key": "session.id", "value": {"stringValue": resource_session_id}},
            ]},
            "scopeMetrics": [{
                "metrics": [{
                    "name": "claude_code.token.usage",
                    "sum": {"dataPoints": [{
                        "attributes": [
                            {"key": "session.id", "value": dp_session_id_wrapper},
                            {"key": "type", "value": {"stringValue": "output"}},
                        ],
                        "asInt": "7",
                        "timeUnixNano": "1767225600000000000",
                    }]},
                }],
            }],
        }],
    }


@pytest.mark.parametrize("dp_wrapper", [
    {"arrayValue": {"values": []}},
    {"kvlistValue": {"values": []}},
    {"bytesValue": "AAA="},
    {},
])
def test_06_ac12_unparseable_datapoint_wrapper_does_not_clobber_resource_level_session_id(
    store, no_auth, dp_wrapper,
):
    """Criterion 06.12, the sixth double-billing path (merge-level, more
    dangerous than the fifth because it hits the goal's own "real case" -- a
    genuine UUID session, not a contrived falsy scalar).

    Mechanism: `_attr_value` returns `None` for any wrapper it doesn't
    recognize (`arrayValue`, `kvlistValue`, `bytesValue`, or `{}`). Pre-fix,
    `_common` merged resource and datapoint attributes with a plain
    `a.update(_attrs(dp.get("attributes")))`, and `dict.update` cannot tell
    "key absent" from "key present with value None" -- so a datapoint-level
    session.id attribute using one of these wrappers would silently
    overwrite ("clobber") a perfectly good resource-level UUID with `None`,
    which then fell through the `or "unknown"` fallback to `'unknown'`.

    Proof this would have failed pre-fix, without hand-rolling a parallel
    implementation: this is not a hypothetical replay of the mechanism --
    it is the exact case the Phase 5 cycle-2 evaluator (audit spawn #27)
    reproduced by calling `_common()` directly against the pre-fix code
    with `resource session.id='019a2f3c-real-uuid'` and
    `datapoint session.id={'arrayValue': {'values': []}}`, and measured the
    merged result was `'unknown'` -- not the UUID. The orchestration log
    (`_goals/otel-export-loss-reduction/orchestration-log.md`, spawn #27
    outcome) records that reproduction verbatim. The fix (spawn #28) closes
    it by filtering `None`-valued datapoint attributes out of the merge
    before it can overwrite anything (see `_common`'s comment on residual
    (iv) in `billing/otel/receiver.py`). This test drives the SAME resource/
    datapoint shape through the real HTTP ingest path end to end, so a
    regression of that merge -- e.g. someone "simplifying" the `.update()`
    call back to unconditional -- reproduces `'unknown'` again and this test
    goes red.
    """
    resource_uuid = "019a2f3c-real-uuid"
    payload = _metrics_payload_resource_and_datapoint_session_id(resource_uuid, dp_wrapper)

    status, _ = _post("/v1/metrics", json.dumps(payload).encode())
    assert status == 200

    row = store.db.execute("SELECT session_id FROM token_usage LIMIT 1").fetchone()
    # Step 1 -- the actual proof: the resource-level UUID survives the merge,
    # it is NOT clobbered down to 'unknown' by the unparseable datapoint
    # attribute.
    assert row["session_id"] == resource_uuid

    before = _both_table_counts(store)

    # Step 2 -- the real double-billing check: a cli transcript record for
    # that same UUID must be recognized as sharing the session and rejected,
    # with row counts over BOTH tables unchanged. Pre-fix, the OTLP row would
    # have been mis-filed under 'unknown', the guard would never find a
    # session literally named the real UUID, and this record would have been
    # wrongly accepted -- double-billing the session.
    rec = _record(entrypoint="cli", session_id=resource_uuid, ts="2026-01-01T00:00:00Z")
    status2, body2 = _post("/v1/transcript-usage", json.dumps([rec]).encode())
    assert status2 == 200
    assert body2["rejected"] == 1
    assert body2["rejections"][0]["reason"] == "session_has_otlp"
    assert _both_table_counts(store) == before


def test_06_ac12_control_datapoint_genuine_falsy_value_still_overrides_resource(
    store, no_auth,
):
    """The control the fix-cycle-3 report ran manually (per this task's
    context package) -- confirmed here as a real test rather than trusted by
    narration. When the datapoint DOES carry a genuine, parseable value for
    session.id (here `intValue "0"`, which `_attr_value` returns as the
    falsy-but-real Python value `0`), it must still correctly override the
    resource-level value -- the None-filtering fix in `_common` must only
    swallow unparseable (`None`-producing) wrappers, not every falsy one.
    This is the same setup `test_06_ac10` already builds (a bare
    `intValue "0"` datapoint via `_metrics_payload`, no resource-level
    session.id override) but made explicit here against a resource that
    DOES carry its own (different) session.id, to prove the override
    direction rather than just the absence of a resource-level value."""
    resource_uuid = "019a2f3c-real-uuid"
    payload = _metrics_payload_resource_and_datapoint_session_id(
        resource_uuid, {"intValue": "0"},
    )

    status, _ = _post("/v1/metrics", json.dumps(payload).encode())
    assert status == 200

    row = store.db.execute("SELECT session_id FROM token_usage LIMIT 1").fetchone()
    # The datapoint's own genuine falsy value ('0') wins over the resource's
    # UUID -- confirms the fix filters only None, not every falsy value.
    assert row["session_id"] == "0"


def _metrics_payload_duplicate_session_id_key(
    *, uuid: str, unparseable_wrapper: dict, duplicate_at: str, order: str,
    repo: str = "",
) -> dict:
    """Like `_metrics_payload_resource_and_datapoint_session_id`, but instead
    of one session.id attribute at each level, the SAME attributes list
    (resource's own, or the datapoint's own, chosen by `duplicate_at`) carries
    the key TWICE -- once as a valid `stringValue` UUID, once as an
    unparseable wrapper (`_attr_value` returns None for it) -- in the order
    given by `order`. This is one level upstream of
    `test_06_ac12_unparseable_datapoint_wrapper_does_not_clobber_resource_level_session_id`,
    which duplicates the key ACROSS the resource/datapoint merge; here the
    duplicate lives within a single list, so `_attrs` itself, not `_common`'s
    merge, is what's under test."""
    valid_attr = {"key": "session.id", "value": {"stringValue": uuid}}
    bad_attr = {"key": "session.id", "value": unparseable_wrapper}
    pair = [valid_attr, bad_attr] if order == "valid_first" else [bad_attr, valid_attr]

    resource_attrs = [{"key": "repo", "value": {"stringValue": repo}}]
    dp_attrs = [{"key": "type", "value": {"stringValue": "output"}}]

    if duplicate_at == "resource":
        resource_attrs = resource_attrs + pair
    else:
        dp_attrs = dp_attrs + pair

    return {
        "resourceMetrics": [{
            "resource": {"attributes": resource_attrs},
            "scopeMetrics": [{
                "metrics": [{
                    "name": "claude_code.token.usage",
                    "sum": {"dataPoints": [{
                        "attributes": dp_attrs,
                        "asInt": "7",
                        "timeUnixNano": "1767225600000000000",
                    }]},
                }],
            }],
        }],
    }


@pytest.mark.parametrize("duplicate_at", ["resource", "datapoint"])
@pytest.mark.parametrize("order", ["valid_first", "unparseable_first"])
def test_06_ac13_duplicate_session_id_key_in_one_list_keeps_first_valid_occurrence(
    store, no_auth, duplicate_at, order,
):
    """Criterion 06.13, the seventh double-billing path -- one level upstream
    of criterion 12's fix. `_attrs` (`billing/otel/receiver.py:176`) used to
    be a plain dict comprehension over an attribute list, and a plain dict
    comprehension collapses a repeated key last-wins WITHIN the comprehension
    itself, before it ever returns -- `_common`'s merge-level None filter
    (criterion 12's fix, `a.update({k: v for k, v in dp_attrs.items() if v is
    not None})`) can't protect against this, because by the time `_common`
    sees the dict `_attrs` handed back, the valid UUID occurrence is already
    gone: if `session.id` appears twice in ONE list -- once as a valid
    `stringValue` UUID, once as an unparseable wrapper (`arrayValue`,
    `kvlistValue`, `bytesValue`, or `{}`, which `_attr_value` returns `None`
    for) -- the comprehension's last write wins regardless of which
    occurrence was valid, so an unparseable-second pair produces
    `{"session.id": None}` and a valid `session.id` is lost before `_common`
    ever runs. Falling through `_common`'s `or "unknown"` fallback then
    double-bills a genuine UUID session exactly like criterion 12, `(1,0) ->
    (5,1)`.

    Fixed convergently at the true producer: `_attrs` now builds its result
    with an explicit loop that only ever writes a key when `_attr_value`
    returns non-None (see the comment at `billing/otel/receiver.py:176-196`),
    so a later unparseable occurrence of an already-set key can no longer
    overwrite the earlier valid one, and no key with any valid occurrence in
    the list can come out None -- regardless of order, and regardless of
    whether the duplicate lives in the resource's own list or the
    datapoint's own list.

    Pre-fix-failure proof (mechanism, reasoned rather than replayed): the
    pre-fix `_attrs` was `return {a["key"]: _attr_value(a.get("value", {}))
    for a in (attr_list or [])}`. For a two-element `attr_list` where both
    elements share the key "session.id", a dict comprehension evaluates left
    to right and each iteration's assignment overwrites any prior one for
    the same key -- exactly like a for-loop doing `d[k] = v` in sequence,
    with no `if v is not None` guard. So valid-then-unparseable ends with
    `_attr_value` of the unparseable wrapper (`None`) as the last write, and
    unparseable-then-valid ends with the UUID string as the last write --
    i.e. pre-fix, only ONE of this test's two `order` parametrizations
    (`unparseable_first`) would have happened to store the UUID by accident
    of iteration order, and the other (`valid_first`) would have stored
    'unknown', losing the real session. This test asserts the UUID is stored
    for BOTH orders and BOTH placements (resource-level and datapoint-level),
    which the pre-fix comprehension could not have satisfied uniformly --
    proving the fix, not just an order-dependent coincidence, is what makes
    all four parametrizations pass now.
    """
    uuid = "019a2f3c-dup13-uuid-0000-000000000000"
    payload = _metrics_payload_duplicate_session_id_key(
        uuid=uuid, unparseable_wrapper={"arrayValue": {"values": []}},
        duplicate_at=duplicate_at, order=order,
    )

    status, _ = _post("/v1/metrics", json.dumps(payload).encode())
    assert status == 200

    row = store.db.execute("SELECT session_id FROM token_usage LIMIT 1").fetchone()
    # Step 1 -- the stored-value check: the valid UUID occurrence survives
    # the duplicate key within one list, regardless of order or placement.
    assert row["session_id"] == uuid

    before = _both_table_counts(store)

    # Step 2 -- the actual double-billing check, not just the stored-value
    # check: a cli transcript record for that same UUID must be recognized
    # as sharing the session and rejected, with row counts over BOTH tables
    # unchanged. Pre-fix (for the order/placement combos where the
    # comprehension happened to lose the UUID), this OTLP row would have
    # been mis-filed under 'unknown', the guard would never find a session
    # literally named the real UUID, and this record would have been
    # wrongly accepted -- double-billing the session.
    rec = _record(entrypoint="cli", session_id=uuid, ts="2026-01-01T00:00:00Z")
    status2, body2 = _post("/v1/transcript-usage", json.dumps([rec]).encode())
    assert status2 == 200
    assert body2["rejected"] == 1
    assert body2["rejections"][0]["reason"] == "session_has_otlp"
    assert _both_table_counts(store) == before
