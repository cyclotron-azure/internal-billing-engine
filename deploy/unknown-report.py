#!/usr/bin/env python3
"""Read-only report: every `unknown` usage row by day x user x repo, with the
attribution_source class and the unattributed_project diagnostic.

Deliberately independent of billing.otel.export, so it runs on a host whose
export.py predates the lake-table diagnostic columns. It needs only
billing.otel.attribute (resolved_view) and, for the project label,
billing.otel.project_label (pure stdlib). Nothing is written to the store.

    python3 deploy/unknown-report.py [--db ./data/otel.db] [--csv out.csv]
                                     [--start YYYY-MM-DD] [--end YYYY-MM-DD]
                                     [--domains cyclotron.com,...]
"""

from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from billing.otel.attribute import resolved_view  # noqa: E402

try:
    from billing.otel.project_label import load_session_labels  # noqa: E402
except ImportError:  # host predates project_label.py
    load_session_labels = None

FIELDS = ["usage_date_utc", "user_email", "repo", "attribution_source",
          "unattributed_project", "tokens", "actual_cost_usd"]


def _allowed(email, domains) -> bool:
    e = (email or "").strip().lower()
    if not e or e == "unknown":
        return True
    return "@" in e and e.rsplit("@", 1)[1] in domains


def unknown_rows(db_path, start=None, end=None, domains=("cyclotron.com",)):
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    labels = load_session_labels(db) if load_session_labels else {}
    agg: dict = {}
    for table, col, slot in (("token_usage", "SUM(tokens)", "tokens"),
                             ("cost_usage", "SUM(cost_usd)", "cost")):
        sql = (f"WITH r AS ({resolved_view(table)}) "
               f"SELECT substr(ts,1,10) d, user_email, attribution_source src, "
               f"session_id sid, {col} v FROM r WHERE resolved_repo = 'unknown' "
               f"GROUP BY d, user_email, src, sid")
        for r in db.execute(sql):
            if not _allowed(r["user_email"], domains):
                continue
            if (start and r["d"] < start) or (end and r["d"] > end):
                continue
            key = (r["d"], r["user_email"] or "unknown", r["src"],
                   labels.get(r["sid"], ""))
            a = agg.setdefault(key, {"tokens": 0, "cost": 0.0})
            a[slot] += r["v"] or 0
    db.close()
    return [{"usage_date_utc": d, "user_email": u, "repo": "unknown",
             "attribution_source": s, "unattributed_project": p,
             "tokens": int(v["tokens"]), "actual_cost_usd": round(v["cost"], 6)}
            for (d, u, s, p), v in sorted(agg.items())]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=os.environ.get("OTEL_DB", "./data/otel.db"))
    ap.add_argument("--csv", default=None, help="also write the rows to this CSV")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--domains", default="cyclotron.com",
                    help="comma-separated work domains to keep")
    a = ap.parse_args()
    domains = tuple(d.strip().lower() for d in a.domains.split(",") if d.strip())
    if load_session_labels is None:
        print("note: billing/otel/project_label.py missing -- project column blank",
              file=sys.stderr)
    rows = unknown_rows(a.db, a.start, a.end, domains)

    print(f"{'date':10}  {'user':32}  {'repo':7}  {'source':15}  "
          f"{'project':28}  {'tokens':>12}  {'cost_usd':>9}")
    for r in rows:
        print(f"{r['usage_date_utc']:10}  {r['user_email'][:32]:32}  {r['repo']:7}  "
              f"{r['attribution_source']:15}  {(r['unattributed_project'] or '-')[:28]:28}  "
              f"{r['tokens']:>12,}  {r['actual_cost_usd']:>9.2f}")

    tot: dict = {}
    for r in rows:
        t = tot.setdefault(r["attribution_source"], [0, 0.0])
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
