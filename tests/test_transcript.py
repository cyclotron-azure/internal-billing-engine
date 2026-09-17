"""Tests for billing.otel.transcript -- task 02 of desktop-usage-capture.

Covers the nine acceptance criteria in
_goals/desktop-usage-capture/02-transcript-payload.md. Pure unit tests: no
database, no network, no filesystem -- transcript.py is a pure module.
"""

from __future__ import annotations

import copy
import json

import pytest

from billing.otel import otel_store
from billing.otel.normalize import normalize_remote
from billing.otel.rating import RatingService
from billing.otel.transcript import (
    EPOCH_FLOOR_NANO,
    MAX_BATCH_SIZE,
    REJECTION_REASONS,
    map_record,
    validate_batch,
)


def _record(**overrides) -> dict:
    base = dict(
        session_id="sess-1",
        ts="2026-01-01T21:20:00.187Z",
        request_id="req-1",
        model="claude-sonnet-5",
        input_tokens=100,
        output_tokens=50,
        cache_read_input_tokens=200,
        cache_creation_input_tokens=30,
        repo_raw="git@github.com:Cyclotron/Acme-Web.git",
        entrypoint="claude-desktop",
        query_source="main",
        user_email="alice@cyclotron.com",
        user_id="u-alice",
        org_id="org-cyclotron",
    )
    base.update(overrides)
    return base


# --- AC1: well-formed single-record batch --------------------------------

def test_ac1_well_formed_record_maps_to_expected_rows():
    accepted, rejected = validate_batch([_record()])
    assert rejected == []
    assert len(accepted) == 1

    mapped = map_record(accepted[0])
    token_rows = mapped["token_rows"]
    assert len(token_rows) == 4
    types = {row["token_type"] for row in token_rows}
    assert types == {"input", "output", "cacheRead", "cacheCreation"}

    by_type = {row["token_type"]: row for row in token_rows}
    assert by_type["input"]["tokens"] == 100
    assert by_type["output"]["tokens"] == 50
    assert by_type["cacheRead"]["tokens"] == 200
    assert by_type["cacheCreation"]["tokens"] == 30

    cost_row = mapped["cost_row"]
    assert cost_row["cost_source"] == "rate_card"
    assert cost_row["cost_usd"] > 0
    # exactly one cost row is produced
    assert "cost_row" in mapped and isinstance(mapped["cost_row"], dict)


# --- The fields that actually reach the database (not just `ts`) ----------
#
# `map_record`'s top-level "ts" key has NO consumer in the designed flow --
# `insert_datapoint`/`insert_cost_datapoint` recompute the stored ts
# themselves from `time_unix_nano` via `otel_store._ns_to_iso`. These tests
# assert the fields that are actually written: `time_unix_nano` (tied back to
# the emitted "ts" via the store's own conversion, so the two can never
# silently drift apart), `request_id`, `usage_source`, and `entrypoint`.

def test_time_unix_nano_matches_emitted_ts_via_store_conversion():
    record = _record(ts="2026-01-01T21:20:00.187Z")
    accepted, rejected = validate_batch([record])
    assert rejected == []
    mapped = map_record(accepted[0])

    for row in mapped["token_rows"]:
        assert otel_store._ns_to_iso(row["time_unix_nano"]) == mapped["ts"]
    assert otel_store._ns_to_iso(mapped["cost_row"]["time_unix_nano"]) == mapped["ts"]
    # Pin the actual value too -- a zeroed time_unix_nano would still satisfy
    # a self-referential equality check against a similarly-zeroed "ts".
    assert mapped["ts"] == "2026-01-01T21:20:00Z"
    assert all(row["time_unix_nano"] != 0 for row in mapped["token_rows"])
    assert mapped["cost_row"]["time_unix_nano"] != 0


def test_request_id_is_carried_onto_every_row():
    record = _record(request_id="req-money-critical")
    accepted, rejected = validate_batch([record])
    assert rejected == []
    mapped = map_record(accepted[0])

    for row in mapped["token_rows"]:
        assert row["request_id"] == "req-money-critical"
    assert mapped["cost_row"]["request_id"] == "req-money-critical"


