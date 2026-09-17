"""Task 07 (closer): end-to-end desktop path integration tests.

Every task 00-06 tested its own seam in isolation. This file is the only one
that drives the WHOLE desktop path in-process -- task 00's synthetic projects
tree -> the real client hook (`deploy/claude-transcript-usage.py`, imported by
file path exactly as `tests/test_transcript_hook.py` does) -> the real
server-side validator (`billing.otel.transcript.validate_batch`, invoked
inside `receiver.ingest_transcript_usage_payload`, the same function
`Handler.do_POST` calls -- only the HTTP framing itself is skipped, and that
framing is already covered end-to-end in `tests/test_receiver.py`) -> the
store -> `billing.otel.bill`.

Also covers the four requirements routed here because no single task's tests
could reach them: the `_FIRST` attribution arm, the systemic-failure alarm,
the `transcript_key` stripping contract, and the cross-task `_mark_resolved`
key seam (seeded and asserted, NOT fixed -- see that test's docstring).

No test binds a real port or reaches a live service. Every database is a
`tmp_path` file. The one non-mocked external process is a local `git`
subprocess the hook itself shells out to for repo resolution (identical to
`tests/test_transcript_hook.py`'s convention): fixture `cwd` values point at
paths that do not exist on the test machine, so it exits non-zero and
`repo_raw` comes back `''` -- exercised, not networked.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from billing.otel import attribute, bill, receiver
from billing.otel.otel_store import OtelStore, transcript_key
from billing.otel.rating import RatingService

from tests.conftest import (
    DUPLICATE_CACHE_CREATION,
    DUPLICATE_CACHE_READ,
    DUPLICATE_INPUT,
    DUPLICATE_OUTPUT,
    EXPECTED_COMBINED_TOTAL_TOKENS,
    EXPECTED_MAIN_ONLY_TOTAL_TOKENS,
    MULTI_BLOCK_CACHE_CREATION,
    MULTI_BLOCK_CACHE_READ,
    MULTI_BLOCK_INPUT,
    MULTI_BLOCK_OUTPUT_PARTIAL,
    MULTI_BLOCK_OUTPUT_TERMINAL,
    SEEDED_SESSIONS,
    SESSION_A_ID,
    SIDECHAIN_CACHE_CREATION,
    SIDECHAIN_CACHE_READ,
    SIDECHAIN_INPUT,
    SIDECHAIN_OUTPUT,
    _usage_row,
    seed_otlp_rows,
)

DESKTOP_MODEL = "claude-sonnet-5"  # every projects_tree row's model (conftest default)
MARKUP = 1.50

_HOOK_PATH = Path(__file__).resolve().parents[1] / "deploy" / "claude-transcript-usage.py"


@pytest.fixture(scope="module")
def hook():
    """The real client hook, imported by file path -- it is standalone and
    stdlib-only, and cannot be imported as a package (see its own docstring)."""
    spec = importlib.util.spec_from_file_location(
        "claude_transcript_usage_hook_integration", _HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Small local helpers (mirrors of tests/test_transcript_hook.py's own, kept
# local rather than imported so this file's write fence stays self-contained)
# ---------------------------------------------------------------------------

def _soon() -> datetime:
    """`now` a couple of seconds after the wall clock -- paired with
    idle_threshold_seconds=0 so every trailing group in a freshly-written
    fixture file is unambiguously idle-elapsed regardless of filesystem mtime
    resolution."""
    return datetime.now(timezone.utc) + timedelta(seconds=2)


def _seed_epoch_install(state_path: Path) -> None:
    """Pre-seed the hook's state file so its forward-only install watermark
    (which on a real first run is set from wall-clock time) does not filter
    out these fixtures' 2026-01-0x timestamps, which sit in the past relative
    to the real clock this test suite runs under."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        "install_ts": "1970-01-01T00:00:00.000000Z",
        "files": {}, "envelope_retries": {}, "drops": [],
    }), encoding="utf-8")


def _run_bill(db_path: str, markup: float = MARKUP, basis: str = "actual") -> str:
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bill.run(db=db_path, markup=markup, basis=basis)
    return buf.getvalue()


def _grand_billed(output: str) -> float:
    m = re.search(r"GRAND TOTAL billed\s+\$\s*([\d,]+\.\d+)", output)
    assert m, output
    return float(m.group(1).replace(",", ""))


