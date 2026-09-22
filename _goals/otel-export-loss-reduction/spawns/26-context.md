You are the test-writer subagent. Read: .claude/agents/test-writer.md

CURRENT_DATETIME: 2026-09-21T11:00-04:00

## Task

Four independent fixes to the test suite, none of which are novel bug-hunting — each
corrects a test to match a decision or fix already made and recorded. Read the four cited
task-file sections before touching anything; each explains the "why" you'll need.

## Fix 1 — `pilot-package/` was deleted; three tests still reference it

`pilot-package/` (and `pilot-package.zip`) were deleted by the user's own decision — it was
already documented as "superseded by `client-package/`" in `README.md`. Full record:
`_goals/otel-export-loss-reduction/01-export-interval.md`'s new "Addendum" section at the
bottom.

In `tests/test_cli_backfill.py`:

- **`test_01_ac01_all_four_config_sources_carry_10000_dev_selftest_keeps_5000`** — the
  `sources` dict has four entries; remove the two `pilot-package/*` entries. Keep
  `deploy/managed-settings.json` and `client-package/configure.py`. Rename the function to
  drop "four" from its name (e.g. `test_01_ac01_surviving_config_sources_carry_10000_dev_selftest_keeps_5000`).
- **`test_01_ac02_managed_settings_and_pilot_settings_carry_string_10000`** — delete the
  `pilot = json.loads(...)` block and its two assertions. Rename to drop "pilot" (e.g.
  `test_01_ac02_managed_settings_carries_string_10000`).
- **`test_01_ac04_install_sh_parses_and_emits_valid_json_with_new_value`** — **delete this
  test entirely.** `client-package/install.sh` is a thin shim to `configure.py` and never
  wrote a JSON heredoc (confirmed: `cat client-package/install.sh` — it's a `case` statement
  that execs `configure.py`), so there is no surviving file this test's mechanism applies
  to. Its coverage purpose is already carried by `test_01_ac03` (`configure.py`'s defaults
  dict). Do not retarget it onto something that doesn't test the same thing.

Do not touch `test_01_ac03` or `test_01_ac05`-`ac07` — they already only reference the two
surviving sources.

## Fix 2 — two dead node ids in `tests/COVERAGE_MAP.md`

Task 05's inversions renamed two tests; the map still cites the old names.

```
line 72:  | 5. `entrypoint='cli'` rejected, not inserted | `test_receiver.py::test_non_desktop_entrypoint_is_rejected` |
line 113: | 1. Only desktop entrypoint ships | `test_transcript_hook.py::test_ac1_only_desktop_entrypoint_ships` |
```

Current replacement tests (confirmed present and collected):
- `test_receiver.py::test_backfill_entrypoint_is_accepted_when_old_enough_and_no_otlp_row`
  (the positive half) and `::test_out_of_set_entrypoint_still_rejected_with_invalid_entrypoint`
  (negative case) — cite both, since the old single row's behavior split into two tests.
- `test_transcript_hook.py::test_ac1_desktop_and_cli_entrypoints_ship_claude_vscode_withheld_trailing`
  and `::test_ac1_out_of_set_entrypoint_never_ships` — same split.

Update both map rows to cite the real, currently-collected test(s). If a row's criterion
text ("entrypoint='cli' rejected") now describes the *old*, deliberately-reversed
behavior, reword the criterion text too so the map doesn't read as documenting a bug.

## Fix 3 — task 06 fix cycle 2 landed; two tests in `tests/test_receiver_health.py` test the OLD behavior or a weak assertion style

