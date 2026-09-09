"""Tests for billing/otel/bill.py -- task 05: honest actual-vs-estimated billing.

Covers the goal.md task-05 acceptance criteria:
  1/1b  golden byte-match for an OTLP-only store (regression gate)
  2     transcript-only store bills non-zero, labels rate-card
  3     mixed store bills the sum, states both portions
  4     markup applied exactly once
  5     --basis rates never re-rates already-rated (cost_usage) rows
  6     desktop-scratch gets its own ATTRIBUTION SOURCE line
  7     the double-billing (otlp + transcript) overlap detector
"""

from __future__ import annotations

import contextlib
import io
import re
from pathlib import Path

import pytest

from billing.otel import bill
from billing.otel.otel_store import OtelStore
from billing.otel.rating import RatingService

GOLDEN_PATH = (
    Path(__file__).parent / "golden" / "bill_otlp_baseline.txt"
)


def _run_bill(db_path: str, markup: float = 1.50, basis: str = "actual") -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bill.run(db=db_path, markup=markup, basis=basis)
    return buf.getvalue()


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n")


def _read_golden_normalized() -> str:
    with open(GOLDEN_PATH, "rb") as fh:
        raw = fh.read()
    return raw.decode("utf-8").replace("\r\n", "\n")


def _repo_block(output: str, repo: str) -> str:
    """Return just the printed block for one repo section (up to the next
    blank-line-prefixed repo header or the closing '=' rule)."""
    lines = output.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln == repo:
            start = i
            break
    assert start is not None, f"repo {repo!r} not found in output:\n{output}"
    end = start + 1
    while end < len(lines) and not lines[end].startswith("="):
        # a subsequent repo header is a bare name line following a blank line
        if (
            end > start + 1
            and lines[end - 1] == ""
            and lines[end]
            and not lines[end].startswith(" ")
        ):
            break
        end += 1
    return "\n".join(lines[start:end])


def _money(label: str, block: str) -> float:
    m = re.search(re.escape(label) + r"\s*\$\s*([\d,]+\.\d+)", block)
    assert m, f"{label!r} not found in block:\n{block}"
    return float(m.group(1).replace(",", ""))


# ---------------------------------------------------------------------------
# AC 1 / 1b -- golden byte-match for an OTLP-only store
# ---------------------------------------------------------------------------

def test_otlp_only_matches_golden_baseline(seeded_otlp_db_path):
    output = _run_bill(seeded_otlp_db_path, markup=1.50, basis="actual")
    golden = _read_golden_normalized()
    assert _normalize(output) == golden


def test_golden_baseline_file_is_lf_only():
    """Guards the fixture itself: the baseline must stay LF-only so a naive
    (non-normalizing) comparison failure is never blamed on this file."""
    raw = GOLDEN_PATH.read_bytes()
    assert b"\r\n" not in raw


# ---------------------------------------------------------------------------
# Fixture builders for desktop / mixed stores
# ---------------------------------------------------------------------------

DESKTOP_MODEL = "claude-sonnet-5"
DESKTOP_TOKENS = {"input": 100_000, "output": 40_000}


def _seed_desktop_rows(store: OtelStore, *, session_id: str, repo: str,
                       repo_raw: str, request_id: str, model=DESKTOP_MODEL,
                       tokens=None, nano=1_800_000_000_000_000_000) -> float:
    """Insert one desktop (transcript-sourced) request's worth of token_usage
    + cost_usage rows, mirroring transcript.map_record's convention exactly:
    cost_usage.cost_usd is the RAW (pre-markup) RatingService estimate, no
    markup applied. Returns that raw cost so tests can assert against it
    independently."""
    tokens = tokens if tokens is not None else DESKTOP_TOKENS
    rating = RatingService()  # markup default irrelevant -- raw_cost ignores it
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


def _seed_otlp_actual(store: OtelStore, *, session_id: str, repo: str,
                      repo_raw: str, model="claude-opus-4-8", cost_usd=10.0,
                      tokens=None, nano=1_700_000_000_000_000_000) -> None:
    tokens = tokens if tokens is not None else {"input": 100_000, "output": 20_000}
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


# ---------------------------------------------------------------------------
# AC 2 -- transcript-only store bills non-zero, labels rate-card
# ---------------------------------------------------------------------------

