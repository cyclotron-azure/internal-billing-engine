"""Build the running usage datasets for the data lake.

Two flat, all-history CSVs — NOT partitioned into per-period folders — so Fabric
loads each as a single running table that accumulates records across months:

    claudeusagesummary.csv     one row per (usage date, repo, user_email)
    claudeusagelineitems.csv   one row per (usage date, repo, model, user_email)

`repo` is the short billing name (the last path segment, or an override from the
repo_name_map); the line-item table also carries `repo_key`, the full canonical
key, so same-named repos in different orgs stay distinguishable.

Each row carries WHEN the usage happened — usage_date_utc (the day) plus the
first_usage_at_utc / last_usage_at_utc timestamps bounding that day's activity —
and the calendar month it bills to (period_start / period_end), so a monthly
rollup is just a GROUP BY. All three are UTC, as emitted by Claude Code.
generated_at is unrelated to usage: it records when the snapshot was produced.
Rows billed to `unknown` are further split by the trailing attribution_source
(why no repo was found) and unattributed_project (a privacy-safe project-folder
label from the session timeline, or ""); both are "" for attributed rows and are
diagnostic only -- never part of `repo` / `repo_key`.
Regenerated in full from the store on every sync and written to a STABLE path, so
Fabric can load-to-table with OVERWRITE and always get the complete,
de-duplicated history.

Work-domain filter: datapoints whose user_email is a real address outside the
allowed domain set (env ALLOWED_EMAIL_DOMAINS, comma-separated, default
cyclotron.com; read at call time) are dropped before aggregation, so neither CSV
carries personal-account usage. Match is case-insensitive on the exact domain
after the last '@'. Missing/`unknown` users are kept. The raw store is untouched;
each export prints how many groups were excluded.
"""

from __future__ import annotations

import csv
import os
from datetime import date, datetime, timezone

from .attribute import resolved_view
from .normalize import normalize_model, repo_name
from .otel_store import OtelStore
from .project_label import load_session_labels

SUMMARY_TABLE = "claudeusagesummary"
LINEITEMS_TABLE = "claudeusagelineitems"

SUMMARY_FIELDS = ["usage_date_utc", "period_start", "period_end", "repo", "user_email",
                  "tokens", "actual_cost_usd", "markup", "total_billed_usd",
                  "first_usage_at_utc", "last_usage_at_utc", "generated_at",
                  "attribution_source", "unattributed_project"]
LINE_FIELDS = ["usage_date_utc", "period_start", "period_end", "repo", "repo_key", "model",
               "user_email", "tokens", "actual_cost_usd", "billed_usd",
               "first_usage_at_utc", "last_usage_at_utc", "generated_at",
               "attribution_source", "unattributed_project"]