def _make_real_post_batch(store: OtelStore, sink: list | None = None):
    """A hook `post_batch` wired to the REAL receiver ingest function --
    `receiver.ingest_transcript_usage_payload` is exactly what
    `Handler.do_POST` calls for `/v1/transcript-usage`; only the HTTP
    request/response framing around it is skipped here (that framing is
    covered end to end in `tests/test_receiver.py`'s in-process socket
    harness). This drives the real `validate_batch` and the real store
    inserts -- never a stub of either."""
    def _post(records):
        result = receiver.ingest_transcript_usage_payload(records, store)
        if sink is not None:
            sink.append(result)
        return "ok", 200, result
    return _post


# ---------------------------------------------------------------------------
# Requirement 1 -- discriminate _FIRST from _AS_OF in the attribution join.
#
# A datapoint whose ts PRECEDES every timeline entry for its session must
# resolve via _FIRST (the session's earliest timeline entry), not fall
# through to the wrapper tag. Two DIFFERENT timeline entries are seeded, both
# strictly AFTER the datapoint's ts, so _AS_OF (latest entry <= ts) can never
# match for either -- only _FIRST (earliest entry, unconditional on ts) can
# resolve this row at all.
# ---------------------------------------------------------------------------

FIRST_ARM_SESSION = "sess-first-arm-precedes-timeline"
FIRST_ARM_REAL_REPO = "github.com/cyclotron/acme-web"
FIRST_ARM_WRAPPER_REPO = "github.com/cyclotron/wrapper-tag-only"


def _seed_first_arm_fixture(store: OtelStore) -> None:
    sid = FIRST_ARM_SESSION
    # Two DISTINCT timeline entries, both after the datapoint's ts (below).
    store.insert_session_repo(
        session_id=sid, ts="2026-01-05T00:00:10Z", seq=0,
        repo=FIRST_ARM_REAL_REPO, repo_raw="git@github.com:Cyclotron/Acme-Web.git",
        cwd="/home/dev/acme-web", event="SessionStart",
    )
    store.insert_session_repo(
        session_id=sid, ts="2026-01-05T00:01:00Z", seq=0,
        repo="github.com/cyclotron/globex-api", repo_raw="git@github.com:Cyclotron/Globex-Api.git",
        cwd="/home/dev/globex-api", event="CwdChanged",
    )
    dp_ts = datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone.utc)
    nano = int(dp_ts.timestamp() * 1_000_000_000)
    # The wrapper's launch-time tag -- deliberately a THIRD, distinct repo, so
    # a fall-through to it is unmistakable from a correct _FIRST resolution.
    store.insert_datapoint(
        session_id=sid, repo=FIRST_ARM_WRAPPER_REPO,
        repo_raw="git@github.com:Cyclotron/Wrapper-Tag-Only.git",
        user_email="dev@cyclotron.com", user_id="u-dev", org_id="org-cyclotron",
        model="claude-sonnet-5", token_type="input", query_source="main",
        tokens=100, time_unix_nano=nano,
    )
    store.commit()


def _fetch_first_arm_row(store: OtelStore) -> sqlite3.Row:
    return store.db.execute(
        f"WITH r AS ({attribute.resolved_view('token_usage')}) "
        "SELECT resolved_repo, attribution_source FROM r WHERE session_id=?",
        (FIRST_ARM_SESSION,),
    ).fetchone()


def test_first_arm_resolves_datapoint_preceding_all_timeline_entries(tmp_db_path):
    """A datapoint whose ts PRECEDES every timeline entry for its session
    resolves via _FIRST (the earliest entry) -- attribute.py's own docstring
    says this arm exists for 'export-interval rounding, small clock skew'."""
    store = OtelStore(tmp_db_path)
    _seed_first_arm_fixture(store)
    row = _fetch_first_arm_row(store)
    assert row["resolved_repo"] == FIRST_ARM_REAL_REPO  # the EARLIEST entry
    assert row["resolved_repo"] != FIRST_ARM_WRAPPER_REPO  # not a fall-through
    assert row["attribution_source"] == "timeline"
    store.close()


def test_first_arm_mutation_check_neutering_first_falls_through_to_wrapper(
    tmp_db_path, monkeypatch
):
    """Companion proof for the test above, satisfying this task's stated
    acceptance: 'mutating _FIRST to NULL must turn this test red.'

    Rather than hand-editing the production module (out of this task's write
    fence -- attribute.py belongs to task 04), the mutation is performed with
    `monkeypatch` against the SAME fixture the previous test uses: with
    `_FIRST` neutered to `(SELECT NULL)`, resolution can no longer fall back
    to the timeline at all (both _AS_OF and _FIRST come back NULL), so it
    falls all the way through to the wrapper's launch-time tag. That this
    result DIFFERS from the un-mutated test above is exactly the proof that
    the un-mutated test's assertion actually depends on `_FIRST` executing --
    i.e. that mutating `_FIRST` to NULL turns the previous test red.
    """
    monkeypatch.setattr(attribute, "_FIRST", "(SELECT NULL)")
    store = OtelStore(tmp_db_path)
    _seed_first_arm_fixture(store)
    row = _fetch_first_arm_row(store)
    assert row["resolved_repo"] == FIRST_ARM_WRAPPER_REPO
    assert row["attribution_source"] == "wrapper"
    store.close()