def test_usage_source_is_transcript_on_every_row():
    accepted, rejected = validate_batch([_record()])
    assert rejected == []
    mapped = map_record(accepted[0])

    for row in mapped["token_rows"]:
        assert row["usage_source"] == "transcript"
    assert mapped["cost_row"]["usage_source"] == "transcript"


def test_entrypoint_present_on_token_rows_and_absent_from_cost_row():
    accepted, rejected = validate_batch([_record()])
    assert rejected == []
    mapped = map_record(accepted[0])

    for row in mapped["token_rows"]:
        assert row["entrypoint"] == "claude-desktop"
    # cost_usage has no entrypoint column -- insert_cost_datapoint does not
    # accept the keyword, so the cost row must not carry it.
    assert "entrypoint" not in mapped["cost_row"]


# --- AC2: entrypoint acceptance / rejection --------------------------------
#
# Inverted for otel-export-loss-reduction task 03: `cli` and `claude-vscode`
# are now members of ALLOWED_ENTRYPOINTS, not rejected. The old expectation
# is kept alive below against a genuinely out-of-set entrypoint
# (`claude-web`), which must still reject with the unchanged reason string.

@pytest.mark.parametrize("entrypoint", ["cli", "claude-vscode"])
def test_ac2_backfill_entrypoint_now_accepted(entrypoint):
    accepted, rejected = validate_batch([_record(entrypoint=entrypoint)])
    assert rejected == []
    assert len(accepted) == 1
    assert accepted[0]["entrypoint"] == entrypoint


def test_ac2_non_desktop_entrypoint_rejected():
    """Kept alive against a genuinely out-of-set entrypoint -- the OTLP-
    exclusion / quarantine checks live in receiver.py, not here; this module
    only enforces membership in ALLOWED_ENTRYPOINTS."""
    accepted, rejected = validate_batch([_record(entrypoint="claude-web")])
    assert accepted == []
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "invalid_entrypoint"


# --- AC3: zero output_tokens produces no output row -----------------------

def test_ac3_zero_output_tokens_omits_output_row():
    accepted, rejected = validate_batch([_record(output_tokens=0)])
    assert rejected == []
    mapped = map_record(accepted[0])
    types = {row["token_type"] for row in mapped["token_rows"]}
    assert "output" not in types
    assert len(mapped["token_rows"]) == 3


def test_ac3_absent_output_tokens_omits_output_row():
    record = _record()
    del record["output_tokens"]
    accepted, rejected = validate_batch([record])
    assert rejected == []
    mapped = map_record(accepted[0])
    types = {row["token_type"] for row in mapped["token_rows"]}
    assert "output" not in types


# --- AC4: envelope vs per-record malformations ----------------------------

def test_ac4_non_list_envelope_raises_value_error():
    with pytest.raises(ValueError):
        validate_batch({"not": "a list"})


def test_ac4_oversized_batch_raises_value_error():
    batch = [_record(request_id=f"req-{i}") for i in range(MAX_BATCH_SIZE + 1)]
    with pytest.raises(ValueError):
        validate_batch(batch)


def test_ac4_batch_at_max_size_is_accepted():
    batch = [_record(request_id=f"req-{i}") for i in range(MAX_BATCH_SIZE)]
    accepted, rejected = validate_batch(batch)
    assert len(accepted) == MAX_BATCH_SIZE
    assert rejected == []


@pytest.mark.parametrize("field", [
    "session_id", "ts", "request_id", "model",
])
def test_ac4_missing_required_field_is_per_record_rejection(field):
    record = _record()
    del record[field]
    accepted, rejected = validate_batch([record])
    assert accepted == []
    assert len(rejected) == 1
    assert rejected[0]["reason"] == f"missing_field:{field}"


@pytest.mark.parametrize("field", [
    "input_tokens", "output_tokens",
    "cache_read_input_tokens", "cache_creation_input_tokens",
])
def test_ac4_negative_token_count_is_per_record_rejection(field):
    accepted, rejected = validate_batch([_record(**{field: -1})])
    assert accepted == []
    assert rejected[0]["reason"] == f"invalid_tokens:{field}"


def test_ac4_non_numeric_token_count_is_per_record_rejection():
    accepted, rejected = validate_batch([_record(input_tokens="lots")])
    assert accepted == []
    assert rejected[0]["reason"] == "invalid_tokens:input_tokens"


