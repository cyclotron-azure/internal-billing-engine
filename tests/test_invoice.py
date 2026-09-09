"""Tests for billing/otel/invoice.py -- task 05: honest actual-vs-estimated
invoicing.

Covers the goal.md task-05 acceptance criteria:
  8   the .txt distinguishes actual from estimated cost
  8b  summary.csv / line_items.csv never report a rate-card estimate under a
      column named as actual cost
  9   invoice regeneration semantics (DELETE + INSERT OR REPLACE) are
      untouched
"""

from __future__ import annotations

import csv
import re

import pytest

from billing.otel import invoice
from billing.otel.otel_store import OtelStore
from billing.otel.rating import RatingService

PERIOD_START = "2026-01-01"
PERIOD_END = "2026-02-01"
TS = "2026-01-15T00:00:00Z"


def _nano_for(ts: str) -> int:
    # invoice.gather() only ever compares substr(ts,1,10), so any nanosecond
    # value that stringifies (via OtelStore._ns_to_iso) into a ts starting
    # with PERIOD_START's date range is fine. We use fixed literals instead.
    return 1_767_225_600_000_000_000  # 2026-01-01T00:00:00Z


def _seed_actual(store: OtelStore, *, session_id, repo, repo_raw, model, cost_usd,
                 tokens):
    nano = _nano_for(TS)
    for token_type, tok in tokens.items():
        store.insert_datapoint(
            session_id=session_id, repo=repo, repo_raw=repo_raw,
            user_email="", user_id="", org_id="", model=model,
            token_type=token_type, query_source="main", tokens=tok,
            time_unix_nano=nano,
        )
    store.insert_cost_datapoint(
        session_id=session_id, repo=repo, repo_raw=repo_raw,
        user_email="", user_id="", org_id="", model=model,
        query_source="main", cost_usd=cost_usd, time_unix_nano=nano,
    )
    store.commit()


def _seed_desktop(store: OtelStore, *, session_id, repo, repo_raw, model, tokens,
                  request_id):
    nano = _nano_for(TS)
    rating = RatingService()
    raw_cost = 0.0
    for token_type, tok in tokens.items():
        store.insert_datapoint(
            session_id=session_id, repo=repo, repo_raw=repo_raw,
            user_email="", user_id="", org_id="", model=model,
            token_type=token_type, query_source="main", tokens=tok,
            time_unix_nano=nano, usage_source="transcript",
            entrypoint="claude-desktop", request_id=request_id,
        )
        raw_cost += rating.raw_cost(model, token_type, tok)
    store.insert_cost_datapoint(
        session_id=session_id, repo=repo, repo_raw=repo_raw,
        user_email="", user_id="", org_id="", model=model,
        query_source="main", cost_usd=raw_cost, time_unix_nano=nano,
        usage_source="transcript", cost_source="rate_card", request_id=request_id,
    )
    store.commit()
    return raw_cost


def _read_csv(path) -> list[dict]:
    with open(path, "r", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture
def mixed_store_db(tmp_path):
    db_path = str(tmp_path / "invoice_mixed.db")
    store = OtelStore(db_path)
    _seed_actual(
        store, session_id="sess-otlp-1", repo="github.com/cyclotron/acme-web",
        repo_raw="git@github.com:Cyclotron/Acme-Web.git", model="claude-opus-4-8",
        cost_usd=10.0, tokens={"input": 100_000, "output": 20_000},
    )
    raw_desktop = _seed_desktop(
        store, session_id="sess-desk-1", repo="github.com/cyclotron/acme-web",
        repo_raw="git@github.com:Cyclotron/Acme-Web.git", model="claude-sonnet-5",
        tokens={"input": 100_000, "output": 40_000}, request_id="req-1",
    )
    store.close()
    return db_path, raw_desktop


# ---------------------------------------------------------------------------
# AC 8 -- .txt distinguishes actual from estimated cost
# ---------------------------------------------------------------------------

def _line_starting_with(text: str, label: str) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip().startswith(label)]
    assert len(lines) == 1, f"expected exactly one line starting with {label!r}, got {lines!r}"
    return lines[0]


