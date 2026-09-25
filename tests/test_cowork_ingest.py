"""Tests for billing.otel.cowork_ingest -- the pure Cowork OTLP payload
parser (task 02 of the cowork-telemetry-ingest goal).

Reuses tests/conftest.py's build_cowork_metrics_payload/cowork_metrics_payload
fixtures (task 00) rather than duplicating payload construction.

This file was adversarially expanded after an evaluator ran probe scripts
against the happy-path-only version of this module and found real
fail-closed gaps (see the module's own docstring for the resulting design:
every rejection reason and numeric-validation rule below is documented
there). Every probe case the evaluator reproduced has a dedicated test here.
"""

from __future__ import annotations

import ast
import copy
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from billing.otel import cowork_ingest
from billing.otel.cowork_ingest import (
    COST_METRIC,
    KNOWN_SERVICE_NAME,
    MAX_TIME_UNIX_NANO,
    SQLITE_INT64_MAX,
    TOKEN_METRIC,
    parse_cowork_payload,
)
from tests.conftest import (
    COWORK_INPUT_TOKENS,
    COWORK_MODEL,
    COWORK_OUTPUT_TOKENS,
    COWORK_QUERY_SOURCE,
    COWORK_USER_EMAIL,
    build_cowork_metrics_payload,
)


def _token_metric(payload):
    metric = payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]
    assert metric["name"] == TOKEN_METRIC
    return metric


def _cost_metric(payload):
    metric = payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][1]
    assert metric["name"] == COST_METRIC
    return metric


# ---------------------------------------------------------------------------
# AC1 -- cowork service.name, recognized metrics -> one token row, one cost
# row, zero rejections.
# ---------------------------------------------------------------------------

def test_accepted_cowork_payload_produces_rows_and_no_rejections(cowork_metrics_payload):
    result = parse_cowork_payload(cowork_metrics_payload)

    assert result["rejections"] == []
    # Two token datapoints (input + output) in the default fixture.
    assert len(result["token_rows"]) == 2
    assert len(result["cost_rows"]) == 1
    assert sorted(result["metrics_seen"]) == sorted([TOKEN_METRIC, COST_METRIC])

    token_types = {row["token_type"] for row in result["token_rows"]}
    assert token_types == {"input", "output"}

    for row in result["token_rows"] + result["cost_rows"]:
        assert row["model"] == COWORK_MODEL
        assert row["query_source"] == COWORK_QUERY_SOURCE
        assert row["user_email"] == COWORK_USER_EMAIL
        # repo/repo_raw pass through verbatim-unresolved; no repo attribute
        # was set on this fixture, so both coalesce to "".
        assert row["repo"] == ""
        assert row["repo_raw"] == ""

    cost_row = result["cost_rows"][0]
    assert cost_row["cost_usd"] == pytest.approx(2.5)

    input_row = next(r for r in result["token_rows"] if r["token_type"] == "input")
    assert input_row["tokens"] == COWORK_INPUT_TOKENS
    output_row = next(r for r in result["token_rows"] if r["token_type"] == "output")
    assert output_row["tokens"] == COWORK_OUTPUT_TOKENS

    # Row dicts must match CoworkStore's frozen keyword signatures EXACTLY --
    # no extra, no missing.
    expected_token_keys = {
        "session_id", "repo", "repo_raw", "user_email", "user_id", "org_id",
        "model", "token_type", "query_source", "tokens", "time_unix_nano",
    }
    expected_cost_keys = {
        "session_id", "repo", "repo_raw", "user_email", "user_id", "org_id",
        "model", "query_source", "cost_usd", "time_unix_nano",
    }
    for row in result["token_rows"]:
        assert set(row.keys()) == expected_token_keys
    for row in result["cost_rows"]:
        assert set(row.keys()) == expected_cost_keys


def test_accepted_rows_are_insertable_into_cowork_store(tmp_path, cowork_metrics_payload):
    """End-to-end sanity: the row dicts this module produces are actually
    accepted by CoworkStore's real insert_* keyword signatures (task 01)."""
    from billing.otel.cowork_store import CoworkStore

    result = parse_cowork_payload(cowork_metrics_payload)
    store = CoworkStore(str(tmp_path / "cowork.db"))
    try:
        for row in result["token_rows"]:
            assert store.insert_datapoint(**row) is True
        for row in result["cost_rows"]:
            assert store.insert_cost_datapoint(**row) is True
        store.commit()
    finally:
        store.close()


# ---------------------------------------------------------------------------
# AC2 -- service.name="claude-code" (the CLI's real, hyphenated value) ->
# zero rows, one rejection per metric, reason prefixed unrecognized_service_name.
# ---------------------------------------------------------------------------

def test_hyphenated_claude_code_service_name_is_rejected():
    payload = build_cowork_metrics_payload(service_name="claude-code")
    result = parse_cowork_payload(payload)

    assert result["token_rows"] == []
    assert result["cost_rows"] == []
    assert len(result["rejections"]) == 2  # one per metric (token + cost)
    for rejection in result["rejections"]:
        assert rejection["reason"].startswith("unrecognized_service_name:")
        assert "claude-code" in rejection["reason"]


# ---------------------------------------------------------------------------
# AC3 -- service.name entirely absent behaves the same as AC2 (not silently
# accepted).
# ---------------------------------------------------------------------------

def test_absent_service_name_is_rejected_not_accepted():
    payload = build_cowork_metrics_payload(service_name=None)
    result = parse_cowork_payload(payload)

    assert result["token_rows"] == []
    assert result["cost_rows"] == []
    assert len(result["rejections"]) == 2
    for rejection in result["rejections"]:
        assert rejection["reason"].startswith("unrecognized_service_name:")
        assert "absent" in rejection["reason"]


# ---------------------------------------------------------------------------
# AC4 -- service.name="cowork" but an unrecognized metric name -> rejection
# reason prefixed unrecognized_metric, never raises.
# ---------------------------------------------------------------------------

