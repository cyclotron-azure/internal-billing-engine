Fix cycle 2 for task 03 (fresh spawn, claude-fable-5-1 per rotation policy). All 4 issues
addressed:

1. .env test leak: reload now runs inside unittest.mock.patch.dict(os.environ, clear=False);
   both token vars popped inside the context, never via monkeypatch.delenv after load_env() ran;
   test asserts dict(os.environ) == env_before at the end. New dedicated leak-verification test
   runs immediately after. Confirmed before/after with a scratch plugin: before fix, both fake
   tokens leaked into os.environ after the full suite; after fix, both None before and after.
2. Header/path log injection: safe_path/ctype/te/ce sanitized once, only sanitized copies reach
   _log. Full call-site audit done post-edit (every _log(...) site listed with each interpolated
   value's sanitization status).
3. Sanitizer now escapes every non-printable char (str.isprintable() gate), not just \r/\n --
   \r/\n keep readable escapes for existing test compatibility, everything else -> \xNN.
4. Bounded body: MAX_BODY_BYTES = 8 MiB (documented reasoning), applied to Content-Length
   pre-read validation, chunked cumulative/per-chunk bound, and post-gzip-decompression bound;
   MemoryError caught as a last-resort net; BodyTooLargeError (413) kept distinct from
   malformed-input ValueError (400).

Verification: 91 passed (test file alone, 43 pre-existing + 48 new), 709 passed (full suite).
Mutation-verified: 8 targeted mutants across all 4 issues, all caught (one chunked-bound mutant
initially survived via the MemoryError net catching it a different way; implementer added 2
more precise tests to catch it before rfile.read, then it failed as expected).
sha256sum confirms receiver.py/cowork_store.py/cowork_ingest.py byte-identical to pre-cycle
snapshot (these are untracked so git diff alone is insufficient).

Noted but explicitly out of scope: 7 pre-existing test_invoice.py failures under `pytest -s`
on Windows (unrelated cp1252/arrow-character encoding issue, unrelated to this task) --
flagged as a separate task rather than touched.

Full report with exact line numbers and judgment-call reasoning in the completion notification
for agentId a5e7986cea9866c2b.