def _sole_money(line: str) -> float:
    vals = re.findall(r"\$\s*([\d,]+\.\d+)", line)
    assert len(vals) == 1, f"expected exactly one $ figure on line {line!r}, got {vals!r}"
    return float(vals[0].replace(",", ""))


def _line_containing(text: str, needle: str) -> str:
    lines = [ln for ln in text.splitlines() if needle in ln]
    assert len(lines) == 1, f"expected exactly one line containing {needle!r}, got {lines!r}"
    return lines[0]


def test_txt_distinguishes_actual_from_estimated(mixed_store_db, tmp_path):
    db_path, raw_desktop = mixed_store_db
    out_dir = str(tmp_path / "out")
    invoice.run(PERIOD_START, PERIOD_END, markup=1.50, db=db_path, out_dir=out_dir)

    txt_path = f"{out_dir}/INV-{PERIOD_START}-acme-web.txt"
    with open(txt_path, "r", encoding="utf-8") as fh:
        text = fh.read()

    assert "Subtotal (Anthropic actual cost)" in text
    assert "Subtotal (rate-card estimate, desktop)" in text

    # Bind each figure to ITS OWN label's line -- a free-floating substring
    # check would still pass if the two subtotals' numbers were swapped, or
    # if the "actual" subtotal silently included the estimate (the exact
    # mislabelling this task exists to prevent: a rate-card figure printed
    # as Anthropic's reported cost on a client invoice).
    actual_subtotal = _sole_money(_line_starting_with(text, "Subtotal (Anthropic actual cost)"))
    estimated_subtotal = _sole_money(
        _line_starting_with(text, "Subtotal (rate-card estimate, desktop)"))
    assert actual_subtotal == pytest.approx(10.0, abs=1e-9)
    assert actual_subtotal != pytest.approx(10.0 + raw_desktop, abs=1e-9)
    assert estimated_subtotal == pytest.approx(raw_desktop, abs=1e-9)

    # Per-line-item columns: the sonnet-5 (desktop, rate-card-only) row must
    # show $0.0000 under Actual and the full estimate under Est.(rate-card) --
    # not the estimate folded into the Actual column.
    sonnet_line = _line_containing(text, "claude-sonnet-5")
    sonnet_values = [float(v.replace(",", "")) for v in
                     re.findall(r"\$\s*([\d,]+\.\d+)", sonnet_line)]
    assert len(sonnet_values) == 3, sonnet_line  # Actual, Est.(rate-card), Billed
    sonnet_actual, sonnet_estimated, sonnet_billed = sonnet_values
    assert sonnet_actual == pytest.approx(0.0, abs=1e-9)
    assert sonnet_estimated == pytest.approx(raw_desktop, abs=1e-9)
    assert sonnet_billed == pytest.approx(raw_desktop * 1.50, rel=1e-6)

    opus_line = _line_containing(text, "claude-opus-4-8")
    opus_values = [float(v.replace(",", "")) for v in
                   re.findall(r"\$\s*([\d,]+\.\d+)", opus_line)]
    assert len(opus_values) == 3, opus_line
    opus_actual, opus_estimated, opus_billed = opus_values
    assert opus_actual == pytest.approx(10.0, abs=1e-9)
    assert opus_estimated == pytest.approx(0.0, abs=1e-9)
    assert opus_billed == pytest.approx(10.0 * 1.50, rel=1e-6)

    # The client-facing bottom line: TOTAL DUE must be the BILLED total
    # (actual + estimated, marked up) -- not the pre-markup cost basis. This
    # is the number a client actually pays, and the estimate-branch table has
    # its own copy of this line (see write_invoice_text) that can drift from
    # the actual-only branch's copy independently.
    total_due = _sole_money(_line_starting_with(text, "TOTAL DUE (USD)"))
    assert total_due == pytest.approx((10.0 + raw_desktop) * 1.50, rel=1e-6)
    assert total_due != pytest.approx(10.0 + raw_desktop, rel=1e-6)  # not the cost basis


