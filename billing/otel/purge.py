"""Empty the receiver's store so a fresh batch of telemetry can be tested.

Wipes what the receiver has RECEIVED (usage datapoints + the session->repo
timeline) and everything derived from it (persisted invoices, line items, the
data-lake delivery outbox), leaving the schema in place so the receiver keeps
serving without a restart. The optional repo->billing-name overrides are
CONFIG, not received data, so they survive unless you ask for them too.

Counts first, deletes only when told to:

    python -m billing.otel.purge                  # dry run — show what WOULD go
    python -m billing.otel.purge --yes            # delete telemetry + derived rows
    python -m billing.otel.purge --yes --all      # also drop repo_name_map / meta
    python -m billing.otel.purge --yes --log      # also truncate receiver.log

Against the Docker receiver, run it on the host over the mounted volume — the
`billing/` copy inside a running container is whatever the image was built
with:

    docker compose stop receiver sync
    OTEL_DB=./otel-data/otel.db python3 -m billing.otel.purge --yes --log
    docker compose start receiver sync

Two things this does NOT touch, because they live outside the store: the CSVs
and invoice files already written under ./exports and ./invoices, and anything
the sync worker already uploaded to ADLS Gen2 / OneLake. The lake tables are
regenerated in full from the store and overwritten on every sync, so the next
sync after a purge replaces them with the post-purge data.
"""

from __future__ import annotations

import argparse
import os
import sqlite3

from ..config import load_env
from .otel_store import DEFAULT_DB, OtelStore

load_env()

# Rows the receiver wrote from inbound POSTs.
RECEIVED_TABLES = ["token_usage", "cost_usage", "session_repo_timeline"]

# Rows computed from the above — stale the moment the usage rows go.
DERIVED_TABLES = ["invoices", "invoice_line_items", "fabric_outbox"]

# Configuration that happens to share the database. Kept unless --all.
CONFIG_TABLES = ["repo_name_map", "meta"]

LOG_PATH = os.environ.get("RECEIVER_LOG", "data/receiver.log")


def counts(store: OtelStore, tables: list) -> dict:
    return {t: store.db.execute(f"SELECT COUNT(*) n FROM {t}").fetchone()["n"]
            for t in tables}


def purge(store: OtelStore, tables: list) -> dict:
    """Delete every row in `tables`, in one transaction. Returns rows deleted
    per table."""
    deleted = {}
    with store.db:  # commits on success, rolls back on error
        for t in tables:
            deleted[t] = store.db.execute(f"DELETE FROM {t}").rowcount
    return deleted


def truncate_log(path: str) -> bool:
    """Empty the receiver's request log in place (kept, not unlinked, so a
    running receiver keeps appending to the same file)."""
    try:
        with open(path, "w", encoding="utf-8"):
            pass
        return True
    except OSError as e:
        print(f"[purge] could not truncate {path}: {e}")
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=None,
                    help=f"OTEL store path (default {DEFAULT_DB})")
    ap.add_argument("--yes", action="store_true",
                    help="actually delete; without it this is a dry run")
    ap.add_argument("--all", action="store_true", dest="all_tables",
                    help="also clear the repo->billing-name overrides and meta")
    ap.add_argument("--log", action="store_true",
                    help=f"also truncate the receiver request log ({LOG_PATH})")
    ap.add_argument("--keep-invoices", action="store_true",
                    help="keep persisted invoices, line items and the delivery "
                         "outbox (they will no longer match the usage rows)")
    args = ap.parse_args()

    tables = list(RECEIVED_TABLES)
    if not args.keep_invoices:
        tables += DERIVED_TABLES
    if args.all_tables:
        tables += CONFIG_TABLES

    path = args.db or DEFAULT_DB
    store = OtelStore(args.db) if args.db else OtelStore()
    before = counts(store, tables)
    total = sum(before.values())

    print(f"[purge] store {os.path.abspath(path)}")
    for t in tables:
        print(f"  {t:<24} {before[t]:>9,} row(s)")
    print(f"  {'TOTAL':<24} {total:>9,} row(s)")

    if not args.yes:
        print("\n[purge] DRY RUN — nothing deleted. Re-run with --yes to delete.")
        if not args.all_tables:
            print("[purge] repo_name_map / meta are kept; add --all to clear them too.")
        store.close()
        return

    deleted = purge(store, tables)
    print(f"\n[purge] deleted {sum(deleted.values()):,} row(s)")

    # Reclaim the file space. Needs no other connection mid-write, so it can
    # lose a race with a live receiver — not fatal, the rows are already gone.
    try:
        store.db.execute("VACUUM")
    except sqlite3.OperationalError as e:
        print(f"[purge] VACUUM skipped ({e}) — rows are deleted; the file will "
              "reuse the space as new data arrives.")

    if args.log and truncate_log(LOG_PATH):
        print(f"[purge] truncated {os.path.abspath(LOG_PATH)}")

    store.close()
    print("[purge] store is empty — the next telemetry export starts a clean set.")


if __name__ == "__main__":
    main()
