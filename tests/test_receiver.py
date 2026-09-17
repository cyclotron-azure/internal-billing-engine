"""Tests for task 03: POST /v1/transcript-usage on billing/otel/receiver.py.

Drives the handler IN-PROCESS against a connected socket pair (never a real
bound port) so do_POST runs exactly as it would in production, including
auth, body reading (gzip/chunked via _read_body), JSON parsing, per-record
validation via transcript.py, and store writes via otel_store.py.
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

def _post(path: str, body: bytes, headers: dict | None = None) -> tuple[int, dict]:
    """POST `body` to `path` against receiver.Handler, in-process.

    Returns (status_code, parsed_json_body_or_empty_dict). Uses HTTP/1.0 so
    the handler closes the connection after one request (no keep-alive loop
    to manage).
    """
    headers = dict(headers or {})
    client_sock, server_sock = socket.socketpair()
    try:
        lines = [f"POST {path} HTTP/1.0\r\n".encode()]
        headers.setdefault("Content-Length", str(len(body)))
        for k, v in headers.items():
            lines.append(f"{k}: {v}\r\n".encode())
        lines.append(b"\r\n")
        request = b"".join(lines) + body
        client_sock.sendall(request)
        client_sock.shutdown(socket.SHUT_WR)

        # BaseHTTPRequestHandler.__init__ runs setup/handle/finish
        # synchronously -- this call performs the entire request/response
        # cycle before returning.
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


@pytest.fixture(autouse=True)
def _patch_log_path(tmp_path, monkeypatch):
    """LOG_PATH is read at import and defaults to the repo-relative
    data/receiver.log -- patch the module attribute so tests never write
    into the repo."""
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
    """AUTH_TOKEN is read at import -- patch the module attribute, not the
    environment, so tests actually change enforcement."""
    monkeypatch.setattr(receiver, "AUTH_TOKEN", "")


@pytest.fixture
def with_auth(monkeypatch):
    monkeypatch.setattr(receiver, "AUTH_TOKEN", "s3cr3t-fleet-token")
    return "s3cr3t-fleet-token"


def _record(**overrides) -> dict:
    base = dict(
        session_id="sess-desktop-a",
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


def _token_rows(store: OtelStore):
    return store.db.execute(
        "SELECT dp_key, session_id, user_email, user_id, org_id, "
        "query_source, token_type, tokens FROM token_usage "
        "WHERE usage_source='transcript'"
    ).fetchall()


def _cost_rows(store: OtelStore):
    return store.db.execute(
        "SELECT session_id, user_email, user_id, org_id, query_source, cost_usd "
        "FROM cost_usage WHERE usage_source='transcript'"
    ).fetchall()


# ---------------------------------------------------------------------------
# AC 1: authenticated valid batch -> 200, rows exist.
# ---------------------------------------------------------------------------

def test_valid_batch_inserts_rows_and_returns_200(store, no_auth):
    status, body = _post("/v1/transcript-usage",
                          json.dumps([_record()]).encode())
    assert status == 200
    assert body["inserted"] == 5  # 4 token rows + 1 cost row
    assert body["rejected"] == 0
    assert body["duplicate"] == 0

    tok_rows = _token_rows(store)
    assert len(tok_rows) == 4
    cost_rows = _cost_rows(store)
    assert len(cost_rows) == 1


# ---------------------------------------------------------------------------
# AC 2: unauthenticated POST with RECEIVER_AUTH_TOKEN set -> 401, writes
# nothing.
# ---------------------------------------------------------------------------

def test_unauthenticated_post_returns_401_and_writes_nothing(store, with_auth):
    status, _ = _post("/v1/transcript-usage", json.dumps([_record()]).encode())
    assert status == 401
    assert _token_rows(store) == []
    assert _cost_rows(store) == []


def test_authenticated_post_with_correct_token_succeeds(store, with_auth):
    status, body = _post(
        "/v1/transcript-usage", json.dumps([_record()]).encode(),
        headers={"X-Billing-Token": with_auth},
    )
    assert status == 200
    assert body["inserted"] == 5


# ---------------------------------------------------------------------------
# AC 3: unusable envelope -> 400, writes nothing.
# ---------------------------------------------------------------------------

def test_non_list_envelope_returns_400_and_writes_nothing(store, no_auth):
    status, _ = _post("/v1/transcript-usage",
                       json.dumps({"not": "a list"}).encode())
    assert status == 400
    assert _token_rows(store) == []
    assert _cost_rows(store) == []


def test_oversized_batch_returns_400_and_writes_nothing(store, no_auth):
    from billing.otel.transcript import MAX_BATCH_SIZE

    batch = [_record(request_id=f"req-{i}") for i in range(MAX_BATCH_SIZE + 1)]
    status, _ = _post("/v1/transcript-usage", json.dumps(batch).encode())
    assert status == 400
    assert _token_rows(store) == []
    assert _cost_rows(store) == []


def test_malformed_json_returns_400(store, no_auth):
    status, _ = _post("/v1/transcript-usage", b"not json {{{")
    assert status == 400
    assert _token_rows(store) == []


# ---------------------------------------------------------------------------
# AC 3b: mixed valid/invalid batch -> 200, valid inserted, invalid rejected.
# Regression test for the batch-poisoning path.
# ---------------------------------------------------------------------------

def test_mixed_batch_inserts_valid_and_rejects_invalid(store, no_auth):
    valid = _record(request_id="req-valid")
    invalid = _record(request_id="req-invalid", ts="garbage-not-a-timestamp")
    status, body = _post("/v1/transcript-usage",
                          json.dumps([valid, invalid]).encode())
    assert status == 200
    assert body["rejected"] == 1
    assert body["inserted"] == 5  # only the valid record's rows

    reasons = {r["request_id"]: r["reason"] for r in body["rejections"]}
    assert reasons["req-invalid"] == "invalid_ts"

    tok_rows = _token_rows(store)
    assert len(tok_rows) == 4  # only the valid record's four token rows
    assert all(row[1] == "sess-desktop-a" for row in tok_rows)


def test_store_valueerror_is_caught_per_record_not_whole_batch(store, no_auth, monkeypatch):
    """A ValueError escaping map_record OR the store insert for one record
    must be caught and counted as a rejection -- never allowed to abort the
    whole batch. This directly exercises the requirement that both
    map_record AND the store insert are wrapped, per record, by forcing
    map_record itself to raise for one record while leaving another valid.
    """
    import billing.otel.receiver as receiver_mod

    real_map_record = receiver_mod.map_record

    def _boom_for_bad(record, rating=None):
        if record.get("request_id") == "req-boom":
            raise ValueError("simulated map_record failure")
        return real_map_record(record, rating)

    monkeypatch.setattr(receiver_mod, "map_record", _boom_for_bad)

    good = _record(request_id="req-good")
    boom = _record(request_id="req-boom")
    status, body = _post("/v1/transcript-usage",
                          json.dumps([good, boom]).encode())
    assert status == 200
    assert body["rejected"] == 1
    assert body["inserted"] == 5  # only req-good's rows

    tok_rows = _token_rows(store)
    assert len(tok_rows) == 4  # only req-good's four token rows


# ---------------------------------------------------------------------------
# AC 4: re-POSTing the same batch -> 200, zero new inserts, all duplicates.
# ---------------------------------------------------------------------------

def test_replay_of_identical_batch_inserts_nothing_new(store, no_auth):
    batch = [_record()]
    status1, body1 = _post("/v1/transcript-usage", json.dumps(batch).encode())
    assert status1 == 200
    assert body1["inserted"] == 5

    row_count_before = len(_token_rows(store)) + len(_cost_rows(store))

    status2, body2 = _post("/v1/transcript-usage", json.dumps(batch).encode())
    assert status2 == 200
    assert body2["inserted"] == 0
    assert body2["duplicate"] == 5

    row_count_after = len(_token_rows(store)) + len(_cost_rows(store))
    assert row_count_after == row_count_before


# ---------------------------------------------------------------------------
# AC 5: cli/claude-vscode are now accepted backfill entrypoints (task 03,
# otel-export-loss-reduction) -- inverted from the original "rejected"
# expectation. The old expectation is kept alive against a genuinely
# out-of-set entrypoint (claude-web) just below.
# ---------------------------------------------------------------------------

def test_backfill_entrypoint_is_accepted_when_old_enough_and_no_otlp_row(store, no_auth):
    rec = _record(entrypoint="cli", ts="2026-01-01T00:00:00Z")  # far older than 900s
    status, body = _post("/v1/transcript-usage", json.dumps([rec]).encode())
    assert status == 200
    assert body["rejected"] == 0
    assert body["inserted"] == 5
    tok_rows = _token_rows(store)
    assert len(tok_rows) == 4


def test_out_of_set_entrypoint_still_rejected_with_invalid_entrypoint(store, no_auth):
    status, body = _post("/v1/transcript-usage",
                          json.dumps([_record(entrypoint="claude-web")]).encode())
    assert status == 200
    assert body["rejected"] == 1
    assert body["inserted"] == 0
    assert body["rejections"][0]["reason"] == "invalid_entrypoint"
    assert _token_rows(store) == []
    assert _cost_rows(store) == []


# ---------------------------------------------------------------------------
# AC 6: identity round-trips end to end.
# ---------------------------------------------------------------------------

def test_identity_round_trips_to_stored_rows(store, no_auth):
    status, _ = _post(
        "/v1/transcript-usage",
        json.dumps([_record(user_email="carol@cyclotron.com", user_id="u-carol",
                             org_id="org-cyclotron")]).encode(),
    )
    assert status == 200

    tok_row = store.db.execute(
        "SELECT user_email, user_id, org_id FROM token_usage "
        "WHERE usage_source='transcript' LIMIT 1"
    ).fetchone()
    assert tuple(tok_row) == ("carol@cyclotron.com", "u-carol", "org-cyclotron")

    cost_row = store.db.execute(
        "SELECT user_email, user_id, org_id FROM cost_usage "
        "WHERE usage_source='transcript' LIMIT 1"
    ).fetchone()
    assert tuple(cost_row) == ("carol@cyclotron.com", "u-carol", "org-cyclotron")


# ---------------------------------------------------------------------------
# AC 6b: main + subagent rows for the same session store distinct query_source
# and distinct dp_keys.
# ---------------------------------------------------------------------------

def test_main_and_subagent_rows_preserve_distinct_query_source_and_keys(store, no_auth):
    from billing.otel.otel_store import transcript_key

    main_rec = _record(session_id="sess-shared", request_id="req-main",
                        query_source="main")
    sub_rec = _record(session_id="sess-shared", request_id="req-sub",
                       query_source="subagent")
    status, body = _post("/v1/transcript-usage",
                          json.dumps([main_rec, sub_rec]).encode())
    assert status == 200
    assert body["rejected"] == 0
    assert body["inserted"] == 10  # 2 records x (4 token rows + 1 cost row)

    rows = store.db.execute(
        "SELECT dp_key, query_source, token_type FROM token_usage "
        "WHERE usage_source='transcript' AND session_id='sess-shared'"
    ).fetchall()
    assert len(rows) == 8  # 4 token rows each, for two distinct requests

    by_query_source = {}
    for dp_key, query_source, token_type in rows:
        by_query_source.setdefault(query_source, set()).add(dp_key)
    assert set(by_query_source.keys()) == {"main", "subagent"}
    assert len(by_query_source["main"]) == 4
    assert len(by_query_source["subagent"]) == 4
    # Both preserved and distinct: no dp_key collision between the two
    # requests despite sharing session_id.
    assert by_query_source["main"].isdisjoint(by_query_source["subagent"])

    # And they match the frozen transcript_key composition exactly (proves
    # query_source, though excluded from the key, was still stored/preserved
    # correctly per row rather than collapsed/overwritten).
    expected_main = {transcript_key("sess-shared", "req-main", tt)
                      for tt in ("input", "output", "cacheRead", "cacheCreation")}
    expected_sub = {transcript_key("sess-shared", "req-sub", tt)
                     for tt in ("input", "output", "cacheRead", "cacheCreation")}
    assert by_query_source["main"] == expected_main
    assert by_query_source["subagent"] == expected_sub


# ---------------------------------------------------------------------------
# AC 7: the malformed-POST log line for this endpoint contains no request
# bytes.
# ---------------------------------------------------------------------------

def test_malformed_post_log_line_contains_no_request_bytes(store, no_auth, tmp_path):
    secret_marker = "SECRET_CONVERSATION_CONTENT_MARKER_XYZ"
    bad_body = f'{{"prompt": "{secret_marker}"'.encode()  # malformed JSON

    status, _ = _post("/v1/transcript-usage", bad_body)
    assert status == 400

    log_text = (tmp_path / "receiver.log").read_text(encoding="utf-8")
    assert secret_marker not in log_text


# ---------------------------------------------------------------------------
# AC 8: startup banner names the new endpoint.
# ---------------------------------------------------------------------------

def test_startup_banner_mentions_transcript_usage_endpoint(tmp_path, monkeypatch, capsys):
    """Asserts on the ACTUAL printed banner, not on serve()'s source text --
    a source-text assertion would survive a mutation that drops the endpoint
    from the real f-string print but leaves its name sitting in a nearby
    comment. HTTPServer is replaced with a fake that never binds a socket
    (real requirement: never bind a real port in a test), and serve_forever
    is made to return immediately instead of blocking."""

    class _FakeServer:
        def __init__(self, addr, handler_cls):
            self.addr = addr
            self.handler_cls = handler_cls

        def serve_forever(self):
            return  # simulate an immediate, clean shutdown

    monkeypatch.setattr(receiver, "HTTPServer", _FakeServer)
    monkeypatch.setattr(receiver, "AUTH_TOKEN", "")

    receiver.serve("127.0.0.1", 0, db=str(tmp_path / "banner_otel.db"))

    printed = capsys.readouterr().out
    assert "/v1/transcript-usage" in printed
    assert "/v1/metrics" in printed
    assert "/v1/session-repo" in printed


# ---------------------------------------------------------------------------
# Fix-cycle-1 regression coverage.
# ---------------------------------------------------------------------------

# --- store-path containment, REAL client-shaped data, no monkeypatching ----

def test_store_path_containment_real_whitespace_request_id_no_mocking(store, no_auth):
    """The store's guard (task 01) rejects a whitespace-only request_id --
    truthy, so it PASSES transcript.py's validation and only trips
    otel_store.py's own check. No monkeypatching: this drives the real
    validate_batch -> map_record -> insert_datapoint path end to end, so it
    also kills a mutation that moves the store inserts outside the
    containing try (they'd then raise ValueError uncaught -> 400 for the
    whole batch instead of a clean per-record rejection)."""
    good_a = _record(request_id="req-good-a")
    good_b = _record(request_id="req-good-b", session_id="sess-desktop-b")
    whitespace_id = _record(request_id="   ")  # truthy, passes validate_batch

    status, body = _post(
        "/v1/transcript-usage",
        json.dumps([good_a, whitespace_id, good_b]).encode(),
    )
    assert status == 200
    assert body["rejected"] == 1
    assert body["inserted"] == 10  # two good records x 5 rows each

    rejection = body["rejections"][0]
    assert rejection["index"] == 1  # the whitespace record's real batch position
    assert rejection["request_id"] == "   "
    assert rejection["reason"] == "store_error:ValueError"

    tok_rows = _token_rows(store)
    assert len(tok_rows) == 8  # 4 rows x 2 good records, none from the bad one


def test_store_path_containment_literal_none_string_request_id(store, no_auth):
    """Companion case: request_id="None" (the literal string) is also
    truthy and passes transcript.py's validation, and also trips task 01's
    guard (it's compared to the string "None" specifically, to catch a
    client that stringified a missing id)."""
    good = _record(request_id="req-good-c")
    literal_none = _record(request_id="None")

    status, body = _post("/v1/transcript-usage",
                          json.dumps([good, literal_none]).encode())
    assert status == 200
    assert body["rejected"] == 1
    assert body["inserted"] == 5

    rejection = body["rejections"][0]
    assert rejection["index"] == 1
    assert rejection["request_id"] == "None"
    assert rejection["reason"] == "store_error:ValueError"


def test_store_path_rejection_index_survives_a_preceding_validation_rejection(store, no_auth):
    """Discriminates the real index-derivation
    (`accepted_indices = [i for i in range(len(payload)) if i not in
    rejected_indices]`) from the naive `list(range(len(accepted)))`, which
    every OTHER test in this file cannot: those all put the bad record at
    batch position 1 with no PRECEDING validate_batch rejection, so both
    formulas happen to agree there.

    Here a validation-level rejection (bad `ts`) sits BEFORE the store-path
    rejection (whitespace request_id) in the batch:

        index 0: good                          -> accepted
        index 1: bad ts (validate_batch reject) -> rejected, index 1
        index 2: whitespace request_id          -> accepted by validate_batch,
                                                     rejected by the store

    `accepted` (in order) is [good, whitespace] -- position 1 within
    `accepted`. The naive `list(range(len(accepted)))` would report the
    store rejection at index 1, colliding with (and indistinguishable from)
    the validation rejection already at index 1. The real batch position is
    2; only the derivation that accounts for validate_batch's own rejected
    indices gets this right.
    """
    good = _record(request_id="req-good-interleave")
    bad_ts = _record(request_id="req-bad-ts", ts="garbage-not-a-timestamp")
    whitespace_id = _record(request_id="   ")

    status, body = _post(
        "/v1/transcript-usage",
        json.dumps([good, bad_ts, whitespace_id]).encode(),
    )
    assert status == 200
    assert body["rejected"] == 2
    assert body["inserted"] == 5  # only the one good record's rows

    by_index = {r["index"]: r for r in body["rejections"]}
    assert set(by_index) == {1, 2}
    assert by_index[1]["reason"] == "invalid_ts"
    assert by_index[1]["request_id"] == "req-bad-ts"
    assert by_index[2]["reason"] == "store_error:ValueError"
    assert by_index[2]["request_id"] == "   "


# --- wrong-typed field: now CAUGHT (not escaping) after the broadened catch

def test_wrong_typed_model_field_is_rejected_not_escaped(store, no_auth):
    """model=123 (an int, not a str) passes validate_batch (which only
    checks model for TRUTHINESS) and raises TypeError inside map_record's
    RatingService.raw_cost call (`key in (model or "")` on a truthy int).
    Before the broadened catch this escaped both the per-record loop and
    do_POST's `except (ValueError, KeyError)`, dropping the connection with
    no HTTP response. It must now come back as an ordinary 200 with a
    per-record rejection."""
    good = _record(request_id="req-good-typed")
    bad_model = _record(request_id="req-bad-model", model=123)

    status, body = _post("/v1/transcript-usage",
                          json.dumps([good, bad_model]).encode())
    assert status == 200
    assert body["rejected"] == 1
    assert body["inserted"] == 5

    rejection = body["rejections"][0]
    assert rejection["index"] == 1
    assert rejection["request_id"] == "req-bad-model"
    assert rejection["reason"] == "store_error:TypeError"

    tok_rows = _token_rows(store)
    assert len(tok_rows) == 4  # only req-good-typed's rows


def test_wrong_typed_session_id_field_is_rejected_not_escaped(store, no_auth):
    """session_id=["x"] (a list) is now caught upstream by validate_batch's
    task-03 type check on session_id and rejected `invalid_session_id` --
    inverted from the original expectation that it escaped validate_batch's
    truthiness-only check and only got caught downstream as
    sqlite3.ProgrammingError. This is the most instructive artifact in the
    goal: the old downstream net caught only types SQLite REFUSES (a list
    raises ProgrammingError); types SQLite silently CONVERTS (true, false,
    1e20) sailed through and double-billed. `_RECORD_DATA_ERRORS` still needs
    sqlite3.ProgrammingError for the user_email={"a":1} case below, which
    keeps exercising that downstream net for a field session_id's fix does
    not cover.
    """
    good = _record(request_id="req-good-sid")
    bad_sid = _record(request_id="req-bad-sid", session_id=["x"])

    status, body = _post("/v1/transcript-usage",
                          json.dumps([good, bad_sid]).encode())
    assert status == 200
    assert body["rejected"] == 1
    assert body["inserted"] == 5
    assert body["rejections"][0]["reason"] == "invalid_session_id"


def test_wrong_typed_user_email_field_still_escapes_to_programming_error(store, no_auth):
    """Kept alive: `_RECORD_DATA_ERRORS` still needs sqlite3.ProgrammingError
    coverage for a field task 03's type-validation does NOT cover --
    user_email={"a": 1} is truthy, passes validate_batch (which only checks
    user_email for truthiness), and raises sqlite3.ProgrammingError when
    bound as a query parameter, exactly as session_id used to before its
    fix."""
    good = _record(request_id="req-good-email")
    bad_email = _record(request_id="req-bad-email", user_email={"a": 1})

    status, body = _post("/v1/transcript-usage",
                          json.dumps([good, bad_email]).encode())
    assert status == 200
    assert body["rejected"] == 1
    assert body["inserted"] == 5
    assert body["rejections"][0]["reason"] == "store_error:ProgrammingError"


# --- commit() called exactly once per request -------------------------------

def test_commit_called_exactly_once_per_request(store, no_auth, monkeypatch):
    commit_calls = {"n": 0}
    real_commit = store.commit

    def _counting_commit():
        commit_calls["n"] += 1
        return real_commit()

    monkeypatch.setattr(store, "commit", _counting_commit)

    batch = [_record(request_id=f"req-{i}") for i in range(5)]
    status, body = _post("/v1/transcript-usage", json.dumps(batch).encode())
    assert status == 200
    assert commit_calls["n"] == 1


# --- the escape-with-orphaned-uncommitted-rows leak is closed ---------------

def test_operational_error_rolls_back_instead_of_orphaning_uncommitted_rows(
    store, store_path, no_auth, monkeypatch
):
    """Simulates a genuinely operational store failure (sqlite3.
    OperationalError) partway through a batch, after one record's rows have
    already been staged (uncommitted) on the connection. That error is
    DELIBERATELY not contained per-record (see _RECORD_DATA_ERRORS) -- it
    must propagate -- but the connection must be rolled back FIRST, so nothing
    from the failed request survives to be silently committed as a side
    effect of a later, unrelated request.
    """
    real_insert_cost = store.insert_cost_datapoint
    calls = {"n": 0}

    def _flaky_insert_cost(**kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise sqlite3.OperationalError("simulated disk I/O error")
        return real_insert_cost(**kwargs)

    monkeypatch.setattr(store, "insert_cost_datapoint", _flaky_insert_cost)

    good_a = _record(request_id="req-good-a")
    bad_b = _record(request_id="req-bad-b", session_id="sess-desktop-b")

    with pytest.raises(sqlite3.OperationalError):
        _post("/v1/transcript-usage", json.dumps([good_a, bad_b]).encode())

    # Nothing from the failed request should be visible even to THIS SAME
    # connection (rollback discards the whole uncommitted batch, not just
    # the record that raised) -- verified via a genuinely separate outside
    # connection to the same database file, so an in-process cache can't
    # paper over an uncommitted write.
    outside = sqlite3.connect(store_path)
    try:
        tok_count, cost_count = outside.execute(
            "SELECT (SELECT COUNT(*) FROM token_usage WHERE usage_source='transcript'), "
            "(SELECT COUNT(*) FROM cost_usage WHERE usage_source='transcript')"
        ).fetchone()
        assert (tok_count, cost_count) == (0, 0)
    finally:
        outside.close()

    # A second, unrelated, entirely valid request must succeed normally and
    # show ONLY its own rows -- proving the previous escape left no orphaned
    # rows for this commit() to sweep up as a side effect.
    unrelated = _record(request_id="req-unrelated", session_id="sess-desktop-c")
    status, body = _post("/v1/transcript-usage", json.dumps([unrelated]).encode())
    assert status == 200
    assert body["inserted"] == 5

    outside2 = sqlite3.connect(store_path)
    try:
        rows = outside2.execute(
            "SELECT DISTINCT session_id FROM token_usage WHERE usage_source='transcript'"
        ).fetchall()
        assert {r[0] for r in rows} == {"sess-desktop-c"}
    finally:
        outside2.close()


def test_commit_failure_rolls_back_instead_of_orphaning_uncommitted_rows(
    store, store_path, no_auth, monkeypatch
):
    """Companion to the loop-failure rollback test above, moved to the
    commit path: `store.commit()` itself can raise sqlite3.OperationalError
    ("database is locked", "disk I/O error" -- ordinary conditions on a
    single-host SQLite deployment, not exotic ones). That call sits INSIDE
    the same guarded region as the record loop, so a commit-time failure
    must roll back before re-raising exactly as a mid-loop failure already
    does -- otherwise this batch's rows sit uncommitted on the connection
    and get silently committed as a side effect of a LATER, unrelated
    request's own commit(), with no response ever having been sent for
    THIS one.
    """
    real_commit = store.commit
    calls = {"n": 0}

    def _flaky_commit():
        calls["n"] += 1
        if calls["n"] == 1:
            raise sqlite3.OperationalError("database is locked")
        return real_commit()

    monkeypatch.setattr(store, "commit", _flaky_commit)

    good = _record(request_id="req-good-commit-fail")

    with pytest.raises(sqlite3.OperationalError):
        _post("/v1/transcript-usage", json.dumps([good]).encode())

    # The record's rows were staged before commit() was even attempted --
    # verify a genuinely separate connection to the same file sees NONE of
    # them: the failed commit must have been rolled back, not left dangling.
    outside = sqlite3.connect(store_path)
    try:
        tok_count, cost_count = outside.execute(
            "SELECT (SELECT COUNT(*) FROM token_usage WHERE usage_source='transcript'), "
            "(SELECT COUNT(*) FROM cost_usage WHERE usage_source='transcript')"
        ).fetchone()
        assert (tok_count, cost_count) == (0, 0)
    finally:
        outside.close()

    # A later, unrelated, entirely valid request must succeed and commit
    # ONLY its own record -- proving the failed commit left no orphaned
    # rows behind for this one to sweep up as a side effect.
    unrelated = _record(request_id="req-unrelated-commit-fail",
                         session_id="sess-desktop-commit-fail")
    status, body = _post("/v1/transcript-usage", json.dumps([unrelated]).encode())
    assert status == 200
    assert body["inserted"] == 5

    outside2 = sqlite3.connect(store_path)
    try:
        rows = outside2.execute(
            "SELECT DISTINCT session_id FROM token_usage WHERE usage_source='transcript'"
        ).fetchall()
        assert {r[0] for r in rows} == {"sess-desktop-commit-fail"}
    finally:
        outside2.close()
