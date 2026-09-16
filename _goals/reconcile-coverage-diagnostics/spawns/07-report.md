VERDICT: PASS (with notes)
MODEL: claude-opus-5 (as reported by the harness)

## Summary

The implementation is correct, and I verified all sixteen acceptance criteria by direct observation — including the eight the implementer left "NOT YET". The two highest-risk items both hold under live test: `analytics_claude_code_daily` truncates the raw RFC3339 `starting_at` so its key is byte-identical to `otel_daily`'s for the same day (union size 2, not 3 — no phantom outage rows), and `otel_daily`'s `tagged` is driven entirely by `resolved_repo`, so inserting a late `session_repo_timeline` entry moved 70 tokens from untagged to tagged with the raw `repo` column still reading `unknown`. Rather than trust the implementer's pasted baseline, I extracted the pre-change `otel_totals` and `analytics_claude_code_totals` verbatim from git HEAD and ran both against the same fixtures: outputs are identical, so the 24 deletions are a restructure, not a behavior change. Biggest residual risk is not in this code but downstream: nothing here is covered by a committed pytest file until task 04 lands, so every guarantee I observed is currently unpinned against regression.

## Acceptance criteria

1. **VERIFIED** — not self-compared. Ran a verbatim copy of HEAD's `otel_totals` beside the new one on one fixture: `captured {input:111, output:50, cacheRead:20, cacheCreation:40}` and `tagged {111, 50, 0, 40}` identical, and identical again on the email-filtered path.
2. **VERIFIED** — `unmapped['cacheCreation5m'] == 7`; `captured` sums to 221, which is exactly the CANON-only total, so 7 is in no bucket.
3. **VERIFIED** — NULL `token_type` (3 tokens) → `unmapped['(none)'] == 3`, no raise; spelling is `(none)`, never `(null)`.
4. **VERIFIED** — `usage_source`/`entrypoint`/`query_source` each sum to 221 == `captured_total` == `sum(otel_totals[...]["captured"].values())`. Fixture included NULL `query_source`, NULL `entrypoint`, and empty-string dimensions.
5. **VERIFIED** — NULL-entrypoint OTLP rows land in `entrypoint['(none)'] == 201`; the NULL `query_source` row in `query_source['(none)'] == 31`; an empty-string `usage_source` row in `usage_source['(none)'] == 11`.
6. **VERIFIED** — three-day fixture, Σdaily == period for all four CANON buckets in both `captured` and `tagged`; out-of-window rows at `2026-07-13` and `2026-07-17` correctly excluded (half-open).
7. **VERIFIED** (implementer: NOT YET) — Seam B, org side: Σdaily `117/206/301/11` == `analytics_claude_code_totals`. Pure-SQLite user side: Σdaily `22/33/44/11` == `analytics_user_totals`.
8. **VERIFIED** — fake yielding `"2026-07-14T00:00:00Z"` produced key `"2026-07-14"`; `==` against `otel_daily`'s key for the same day; no `T` in any key; two rows sharing a day accumulated (17/6/1/9) rather than overwriting.
9. **VERIFIED** (NOT YET) — Seam B call-counting fake through `run()`: exactly **1** `usage_report` call, 3 payload iterations. `run()`'s body contains no reference to `analytics_claude_code_totals`.
10. **VERIFIED** (NOT YET) — new `analytics_claude_code_totals` == verbatim HEAD implementation on the same fake payload: `{input:117, output:206, cacheRead:301, cacheCreation:11}`, same key order; `total_tokens` never read.
11. **VERIFIED** (NOT YET) — with `ANTHROPIC_ANALYTICS_TOKEN` set and the raise planted inside the patched `usage_report` generator (a flag proves it was reached, so the constructor cannot be the origin): `run()` printed "Could not reach Analytics API" plus the unchanged revoked-token hint, printed **no** funnel, and did not let `AnalyticsError` escape.
12. **VERIFIED** — `type(result) is dict`; the fake's iteration counter already read 3 on return, proving the pass completed eagerly inside `run()`'s `try`.
13. **VERIFIED** (NOT YET) — all five placements: `epoch is None`→none, `epoch_day == end`→none, `epoch_day > end`→none, `epoch_day < start`→full, `epoch_day == start`→**partial**, `start < epoch_day < end`→partial.
14. **VERIFIED** (NOT YET) — the query-time-attribution invariant, tested in both directions. Raw `repo='unknown'` + a timeline entry resolving to `repoZ`: `tagged["input"]` went 0 → 70 while the stored `repo` column still read `unknown`. Raw `repo='repoQ'` + a timeline resolving to `unknown`: `tagged["output"]` went 5 → 0. `otel_totals` agreed with `otel_daily` after both corrections.
15. **VERIFIED** (NOT YET) — stdout and stderr both empty around direct calls to all seven added/changed aggregation functions against fixtures with rows.
16. **VERIFIED** (NOT YET) — replayed-export route (drops dated `2026-07-15`, epoch `2026-07-20`): `measurement="none"`, `by_type={'input':4}` not suppressed, flag `True`. Interrupted-write route (epoch absent, drops present): flag `True`. Fully-counted window: `measurement="full"`, `by_type={'output':9}`, flag `False`. Also confirmed `partial`+drops→`True` and that the flag is a real `bool`, not a truthy dict.