def test_unrecognized_metric_name_is_rejected():
    payload = build_cowork_metrics_payload(
        service_name=KNOWN_SERVICE_NAME, token_metric_name="some.other.metric")
    result = parse_cowork_payload(payload)  # must not raise

    assert result["token_rows"] == []
    # The cost metric in the same payload is still recognized and accepted.
    assert len(result["cost_rows"]) == 1
    reasons = [r["reason"] for r in result["rejections"]]
    assert any(r.startswith("unrecognized_metric:some.other.metric") for r in reasons)
    assert "some.other.metric" in result["metrics_seen"]


# ---------------------------------------------------------------------------
# AC5 -- a non-dict payload (bare list, None) -> a documented exception
# (this task commits to TypeError; see module docstring).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_payload", [None, [], ["not", "a", "dict"], "nope", 42])
def test_non_dict_payload_raises_documented_exception(bad_payload):
    with pytest.raises(TypeError):
        parse_cowork_payload(bad_payload)


# ---------------------------------------------------------------------------
# AC6 -- session_id=0 and session_id="" (present-but-falsy) preserved as
# their own distinct string values, not collapsed with a genuinely absent
# session_id.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("session_id_value,expected", [(0, "0"), ("", "")])
def test_falsy_but_present_session_id_is_preserved(session_id_value, expected):
    payload = build_cowork_metrics_payload(session_id=session_id_value)
    result = parse_cowork_payload(payload)
    assert result["token_rows"], "expected accepted token rows"
    for row in result["token_rows"]:
        assert row["session_id"] == expected


def _payload_without_session_id():
    payload = build_cowork_metrics_payload()
    payload["resourceMetrics"][0]["resource"]["attributes"] = [
        a for a in payload["resourceMetrics"][0]["resource"]["attributes"]
        if a["key"] != "session.id"
    ]
    return payload


def test_absent_session_id_maps_to_sentinel_distinct_from_falsy_values():
    result = parse_cowork_payload(_payload_without_session_id())
    assert result["token_rows"], "expected accepted token rows"
    session_ids = {row["session_id"] for row in result["token_rows"]}
    assert session_ids == {"unknown"}


def test_three_session_id_variants_produce_three_distinct_outcomes():
    outcomes = set()
    for session_id_value in (0, "", None):
        if session_id_value is None:
            payload = _payload_without_session_id()
        else:
            payload = build_cowork_metrics_payload(session_id=session_id_value)
        result = parse_cowork_payload(payload)
        session_ids = {row["session_id"] for row in result["token_rows"]}
        assert len(session_ids) == 1
        outcomes.add(next(iter(session_ids)))
    # The real assertion: three genuinely distinct string outcomes, and the
    # absent-case sentinel is neither of the two falsy-but-present spellings.
    assert outcomes == {"0", "", "unknown"}


# ---------------------------------------------------------------------------
# AC7 -- git diff on receiver.py / transcript.py is empty. Verified at the
# repo level via `git diff` in the completion report (not something a unit
# test can assert in isolation).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# AC8 -- cowork_ingest.py contains no import of billing.otel.receiver, in
# ANY form: `import billing.otel.receiver`, `from billing.otel import
# receiver`, `from . import receiver`, a multi-line import, or a conditional
# import. The AST check inspects both `ImportFrom.module` AND every
# `alias.name` (the earlier version only checked `.module`, which misses
# `from billing.otel import receiver`). A subprocess check backs it up: it
# proves `billing.otel.receiver` never lands in sys.modules as a SIDE EFFECT
# of merely importing this module, in a fresh interpreter -- not just that
# the source text looks clean.
# ---------------------------------------------------------------------------