UNKNOWN_USER = "unknown"  # datapoints that arrived without a user.email attribute


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _month_end(ym: str) -> str:
    """'YYYY-MM' -> first day of the NEXT month, as YYYY-MM-DD."""
    y, m = int(ym[:4]), int(ym[5:7])
    return date(y + m // 12, m % 12 + 1, 1).isoformat()


DEFAULT_ALLOWED_DOMAINS = ("cyclotron.com",)


def allowed_domains() -> tuple:
    """Allowed work-email domains, read from ALLOWED_EMAIL_DOMAINS at CALL time.

    Comma-separated; entries are stripped, lower-cased, and a leading '@' is
    dropped. Unset or effectively empty -> DEFAULT_ALLOWED_DOMAINS."""
    raw = os.environ.get("ALLOWED_EMAIL_DOMAINS") or ""
    doms = tuple(d for d in (p.strip().lower().lstrip("@").strip()
                             for p in raw.split(",")) if d)
    return doms or DEFAULT_ALLOWED_DOMAINS


def is_allowed_user(email, domains) -> bool:
    """True if a datapoint with this user_email belongs in the lake.

    NULL/empty/whitespace-only and the literal 'unknown' are kept. Otherwise the
    domain after the LAST '@' must exactly equal an allowed domain; an address
    with no '@' is excluded."""
    if email is None:
        return True
    e = str(email).strip().lower()
    if not e or e == UNKNOWN_USER:
        return True
    if "@" not in e:
        return False
    return e.rsplit("@", 1)[1] in domains


def build(store: OtelStore, markup: float, allowed_domains=None, stats=None):
    """Return (summary_rows, line_rows) covering the store's usage for allowed
    users, aggregated per usage DAY × repo/model × user.

    Datapoints whose user_email is a real address outside `allowed_domains`
    (default: ALLOWED_EMAIL_DOMAINS / cyclotron.com) are dropped before keying.
    If `stats` is a dict it receives `excluded_groups` (distinct excluded
    (day, repo, model, user_email) groups) and `excluded_domains` (sorted
    dropped domains, never full emails)."""
    if allowed_domains is None:
        allowed_domains = globals()["allowed_domains"]()
    excluded_groups: set = set()
    excluded_domains: set = set()
    mapping = store.get_mapping()
    name_of = lambda repo: mapping.get(repo) or repo_name(repo)

    # first/last datapoint time per key, merged across both source tables.
    span: dict = {}

    def _span(key, lo, hi):
        cur = span.get(key)
        if cur is None:
            span[key] = [lo, hi]
        else:
            cur[0] = min(cur[0], lo)
            cur[1] = max(cur[1], hi)

    # Repo is resolved per datapoint BEFORE the day/model/user rollup, so a
    # session that moved between repos splits into separate rows rather than
    # billing wholly to wherever it launched. See billing.otel.attribute.
    # Rows that resolve to 'unknown' also carry their attribution class and
    # session (mapped to a project label below); attributed rows get NULLs.
    labels = load_session_labels(store.db)  # once per build; never persisted

    def _scan(table, agg):
        for r in store.db.execute(
                f"WITH r AS ({resolved_view(table)}) "
                "SELECT substr(ts,1,10) d, resolved_repo, model, user_email, "
                "CASE WHEN resolved_repo = 'unknown' THEN attribution_source END src, "
                "CASE WHEN resolved_repo = 'unknown' THEN session_id END sid, "
                f"{agg} v, MIN(ts) lo, MAX(ts) hi "
                "FROM r GROUP BY d, resolved_repo, model, user_email, src, sid"):
            if not is_allowed_user(r["user_email"], allowed_domains):
                excluded_groups.add((r["d"], r["resolved_repo"], r["model"], r["user_email"]))
                addr = str(r["user_email"]).strip().lower()
                if "@" in addr:
                    excluded_domains.add(addr.rsplit("@", 1)[1])
                continue
            unknown = r["resolved_repo"] == "unknown"
            key = (r["d"], r["resolved_repo"], normalize_model(r["model"]),
                   r["user_email"] or UNKNOWN_USER,
                   (r["src"] or "") if unknown else "",
                   labels.get(r["sid"], "") if unknown else "")
            yield key, r["v"], r["lo"], r["hi"]

    cost = {}
    for key, v, lo, hi in _scan("cost_usage", "SUM(cost_usd)"):
        cost[key] = cost.get(key, 0.0) + (v or 0.0)
        _span(key, lo, hi)

    toks = {}
    for key, v, lo, hi in _scan("token_usage", "SUM(tokens)"):
        toks[key] = toks.get(key, 0) + (v or 0)
        _span(key, lo, hi)

    gen = _now_iso()
    line_rows = []
    summ: dict = {}  # (day, repo, user_email, source, label) -> [tokens, cost, first, last]
    for key in sorted(set(cost) | set(toks)):
        day, repo_key, model, user, src, label = key
        c = cost.get(key, 0.0)
        t = toks.get(key, 0)
        lo, hi = span[key]
        bn = name_of(repo_key)
        ps, pe = f"{day[:7]}-01", _month_end(day[:7])
        line_rows.append({
            "usage_date_utc": day, "period_start": ps, "period_end": pe,
            "repo": bn, "repo_key": repo_key, "model": model, "user_email": user,
            "tokens": t, "actual_cost_usd": round(c, 6),
            "billed_usd": round(c * markup, 6),
            "first_usage_at_utc": lo, "last_usage_at_utc": hi, "generated_at": gen,
            "attribution_source": src, "unattributed_project": label})
        agg = summ.setdefault((day, bn, user, src, label), [0, 0.0, lo, hi])
        agg[0] += t
        agg[1] += c
        agg[2] = min(agg[2], lo)
        agg[3] = max(agg[3], hi)

    summary_rows = []
    for (day, bn, user, src, label), (t, c, lo, hi) in sorted(summ.items()):
        ps, pe = f"{day[:7]}-01", _month_end(day[:7])
        summary_rows.append({
            "usage_date_utc": day, "period_start": ps, "period_end": pe,
            "repo": bn, "user_email": user, "tokens": t,
            "actual_cost_usd": round(c, 6), "markup": markup,
            "total_billed_usd": round(c * markup, 6),
            "first_usage_at_utc": lo, "last_usage_at_utc": hi, "generated_at": gen,
            "attribution_source": src, "unattributed_project": label})
    if stats is not None:
        stats["excluded_groups"] = len(excluded_groups)
        stats["excluded_domains"] = sorted(excluded_domains)
    return summary_rows, line_rows


def _write_csv(path: str, fields: list, rows: list) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _print_excluded(stats: dict) -> None:
    """One line: how many groups the domain filter dropped (domains only)."""
    print(f"[export] excluded {stats.get('excluded_groups', 0)} group(s) outside "
          f"{','.join(allowed_domains())}")


def build_and_enqueue(store: OtelStore, markup: float, out_dir: str = "exports"):
    """Write the two running CSVs and queue them for upload to stable, flat
    paths (<prefix>/claudeusagesummary.csv, <prefix>/claudeusagelineitems.csv)."""
    os.makedirs(out_dir, exist_ok=True)
    stats: dict = {}
    summary_rows, line_rows = build(store, markup, stats=stats)
    _print_excluded(stats)

    sp = os.path.join(out_dir, f"{SUMMARY_TABLE}.csv")
    lp = os.path.join(out_dir, f"{LINEITEMS_TABLE}.csv")
    _write_csv(sp, SUMMARY_FIELDS, summary_rows)
    _write_csv(lp, LINE_FIELDS, line_rows)

    # 'running' period marker -> one pending row per table, replaced each run.
    store.fabric_enqueue(kind=SUMMARY_TABLE, period_start="running", period_end="running",
                         local_path=os.path.abspath(sp), onelake_path=f"{SUMMARY_TABLE}.csv")
    store.fabric_enqueue(kind=LINEITEMS_TABLE, period_start="running", period_end="running",
                         local_path=os.path.abspath(lp), onelake_path=f"{LINEITEMS_TABLE}.csv")
    return len(summary_rows), len(line_rows)


def main():
    """Write the running CSVs locally, without needing a storage target.

    The scheduler only calls build_and_enqueue() when ADLS/OneLake credentials
    are configured, so this is the way to regenerate and inspect the lake tables
    on a machine with no storage target — demos, local verification, debugging a
    row that looks wrong before it ships.
    """
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=None, help="OTEL store path (default ./data/otel.db)")
    ap.add_argument("--markup", type=float, default=1.50)
    ap.add_argument("--out-dir", default="exports")
    ap.add_argument("--no-enqueue", action="store_true",
                    help="write the CSVs but do not queue them for upload")
    args = ap.parse_args()

    from ..config import load_env
    load_env()  # honor a .env ALLOWED_EMAIL_DOMAINS (call time, not import time)

    store = OtelStore(args.db) if args.db else OtelStore()
    if args.no_enqueue:
        stats: dict = {}
        summary_rows, line_rows = build(store, args.markup, stats=stats)
        _print_excluded(stats)
        os.makedirs(args.out_dir, exist_ok=True)
        _write_csv(os.path.join(args.out_dir, f"{SUMMARY_TABLE}.csv"),
                   SUMMARY_FIELDS, summary_rows)
        _write_csv(os.path.join(args.out_dir, f"{LINEITEMS_TABLE}.csv"),
                   LINE_FIELDS, line_rows)
        ns, nl = len(summary_rows), len(line_rows)
    else:
        ns, nl = build_and_enqueue(store, args.markup, args.out_dir)
    store.commit()
    store.close()
    print(f"[export] {args.out_dir}/{SUMMARY_TABLE}.csv    {ns} row(s)")
    print(f"[export] {args.out_dir}/{LINEITEMS_TABLE}.csv  {nl} row(s)")


if __name__ == "__main__":
    main()
