MODEL: claude-sonnet-5
STATUS: completed

## What changed

All edits are in `billing/reconcile.py` (targeted-insertion, only file in the write fence):

- **Imports**: added `DEDUPE_EPOCH_META_KEY` from `billing.otel.otel_store` and `_day` from `billing.store` (alongside existing `Store`, `tokens as analytics_tokens`).
- **`_is_tagged(repo)`** (new helper): factors out the "truthy and not `'unknown'`" predicate so `otel_totals` and `otel_daily` cannot diverge on the tagged rule.
- **`otel_totals`**: extended additively with `"unmapped"` — `{token_type: tokens}` for every token_type outside `CANON`, built from the existing `GROUP BY resolved_repo, token_type` rows (no second query) by replacing the silent `continue` with accumulation into `unmapped`, using the literal `"(none)"` for NULL/empty token_type. `"captured"`/`"tagged"` shape and values unchanged for CANON rows.
- **`otel_by_surface`** (new): queries `token_usage` directly (comment documents it must switch to `resolved_view` if it ever grows a repo dimension), restricted to `CANON`, coalescing `usage_source`/`entrypoint`/`query_source` NULL/empty to `"(none)"`, returning `captured_total`.
- **`otel_daily`** (new): reads `resolved_repo` via `resolved_view("token_usage")`, groups by `substr(ts,1,10)` (already `YYYY-MM-DD`) + `resolved_repo` + `token_type`, applies `_is_tagged` for the `"tagged"` side — same predicate as `otel_totals`.
- **`analytics_claude_code_daily`** (new): single `usage_report` pass, normalizes each yielded `starting_at` with `_day()` (`[:10]`), accumulates into a materialized `dict` (not a generator).
- **`analytics_claude_code_totals`**: restructured into a thin wrapper that calls `analytics_claude_code_daily` once and sums; signature/shape unchanged.
- **`analytics_user_daily`** (new): same `LOWER(TRIM(email))` matching as `analytics_user_totals`, reads `user_cc_usage.day` (already truncated on write), returns possibly-empty dict, no `None` sentinel (that stays with `analytics_user_totals`).
- **`dedupe_drop_report`** (new): calls only `store.dedupe_epoch()`, `store.dedupe_drops()`, `store.dedupe_drops_by_day()`; derives `measurement` via the exact `none`/`full`/`partial` string-comparison rule; sets `counts_outside_measurement` whenever `by_type` is non-empty and `measurement != "full"`.
- **`run()`**: rewired to call `analytics_claude_code_daily(start, end)` instead of `analytics_claude_code_totals`, still inside the existing `try`/`except AnalyticsError`; sums the returned daily dict locally into `truth` before calling `_print_funnel`, unchanged otherwise.

No printing, no `sys.exit`, no `argparse` changes added by this task; `_print_funnel` untouched.

## Pre-change baseline (required by criterion 1)

Ran against the pre-change `billing/reconcile.py` (before any edits), fixture: 4 otlp rows for `s1`/`repoA` (input=100, output=50, unmapped `cacheCreation5m`=7, NULL token_type=3) on 2026-07-14, 1 transcript row for `s2`/`repo=unknown` (cacheRead=20, NULL query_source) on 2026-07-15, 1 otlp row for `s3`/`repoB` (cacheCreation=40) on 2026-07-16, queried over `2026-07-14`..`2026-07-17`:

```
{'captured': {'input': 100, 'output': 50, 'cacheRead': 20, 'cacheCreation': 40},
 'tagged':   {'input': 100, 'output': 50, 'cacheRead': 0,  'cacheCreation': 40}}
```

(First attempt used 2025 epoch seconds by mistake and produced all-zero output — corrected to 2026 timestamps before this baseline was captured.)

## Acceptance criteria