# ---------------------------------------------------------------------------
# Requirement 3 -- transcript_key does NOT strip; the insert methods do.
# Carried forward from task 01's contract note because this file computes
# expected totals independently in several places; pinned explicitly here.
# ---------------------------------------------------------------------------

def test_transcript_key_contract_does_not_strip_request_id():
    """`transcript_key` itself performs no stripping -- only `insert_datapoint`
    / `insert_cost_datapoint` do. A caller (including this test file) that
    computes an expected key by calling `transcript_key(...)` directly must
    pass an already-stripped `request_id`, or the computed key silently
    mismatches what the store actually wrote."""
    assert transcript_key("s", " req-1 ", "input") != transcript_key("s", "req-1", "input")


# ---------------------------------------------------------------------------
# Requirement 2 -- the systemic-failure alarm: "every accepted record
# rejected with a store_error: reason" is an alarm, not ordinary client-data
# noise. The detector itself is authored HERE (task 07's own integration
# check) -- no production file defines it; it is only a query over the
# receiver's existing, already-correct response shape.
# ---------------------------------------------------------------------------

def _systemic_store_failure_signature(result: dict) -> bool:
    """True iff EVERY record the batch produced was rejected, and every one
    of those rejections is a store_error (never a validate_batch rejection,
    e.g. invalid_entrypoint/missing_field/etc, which is ordinary client-data
    noise). Mirrors the signature this task's spec states verbatim:
    `accepted > 0 AND rejected == len(accepted) AND every reason starts with
    'store_error:'`. `result['inserted'] == 0` stands in for that condition:
    both real reproductions (a closed-database ProgrammingError, and a
    receiver-side KeyError from a map_record contract break) raise before any
    row of the record is written, so a 100% store-error rate implies zero
    successful inserts anywhere in the response.
    """
    rejections = result.get("rejections") or []
    if not rejections:
        return False
    if result.get("inserted", 0) != 0:
        return False
    return all(r.get("reason", "").startswith("store_error:") for r in rejections)


def _full_record(**overrides) -> dict:
    base = dict(
        session_id="sess-systemic-alarm",
        ts="2026-01-01T00:00:00Z",
        request_id="req-systemic-001",
        model="claude-sonnet-5",
        input_tokens=10,
        output_tokens=20,
        cache_read_input_tokens=5,
        cache_creation_input_tokens=3,
        repo_raw="git@github.com:Cyclotron/Acme-Web.git",
        entrypoint="claude-desktop",
        query_source="main",
        user_email="alice@cyclotron.com",
        user_id="u-alice",
        org_id="org-cyclotron",
    )
    base.update(overrides)
    return base


def test_systemic_alarm_fires_on_closed_database(tmp_path, monkeypatch):
    """Residual path 1: sqlite3.ProgrammingError('Cannot operate on a closed
    database') raised from the store's insert calls -- every accepted record
    fails inside the per-record try/except, but the connection itself stays
    healthy enough for the batch's own `store.commit()` (inside the outer
    guarded region, per receiver.py's current code) to succeed, so the
    response really is a clean 200 (rather than an unhandled exception
    escaping past do_POST's narrow `except (ValueError, KeyError)` -- which
    is what actually closing the connection up front does instead: see
    `test_actually_closed_database_escapes_past_the_per_record_guard` below
    for that surprising divergence, reported there as a separate finding,
    not asserted here)."""
    store = OtelStore(str(tmp_path / "closed.db"))

    def _raise_closed(**kwargs):
        raise sqlite3.ProgrammingError("Cannot operate on a closed database.")

    monkeypatch.setattr(store, "insert_datapoint", _raise_closed)
    monkeypatch.setattr(store, "insert_cost_datapoint", _raise_closed)

    batch = [
        _full_record(request_id="req-closed-1", session_id="sess-closed-a"),
        _full_record(request_id="req-closed-2", session_id="sess-closed-b"),
    ]
    result = receiver.ingest_transcript_usage_payload(batch, store)

    assert result["rejected"] == 2
    assert result["inserted"] == 0
    assert all(r["reason"] == "store_error:ProgrammingError" for r in result["rejections"])
    assert _systemic_store_failure_signature(result) is True
    store.close()


