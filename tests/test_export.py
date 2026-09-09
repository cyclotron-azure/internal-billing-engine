"""Tests for billing/otel/export.py -- the lake CSV builder.

No task in this goal owns export.py, but task 04's `attribution_source`
change put it at risk: `export.py:78` calls `resolved_view('cost_usage')`,
the same prepare-time-failure risk task 04's own tests cover for an
OTLP-only store. This task (07, the closer) is the first to exercise
export.py against a MIXED (OTLP + desktop transcript) store, and pins:

  - both lake CSVs still build after every change in this goal
  - transcript-sourced rows appear in them with correct UTC date columns
  - export.py currently emits NO `cost_source` column (goal.md's accepted
    Out of Scope: rate-card estimates and Anthropic actuals are
    indistinguishable downstream in Fabric) -- pinned here so a future
    change to that is deliberate and visible, not accidental.

Every database is a tmp_path file; nothing reaches ADLS Gen2 / OneLake /
Fabric (store.fabric_enqueue only writes a local outbox row -- no network).
"""

from __future__ import annotations

import csv
import os

import pytest

from billing.otel import export
from billing.otel.otel_store import OtelStore
from billing.otel.rating import RatingService

from tests.conftest import seed_otlp_rows

DESKTOP_SESSION = "sess-export-desktop"
DESKTOP_MODEL = "claude-sonnet-5"
DESKTOP_TOKENS = {"input": 20_000, "output": 8_000, "cacheRead": 1_000, "cacheCreation": 500}
DESKTOP_NANO = 1_767_312_000_000_000_000  # 2026-01-02T00:00:00Z
DESKTOP_USER_EMAIL = "dev@cyclotron.com"


def _seed_desktop_row(store: OtelStore) -> float:
    """One desktop (transcript-sourced) request's worth of rows, mirroring
    transcript.map_record's convention: cost_usage.cost_usd is the RAW
    (pre-markup) RatingService estimate. Returns that raw cost."""
    rating = RatingService()
    raw = 0.0
    for token_type, tok in DESKTOP_TOKENS.items():
        store.insert_datapoint(
            session_id=DESKTOP_SESSION, repo="github.com/cyclotron/acme-web",
            repo_raw="git@github.com:Cyclotron/Acme-Web.git",
            user_email=DESKTOP_USER_EMAIL, user_id="u-dev", org_id="org-cyclotron",
            model=DESKTOP_MODEL, token_type=token_type, query_source="main",
            tokens=tok, time_unix_nano=DESKTOP_NANO, usage_source="transcript",
            entrypoint="claude-desktop", request_id="req-export-desktop",
        )
        raw += rating.raw_cost(DESKTOP_MODEL, token_type, tok)
    store.insert_cost_datapoint(
        session_id=DESKTOP_SESSION, repo="github.com/cyclotron/acme-web",
        repo_raw="git@github.com:Cyclotron/Acme-Web.git",
        user_email=DESKTOP_USER_EMAIL, user_id="u-dev", org_id="org-cyclotron",
        model=DESKTOP_MODEL, query_source="main", cost_usd=raw,
        time_unix_nano=DESKTOP_NANO, usage_source="transcript",
        cost_source="rate_card", request_id="req-export-desktop",
    )
    store.commit()
    return raw


@pytest.fixture
def mixed_export_db(tmp_path) -> str:
    path = str(tmp_path / "export_mixed.db")
    store = OtelStore(path)
    seed_otlp_rows(store)
    _seed_desktop_row(store)
    store.close()
    return path


def _read_csv(path: str):
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        return reader.fieldnames, rows


# ---------------------------------------------------------------------------
# Both lake CSVs still build after every change in this goal.
# ---------------------------------------------------------------------------

def test_both_lake_csvs_build_for_mixed_store(mixed_export_db, tmp_path):
    store = OtelStore(mixed_export_db)
    out_dir = str(tmp_path / "exports")
    ns, nl = export.build_and_enqueue(store, markup=1.50, out_dir=out_dir)
    store.close()

    summary_path = os.path.join(out_dir, f"{export.SUMMARY_TABLE}.csv")
    lineitems_path = os.path.join(out_dir, f"{export.LINEITEMS_TABLE}.csv")
    assert os.path.exists(summary_path)
    assert os.path.exists(lineitems_path)
    assert ns > 0
    assert nl > 0

    header, rows = _read_csv(summary_path)
    assert header == export.SUMMARY_FIELDS
    assert len(rows) == ns

    header2, rows2 = _read_csv(lineitems_path)
    assert header2 == export.LINE_FIELDS
    assert len(rows2) == nl


def test_csvs_are_enqueued_for_fabric_delivery_not_uploaded_directly(mixed_export_db, tmp_path):
    """build_and_enqueue must not reach ADLS/OneLake itself -- it only writes
    a local outbox row for billing.otel.fabric_sync to drain later."""
    store = OtelStore(mixed_export_db)
    out_dir = str(tmp_path / "exports_outbox")
    export.build_and_enqueue(store, markup=1.50, out_dir=out_dir)

    counts = store.fabric_outbox_counts()
    store.close()
    assert counts.get("pending", 0) == 2  # summary + line items


# ---------------------------------------------------------------------------
# Transcript-sourced rows appear with correct UTC date columns.
# ---------------------------------------------------------------------------

