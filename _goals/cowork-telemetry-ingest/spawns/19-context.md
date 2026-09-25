You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-24T00:00:00Z

## Task

This is FIX CYCLE 2 for Task 03 of the `cowork-telemetry-ingest` goal. You are a fresh agent
with no memory of prior work — this context package is fully self-contained.

Task 03's module (`billing/otel/cowork_receiver.py`) is a brand-new, standalone HTTP receiver
for Cowork telemetry — the live network ingress point for this goal. It has already been
through one implementation pass plus one fix cycle (both by a different agent), driven by
adversarial evaluator probing (constructing malicious/malformed inputs and mutation-testing
the fixes, not just reading tests). The first evaluation found a `security`-tagged log-injection/
disk-fill issue plus 6 other major issues; fix cycle 1 closed all 7 (verified via 14 fresh
mutation tests). A second adversarial pass just found the log-injection class REAPPEARING via a
different route (HTTP headers instead of payload fields), a test-cleanup fix that made things
WORSE (a real leak, now confirmed), an incomplete character sanitizer, and an unbounded
`Content-Length` causing `MemoryError`. Fix ALL FOUR below completely.

### Issue 1 [major]: the `.env` test's own cleanup leaks a fake token into every later test

`tests/test_cowork_receiver.py`, the `test_cowork_receiver_auth_token_loaded_from_dotenv` test
(~lines 415-449): it currently uses `monkeypatch.delenv(k, raising=False)` BEFORE calling
`load_env()` to ensure clean state, then in a `finally` block calls `delenv` again to try to
clean up. The bug: `monkeypatch.delenv(k, raising=False)` on a variable that is NOT currently
set records NOTHING for monkeypatch to restore later (there's nothing to restore TO). Then
`load_env()` sets the variable from the temp `.env` file. The `finally` block's second
`delenv(k, raising=False)` call then captures THIS newly-set (leaked) value as what
monkeypatch should restore when the test's monkeypatch fixture tears down — so monkeypatch
"restores" the environment to a state WITH the leaked value in it, not to the original
(unset) state. Verified by the evaluator: after this test runs, `RECEIVER_AUTH_TOKEN` and
`COWORK_RECEIVER_AUTH_TOKEN` are BOTH left set to fake test values in `os.environ` for the rest
of the test session — worse than the original problem, since this is now a confirmed real leak,
not just an undertested claim.

**Fix**: use `unittest.mock.patch.dict(os.environ, ..., clear=False)` as a context manager (or
equivalent) around the reload, which snapshots and exactly restores the FULL environment
regardless of add/remove operations performed inside — rather than trying to use
`monkeypatch.delenv`/`setenv` calls whose restore-recording depends on call ORDER relative to
when values were actually set. Alternatively: manually snapshot
`{k: os.environ.get(k) for k in (...)}` before the test body, and in a `finally` block, for each
key: if the snapshotted value was `None`, `os.environ.pop(k, None)`; else
`os.environ[k] = snapshotted_value`. Do NOT call `monkeypatch.delenv` again AFTER `load_env()`
has potentially set a new value — that's the exact ordering bug. Verify your fix by running the
FULL test suite and asserting (in a small scratch check, or via a dedicated
teardown-verification test) that `RECEIVER_AUTH_TOKEN` and `COWORK_RECEIVER_AUTH_TOKEN` are
both absent from `os.environ` both BEFORE and AFTER running `tests/test_cowork_receiver.py`.

### Issue 2 [major]: log injection reappears via unsanitized HTTP header values and `self.path`

`billing/otel/cowork_receiver.py` (around lines 364, 386, 392, 409 in the current version — read
the actual current file, these line numbers may have shifted): the fix cycle 1 sanitizer
(`_sanitize_log_field`) is applied to rejection reasons/details and `metrics_seen`, but several
OTHER values written into log lines are NOT passed through it: `ctype` (Content-Type header),
`te` (Transfer-Encoding header), `ce` (Content-Encoding header), and `self.path` (the request
path) — all attacker-controlled, all going straight into `_log(...)` calls unsanitized.
Reproduced: a `Content-Type` header value containing a CRLF-folded sequence
(`"application/json\r\n 12:00:00 FORGED-VIA-FOLD"`) produces a genuinely separate, forged log
line. A ~5.4MB folded header value produces a ~5.4MB log write per request. The 401
(unauthorized) log line logs `self.path` with ZERO sanitization even when the request isn't
authenticated at all — a 60KB path writes 60KB to the log, unauthenticated.

**Fix**: pass EVERY value that goes into a `_log(...)` call through `_sanitize_log_field`
(or an equivalent sanitizing step) — this includes `self.path` on the 401 log line, and
`ctype`/`te`/`ce` on both the POST-received log line and the BAD-request log lines. There should
be NO log-writing call site left that interpolates a raw, attacker-controlled string directly.
Add tests: a folded/CRLF-containing header value doesn't create a new log line; a very long path
on the 401 log line is bounded in length; grep or otherwise audit every `_log(f"...")` call site
in the file to confirm each interpolated variable that could originate from request data is
sanitized (state in your report that you did this audit and list the call sites you checked).

### Issue 3 [major]: the sanitizer only escapes `\r` and `\n`, missing other line-breaking characters

`billing/otel/cowork_receiver.py`, `_sanitize_log_field` (or equivalent, current line ~92-101):
it currently escapes only `\r` and `\n`. Other Unicode/control characters that break lines when
displayed or parsed still get through unescaped: NEL (`\x85`), LINE SEPARATOR (` `),
vertical tab (`\x0b`), form feed (`\x0c`), file separator (`\x1c`), and ANSI escape sequences
(`\x1b[...`). Each of these can forge an apparent new log line when the file is read with
`str.splitlines()` (which the tests themselves use to check line counts) or displayed in a
terminal (e.g. `tail -f`), and ANSI escapes specifically can rewrite/hide earlier terminal
output for a live viewer.

**Fix**: escape or strip EVERY non-printable character, not just `\r`/`\n` — a solid approach:
`"".join(c if c.isprintable() else f"\\x{ord(c):02x}" for c in s)` (note: `str.isprintable()`
returns `False` for control characters, line/paragraph separators, and most other characters
that would misbehave in a log; adjust if you find it too aggressive for legitimate content, but
justify any exception explicitly). Add tests for `\x85`, ` `, `\x0b`, and an ANSI ESC
sequence (`\x1b[31m`) each individually — confirm none of them can still produce what
`str.splitlines()` would count as an extra line.

### Issue 4 [major]: unbounded `Content-Length` causes `MemoryError` with no HTTP response

In the locally-duplicated `_read_body` function (mirroring `receiver.py`'s, current line ~160):
a `Content-Length` header of `99999999999999` (a huge but syntactically valid integer) causes
`handler.rfile.read(length)` to attempt allocating that much memory, raising `MemoryError`
which is NOT currently caught anywhere in the call chain — the connection drops with no HTTP
response and a traceback to stderr. A merely large-but-plausible value (e.g. 2GB) would also
attempt that allocation per request, and a NEGATIVE `Content-Length` currently reads until the
client closes the connection (a potential hang on a slow/malicious client), rather than being
rejected outright.

**Fix**: before calling `handler.rfile.read(length)` in your local `_read_body`, validate
`length`: reject (return an error status, e.g. 400 or 413, from the calling `do_POST`) if it is
negative, or if it exceeds some explicit maximum reasonable body size for this receiver's
traffic (pick a sane bound — e.g. a few megabytes; Cowork OTLP metric exports are not expected
to be enormous; document your chosen bound and reasoning in a comment). Also add a defensive
`try/except MemoryError` around the actual read call as a last-resort safety net in case a
value slips through validation on a platform where the bound check itself has an edge case.
Add tests for: `Content-Length: 99999999999999` → clean 400/413, not a dropped connection; a
negative `Content-Length` → clean 400, not an indefinite read; a large-but-under-your-chosen-
limit valid request still succeeds normally (don't accidentally break legitimate large-ish
payloads).

## Files to Read

- `_goals/cowork-telemetry-ingest/03-cowork-receiver.md` — the task's Requirements and
  Acceptance Criteria.
- `billing/otel/cowork_receiver.py` — the current, twice-worked-on module. READ IT FULLY,
  understand the current state of `_sanitize_log_field`, `_read_body`, `do_POST`, `_authorized`,
  and every `_log(...)` call site, before editing.
- `tests/test_cowork_receiver.py` — the current 43 tests. Read fully; extend, don't duplicate or
  restructure what's already correct.
- `billing/otel/receiver.py` — reference only, for the original `_read_body` pattern being
  mirrored (do NOT import from it, do NOT modify it).
- `billing/otel/cowork_store.py`, `billing/otel/cowork_ingest.py` — the frozen contracts this
  receiver depends on (unchanged in this fix cycle, read for context only if needed).
- `billing/config.py` — `load_env()`, relevant to Issue 1's reload mechanics.

## Write fence

ONLY these paths (unchanged from the original task):
- billing/otel/cowork_receiver.py
- tests/test_cowork_receiver.py
- .env.example (only if genuinely needed for this cycle's fixes — likely not needed)

Do NOT modify `billing/otel/receiver.py`, `billing/otel/cowork_store.py`, or
`billing/otel/cowork_ingest.py` in any way.

## Model

requested: claude-fable-5-1 · tier: light · rotation: cycle 2 (different model line, per this
repo's fix-cycle rotation policy — model map: cycle 1 claude-sonnet-5, cycle 2
claude-fable-5-1, cycle 3 claude-opus-5)

## Rules

- Fix all four issues completely, each with dedicated regression test(s) that would fail
  without the fix — verify this yourself: temporarily reintroduce each bug, confirm your test
  catches it, then restore the fix. This exact technique has been used against this module
  three times already by the evaluator; match that rigor.
- Do not regress anything — all 43 existing tests in this file, and the full 661-test suite,
  must still pass.
- Pay special, careful attention to Issue 1's exact mechanics — it's a subtle test-cleanup
  ordering bug, not a production code bug, but it has real consequences for every test that
  runs after it in the same process (including, eventually, task 05's integration tests).
- Stdlib only.
- Run the FULL test suite (`python -m pytest tests/ -q`) before reporting completion, and
  double-check every numeric claim (test counts, line numbers) against actual command output
  immediately before writing your report.
- State any judgment calls explicitly (e.g. your chosen max body size bound for Issue 4).

## Output

A completion report: what you changed (exact file paths and line references, verified live via
grep/read immediately before writing the report), how each of issues 1-4 is fixed and tested,
the full output of `python -m pytest tests/ -q`, `git diff` confirmation on the three untouched
files, and judgment calls. End with a `### Footprint` section: files_read count/approx chars,
commands_run count.