def test_actually_closed_database_escapes_past_the_per_record_guard(tmp_path):
    """FINDING (reported, not fixed -- see this task's completion report):
    an ALREADY-closed store does not reach the 'cheerful 200 with 100%
    store_error rejections' this task's spec describes for this residual
    path. Every per-record insert does raise ProgrammingError and IS caught
    and rejected as designed. `receiver.ingest_transcript_usage_payload`'s
    `store.commit()` call lives INSIDE the outer guarded try block (current
    receiver.py, `billing/otel/receiver.py:378`) -- so when the connection is
    already closed, that commit() ALSO raises the same ProgrammingError, and
    control reaches the outer `except Exception`, which calls
    `store.db.rollback()` to leave clean state before re-raising. But the
    connection is already closed, so `rollback()` itself raises the SAME
    ProgrammingError -- and it is THAT call's exception, not commit()'s
    original one, which actually escapes uncaught past `do_POST`'s
    `except (ValueError, KeyError)`. A fully-closed connection is therefore
    still WORSE than the alarm this task exists to surface: not a loud 200,
    but an unhandled exception, now surfacing one statement later than when
    this finding was first written (owning task: 03, billing/otel/receiver.py).
    """
    store = OtelStore(str(tmp_path / "actually_closed.db"))
    store.close()
    batch = [_full_record(request_id="req-actually-closed-1")]
    with pytest.raises(sqlite3.ProgrammingError):
        receiver.ingest_transcript_usage_payload(batch, store)


def test_systemic_alarm_fires_on_map_record_key_rename_regression(tmp_path, monkeypatch):
    """Residual path 2: a future rename of map_record's returned dict keys
    (e.g. 'token_rows' -> something else) raises KeyError for every accepted
    record, belt-and-braces coverage per receiver.py's own docstring."""
    store = OtelStore(str(tmp_path / "keyerr.db"))

    def _broken_map_record(record, rating=None):
        # Missing "token_rows" -- simulates the exact regression the
        # receiver's docstring names.
        return {"ts": "2026-01-01T00:00:00Z", "cost_row": {}}

    monkeypatch.setattr(receiver, "map_record", _broken_map_record)

    batch = [_full_record(request_id="req-keyerr-1")]
    result = receiver.ingest_transcript_usage_payload(batch, store)

    assert result["rejected"] == 1
    assert result["inserted"] == 0
    assert result["rejections"][0]["reason"] == "store_error:KeyError"
    assert _systemic_store_failure_signature(result) is True
    store.close()


def test_systemic_alarm_silent_for_ordinary_mixed_batch(tmp_path):
    """Ordinary bad client data (one bad record among good ones) must NOT
    trip the alarm -- ordinary client-data noise is not a 100% store-error
    rate."""
    store = OtelStore(str(tmp_path / "ordinary.db"))
    good = _full_record(request_id="req-good-1")
    bad_model = _full_record(request_id="req-bad-model", model=123, session_id="sess-bad-model")

    result = receiver.ingest_transcript_usage_payload([good, bad_model], store)

    assert result["rejected"] == 1
    assert result["inserted"] > 0
    assert _systemic_store_failure_signature(result) is False
    store.close()


def test_systemic_alarm_silent_for_pure_validation_rejections(tmp_path):
    """A validate_batch-level rejection (e.g. invalid_entrypoint) is ordinary
    client-data noise, not a store failure -- must not trip the alarm even
    when it is the batch's only rejection.

    Inverted for otel-export-loss-reduction task 03: `entrypoint="cli"` is no
    longer rejected (cli/claude-vscode are now accepted backfill
    entrypoints), so the out-of-set entrypoint (claude-web) is used here
    instead to keep exercising this same validate_batch-level rejection
    path -- the CLI-specific ingest="cli" record must instead call this
    function with `entrypoint="cli"` via receiver.ingest_transcript_usage_payload
    directly, whose default entrypoint used elsewhere in this module is
    "claude-desktop"."""
    store = OtelStore(str(tmp_path / "valonly.db"))
    good = _full_record(request_id="req-good-2")
    bad_entrypoint = _full_record(request_id="req-bad-entry", entrypoint="claude-web",
                                  session_id="sess-bad-entry")

    result = receiver.ingest_transcript_usage_payload([good, bad_entrypoint], store)

    assert result["rejected"] == 1
    assert result["rejections"][0]["reason"] == "invalid_entrypoint"
    assert _systemic_store_failure_signature(result) is False
    store.close()


