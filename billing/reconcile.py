"""Reconcile OTEL-captured Claude Code usage against the authoritative
Analytics API totals, to quantify coverage and the attribution gap.

The Analytics API knows the TRUE org-wide claude_code token totals (every user,
every machine). The OTEL pipeline only sees usage from machines that are
actually emitting telemetry, and can only bill usage that carries a repo tag.
Comparing the two answers: "what fraction of real usage are we capturing and
attributing?"

    python -m billing.reconcile --start 2026-07-14 --end 2026-07-15

Coverage funnel (tokens):
    Analytics truth  ── org-wide claude_code (authoritative)
      └ OTEL captured        gap = telemetry never received (machines not emitting)
          └ repo-tagged      gap = received but no repo tag (wrapper missing)

A repo tag is all that's needed to bill now — usage bills to the repo it was
done in — so repo-tagged usage IS billable (no separate client-mapping step).

Token types are mapped between the two APIs (they name them differently).
"""

from __future__ import annotations

import argparse
import textwrap

from .analytics_client import AnalyticsClient, AnalyticsError
from .otel.attribute import resolved_view
from .otel.otel_store import OtelStore
from .store import Store, _day, tokens as analytics_tokens

# canonical token buckets used on both sides
CANON = ["input", "output", "cacheRead", "cacheCreation"]

# ---- output width -------------------------------------------------------
# Column widths for every table. RULE_WIDTH is the module-level width
# constant used for every "=" / "-" rule and for prose wrapping: it is sized
# to the WIDEST line in the feature across every flag combination, which is
# the six-column --daily row (day + truth/captured/tagged ftok+exact pairs +
# two pct columns) -- not the widest table in the default output. The
# default invocation's narrower tables therefore sit inside intentionally
# wider rules; that is correct and expected.
LABEL_W = 18       # row-label column (token type / surface value / etc.)
FT_COL = 10        # ftok() column
EXACT_COL = 15     # exact, thousands-separated integer column beside it
PCT_COL = 9        # percentage column
PAIR_W = FT_COL + 1 + EXACT_COL  # "<ftok> <exact,int>" combined width
RULE_WIDTH = 2 + 10 + PAIR_W * 3 + PCT_COL * 2  # the --daily row's width


def ftok(n) -> str:
    n = n or 0
    if n >= 1_000_000_000:
        return f"{n/1e9:.2f}B"
    if n >= 1_000_000:
        return f"{n/1e6:.1f}M"
    if n >= 1_000:
        return f"{n/1e3:.1f}K"
    return str(int(n))


def pct(part, whole) -> str:
    return f"{(100.0 * part / whole):.2f}%" if whole else "n/a"


def _pair(n) -> str:
    """`ftok()` beside its exact, thousands-separated integer, at a fixed
    combined width (`PAIR_W`) so every table's columns line up regardless of
    magnitude."""
    n = n or 0
    return f"{ftok(n):>{FT_COL}} {f'{int(n):,}':>{EXACT_COL}}"


def _wrap(text: str) -> list[str]:
    """Wrap prose to `RULE_WIDTH` so every printed line -- not just table
    rows -- respects the module-wide width constant."""
    return textwrap.wrap(text, width=RULE_WIDTH) or [""]


def _normalize_emails(emails: list[str]) -> list[str]:
    return [e.strip().lower() for e in emails]


def _is_tagged(repo) -> bool:
    """A row counts as repo-tagged when its resolved repo is truthy and not
    the literal 'unknown'. `otel_totals` and `otel_daily` must apply this
    identical rule -- factored out here so the two cannot diverge."""
    return bool(repo) and repo != "unknown"