## Verification points

1. **PASS** — day-key contract. All four day-producing sources yield `YYYY-MM-DD`: `otel_daily` (`substr(ts,1,10)`), `analytics_claude_code_daily` (`_day(starting_at)`), `analytics_user_daily` (`user_cc_usage.day`), `dedupe_drop_report["by_day"]`. Truth and captured keys compare equal; observed, not inferred.
2. **PASS** — all four Σdaily == period identities hold, including the two the implementer only reasoned about.
3. **PASS** — exactly one `usage_report` pass via Seam B through `run()`.
4. **PASS** — `AnalyticsError` from `usage_report` reaches the existing `except` with no funnel; token was set so the raise provably did not come from the constructor.
5. **PASS** — real `dict`, counter advanced on return.
6. **PASS** — additive compatibility proved against verbatim HEAD code for both `otel_totals` and `analytics_claude_code_totals`; `analytics_user_totals` still returns `(totals, matched) | None` with its `None` sentinel intact. Every deletion is a restructure.
7. **PASS** — `_is_tagged` is defined once (`reconcile.py:55`) and called at `:99` (`otel_totals`) and `:181` (`otel_daily`). No second `!= "unknown"` comparison survives anywhere in the file; the old inline predicate was removed by the diff.
8. **PASS** — see criterion 14 above. Both functions read `resolved_repo` from `resolved_view("token_usage")`; the raw `repo` column is never read for tagging, and nothing is persisted.
9. **PASS** — the required comment is present (`reconcile.py:116-118`, "must never grow a repo dimension without switching to `resolved_view`"), and skipping the view did not change the row universe: `captured_total` equalled `sum(otel_totals[...]["captured"].values())` on both the mixed fixture and the timeline-corrected one.
10. **PASS** — five placements plus three `counts_outside_measurement` scenarios, epoch manipulated directly in tmp stores. Also confirmed a drop generated through task 01's real `insert_datapoint` duplicate path is reported.
11. **PASS** — no added function prints; `run()`/`_print_funnel` rendering untouched.
12. **PASS** — `python -m pytest tests/test_otel_store.py -q` → `27 passed in 2.55s`. Full suite deliberately not run.

