#!/usr/bin/env python3
"""Read-only report: every `unknown` usage row by day x user x repo, with the
attribution_source class and the unattributed_project diagnostic.

Reuses billing.otel.export.build(), so the rows, the work-domain filter and the
project labels are exactly what the lake tables carry. Nothing is written to the
store or enqueued.

    python deploy/unknown-report.py [--db ./data/otel.db] [--csv out.csv]
                                    [--start YYYY-MM-DD] [--end YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from billing.otel.export import build  # noqa: E402
from billing.otel.otel_store import OtelStore  # noqa: E402

FIELDS = ["usage_date_utc", "user_email", "repo", "attribution_source",
          "unattributed_project", "tokens", "actual_cost_usd"]


def unknown_rows(db=None, start=None, end=None):
    store = OtelStore(db) if db else OtelStore()
    try:
        summary, _ = build(store, markup=1.0)
    finally:
        store.close()
    out = []
    for r in summary:
        if r["repo"] != "unknown" or not r["attribution_source"]:
            continue
        if (start and r["usage_date_utc"] < start) or (end and r["usage_date_utc"] > end):
            continue
        out.append({k: r[k] for k in FIELDS})
    return sorted(out, key=lambda r: (r["usage_date_utc"], r["user_email"],
                                      r["attribution_source"], r["unattributed_project"]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=None)
    ap.add_argument("--csv", default=None, help="also write the rows to this CSV")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    a = ap.parse_args()
    rows = unknown_rows(a.db, a.start, a.end)

    print(f"{'date':10}  {'user':32}  {'repo':7}  {'source':15}  "
          f"{'project':28}  {'tokens':>12}  {'cost_usd':>9}")
    for r in rows:
        print(f"{r['usage_date_utc']:10}  {r['user_email'][:32]:32}  {r['repo']:7}  "
              f"{r['attribution_source']:15}  {(r['unattributed_project'] or '-')[:28]:28}  "
              f"{r['tokens']:>12,}  {r['actual_cost_usd']:>9.2f}")

    tot = {}
    for r in rows:
        k = r["attribution_source"]
        t = tot.setdefault(k, [0, 0.0])
        t[0] += r["tokens"]
        t[1] += r["actual_cost_usd"]
    print("\nTotals by class:")
    for k, (t, c) in sorted(tot.items(), key=lambda kv: -kv[1][1]):
        print(f"  {k:15} {t:>14,} tokens  ${c:,.2f}")

    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        print(f"\nWrote {len(rows)} rows to {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