1. Post-change `otel_totals["captured"]`/`["tagged"]` on the same fixture reproduce the baseline exactly (see Verification output below: `captured` and `tagged` match the pasted baseline digit-for-digit) — satisfied.
2. `cacheCreation5m`=7 appears under `unmapped["cacheCreation5m"]`, and 7 is absent from every `captured` bucket — satisfied, see verify.py output.
3. NULL token_type (tokens=3) appears under `unmapped["(none)"]` without raising — satisfied.
4. `otel_by_surface`'s three dimension dicts each sum to `captured_total`=210, and `captured_total == sum(otel_totals(...)["captured"].values())` = 100+50+20+40=210 — satisfied, verified by construction and by the printed output.
5. OTLP rows -> `entrypoint["(none)"]`=190; transcript's NULL `query_source` -> `query_source["(none)"]`=20 — satisfied.
6. Σdaily == period for captured and tagged, every CANON bucket — explicitly asserted in verify.py and printed "Sigma daily == period OK".
7. Σdaily == period, truth side — NOT YET verified by me directly (task 04 owns `tests/test_reconcile.py`; requires Seam B AnalyticsClient mocking with `ANTHROPIC_ANALYTICS_TOKEN` set, which I did not construct as a full pytest test here). Implementation satisfies it structurally: `analytics_claude_code_totals` is a pure sum over `analytics_claude_code_daily`'s output, and `analytics_user_totals`/`analytics_user_daily` both scan the same `user_cc_usage` rows with identical accumulation logic.
8. Day-key literal: verified directly — a fake `usage_report` yielding `"2026-07-14T00:00:00Z"` produces key `"2026-07-14"` in `analytics_claude_code_daily`, and it compares equal (`==`) to `otel_daily`'s key for the same day. See verify.py output: "Day-key contract OK".
9. Exactly one `usage_report` call across `run()` — satisfied by construction (`run()` calls `analytics_claude_code_daily` exactly once and no longer calls `analytics_claude_code_totals`); NOT YET independently verified with a call-counting fake through `run()` itself (that's task 04's pytest with Seam B).
10. `analytics_claude_code_totals` returns the same summed CANON dict as before for a fixed fake payload — NOT YET verified with a pytest Seam B test; structurally guaranteed since it's a pure sum of `analytics_claude_code_daily`'s per-day buckets which use identical column mapping to the old code.
11. `AnalyticsError` from `usage_report` still propagates to `run()`'s existing except branch — satisfied by construction: `analytics_claude_code_daily` iterates the generator synchronously inside `run()`'s `try`, so the raise is not moved outside; NOT YET independently pytest-verified (task 04).
12. `analytics_claude_code_daily` returns a `dict`, not a generator — verified directly: `isinstance(daily_truth, dict)` asserted true in verify.py.
13. `measurement` cases — NOT YET independently pytest-verified across all five placements (task 04); logic implemented exactly per spec (`none`/`full`/`partial` via string comparison) and exercised once in verify.py (epoch written at fixture-creation time falls after `end`, producing `"none"` correctly).
14. `otel_daily`'s tagged reflecting resolved (not raw) repo — NOT YET independently verified with a raw-repo=`"unknown"` + timeline-resolves-elsewhere fixture; implementation reuses the identical `resolved_view("token_usage")` + `_is_tagged(r["repo"])` (where `r["repo"]` is `resolved_repo`) as `otel_totals`, which already relies on this mechanism.
15. No printing from any new function — satisfied by construction (no `print`/`sys.exit` in any added function); NOT YET verified with `capsys` (task 04).
16. `counts_outside_measurement` True/False cases — logic implemented per spec; NOT YET independently verified across all three required scenarios (task 04 pytest).

## Return shapes as implemented

- `otel_totals(store, start, end, emails=None) -> {"captured": {CANON: int}, "tagged": {CANON: int}, "unmapped": {token_type_or_"(none)": int}}`
- `otel_by_surface(store, start, end, emails=None) -> {"usage_source": {value: int}, "entrypoint": {value: int}, "query_source": {value: int}, "captured_total": int}` — NULL/empty coalesced to `"(none)"` in all three dimension dicts.
- `otel_daily(store, start, end, emails=None) -> {day: {"captured": {CANON: int}, "tagged": {CANON: int}}}`, day key = `YYYY-MM-DD` (from `substr(ts,1,10)`).
- `analytics_claude_code_daily(start, end) -> {day: {CANON: int}}`, day key = `YYYY-MM-DD` (via `_day()` truncation of the raw `starting_at`).
- `analytics_claude_code_totals(start, end) -> {CANON: int}` (unchanged shape).
- `analytics_user_daily(emails, start, end, analytics_db=None) -> {day: {CANON: int}}`, day key = `YYYY-MM-DD` (already truncated in `user_cc_usage.day`). Possibly empty.
- `analytics_user_totals(...)` unchanged: `(totals, matched_emails) | None`.
- `dedupe_drop_report(store, start, end) -> {"epoch": str|None, "epoch_day": str|None, "measurement": "none"|"partial"|"full", "counts_outside_measurement": bool, "by_type": {token_type: int}, "by_day": {day: {token_type: int}}}`.

