"""Tests for task 03: billing/otel/cowork_receiver.py -- the standalone
Cowork HTTP receiver process.

Drives the handler IN-PROCESS against a connected socket pair (never a real
bound port) -- the same established convention `tests/test_receiver.py` uses
("real requirement: never bind a real port in a test"), reproduced here as a
separate, analogous harness rather than shared code.

Reuses tests/conftest.py's build_cowork_metrics_payload / cowork_db_path
fixtures rather than duplicating payload construction.
"""

from __future__ import annotations

import ast
import gzip
import http.client
import importlib
import json
import os
import socket
import sqlite3
import sys
import zlib
from pathlib import Path

import pytest

from billing.otel import cowork_receiver
from billing.otel.cowork_store import CoworkStore
from tests.conftest import (
    COWORK_LOOKUP_SESSION_ID,
    build_cowork_metrics_payload,
)


class _FakeServer:
    """A stand-in for http.server.HTTPServer that never binds a real socket
    or port -- reused by every test that needs to exercise serve() without
    the "real requirement: never bind a real port in a test" convention
    ever being at risk from a regression."""

    def __init__(self, addr, handler_cls):
        self.addr = addr
        self.handler_cls = handler_cls

    def serve_forever(self):
        return  # simulate an immediate, clean shutdown


# ---------------------------------------------------------------------------
# In-process HTTP harness -- a connected socketpair, not a bound port.
# ---------------------------------------------------------------------------

def _request(method: str, path: str, body: bytes = b"",
             headers: dict | None = None) -> tuple[int, dict]:
    """Send `method path` to cowork_receiver.Handler, in-process, over a
    connected socket.socketpair() -- never a real bound port.

    Returns (status_code, parsed_json_body_or_empty_dict). Uses HTTP/1.0 so
    the handler closes the connection after one request.
    """
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

        # BaseHTTPRequestHandler.__init__ runs setup/handle/finish
        # synchronously -- this call performs the entire request/response
        # cycle before returning.
        cowork_receiver.Handler(server_sock, ("127.0.0.1", 0), None)
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


def _post(path: str, body: bytes, headers: dict | None = None) -> tuple[int, dict]:
    return _request("POST", path, body, headers)


def _get(path: str, headers: dict | None = None) -> tuple[int, dict]:
    return _request("GET", path, b"", headers)


@pytest.fixture(autouse=True)
def _patch_log_path(tmp_path, monkeypatch):
    """LOG_PATH is read at import and defaults to the repo-relative
    data/cowork_receiver.log -- patch the module attribute so tests never
    write into the repo."""
    monkeypatch.setattr(cowork_receiver, "LOG_PATH", str(tmp_path / "cowork_receiver.log"))


@pytest.fixture
def store(cowork_db_path) -> CoworkStore:
    s = CoworkStore(cowork_db_path)
    cowork_receiver.Handler.store = s
    yield s
    s.close()


@pytest.fixture
def no_auth(monkeypatch):
    """AUTH_TOKEN is read at import -- patch the module attribute, not the
    environment, so tests actually change enforcement."""
    monkeypatch.setattr(cowork_receiver, "AUTH_TOKEN", "")


@pytest.fixture
def with_auth(monkeypatch):
    monkeypatch.setattr(cowork_receiver, "AUTH_TOKEN", "s3cr3t-cowork-token")
    return "s3cr3t-cowork-token"


def _token_rows(store: CoworkStore):
    return store.db.execute(
        "SELECT dp_key, session_id, user_email, model, token_type, tokens "
        "FROM cowork_token_usage"
    ).fetchall()


class _RollbackSpy:
    """A thin proxy standing in for `store.db` (a `sqlite3.Connection`) that
    counts `rollback()` calls while delegating everything else, including
    the real `rollback()` itself, unchanged. `sqlite3.Connection` instances
    refuse arbitrary attribute assignment (`monkeypatch.setattr(store.db,
    "rollback", ...)` raises `AttributeError: ... attribute 'rollback' is
    read-only`), so the whole `store.db` ATTRIBUTE must be swapped for a
    proxy instead of patching one method on the connection object itself."""

    def __init__(self, real_db):
        self._real = real_db
        self.rollback_calls = 0

    def rollback(self):
        self.rollback_calls += 1
        return self._real.rollback()

    def __getattr__(self, name):
        return getattr(self._real, name)


def _cost_rows(store: CoworkStore):
    return store.db.execute(
        "SELECT dp_key, session_id, user_email, model, cost_usd "
        "FROM cowork_cost_usage"
    ).fetchall()


# ---------------------------------------------------------------------------
# AC 1: authenticated valid payload -> 200, rows exist in CoworkStore.
# ---------------------------------------------------------------------------

def test_valid_payload_inserts_rows_and_returns_200(store, no_auth):
    payload = build_cowork_metrics_payload()
    status, body = _post("/v1/metrics", json.dumps(payload).encode())
    assert status == 200
    assert body["inserted"] == 3  # 2 token rows (input+output) + 1 cost row
    assert body["rejected"] == 0

    assert len(_token_rows(store)) == 2
    assert len(_cost_rows(store)) == 1


def test_valid_payload_with_correct_token_succeeds(store, with_auth):
    payload = build_cowork_metrics_payload()
    status, body = _post("/v1/metrics", json.dumps(payload).encode(),
                          headers={"X-Billing-Token": with_auth})
    assert status == 200
    assert body["inserted"] == 3


# ---------------------------------------------------------------------------
# AC 2: missing/wrong token -> 401 when COWORK_RECEIVER_AUTH_TOKEN is set.
# ---------------------------------------------------------------------------

def test_missing_token_returns_401_and_writes_nothing(store, with_auth):
    payload = build_cowork_metrics_payload()
    status, _ = _post("/v1/metrics", json.dumps(payload).encode())
    assert status == 401
    assert _token_rows(store) == []
    assert _cost_rows(store) == []


def test_wrong_token_returns_401(store, with_auth):
    payload = build_cowork_metrics_payload()
    status, _ = _post("/v1/metrics", json.dumps(payload).encode(),
                       headers={"X-Billing-Token": "not-the-right-token"})
    assert status == 401
    assert _token_rows(store) == []


def test_bearer_auth_header_also_accepted(store, with_auth):
    payload = build_cowork_metrics_payload()
    status, body = _post("/v1/metrics", json.dumps(payload).encode(),
                          headers={"Authorization": f"Bearer {with_auth}"})
    assert status == 200
    assert body["inserted"] == 3


# ---------------------------------------------------------------------------
# AC 3: --require-auth with no token set refuses to start.
# ---------------------------------------------------------------------------