def otel_totals(store: OtelStore, start, end, emails: list[str] | None = None) -> dict:
    """OTEL captured tokens in [start, end), split into captured / tagged /
    unmapped.

    A repo tag is sufficient to bill (usage bills to the repo), so repo-tagged
    tokens are exactly the billable tokens. Uses `resolved_repo` (attribute.py's
    as-of join against session_repo_timeline) rather than the raw `repo` column,
    so this matches what bill.py actually bills -- not just the frozen launch-time
    wrapper tag. `emails`, when given, scopes to those (case/whitespace-insensitive)
    OTEL-side user_email values.

    `"unmapped"` is `{token_type: tokens}` for every token_type present in the
    window that is not one of CANON -- built from the same GROUP BY rows as
    captured/tagged (no second query). A NULL/empty token_type is reported
    under the stable literal key "(none)". Token types with no tokens are
    absent from the dict."""
    sql = f"""SELECT resolved_repo AS repo, token_type, SUM(tokens) tok
              FROM ({resolved_view("token_usage")})
              WHERE substr(ts,1,10) >= ? AND substr(ts,1,10) < ?"""
    params: list = [start, end]
    if emails:
        norm = _normalize_emails(emails)
        sql += f" AND LOWER(TRIM(user_email)) IN ({','.join('?' * len(norm))})"
        params.extend(norm)
    sql += " GROUP BY resolved_repo, token_type"
    rows = store.db.execute(sql, params).fetchall()
    captured = {k: 0 for k in CANON}
    tagged = {k: 0 for k in CANON}
    unmapped: dict = {}
    for r in rows:
        tok = r["tok"] or 0
        tt = r["token_type"]
        if tt not in CANON:
            key = tt if tt else "(none)"
            unmapped[key] = unmapped.get(key, 0) + tok
            continue
        captured[tt] += tok
        if _is_tagged(r["repo"]):
            tagged[tt] += tok
    return {"captured": captured, "tagged": tagged, "unmapped": unmapped}


def otel_by_surface(store: OtelStore, start, end, emails: list[str] | None = None) -> dict:
    """Share of CANON captured tokens by usage_source / entrypoint / query_source.

    Restricted to CANON token types with the identical date window and email
    filter as `otel_totals`, so each dimension sums to `captured_total` (which
    equals `sum(otel_totals(...)["captured"].values())`). Unmapped types are
    reported by `otel_totals` and never mixed in here. Every dimension
    coalesces NULL and empty-string to the literal "(none)" -- entrypoint is
    NULL for every OTLP row, and query_source is nullable in the schema even
    though both current writers coalesce it.

    This function reads no repo column, so it queries `token_usage` directly
    rather than through `resolved_view("token_usage")` -- paying for
    attribute.py's correlated subqueries would buy nothing here. It must never
    grow a repo dimension without switching to `resolved_view`.
    """
    sql = """SELECT usage_source, entrypoint, query_source, token_type, SUM(tokens) tok
             FROM token_usage
             WHERE substr(ts,1,10) >= ? AND substr(ts,1,10) < ?"""
    params: list = [start, end]
    if emails:
        norm = _normalize_emails(emails)
        sql += f" AND LOWER(TRIM(user_email)) IN ({','.join('?' * len(norm))})"
        params.extend(norm)
    sql += " GROUP BY usage_source, entrypoint, query_source, token_type"
    rows = store.db.execute(sql, params).fetchall()
    usage_source: dict = {}
    entrypoint: dict = {}
    query_source: dict = {}
    captured_total = 0
    for r in rows:
        if r["token_type"] not in CANON:
            continue
        tok = r["tok"] or 0
        captured_total += tok
        us = r["usage_source"] or "(none)"
        ep = r["entrypoint"] or "(none)"
        qs = r["query_source"] or "(none)"
        usage_source[us] = usage_source.get(us, 0) + tok
        entrypoint[ep] = entrypoint.get(ep, 0) + tok
        query_source[qs] = query_source.get(qs, 0) + tok
    return {
        "usage_source": usage_source,
        "entrypoint": entrypoint,
        "query_source": query_source,
        "captured_total": captured_total,
    }


