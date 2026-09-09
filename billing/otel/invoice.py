"""Generate per-repo invoices for a billing period.

For each billing name (a repo, or an override that renames/groups repos) with
attributed usage in [start, end):
  - aggregate actual cost (claude_code.cost.usage) and tokens per repo x model,
  - apply markup,
  - persist an immutable invoice + line items to the store,
  - write a human-readable invoice + CSVs under ./invoices/<start>_<end>/.

Usage from sessions with no git remote (the `unknown` bucket) is reported but
NOT invoiced.

    python -m billing.otel.invoice --start 2026-07-01 --end 2026-08-01 --markup 1.5
"""

from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict
from datetime import datetime, timezone

from .normalize import normalize_model, repo_name
from .otel_store import OtelStore

UNATTRIBUTED = "unknown"  # sessions with no git remote -> not tied to a repo


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ftok(n) -> str:
    n = n or 0
    if n >= 1_000_000_000:
        return f"{n/1e9:.2f}B"
    if n >= 1_000_000:
        return f"{n/1e6:.1f}M"
    if n >= 1_000:
        return f"{n/1e3:.1f}K"
    return str(int(n))


def _in_period(col_table, start, end):
    return (f"WHERE substr(ts,1,10) >= '{start}' AND substr(ts,1,10) < '{end}'")


def gather(store: OtelStore, start: str, end: str):
    """Return {bill_name: {(repo, model): {tokens, actual_cost, estimated_cost}}}
    for the period.

    `actual_cost` is the sum of cost_usage rows with cost_source='actual'
    (Anthropic-reported claude_code.cost.usage). `estimated_cost` is the sum
    of cost_source='rate_card' rows (desktop transcripts, task 02/04 --
    already a pre-markup RatingService estimate, computed by
    transcript.map_record). The split is derived here, at generation time,
    from the existing `cost_source` column -- no new persisted column.
    """
    mapping = store.get_mapping()
    name_of = lambda repo: mapping.get(repo) or repo_name(repo)

    # actual vs rate-card cost per repo x model, kept separate so a caller
    # never has to guess how much of a combined figure is an estimate.
    #
    # Strict equality on BOTH recognized values -- matching bill.py's
    # `cost_source == "actual"` / `== "rate_card"` filters exactly -- so the
    # two files agree on what happens to an unrecognized cost_source: such a
    # row is excluded from both buckets, never silently folded into
    # "actual". In practice `cost_source` is only ever 'actual' or
    # 'rate_card' (otel_store.SCHEMA's CHECK-free default plus the only two
    # writers, task 01/02); this branch is unreachable from production but
    # keeps bill.py and invoice.py from disagreeing if that ever changes.
    cost_actual = defaultdict(float)
    cost_estimated = defaultdict(float)
    for r in store.db.execute(
            "SELECT repo, model, cost_source, SUM(cost_usd) c FROM cost_usage "
            "WHERE substr(ts,1,10) >= ? AND substr(ts,1,10) < ? "
            "GROUP BY repo, model, cost_source", (start, end)):
        key = (r["repo"], normalize_model(r["model"]))
        if r["cost_source"] == "rate_card":
            cost_estimated[key] += r["c"] or 0.0
        elif r["cost_source"] == "actual":
            cost_actual[key] += r["c"] or 0.0

    # tokens per repo x model
    toks = defaultdict(int)
    for r in store.db.execute(
            "SELECT repo, model, SUM(tokens) t FROM token_usage "
            "WHERE substr(ts,1,10) >= ? AND substr(ts,1,10) < ? "
            "GROUP BY repo, model", (start, end)):
        toks[(r["repo"], normalize_model(r["model"]))] += r["t"] or 0

    entities = defaultdict(lambda: defaultdict(
        lambda: {"tokens": 0, "actual_cost": 0.0, "estimated_cost": 0.0}))
    for key in set(cost_actual) | set(cost_estimated) | set(toks):
        repo, model = key
        nm = name_of(repo)
        entities[nm][(repo, model)] = {
            "tokens": toks.get(key, 0),
            "actual_cost": cost_actual.get(key, 0.0),
            "estimated_cost": cost_estimated.get(key, 0.0),
        }
    return entities