def test_systemic_alarm_silent_for_cli_entrypoint_now_accepted(tmp_path):
    """The other half of the inversion: a `cli` record with no OTLP row and
    an old-enough timestamp is now ACCEPTED end to end, so it must not
    contribute a rejection at all -- and must not trip the systemic alarm."""
    store = OtelStore(str(tmp_path / "cli_accepted.db"))
    good = _full_record(request_id="req-good-3")
    cli_record = _full_record(request_id="req-cli-accepted", entrypoint="cli",
                               session_id="sess-cli-accepted", ts="2026-01-01T00:00:00Z")

    result = receiver.ingest_transcript_usage_payload([good, cli_record], store)

    assert result["rejected"] == 0
    assert _systemic_store_failure_signature(result) is False
    store.close()


def test_systemic_alarm_silent_when_batch_is_entirely_clean(tmp_path):
    """No rejections at all -> the alarm must stay silent (a detector that
    never fires and one that fires constantly are both worthless)."""
    store = OtelStore(str(tmp_path / "clean.db"))
    result = receiver.ingest_transcript_usage_payload(
        [_full_record(request_id="req-clean-1")], store)
    assert result["rejected"] == 0
    assert _systemic_store_failure_signature(result) is False
    store.close()


# ---------------------------------------------------------------------------
# Integration coverage -- the end-to-end desktop path.
# ---------------------------------------------------------------------------

def test_end_to_end_desktop_path_exact_billed_amount(hook, projects_tree, tmp_path):
    """Drives task 00's synthetic projects tree (main transcript + sidechain,
    across two project directories) through the real hook, the real
    validator, the real receiver ingest path, and the real store, then bills
    it with the real bill.py -- and asserts the EXACT dollar figure,
    independently re-derived from RatingService and the markup, against
    none of the three historical billing errors this plan's earlier drafts
    contained.
    """
    state_path = projects_tree["projects_root"].parent / "state.json"
    _seed_epoch_install(state_path)
    db_path = str(tmp_path / "e2e.db")
    store = OtelStore(db_path)
    results: list = []
    post = _make_real_post_batch(store, sink=results)

    hook.run(
        projects_root=projects_tree["projects_root"],
        state_path=state_path,
        claude_json_path=projects_tree["projects_root"].parent / "missing.claude.json",
        transcript_path_hint=str(projects_tree["main_path"]),
        hook_event_name="SessionEnd", now=_soon(), post_batch=post,
        idle_threshold_seconds=0,
    )
    store.commit()

    # --- harness validity check (this goal has repeatedly shipped a
    # verification step that silently did nothing while looking clean) ---
    assert results, "no batch was ever posted -- the harness produced nothing"
    total_rejected = sum(r["rejected"] for r in results)
    total_inserted = sum(r["inserted"] for r in results)
    assert total_rejected == 0, results
    # 4 groups (multi-block, duplicate, sidechain, second-project) x
    # (4 token rows + 1 cost row) = 20 -- every token field in every group is
    # nonzero, so nothing is omitted by map_record's zero-token skip.
    assert total_inserted == 20, results

    # --- token-level check against task 00's published combined total ---
    session_a_tokens = store.db.execute(
        "SELECT SUM(tokens) FROM token_usage WHERE session_id=? AND usage_source='transcript'",
        (SESSION_A_ID,),
    ).fetchone()[0]
    assert session_a_tokens == EXPECTED_COMBINED_TOTAL_TOKENS
    assert session_a_tokens != EXPECTED_MAIN_ONLY_TOTAL_TOKENS  # not main-file-only

    # --- independent dollar computation, from RatingService + markup ---
    rating = RatingService()

    def _raw(input_t, output_t, cache_creation_t, cache_read_t) -> float:
        return (
            rating.raw_cost(DESKTOP_MODEL, "input", input_t)
            + rating.raw_cost(DESKTOP_MODEL, "output", output_t)
            + rating.raw_cost(DESKTOP_MODEL, "cacheCreation", cache_creation_t)
            + rating.raw_cost(DESKTOP_MODEL, "cacheRead", cache_read_t)
        )

    multi_terminal_raw = _raw(
        MULTI_BLOCK_INPUT, MULTI_BLOCK_OUTPUT_TERMINAL,
        MULTI_BLOCK_CACHE_CREATION, MULTI_BLOCK_CACHE_READ)
    duplicate_raw = _raw(
        DUPLICATE_INPUT, DUPLICATE_OUTPUT, DUPLICATE_CACHE_CREATION, DUPLICATE_CACHE_READ)
    sidechain_raw = _raw(
        SIDECHAIN_INPUT, SIDECHAIN_OUTPUT, SIDECHAIN_CACHE_CREATION, SIDECHAIN_CACHE_READ)
    second_project_raw = _raw(7, 99, 250, 900)  # SECOND_PROJECT fixture values (conftest.py)

    expected_raw = multi_terminal_raw + duplicate_raw + sidechain_raw + second_project_raw
    expected_billed = expected_raw * MARKUP

    # bill.py prints dollar figures at 4 decimal places (`${amt:>10,.4f}`), so
    # the parsed grand_billed can differ from the un-rounded expectation by
    # up to half a cent-of-a-cent -- an absolute, not relative, tolerance.
    ROUND_TOL = 5e-5

    output = _run_bill(db_path)
    grand_billed = _grand_billed(output)
    assert grand_billed == pytest.approx(expected_billed, abs=ROUND_TOL)
    assert grand_billed > 0

    # --- the three negatives this plan's earlier drafts actually shipped ---

    # 1) NOT the naive sum of the cumulative blocks (both apiBlockIndex 0 AND
    #    1 of the multi-block group, instead of just the terminal one).
    multi_sum_raw = multi_terminal_raw + rating.raw_cost(
        DESKTOP_MODEL, "output", MULTI_BLOCK_OUTPUT_PARTIAL)
    naive_sum_billed = (multi_sum_raw + duplicate_raw + sidechain_raw + second_project_raw) * MARKUP
    assert grand_billed != pytest.approx(naive_sum_billed, abs=ROUND_TOL)

    # 2) NOT the first-block value (apiBlockIndex=0's output, not the
    #    terminal apiBlockIndex=1's).
    multi_first_raw = _raw(
        MULTI_BLOCK_INPUT, MULTI_BLOCK_OUTPUT_PARTIAL,
        MULTI_BLOCK_CACHE_CREATION, MULTI_BLOCK_CACHE_READ)
    first_block_billed = (multi_first_raw + duplicate_raw + sidechain_raw + second_project_raw) * MARKUP
    assert grand_billed != pytest.approx(first_block_billed, abs=ROUND_TOL)

    # 3) NOT the main-file-only total (omitting the sidechain file entirely,
    #    and the second project directory -- a single-transcript-file sweep).
    main_file_only_billed = (multi_terminal_raw + duplicate_raw) * MARKUP
    assert grand_billed != pytest.approx(main_file_only_billed, abs=ROUND_TOL)
    assert grand_billed > main_file_only_billed