def test_require_auth_with_no_token_refuses_to_start(no_auth, tmp_path, monkeypatch):
    """HTTPServer is patched to the never-binds-a-real-socket fake BEFORE
    calling serve() -- fix-cycle 1: if a regression ever moved the
    --require-auth guard to AFTER the HTTPServer(...) construction, this
    test must fail loudly (SystemExit not raised) rather than silently
    binding (and hanging on) a real port."""
    monkeypatch.setattr(cowork_receiver, "HTTPServer", _FakeServer)
    with pytest.raises(SystemExit):
        cowork_receiver.serve("127.0.0.1", 0, db=str(tmp_path / "x.db"),
                               require_auth=True)


def test_require_auth_with_token_set_does_not_raise_on_the_guard(with_auth, tmp_path, monkeypatch):
    """Only exercises the --require-auth guard itself (never binds a real
    socket): HTTPServer is replaced with a fake, and serve_forever returns
    immediately instead of blocking -- same technique test_receiver.py's own
    startup-banner test uses."""
    monkeypatch.setattr(cowork_receiver, "HTTPServer", _FakeServer)
    cowork_receiver.serve("127.0.0.1", 0, db=str(tmp_path / "x.db"), require_auth=True)


# ---------------------------------------------------------------------------
# AC 4: a claude-code (non-cowork) payload -> 0 rows stored, still 200 with
# rejection reflected in the response body -- never a crash.
# ---------------------------------------------------------------------------

def test_non_cowork_service_name_rejected_but_returns_200(store, no_auth):
    payload = build_cowork_metrics_payload(service_name="claude-code")
    status, body = _post("/v1/metrics", json.dumps(payload).encode())
    assert status == 200
    assert body["inserted"] == 0
    assert body["rejected"] > 0
    assert _token_rows(store) == []
    assert _cost_rows(store) == []


# ---------------------------------------------------------------------------
# AC 5: GET /healthz with no token configured never includes last_ingest_at.
# ---------------------------------------------------------------------------

def test_healthz_no_token_configured_never_includes_last_ingest_at(store, no_auth):
    status, body = _get("/healthz")
    assert status == 200
    assert body["status"] == "ok"
    assert "now" in body
    assert "last_ingest_at" not in body


def test_healthz_no_token_configured_even_with_a_presented_token(store, no_auth):
    """_authorized() alone returns True when AUTH_TOKEN is unset -- the gate
    must require AUTH_TOKEN non-empty too, not just _authorized()."""
    status, body = _get("/healthz", headers={"X-Billing-Token": "anything"})
    assert status == 200
    assert "last_ingest_at" not in body


def test_healthz_with_token_configured_and_correct_token_includes_last_ingest_at(store, with_auth):
    status, body = _get("/healthz", headers={"X-Billing-Token": with_auth})
    assert status == 200
    assert "last_ingest_at" in body


def test_healthz_with_token_configured_but_no_presented_token_excludes_detail(store, with_auth):
    status, body = _get("/healthz")
    assert status == 200
    assert "last_ingest_at" not in body


# ---------------------------------------------------------------------------
# AC 6: distinct defaults/env-var names, RECEIVER_AUTH_TOKEN never read, and
# COWORK_RECEIVER_AUTH_TOKEN loaded from .env when present.
# ---------------------------------------------------------------------------

def test_source_never_references_RECEIVER_AUTH_TOKEN_as_a_distinct_token():
    """Grep/AST-style check: the exact token RECEIVER_AUTH_TOKEN (not a
    substring of COWORK_RECEIVER_AUTH_TOKEN) never appears in the source."""
    src_path = Path(cowork_receiver.__file__)
    source = src_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    names_and_strings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names_and_strings.add(node.id)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            names_and_strings.add(node.value)
    assert "RECEIVER_AUTH_TOKEN" not in names_and_strings

    # Also a raw substring scan restricted to actual CODE lines (skipping the
    # module docstring / comments, which may need to name the sibling env var
    # in prose to explain the isolation rule) -- tokenized on non-identifier
    # boundaries so it doesn't false-positive on COWORK_RECEIVER_AUTH_TOKEN.
    import re
    module_docstring = ast.get_docstring(tree) or ""
    code_only = source.replace(module_docstring, "")
    for line in code_only.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        code_part = line.split("#", 1)[0]
        for match in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*", code_part):
            assert match.group(0) != "RECEIVER_AUTH_TOKEN", (
                f"literal RECEIVER_AUTH_TOKEN token found in code: {line!r}")