def test_ac4_fractional_float_token_count_is_rejected_not_truncated():
    # 100.7 must be rejected, not silently int()'ed down to 100 -- fail-closed
    # matches the house style used for unknown fields.
    accepted, rejected = validate_batch([_record(input_tokens=100.7)])
    assert accepted == []
    assert rejected[0]["reason"] == "invalid_tokens:input_tokens"


def test_ac4_integral_float_token_count_is_accepted_as_int():
    # json.loads('100.0') is a float. Rejecting it would lose EVERY record
    # from a client that serializes counts as floats; the value is lossless.
    accepted, rejected = validate_batch([_record(input_tokens=100.0)])
    assert rejected == []
    assert accepted[0]["input_tokens"] == 100
    assert type(accepted[0]["input_tokens"]) is int
    by_type = {r["token_type"]: r for r in map_record(accepted[0])["token_rows"]}
    assert by_type["input"]["tokens"] == 100


def test_ac4_exponent_float_token_count_is_accepted_as_int():
    # json.loads('1e2') is also a float (100.0).
    value = json.loads("1e2")
    assert isinstance(value, float)
    accepted, rejected = validate_batch([_record(output_tokens=value)])
    assert rejected == []
    assert accepted[0]["output_tokens"] == 100
    assert type(accepted[0]["output_tokens"]) is int


def test_ac4_bool_token_count_is_rejected():
    accepted, rejected = validate_batch([_record(input_tokens=True)])
    assert accepted == []
    assert rejected[0]["reason"] == "invalid_tokens:input_tokens"


# --- ts must be validated up front, never left to raise in map_record ------
#
# Task 03 wraps each record in a per-record try/except. A raise from
# map_record escapes that scope and 400s the WHOLE batch, which task 06 then
# retries and eventually drops -- valid billable records lost because of one
# bad timestamp. validate_batch must catch it first.

@pytest.mark.parametrize("bad_ts", [
    "garbage",
    "2026-13-45T99:99:99Z",
    "",                          # falsy -> missing_field, asserted separately
    12345,                       # non-string: would AttributeError on .strip()
    "0001-01-01T00:00:00Z",      # pre-epoch: below the explicit epoch floor
])
def test_malformed_ts_is_per_record_rejection_and_batch_survives(bad_ts):
    good_1 = _record(request_id="req-good-1")
    bad = _record(request_id="req-bad", ts=bad_ts)
    good_2 = _record(request_id="req-good-2")
    accepted, rejected = validate_batch([good_1, bad, good_2])

    assert {r["request_id"] for r in accepted} == {"req-good-1", "req-good-2"}
    assert len(rejected) == 1
    assert rejected[0]["request_id"] == "req-bad"
    assert rejected[0]["index"] == 1
    expected = "missing_field:ts" if bad_ts == "" else "invalid_ts"
    assert rejected[0]["reason"] == expected

    # map_record is never reached for the bad record: every accepted record
    # maps without raising.
    for rec in accepted:
        map_record(rec)


@pytest.mark.parametrize("bad_ts", ["garbage", "2026-13-45T99:99:99Z"])
def test_malformed_ts_reason_is_invalid_ts(bad_ts):
    accepted, rejected = validate_batch([_record(ts=bad_ts)])
    assert accepted == []
    assert rejected == [{"index": 0, "request_id": "req-1", "reason": "invalid_ts"}]


def test_invalid_ts_is_in_rejection_reasons_vocabulary():
    assert "invalid_ts" in REJECTION_REASONS


# --- the epoch floor is a CONTRACT boundary, not a platform artifact ------
#
# Before the explicit `nano < EPOCH_FLOOR_NANO` check, the accept/reject line
# sat wherever the host C library's fromtimestamp gave up: on Windows that is
# an undocumented point inside December 1969 (1969-12-31T23:59:59Z was
# ACCEPTED there), and on the python:3.12-slim image the Dockerfile ships it
# does not exist at all. A pre-epoch record accepted in production stores a
# ts that sorts below every session_repo_timeline entry in attribute.py's
# lexicographic as-of join and falls outside every invoice period -- billed
# to nobody, with no error anywhere. These two cases pin the boundary itself
# and hold identically on every platform.