def test_scratch_workspace_reaches_billing_as_desktop_scratch(hook, tmp_path):
    """A desktop record with repo_raw='' (cwd='', no git remote to resolve)
    reaches billing classified `desktop-scratch`, end to end through the
    real hook/validator/receiver/store/bill.py path."""
    root = tmp_path / "scratch_projects"
    project_dir = root / "project-scratch-workspace"
    project_dir.mkdir(parents=True)
    session_id = "sess-scratch-e2e"
    path = project_dir / f"{session_id}.jsonl"
    row = _usage_row(
        session_id=session_id, request_id="req-scratch-e2e", message_id="msg-scratch-e2e",
        api_block_index=0, stop_reason="end_turn",
        input_tokens=50, output_tokens=80,
        cache_creation_input_tokens=10, cache_read_input_tokens=20,
        cwd="", timestamp="2026-01-04T00:00:00.000Z",
    )
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    state_path = root.parent / "state.json"
    _seed_epoch_install(state_path)
    db_path = str(tmp_path / "scratch.db")
    store = OtelStore(db_path)
    results: list = []
    post = _make_real_post_batch(store, sink=results)

    hook.run(
        projects_root=root, state_path=state_path,
        claude_json_path=root.parent / "missing.claude.json",
        transcript_path_hint=str(path), hook_event_name="SessionEnd",
        now=_soon(), post_batch=post, idle_threshold_seconds=0,
    )
    store.commit()

    assert results and results[0]["rejected"] == 0 and results[0]["inserted"] > 0
    store.close()

    output = _run_bill(db_path)
    lines = [ln for ln in output.splitlines() if ln.strip().startswith("desktop-scratch")]
    assert len(lines) == 1, output