def otel_daily(store: OtelStore, start, end, emails: list[str] | None = None) -> dict:
    """Per-UTC-day {"captured": {CANON: int}, "tagged": {CANON: int}}, for
    every day with rows in [start, end). Same half-open window and email
    filter as `otel_totals`, and reads `resolved_repo` via
    `resolved_view("token_usage")` the same way. `"tagged"` applies the
    identical `_is_tagged` predicate `otel_totals` uses, so the two cannot
    diverge. Day key is `substr(ts,1,10)` -- already `YYYY-MM-DD`."""
    sql = f"""SELECT substr(ts,1,10) AS day, resolved_repo AS repo, token_type,
                     SUM(tokens) tok
              FROM ({resolved_view("token_usage")})
              WHERE substr(ts,1,10) >= ? AND substr(ts,1,10) < ?"""
    params: list = [start, end]
    if emails:
        norm = _normalize_emails(emails)
        sql += f" AND LOWER(TRIM(user_email)) IN ({','.join('?' * len(norm))})"
        params.extend(norm)
    sql += " GROUP BY day, resolved_repo, token_type"
    rows = store.db.execute(sql, params).fetchall()
    out: dict = {}
    for r in rows:
        tt = r["token_type"]
        if tt not in CANON:
            continue
        day = r["day"]
        bucket = out.setdefault(
            day, {"captured": {k: 0 for k in CANON}, "tagged": {k: 0 for k in CANON}})
        tok = r["tok"] or 0
        bucket["captured"][tt] += tok
        if _is_tagged(r["repo"]):
            bucket["tagged"][tt] += tok
    return out


def analytics_claude_code_daily(start, end) -> dict:
    """Authoritative org-wide claude_code tokens, per UTC day, in canonical
    buckets: {day: {CANON: int}}. Makes exactly ONE `usage_report` pass and
    returns a fully materialized dict (never a generator) -- `run()` relies on
    this to keep the HTTP call (and its AnalyticsError) inside its existing
    try/except.

    `usage_report` yields `bucket.get("starting_at")` verbatim from the API --
    an RFC3339 timestamp, not a date -- so the day key is normalized with the
    same `_day()` ([:10]) truncation `billing.store` uses on write, making it
    compare equal to `otel_daily`'s day key for the same day."""
    client = AnalyticsClient()
    out: dict = {}
    for starting_at, row in client.usage_report(start, end, products=["claude_code"]):
        day = _day(starting_at)
        t = analytics_tokens(row)
        bucket = out.setdefault(day, {k: 0 for k in CANON})
        bucket["input"] += t["uncached_input"]
        bucket["output"] += t["output"]
        bucket["cacheRead"] += t["cache_read"]
        bucket["cacheCreation"] += t["cache_creation_1h"] + t["cache_creation_5m"]
    return out


def analytics_claude_code_totals(start, end) -> dict:
    """Authoritative org-wide claude_code tokens, in canonical buckets.

    Thin public wrapper over `analytics_claude_code_daily`'s single
    `usage_report` pass -- kept for external callers. `run()` calls
    `analytics_claude_code_daily` directly and sums locally instead, so the
    org-wide path never makes a second pass."""
    daily = analytics_claude_code_daily(start, end)
    out = {k: 0 for k in CANON}
    for day_totals in daily.values():
        for k in CANON:
            out[k] += day_totals[k]
    return out


def analytics_user_daily(emails: list[str], start: str, end: str,
                          analytics_db: str | None = None) -> dict:
    """Per-UTC-day {day: {CANON: int}} truth for specific users, straight from
    `user_cc_usage` (`day` was already truncated by `store._day()` on write).
    Same `LOWER(TRIM(email)) IN (...)` matching as `analytics_user_totals`.
    Returns a possibly-empty dict; the None-means-"run ingest first" signal
    stays with `analytics_user_totals` and is not duplicated here."""
    norm = _normalize_emails(emails)
    store = Store(analytics_db) if analytics_db else Store()
    placeholders = ",".join("?" * len(norm))
    rows = store.db.execute(
        f"""SELECT day, uncached_input, cache_creation_1h, cache_creation_5m,
                   cache_read, output
            FROM user_cc_usage
            WHERE day >= ? AND day < ? AND LOWER(TRIM(email)) IN ({placeholders})""",
        [start, end, *norm]).fetchall()
    store.close()
    out: dict = {}
    for r in rows:
        bucket = out.setdefault(r["day"], {k: 0 for k in CANON})
        bucket["input"] += r["uncached_input"] or 0
        bucket["output"] += r["output"] or 0
        bucket["cacheRead"] += r["cache_read"] or 0
        bucket["cacheCreation"] += (r["cache_creation_1h"] or 0) + (r["cache_creation_5m"] or 0)
    return out