@pytest.mark.parametrize("ts,expect_accepted", [
    ("1970-01-01T00:00:00Z", True),    # the epoch itself is legal
    ("1969-12-31T23:59:59Z", False),   # one second before it is not
])
def test_epoch_floor_boundary_is_platform_independent(ts, expect_accepted):
    accepted, rejected = validate_batch([_record(ts=ts)])
    if expect_accepted:
        assert rejected == []
        assert len(accepted) == 1
        assert map_record(accepted[0])["ts"] == "1970-01-01T00:00:00Z"
    else:
        assert accepted == []
        assert rejected == [
            {"index": 0, "request_id": "req-1", "reason": "invalid_ts"}
        ]


def test_epoch_floor_constant_is_the_unix_epoch():
    # A named contract value, so the boundary is stated rather than implied.
    assert EPOCH_FLOOR_NANO == 0


def test_date_only_ts_is_accepted_and_maps_to_midnight_utc():
    # Documented decision in transcript._validate_ts: a bare date is legal.
    accepted, rejected = validate_batch([_record(ts="2026-01-01")])
    assert rejected == []
    assert map_record(accepted[0])["ts"] == "2026-01-01T00:00:00Z"


def test_ac4_not_a_dict_record_is_rejected():
    accepted, rejected = validate_batch(["just a string, not a record"])
    assert accepted == []
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "not_a_dict"
    assert rejected[0]["index"] == 0
    assert rejected[0]["request_id"] is None


def test_ac4_unknown_field_is_per_record_rejection():
    accepted, rejected = validate_batch([_record(extra_field="surprise")])
    assert accepted == []
    assert rejected[0]["reason"] == "unknown_field:extra_field"


def test_ac4_cwd_field_is_rejected():
    accepted, rejected = validate_batch(
        [_record(cwd="/home/dev/scratch-workspaces/abc")])
    assert accepted == []
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "unknown_field:cwd"


def test_ac4_mixed_batch_good_records_survive_alongside_bad_one():
    good_1 = _record(request_id="req-good-1")
    good_2 = _record(request_id="req-good-2")
    bad = _record(request_id="req-bad", cwd="/some/path")
    accepted, rejected = validate_batch([good_1, bad, good_2])
    assert len(accepted) == 2
    assert {r["request_id"] for r in accepted} == {"req-good-1", "req-good-2"}
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "unknown_field:cwd"
    # `index` is the record's TRUE position in the original batch, not its
    # position among the rejected ones -- task 03 logs/acts on it.
    assert rejected[0]["index"] == 1
    assert rejected[0]["request_id"] == "req-bad"


def test_rejection_index_is_original_batch_position_in_larger_mixed_batch():
    # req-2 (entrypoint="cli") is now ACCEPTED (task 03 widens
    # ALLOWED_ENTRYPOINTS) -- inverted from the original expectation, which
    # pinned "cli" as rejected. req-6 (entrypoint="claude-web", genuinely
    # out-of-set) keeps that original rejection coverage alive.
    batch = [
        _record(request_id="req-0"),
        _record(request_id="req-1", cwd="/x"),
        _record(request_id="req-2", entrypoint="cli"),
        _record(request_id="req-3"),
        _record(request_id="req-4", ts="garbage"),
        _record(request_id="req-5", input_tokens=-1),
        _record(request_id="req-6", entrypoint="claude-web"),
    ]
    accepted, rejected = validate_batch(batch)
    assert [r["request_id"] for r in accepted] == ["req-0", "req-2", "req-3"]
    assert [r["index"] for r in rejected] == [1, 4, 5, 6]
    assert [r["request_id"] for r in rejected] == ["req-1", "req-4", "req-5", "req-6"]
    assert rejected[-1]["reason"] == "invalid_entrypoint"


# --- Rejection shape is content-free (contract for task 03) ---------------

def test_rejection_entry_shape_is_content_free():
    """A rejection is `{"index": int, "request_id": str|None, "reason": str}`
    -- exactly three keys, never the original record or any of its other
    fields."""
    record = _record(request_id="req-shape", cwd="/some/path")
    accepted, rejected = validate_batch([record])
    assert accepted == []
    assert len(rejected) == 1
    entry = rejected[0]
    assert set(entry.keys()) == {"index", "request_id", "reason"}
    assert entry["index"] == 0
    assert entry["request_id"] == "req-shape"
    assert entry["reason"] == "unknown_field:cwd"