def test_module_has_no_import_of_receiver_ast():
    source_path = Path(cowork_ingest.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "receiver" not in alias.name, (
                    f"cowork_ingest.py must not import receiver, found: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert "receiver" not in module, (
                f"cowork_ingest.py must not import from module: {module}")
            # Catches `from billing.otel import receiver` and
            # `from . import receiver` (relative, node.module is None/short,
            # node.level > 0) -- the alias name is where "receiver" actually
            # appears in both of those forms.
            for alias in node.names:
                assert "receiver" not in alias.name, (
                    f"cowork_ingest.py must not import name: {alias.name} "
                    f"(from module={module!r}, level={node.level})")


def test_importing_module_leaves_receiver_out_of_sys_modules_subprocess():
    """Runtime proof, in a FRESH interpreter, that merely importing
    billing.otel.cowork_ingest never pulls billing.otel.receiver into
    sys.modules as a side effect -- the exact hazard `receiver.py`'s
    import-time `load_env()` call creates."""
    project_root = Path(__file__).resolve().parent.parent
    code = (
        "import sys\n"
        "import billing.otel.cowork_ingest\n"
        "assert 'billing.otel.receiver' not in sys.modules, "
        "'receiver was imported as a side effect of importing cowork_ingest'\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(project_root),
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, (
        f"subprocess failed:\nstdout={result.stdout}\nstderr={result.stderr}")
    assert "OK" in result.stdout


# ---------------------------------------------------------------------------
# AC9 -- rewritten per orchestrator's resolution of the "missing timeUnixNano
# entirely" ambiguity: (a) timeUnixNano absent but startTimeUnixNano present
# is an intended ACCEPT via fallback (matches receiver.py's own existing
# convention -- see module docstring), tested explicitly rather than by
# omission; (b) BOTH absent is the real "missing entirely" case and must be
# malformed_datapoint:time_unix_nano. Also covers the asInt="not-a-number"
# half of AC9.
# ---------------------------------------------------------------------------

def test_non_numeric_asint_is_rejected_without_raising(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    # Corrupt the first token datapoint's asInt; leave the second untouched.
    data_points[0]["asInt"] = "not-a-number"

    result = parse_cowork_payload(payload)  # must not raise

    reasons = [r["reason"] for r in result["rejections"]]
    assert any(r.startswith("malformed_datapoint:asInt") for r in reasons)
    # The other valid token datapoint, plus the cost datapoint, still land.
    assert len(result["token_rows"]) == 1
    assert len(result["cost_rows"]) == 1


def test_timeunixnano_absent_but_starttime_present_is_accepted_via_fallback(
        cowork_metrics_payload):
    """(a) -- the INTENDED fallback behavior, asserted explicitly."""
    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    start_nano = data_points[0]["startTimeUnixNano"]
    del data_points[0]["timeUnixNano"]

    result = parse_cowork_payload(payload)  # must not raise, must not reject

    assert result["rejections"] == []
    assert len(result["token_rows"]) == 2
    fallback_row = next(
        r for r in result["token_rows"] if r["time_unix_nano"] == int(start_nano))
    assert fallback_row is not None


def test_both_timeunixnano_and_starttime_absent_is_rejected(cowork_metrics_payload):
    """(b) -- the REAL "missing entirely" case AC9 means."""
    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    del data_points[0]["timeUnixNano"]
    del data_points[0]["startTimeUnixNano"]

    result = parse_cowork_payload(payload)  # must not raise

    reasons = [r["reason"] for r in result["rejections"]]
    assert any(r.startswith("malformed_datapoint:time_unix_nano") for r in reasons)
    assert len(result["token_rows"]) == 1
    assert len(result["cost_rows"]) == 1
    # Never silently defaults to time_unix_nano=0 (receiver.py's own `or 0`
    # convention is deliberately NOT mirrored here -- see module docstring).
    assert all(row["time_unix_nano"] != 0 for row in result["token_rows"])


def test_non_numeric_asdouble_cost_is_rejected_without_raising(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    cost_metric = _cost_metric(payload)
    cost_metric["sum"]["dataPoints"][0]["asDouble"] = "not-a-number"

    result = parse_cowork_payload(payload)  # must not raise

    reasons = [r["reason"] for r in result["rejections"]]
    assert any(r.startswith("malformed_datapoint:asDouble") for r in reasons)
    assert result["cost_rows"] == []
    # Token rows in the same payload are unaffected.
    assert len(result["token_rows"]) == 2


# ---------------------------------------------------------------------------
# Issue 1 -- malformed individual attributes/records must never RAISE. Every
# case below is a probe the evaluator reproduced against the earlier version
# of this module.
# ---------------------------------------------------------------------------

def test_attribute_intvalue_non_numeric_string_does_not_raise(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    payload["resourceMetrics"][0]["resource"]["attributes"].append(
        {"key": "bogus.attr", "value": {"intValue": "notint"}})
    result = parse_cowork_payload(payload)  # must not raise (ValueError from int())
    assert len(result["token_rows"]) == 2
    assert result["rejections"] == []  # a bad EXTRA attribute is just dropped


def test_attribute_intvalue_list_does_not_raise(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    payload["resourceMetrics"][0]["resource"]["attributes"].append(
        {"key": "bogus.attr", "value": {"intValue": [1]}})
    result = parse_cowork_payload(payload)  # must not raise (TypeError from int())
    assert len(result["token_rows"]) == 2


def test_attribute_value_not_a_dict_does_not_raise(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    payload["resourceMetrics"][0]["resource"]["attributes"].append(
        {"key": "bogus.attr", "value": 5})
    result = parse_cowork_payload(payload)  # must not raise (AttributeError on .get)
    assert len(result["token_rows"]) == 2


def test_attribute_key_unhashable_does_not_raise(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    payload["resourceMetrics"][0]["resource"]["attributes"].append(
        {"key": ["not", "hashable"], "value": {"stringValue": "x"}})
    result = parse_cowork_payload(payload)  # must not raise (TypeError, unhashable)
    assert len(result["token_rows"]) == 2


def test_resource_attributes_non_list_does_not_raise():
    payload = build_cowork_metrics_payload()
    payload["resourceMetrics"][0]["resource"]["attributes"] = "not-a-list"
    result = parse_cowork_payload(payload)  # must not raise (TypeError iterating)
    # service.name is now unreadable -> falls back to "absent" -> rejected,
    # but never raises.
    assert result["token_rows"] == []
    assert all(r["reason"].startswith("unrecognized_service_name:absent")
               for r in result["rejections"])


def test_datapoint_attributes_non_list_does_not_raise(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    _token_metric(payload)["sum"]["dataPoints"][0]["attributes"] = "not-a-list"
    result = parse_cowork_payload(payload)  # must not raise
    # The datapoint itself is still numerically valid -- its own extra
    # attributes (model/type/query_source) just fall back to defaults.
    assert len(result["token_rows"]) == 2


def test_metric_sum_non_dict_does_not_raise_and_is_rejected(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    token_metric = _token_metric(payload)
    token_metric["sum"] = "not-a-dict"  # was: AttributeError on .get("dataPoints")

    result = parse_cowork_payload(payload)  # must not raise

    assert result["token_rows"] == []
    assert any(r["reason"] == "malformed_datapoints" for r in result["rejections"])
    # Cost metric in the same payload is unaffected.
    assert len(result["cost_rows"]) == 1


def test_metric_name_unhashable_does_not_raise(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    _token_metric(payload)["name"] = ["not", "hashable"]

    result = parse_cowork_payload(payload)  # must not raise (TypeError, set.add)

    assert result["token_rows"] == []  # no longer matches TOKEN_METRIC
    # Falls through to the unrecognized_metric branch harmlessly.
    assert len(result["cost_rows"]) == 1


# ---------------------------------------------------------------------------
# Issue 7 -- non-list resourceMetrics/scopeMetrics/metrics/dataPoints must
# produce an EXPLICIT rejection, never a silent drop.
# ---------------------------------------------------------------------------

def test_non_list_resource_metrics_produces_explicit_rejection():
    result = parse_cowork_payload({"resourceMetrics": "not-a-list"})
    assert result["token_rows"] == []
    assert result["cost_rows"] == []
    assert any(r["reason"] == "malformed_resource_metrics" for r in result["rejections"])


def test_non_dict_resource_metrics_entry_is_rejected():
    result = parse_cowork_payload({"resourceMetrics": ["not-a-dict"]})
    assert result["token_rows"] == []
    assert result["cost_rows"] == []
    assert any(r["reason"] == "malformed_resource_metrics_entry"
               for r in result["rejections"])


def test_non_list_scope_metrics_produces_explicit_rejection(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    payload["resourceMetrics"][0]["scopeMetrics"] = "not-a-list"
    result = parse_cowork_payload(payload)
    assert result["token_rows"] == []
    assert any(r["reason"] == "malformed_scope_metrics" for r in result["rejections"])


def test_non_list_metrics_produces_explicit_rejection(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"] = "not-a-list"
    result = parse_cowork_payload(payload)
    assert result["token_rows"] == []
    assert any(r["reason"] == "malformed_metrics" for r in result["rejections"])


def test_non_list_datapoints_produces_explicit_rejection(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    _token_metric(payload)["sum"]["dataPoints"] = "not-a-list"
    result = parse_cowork_payload(payload)
    assert result["token_rows"] == []
    assert any(r["reason"] == "malformed_datapoints" for r in result["rejections"])


def test_missing_resource_metrics_key_returns_empty_result_no_rejection():
    """Absence is not an error -- only a present-but-wrong-type value is."""
    result = parse_cowork_payload({})
    assert result == {
        "token_rows": [], "cost_rows": [], "metrics_seen": [], "rejections": [],
    }


# ---------------------------------------------------------------------------
# Issue 2 -- OverflowError (e.g. from wire-level Infinity) must be caught
# alongside TypeError/ValueError wherever int()/float() conversion happens.
# ---------------------------------------------------------------------------

def test_overflowing_asint_string_does_not_raise(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    data_points[0]["asInt"] = "1" * 400  # int() succeeds (arbitrary precision)
    # then float()/range-check must reject it, not raise.
    result = parse_cowork_payload(payload)
    reasons = [r["reason"] for r in result["rejections"]]
    assert any(r.startswith("malformed_datapoint:asInt") for r in reasons)


def test_overflowing_time_unix_nano_does_not_raise(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    data_points[0]["timeUnixNano"] = "1" * 30
    result = parse_cowork_payload(payload)  # must not raise
    reasons = [r["reason"] for r in result["rejections"]]
    assert any(r.startswith("malformed_datapoint:time_unix_nano") for r in reasons)


def test_wire_level_infinity_asint_does_not_raise(cowork_metrics_payload):
    """`json.loads` parses the non-standard `Infinity` token to a Python
    float by default -- matching how receiver.py itself parses request
    bodies. Converting that onward toward an int must not raise
    OverflowError."""
    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    data_points[0]["asInt"] = json.loads("Infinity")
    result = parse_cowork_payload(payload)  # must not raise
    reasons = [r["reason"] for r in result["rejections"]]
    assert any(r.startswith("malformed_datapoint:asInt") for r in reasons)


# ---------------------------------------------------------------------------
# Issue 3 -- NaN/Infinity cost values must be rejected, never stored (never
# silently accepted as garbage that becomes NULL/inf downstream).
# ---------------------------------------------------------------------------

def test_wire_level_nan_cost_is_rejected(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    _cost_metric(payload)["sum"]["dataPoints"][0]["asDouble"] = json.loads("NaN")
    result = parse_cowork_payload(payload)  # must not raise
    assert result["cost_rows"] == []
    assert any(r["reason"].startswith("malformed_datapoint:asDouble")
               for r in result["rejections"])


def test_wire_level_infinity_cost_is_rejected(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    _cost_metric(payload)["sum"]["dataPoints"][0]["asDouble"] = json.loads("Infinity")
    result = parse_cowork_payload(payload)
    assert result["cost_rows"] == []
    assert any(r["reason"].startswith("malformed_datapoint:asDouble")
               for r in result["rejections"])


def test_python_level_float_nan_cost_is_rejected(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    _cost_metric(payload)["sum"]["dataPoints"][0]["asDouble"] = float("nan")
    result = parse_cowork_payload(payload)
    assert result["cost_rows"] == []


def test_string_nan_and_inf_cost_are_rejected(cowork_metrics_payload):
    for literal in ("NaN", "inf", "-inf", "Infinity"):
        payload = copy.deepcopy(cowork_metrics_payload)
        _cost_metric(payload)["sum"]["dataPoints"][0]["asDouble"] = literal
        result = parse_cowork_payload(payload)
        assert result["cost_rows"] == [], f"literal={literal!r} must be rejected"
        assert any(r["reason"].startswith("malformed_datapoint:asDouble")
                   for r in result["rejections"]), literal


def test_rejected_nan_cost_is_never_inserted_as_garbage(tmp_path, cowork_metrics_payload):
    """Proves the rejection actually prevents storage -- not just that the
    row is absent from the returned list, but that nothing NaN/inf-shaped
    ever reaches CoworkStore."""
    from billing.otel.cowork_store import CoworkStore

    payload = copy.deepcopy(cowork_metrics_payload)
    _cost_metric(payload)["sum"]["dataPoints"][0]["asDouble"] = float("nan")
    result = parse_cowork_payload(payload)
    assert result["cost_rows"] == []

    store = CoworkStore(str(tmp_path / "cowork.db"))
    try:
        for row in result["cost_rows"]:
            store.insert_cost_datapoint(**row)
        store.commit()
        total = store.db.execute(
            "SELECT COUNT(*) AS n FROM cowork_cost_usage").fetchone()["n"]
        assert total == 0
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Issue 4 -- an accepted row must ALWAYS actually insert into CoworkStore.
# Oversized asInt (SQLite int64 overflow) / timeUnixNano (datetime overflow)
# must be rejected here, before ever reaching the store.
# ---------------------------------------------------------------------------

def test_oversized_asint_rejected_not_accepted(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    data_points[0]["asInt"] = "1" * 40  # a 40-digit number
    result = parse_cowork_payload(payload)
    reasons = [r["reason"] for r in result["rejections"]]
    assert any(r.startswith("malformed_datapoint:asInt") for r in reasons)
    # Never even attempt an insert of the oversized value.
    assert all(row["tokens"] <= SQLITE_INT64_MAX for row in result["token_rows"])


def test_oversized_time_unix_nano_rejected_not_accepted(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    data_points[0]["timeUnixNano"] = "1" * 30  # a 30-digit number
    result = parse_cowork_payload(payload)
    reasons = [r["reason"] for r in result["rejections"]]
    assert any(r.startswith("malformed_datapoint:time_unix_nano") for r in reasons)
    assert all(row["time_unix_nano"] <= MAX_TIME_UNIX_NANO
               for row in result["token_rows"])


def test_boundary_valid_values_are_genuinely_insertable(tmp_path, cowork_metrics_payload):
    """The inverse of the two tests above: values AT the accepted boundary
    must actually insert without raising."""
    from billing.otel.cowork_store import CoworkStore

    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    data_points[0]["asInt"] = str(SQLITE_INT64_MAX)
    data_points[0]["timeUnixNano"] = str(MAX_TIME_UNIX_NANO)

    result = parse_cowork_payload(payload)
    assert result["rejections"] == []
    assert len(result["token_rows"]) == 2

    store = CoworkStore(str(tmp_path / "cowork.db"))
    try:
        for row in result["token_rows"]:
            assert store.insert_datapoint(**row) is True  # must not raise
        for row in result["cost_rows"]:
            assert store.insert_cost_datapoint(**row) is True
        store.commit()
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Issue 8 -- fractional and negative values are explicitly rejected (the
# safer default for billing data), not silently accepted/truncated.
# ---------------------------------------------------------------------------

def test_fractional_token_count_is_rejected(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    data_points[0]["asInt"] = 3.7  # a genuine JSON number, not a string
    result = parse_cowork_payload(payload)
    reasons = [r["reason"] for r in result["rejections"]]
    assert any(r.startswith("malformed_datapoint:asInt") for r in reasons)
    assert all(row["tokens"] != 3 for row in result["token_rows"])  # never truncated


def test_negative_token_count_is_rejected(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    data_points[0]["asInt"] = "-5"
    result = parse_cowork_payload(payload)
    reasons = [r["reason"] for r in result["rejections"]]
    assert any(r.startswith("malformed_datapoint:asInt") for r in reasons)


def test_negative_cost_is_rejected(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    _cost_metric(payload)["sum"]["dataPoints"][0]["asDouble"] = -3.0
    result = parse_cowork_payload(payload)
    assert result["cost_rows"] == []
    assert any(r["reason"].startswith("malformed_datapoint:asDouble")
               for r in result["rejections"])


def test_negative_time_unix_nano_is_rejected(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    data_points[0]["timeUnixNano"] = "-1"
    result = parse_cowork_payload(payload)
    reasons = [r["reason"] for r in result["rejections"]]
    assert any(r.startswith("malformed_datapoint:time_unix_nano") for r in reasons)


# ---------------------------------------------------------------------------
# Additional required coverage: asInt=True (bool disguised as int) must
# still be rejected after all the above changes.
# ---------------------------------------------------------------------------

def test_bool_as_asint_is_rejected(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    data_points[0]["asInt"] = True
    result = parse_cowork_payload(payload)
    reasons = [r["reason"] for r in result["rejections"]]
    assert any(r.startswith("malformed_datapoint:asInt") for r in reasons)


def test_bool_as_asdouble_cost_is_rejected(cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    _cost_metric(payload)["sum"]["dataPoints"][0]["asDouble"] = False
    result = parse_cowork_payload(payload)
    assert result["cost_rows"] == []
    assert any(r["reason"].startswith("malformed_datapoint:asDouble")
               for r in result["rejections"])


def test_bool_as_intvalue_attribute_is_dropped_not_stored_as_number(
        cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    payload["resourceMetrics"][0]["resource"]["attributes"].append(
        {"key": "bogus.count", "value": {"intValue": True}})
    result = parse_cowork_payload(payload)  # must not raise
    assert len(result["token_rows"]) == 2


# ---------------------------------------------------------------------------
# Minor cleanup: replace the earlier tautological assertion with something
# behaviorally meaningful (covered thoroughly above by
# test_three_session_id_variants_produce_three_distinct_outcomes; this test
# is the direct, explicit successor to the flagged line).
# ---------------------------------------------------------------------------

def test_absent_session_id_sentinel_differs_from_both_falsy_spellings():
    absent_result = parse_cowork_payload(_payload_without_session_id())
    zero_result = parse_cowork_payload(build_cowork_metrics_payload(session_id=0))
    empty_result = parse_cowork_payload(build_cowork_metrics_payload(session_id=""))

    absent_id = absent_result["token_rows"][0]["session_id"]
    zero_id = zero_result["token_rows"][0]["session_id"]
    empty_id = empty_result["token_rows"][0]["session_id"]

    assert absent_id != zero_id
    assert absent_id != empty_id
    assert zero_id != empty_id


def test_terminal_type_never_appears_in_returned_rows(cowork_metrics_payload):
    result = parse_cowork_payload(cowork_metrics_payload)
    for row in result["token_rows"] + result["cost_rows"]:
        assert "terminal.type" not in row
        assert "terminal_type" not in row


# ---------------------------------------------------------------------------
# Fix cycle 2, issue A [blocker] -- a HASHABLE non-string metric name (5,
# 1.5, True, ("a",)) used to insert into the metrics_seen set fine and then
# crash the final `sorted(metrics_seen)` with a mixed-type '<' TypeError.
# The earlier guard only caught UNHASHABLE names (lists). Exercised on both
# the accepted-service path and the rejected-service path, since
# metrics_seen is built on both.
# ---------------------------------------------------------------------------

_NON_STRING_METRIC_NAMES = [5, 1.5, True, ("a",)]


@pytest.mark.parametrize("bad_name", _NON_STRING_METRIC_NAMES,
                         ids=["int", "float", "bool", "tuple"])
def test_hashable_non_string_metric_name_does_not_raise_on_cowork_path(bad_name):
    payload = build_cowork_metrics_payload(service_name=KNOWN_SERVICE_NAME)
    _token_metric(payload)["name"] = bad_name

    result = parse_cowork_payload(payload)  # must not raise (sorted() TypeError)

    # metrics_seen is str-only: the bad name is skipped, the real cost
    # metric (a str, in the same payload) is still recorded and sortable.
    assert all(isinstance(n, str) for n in result["metrics_seen"])
    assert bad_name not in result["metrics_seen"]
    assert result["metrics_seen"] == [COST_METRIC]
    # The renamed token metric no longer matches TOKEN_METRIC -> rejected as
    # unrecognized, one per datapoint; the cost metric still lands.
    assert result["token_rows"] == []
    assert len(result["cost_rows"]) == 1
    assert sum(r["reason"].startswith("unrecognized_metric:")
               for r in result["rejections"]) == 2


@pytest.mark.parametrize("bad_name", _NON_STRING_METRIC_NAMES,
                         ids=["int", "float", "bool", "tuple"])
def test_hashable_non_string_metric_name_does_not_raise_on_rejected_service_path(bad_name):
    payload = build_cowork_metrics_payload(service_name="claude-code")
    _token_metric(payload)["name"] = bad_name

    result = parse_cowork_payload(payload)  # must not raise (sorted() TypeError)

    assert all(isinstance(n, str) for n in result["metrics_seen"])
    assert result["metrics_seen"] == [COST_METRIC]
    assert result["token_rows"] == []
    assert result["cost_rows"] == []
    assert len(result["rejections"]) == 2
    assert all(r["reason"].startswith("unrecognized_service_name:claude-code")
               for r in result["rejections"])


def test_mixed_string_and_non_string_metric_names_in_one_payload_do_not_raise():
    """The exact crash shape: a str AND several non-str names in the same
    set, so that `sorted()` must compare across types."""
    payload = build_cowork_metrics_payload()
    metrics = payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
    for bad_name in _NON_STRING_METRIC_NAMES:
        metrics.append({"name": bad_name, "sum": {"dataPoints": []}})

    result = parse_cowork_payload(payload)  # must not raise

    assert result["metrics_seen"] == sorted([TOKEN_METRIC, COST_METRIC])
    assert len(result["token_rows"]) == 2
    assert len(result["cost_rows"]) == 1


# ---------------------------------------------------------------------------
# Fix cycle 2, issue B [major] -- every string-typed row field must be a
# genuine `str` in the returned row, or the datapoint must be rejected.
# `_attr_value` passes `boolValue` through unchecked (so a list/dict can
# reach a string field) and `intValue` is unbounded (so a 30-digit int can
# reach one); either used to surface as a sqlite3 bind-time crash
# (ProgrammingError / OverflowError) INSIDE CoworkStore, after this module
# had already said "accepted". Fix approach (b): coerce scalars with str(),
# reject list/dict as malformed_datapoint:<row field>. Every test below
# actually calls the real CoworkStore insert -- the dict shape alone is not
# the contract, insertability is.
# ---------------------------------------------------------------------------

#: (merged-attribute key, row field name) for every string-typed row field.
#: `type` -> token_type exists on token rows only; everything else is
#: shared by token and cost rows.
_STRING_ATTR_FIELDS = [
    ("model", "model"),
    ("type", "token_type"),
    ("repo", "repo"),
    ("user.email", "user_email"),
    ("user.id", "user_id"),
    ("organization.id", "org_id"),
    ("query_source", "query_source"),
    ("session.id", "session_id"),
]

_UNBINDABLE_WRAPPERS = [
    pytest.param({"boolValue": [1]}, id="boolValue-list"),
    pytest.param({"boolValue": {"a": 1}}, id="boolValue-dict"),
]

_OVERSIZED_INT_WRAPPERS = [
    pytest.param({"intValue": "9" * 30}, id="intValue-30-digits"),
    pytest.param({"intValue": str(2**64)}, id="intValue-2^64"),
]


def _insert_all(tmp_path, result):
    """Insert every accepted row into a real CoworkStore; raises if any row
    is not genuinely bindable. Returns the store's (token, cost) row counts."""
    from billing.otel.cowork_store import CoworkStore

    store = CoworkStore(str(tmp_path / "cowork.db"))
    try:
        for row in result["token_rows"]:
            store.insert_datapoint(**row)
        for row in result["cost_rows"]:
            store.insert_cost_datapoint(**row)
        store.commit()
        n_tok = store.db.execute(
            "SELECT COUNT(*) AS n FROM cowork_token_usage").fetchone()["n"]
        n_cost = store.db.execute(
            "SELECT COUNT(*) AS n FROM cowork_cost_usage").fetchone()["n"]
        return n_tok, n_cost
    finally:
        store.close()


@pytest.mark.parametrize("attr_key,row_field", _STRING_ATTR_FIELDS)
@pytest.mark.parametrize("wrapper", _UNBINDABLE_WRAPPERS)
def test_unbindable_string_field_on_token_datapoint_is_rejected_and_rest_inserts(
        tmp_path, attr_key, row_field, wrapper):
    payload = build_cowork_metrics_payload()
    _token_metric(payload)["sum"]["dataPoints"][0]["attributes"].append(
        {"key": attr_key, "value": wrapper})

    result = parse_cowork_payload(payload)  # must not raise

    # The corrupted datapoint is an explicit rejection naming the ROW field...
    assert any(r["reason"] == f"malformed_datapoint:{row_field}"
               for r in result["rejections"]), result["rejections"]
    # ...the other token datapoint and the cost datapoint still land...
    assert len(result["token_rows"]) == 1
    assert len(result["cost_rows"]) == 1
    # ...every string field on every returned row is a genuine str...
    for row in result["token_rows"] + result["cost_rows"]:
        for field in ("session_id", "repo", "repo_raw", "user_email", "user_id",
                      "org_id", "model", "query_source"):
            assert isinstance(row[field], str), (field, row[field])
    # ...and the REAL store accepts them -- the contract that was broken.
    assert _insert_all(tmp_path, result) == (1, 1)


@pytest.mark.parametrize(
    "attr_key,row_field",
    [f for f in _STRING_ATTR_FIELDS if f[0] != "type"])  # cost rows have no token_type
@pytest.mark.parametrize("wrapper", _UNBINDABLE_WRAPPERS)
def test_unbindable_string_field_on_cost_datapoint_is_rejected_and_rest_inserts(
        tmp_path, attr_key, row_field, wrapper):
    payload = build_cowork_metrics_payload()
    _cost_metric(payload)["sum"]["dataPoints"][0]["attributes"].append(
        {"key": attr_key, "value": wrapper})

    result = parse_cowork_payload(payload)  # must not raise

    assert any(r["reason"] == f"malformed_datapoint:{row_field}"
               for r in result["rejections"]), result["rejections"]
    assert result["cost_rows"] == []
    assert len(result["token_rows"]) == 2
    assert _insert_all(tmp_path, result) == (2, 0)


#: The fixture sets model/type/query_source at the DATAPOINT level, where
#: they correctly win the merge over any resource-level value -- so only the
#: fields the fixture leaves resource-only can be corrupted from the resource.
_RESOURCE_ONLY_STRING_ATTR_FIELDS = [
    f for f in _STRING_ATTR_FIELDS if f[0] not in ("model", "type", "query_source")]


@pytest.mark.parametrize("attr_key,row_field", _RESOURCE_ONLY_STRING_ATTR_FIELDS)
@pytest.mark.parametrize("wrapper", _UNBINDABLE_WRAPPERS)
def test_unbindable_string_field_at_resource_level_rejects_every_datapoint(
        tmp_path, attr_key, row_field, wrapper):
    """A resource-level attribute merges into EVERY datapoint under it, so
    a bad one must reject all of them -- both token datapoints AND the cost
    datapoint -- each with the same field-named reason."""
    payload = build_cowork_metrics_payload()
    payload["resourceMetrics"][0]["resource"]["attributes"].append(
        {"key": attr_key, "value": wrapper})

    result = parse_cowork_payload(payload)  # must not raise

    assert result["token_rows"] == []
    assert result["cost_rows"] == []
    rejections = [r for r in result["rejections"]
                  if r["reason"] == f"malformed_datapoint:{row_field}"]
    assert len(rejections) == 3
    assert _insert_all(tmp_path, result) == (0, 0)


def test_datapoint_level_string_attr_overrides_unbindable_resource_level_one(tmp_path):
    """Merge semantics preserved: a valid DATAPOINT-level `model` wins over
    an unbindable RESOURCE-level one, so the datapoint is accepted (and
    insertable) rather than rejected for a value it does not carry."""
    payload = build_cowork_metrics_payload()
    payload["resourceMetrics"][0]["resource"]["attributes"].append(
        {"key": "model", "value": {"boolValue": [1]}})

    result = parse_cowork_payload(payload)

    assert result["rejections"] == []
    assert all(row["model"] == COWORK_MODEL
               for row in result["token_rows"] + result["cost_rows"])
    assert _insert_all(tmp_path, result) == (2, 1)


@pytest.mark.parametrize("attr_key,row_field", _STRING_ATTR_FIELDS)
@pytest.mark.parametrize("wrapper", _OVERSIZED_INT_WRAPPERS)
def test_oversized_intvalue_in_string_field_is_stringified_and_inserts(
        tmp_path, attr_key, row_field, wrapper):
    """An `intValue` beyond SQLite's int64 range is a perfectly good Python
    int and a perfectly good STRING -- in a TEXT column it must be stored
    as its decimal spelling, never handed to sqlite3 as an int (which
    raised OverflowError at bind time)."""
    from billing.otel.cowork_store import CoworkStore

    expected = str(int(wrapper["intValue"]))
    payload = build_cowork_metrics_payload()
    dp = _token_metric(payload)["sum"]["dataPoints"][0]
    dp["attributes"].append({"key": attr_key, "value": wrapper})
    cost_dp = _cost_metric(payload)["sum"]["dataPoints"][0]
    cost_dp["attributes"].append({"key": attr_key, "value": wrapper})

    result = parse_cowork_payload(payload)

    assert result["rejections"] == []  # a bindable scalar is NOT malformed
    assert len(result["token_rows"]) == 2
    assert len(result["cost_rows"]) == 1
    affected_rows = [r for r in result["token_rows"] if r.get(row_field) == expected]
    assert len(affected_rows) == 1, (row_field, result["token_rows"])
    if attr_key != "type":
        assert result["cost_rows"][0][row_field] == expected
    for row in result["token_rows"] + result["cost_rows"]:
        assert isinstance(row.get(row_field, ""), str)

    store = CoworkStore(str(tmp_path / "cowork.db"))
    try:
        for row in result["token_rows"]:
            assert store.insert_datapoint(**row) is True  # must not raise
        for row in result["cost_rows"]:
            assert store.insert_cost_datapoint(**row) is True
        store.commit()
        # Round-trip: the stored spelling is the full decimal string.
        column = {"token_type": "token_type"}.get(row_field, row_field)
        stored = store.db.execute(
            f"SELECT {column} AS v FROM cowork_token_usage WHERE {column} = ?",
            (expected,)).fetchall()
        assert len(stored) == 1
        assert stored[0]["v"] == expected
    finally:
        store.close()


@pytest.mark.parametrize("attr_key,row_field", _STRING_ATTR_FIELDS)
def test_genuine_bool_in_string_field_is_stringified_not_rejected(
        tmp_path, attr_key, row_field):
    """A real JSON `true` in a string field is a bindable scalar: stringified
    ("True"), consistent with receiver.py's `_common`, and insertable."""
    payload = build_cowork_metrics_payload()
    _token_metric(payload)["sum"]["dataPoints"][0]["attributes"].append(
        {"key": attr_key, "value": {"boolValue": True}})

    result = parse_cowork_payload(payload)

    assert result["rejections"] == []
    assert len(result["token_rows"]) == 2
    assert any(r[row_field] == "True" for r in result["token_rows"])
    assert _insert_all(tmp_path, result) == (2, 1)


def test_every_string_row_field_is_str_on_the_happy_path(cowork_metrics_payload):
    """Type-level contract, asserted directly: no int/float/bool/list ever
    leaks into a string-typed row field, even from the well-formed fixture."""
    result = parse_cowork_payload(cowork_metrics_payload)
    string_fields = ("session_id", "repo", "repo_raw", "user_email", "user_id",
                     "org_id", "model", "query_source")
    for row in result["token_rows"]:
        for field in string_fields + ("token_type",):
            assert type(row[field]) is str, (field, row[field])
    for row in result["cost_rows"]:
        for field in string_fields:
            assert type(row[field]) is str, (field, row[field])


# ---------------------------------------------------------------------------
# Fix cycle 2, issue C [major] -- a float-formatted STRING for an integer
# field used to be accepted via int(float(s)), silently yielding a DIFFERENT
# integer above 2**53 ("1767312000000000001.0" -> 1767312000000000000; the
# dedup key changes with it). Choice (a): reject every non-integer-formatted
# string for an integer field outright. A genuine JSON float is likewise
# rejected above 2**53, the exact-integer bound for IEEE-754 doubles.
# ---------------------------------------------------------------------------

_PRECISION_LOSING_TIME = "1767312000000000001.0"
_PRECISION_LOSING_TIME_TRUNCATED = 1767312000000000000


def test_float_formatted_time_unix_nano_string_is_rejected_not_truncated(
        cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    data_points[0]["timeUnixNano"] = _PRECISION_LOSING_TIME

    result = parse_cowork_payload(payload)  # must not raise

    reasons = [r["reason"] for r in result["rejections"]]
    assert any(r.startswith("malformed_datapoint:time_unix_nano") for r in reasons)
    assert len(result["token_rows"]) == 1  # only the untouched datapoint
    # The wrong, truncated value NEVER appears in any accepted row.
    assert all(row["time_unix_nano"] != _PRECISION_LOSING_TIME_TRUNCATED
               for row in result["token_rows"])


def test_float_formatted_time_unix_nano_does_not_collide_with_true_value(
        tmp_path, cowork_metrics_payload):
    """The dedup-key consequence, end to end: a datapoint whose timestamp
    string is the truncated integer and one whose timestamp is the
    precision-losing float string must NOT collapse into one stored row."""
    from billing.otel.cowork_store import CoworkStore

    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    # Same dims (type=input/model/query_source) for both, differing only in
    # timestamp spelling. Make datapoint 1 a copy of datapoint 0's dims.
    data_points[1]["attributes"] = copy.deepcopy(data_points[0]["attributes"])
    data_points[0]["timeUnixNano"] = str(_PRECISION_LOSING_TIME_TRUNCATED)
    data_points[1]["timeUnixNano"] = _PRECISION_LOSING_TIME

    result = parse_cowork_payload(payload)

    assert len(result["token_rows"]) == 1  # the float-string one is rejected
    assert result["token_rows"][0]["time_unix_nano"] == _PRECISION_LOSING_TIME_TRUNCATED
    store = CoworkStore(str(tmp_path / "cowork.db"))
    try:
        # Exactly one insert, and it is genuinely a new row -- had the second
        # datapoint been accepted-and-truncated, it would have silently
        # deduped against this one (insert_datapoint -> False).
        assert store.insert_datapoint(**result["token_rows"][0]) is True
        store.commit()
    finally:
        store.close()


def test_scientific_notation_asint_string_is_rejected_not_truncated(
        cowork_metrics_payload):
    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    data_points[0]["asInt"] = "1.767312000000000001e18"

    result = parse_cowork_payload(payload)  # must not raise

    reasons = [r["reason"] for r in result["rejections"]]
    assert any(r.startswith("malformed_datapoint:asInt") for r in reasons)
    assert all(row["tokens"] != 1767312000000000000 for row in result["token_rows"])
    assert len(result["token_rows"]) == 1


@pytest.mark.parametrize("bad_string", [
    "3.0",            # whole-valued float spelling -- rejected by choice (a)
    "3.",
    "1e3",
    "1_000",          # int() accepts underscores; the OTLP wire never emits them
    "0x10",
    " 12 34",
    "+",
    "",
], ids=repr)
def test_non_integer_formatted_asint_string_is_rejected(cowork_metrics_payload, bad_string):
    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    data_points[0]["asInt"] = bad_string

    result = parse_cowork_payload(payload)  # must not raise

    reasons = [r["reason"] for r in result["rejections"]]
    assert any(r.startswith("malformed_datapoint:asInt") for r in reasons), bad_string
    assert len(result["token_rows"]) == 1


@pytest.mark.parametrize("good_string,expected", [
    ("42", 42),
    ("+42", 42),
    (" 42 ", 42),    # surrounding whitespace is still stripped
    ("0", 0),
    (str(SQLITE_INT64_MAX), SQLITE_INT64_MAX),
    ("1767312000000000001", 1767312000000000001),  # > 2**53, exact as a string
])
def test_integer_formatted_asint_strings_are_accepted_exactly(
        cowork_metrics_payload, good_string, expected):
    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    data_points[0]["asInt"] = good_string

    result = parse_cowork_payload(payload)

    assert result["rejections"] == []
    assert expected in [row["tokens"] for row in result["token_rows"]]


def test_exact_large_integer_time_unix_nano_string_is_accepted_exactly(
        cowork_metrics_payload):
    """The positive counterpart of the precision test: the SAME value spelled
    as a plain integer string is accepted bit-for-bit."""
    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    data_points[0]["timeUnixNano"] = "1767312000000000001"

    result = parse_cowork_payload(payload)

    assert result["rejections"] == []
    assert 1767312000000000001 in [row["time_unix_nano"] for row in result["token_rows"]]


def test_whole_json_float_above_exact_integer_bound_is_rejected(cowork_metrics_payload):
    """A genuine JSON float (Python float) above 2**53 has already lost
    precision on the wire; int(f) is a plausible-looking wrong number."""
    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    data_points[0]["timeUnixNano"] = float(1767312000000000001)  # -> 1.767312e18
    data_points[1]["asInt"] = float(2**53 + 2)  # whole, but beyond exact range

    result = parse_cowork_payload(payload)  # must not raise

    reasons = [r["reason"] for r in result["rejections"]]
    assert any(r.startswith("malformed_datapoint:time_unix_nano") for r in reasons)
    assert any(r.startswith("malformed_datapoint:asInt") for r in reasons)
    assert result["token_rows"] == []


def test_whole_json_float_within_exact_integer_bound_is_still_accepted(
        cowork_metrics_payload):
    """Small whole floats (`asDouble: 3.0` as a token count) remain valid --
    the bound only bites where precision is genuinely at risk."""
    payload = copy.deepcopy(cowork_metrics_payload)
    data_points = _token_metric(payload)["sum"]["dataPoints"]
    data_points[0]["asInt"] = 3.0
    data_points[1]["asInt"] = float(2**53)  # exactly at the bound: accepted

    result = parse_cowork_payload(payload)

    assert result["rejections"] == []
    assert sorted(row["tokens"] for row in result["token_rows"]) == [3, 2**53]