def dedupe_drop_report(store: OtelStore, start: str, end: str) -> dict:
    """Dedupe-drop diagnostics for [start, end), built only from task 01's
    three frozen read methods (`dedupe_epoch`, `dedupe_drops`,
    `dedupe_drops_by_day`) -- never queries `dedupe_drops` directly.

    `"measurement"` ("none" | "partial" | "full") describes how much of the
    window counting actually covered, derived from the epoch day
    (`DEDUPE_EPOCH_META_KEY`'s value, truncated to YYYY-MM-DD) compared
    against the window via plain string comparison (correct for YYYY-MM-DD):
      - "none":    epoch is None, or epoch_day >= end
      - "full":    epoch_day < start
      - "partial": otherwise (start <= epoch_day < end)

    `"counts_outside_measurement"` is True whenever `by_type` is non-empty
    AND measurement != "full" -- this state is reachable both by design (a
    replayed old export counts drops dated entirely before the epoch) and by
    interruption (a rolled-back first epoch write leaves epoch absent while
    later committed drops persist). Either way, a non-empty `by_type` is
    NEVER suppressed on account of measurement; this flag lets the caller
    qualify a real count instead of hiding it."""
    epoch = store.dedupe_epoch()
    epoch_day = epoch[:10] if epoch else None
    if not epoch or epoch_day >= end:
        measurement = "none"
    elif epoch_day < start:
        measurement = "full"
    else:
        measurement = "partial"
    by_type = store.dedupe_drops(start, end)
    by_day = store.dedupe_drops_by_day(start, end)
    counts_outside_measurement = bool(by_type) and measurement != "full"
    return {
        "epoch": epoch,
        "epoch_day": epoch_day,
        "measurement": measurement,
        "counts_outside_measurement": counts_outside_measurement,
        "by_type": by_type,
        "by_day": by_day,
    }


def analytics_user_totals(emails: list[str], start: str, end: str,
                           analytics_db: str | None = None):
    """Truth side scoped to specific users. Returns None if zero rows matched
    across all supplied emails, else (totals, matched_emails) where totals is a
    pure CANON dict and matched_emails is the subset of the (normalized) input
    that matched at least one row."""
    norm = _normalize_emails(emails)
    store = Store(analytics_db) if analytics_db else Store()
    placeholders = ",".join("?" * len(norm))
    rows = store.db.execute(
        f"""SELECT email, uncached_input, cache_creation_1h, cache_creation_5m,
                   cache_read, output
            FROM user_cc_usage
            WHERE day >= ? AND day < ? AND LOWER(TRIM(email)) IN ({placeholders})""",
        [start, end, *norm]).fetchall()
    store.close()
    if not rows:
        return None
    totals = {k: 0 for k in CANON}
    matched: set[str] = set()
    for r in rows:
        matched.add(r["email"].strip().lower())
        totals["input"] += r["uncached_input"] or 0
        totals["output"] += r["output"] or 0
        totals["cacheRead"] += r["cache_read"] or 0
        totals["cacheCreation"] += (r["cache_creation_1h"] or 0) + (r["cache_creation_5m"] or 0)
    return totals, sorted(matched)