Full record: `_goals/otel-export-loss-reduction/06-otlp-session-id-coercion.md` criteria
10-11. `billing/otel/receiver.py`'s `_common` was just changed so that only a **genuinely
absent** `session.id` (or one `_attr_value` can't parse) maps to `'unknown'`; a
**present-but-falsy** value (`0`, `False`, `0.0`, `''`) now keeps its own `str()` spelling.

- **`test_06_ac06_falsy_or_absent_session_id_stores_unknown`** (parametrized over
  `{"intValue": "0"}`, `{"stringValue": ""}`, `{"boolValue": False}`) asserts all three
  store `'unknown'`. That's now wrong for all three. Split into two tests:
  - `test_06_ac06_present_but_falsy_session_id_keeps_own_spelling` — parametrize over the
    same three wrappers, assert the stored value is `'0'`, `''`, `'False'` respectively
    (their own `str()`), **not** `'unknown'`.
  - `test_06_ac11_genuinely_absent_session_id_still_stores_unknown` — an OTLP datapoint
    with **no** `session.id` attribute at all (empty `attributes` list, or omit the key
    entirely) still stores `'unknown'`. This is criterion 11 — the case that must stay
    exactly as it was.
  - **Add the actual double-billing regression**, which is the point of this fix and isn't
    tested by either of the above alone: seed an OTLP row via one of the three falsy
    wrappers (say `intValue "0"`), then post a `cli` transcript record for
    `session_id="0"` with no other OTLP row. Assert it is **rejected** `session_has_otlp`
    and `SELECT COUNT(*)` over both `token_usage` and `cost_usage` is unchanged before vs.
    after. Before this fix, that record was wrongly **accepted** — this is the assertion
    that would have caught the bug. Name it
    `test_06_ac10_falsy_session_id_now_correctly_excludes_matching_cli_record`.

- **`test_06_ac09_other_ingest_paths_unaffected_by_common_coercion`** — its final assertion
  is a **source-text substring check**:
  `assert "str(a.get(\"session.id\")" in src or "str(a.get('session.id')" in src`. This is
  a weak assertion style (it checks that the code *looks* a certain way, not that it
  *behaves* correctly) and it broke because the fix legitimately restructured that
  expression into a local variable. **Delete that last assertion and the now-unused
  `import inspect` line; keep everything above it** — the `/v1/session-repo`, `/healthz`,
  and `/v1/transcript-usage` behavioral checks in the rest of the function are still valid
  and still worth having. If you want confinement coverage for `_common`, express it
  behaviorally (e.g. assert the four other fields in a returned `_common(...)` dict are
  unchanged for a representative payload) rather than grepping source text.

## Fix 4 — no behavioral test for `sqlite3.Error` propagation in `sessions_with_otlp_rows`

Full record: `_goals/otel-export-loss-reduction/02-store-reads.md` criterion 16.

Add to `tests/test_store_reads.py`: force the store's connection to raise `sqlite3.Error`
during the query `sessions_with_otlp_rows` issues (e.g. close the underlying connection
first, or monkeypatch `execute` on a delegating wrapper — reuse the `_ExecuteSpy` pattern
already in this suite at `tests/test_dedupe_counter.py:57` if you need one that raises
instead of just counting), and assert the exception **propagates out of the call** —
`pytest.raises(sqlite3.Error)` or similar — rather than being caught and turned into an
empty `set()`. Name it `test_ac16_sqlite_error_propagates_not_swallowed`.

Add this row to `tests/COVERAGE_MAP.md`'s task-02 section.

## Full inventory of write-fence files for this spawn

```
tests/test_cli_backfill.py       (fix 1 — targeted edits to 3 test functions)
tests/test_receiver_health.py    (fix 3 — targeted edits to 2 test functions, +2 new)
tests/test_store_reads.py        (fix 4 — +1 new test)
tests/COVERAGE_MAP.md            (fixes 2 and 4 — targeted row updates/additions)
```

Nothing else. Not `billing/`, not `client-package/`, not `deploy/`.

## Model

requested: claude-sonnet-5 · tier: light · rotation: n/a

## Rules

- Do not weaken an assertion to make it pass. If something you'd expect to hold does not,
  report it — do not paper over it.
- Every store/fixture stays `tmp_path`-scoped; no live network; nothing touches
  `data/*.db` or the real `~/.claude`.
- Run the **full suite** at the end (not just a subset) — this spawn's job is specifically
  to get the suite back to fully green after the pilot-package deletion and the fix-cycle
  landed, so verify against the whole thing, not a partial selection.
- Standard library plus `pytest` only.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Fix 1 (pilot-package)
[Renamed/deleted test names, final state of each.]

## Fix 2 (coverage map dead ids)
[The two corrected rows, verbatim.]

## Fix 3 (task 06 tests)
[The split, the new regression test, and the ac09 rewrite. Confirm the regression test
would have FAILED against the pre-fix code -- state how you know (e.g. you can point to
the fix-cycle report's reproduction, or reason about it directly).]

## Fix 4 (sqlite3.Error test)
[The test, and confirm it fails if `sessions_with_otlp_rows` is wrapped in
try/except sqlite3.Error: return set() -- reason about this or check against a scratchpad
mutation, never the repo.]

## Verification
[Full suite -> result. MUST be green. Report the count.]

## Anything else touched
["None" is valid.]

### Footprint
files_read: <N> (~<C> chars)
```