def test_transcript_rows_appear_with_correct_utc_date_columns(mixed_export_db, tmp_path):
    store = OtelStore(mixed_export_db)
    out_dir = str(tmp_path / "exports2")
    export.build_and_enqueue(store, markup=1.50, out_dir=out_dir)
    store.close()

    _, rows = _read_csv(os.path.join(out_dir, f"{export.LINEITEMS_TABLE}.csv"))
    desktop_rows = [r for r in rows if r["user_email"] == DESKTOP_USER_EMAIL]
    assert desktop_rows, rows
    for r in desktop_rows:
        assert r["usage_date_utc"] == "2026-01-02"
        assert r["first_usage_at_utc"].startswith("2026-01-02T")
        assert r["last_usage_at_utc"].startswith("2026-01-02T")
        assert r["first_usage_at_utc"].endswith("Z")
        assert r["last_usage_at_utc"].endswith("Z")
        assert r["period_start"] == "2026-01-01"
        assert r["period_end"] == "2026-02-01"
        assert r["repo"] == "acme-web"
        assert r["model"] == DESKTOP_MODEL

    _, summary_rows = _read_csv(os.path.join(out_dir, f"{export.SUMMARY_TABLE}.csv"))
    desktop_summary = [r for r in summary_rows if r["user_email"] == DESKTOP_USER_EMAIL]
    assert desktop_summary, summary_rows
    for r in desktop_summary:
        assert r["usage_date_utc"] == "2026-01-02"
        assert r["period_start"] == "2026-01-01"
        assert r["period_end"] == "2026-02-01"


def test_transcript_row_token_and_cost_totals_are_correct_in_lineitems(mixed_export_db, tmp_path):
    store = OtelStore(mixed_export_db)
    out_dir = str(tmp_path / "exports_totals")
    export.build_and_enqueue(store, markup=1.50, out_dir=out_dir)
    store.close()

    _, rows = _read_csv(os.path.join(out_dir, f"{export.LINEITEMS_TABLE}.csv"))
    desktop_row = next(r for r in rows if r["user_email"] == DESKTOP_USER_EMAIL)
    assert int(desktop_row["tokens"]) == sum(DESKTOP_TOKENS.values())

    rating = RatingService()
    raw = sum(rating.raw_cost(DESKTOP_MODEL, tt, tok) for tt, tok in DESKTOP_TOKENS.items())
    # build() rounds to 6 decimal places for the CSV -- compare with a small
    # absolute tolerance so that rounding, not a real drift, is what's allowed.
    assert float(desktop_row["actual_cost_usd"]) == pytest.approx(raw, abs=1e-6)
    assert float(desktop_row["billed_usd"]) == pytest.approx(raw * 1.50, abs=1e-6)


# ---------------------------------------------------------------------------
# export.py currently emits NO cost_source column -- pinned Out of Scope
# state (goal.md), so a future change to it is deliberate, not accidental.
# ---------------------------------------------------------------------------

def test_export_emits_no_cost_source_column_pinned_out_of_scope(mixed_export_db, tmp_path):
    """goal.md lists surfacing cost_source in the lake CSVs as accepted Out
    of Scope: estimates (rate-card, desktop) and actuals (OTLP) are
    indistinguishable downstream in Fabric today. This test pins that state
    explicitly so a later change to it is a deliberate, visible edit to this
    assertion rather than a silent regression."""
    store = OtelStore(mixed_export_db)
    out_dir = str(tmp_path / "exports3")
    export.build_and_enqueue(store, markup=1.50, out_dir=out_dir)
    store.close()

    header_s, _ = _read_csv(os.path.join(out_dir, f"{export.SUMMARY_TABLE}.csv"))
    header_l, _ = _read_csv(os.path.join(out_dir, f"{export.LINEITEMS_TABLE}.csv"))

    assert "cost_source" not in header_s
    assert "cost_source" not in header_l
    assert set(header_s) == set(export.SUMMARY_FIELDS)
    assert set(header_l) == set(export.LINE_FIELDS)

    # Both actual (OTLP) and rate-card (desktop) dollars land in the SAME
    # actual_cost_usd / billed_usd / total_billed_usd columns -- there is no
    # column split telling them apart downstream, which is exactly the risk
    # this test pins as an accepted, visible state.
    assert "actual_cost_usd" in header_l and "billed_usd" in header_l
    assert "actual_cost_usd" in header_s and "total_billed_usd" in header_s


# ---------------------------------------------------------------------------
# resolved_view('cost_usage') prepare-time risk (export.py:78), repeated here
# for an OTLP-only store: no task in this goal owns export.py, so it must
# not silently regress even though test_attribute.py already covers this
# exact risk for bill.py.
# ---------------------------------------------------------------------------

def test_export_runs_against_otlp_only_store(seeded_otlp_db_path, tmp_path):
    store = OtelStore(seeded_otlp_db_path)
    out_dir = str(tmp_path / "exports_otlp_only")
    ns, nl = export.build_and_enqueue(store, markup=1.50, out_dir=out_dir)
    store.close()
    assert ns > 0
    assert nl > 0

    header_s, _ = _read_csv(os.path.join(out_dir, f"{export.SUMMARY_TABLE}.csv"))
    header_l, _ = _read_csv(os.path.join(out_dir, f"{export.LINEITEMS_TABLE}.csv"))
    assert header_s == export.SUMMARY_FIELDS
    assert header_l == export.LINE_FIELDS