def test_rejection_entry_has_no_request_id_when_it_cannot_be_read():
    record = _record()
    del record["request_id"]
    accepted, rejected = validate_batch([record])
    assert accepted == []
    assert rejected[0]["reason"] == "missing_field:request_id"
    assert rejected[0]["request_id"] is None
    assert rejected[0]["index"] == 0


def test_rejected_record_content_does_not_leak_through_json_dumps():
    """A distinctive file-path string seeded into a rejected record's `cwd`
    must never appear in the serialized rejection list -- the consent
    guarantee (no file paths collected) must hold structurally, not just by
    task 03 remembering to strip the record."""
    secret_path = "/home/zane/super-secret-project-path-should-not-leak"
    record = _record(cwd=secret_path)
    accepted, rejected = validate_batch([record])
    assert accepted == []
    serialized = json.dumps(rejected)
    assert secret_path not in serialized
    # The field NAME "cwd" legitimately appears as part of the reason
    # vocabulary (`unknown_field:cwd`) -- that names which rule fired, not
    # the record's content. What must never appear is the record's cwd
    # VALUE, asserted above.


def test_path_shaped_unknown_field_name_does_not_leak_into_reason():
    """The unknown-field NAME is client-controlled too. A path-shaped key
    must not be interpolated into the reason string -- fall back to the bare
    `unknown_field` reason."""
    secret_key = r"C:\Users\Zane\clients\SECRET-CLIENT-NAME\src"
    record = _record(**{secret_key: 1})
    accepted, rejected = validate_batch([record])
    assert accepted == []
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "unknown_field"
    serialized = json.dumps(rejected)
    assert "SECRET-CLIENT-NAME" not in serialized
    assert "Zane" not in serialized


@pytest.mark.parametrize("key", [
    "a" * 41,                 # over the 40-char bound
    "with space",
    "dotted.name",
    "dash-name",
])
def test_non_identifier_unknown_field_name_yields_bare_reason(key):
    accepted, rejected = validate_batch([_record(**{key: 1})])
    assert accepted == []
    assert rejected[0]["reason"] == "unknown_field"
    assert key not in json.dumps(rejected)


def test_identifier_shaped_unknown_field_name_is_still_interpolated():
    accepted, rejected = validate_batch([_record(**{"a" * 40: 1})])
    assert rejected[0]["reason"] == "unknown_field:" + "a" * 40


# --- Padded request_id must not slip the batch dedupe ----------------------

def test_padded_request_id_is_caught_by_dedupe_like_the_store_strips_it():
    """`insert_datapoint`/`insert_cost_datapoint` strip `request_id` before
    hashing it into `transcript_key`. If `validate_batch`'s dedupe compared
    raw, unstripped strings, `["rq1", " rq1 "]` would both be accepted here
    and then collide silently at insert time (INSERT OR IGNORE drops the
    second with no error). The dedupe here must strip identically."""
    first = _record(session_id="sess-pad", request_id="rq1", output_tokens=50)
    second = _record(session_id="sess-pad", request_id=" rq1 ", output_tokens=999)
    accepted, rejected = validate_batch([first, second])
    assert len(accepted) == 1
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "duplicate_request_id"


# --- AC4b: duplicate (session_id, request_id) within one batch -----------

def test_ac4b_duplicate_request_id_accepts_one_rejects_other():
    first = _record(session_id="sess-x", request_id="req-x", output_tokens=50)
    second = _record(session_id="sess-x", request_id="req-x", output_tokens=999)
    accepted, rejected = validate_batch([first, second])
    assert len(accepted) == 1
    assert accepted[0]["output_tokens"] == 50  # the first record's value, not summed
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "duplicate_request_id"

    mapped = map_record(accepted[0])
    by_type = {row["token_type"]: row for row in mapped["token_rows"]}
    assert by_type["output"]["tokens"] == 50


# --- AC5: cost equals RatingService's raw pre-markup value ----------------

