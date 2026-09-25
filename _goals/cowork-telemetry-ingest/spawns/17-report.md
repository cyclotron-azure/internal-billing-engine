Fix cycle 1 for task 03. All 7 issues (including the security-tagged one) plus 3 optional
cleanups addressed:

1. Empty-log-path fix: LOG_PATH/AUTH_TOKEN now use `or` fallback, not `.get(key, default)`, so
   an env var present-but-empty falls back correctly. .env.example's new lines recommented
   with real defaults shown.
2. COWORK_DB from .env now honored: main() resolves the --db default at call time via
   os.environ.get("COWORK_DB") or DEFAULT_COWORK_DB, after load_env() has run, instead of using
   the import-time-frozen constant.
3. [security] Added _sanitize_log_field() (escapes \r/\n, caps to 200 chars) applied to every
   rejection reason/detail and metrics_seen entries; capped rejection log lines per request to
   20 with a "+N more omitted" summary line.
4. Rejections now logged in a finally block regardless of whether commit succeeds.
5. AC11 rollback tests strengthened with a _RollbackSpy proxy (sqlite3.Connection refuses
   arbitrary attribute assignment, so the whole store.db attribute is swapped) asserting
   rollback() was actually called exactly once, plus a full round-trip proving the failed
   batch's rows never persist.
6. AC6 .env test rewritten to monkeypatch.delenv both token vars, use a real temp .env file,
   importlib.reload, and assert against the actual reloaded module state; a finally block
   restores clean state for later tests.
7. Malformed requests (bad Content-Length, truncated gzip, corrupt deflate, deep JSON nesting,
   non-ASCII token) now get clean 400/401 responses via new exception handling in do_POST and
   _authorized(), without touching receiver.py.

Every fix verified by deliberately reintroducing the bug and confirming the specific test
fails, then restoring -- including both evaluator-named mutants for issue 6.

python -m pytest tests/test_cowork_receiver.py -v -> 43 passed (up from 30)
python -m pytest tests/ -q (full suite) -> 661 passed
git diff -- billing/otel/receiver.py -> empty

Full report with line references in the completion notification for agentId
a6a6a5ee81c60e7d9.