**Scope/fence:** clean. `git diff --name-only` shows `billing/reconcile.py` as the only in-fence file touched. `billing/otel/otel_store.py` is task 01's already-evaluated work; `README.md`, `deploy/README.md`, and `client-package/INSTRUCTIONS.md` all carry mtime `2026-09-15T21:01Z`, a day before this implementer's run (`billing/reconcile.py` at `2026-09-16T14:43Z`), and their content is about VS Code/desktop OTEL, unrelated to this task. No auto-fail trigger fired: standard library only, no secret, no second connection or threading, no persisted attribution, no weakened auth, no live external call (`usage_report` patched on the class throughout).

## Findings

### NON-BLOCKING An empty-string epoch value crashes `dedupe_drop_report`
- **Where**: `billing/reconcile.py:272-274` — `epoch_day = epoch[:10] if epoch else None` followed by `if epoch is None or epoch_day >= end`.
- **Problem**: for `epoch == ""`, the first branch computes `epoch_day = None` (empty string is falsy) but the guard tests `epoch is None`, which is `False`, so it evaluates `None >= end`. Observed: `TypeError: '>=' not supported between instances of 'NoneType' and 'str'`.
- **Consequence**: none for any reachable input. `_ensure_dedupe_epoch` is the only writer of that meta key and writes `_now()`, which is never empty; `Store.set_meta` returns early on `None`. The task contract types `epoch` as `str | None`, so `""` is outside the declared domain, and no requirement or acceptance criterion names it. **Downgraded to minor on that basis** — unreachable in-repo and behavior-neutral — not dropped.
- **Fix**: change the guard to `if not epoch or epoch_day >= end`, which makes the falsy-epoch branch consistent with the `epoch_day` computation one line above.

### NON-BLOCKING `DEDUPE_EPOCH_META_KEY` is an unused import
- **Where**: `billing/reconcile.py:29` (import), referenced only in prose at `:259`.
- **Problem**: no executable reference. Flagged accurately by the implementer.
- **Consequence**: cosmetic only. There is no linter configured in this repo (no `.flake8`, `ruff.toml`, `setup.cfg`, `pyproject.toml`, `tox.ini`, or `.github/workflows`), so F401 is inert here.
- **Fix**: see Disclosed items.

### Note for task 03 (not a defect)
`analytics_user_daily` and `analytics_user_totals` each open and close their own `Store`, so a task-03 renderer that calls both makes two sequential opens of `analytics.db` and two passes over the same rows. This is the split the task file mandated (the `None` sentinel stays with `totals` and must not be duplicated), and it is sequential — no pool, no threading, no single-host violation. Task 03 can sum `analytics_user_daily`'s output locally for the period figure, the same way `run()` now does on the org path.

## Disclosed items

**Unused `DEDUPE_EPOCH_META_KEY` import — ruling: drop it.** There is no legitimate executable use available. Requirement 4 mandates going through task 01's three frozen read methods, and `dedupe_epoch()` resolves the meta key internally, so `reconcile.py` never handles the string at all. Requirement 4's actual purpose — "import ... rather than re-declaring the string" — is a conditional: it prevents a hardcoded duplicate of `"dedupe_counting_since"`. With nothing to hardcode, that purpose is met by the docstring reference alone, which names the constant in prose and needs no import. Keeping a purely decorative import is the weaker of the two options. This is non-blocking either way, and requirement 4's wording should be softened in a future revision so the next implementer is not pushed into the same dead import.

**Cross-module `_day` import — ruling: agree, it is the better of the two permitted options.** Requirement 0 exists because the truth-side day key must match what `store._day()` already wrote into `user_cc_usage.day`. That is a shared invariant across two modules, so a single definition is the correct expression of it: restating the one-liner would let the two truncations drift silently, which is precisely the disjoint-union failure requirement 0 warns about. The `_` prefix is a weaker signal than the cross-module coupling is a benefit here, and `store._day` is already imported cross-module by `ingest.py`'s write path, so this matches established practice. One concrete hazard the implementer avoided and deserves credit for: HEAD's `analytics_claude_code_totals` used `_day` as its loop variable (`for _day, row in client.usage_report(...)`). Importing the function while keeping that name would have shadowed it and produced either a `str is not callable` crash or a silently wrong key. The loop variable was renamed to `starting_at`; I grepped the file and `_day` now appears only at the import and at its single call site.