def run(start: str, end: str, db: str | None = None,
        emails: list[str] | None = None, analytics_db: str | None = None,
        *, by_surface: bool = False, daily: bool = False):
    store = OtelStore(db) if db else OtelStore()

    banner = f"RECONCILIATION  period {start} -> {end}  (product=claude_code)"
    if emails:
        banner += f"  emails={','.join(emails)}"
    print("=" * RULE_WIDTH)
    print(banner)
    print("=" * RULE_WIDTH)

    if emails:
        normalized = _normalize_emails(emails)
        result = analytics_user_totals(emails, start, end, analytics_db)
        if result is None:
            print(f"\n!! No analytics rows for {emails} in {start}..{end}.")
            print(f"   Run: python -m billing.ingest --start {start} --end {end}")
            store.close()
            return
        truth, matched_emails = result
        unmatched = sorted(set(normalized) - set(matched_emails))
        if unmatched:
            print(f"\n!! no analytics rows matched: {', '.join(unmatched)}")
        otel = otel_totals(store, start, end, emails=emails)
        captured, tagged, unmapped = otel["captured"], otel["tagged"], otel["unmapped"]
        dd = dedupe_drop_report(store, start, end)
        _print_funnel(truth, captured, tagged, suppress_synthetic_note=True)
        _print_unmapped(unmapped)
        _print_dedupe(dd, daily=daily)
        if by_surface:
            _print_by_surface(otel_by_surface(store, start, end, emails=emails))
        if daily:
            truth_daily = analytics_user_daily(emails, start, end, analytics_db)
            cap_daily = otel_daily(store, start, end, emails=emails)
            _print_daily(truth_daily, cap_daily)
        store.close()
        return

    try:
        truth_daily_full = analytics_claude_code_daily(start, end)
    except AnalyticsError as e:
        print(f"\n!! Could not reach Analytics API: {e}")
        print("   (Is the token in .env valid? It may have been revoked.)")
        store.close()
        return

    truth = {k: 0 for k in CANON}
    for day_totals in truth_daily_full.values():
        for k in CANON:
            truth[k] += day_totals[k]

    otel = otel_totals(store, start, end)
    captured, tagged, unmapped = otel["captured"], otel["tagged"], otel["unmapped"]
    dd = dedupe_drop_report(store, start, end)
    _print_funnel(truth, captured, tagged, suppress_synthetic_note=False)
    _print_unmapped(unmapped)
    _print_dedupe(dd, daily=daily)
    if by_surface:
        _print_by_surface(otel_by_surface(store, start, end))
    if daily:
        cap_daily = otel_daily(store, start, end)
        _print_daily(truth_daily_full, cap_daily)
    store.close()


def _print_funnel(truth, captured, tagged, suppress_synthetic_note: bool):

    # Per-token-type: truth vs captured -----------------------------------
    print(f"\nBY TOKEN TYPE   {'analytics(truth)':>{PAIR_W}}{'otel captured':>{PAIR_W}}"
          f"{'coverage':>{PCT_COL}}")
    print("-" * RULE_WIDTH)
    for k in CANON:
        print(f"  {k:<14}{_pair(truth[k]):>{PAIR_W}}{_pair(captured[k]):>{PAIR_W}}"
              f"{pct(captured[k], truth[k]):>{PCT_COL}}")
    A = sum(truth.values())
    C = sum(captured.values())
    T = sum(tagged.values())
    print("-" * RULE_WIDTH)
    print(f"  {'TOTAL':<14}{_pair(A):>{PAIR_W}}{_pair(C):>{PAIR_W}}{pct(C, A):>{PCT_COL}}")

    # Coverage funnel -----------------------------------------------------
    print("\nCOVERAGE FUNNEL (total tokens)")
    print("-" * RULE_WIDTH)
    print(f"  Analytics truth (org claude_code)   {_pair(A):>{PAIR_W}}   100.00%")
    print(f"  OTEL captured                       {_pair(C):>{PAIR_W}}   {pct(C, A):>7}")
    gap1 = A - C
    for line in _wrap(f"    gap {ftok(gap1)} ({gap1:,}) not received"):
        print(line)
    print(f"    of which repo-tagged (billable)   {_pair(T):>{PAIR_W}}   {pct(T, A):>7}")
    gap2 = C - T
    for line in _wrap(f"    gap {ftok(gap2)} ({gap2:,}) received, no repo"):
        print(line)

    print("\nBILLABLE COVERAGE = repo-tagged / truth = " + pct(T, A))
    if not suppress_synthetic_note and C < A * 0.99:
        print()
        for line in _wrap(
                "Note: OTEL data here is SYNTHETIC (sample_payload), so low coverage is "
                "expected — it reflects that no real machines emit yet, not a bug. "
                "Against live telemetry, this % is your real attribution rate."):
            print(line)