def test_mixed_otlp_and_transcript_store_bills_each_once_no_overlap(tmp_path):
    """A store containing OTLP rows for a CLI session and transcript rows for
    a DIFFERENT (desktop) session bills each exactly once, and the overlap
    detector (which fires only when ONE session_id carries BOTH
    usage_source values) stays silent."""
    db_path = str(tmp_path / "non_dup.db")
    store = OtelStore(db_path)
    seed_otlp_rows(store)  # 3 distinct OTLP/CLI sessions

    desktop_model = "claude-sonnet-5"
    desktop_tokens = {"input": 40_000, "output": 15_000, "cacheRead": 5_000, "cacheCreation": 2_000}
    rating = RatingService()
    raw_desktop = 0.0
    for token_type, tok in desktop_tokens.items():
        store.insert_datapoint(
            session_id="sess-desktop-nondup", repo="unknown", repo_raw="",
            user_email="", user_id="", org_id="", model=desktop_model,
            token_type=token_type, query_source="main", tokens=tok,
            time_unix_nano=1_800_000_000_000_000_000, usage_source="transcript",
            entrypoint="claude-desktop", request_id="req-nondup",
        )
        raw_desktop += rating.raw_cost(desktop_model, token_type, tok)
    store.insert_cost_datapoint(
        session_id="sess-desktop-nondup", repo="unknown", repo_raw="",
        user_email="", user_id="", org_id="", model=desktop_model,
        query_source="main", cost_usd=raw_desktop, time_unix_nano=1_800_000_000_000_000_000,
        usage_source="transcript", cost_source="rate_card", request_id="req-nondup",
    )
    store.commit()
    store.close()

    output = _run_bill(db_path)
    assert "DOUBLE-BILLING RISK" not in output

    expected_otlp_actual = sum(s["cost_usd"] for s in SEEDED_SESSIONS)
    expected_total_billed = (expected_otlp_actual + raw_desktop) * MARKUP
    grand_billed = _grand_billed(output)
    assert grand_billed == pytest.approx(expected_total_billed, rel=1e-6)

    # "Exactly once": bill.py performs no writes, so re-running it against
    # the SAME store must reproduce byte-identical output -- a double-count
    # bug (e.g. an unintended JOIN fan-out) would surface here as drift.
    output2 = _run_bill(db_path)
    assert output2 == output


# ---------------------------------------------------------------------------
# Requirement 4 -- the _mark_resolved cross-task key seam.
#
# SEED ONLY, ASSERT WHAT ACTUALLY HAPPENS, DO NOT FIX. The hook groups usage
# by (sessionId, requestId, message.id); the server (task 01/02) dedupes by
# (session_id, request_id) alone. One session producing two groups that share
# a requestId but differ in message.id makes the hook ship two records for
# one requestId; the server accepts the first and rejects the second as
# duplicate_request_id; the hook then marks that (shared) request_id
# resolved regardless -- losing the second group's tokens permanently, with
# a 200 and no retry. Neither side is individually wrong; the defect lives
# in the seam. See this file's completion report for the measured loss.
# ---------------------------------------------------------------------------

CROSS_TASK_SESSION = "sess-cross-task-seam"
CROSS_TASK_REQUEST_ID = "req-cross-task-shared"

# The group that WINS (earlier ts -> sorted first -> validate_batch accepts
# it before it ever sees the second group's shared request_id).
CROSS_TASK_WINNER = dict(input_tokens=10, output_tokens=20,
                          cache_creation_input_tokens=5, cache_read_input_tokens=8)
# The group that is LOST -- deliberately much larger, so the loss is obvious
# and its dollar value is unambiguous to compute.
CROSS_TASK_LOSER = dict(input_tokens=1000, output_tokens=2000,
                         cache_creation_input_tokens=300, cache_read_input_tokens=500)


def _build_cross_task_seam_tree(root: Path) -> Path:
    project_dir = root / "project-cross-task-seam"
    project_dir.mkdir(parents=True)
    path = project_dir / f"{CROSS_TASK_SESSION}.jsonl"
    row_winner = _usage_row(
        session_id=CROSS_TASK_SESSION, request_id=CROSS_TASK_REQUEST_ID,
        message_id="msg-cross-task-1", api_block_index=0, stop_reason="end_turn",
        timestamp="2026-01-03T10:00:00.000Z", **CROSS_TASK_WINNER,
    )
    row_loser = _usage_row(
        session_id=CROSS_TASK_SESSION, request_id=CROSS_TASK_REQUEST_ID,
        message_id="msg-cross-task-2", api_block_index=0, stop_reason="end_turn",
        timestamp="2026-01-03T10:05:00.000Z", **CROSS_TASK_LOSER,
    )
    path.write_text(
        "\n".join(json.dumps(r) for r in (row_winner, row_loser)) + "\n", encoding="utf-8")
    return path


