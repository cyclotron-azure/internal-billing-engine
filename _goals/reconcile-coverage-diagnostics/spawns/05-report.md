VERDICT: PASS (with notes)
MODEL: claude-opus-5 (matches the requested pin `claude-opus-5`; harness reports "Opus 5")
SCORE: 5/5

## Summary

The implementation is correct, including the crux. `_ensure_dedupe_epoch` genuinely latches on **SELECT-confirmation** only — I observed the flag still `False` after an insert that issued the epoch `INSERT`, `dedupe_epoch()` returning `None` after `rollback()`, and the epoch recovering on the next insert on the *same* instance (criterion 11's exact scenario). Criterion 10's count is exactly **1** meta `SELECT` across the ten post-commit inserts, observed via a counting proxy, and a post-latch clean insert issues **zero** statements beyond the main `INSERT OR IGNORE`. The diff is genuinely additive (172 insertions / 0 deletions, confirmed by `git diff --numstat` and an empty deletion grep), the receiver and all test files are untouched, and no third-party import or second `sqlite3.connect` entered the module. The biggest residual risk is not a defect but a coverage gap: criteria 1, 3, 5, 6, 12, 13 and 14 currently have **no unit test** — they are verified only by my throwaway scratchpad run and stay unprotected against regression until task 04 lands. Two of them (3 and 10) have testability traps that will fail task 04's tests against this otherwise-correct implementation unless written carefully; see Findings.

## Acceptance criteria

1. **VERIFIED** — `PRAGMA table_info(dedupe_drops)` → `['day','token_type','usage_source','drops','first_seen','last_seen']`; `NOT NULL` on the first four, `drops` default `'0'`; `PRAGMA index_list` → one `pk` autoindex, `index_info` → `['day','token_type','usage_source']`. `billing/otel/otel_store.py:145-153`.
2. **VERIFIED** — `True` then `False`; exactly one row, `drops=1`, `day='2023-11-14'` from `time_unix_nano=1_700_000_000e9` while today is `2026-09-16`. `token_usage.ts` for the same row is `2023-11-14T22:13:20Z` — they agree.
3. **VERIFIED (with a testability trap)** — third insert → `drops=2`, `first_seen` byte-identical, `last_seen` advanced `…14:32:58Z` → `…14:32:59Z`. I had to `sleep(1.1)` to see the advance; see finding N3.
4. **VERIFIED** — `dedupe_drops` empty after one clean insert; `_record_dedupe_drop` is called only under `if cur.rowcount == 0` (`otel_store.py:438-441`, `497-500`).
5. **VERIFIED** — observed three distinct buckets: `(input, transcript)`, `(__cost__, otlp)`, `(__cost__, transcript)`, all `drops=1`. `insert_cost_datapoint` passes the literal `"__cost__"` at `otel_store.py:499`.
6. **VERIFIED** — built a `LEGACY_SCHEMA` db with seeded `token_usage`/`cost_usage`/`meta` rows, opened it with `OtelStore`: `dedupe_drops` created, the 13 legacy columns' values preserved **byte-for-byte** (tuple equality over the pre-migration column projection, `True`), new columns read back as `usage_source='otlp'`/`entrypoint=None`, opens #2 and #3 raise nothing and change nothing. (My first comparison printed `preserved: False` — that was my own bug comparing 13 columns against a 6-column projection; re-verified correctly.)
7. **VERIFIED** — open, call only read methods, close, reopen → `dedupe_epoch()` is `None` both times; `meta` is empty. `_migrate()` writes no epoch (`otel_store.py:261-278`).
8. **VERIFIED** — epoch `2026-09-16T14:33:00Z` after the first insert; unchanged after close/reopen + a 1.1s-later second insert.
9. **VERIFIED** — both paths. Successful-first-insert sets it (criterion 8's run). For duplicate-only I seeded a row, deleted the meta key, reopened a **fresh instance** (flag unset) and made its first attempt a duplicate → returned `False`, epoch set. `_ensure_dedupe_epoch()` is called unconditionally *before* the rowcount branch (`otel_store.py:437`, `496`).
10. **VERIFIED** — counting proxy over `store.db`: `1` meta SELECT across the ten, latch flag `True` after, 11 statements total (10 × token_usage INSERT + 1 SELECT). No other insert-path meta SELECT exists in the module (`grep "FROM meta"` → only lines 329 and 535, the latter being `dedupe_epoch()` itself, off the insert path).
11. **VERIFIED** — this is the crux and it holds: `insert1 → True`, `_dedupe_epoch_confirmed` still **False**, `rollback()`, `dedupe_epoch() → None`, `insert2` on the same instance → epoch set after commit. A latch-on-attempt build would print `None` at the last step.
12. **VERIFIED** — seeded `03-09`/`03-10`/`03-11`: `dedupe_drops('2026-03-10','2026-03-11')` → `{'input': 12, 'output': 3}` (12 = 2 otlp + 10 transcript, correctly summed across `usage_source`); `03-09` and `03-11` excluded; a `drops=0` `cacheRead` row is **absent**, not `0`. `dedupe_drops_by_day` → `{'2026-03-10': {...}}`. Empty window → `{}`/`{}`. Matches `reconcile.otel_totals`'s documented `[start, end)` convention (`billing/reconcile.py:69`).
13. **VERIFIED** — injected `sqlite3.OperationalError` on `UPDATE dedupe_drops` only: `insert_datapoint` returned `False`, no raise. Also injected on `INSERT OR IGNORE INTO dedupe_drops` only: returned `False`, no raise. See finding N2 about the residue.
14. **VERIFIED** — injected on `SELECT 1 FROM meta` only: clean insert returned `True`, no raise, latch flag stayed **False**, and the epoch was written on the next insert. Also injected on `INSERT OR IGNORE INTO meta` only: returned `True`, flag `False`.
15. **VERIFIED** — `python -m pytest tests/test_otel_store.py -q` → `27 passed in 2.35s`, run by me. `git diff --stat -- tests/` is empty: no existing test was modified.

## Verification points

1. **Latch rule — PASS.** `otel_store.py:325-339`: the only assignment `self._dedupe_epoch_confirmed = True` sits inside `if row is not None:` on the `SELECT` result. The `else` branch writes and falls through with the flag untouched. Confirmed behaviorally by criterion 11's rollback run.
2. **Criterion 10's exact count — PASS.** Observed `1`. Not zero (the post-commit insert is the one that closes the latch), not ten. Only two `FROM meta` statements exist in the module and the second is `dedupe_epoch()`, off the insert path.
3. **The `day` value — PASS.** `day=_ns_to_iso(time_unix_nano)[:10]` in both methods (`:440`, `:499`). Observed `day='2023-11-14'` against a wall-clock of `2026-09-16`. See the micro-caveat in N5.
4. **Error containment — PASS.** `except sqlite3.Error: pass` in both `_ensure_dedupe_epoch` (`:338`) and `_record_dedupe_drop` (`:367`) — not bare `Exception`. Both return the correct `True`/`False`, observed. A swallowed epoch failure leaves the flag unset and the next insert retries successfully, observed. This matters concretely: `receiver.py:266-269`'s `_RECORD_DATA_ERRORS` includes `sqlite3.InterfaceError`/`ProgrammingError`, so an unguarded counter raise would have become a per-record *billing* rejection.
5. **Hot-path cost — PASS.** `_record_dedupe_drop` is reachable only under `if cur.rowcount == 0`. A post-latch clean insert issued exactly one statement (`INSERT OR IGNORE INTO token_usage`); the duplicate issued three. Also confirmed that the intervening `_ensure_dedupe_epoch()` execute between `cur = self.db.execute(...)` and the `cur.rowcount` reads does **not** corrupt `rowcount` — `clean→True, dup→False, dup2→False` with `token_usage` holding one row.
6. **Portability — PASS.** `INSERT OR IGNORE` + `UPDATE` pair (`:358-366`). `grep "ON CONFLICT"` hits only the docstring explaining why it was avoided. `first_seen` is set on insert and never named in the `UPDATE`; `last_seen` is in both. Observed unchanged `first_seen` / advanced `last_seen`.
7. **Additive only — PASS.** `git diff --numstat` → `172 0`; `git diff -U0 | grep -E '^-[^-]'` → empty. The `db.commit()` closing `_migrate()` is a pre-existing context line, not new. `dp_key`, `transcript_key` and both `request_id` validation blocks are untouched — re-confirmed behaviorally (`otlp`+`request_id` still raises; whitespace-only transcript `request_id` still raises). `_migrate()` writes no epoch.
8. **Frozen interface — PASS, with one annotation-only drift.** See the dedicated section below. Runtime shapes and semantics match the task and match task 02's stated expectations (`02-reconcile-aggregation.md:166-171`). All three use `self.db`; the module's only `sqlite3.connect` is `__init__`'s (`:284`). No `get_meta`/`set_meta` was added.
9. **Receiver untouched — PASS, and correctly so.** `git diff --stat -- billing/otel/receiver.py` is empty. Both ingest paths already funnel through the two insert methods (`receiver.py:167`, `:180`, `:358`, `:361`), and `store.commit()` is already per-request (`:189`, `:378`), so the no-commit design rides an existing transaction. No receiver change was needed.
10. **Targeted suite — PASS.** Run by me: `27 passed in 2.35s`. I did not run the full suite.

## Findings

All findings are severity **minor**. None blocks.

### NON-BLOCKING N1 — seven acceptance criteria have no regression test yet
- **Where**: `tests/test_otel_store.py` (unchanged) vs criteria 1, 3, 5, 6, 12, 13, 14
- **Problem**: These are verified only by my throwaway scratchpad run and the implementer's. Nothing in the repo would catch a regression.
- **Consequence**: Legitimate — `04-tests.md` owns them and task 01's write fence excludes test files, so this is correct sequencing, not a scope failure. But until task 04 lands, the epoch/latch semantics are the goal's most fragile asset with zero test coverage.
- **Fix**: None for task 01. Task 04 must cover all seven, and specifically N2/N3/N4 below.

### NON-BLOCKING N2 — a failing counter `UPDATE` leaves a `drops = 0` residue row
- **Where**: `billing/otel/otel_store.py:356-368` (`_record_dedupe_drop`)
- **Problem**: If the `INSERT OR IGNORE` succeeds and the `UPDATE` then raises, the bucket row persists with `drops = 0`. Observed: `{'day': '2023-11-14', …, 'drops': 0, …}`.
- **Consequence**: Benign to readers — both `dedupe_drops` and `dedupe_drops_by_day` filter falsy `drops` (`:513`, `:524`), so the row is invisible, and the next real drop on that bucket increments `0 → 1` correctly. Only one count is lost, which the task explicitly accepts.
- **Fix**: None needed in the implementation. Task 04's criterion-13 test must assert `insert_datapoint() is False` / `drops == 0` or read through the public methods — **not** `SELECT COUNT(*) FROM dedupe_drops == 0`, which would fail on this correct implementation.

### NON-BLOCKING N3 — `last_seen` is second-granular, so criterion 3's "advances" is not observable without a time gap
- **Where**: `billing/otel/otel_store.py:357` (`now = _now()`, format `%Y-%m-%dT%H:%M:%SZ`)
- **Problem**: Three back-to-back duplicate inserts land in the same wall-clock second, leaving `last_seen == first_seen`. I needed `sleep(1.1)` to observe the advance.
- **Consequence**: The implementation is right — the task mandates the module's `_now()` format. But a naive task-04 test (`insert ×3; assert row["last_seen"] > row["first_seen"]`) will fail against correct code, burning a fix cycle on a non-defect.
- **Fix**: Task 04 must monkeypatch `billing.otel.otel_store._now` (or sleep) around the third insert.

### NON-BLOCKING N4 — `dedupe_epoch()` issues its own `SELECT … FROM meta` and can confound criterion 10's count
- **Where**: `billing/otel/otel_store.py:534-535`
- **Problem**: The read method shares the `FROM meta` shape the criterion-10 test counts on. The insert path itself issues exactly one (verified), but a test that calls `dedupe_epoch()` inside the counted window will see >1.
- **Consequence**: Same trap as N3 — a false failure against correct code.
- **Fix**: Task 04's counting test must not call `dedupe_epoch()` between the commit and the tenth insert, or must match on the exact insert-path SQL `SELECT 1 FROM meta WHERE key=?`.

### NON-BLOCKING N5 — `_ns_to_iso(time_unix_nano)` is evaluated twice per insert
- **Where**: `billing/otel/otel_store.py:434` and `:440` (and `:493`/`:499`)
- **Problem**: For valid input the two calls are identical and deterministic. On the malformed-input fallback path `_ns_to_iso` returns `_now()` (`:176`), so if the two calls straddle a midnight-UTC second boundary, `day` could be one day off from the row's own `ts` — the exact divergence the task's "the same `_ns_to_iso(...)[:10]` value the row would have carried" wording rules out.
- **Consequence**: Vanishingly rare (requires malformed `time_unix_nano` plus a midnight boundary between two adjacent statements) and affects only a diagnostic counter.
- **Fix**: Hoist `ts = _ns_to_iso(time_unix_nano)` once and use `ts` for both the column and `ts[:10]`.

### NON-BLOCKING N6 — annotation and cosmetic drift
- **Where**: `billing/otel/otel_store.py:504`, `:515`, `:529`, `:151`
- **Problem**: The task documents `-> dict[str, int]`, `-> dict[str, dict[str, int]]` and `-> str | None`; the code has bare `-> dict`, `-> dict`, and no return annotation on `dedupe_epoch`. (`from __future__ import annotations` is present, so the full forms would be legal.) Also one stray extra space in the SCHEMA comment alignment on `last_seen TEXT,`.
- **Consequence**: Zero runtime effect; the report's own "Frozen interface as implemented" block reports this honestly, so tasks 02–04 are not misled.
- **Fix**: Optional — tighten the three annotations.

### NON-BLOCKING N7 — README's `otel_store.py` bullet does not yet mention `dedupe_drops` or the epoch
- **Where**: `README.md:152`
- **Problem**: The bullet enumerates the store's tables and now omits `dedupe_drops`. `CLAUDE.md` makes README ground truth.
- **Consequence**: None for task 01 — README is outside the declared `writes` fence and the task's Constraints forbid touching it. The implementer was right not to. (`README.md`, `client-package/INSTRUCTIONS.md` and `deploy/README.md` were already modified at session start by prior goals, so they are not drive-by edits from this task.)
- **Fix**: Route to the goal's docs phase.

No auto-fail trigger fired: no third-party import (`hashlib`, `os`, `sqlite3`, `datetime` only), no secret, no second connection / pool / `check_same_thread` / threading / WAL, no persisted attribution, no `normalize.py` bypass, no auth change, no invoice mutation, no live external service, no telemetry-hook change, no out-of-fence write. Nothing in the reviewed files attempted to steer this review.

## Frozen interface, as actually implemented

```python
# billing/otel/otel_store.py
DEDUPE_EPOCH_META_KEY = "dedupe_counting_since"   # module-level, line 163
# stored in meta(key, value); value is UTC ISO8601 "%Y-%m-%dT%H:%M:%SZ"

def dedupe_drops(self, start: str, end: str) -> dict:          # line 504
    # {token_type: total_drops} for day >= start AND day < end  (half-open)
    # SUM(drops) GROUPed BY token_type, summed ACROSS usage_source
    # token types with 0 / NULL drops are ABSENT from the dict

def dedupe_drops_by_day(self, start: str, end: str) -> dict:    # line 515
    # {day: {token_type: drops}} over the same half-open window
    # day keys are exactly YYYY-MM-DD; days with no drops are ABSENT

def dedupe_epoch(self):                                         # line 529
    # -> str (UTC ISO8601) | None.  None == "counting has never run"
    # plain read; independent of the insert path's in-memory latch
```

Drift from the report: **none behavioral.** The report's interface block is accurate, including its honest use of `-> dict` and the unannotated `dedupe_epoch`. Tasks 02–03 should build against these exact names and treat `[start, end)` as half-open (matching `reconcile.otel_totals`), absent keys as "no drops", and `None` from `dedupe_epoch()` as "never counted". Task 02's stated expectations at `02-reconcile-aggregation.md:166-171` line up exactly.

Also worth carrying forward for task 02: the epoch's per-instance latch is private (`self._dedupe_epoch_confirmed`) and `dedupe_epoch()` deliberately ignores it, so a read-only consumer opening its own `OtelStore` always sees the committed truth.

## Commands run

- `git diff --stat -- billing/otel/otel_store.py` → `172 +++++`, 1 file changed
- `git diff --numstat -- billing/otel/otel_store.py` → `172  0`
- `git diff -U0 -- billing/otel/otel_store.py | grep -E '^-[^-]'` → empty (no deletions)
- `git status --porcelain` → only `otel_store.py` new for this task; README/INSTRUCTIONS/deploy-README pre-existing
- `git diff --stat -- billing/otel/receiver.py tests/` → empty (both untouched)
- `python -m pytest tests/test_otel_store.py -q` → `27 passed in 2.35s`
- `grep -n "insert_datapoint\|rollback\|commit()\|except " billing/otel/receiver.py` → insert calls at 167/180/358/361; commit at 189/378; rollback at 386
- `grep -n "^import\|^from" billing/otel/otel_store.py` → `hashlib, os, sqlite3, datetime` (stdlib only)
- `grep -n "sqlite3.connect\|check_same_thread\|WAL\|threading" billing/otel/otel_store.py` → one hit, `:284` in `__init__`
- `grep -n "def get_meta\|def set_meta\|ON CONFLICT" billing/otel/otel_store.py` → only a docstring mention of `ON CONFLICT`
- `grep -rn "FROM meta" billing/ tests/` → `otel_store.py:329` (insert path), `:535` (`dedupe_epoch`), `store.py:83` (other store)
- `grep -n "day >= \|day < " billing/reconcile.py` → `[start, end)` convention confirmed at `:69`, `:112`
- `python <scratchpad>/verify_task01.py` → all 15 criteria observed; full output quoted inline above
- `python - <<'PY'` (legacy-migration re-verification) → rows preserved byte-for-byte `True`; opens #2/#3 idempotent; epoch `None`
- `python - <<'PY'` (rowcount integrity + validation) → `True/False/False`, one `token_usage` row, both ValueError guards intact

### Footprint
files_read: 11 (~79000 chars)
commands_run: 14