def _print_unmapped(unmapped: dict) -> None:
    """`UNMAPPED TOKEN TYPES` -- printed only when non-empty, regardless of
    flags. States plainly that these tokens are excluded from the captured
    figures above (and therefore understate coverage), and names a
    token-type vocabulary change as the likely cause, using the file's
    existing `!!` prefix convention."""
    if not unmapped:
        return
    print("\n!! UNMAPPED TOKEN TYPES")
    print("-" * RULE_WIDTH)
    for line in _wrap(
            "These token types are not one of the canonical buckets counted above, so "
            "they are EXCLUDED from every captured/coverage figure above and UNDERSTATE "
            "coverage by the amount shown below. Likely cause: a new or changed "
            "token-type name upstream that this pipeline has not yet been taught to "
            "map."):
        print(line)
    for tt, n in sorted(unmapped.items(), key=lambda kv: -kv[1]):
        print(f"  {tt:<{LABEL_W}}{_pair(n):>{PAIR_W}}")


def _dedupe_qualifier(epoch, measurement: str) -> str:
    """The measurement-state wording for `DEDUPE DROPS`. Selects wording
    only -- callers decide independently whether counts are shown."""
    if measurement == "none" and not epoch:
        return "Counting has never run against this database"
    if measurement == "none":
        return f"Counting began after this window (at {epoch})"
    if measurement == "partial":
        return (f"Counting began during this window, at {epoch}, so the counts below "
                 "are a LOWER BOUND")
    return f"Window is fully counted (counting began at {epoch})"


def _print_dedupe(dd: dict, *, daily: bool = False) -> None:
    """`DEDUPE DROPS` -- driven by `dedupe_drop_report(...)`. The
    measurement state (see `_dedupe_qualifier`) selects the wording; it
    never decides whether a non-empty `by_type` is shown -- those rows
    always print, under every measurement state. Prints no bare drop
    figure when `by_type` is empty; a measured-zero window (state "full")
    says so explicitly so it cannot be confused with an unmeasured one."""
    print("\nDEDUPE DROPS")
    print("-" * RULE_WIDTH)
    epoch = dd["epoch"]
    measurement = dd["measurement"]
    by_type = dd["by_type"]
    qualifier = _dedupe_qualifier(epoch, measurement)
    if by_type:
        total = sum(by_type.values())
        if dd["counts_outside_measurement"] and measurement != "partial":
            # measurement == "none": the epoch genuinely contradicts the
            # presence of counts -- a real anomaly worth flagging.
            sentence = (f"!! {qualifier} -- yet {total:,} drop(s) dated inside this "
                        "window were recorded (a replayed export, or an interrupted "
                        "first write).")
        else:
            # measurement == "full", or "partial" (where drops dated inside
            # the counted portion are expected, not an anomaly).
            sentence = qualifier + "."
        for line in _wrap(sentence):
            print(line)
        for tt, n in sorted(by_type.items(), key=lambda kv: -kv[1]):
            label = f"{tt} (cost)" if tt == "__cost__" else tt
            print(f"  {label:<{LABEL_W}}{_pair(n):>{PAIR_W}}")
    elif measurement == "full":
        for line in _wrap(qualifier + " -- no duplicate datapoints in this window."):
            print(line)
    elif measurement == "partial":
        for line in _wrap(
                f"Counting began during this window, at {epoch} -- no duplicate "
                "datapoints were recorded from that instant onward, and any earlier "
                "in this window were never counted."):
            print(line)
    else:
        for line in _wrap(qualifier + "."):
            print(line)

    by_day = dd["by_day"]
    if daily and by_day:
        print("\n  by day:")
        for day in sorted(by_day):
            for tt, n in sorted(by_day[day].items(), key=lambda kv: -kv[1]):
                label = f"{tt} (cost)" if tt == "__cost__" else tt
                print(f"    {day}  {label:<{LABEL_W}}{_pair(n):>{PAIR_W}}")