## Verification

- `python -m pytest tests/test_otel_store.py -q` -> `27 passed in 2.06s`
- Test ladder rung 1 (new): skipped — this task adds no test files (task 04 owns `tests/test_reconcile.py`).
- Test ladder rung 2 (impacted): `python -m pytest tests/test_otel_store.py -q` -> pass (above). Rung 3 (`python -m pytest -q`) was **not** run, per instructions.
- Scratchpad evidence (verbatim, from `verify.py` — mixed otlp+transcript fixture with unmapped type, NULL token_type, NULL query_source, NULL entrypoint, three days):

```
otel_totals: {'captured': {'input': 100, 'output': 50, 'cacheRead': 20, 'cacheCreation': 40}, 'tagged': {'input': 100, 'output': 50, 'cacheRead': 0, 'cacheCreation': 40}, 'unmapped': {'(none)': 3, 'cacheCreation5m': 7}}
otel_by_surface: {'usage_source': {'otlp': 190, 'transcript': 20}, 'entrypoint': {'(none)': 190, 'claude-desktop': 20}, 'query_source': {'main': 150, 'subagent': 40, '(none)': 20}, 'captured_total': 210}
otel_daily: {'2026-07-14': {'captured': {'input': 100, 'output': 50, 'cacheRead': 0, 'cacheCreation': 0}, 'tagged': {'input': 100, 'output': 50, 'cacheRead': 0, 'cacheCreation': 0}}, '2026-07-15': {'captured': {'input': 0, 'output': 0, 'cacheRead': 20, 'cacheCreation': 0}, 'tagged': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheCreation': 0}}, '2026-07-16': {'captured': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheCreation': 40}, 'tagged': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheCreation': 40}}}
dedupe_drop_report: {'epoch': '2026-09-16T14:44:41Z', 'epoch_day': '2026-09-16', 'measurement': 'none', 'counts_outside_measurement': False, 'by_type': {}, 'by_day': {}}
Sigma daily == period OK for captured and tagged, all CANON buckets
analytics_claude_code_daily (fake starting_at 2026-07-14T00:00:00Z): {'2026-07-14': {'input': 10, 'output': 5, 'cacheRead': 0, 'cacheCreation': 0}}
Day-key contract OK: '2026-07-14' (truth) == '2026-07-14' (otel_daily)
ALL CHECKS PASSED
```

- Day-key evidence: shown above — fake `usage_report` yielding `starting_at="2026-07-14T00:00:00Z"` produced key `"2026-07-14"` from `analytics_claude_code_daily`, and `"2026-07-14" == "2026-07-14"` against `otel_daily`'s key for the same day. `isinstance(daily_truth, dict)` also asserted true.

## Deviations / concerns

- Criteria 7, 9, 10, 11, 13, 14, 15, 16 require **Seam B** pytest tests (`AnalyticsClient` monkeypatching with `ANTHROPIC_ANALYTICS_TOKEN` set, `capsys`, multiple fixture placements) that are explicitly task 04's write fence (`tests/test_reconcile.py`), not mine (`billing/reconcile.py` only). I verified the underlying logic directly via scratchpad scripts (not pytest) wherever practical without touching test files, and structurally reasoned through the rest. These are marked NOT YET above and should be confirmed once task 04 lands.
- `DEDUPE_EPOCH_META_KEY` is imported per the requirement ("import rather than re-declare") but is only referenced in a docstring, not in executable code — `dedupe_epoch()` already resolves the meta key internally, so there was no place in `reconcile.py` that needed the raw string value. Flagging this as a judgment call rather than a silent omission.
- Everything else in the spec (day-key contract, unmapped handling, surface breakdown, per-day aggregation for both otel and analytics paths, single-usage_report-pass restructuring, dedupe_drop_report) was implementable exactly as written — no conflicts found.

### Footprint
files_read: 8 (~35000 chars)
commands_run: 9