def test_transcript_only_store_bills_nonzero_and_labels_ratecard(tmp_path):
    db_path = str(tmp_path / "transcript_only.db")
    store = OtelStore(db_path)
    raw = _seed_desktop_rows(
        store, session_id="sess-desk-1", repo="github.com/cyclotron/acme-web",
        repo_raw="git@github.com:Cyclotron/Acme-Web.git", request_id="req-1",
    )
    store.close()

    output = _run_bill(db_path, markup=1.50, basis="actual")

    assert "RATE-CARD estimate" in output
    assert "ACTUAL cost from claude_code.cost.usage  x" not in output
    assert "MIXED" not in output

    m = re.search(r"GRAND TOTAL billed\s+\$\s*([\d,]+\.\d+)", output)
    assert m, output
    grand_billed = float(m.group(1).replace(",", ""))
    assert grand_billed > 0
    assert grand_billed == pytest.approx(raw * 1.50, rel=1e-6)


# ---------------------------------------------------------------------------
# AC 3 -- mixed store bills the sum of both, states both portions
# ---------------------------------------------------------------------------

def test_mixed_store_bills_sum_and_states_both_portions(tmp_path):
    db_path = str(tmp_path / "mixed.db")
    store = OtelStore(db_path)
    _seed_otlp_actual(
        store, session_id="sess-otlp-1", repo="github.com/cyclotron/acme-web",
        repo_raw="git@github.com:Cyclotron/Acme-Web.git", cost_usd=10.0,
    )
    raw_desktop = _seed_desktop_rows(
        store, session_id="sess-desk-1", repo="github.com/cyclotron/acme-web",
        repo_raw="git@github.com:Cyclotron/Acme-Web.git", request_id="req-1",
    )
    store.close()

    output = _run_bill(db_path, markup=1.50, basis="actual")

    assert "MIXED" in output
    # A mixed store must never be labelled simply "ACTUAL".
    basis_line = next(ln for ln in output.splitlines() if ln.startswith("basis:"))
    assert basis_line.strip() != "basis: ACTUAL cost from claude_code.cost.usage  x1.50 markup"

    block = _repo_block(output, "acme-web")
    actual_line = _money("actual (claude_code.cost.usage)", block)
    ratecard_line = _money("rate-card estimate (desktop)", block)
    cost_basis = _money("cost basis", block)
    billed = _money("BILLED (x1.50)", block)

    assert actual_line == pytest.approx(10.0, rel=1e-6)
    assert ratecard_line == pytest.approx(raw_desktop, rel=1e-6)
    assert cost_basis == pytest.approx(10.0 + raw_desktop, rel=1e-6)
    assert billed == pytest.approx((10.0 + raw_desktop) * 1.50, rel=1e-6)

    m = re.search(r"GRAND TOTAL billed\s+\$\s*([\d,]+\.\d+)", output)
    grand_billed = float(m.group(1).replace(",", ""))
    assert grand_billed == pytest.approx((10.0 + raw_desktop) * 1.50, rel=1e-6)


# ---------------------------------------------------------------------------
# AC 4 -- markup applied exactly once to a transcript row's billed figure
# ---------------------------------------------------------------------------

def test_markup_applied_exactly_once_for_desktop_row(tmp_path):
    db_path = str(tmp_path / "markup_once.db")
    store = OtelStore(db_path)
    raw = _seed_desktop_rows(
        store, session_id="sess-desk-2", repo="github.com/cyclotron/globex-api",
        repo_raw="git@github.com:Cyclotron/Globex-Api.git", request_id="req-2",
        model="claude-opus-4-8", tokens={"input": 200_000, "output": 10_000},
    )
    store.close()

    markup = 1.50
    rating = RatingService(markup=markup)
    expected_billed = (
        rating.billed("claude-opus-4-8", "input", 200_000)
        + rating.billed("claude-opus-4-8", "output", 10_000)
    )
    # Sanity: RatingService.billed() itself applies markup exactly once.
    assert expected_billed == pytest.approx(raw * markup, rel=1e-9)

    output = _run_bill(db_path, markup=markup, basis="actual")
    m = re.search(r"GRAND TOTAL billed\s+\$\s*([\d,]+\.\d+)", output)
    grand_billed = float(m.group(1).replace(",", ""))

    assert grand_billed == pytest.approx(expected_billed, rel=1e-6)
    # A double-apply bug (base * markup * markup) would produce this instead --
    # assert we are NOT anywhere near it.
    assert grand_billed != pytest.approx(raw * markup * markup, rel=1e-6)


# ---------------------------------------------------------------------------
# AC 5 -- --basis rates on a mixed store never re-rates cost_usage rows
# ---------------------------------------------------------------------------