def persist_invoice(store, invoice_number, bill_name, start, end, markup,
                    line_items, actual_cost, tokens, total_billed):
    store.db.execute("DELETE FROM invoice_line_items WHERE invoice_number = ?",
                     (invoice_number,))
    store.db.execute(
        """INSERT OR REPLACE INTO invoices
           (invoice_number, bill_name, period_start, period_end, currency,
            actual_cost, markup, total_billed, tokens, status, generated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (invoice_number, bill_name, start, end, "USD", actual_cost, markup,
         total_billed, tokens, "draft", _now()))
    for li in line_items:
        store.db.execute(
            """INSERT INTO invoice_line_items
               (invoice_number, repo, model, tokens, actual_cost, billed_amount)
               VALUES (?,?,?,?,?,?)""",
            (invoice_number, li["repo"], li["model"], li["tokens"],
             li["actual_cost"], li["billed"]))
    store.commit()


def write_invoice_text(path, invoice_number, bill_name, start, end, markup,
                       line_items, actual_cost, estimated_cost, tokens, total_billed):
    """Render the human-readable invoice.

    `actual_cost` (Anthropic-reported) and `estimated_cost` (desktop
    rate-card, derived at generation time from cost_usage.cost_source) are
    always shown as separate figures per line item and in the subtotal --
    never merged into a single number labelled "actual", so a rate-card
    estimate can never be mistaken for an Anthropic-reported cost on a
    client-facing invoice.
    """
    W = 104
    money = lambda x: f"${x:,.4f}"
    trunc = lambda s, n: s if len(s) <= n else s[:n - 1] + "…"
    has_estimate = any(li["estimated_cost"] for li in line_items) or estimated_cost
    lines = []
    lines.append("CYCLOTRON — Claude Usage Invoice")
    lines.append("=" * W)
    lines.append(f"Invoice #:  {invoice_number}")
    lines.append(f"Repo:       {bill_name}")
    lines.append(f"Period:     {start}  →  {end}")
    lines.append(f"Generated:  {_now()}")
    lines.append("Status:     DRAFT")
    lines.append("")
    if has_estimate:
        # Column widths sum to exactly W (104), matching the rules/subtotals
        # below -- 38+20+8+13+17+13 (=109) previously overhung the table's
        # own "-"*104 rule by 5 characters on a client-facing invoice.
        lines.append(f"{'Repo':<35}{'Model':<18}{'Tokens':>8}"
                     f"{'Actual':>13}{'Est.(rate-card)':>17}{'Billed':>13}")
        lines.append("-" * W)
        for li in sorted(line_items, key=lambda x: -x["billed"]):
            lines.append(f"{trunc(li['repo'], 34):<35}{trunc(li['model'], 17):<18}"
                         f"{ftok(li['tokens']):>8}{money(li['actual_cost']):>13}"
                         f"{money(li['estimated_cost']):>17}{money(li['billed']):>13}")
        lines.append("-" * W)
        lines.append(f"{'Subtotal (Anthropic actual cost)':<88}{money(actual_cost):>16}")
        lines.append(f"{'Subtotal (rate-card estimate, desktop)':<88}"
                     f"{money(estimated_cost):>16}")
        lines.append(f"{'Markup':<88}{'x%.2f' % markup:>16}")
        lines.append(f"{'TOTAL DUE (USD)':<88}{money(total_billed):>16}")
    else:
        lines.append(f"{'Repo':<46}{'Model':<24}{'Tokens':>8}{'Cost':>13}{'Billed':>13}")
        lines.append("-" * W)
        for li in sorted(line_items, key=lambda x: -x["billed"]):
            lines.append(f"{trunc(li['repo'], 45):<46}{trunc(li['model'], 23):<24}"
                         f"{ftok(li['tokens']):>8}{money(li['actual_cost']):>13}"
                         f"{money(li['billed']):>13}")
        lines.append("-" * W)
        lines.append(f"{'Subtotal (Anthropic actual cost)':<88}{money(actual_cost):>16}")
        lines.append(f"{'Markup':<88}{'x%.2f' % markup:>16}")
        lines.append(f"{'TOTAL DUE (USD)':<88}{money(total_billed):>16}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def run(start: str, end: str, markup: float = 1.50, db: str | None = None,
        out_dir: str | None = None):
    store = OtelStore(db) if db else OtelStore()
    out_dir = out_dir or os.path.join("invoices", f"{start}_{end}")
    os.makedirs(out_dir, exist_ok=True)

    entities = gather(store, start, end)

    summary_rows = []
    all_line_items = []
    print(f"Generating invoices for {start} → {end}  (markup x{markup:.2f})\n")

    for bill_name in sorted(c for c in entities if c != UNATTRIBUTED):
        items = entities[bill_name]
        line_items = []
        actual_cost = 0.0
        estimated_cost = 0.0
        tokens = 0
        for (repo, model), v in items.items():
            # Desktop usage actually bills: both the actual and rate-card
            # portions go into the billed cost basis. Both are already
            # pre-markup USD (task 02's transcript.map_record uses
            # RatingService.raw_cost, no markup), so this is a plain sum --
            # markup is applied exactly once, below.
            cost_basis = v["actual_cost"] + v["estimated_cost"]
            billed = cost_basis * markup
            line_items.append({"repo": repo, "model": model,
                               "tokens": v["tokens"], "actual_cost": v["actual_cost"],
                               "estimated_cost": v["estimated_cost"],
                               "cost_basis": cost_basis, "billed": billed})
            actual_cost += v["actual_cost"]
            estimated_cost += v["estimated_cost"]
            tokens += v["tokens"]
        cost_basis_total = actual_cost + estimated_cost
        total_billed = cost_basis_total * markup
        invoice_number = f"INV-{start}-{bill_name}"

        # persist_invoice's `actual_cost` column keeps its existing, honest
        # meaning -- summed claude_code.cost.usage only (never the desktop
        # estimate) -- per otel_store.SCHEMA's own comment. `total_billed`
        # correctly includes the desktop portion so desktop usage doesn't
        # silently bill zero. Regeneration mechanics (DELETE + INSERT OR
        # REPLACE) are unchanged -- out of scope for this task.
        persist_invoice(store, invoice_number, bill_name, start, end, markup,
                        line_items, actual_cost, tokens, total_billed)
        text_path = os.path.join(out_dir, f"{invoice_number}.txt")
        write_invoice_text(text_path, invoice_number, bill_name, start, end, markup,
                           line_items, actual_cost, estimated_cost, tokens, total_billed)

        summary_rows.append({
            "invoice_number": invoice_number, "bill_name": bill_name,
            "period_start": start, "period_end": end, "tokens": tokens,
            "actual_cost_usd": round(actual_cost, 6),
            "estimated_cost_usd": round(estimated_cost, 6), "markup": markup,
            "total_billed_usd": round(total_billed, 6),
        })
        for li in line_items:
            all_line_items.append({
                "invoice_number": invoice_number, "bill_name": bill_name,
                "repo": li["repo"], "model": li["model"], "tokens": li["tokens"],
                "actual_cost_usd": round(li["actual_cost"], 6),
                "estimated_cost_usd": round(li["estimated_cost"], 6),
                "billed_usd": round(li["billed"], 6),
            })
        print(f"  {invoice_number:<34} {ftok(tokens):>7} tok  "
              f"cost ${cost_basis_total:,.4f}  billed ${total_billed:,.4f}")

    # CSVs
    summary_csv = os.path.join(out_dir, "summary.csv")
    with open(summary_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["invoice_number", "bill_name",
            "period_start", "period_end", "tokens", "actual_cost_usd",
            "estimated_cost_usd", "markup", "total_billed_usd"])
        w.writeheader()
        w.writerows(summary_rows)
    line_csv = os.path.join(out_dir, "line_items.csv")
    with open(line_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["invoice_number", "bill_name", "repo",
            "model", "tokens", "actual_cost_usd", "estimated_cost_usd", "billed_usd"])
        w.writeheader()
        w.writerows(all_line_items)

    grand = sum(r["total_billed_usd"] for r in summary_rows)
    print(f"\n{len(summary_rows)} invoice(s), grand total billed ${grand:,.4f}")
    print(f"Written to {out_dir}/  (per-repo .txt, summary.csv, line_items.csv)")

    # Unattributed report (not invoiced): sessions with no git remote.
    if UNATTRIBUTED in entities:
        un_actual = sum(v["actual_cost"] for v in entities[UNATTRIBUTED].values())
        un_estimated = sum(v["estimated_cost"] for v in entities[UNATTRIBUTED].values())
        un_cost = un_actual + un_estimated
        print(f"\n⚠  UNINVOICED (no git remote → 'unknown'): ${un_cost:,.4f} cost basis"
              + (f" (${un_actual:,.4f} actual + ${un_estimated:,.4f} rate-card estimate)"
                 if un_estimated else "") + ".")
        print("   Ensure sessions run inside a git repo so usage carries a repo tag.")

    # (Data-lake delivery is handled separately by billing.otel.export /
    #  billing.otel.scheduler as running, all-history tables — not per-period files.)
    store.close()


def main():
    ap = argparse.ArgumentParser(description="Generate per-repo invoices.")
    ap.add_argument("--start", required=True, help="period start YYYY-MM-DD (inclusive)")
    ap.add_argument("--end", required=True, help="period end YYYY-MM-DD (exclusive)")
    ap.add_argument("--markup", type=float, default=1.50)
    ap.add_argument("--db", default=None)
    ap.add_argument("--out", default=None, help="output dir (default ./invoices/<start>_<end>)")
    args = ap.parse_args()
    run(args.start, args.end, args.markup, args.db, args.out)


if __name__ == "__main__":
    main()
