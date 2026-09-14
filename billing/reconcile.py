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

from .analytics_client import AnalyticsClient, AnalyticsError
from .otel.otel_store import OtelStore
from .store import Store, tokens as analytics_tokens

# canonical token buckets used on both sides
CANON = ["input", "output", "cacheRead", "cacheCreation"]


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


def analytics_claude_code_totals(start, end) -> dict:
    """Authoritative org-wide claude_code tokens, in canonical buckets."""
    client = AnalyticsClient()
    out = {k: 0 for k in CANON}
    for _day, row in client.usage_report(start, end, products=["claude_code"]):
        t = analytics_tokens(row)
        out["input"] += t["uncached_input"]
        out["output"] += t["output"]
        out["cacheRead"] += t["cache_read"]
        out["cacheCreation"] += t["cache_creation_1h"] + t["cache_creation_5m"]
    return out


def _normalize_emails(emails: list[str]) -> list[str]:
    return [e.strip().lower() for e in emails]


def otel_totals(store: OtelStore, start, end, emails: list[str] | None = None) -> dict:
    """OTEL captured tokens in [start, end), split into captured / tagged.

    A repo tag is sufficient to bill (usage bills to the repo), so repo-tagged
    tokens are exactly the billable tokens. `emails`, when given, scopes to those
    (case/whitespace-insensitive) OTEL-side user_email values."""
    sql = """SELECT repo, token_type, SUM(tokens) tok FROM token_usage
             WHERE substr(ts,1,10) >= ? AND substr(ts,1,10) < ?"""
    params: list = [start, end]
    if emails:
        norm = _normalize_emails(emails)
        sql += f" AND LOWER(TRIM(user_email)) IN ({','.join('?' * len(norm))})"
        params.extend(norm)
    sql += " GROUP BY repo, token_type"
    rows = store.db.execute(sql, params).fetchall()
    captured = {k: 0 for k in CANON}
    tagged = {k: 0 for k in CANON}
    for r in rows:
        tt = r["token_type"] if r["token_type"] in CANON else None
        if tt is None:
            continue
        captured[tt] += r["tok"] or 0
        if r["repo"] and r["repo"] != "unknown":
            tagged[tt] += r["tok"] or 0
    return {"captured": captured, "tagged": tagged}


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
        emails: list[str] | None = None, analytics_db: str | None = None):
    store = OtelStore(db) if db else OtelStore()

    banner = f"RECONCILIATION  period {start} -> {end}  (product=claude_code)"
    if emails:
        banner += f"  emails={','.join(emails)}"
    print("=" * 70)
    print(banner)
    print("=" * 70)

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
        captured, tagged = otel["captured"], otel["tagged"]
        _print_funnel(truth, captured, tagged, suppress_synthetic_note=True)
        store.close()
        return

    try:
        truth = analytics_claude_code_totals(start, end)
    except AnalyticsError as e:
        print(f"\n!! Could not reach Analytics API: {e}")
        print("   (Is the token in .env valid? It may have been revoked.)")
        store.close()
        return

    otel = otel_totals(store, start, end)
    captured, tagged = otel["captured"], otel["tagged"]
    _print_funnel(truth, captured, tagged, suppress_synthetic_note=False)
    store.close()


def _print_funnel(truth, captured, tagged, suppress_synthetic_note: bool):

    # Per-token-type: truth vs captured -----------------------------------
    print(f"\nBY TOKEN TYPE   {'analytics(truth)':>18}{'otel captured':>16}{'coverage':>11}")
    print("-" * 70)
    for k in CANON:
        print(f"  {k:<14}{ftok(truth[k]):>18}{ftok(captured[k]):>16}"
              f"{pct(captured[k], truth[k]):>11}")
    A = sum(truth.values())
    C = sum(captured.values())
    T = sum(tagged.values())
    print("-" * 70)
    print(f"  {'TOTAL':<14}{ftok(A):>18}{ftok(C):>16}{pct(C, A):>11}")

    # Coverage funnel -----------------------------------------------------
    print("\nCOVERAGE FUNNEL (total tokens)")
    print("-" * 70)
    print(f"  Analytics truth (org claude_code)   {ftok(A):>12}   100.00%")
    print(f"  OTEL captured                       {ftok(C):>12}   {pct(C, A):>7}"
          f"   gap {ftok(A - C)} not received")
    print(f"    of which repo-tagged (billable)   {ftok(T):>12}   {pct(T, A):>7}"
          f"   gap {ftok(C - T)} received, no repo")

    print("\nBILLABLE COVERAGE = repo-tagged / truth = " + pct(T, A))
    if not suppress_synthetic_note and C < A * 0.99:
        print("\nNote: OTEL data here is SYNTHETIC (sample_payload), so low coverage")
        print("      is expected — it reflects that no real machines emit yet, not a")
        print("      bug. Against live telemetry, this % is your real attribution rate.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD (exclusive)")
    ap.add_argument("--db", default=None)
    ap.add_argument("--email", action="append", default=None)
    ap.add_argument("--analytics-db", default=None)
    args = ap.parse_args()
    run(args.start, args.end, args.db, args.email, args.analytics_db)


if __name__ == "__main__":
    main()