def test_basis_rates_recomputes_from_tokens_not_cost_usage(tmp_path):
    """The sharpest correctness trap: seed a desktop cost_usage row with an
    obviously-wrong sentinel cost_usd (nothing like what RatingService would
    compute from the token counts). If bill.py's --basis rates path ever
    reads cost_usage for its estimate, this sentinel leaks into the total and
    the assertion below fails.
    """
    db_path = str(tmp_path / "basis_rates_trap.db")
    store = OtelStore(db_path)
    _seed_otlp_actual(
        store, session_id="sess-otlp-2", repo="github.com/cyclotron/acme-web",
        repo_raw="git@github.com:Cyclotron/Acme-Web.git", cost_usd=10.0,
        tokens={"input": 100_000, "output": 20_000},
    )
    model, tokens = "claude-sonnet-5", {"input": 100_000, "output": 40_000}
    request_id = "req-trap"
    session_id = "sess-desk-trap"
    repo = "github.com/cyclotron/acme-web"
    repo_raw = "git@github.com:Cyclotron/Acme-Web.git"
    nano = 1_800_000_000_000_000_000
    for token_type, tok in tokens.items():
        store.insert_datapoint(
            session_id=session_id, repo=repo, repo_raw=repo_raw,
            user_email="", user_id="", org_id="", model=model,
            token_type=token_type, query_source="main", tokens=tok,
            time_unix_nano=nano, usage_source="transcript",
            entrypoint="claude-desktop", request_id=request_id,
        )
    SENTINEL_COST = 999_999.0
    store.insert_cost_datapoint(
        session_id=session_id, repo=repo, repo_raw=repo_raw,
        user_email="", user_id="", org_id="", model=model,
        query_source="main", cost_usd=SENTINEL_COST, time_unix_nano=nano,
        usage_source="transcript", cost_source="rate_card", request_id=request_id,
    )
    store.commit()
    store.close()

    output = _run_bill(db_path, markup=1.50, basis="rates")

    rating = RatingService(markup=1.50)
    expected_billed = (
        rating.billed("claude-opus-4-8", "input", 100_000)
        + rating.billed("claude-opus-4-8", "output", 20_000)
        + rating.billed(model, "input", tokens["input"])
        + rating.billed(model, "output", tokens["output"])
    )

    m = re.search(r"GRAND TOTAL billed\s+\$\s*([\d,]+\.\d+)", output)
    grand_billed = float(m.group(1).replace(",", ""))
    assert grand_billed == pytest.approx(expected_billed, rel=1e-6)
    assert grand_billed < SENTINEL_COST  # sentinel never leaked in


# ---------------------------------------------------------------------------
# AC 6 -- desktop-scratch gets its own ATTRIBUTION SOURCE line
# ---------------------------------------------------------------------------

def test_desktop_scratch_line_in_attribution_source(tmp_path):
    db_path = str(tmp_path / "scratch.db")
    store = OtelStore(db_path)
    # A desktop session with NO billable repo (repo='unknown', repo_raw='')
    # and no timeline entry -> attribution_source='desktop-scratch'.
    _seed_desktop_rows(
        store, session_id="sess-scratch-1", repo="unknown", repo_raw="",
        request_id="req-scratch",
    )
    store.close()

    output = _run_bill(db_path, markup=1.50, basis="actual")

    lines = [ln for ln in output.splitlines() if ln.strip().startswith("desktop-scratch")]
    assert len(lines) == 1, output
    line = lines[0]
    # Not ragged-wrapped: the note text must appear on the SAME line as the
    # 'desktop-scratch' token, not pushed onto a continuation line.
    assert "desktop session with no billable repo" in line


def test_desktop_scratch_absent_for_otlp_only(seeded_otlp_db_path):
    output = _run_bill(seeded_otlp_db_path, markup=1.50, basis="actual")
    assert "desktop-scratch" not in output


# ---------------------------------------------------------------------------
# AC 7 -- double-billing (otlp + transcript) overlap detector
# ---------------------------------------------------------------------------

def test_overlap_session_triggers_warning(tmp_path):
    db_path = str(tmp_path / "overlap.db")
    store = OtelStore(db_path)
    overlap_session = "sess-overlap-1"
    repo = "github.com/cyclotron/acme-web"
    repo_raw = "git@github.com:Cyclotron/Acme-Web.git"
    # OTLP token row for this session...
    store.insert_datapoint(
        session_id=overlap_session, repo=repo, repo_raw=repo_raw,
        user_email="", user_id="", org_id="", model="claude-opus-4-8",
        token_type="input", query_source="main", tokens=1000,
        time_unix_nano=1_700_000_000_000_000_000,
    )
    # ...AND a transcript token row for the SAME session_id.
    store.insert_datapoint(
        session_id=overlap_session, repo=repo, repo_raw=repo_raw,
        user_email="", user_id="", org_id="", model="claude-sonnet-5",
        token_type="input", query_source="main", tokens=500,
        time_unix_nano=1_800_000_000_000_000_000, usage_source="transcript",
        entrypoint="claude-desktop", request_id="req-overlap",
    )
    store.commit()
    store.close()

    output = _run_bill(db_path, markup=1.50, basis="actual")

    assert "DOUBLE-BILLING RISK" in output
    assert overlap_session in output