def test_txt_actual_only_store_has_no_estimate_subtotal(tmp_path):
    db_path = str(tmp_path / "actual_only.db")
    store = OtelStore(db_path)
    _seed_actual(
        store, session_id="sess-otlp-2", repo="github.com/cyclotron/globex-api",
        repo_raw="git@github.com:Cyclotron/Globex-Api.git", model="claude-opus-4-8",
        cost_usd=20.0, tokens={"input": 150_000, "output": 80_000},
    )
    store.close()

    out_dir = str(tmp_path / "out")
    invoice.run(PERIOD_START, PERIOD_END, markup=1.50, db=db_path, out_dir=out_dir)

    txt_path = f"{out_dir}/INV-{PERIOD_START}-globex-api.txt"
    with open(txt_path, "r", encoding="utf-8") as fh:
        text = fh.read()

    assert "Subtotal (rate-card estimate, desktop)" not in text
    assert "Subtotal (Anthropic actual cost)" in text

    # Pin the actual-only branch's OWN copy of TOTAL DUE too -- the
    # estimate branch and this (no-estimate) branch each carry an
    # independent copy of this line, so it can drift out of sync with the
    # billed total in either branch without the other test noticing.
    total_due = _sole_money(_line_starting_with(text, "TOTAL DUE (USD)"))
    assert total_due == pytest.approx(20.0 * 1.50, rel=1e-6)
    assert total_due != pytest.approx(20.0, rel=1e-6)  # not the (unmarked-up) cost basis


# ---------------------------------------------------------------------------
# AC 8b -- summary.csv / line_items.csv never mislabel an estimate as actual
# ---------------------------------------------------------------------------

def test_summary_csv_splits_actual_and_estimated(mixed_store_db, tmp_path):
    db_path, raw_desktop = mixed_store_db
    out_dir = str(tmp_path / "out")
    invoice.run(PERIOD_START, PERIOD_END, markup=1.50, db=db_path, out_dir=out_dir)

    rows = _read_csv(f"{out_dir}/summary.csv")
    assert len(rows) == 1
    row = rows[0]
    assert "estimated_cost_usd" in row
    actual = float(row["actual_cost_usd"])
    estimated = float(row["estimated_cost_usd"])
    total_billed = float(row["total_billed_usd"])

    # The estimate must not have been folded into the actual_cost_usd column.
    assert actual == pytest.approx(10.0, rel=1e-6)
    assert estimated == pytest.approx(raw_desktop, rel=1e-6)
    assert total_billed == pytest.approx((10.0 + raw_desktop) * 1.50, rel=1e-6)


def test_line_items_csv_splits_actual_and_estimated(mixed_store_db, tmp_path):
    db_path, raw_desktop = mixed_store_db
    out_dir = str(tmp_path / "out")
    invoice.run(PERIOD_START, PERIOD_END, markup=1.50, db=db_path, out_dir=out_dir)

    rows = _read_csv(f"{out_dir}/line_items.csv")
    assert "estimated_cost_usd" in rows[0]

    by_model = {r["model"]: r for r in rows}
    assert float(by_model["claude-opus-4-8"]["actual_cost_usd"]) == pytest.approx(10.0, rel=1e-6)
    assert float(by_model["claude-opus-4-8"]["estimated_cost_usd"]) == pytest.approx(0.0, abs=1e-9)
    assert float(by_model["claude-sonnet-5"]["actual_cost_usd"]) == pytest.approx(0.0, abs=1e-9)
    assert float(by_model["claude-sonnet-5"]["estimated_cost_usd"]) == pytest.approx(
        raw_desktop, rel=1e-6)

    # billed_usd must reflect BOTH portions for every line, not just
    # actual_cost -- a rate-card-only line (claude-sonnet-5 here) must still
    # bill non-zero, and at (actual + estimated) * markup exactly.
    assert float(by_model["claude-opus-4-8"]["billed_usd"]) == pytest.approx(
        10.0 * 1.50, rel=1e-6)
    assert float(by_model["claude-sonnet-5"]["billed_usd"]) == pytest.approx(
        raw_desktop * 1.50, rel=1e-6)
    assert float(by_model["claude-sonnet-5"]["billed_usd"]) > 0