## Return shapes, as actually implemented

No drift from the report — every shape below I obtained by calling the function, not by reading its docstring.

- `otel_totals(store, start, end, emails=None)` → `{"captured": {CANON: int}, "tagged": {CANON: int}, "unmapped": {token_type: int}}`. `captured`/`tagged` always carry all four CANON keys (zeros included); `unmapped` omits zero-token types and is `{}` when nothing was unmapped.
- `otel_by_surface(store, start, end, emails=None)` → `{"usage_source": {value: int}, "entrypoint": {value: int}, "query_source": {value: int}, "captured_total": int}`. NULL **and** empty-string coalesce to `"(none)"` in all three dimensions.
- `otel_daily(store, start, end, emails=None)` → `{"YYYY-MM-DD": {"captured": {CANON: int}, "tagged": {CANON: int}}}`. Only days with rows appear; both inner dicts always carry all four CANON keys.
- `analytics_claude_code_daily(start, end)` → `{"YYYY-MM-DD": {CANON: int}}`, a materialized `dict`.
- `analytics_claude_code_totals(start, end)` → `{CANON: int}` (unchanged).
- `analytics_user_daily(emails, start, end, analytics_db=None)` → `{"YYYY-MM-DD": {CANON: int}}`, possibly `{}`; never `None`.
- `analytics_user_totals(...)` → `(totals, matched_emails) | None` (unchanged).
- `dedupe_drop_report(store, start, end)` → exactly the six keys `{"epoch", "epoch_day", "measurement", "counts_outside_measurement", "by_type", "by_day"}` in every one of the six epoch placements I tested.

One observation for task 03's renderer: in `otel_totals["unmapped"]`, a NULL `token_type`, an empty-string `token_type`, and a literal `token_type` of `"(none)"` all collapse into the single `"(none)"` key (observed: 3 + 5 + 7 = 15). That collapse is what requirement 1 specifies by choosing a stable literal, so it is a spec decision rather than a defect — but task 03 should not render `"(none)"` as though it can only mean "field was absent".

## Commands run

- `git diff --stat -- billing/reconcile.py` → `1 file changed, 223 insertions(+), 24 deletions(-)`
- `git diff -- billing/reconcile.py` → reviewed all 24 deletions; all restructure
- `git status --porcelain` / `git diff --name-only` → only `billing/reconcile.py` in fence; doc files pre-date the run
- `python -m pytest tests/test_otel_store.py -q` → `27 passed in 2.55s`
- `grep -n "_is_tagged|!= 'unknown'|print(|argparse|DEDUPE_EPOCH_META_KEY" billing/reconcile.py` → single shared predicate; no print in any added function
- `python .../scratchpad/ev_otel.py` → OTEL side; every assertion OK (two initial FAILs were my own mis-summed fixture expectations, corrected against the printed totals: `captured_total` is 221, the exact CANON sum, and `entrypoint['(none)']` is 201)
- `python .../scratchpad/ev_analytics.py` → Seam B, truth-side identities, call count 1, error origin, all six measurement placements, all three flag scenarios; only FAIL was my own output-text assertion
- `python .../scratchpad/ev_edges.py` → `run()` truth TOTAL prints `635` (= 117+206+301+11); empty-string epoch raises `TypeError`; `analytics_user_daily([])` → `{}` vs `analytics_user_totals([])` → `None` (parity with pre-existing behavior, no new failure mode)
- `grep -rn` for external callers + mtime check + lint-config check → `analytics_claude_code_totals` has no in-repo caller outside `reconcile.py`; no linter configured; no `data/` pollution, `git status` unchanged after my scripts

### Footprint
files_read: 10 (~106000 chars)
commands_run: 9