def test_no_overlap_session_no_warning(tmp_path):
    db_path = str(tmp_path / "no_overlap.db")
    store = OtelStore(db_path)
    _seed_otlp_actual(
        store, session_id="sess-plain-otlp", repo="github.com/cyclotron/acme-web",
        repo_raw="git@github.com:Cyclotron/Acme-Web.git",
    )
    _seed_desktop_rows(
        store, session_id="sess-plain-desktop", repo="github.com/cyclotron/acme-web",
        repo_raw="git@github.com:Cyclotron/Acme-Web.git", request_id="req-plain",
    )
    store.close()

    output = _run_bill(db_path, markup=1.50, basis="actual")

    assert "DOUBLE-BILLING RISK" not in output


def test_overlap_detector_does_not_change_billed_total(tmp_path):
    """The overlap detector reports; it must not silently correct the total.

    The overlapping session carries a NON-ZERO desktop rate-card cost_usage
    row (not merely an unrated token row) -- so a detector that "corrects"
    the double-billing risk by subtracting the desktop portion for any
    session it flags would visibly change this total. A fixture where the
    overlapping session contributes $0 either way cannot distinguish "the
    detector reported and changed nothing" from "the detector reported and
    silently zeroed out the desktop estimate" -- this one can.
    """
    db_path = str(tmp_path / "overlap_total.db")
    store = OtelStore(db_path)
    overlap_session = "sess-overlap-2"
    repo = "github.com/cyclotron/acme-web"
    repo_raw = "git@github.com:Cyclotron/Acme-Web.git"

    # OTLP side of the overlap: actual cost_usage row.
    store.insert_datapoint(
        session_id=overlap_session, repo=repo, repo_raw=repo_raw,
        user_email="", user_id="", org_id="", model="claude-opus-4-8",
        token_type="input", query_source="main", tokens=100_000,
        time_unix_nano=1_700_000_000_000_000_000,
    )
    store.insert_cost_datapoint(
        session_id=overlap_session, repo=repo, repo_raw=repo_raw,
        user_email="", user_id="", org_id="", model="claude-opus-4-8",
        query_source="main", cost_usd=7.0, time_unix_nano=1_700_000_000_000_000_000,
    )

    # Transcript side of the SAME session_id -- a real desktop rate-card
    # cost_usage row, not just a bare token row, so it actually contributes
    # to the bill and a silent "correction" would be observable.
    desktop_model = "claude-sonnet-5"
    desktop_tokens = {"input": 200_000, "output": 30_000}
    rating = RatingService()
    raw_desktop_cost = sum(
        rating.raw_cost(desktop_model, tt, tok) for tt, tok in desktop_tokens.items()
    )
    assert raw_desktop_cost > 0
    nano2 = 1_800_000_000_000_000_000
    for token_type, tok in desktop_tokens.items():
        store.insert_datapoint(
            session_id=overlap_session, repo=repo, repo_raw=repo_raw,
            user_email="", user_id="", org_id="", model=desktop_model,
            token_type=token_type, query_source="main", tokens=tok,
            time_unix_nano=nano2, usage_source="transcript",
            entrypoint="claude-desktop", request_id="req-overlap-2",
        )
    store.insert_cost_datapoint(
        session_id=overlap_session, repo=repo, repo_raw=repo_raw,
        user_email="", user_id="", org_id="", model=desktop_model,
        query_source="main", cost_usd=raw_desktop_cost, time_unix_nano=nano2,
        usage_source="transcript", cost_source="rate_card", request_id="req-overlap-2",
    )
    store.commit()
    store.close()

    output = _run_bill(db_path, markup=1.50, basis="actual")

    # The overlap really is detected here (sanity check the fixture itself).
    assert "DOUBLE-BILLING RISK" in output
    assert overlap_session in output

    m = re.search(r"GRAND TOTAL billed\s+\$\s*([\d,]+\.\d+)", output)
    grand_billed = float(m.group(1).replace(",", ""))
    expected = (7.0 + raw_desktop_cost) * 1.50
    # If the detector ever silently subtracted the desktop rate-card portion
    # for a flagged session, grand_billed would come back as 7.0 * 1.50
    # instead -- strictly less than `expected`.
    assert grand_billed == pytest.approx(expected, rel=1e-6)
    assert grand_billed != pytest.approx(7.0 * 1.50, rel=1e-6)