def test_ac5_cost_matches_rating_service_raw_cost():
    rating = RatingService()
    record = _record(
        model="claude-sonnet-5",
        input_tokens=100000, output_tokens=50000,
        cache_read_input_tokens=200000, cache_creation_input_tokens=30000,
    )
    accepted, rejected = validate_batch([record])
    assert rejected == []
    mapped = map_record(accepted[0], rating)

    expected = (
        rating.raw_cost("claude-sonnet-5", "input", 100000)
        + rating.raw_cost("claude-sonnet-5", "output", 50000)
        + rating.raw_cost("claude-sonnet-5", "cacheRead", 200000)
        + rating.raw_cost("claude-sonnet-5", "cacheCreation", 30000)
    )
    assert mapped["cost_row"]["cost_usd"] == pytest.approx(expected)

    # Never marked up: raw_cost * markup would differ from raw_cost alone.
    billed_equiv = expected * rating.markup
    assert mapped["cost_row"]["cost_usd"] != pytest.approx(billed_equiv)


# --- AC6: identity round-trips ---------------------------------------------

def test_ac6_identity_fields_round_trip_onto_every_row():
    record = _record(
        user_email="carol@cyclotron.com", user_id="u-carol", org_id="org-acme")
    accepted, rejected = validate_batch([record])
    assert rejected == []
    mapped = map_record(accepted[0])

    for row in mapped["token_rows"]:
        assert row["user_email"] == "carol@cyclotron.com"
        assert row["user_id"] == "u-carol"
        assert row["org_id"] == "org-acme"

    cost_row = mapped["cost_row"]
    assert cost_row["user_email"] == "carol@cyclotron.com"
    assert cost_row["user_id"] == "u-carol"
    assert cost_row["org_id"] == "org-acme"


# --- AC6b: query_source round-trips and is validated ----------------------

@pytest.mark.parametrize("query_source", ["main", "subagent"])
def test_ac6b_query_source_round_trips(query_source):
    record = _record(query_source=query_source)
    accepted, rejected = validate_batch([record])
    assert rejected == []
    mapped = map_record(accepted[0])
    for row in mapped["token_rows"]:
        assert row["query_source"] == query_source
    assert mapped["cost_row"]["query_source"] == query_source


def test_ac6b_invalid_query_source_rejected():
    accepted, rejected = validate_batch([_record(query_source="bogus")])
    assert accepted == []
    assert rejected[0]["reason"] == "invalid_query_source"


# --- AC7: repo_raw='' maps to 'unknown' and is not rejected ---------------

def test_ac7_empty_repo_raw_maps_to_unknown_and_is_accepted():
    record = _record(repo_raw="")
    accepted, rejected = validate_batch([record])
    assert rejected == []
    mapped = map_record(accepted[0])
    for row in mapped["token_rows"]:
        assert row["repo"] == "unknown"
        assert row["repo_raw"] == ""
    assert mapped["cost_row"]["repo"] == "unknown"


# --- AC8: ssh/https spellings of one remote share a repo key -------------

def test_ac8_ssh_and_https_spellings_share_repo_key():
    ssh_record = _record(
        request_id="req-ssh",
        repo_raw="git@github.com:Cyclotron/Acme-Web.git")
    https_record = _record(
        request_id="req-https",
        repo_raw="https://github.com/Cyclotron/Acme-Web.git")
    accepted, rejected = validate_batch([ssh_record, https_record])
    assert rejected == []
    mapped_ssh = map_record(accepted[0])
    mapped_https = map_record(accepted[1])
    assert mapped_ssh["cost_row"]["repo"] == mapped_https["cost_row"]["repo"]
    assert mapped_ssh["cost_row"]["repo"] == normalize_remote(ssh_record["repo_raw"])


# --- AC9: emitted ts matches the store's ts column format -----------------

def test_ac9_emitted_ts_matches_store_column_format():
    record = _record(ts="2026-01-01T21:20:00.187Z")
    accepted, rejected = validate_batch([record])
    assert rejected == []
    mapped = map_record(accepted[0])
    assert mapped["ts"] == "2026-01-01T21:20:00Z"


def test_ac9_ts_without_milliseconds_round_trips_exactly():
    record = _record(ts="2026-01-01T00:00:00Z")
    accepted, rejected = validate_batch([record])
    assert rejected == []
    mapped = map_record(accepted[0])
    assert mapped["ts"] == "2026-01-01T00:00:00Z"


# --- Additional coverage: original record is never mutated ---------------

def test_validate_batch_does_not_mutate_input_records():
    record = _record()
    original = copy.deepcopy(record)
    validate_batch([record])
    assert record == original