def test_summary_csv_no_estimate_for_actual_only_store(tmp_path):
    db_path = str(tmp_path / "actual_only2.db")
    store = OtelStore(db_path)
    _seed_actual(
        store, session_id="sess-otlp-3", repo="github.com/cyclotron/globex-api",
        repo_raw="git@github.com:Cyclotron/Globex-Api.git", model="claude-opus-4-8",
        cost_usd=20.0, tokens={"input": 150_000, "output": 80_000},
    )
    store.close()
    out_dir = str(tmp_path / "out")
    invoice.run(PERIOD_START, PERIOD_END, markup=1.50, db=db_path, out_dir=out_dir)

    rows = _read_csv(f"{out_dir}/summary.csv")
    assert float(rows[0]["estimated_cost_usd"]) == pytest.approx(0.0, abs=1e-9)
    assert float(rows[0]["actual_cost_usd"]) == pytest.approx(20.0, rel=1e-6)


# ---------------------------------------------------------------------------
# Billing correctness -- desktop usage actually bills through invoicing too
# ---------------------------------------------------------------------------

def test_desktop_usage_bills_nonzero_in_invoice(tmp_path):
    db_path = str(tmp_path / "desktop_only_invoice.db")
    store = OtelStore(db_path)
    raw_desktop = _seed_desktop(
        store, session_id="sess-desk-only", repo="github.com/cyclotron/acme-web",
        repo_raw="git@github.com:Cyclotron/Acme-Web.git", model="claude-sonnet-5",
        tokens={"input": 100_000, "output": 40_000}, request_id="req-only",
    )
    store.close()

    out_dir = str(tmp_path / "out")
    invoice.run(PERIOD_START, PERIOD_END, markup=1.50, db=db_path, out_dir=out_dir)

    rows = _read_csv(f"{out_dir}/summary.csv")
    assert len(rows) == 1
    assert float(rows[0]["total_billed_usd"]) == pytest.approx(raw_desktop * 1.50, rel=1e-6)
    assert float(rows[0]["total_billed_usd"]) > 0


# ---------------------------------------------------------------------------
# AC 9 -- regeneration semantics (DELETE + INSERT OR REPLACE) untouched
# ---------------------------------------------------------------------------

def test_regeneration_replaces_line_items_in_place(mixed_store_db, tmp_path):
    db_path, raw_desktop = mixed_store_db
    out_dir = str(tmp_path / "out")
    invoice.run(PERIOD_START, PERIOD_END, markup=1.50, db=db_path, out_dir=out_dir)

    store = OtelStore(db_path)
    invoice_number = f"INV-{PERIOD_START}-acme-web"
    first_count = store.db.execute(
        "SELECT COUNT(*) c FROM invoice_line_items WHERE invoice_number = ?",
        (invoice_number,)).fetchone()["c"]
    first_row = store.db.execute(
        "SELECT * FROM invoices WHERE invoice_number = ?", (invoice_number,)
    ).fetchone()
    assert first_row is not None
    store.close()

    # Regenerate for the exact same period -- must replace, not duplicate.
    invoice.run(PERIOD_START, PERIOD_END, markup=1.50, db=db_path, out_dir=out_dir)

    store = OtelStore(db_path)
    second_count = store.db.execute(
        "SELECT COUNT(*) c FROM invoice_line_items WHERE invoice_number = ?",
        (invoice_number,)).fetchone()["c"]
    invoice_rows = store.db.execute(
        "SELECT COUNT(*) c FROM invoices WHERE invoice_number = ?",
        (invoice_number,)).fetchone()["c"]
    store.close()

    assert second_count == first_count  # replaced, not appended/duplicated
    assert invoice_rows == 1            # INSERT OR REPLACE, not a second row