def _print_by_surface(surf: dict) -> None:
    """`--by-surface` -- three sub-blocks (`usage_source`, `entrypoint`,
    `query_source`), each row sorted by tokens descending, each sub-block
    closed by a `TOTAL` row whose share reads `100.00%`. The header states
    plainly that this is a share of captured, NOT coverage: truth carries no
    surface dimension, so a per-surface percentage has no truth-side
    denominator."""
    captured_total = surf["captured_total"]
    print("\nBY SURFACE  (share of captured, NOT coverage)")
    print("-" * RULE_WIDTH)
    for line in _wrap(
            "Percentages below are each dimension's share of captured, NOT coverage -- "
            "the Analytics truth side carries no usage_source / entrypoint / "
            "query_source dimension to compare against."):
        print(line)
    for dim_name in ("usage_source", "entrypoint", "query_source"):
        dim = surf[dim_name]
        print(f"\n  {dim_name}")
        block_total = 0
        for val, n in sorted(dim.items(), key=lambda kv: -kv[1]):
            block_total += n
            print(f"    {val:<{LABEL_W - 2}}{_pair(n):>{PAIR_W}}"
                  f"{pct(n, captured_total):>{PCT_COL}}")
        print(f"    {'TOTAL':<{LABEL_W - 2}}{_pair(block_total):>{PAIR_W}}"
              f"{pct(block_total, captured_total):>{PCT_COL}}")


def _print_daily(truth_daily: dict, cap_daily: dict) -> None:
    """`--daily` -- one row per UTC day over the union of days present in
    truth and captured, sorted ascending. A day absent from one side prints
    with a zeroed bucket on that side rather than being omitted, so a
    receiver outage (truth present, captured zero) stays visible. Days
    absent from BOTH sides are simply not in the union and never appear."""
    days = sorted(set(truth_daily) | set(cap_daily))
    print("\nDAILY")
    print(f"  {'day':<10}{'truth':>{PAIR_W}}{'captured':>{PAIR_W}}"
          f"{'coverage':>{PCT_COL}}{'tagged':>{PAIR_W}}{'billable':>{PCT_COL}}")
    print("-" * RULE_WIDTH)
    zero = {k: 0 for k in CANON}
    for day in days:
        t = sum(truth_daily.get(day, zero).values())
        cap_bucket = cap_daily.get(day) or {"captured": zero, "tagged": zero}
        c = sum(cap_bucket["captured"].values())
        tg = sum(cap_bucket["tagged"].values())
        print(f"  {day:<10}{_pair(t):>{PAIR_W}}{_pair(c):>{PAIR_W}}"
              f"{pct(c, t):>{PCT_COL}}{_pair(tg):>{PAIR_W}}{pct(tg, t):>{PCT_COL}}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD (exclusive)")
    ap.add_argument("--db", default=None)
    ap.add_argument("--email", action="append", default=None)
    ap.add_argument("--analytics-db", default=None)
    ap.add_argument("--by-surface", action="store_true",
                     help="show captured-share breakdown by usage_source/entrypoint/query_source")
    ap.add_argument("--daily", action="store_true", help="show per-day coverage rows")
    ap.add_argument("--detail", action="store_true", help="implies --by-surface and --daily")
    args = ap.parse_args()
    by_surface = args.by_surface or args.detail
    daily = args.daily or args.detail
    run(args.start, args.end, args.db, args.email, args.analytics_db,
        by_surface=by_surface, daily=daily)


if __name__ == "__main__":
    main()