def test_cross_task_key_seam_second_group_permanently_lost(hook, tmp_path):
    root = tmp_path / "cross_task_projects"
    path = _build_cross_task_seam_tree(root)
    state_path = root.parent / "state.json"
    _seed_epoch_install(state_path)
    db_path = str(tmp_path / "cross_task.db")
    store = OtelStore(db_path)
    shipped_batches: list = []

    def _post(records):
        shipped_batches.append([dict(r) for r in records])
        result = receiver.ingest_transcript_usage_payload(records, store)
        return "ok", 200, result

    hook.run(
        projects_root=root, state_path=state_path,
        claude_json_path=root.parent / "missing.claude.json",
        transcript_path_hint=str(path), hook_event_name="SessionEnd",
        now=_soon(), post_batch=_post, idle_threshold_seconds=0,
    )
    store.commit()

    # --- the hook's own side of the seam: it really does ship BOTH groups,
    # both carrying the SAME request_id, per its (sessionId, requestId,
    # message.id) grouping -- confirms the hook is behaving exactly as this
    # goal mandated, not misbehaving on its own. ---
    shipped = [r for chunk in shipped_batches for r in chunk]
    assert len(shipped) == 2
    assert {r["request_id"] for r in shipped} == {CROSS_TASK_REQUEST_ID}

    # --- what actually happens end to end: only ONE group's tokens survive.
    rows = store.db.execute(
        "SELECT token_type, tokens FROM token_usage WHERE session_id=? "
        "AND usage_source='transcript'", (CROSS_TASK_SESSION,)
    ).fetchall()
    stored_by_type = {r["token_type"]: r["tokens"] for r in rows}

    assert len(rows) == 4  # ONE group's worth (4 token types) -- not 8
    assert stored_by_type == {
        "input": CROSS_TASK_WINNER["input_tokens"],
        "output": CROSS_TASK_WINNER["output_tokens"],
        "cacheCreation": CROSS_TASK_WINNER["cache_creation_input_tokens"],
        "cacheRead": CROSS_TASK_WINNER["cache_read_input_tokens"],
    }
    # The larger (loser) group's tokens are NOT present anywhere in the store
    # under this session -- they are not merged, not summed, not queued for
    # retry. They are gone.
    for tt, tok in stored_by_type.items():
        assert tok != CROSS_TASK_LOSER[
            {"input": "input_tokens", "output": "output_tokens",
             "cacheCreation": "cache_creation_input_tokens",
             "cacheRead": "cache_read_input_tokens"}[tt]]

    # --- quantify the loss (reported as a FINDING, not fixed here) ---
    rating = RatingService()
    lost_tokens = sum(CROSS_TASK_LOSER.values())
    lost_raw_cost = (
        rating.raw_cost(DESKTOP_MODEL, "input", CROSS_TASK_LOSER["input_tokens"])
        + rating.raw_cost(DESKTOP_MODEL, "output", CROSS_TASK_LOSER["output_tokens"])
        + rating.raw_cost(DESKTOP_MODEL, "cacheCreation", CROSS_TASK_LOSER["cache_creation_input_tokens"])
        + rating.raw_cost(DESKTOP_MODEL, "cacheRead", CROSS_TASK_LOSER["cache_read_input_tokens"])
    )
    lost_billed = lost_raw_cost * MARKUP
    assert lost_tokens == 3800
    # Pinned to a LITERAL, not to `lost_raw_cost * MARKUP` recomputed --
    # comparing a value against its own re-derivation can never fail and
    # would leave this dollar figure only ever printed, never pinned
    # (exactly the vacuous-assertion pattern this task exists to catch).
    assert lost_billed == pytest.approx(0.051412, abs=1e-6)
    print(
        f"\n[FINDING] cross-task _mark_resolved key seam: {lost_tokens} tokens "
        f"(${lost_raw_cost:.6f} raw / ${lost_billed:.6f} billed at {MARKUP:.2f}x markup) "
        f"permanently lost, no retry, 200 response. Not fixed here -- see task "
        f"07's completion report."
    )

    # --- and it looks completely healthy from every component's own report,
    # even standalone: the first (in-batch) attempt was rejected
    # 'duplicate_request_id' -- an ordinary-looking reason, not an error --
    # and the hook marks the shared request_id resolved regardless of which
    # group actually landed, so there is no retry path back to the lost
    # group. Re-posting the loser's record ALONE (its own standalone batch,
    # no longer sharing a batch with the winner) doesn't even get that far:
    # its request_id's transcript_key (session_id, request_id, token_type)
    # is IDENTICAL to the winner's already-stored rows (the key composition
    # deliberately excludes message.id -- task 01's contract), so the
    # store's own INSERT OR IGNORE replay guard silently treats it as a
    # replay of an already-delivered record. Zero rejections, zero inserts,
    # every row (4 token + 1 cost) counted as 'duplicate' -- the quietest
    # possible form of the same permanent loss. ---
    loser_only = [row for row in shipped if row["request_id"] == CROSS_TASK_REQUEST_ID][1:]
    result = receiver.ingest_transcript_usage_payload(loser_only, store)
    assert result["rejected"] == 0
    assert result["inserted"] == 0
    assert result["duplicate"] == 5  # 4 token rows + 1 cost row, all "replays"
    store.close()