def test_source_never_imports_billing_otel_receiver():
    src_path = Path(cowork_receiver.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "receiver" not in alias.name.split(".")[-1] or "otel" not in alias.name
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not (module.endswith("otel") and
                        any(a.name == "receiver" for a in node.names))
            assert "billing.otel.receiver" not in module


def test_main_argparse_help_documents_the_distinct_auth_env_var():
    """A meaningful replacement for the earlier near-vacuous version of this
    test (it built a throwaway, disconnected ArgumentParser and asserted
    trivia about it): parses main()'s OWN argparse `--help` output, so a
    mutation that changed --require-auth's help text to name the WRONG env
    var (e.g. RECEIVER_AUTH_TOKEN) actually fails this test. Port/host/db
    defaults are exercised end-to-end (not just in --help text, which
    argparse doesn't print by default) by
    test_main_uses_port_4319_and_cowork_db_default below."""
    import io
    import contextlib

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(sys, "argv", ["cowork_receiver", "--help"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
            cowork_receiver.main()
        help_text = buf.getvalue()
    finally:
        monkeypatch.undo()

    assert "COWORK_RECEIVER_AUTH_TOKEN" in help_text
    # Tokenized check (not a bare substring test) that RECEIVER_AUTH_TOKEN
    # never appears as its OWN word -- only as part of COWORK_RECEIVER_AUTH_TOKEN.
    import re
    for match in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*", help_text):
        assert match.group(0) != "RECEIVER_AUTH_TOKEN"


def test_main_uses_port_4319_and_cowork_db_default(monkeypatch):
    captured = {}

    def _fake_serve(host, port, db=None, require_auth=False):
        captured.update(host=host, port=port, db=db, require_auth=require_auth)

    monkeypatch.delenv("COWORK_DB", raising=False)
    monkeypatch.setattr(cowork_receiver, "serve", _fake_serve)
    monkeypatch.setattr(sys, "argv", ["cowork_receiver"])
    cowork_receiver.main()

    assert captured["port"] == 4319
    assert captured["port"] != 4318
    assert captured["host"] == "127.0.0.1"
    from billing.otel.cowork_store import DEFAULT_COWORK_DB
    assert captured["db"] == DEFAULT_COWORK_DB


def test_never_defaults_to_otel_db_path():
    from billing.otel.cowork_store import DEFAULT_COWORK_DB
    assert "otel.db" not in DEFAULT_COWORK_DB
    assert DEFAULT_COWORK_DB != "./data/otel.db"


# ---------------------------------------------------------------------------
# Fix-cycle 1, issue 6: the previous version of this test read
# `os.environ`/called `load_env()` directly without ever re-executing
# cowork_receiver's own module-level `AUTH_TOKEN = ...` line -- an evaluator
# mutant that skipped `load_env()` entirely, or one that read
# RECEIVER_AUTH_TOKEN instead of COWORK_RECEIVER_AUTH_TOKEN, both still
# passed every test in this file. It also leaked a fake RECEIVER_AUTH_TOKEN
# value into os.environ for the rest of the test session.
#
# Fix-cycle 2, issue 1: the fix-cycle-1 rewrite of this test made the leak
# WORSE. It called `monkeypatch.delenv(k, raising=False)` on the two token
# vars BEFORE `load_env()` ran (when neither was set, so monkeypatch recorded
# NOTHING to restore -- there was nothing to restore TO), then in its
# `finally` called `delenv` AGAIN after `load_env()` had set them from the
# temp .env. That second call recorded the freshly-set FAKE values as the
# "original" state to restore at teardown -- so monkeypatch's undo faithfully
# put `RECEIVER_AUTH_TOKEN=should-never-be-read-by-cowork-receiver` and
# `COWORK_RECEIVER_AUTH_TOKEN=from-dotenv-token-xyz` BACK into os.environ for
# every test that ran afterwards in the same process (evaluator-confirmed).
# The environment is now snapshotted and restored wholesale with
# `unittest.mock.patch.dict(os.environ)`, whose restore does not depend on
# the ORDER of set/unset calls relative to when values actually appeared.
# `test_dotenv_test_left_no_fake_token_in_os_environ` (immediately below,
# and therefore run immediately after under pytest's default file order)
# asserts the leak is gone.
# ---------------------------------------------------------------------------

_FAKE_COWORK_TOKEN = "from-dotenv-token-xyz"
_FAKE_LEGACY_TOKEN = "should-never-be-read-by-cowork-receiver"
_TOKEN_ENV_KEYS = ("COWORK_RECEIVER_AUTH_TOKEN", "RECEIVER_AUTH_TOKEN")


def test_cowork_receiver_auth_token_loaded_from_dotenv(tmp_path, monkeypatch):
    """A token set in .env as COWORK_RECEIVER_AUTH_TOKEN=... IS honored by
    the REAL module-import path -- and RECEIVER_AUTH_TOKEN's own real value,
    present in the very same .env file, must never leak into this module's
    AUTH_TOKEN. And the test itself must leave os.environ EXACTLY as it
    found it."""
    import billing.config as config_mod
    from unittest import mock

    env_before = dict(os.environ)
    monkeypatch.setattr(config_mod, "_LOADED", False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        f"COWORK_RECEIVER_AUTH_TOKEN={_FAKE_COWORK_TOKEN}\n"
        f"RECEIVER_AUTH_TOKEN={_FAKE_LEGACY_TOKEN}\n",
        encoding="utf-8",
    )
    clean_dir = tmp_path / "clean_dir_no_dotenv"
    clean_dir.mkdir()
    monkeypatch.chdir(tmp_path)

    # patch.dict snapshots the FULL environment on entry and restores it
    # exactly on exit -- adds are removed, removes are re-added -- no matter
    # what load_env() or this test's body does in between. Everything that
    # can mutate os.environ (both reloads) happens INSIDE it.
    with mock.patch.dict(os.environ, clear=False):
        for k in _TOKEN_ENV_KEYS:
            os.environ.pop(k, None)   # clean slate for load_env()'s setdefault
        try:
            importlib.reload(cowork_receiver)
            # Kills the "skip load_env() entirely" mutant: without a real
            # load_env() call, COWORK_RECEIVER_AUTH_TOKEN would never reach
            # os.environ and AUTH_TOKEN would resolve to "".
            assert cowork_receiver.AUTH_TOKEN == _FAKE_COWORK_TOKEN
            # Kills the "reads RECEIVER_AUTH_TOKEN instead" mutant: that
            # mutant would resolve AUTH_TOKEN to THIS value instead.
            assert cowork_receiver.AUTH_TOKEN != _FAKE_LEGACY_TOKEN
            # Sanity: load_env really did populate BOTH into os.environ (so
            # the restore below has something real to undo).
            assert os.environ.get("RECEIVER_AUTH_TOKEN") == _FAKE_LEGACY_TOKEN
        finally:
            # Reload again with NEITHER token env var present and from a
            # directory with no .env file at all, so this test can't leave a
            # fake token in cowork_receiver.AUTH_TOKEN (a module-level global
            # set by a direct `reload`, which monkeypatch cannot undo on its
            # own). Still INSIDE patch.dict, so these pops are undone too.
            for k in _TOKEN_ENV_KEYS:
                os.environ.pop(k, None)
            monkeypatch.setattr(config_mod, "_LOADED", False)
            monkeypatch.chdir(clean_dir)
            importlib.reload(cowork_receiver)
            assert cowork_receiver.AUTH_TOKEN == ""

    # The load-bearing assertion for fix-cycle 2 issue 1: os.environ is
    # byte-for-byte what it was before this test touched anything.
    assert dict(os.environ) == env_before


def test_dotenv_test_left_no_fake_token_in_os_environ():
    """Runs immediately AFTER the .env test above (pytest's default order is
    file order). The fix-cycle-1 version of that test left BOTH fake values
    in os.environ at this point -- this test failed against it. Asserting on
    the specific FAKE values (rather than on the keys being absent) keeps it
    correct on a developer machine whose real environment/.env legitimately
    sets either key."""
    assert os.environ.get("COWORK_RECEIVER_AUTH_TOKEN") != _FAKE_COWORK_TOKEN
    assert os.environ.get("RECEIVER_AUTH_TOKEN") != _FAKE_LEGACY_TOKEN
    assert _FAKE_COWORK_TOKEN not in os.environ.values()
    assert _FAKE_LEGACY_TOKEN not in os.environ.values()
    # And the module global was restored to the clean-reload value too.
    assert cowork_receiver.AUTH_TOKEN != _FAKE_COWORK_TOKEN


# ---------------------------------------------------------------------------
# Fix-cycle 1, issue 1: an env value that IS present but EMPTY must fall
# back to the real default, not resolve to "" and silently break logging.
# ---------------------------------------------------------------------------

def test_empty_cowork_receiver_log_env_value_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("COWORK_RECEIVER_LOG", "")
    resolved = os.environ.get("COWORK_RECEIVER_LOG") or "data/cowork_receiver.log"
    assert resolved == "data/cowork_receiver.log"


def test_empty_cowork_receiver_log_env_value_falls_back_via_real_reload(tmp_path, monkeypatch):
    """Exercises the REAL module-level assignment, not just the expression in
    isolation -- reintroducing `.get(key, default)` in place of `or` here
    would make this test fail (LOG_PATH would resolve to "")."""
    import billing.config as config_mod

    monkeypatch.setenv("COWORK_RECEIVER_LOG", "")
    monkeypatch.delenv("COWORK_RECEIVER_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(config_mod, "_LOADED", True)  # no .env file needed here
    clean_dir = tmp_path / "no_dotenv"
    clean_dir.mkdir()
    monkeypatch.chdir(clean_dir)

    try:
        importlib.reload(cowork_receiver)
        assert cowork_receiver.LOG_PATH == "data/cowork_receiver.log"
        assert cowork_receiver.LOG_PATH != ""
    finally:
        monkeypatch.delenv("COWORK_RECEIVER_LOG", raising=False)
        importlib.reload(cowork_receiver)


# ---------------------------------------------------------------------------
# Fix-cycle 1, issue 2: COWORK_DB from .env must actually take effect --
# previously cowork_store.DEFAULT_COWORK_DB was frozen at import time, BEFORE
# cowork_receiver's own load_env() call, so a .env-set COWORK_DB was silently
# ignored (and combined with issue 1, an empty COWORK_DB could resolve
# DEFAULT_COWORK_DB to "", making sqlite3.connect("") open a throwaway temp
# database instead of the intended file).
# ---------------------------------------------------------------------------

def test_cowork_db_env_var_is_honored_by_main(monkeypatch, tmp_path):
    custom_db = str(tmp_path / "custom_cowork.db")
    monkeypatch.setenv("COWORK_DB", custom_db)

    captured = {}

    def _fake_serve(host, port, db=None, require_auth=False):
        captured.update(db=db)

    monkeypatch.setattr(cowork_receiver, "serve", _fake_serve)
    monkeypatch.setattr(sys, "argv", ["cowork_receiver"])
    cowork_receiver.main()

    assert captured["db"] == custom_db


def test_empty_cowork_db_env_var_falls_back_to_default(monkeypatch):
    from billing.otel import cowork_store

    monkeypatch.setenv("COWORK_DB", "")

    captured = {}

    def _fake_serve(host, port, db=None, require_auth=False):
        captured.update(db=db)

    monkeypatch.setattr(cowork_receiver, "serve", _fake_serve)
    monkeypatch.setattr(sys, "argv", ["cowork_receiver"])
    cowork_receiver.main()

    assert captured["db"] == cowork_store.DEFAULT_COWORK_DB
    assert captured["db"] != ""


# ---------------------------------------------------------------------------
# AC 7: every rejection is logged to THIS receiver's own log file.
# ---------------------------------------------------------------------------

def test_rejections_logged_to_own_log_file(store, no_auth, tmp_path):
    payload = build_cowork_metrics_payload(service_name="claude-code")
    status, body = _post("/v1/metrics", json.dumps(payload).encode())
    assert status == 200
    assert body["rejected"] > 0

    log_text = (tmp_path / "cowork_receiver.log").read_text(encoding="utf-8")
    assert "REJECTED" in log_text
    assert "unrecognized_service_name" in log_text


# ---------------------------------------------------------------------------
# Fix-cycle 1, issue 3 [security]: log injection / disk-fill amplification.
# service.name (and other fields cowork_ingest.py echoes into a rejection's
# reason/detail) is attacker-controlled and reachable with NO auth (this
# receiver's documented default posture is OPEN until a token is
# configured).
# ---------------------------------------------------------------------------

def test_newline_in_service_name_does_not_forge_a_log_line(store, no_auth, tmp_path):
    injected = "cowork\nFAKE 200 POST /v1/metrics injected-by-attacker"
    payload = build_cowork_metrics_payload(service_name=injected)
    status, body = _post("/v1/metrics", json.dumps(payload).encode())
    assert status == 200
    assert body["rejected"] > 0

    log_lines = (tmp_path / "cowork_receiver.log").read_text(
        encoding="utf-8").splitlines()
    # The injected newline must never split into a second, independent log
    # line -- every line that mentions the rejection must also carry the
    # REJECTED prefix / escaped newline, never a bare forged line.
    for line in log_lines:
        assert "FAKE 200 POST" not in line or "REJECTED" in line
        assert "\\n" in line or "FAKE 200 POST" not in line


def test_very_long_service_name_is_truncated_in_the_log(store, no_auth, tmp_path):
    huge = "x" * 100_000
    payload = build_cowork_metrics_payload(service_name=huge)
    status, body = _post("/v1/metrics", json.dumps(payload).encode())
    assert status == 200
    assert body["rejected"] > 0

    log_text = (tmp_path / "cowork_receiver.log").read_text(encoding="utf-8")
    assert huge not in log_text
    # Every individual line must be small -- proves the field itself was
    # capped, not merely that some OTHER limit happened to apply.
    for line in log_text.splitlines():
        assert len(line) < 1000


def test_many_rejections_produce_a_bounded_number_of_log_lines(store, no_auth, tmp_path):
    """A payload engineered to carry many malformed datapoints (one
    unrecognized-metric rejection per datapoint) must not turn into one log
    line per rejection unconditionally -- that's the disk-fill amplification
    vector (evaluator-confirmed ~592x on an ~85KB request)."""
    payload = build_cowork_metrics_payload()
    # Add a large number of datapoints under an unrecognized metric name so
    # cowork_ingest.py rejects one per datapoint.
    many_dps = [{"asInt": "1", "timeUnixNano": str(1_767_312_000_000_000_000 + i)}
                for i in range(500)]
    payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"].append({
        "name": "unrecognized.metric.flood",
        "sum": {"dataPoints": many_dps},
    })

    status, body = _post("/v1/metrics", json.dumps(payload).encode())
    assert status == 200
    assert body["rejected"] >= 500

    log_lines = [l for l in
                 (tmp_path / "cowork_receiver.log").read_text(encoding="utf-8").splitlines()
                 if l.strip()]
    # Bounded: a small constant number of real rejection lines plus at most
    # one summary/POST line, never anywhere close to 500+.
    assert len(log_lines) < 30
    assert any("more rejections omitted" in l for l in log_lines)


# ---------------------------------------------------------------------------
# Fix-cycle 1, issue 4: rejections must be logged even when store.commit()
# (or a mid-loop insert) raises -- previously the logging call sat AFTER the
# commit-guarded try/except, so an exception escaping that block skipped
# logging entirely, silently losing exactly the rejections from the batches
# most worth investigating.
# ---------------------------------------------------------------------------

def test_rejections_are_logged_even_when_commit_raises(store, no_auth, tmp_path, monkeypatch):
    payload = build_cowork_metrics_payload(service_name="claude-code")  # all rejected

    def _flaky_commit():
        raise sqlite3.OperationalError("simulated database is locked")

    monkeypatch.setattr(store, "commit", _flaky_commit)

    with pytest.raises(sqlite3.OperationalError):
        cowork_receiver.ingest_cowork_metrics_payload(payload, store)

    log_text = (tmp_path / "cowork_receiver.log").read_text(encoding="utf-8")
    assert "REJECTED" in log_text
    assert "unrecognized_service_name" in log_text


# ---------------------------------------------------------------------------
# do_GET / do_POST catch-all behavior, matching receiver.py exactly.
# ---------------------------------------------------------------------------

def test_get_unknown_path_returns_404(store, no_auth):
    status, _ = _get("/not-healthz")
    assert status == 404


def test_post_logs_and_traces_ack_200_empty_body(store, no_auth):
    for path in ("/v1/logs", "/v1/traces", "/v1/unknown"):
        status, body = _post(path, json.dumps({"anything": "goes"}).encode())
        assert status == 200
        assert body == {}


# ---------------------------------------------------------------------------
# AC 10: a record that passes cowork_ingest's validation but fails at the
# store-insert boundary is caught per-record; every other valid record in the
# same batch still inserts.
# ---------------------------------------------------------------------------

def test_store_insert_error_is_per_record_rejection_others_still_insert(store, no_auth, monkeypatch):
    payload = build_cowork_metrics_payload()
    real_insert = store.insert_datapoint
    calls = {"n": 0}

    def _flaky_insert(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise sqlite3.ProgrammingError("simulated unbindable parameter")
        return real_insert(**kwargs)

    monkeypatch.setattr(store, "insert_datapoint", _flaky_insert)

    status, body = _post("/v1/metrics", json.dumps(payload).encode())
    assert status == 200
    assert body["rejected"] == 1
    # 1 token row failed (the first insert_datapoint call), the other token
    # row and the cost row still succeed.
    assert body["inserted"] == 2

    assert len(_token_rows(store)) == 1
    assert len(_cost_rows(store)) == 1


# ---------------------------------------------------------------------------
# AC 11: a sqlite3.OperationalError mid-commit rolls back before propagating;
# no partial state is left committed.
# ---------------------------------------------------------------------------

def test_operational_error_on_commit_rolls_back_and_leaves_no_partial_state(
    store, cowork_db_path, no_auth, monkeypatch
):
    """Fix-cycle 1, issue 5: the evaluator showed that removing
    `store.db.rollback()` entirely still passed the ORIGINAL version of this
    test -- the "no partial state" assertion alone doesn't discriminate a
    missing rollback from one that happened, because a raised
    OperationalError with nothing yet inserted looks identical either way.
    Strengthened two ways: (a) spy directly on `store.db.rollback` and
    assert it was actually called; (b) follow up with a SECOND, unrelated,
    successful request and assert only ITS row is visible -- proving no
    uncommitted state from the failed request survived on the connection for
    the second request's commit() to silently sweep up.
    """
    payload = build_cowork_metrics_payload()
    real_commit = store.commit

    def _flaky_commit():
        raise sqlite3.OperationalError("simulated database is locked")

    monkeypatch.setattr(store, "commit", _flaky_commit)

    spy = _RollbackSpy(store.db)
    monkeypatch.setattr(store, "db", spy)

    with pytest.raises(sqlite3.OperationalError):
        _post("/v1/metrics", json.dumps(payload).encode())

    assert spy.rollback_calls == 1

    # A genuinely separate connection to the same file must see nothing --
    # rollback happened before the exception propagated.
    outside = sqlite3.connect(cowork_db_path)
    try:
        tok_count, cost_count = outside.execute(
            "SELECT (SELECT COUNT(*) FROM cowork_token_usage), "
            "(SELECT COUNT(*) FROM cowork_cost_usage)"
        ).fetchone()
        assert (tok_count, cost_count) == (0, 0)
    finally:
        outside.close()

    # Restore commit (only) so a second, unrelated request can succeed
    # normally -- re-patching to the real bound method rather than a blanket
    # monkeypatch.undo(), which would also revert this test's no_auth /
    # log-path patches (shared monkeypatch fixture instance).
    monkeypatch.setattr(store, "commit", real_commit)
    second_payload = build_cowork_metrics_payload(
        session_id="sess-unrelated-after-rollback")
    status, body = _post("/v1/metrics", json.dumps(second_payload).encode())
    assert status == 200
    assert body["inserted"] == 3

    outside2 = sqlite3.connect(cowork_db_path)
    try:
        rows = outside2.execute(
            "SELECT DISTINCT session_id FROM cowork_token_usage").fetchall()
        assert {r[0] for r in rows} == {"sess-unrelated-after-rollback"}
    finally:
        outside2.close()


def test_operational_error_mid_loop_rolls_back(store, cowork_db_path, no_auth, monkeypatch):
    payload = build_cowork_metrics_payload()
    real_insert_cost = store.insert_cost_datapoint

    def _flaky_insert_cost(**kwargs):
        raise sqlite3.OperationalError("simulated disk I/O error")

    monkeypatch.setattr(store, "insert_cost_datapoint", _flaky_insert_cost)

    spy = _RollbackSpy(store.db)
    monkeypatch.setattr(store, "db", spy)

    with pytest.raises(sqlite3.OperationalError):
        _post("/v1/metrics", json.dumps(payload).encode())

    assert spy.rollback_calls == 1

    outside = sqlite3.connect(cowork_db_path)
    try:
        tok_count, cost_count = outside.execute(
            "SELECT (SELECT COUNT(*) FROM cowork_token_usage), "
            "(SELECT COUNT(*) FROM cowork_cost_usage)"
        ).fetchone()
        assert (tok_count, cost_count) == (0, 0)
    finally:
        outside.close()


# ---------------------------------------------------------------------------
# AC 12: a 400 response's log line never carries raw request bytes.
# ---------------------------------------------------------------------------

def test_malformed_json_returns_400_and_log_has_no_raw_bytes(store, no_auth, tmp_path):
    secret_marker = "SECRET_COWORK_PAYLOAD_MARKER_XYZ"
    bad_body = f'{{"resourceMetrics": "{secret_marker}"'.encode()  # malformed JSON

    status, _ = _post("/v1/metrics", bad_body)
    assert status == 400

    log_text = (tmp_path / "cowork_receiver.log").read_text(encoding="utf-8")
    assert secret_marker not in log_text


def test_non_dict_envelope_returns_400_and_writes_nothing(store, no_auth):
    status, _ = _post("/v1/metrics", json.dumps([1, 2, 3]).encode())
    assert status == 400
    assert _token_rows(store) == []
    assert _cost_rows(store) == []


def test_non_dict_envelope_log_has_no_raw_bytes(store, no_auth, tmp_path):
    secret_marker = "SECRET_LIST_ENVELOPE_MARKER_ABC"
    status, _ = _post("/v1/metrics", json.dumps([secret_marker]).encode())
    assert status == 400
    log_text = (tmp_path / "cowork_receiver.log").read_text(encoding="utf-8")
    assert secret_marker not in log_text


# ---------------------------------------------------------------------------
# Fix-cycle 1, issue 7: malformed requests that previously got NO HTTP
# response at all (connection dropped, traceback to stderr) -- all five
# originate in the faithfully-duplicated _read_body/JSON-parsing path. These
# bugs also exist in receiver.py (out of this task's write fence -- never
# touched), but this receiver's own call site must not propagate them.
# ---------------------------------------------------------------------------

def test_non_numeric_content_length_returns_400(store, no_auth):
    status, _ = _post("/v1/metrics", b"{}", headers={"Content-Length": "not-a-number"})
    assert status == 400


def test_truncated_gzip_body_returns_400(store, no_auth):
    full = gzip.compress(json.dumps(build_cowork_metrics_payload()).encode())
    truncated = full[:10]
    status, _ = _post("/v1/metrics", truncated, headers={"Content-Encoding": "gzip"})
    assert status == 400


def test_corrupt_deflate_stream_returns_400(store, no_auth):
    full = bytearray(gzip.compress(
        json.dumps(build_cowork_metrics_payload()).encode()))
    # Keep the 10-byte gzip header intact, corrupt everything after it so
    # the deflate stream itself is invalid (confirmed via probing: this
    # raises zlib.error, "invalid block type").
    for i in range(10, len(full)):
        full[i] = 0xFF
    status, _ = _post("/v1/metrics", bytes(full), headers={"Content-Encoding": "gzip"})
    assert status == 400


def test_deeply_nested_json_returns_400_not_a_crash(store, no_auth):
    nested = ("[" * 100_000) + ("]" * 100_000)
    status, _ = _post("/v1/metrics", nested.encode())
    assert status == 400


def test_non_ascii_presented_token_returns_401_not_a_crash(store, with_auth):
    """Not an auth-bypass concern -- the request is correctly refused either
    way. Only proves hmac.compare_digest's TypeError on non-ASCII str input
    is caught and turned into a clean 401 instead of an unhandled
    exception."""
    status, _ = _post("/v1/metrics", json.dumps(build_cowork_metrics_payload()).encode(),
                       headers={"X-Billing-Token": "café-not-the-real-token"})
    assert status == 401


# ---------------------------------------------------------------------------
# Fix-cycle 2 helpers.
# ---------------------------------------------------------------------------

_KNOWN_LINE_PREFIXES = ("POST ", "401 POST ", "413 POST ", "BAD ", "REJECTED ",
                        "/v1/metrics ")


def _log_lines(tmp_path) -> list[str]:
    return [l for l in (tmp_path / "cowork_receiver.log").read_text(
        encoding="utf-8").splitlines() if l.strip()]


def _assert_every_line_is_genuine(lines: list[str]) -> None:
    """Every physical line in the log must be one THIS receiver wrote: an
    HH:MM:SS timestamp followed by one of the known message prefixes. A
    forged line (whatever character split it off) fails this."""
    import re
    for line in lines:
        m = re.match(r"^\d\d:\d\d:\d\d (.*)$", line)
        assert m, f"line without a receiver-written timestamp prefix: {line!r}"
        assert m.group(1).startswith(_KNOWN_LINE_PREFIXES), (
            f"line with an unknown prefix (forged?): {line!r}")


# ---------------------------------------------------------------------------
# Fix-cycle 2, issue 2: log injection via HTTP HEADER values and self.path.
# The fix-cycle-1 sanitizer covered payload-derived fields only; Content-Type
# / Transfer-Encoding / Content-Encoding and the request path went into
# `_log(...)` raw. A CRLF-folded header value (obs-fold, which Python's header
# parser preserves inside the value) forged a genuinely separate log line, and
# a huge folded header / 60KB path wrote that many bytes per request -- the
# 401 path with NO authentication at all.
# ---------------------------------------------------------------------------

_FOLDED_CTYPE = "application/json\r\n 12:00:00 POST /v1/metrics FORGED-VIA-FOLD"


def test_folded_content_type_header_does_not_forge_a_log_line(store, no_auth, tmp_path):
    payload = build_cowork_metrics_payload()
    status, body = _post("/v1/metrics", json.dumps(payload).encode(),
                          headers={"Content-Type": _FOLDED_CTYPE})
    assert status == 200 and body["inserted"] == 3

    lines = _log_lines(tmp_path)
    _assert_every_line_is_genuine(lines)
    # The marker survives -- escaped, on the SAME line as content-type=.
    carrying = [l for l in lines if "FORGED-VIA-FOLD" in l]
    assert len(carrying) == 1
    assert "content-type=" in carrying[0]
    assert "\\r\\n" in carrying[0]
    # No physical line ever starts with the forged timestamp.
    assert not any(l.startswith("12:00:00") for l in lines)


def test_folded_content_type_on_bad_request_body_line_does_not_forge(store, no_auth, tmp_path):
    """The BAD-request-body log line interpolates ctype/te/ce too."""
    status, _ = _post("/v1/metrics", b"{}", headers={
        "Content-Length": "not-a-number", "Content-Type": _FOLDED_CTYPE})
    assert status == 400
    lines = _log_lines(tmp_path)
    _assert_every_line_is_genuine(lines)
    assert any("BAD request body" in l and "FORGED-VIA-FOLD" in l for l in lines)


def test_folded_content_encoding_and_transfer_encoding_do_not_forge(store, no_auth, tmp_path):
    payload = build_cowork_metrics_payload()
    status, body = _post("/v1/metrics", json.dumps(payload).encode(), headers={
        "Content-Encoding": "identity\r\n 12:00:01 FORGED-CE",
        "Transfer-Encoding": "identity\r\n 12:00:02 FORGED-TE",
    })
    assert status == 200 and body["inserted"] == 3
    lines = _log_lines(tmp_path)
    _assert_every_line_is_genuine(lines)
    post_lines = [l for l in lines if " POST /v1/metrics bytes=" in l]
    assert len(post_lines) == 1
    assert "FORGED-CE" in post_lines[0] and "FORGED-TE" in post_lines[0]


def test_folded_content_type_on_bad_metrics_payload_line_does_not_forge(store, no_auth, tmp_path):
    status, _ = _post("/v1/metrics", b"{not json", headers={"Content-Type": _FOLDED_CTYPE})
    assert status == 400
    lines = _log_lines(tmp_path)
    _assert_every_line_is_genuine(lines)
    assert any("BAD metrics payload" in l and "FORGED-VIA-FOLD" in l for l in lines)


def test_huge_folded_header_value_is_bounded_in_the_log(store, no_auth, tmp_path):
    # Folded across several continuation lines (each under http.client's
    # 64KiB per-line limit, so the request itself is accepted) -- the same
    # shape as the evaluator's ~5.4MB reproduction, scaled down.
    huge = "application/json" + ("\r\n " + "A" * 50_000) * 4
    payload = build_cowork_metrics_payload()
    status, _ = _post("/v1/metrics", json.dumps(payload).encode(),
                       headers={"Content-Type": huge})
    assert status == 200
    for line in _log_lines(tmp_path):
        assert len(line) < 1500
    assert (tmp_path / "cowork_receiver.log").stat().st_size < 10_000


def test_long_path_on_unauthenticated_401_log_line_is_bounded(store, with_auth, tmp_path):
    """The 401 line is written BEFORE any auth passes -- an anonymous client
    controls its length via the request path."""
    long_path = "/v1/metrics/" + ("p" * 60_000)
    status, _ = _post(long_path, b"{}")   # no token presented
    assert status == 401
    lines = _log_lines(tmp_path)
    assert any(l.startswith("401 POST", 9) for l in lines)  # after "HH:MM:SS "
    for line in lines:
        assert len(line) < 1000
    assert "p" * 1000 not in (tmp_path / "cowork_receiver.log").read_text(encoding="utf-8")


def test_401_log_line_path_is_sanitized_not_raw(store, with_auth, tmp_path, monkeypatch):
    """A request line can't carry a raw CR/LF (or NEL/FS -- `str.split()`
    treats those as whitespace and the request is refused as malformed),
    but self.path CAN carry other non-printables such as an ANSI ESC
    sequence or DEL -- prove the 401 line escapes them rather than trusting
    the transport."""
    status, _ = _post("/v1/metrics\x1b[31mFORGED\x7fTAIL", b"{}")
    assert status == 401
    lines = _log_lines(tmp_path)
    _assert_every_line_is_genuine(lines)
    line = next(l for l in lines if "401 POST" in l)
    assert "\\x1b" in line and "\\x7f" in line
    assert "\x1b" not in line and "\x7f" not in line


# ---------------------------------------------------------------------------
# Fix-cycle 2, issue 3: the sanitizer escaped only \r and \n. NEL, LINE
# SEPARATOR, VT, FF, FS and ANSI ESC sequences each forge an extra line for
# str.splitlines() / a terminal, and ESC can rewrite earlier terminal output.
# ---------------------------------------------------------------------------

_LINE_BREAKERS = [
    pytest.param("\x85", id="NEL"),
    pytest.param("\u2028", id="LINE-SEPARATOR"),
    pytest.param("\u2029", id="PARAGRAPH-SEPARATOR"),
    pytest.param("\x0b", id="VT"),
    pytest.param("\x0c", id="FF"),
    pytest.param("\x1c", id="FS"),
    pytest.param("\x1d", id="GS"),
    pytest.param("\x1e", id="RS"),
    pytest.param("\x1b[31m", id="ANSI-ESC"),
    pytest.param("\r", id="CR"),
    pytest.param("\n", id="LF"),
    pytest.param("\x00", id="NUL"),
]


@pytest.mark.parametrize("bad", _LINE_BREAKERS)
def test_sanitize_log_field_escapes_every_line_breaking_character(bad):
    out = cowork_receiver._sanitize_log_field(f"head{bad}FORGED-TAIL")
    assert len(out.splitlines()) == 1, out
    assert out.isprintable(), out
    assert "FORGED-TAIL" in out          # content preserved, just escaped
    for ch in bad:
        if not ch.isprintable():
            assert ch not in out
            expected = {"\r": "\\r", "\n": "\\n"}.get(ch, f"\\x{ord(ch):02x}")
            assert expected in out


def test_sanitize_log_field_keeps_printable_unicode():
    """Not over-aggressive: legitimate non-ASCII printable content stays."""
    assert cowork_receiver._sanitize_log_field("café ☃ 日本") == "café ☃ 日本"


def test_sanitize_log_field_escapes_backslash_first_so_output_is_unambiguous():
    # A literal backslash-x85 in the INPUT must not be confusable with an
    # escaped real NEL.
    assert cowork_receiver._sanitize_log_field("a\\x85b") == "a\\\\x85b"
    assert cowork_receiver._sanitize_log_field("a\x85b") == "a\\x85b"


@pytest.mark.parametrize("bad", _LINE_BREAKERS)
def test_line_breaking_character_in_service_name_does_not_forge_a_log_line(
    store, no_auth, tmp_path, bad
):
    """End-to-end through the REJECTED log path: the number of physical
    lines is exactly the number of lines the receiver wrote."""
    payload = build_cowork_metrics_payload(service_name=f"cowork{bad}12:00:00 FORGED-E2E")
    status, body = _post("/v1/metrics", json.dumps(payload).encode())
    assert status == 200 and body["rejected"] > 0
    lines = _log_lines(tmp_path)
    _assert_every_line_is_genuine(lines)
    # splitlines() already splits on every line-breaking character, so a
    # surviving raw one would have shown up above as a forged line; this
    # additionally covers the non-breaking non-printables (ESC, NUL).
    for ch in bad:
        if not ch.isprintable():
            assert all(ch not in l for l in lines)
    assert not any(l.startswith("12:00:00 FORGED") for l in lines)
    # Exactly two REJECTED lines (one per metric in the fixture) carry the
    # marker -- escaped, inline, never as their own line.
    assert sum("FORGED-E2E" in l for l in lines) == 2


# ---------------------------------------------------------------------------
# Fix-cycle 2, issue 4: unbounded Content-Length. A syntactically valid but
# absurd value made `rfile.read(length)` raise an uncaught MemoryError (no
# HTTP response, connection dropped); a negative value read until the client
# closed the connection.
# ---------------------------------------------------------------------------

def test_absurd_content_length_returns_413_not_a_dropped_connection(store, no_auth, tmp_path):
    status, _ = _post("/v1/metrics", b"{}", headers={"Content-Length": "99999999999999"})
    assert status == 413
    assert _token_rows(store) == []
    assert any("413 POST" in l for l in _log_lines(tmp_path))


def test_two_gigabyte_content_length_returns_413(store, no_auth):
    status, _ = _post("/v1/metrics", b"{}", headers={"Content-Length": str(2 * 1024 ** 3)})
    assert status == 413


def test_content_length_just_over_the_bound_returns_413(store, no_auth):
    status, _ = _post("/v1/metrics", b"{}",
                       headers={"Content-Length": str(cowork_receiver.MAX_BODY_BYTES + 1)})
    assert status == 413


def test_negative_content_length_returns_400_not_an_indefinite_read(store, no_auth, tmp_path):
    status, _ = _post("/v1/metrics", b"{}", headers={"Content-Length": "-1"})
    assert status == 400
    assert any("BAD request body" in l and "negative Content-Length" in l
               for l in _log_lines(tmp_path))


def test_large_but_under_bound_valid_payload_still_succeeds(store, no_auth):
    """Don't break legitimate large-ish payloads: a valid JSON document padded
    with insignificant whitespace to 512 KiB (well over any real Cowork
    export, well under MAX_BODY_BYTES) must still ingest normally."""
    body = json.dumps(build_cowork_metrics_payload()).encode()
    body = body + b" " * (512 * 1024 - len(body))
    assert len(body) < cowork_receiver.MAX_BODY_BYTES
    status, resp = _post("/v1/metrics", body)
    assert status == 200
    assert resp["inserted"] == 3
    assert len(_token_rows(store)) == 2


def test_absurd_chunk_size_returns_413(store, no_auth):
    """The chunked path's size lines are exactly as client-controlled."""
    chunked = b"FFFFFFFFFFFF\r\n" + b"{}\r\n" + b"0\r\n\r\n"
    status, _ = _post("/v1/metrics", chunked, headers={"Transfer-Encoding": "chunked"})
    assert status == 413


def test_chunked_body_under_bound_still_succeeds(store, no_auth):
    payload = json.dumps(build_cowork_metrics_payload()).encode()
    chunked = f"{len(payload):x}\r\n".encode() + payload + b"\r\n0\r\n\r\n"
    status, resp = _post("/v1/metrics", chunked, headers={"Transfer-Encoding": "chunked"})
    assert status == 200 and resp["inserted"] == 3


def test_gzip_body_that_inflates_past_the_bound_returns_413(store, no_auth):
    inflated = b" " * (cowork_receiver.MAX_BODY_BYTES + 1024) + b"{}"
    compressed = gzip.compress(inflated)
    assert len(compressed) < cowork_receiver.MAX_BODY_BYTES
    status, _ = _post("/v1/metrics", compressed, headers={"Content-Encoding": "gzip"})
    assert status == 413


class _StubRFile:
    def __init__(self, exc):
        self._exc = exc

    def read(self, n):
        raise self._exc


class _StubHandler:
    def __init__(self, headers: dict, rfile):
        self.headers = headers
        self.rfile = rfile


def test_read_body_turns_memory_error_into_body_too_large(monkeypatch):
    """Last-resort safety net: even if a length slipped past validation, an
    allocation failure during the read becomes BodyTooLargeError (-> 413),
    never a raw MemoryError."""
    h = _StubHandler({"Content-Length": "1024"}, _StubRFile(MemoryError()))
    with pytest.raises(cowork_receiver.BodyTooLargeError):
        cowork_receiver._read_body(h)


def test_read_body_rejects_negative_and_oversized_before_touching_rfile():
    class _NeverRead:
        def read(self, n):
            pytest.fail(f"rfile.read({n}) must not be called for an invalid length")

    with pytest.raises(ValueError):
        cowork_receiver._read_body(_StubHandler({"Content-Length": "-5"}, _NeverRead()))
    with pytest.raises(cowork_receiver.BodyTooLargeError):
        cowork_receiver._read_body(
            _StubHandler({"Content-Length": "99999999999999"}, _NeverRead()))


def test_read_body_rejects_oversized_chunk_before_touching_rfile_read():
    """The chunked bound must trip on the declared size alone -- NOT merely
    because the platform happened to refuse the allocation (that's the
    safety net's job, and it would let a 2GB chunk through on a big host).
    Removing the cumulative-size check in `_read_body`'s chunked branch fails
    this test."""
    class _ChunkedStub:
        def __init__(self):
            self.lines = iter([f"{cowork_receiver.MAX_BODY_BYTES + 1:x}\r\n".encode()])

        def readline(self):
            return next(self.lines, b"")

        def read(self, n):
            pytest.fail(f"rfile.read({n}) must not be called for an oversized chunk")

    h = _StubHandler({"Transfer-Encoding": "chunked"}, _ChunkedStub())
    with pytest.raises(cowork_receiver.BodyTooLargeError):
        cowork_receiver._read_body(h)


def test_read_body_rejects_chunks_that_are_cumulatively_oversized():
    """Two chunks each under the bound whose SUM is over it."""
    half = cowork_receiver.MAX_BODY_BYTES // 2 + 1

    class _TwoChunkStub:
        def __init__(self):
            self.n_reads = 0
            self.lines = iter([f"{half:x}\r\n".encode(), b"\r\n",
                               f"{half:x}\r\n".encode(), b"\r\n"])

        def readline(self):
            return next(self.lines, b"")

        def read(self, n):
            self.n_reads += 1
            return b"x" * n

    stub = _TwoChunkStub()
    with pytest.raises(cowork_receiver.BodyTooLargeError):
        cowork_receiver._read_body(_StubHandler({"Transfer-Encoding": "chunked"}, stub))
    assert stub.n_reads == 1   # first chunk read, second refused before reading


def test_memory_error_during_read_yields_a_clean_413_response(store, no_auth, monkeypatch):
    """End-to-end: do_POST maps the safety net's BodyTooLargeError to 413."""
    def _boom(handler):
        raise cowork_receiver.BodyTooLargeError("could not allocate")
    monkeypatch.setattr(cowork_receiver, "_read_body", _boom)
    status, _ = _post("/v1/metrics", b"{}")
    assert status == 413


def test_body_too_large_error_is_not_a_value_error():
    """413 and 400 must stay distinguishable: a TOO-BIG body is not a
    MALFORMED one."""
    assert not issubclass(cowork_receiver.BodyTooLargeError, ValueError)


# ---------------------------------------------------------------------------
# Startup banner.
# ---------------------------------------------------------------------------

def test_startup_banner_mentions_auth_state(tmp_path, monkeypatch, capsys):
    """HTTPServer replaced with a fake that never binds a socket (real
    requirement: never bind a real port in a test); serve_forever returns
    immediately instead of blocking."""
    monkeypatch.setattr(cowork_receiver, "HTTPServer", _FakeServer)
    monkeypatch.setattr(cowork_receiver, "AUTH_TOKEN", "")

    cowork_receiver.serve("127.0.0.1", 0, db=str(tmp_path / "banner_cowork.db"))

    printed = capsys.readouterr().out
    assert "DISABLED" in printed
    assert "/v1/metrics" in printed


def test_startup_banner_shows_enabled_when_token_set(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cowork_receiver, "HTTPServer", _FakeServer)
    monkeypatch.setattr(cowork_receiver, "AUTH_TOKEN", "some-token")

    cowork_receiver.serve("127.0.0.1", 0, db=str(tmp_path / "banner_cowork2.db"))

    printed = capsys.readouterr().out
    assert "ENABLED" in printed


# ---------------------------------------------------------------------------
# No test in this file binds a real network socket -- static verification.
# ---------------------------------------------------------------------------

def test_this_test_file_never_binds_a_real_socket():
    """AST-scans THIS test file's own CODE (excluding the module docstring's
    prose, which describes the convention in words) for socket.bind / a real
    HTTPServer(...).serve_forever() call against a real address, proving
    AC 9 by construction rather than by convention alone. Every _FakeServer
    used in this file takes an addr but never actually binds one."""
    src_path = Path(__file__)
    source = src_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    module_docstring = ast.get_docstring(tree) or ""
    code_only = source.replace(module_docstring, "")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "bind":
            pytest.fail("found a real .bind(...) call in the test file")
    assert "socketpair()" in code_only
