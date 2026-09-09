"""Wire payload contract for desktop transcript usage: schema, validator, and
the mapping from one validated record to the store rows it becomes.

This module is the CONTRACT OWNER for the transcript payload -- three tasks
depend on the exact shape frozen here:

    - task 02 (this module) validates a batch against the schema and maps
      each accepted record to `token_usage` / `cost_usage` rows.
    - task 03 routes validated/mapped rows into `OtelStore` via
      `insert_datapoint` / `insert_cost_datapoint`.
    - task 06's Claude Code hook PRODUCES exactly this payload shape from the
      on-disk transcript JSONL files, one record per API request (it collapses
      cumulative streaming blocks to the terminal block before sending).

Pure and stdlib-only: no network, no filesystem, no database access, and no
import of anything outside the standard library. The receiver (not this
module) owns all I/O and store writes.

------------------------------------------------------------------------
THE WIRE PAYLOAD SCHEMA -- exactly these fields, nothing else
------------------------------------------------------------------------

    session_id                     str, REQUIRED  -- Claude Code session id.
    ts                              str, REQUIRED  -- ISO-8601 UTC timestamp of
                                                       the API request (accepts
                                                       an optional milliseconds
                                                       component and a trailing
                                                       'Z'); mapped to the
                                                       store's UTC-second `ts`
                                                       column format. VALIDATED
                                                       at validate_batch time
                                                       (rejection reason
                                                       `invalid_ts`), never
                                                       deferred to map_record.
                                                       A date-only value
                                                       ('2026-01-01') IS legal
                                                       and maps to midnight UTC
                                                       -- see `_validate_ts`.
    request_id                     str, REQUIRED  -- one API request's id.
                                                       NEVER sum/merge records
                                                       sharing a request_id --
                                                       task 06 already collapsed
                                                       each request to its
                                                       single terminal block.
    model                           str, REQUIRED  -- the model string as the
                                                       transcript recorded it.
    input_tokens                    int, optional  -- default 0.
    output_tokens                   int, optional  -- default 0.
    cache_read_input_tokens         int, optional  -- default 0.
    cache_creation_input_tokens     int, optional  -- default 0.
    repo_raw                        str, optional  -- the raw git remote URL,
                                                       resolved client-side
                                                       exactly as
                                                       deploy/claude-repo-tag.py
                                                       posts it today. ''
                                                       (empty string) is VALID
                                                       -- it is the
                                                       scratch-workspace case
                                                       and normalizes to the
                                                       'unknown' repo key.
    entrypoint                      str, REQUIRED  -- must be exactly
                                                       'claude-desktop'; any
                                                       other value is rejected,
                                                       server-side, regardless
                                                       of what the client sent.
    query_source                    str, REQUIRED  -- one of 'main' |
                                                       'subagent' | 'auxiliary'
                                                       (the enum otel_store.py
                                                       documents at its
                                                       token_usage.query_source
                                                       column). Required
                                                       because both
                                                       insert_datapoint and
                                                       insert_cost_datapoint
                                                       take it as a required
                                                       keyword and dp_key
                                                       includes it.
    user_email                      str, optional  -- default ''.
    user_id                         str, optional  -- default ''.
    org_id                          str, optional  -- default ''.

No other field is accepted -- an unknown field (including `cwd`, which is
DELIBERATELY absent; see the module-level note below) is a per-record
rejection, not a silently-ignored extra. The schema carries no field capable
of holding message content (no prompt, no response, no file contents).

Why `cwd` is not in the schema: the opt-in consent notice shown to developers
(`client-package/configure.py:109`, `client-package/INSTRUCTIONS.md:76`) says
"Not collected: your prompts, your code, file contents, or file paths." A
desktop `cwd` (e.g. `C:\\Users\\...\\AppData\\Roaming\\Claude\\scratch-
workspaces\\...`) IS a file path. `repo_raw` already carries everything
attribution needs. Rejecting any record that carries `cwd` (via the
unknown-field, fail-closed rule -- no special case needed) makes that consent
guarantee enforceable at the server boundary instead of resting on client
behavior.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .normalize import normalize_remote
from .rating import RatingService

# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

#: Every field the wire payload may carry. Fail-closed: anything else is a
#: per-record rejection (see `_validate_record`).
PAYLOAD_FIELDS = frozenset({
    "session_id",
    "ts",
    "request_id",
    "model",
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "repo_raw",
    "entrypoint",
    "query_source",
    "user_email",
    "user_id",
    "org_id",
})

#: Fields whose absence or falsy value makes a record unusable.
REQUIRED_FIELDS = ("session_id", "ts", "request_id", "model")

#: The four token fields this module knows how to map, in the order rows are
#: emitted, and the `token_usage.token_type` vocabulary each maps onto.
#: Names match `otel_store.py`'s vocabulary exactly: input | output |
#: cacheRead | cacheCreation.
TOKEN_TYPE_BY_FIELD = {
    "input_tokens": "input",
    "output_tokens": "output",
    "cache_read_input_tokens": "cacheRead",
    "cache_creation_input_tokens": "cacheCreation",
}

#: otel_store.py:31's query_source enum.
QUERY_SOURCES = frozenset({"main", "subagent", "auxiliary"})

#: The only entrypoint this ingest path accepts. Enforced server-side, never
#: trusting client-side filtering.
ALLOWED_ENTRYPOINT = "claude-desktop"

#: Maximum records per batch. Exported so task 06's hook can batch to this
#: exact size. A batch larger than this is an unusable ENVELOPE (raises
#: ValueError), not a per-record rejection -- one client must not be able to
#: stall the single-threaded receiver with an unbounded POST body.
MAX_BATCH_SIZE = 500

#: Desktop-sourced rows always carry these two literals -- frozen by task 01.
USAGE_SOURCE = "transcript"
COST_SOURCE = "rate_card"

#: The oldest instant a `ts` may name, in Unix nanoseconds: the Unix epoch
#: itself. This is a CONTRACT value, not a platform artifact. A pre-epoch `ts`
#: yields a negative nano and a year-<1970 `ts` column string, which sorts
#: BELOW every `session_repo_timeline` entry in `attribute.py`'s lexicographic
#: as-of join and falls outside every invoice period -- the row would be
#: accepted, stored, and then never invoiced, with no error raised anywhere.
#: Rejecting it here (reason `invalid_ts`) is checked explicitly so the
#: boundary is identical on every platform rather than being wherever the
#: host C library's `fromtimestamp` happens to give up.
EPOCH_FLOOR_NANO = 0

#: Per-record rejection reasons this module returns. Not exhaustive at the
#: string level (missing_field:* / invalid_tokens:* / unknown_field:* carry a
#: field-name suffix), but every prefix a caller might match on is listed here.
REJECTION_REASONS = (
    "not_a_dict",
    "missing_field",           # missing_field:<name>
    "invalid_ts",
    "invalid_entrypoint",
    "invalid_query_source",
    "invalid_tokens",          # invalid_tokens:<name>
    "unknown_field",           # unknown_field:<name> (name is only
                               # interpolated when it matches
                               # _SAFE_FIELD_NAME; otherwise bare)
    "duplicate_request_id",
)

#: An unknown field NAME is client-controlled and unbounded. It is only
#: echoed into the `unknown_field:<name>` reason when it looks like an
#: identifier; anything else (a path-shaped key, a very long key, a key with
#: separators) yields the bare `unknown_field` reason so no client-chosen
#: string rides out through the rejection channel.
_SAFE_FIELD_NAME = re.compile(r"^[A-Za-z0-9_]{1,40}$")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_record(record: Any) -> str | None:
    """Return a rejection reason string, or None if `record` is valid.

    Per-record only -- never raises. Envelope-level problems (not a list,
    oversized batch) are the caller's (`validate_batch`) responsibility and
    DO raise ValueError.
    """
    if not isinstance(record, dict):
        return "not_a_dict"

    unknown = set(record.keys()) - PAYLOAD_FIELDS
    if unknown:
        # Deterministic reason string (sorted) so tests can assert on it;
        # this is also how a `cwd` field gets rejected -- cwd is simply not
        # in PAYLOAD_FIELDS, no special case required. The NAME is client
        # controlled: only interpolate it when it is identifier-shaped,
        # otherwise emit the bare reason (see _SAFE_FIELD_NAME).
        name = sorted(str(k) for k in unknown)[0]
        if _SAFE_FIELD_NAME.match(name):
            return f"unknown_field:{name}"
        return "unknown_field"

    for field in REQUIRED_FIELDS:
        if not record.get(field):
            return f"missing_field:{field}"

    # Parse `ts` HERE, not in map_record. A malformed ts that escaped
    # validation would raise from map_record, outside the per-record scope
    # task 03 wraps, and turn one bad record into a 400 for the whole batch
    # -- exactly the batch-poisoning path per-record rejection exists to
    # prevent.
    if not _validate_ts(record["ts"]):
        return "invalid_ts"

    if record.get("entrypoint") != ALLOWED_ENTRYPOINT:
        return "invalid_entrypoint"

    if record.get("query_source") not in QUERY_SOURCES:
        return "invalid_query_source"

    for field in TOKEN_TYPE_BY_FIELD:
        if field not in record:
            continue
        value = record[field]
        if value is None:
            continue
        # Fail-closed, same as the unknown-field rule: a genuine int (never
        # bool, which is an int subclass) OR an integral float. `json.loads`
        # yields float for `100.0` and `1e2`, so a client that serializes
        # counts as floats would otherwise lose EVERY record; an integral
        # float converts losslessly in `_normalize_record`. A fractional
        # float (100.7) is still rejected -- `int()` would silently truncate
        # it and under-report by the fractional part.
        if isinstance(value, bool):
            return f"invalid_tokens:{field}"
        if isinstance(value, float):
            if not value.is_integer():
                return f"invalid_tokens:{field}"
        elif not isinstance(value, int):
            return f"invalid_tokens:{field}"
        if value < 0:
            return f"invalid_tokens:{field}"

    return None


def _validate_ts(ts: Any) -> bool:
    """True iff `ts` survives the exact round trip `map_record` performs:
    `_unix_nano_to_ts(_ts_to_unix_nano(ts))`.

    It IS map_record's timestamp work, run ahead of time, so a record that
    passes here can never blow up later in `map_record` (or in the store's
    `_ns_to_iso`, which takes the same `fromtimestamp` path on the same
    nanos). Both halves matter: `'0001-01-01T00:00:00Z'` PARSES fine, so a
    parse-only check would let it through and leave the formatting half
    unproven. Must be a `str`; a non-string (int epoch, None, list) is
    rejected rather than `.strip()`-ing into an AttributeError.

    Epoch floor: a timestamp before the Unix epoch (`nano <
    EPOCH_FLOOR_NANO`) is rejected as `invalid_ts`, IDENTICALLY on every
    platform, because the store's `ts` column and `attribute.py`'s
    lexicographic as-of join both assume post-epoch values -- a year-<1970
    `ts` sorts below every timeline entry and outside every invoice period,
    so the row would be accepted and then silently never invoiced. The
    check is explicit rather than inferred from whether the host C
    library's `fromtimestamp` happens to raise: that boundary sits at an
    undocumented point inside December 1969 on Windows and does not exist
    at all on the Linux image billing runs on, so leaning on it would put
    the accept/reject line of a billing-path validator under the platform's
    control. The `(ValueError, OverflowError, OSError)` catch stays as
    defense in depth for genuinely unexpected platform behaviour (bad
    format, out-of-range fields, far-future overflow) rather than as the
    definition of the lower boundary.

    Date-only decision: a bare date (`'2026-01-01'`) is ACCEPTED and maps to
    `2026-01-01T00:00:00Z`. Rationale: task 06 never emits one, so this is
    not a supported shape so much as a tolerated one; rejecting it would
    drop billable tokens over a precision loss, while accepting it only
    coarsens the `ts` column to midnight (the request_id-keyed transcript
    key is unaffected). If the as-of join ever needs sub-day precision to be
    guaranteed, tighten here and add `invalid_ts` coverage for the date-only
    case.

    Catches every exception the round trip can raise: ValueError (bad
    format, out-of-range fields), and OverflowError/OSError from
    `.timestamp()` / `fromtimestamp()` on dates outside the platform's
    representable range.
    """
    if not isinstance(ts, str):
        return False
    try:
        nano = _ts_to_unix_nano(ts)
        if nano < EPOCH_FLOOR_NANO:
            return False
        _unix_nano_to_ts(nano)
    except (ValueError, OverflowError, OSError):
        return False
    return True


def _normalize_record(record: dict) -> dict:
    """Fill in defaults for optional fields on an already-validated record.

    Does NOT strip whitespace on session_id/request_id -- transcript_key
    itself doesn't either; the store's insert_* methods do their own
    stripping. Passing already-stripped input into transcript_key (if a
    caller ever computes one directly) is the caller's job, per task 01.
    """
    normalized = dict(record)
    normalized["repo_raw"] = normalized.get("repo_raw") or ""
    for field in ("user_email", "user_id", "org_id"):
        normalized[field] = normalized.get(field) or ""
    for field in TOKEN_TYPE_BY_FIELD:
        normalized[field] = int(normalized.get(field) or 0)
    return normalized


def _reject(index: int, record: Any, reason: str) -> dict:
    """Build a content-free rejection entry.

    Deliberately carries NO record content -- not even a copy of a single
    field beyond `request_id` -- because a record can be rejected precisely
    FOR carrying disallowed content (`cwd`, an unknown field), and echoing it
    back out in the rejection list would defeat the fail-closed rule that got
    it rejected in the first place. `index` is the caller's batch position
    (always defined, even for `not_a_dict` / `missing_field:request_id`,
    where no `request_id` can be read at all) so task 03 always has SOME
    identifier to log or act on without guessing.
    """
    request_id = record.get("request_id") if isinstance(record, dict) else None
    if not isinstance(request_id, str):
        request_id = None
    return {"index": index, "request_id": request_id, "reason": reason}


def validate_batch(batch: Any) -> tuple[list[dict], list[dict]]:
    """Partition `batch` into accepted and rejected records.

    Returns `(accepted, rejected)`:
      - `accepted` is a list of normalized record dicts (schema fields only,
        optional fields defaulted) ready for `map_record`.
      - `rejected` is a list of content-free identifiers, each shaped exactly
        `{"index": <int>, "request_id": <str or None>, "reason": <str>}` --
        `index` is the record's position in `batch` (always defined);
        `request_id` is the record's `request_id` when it could be read as a
        string, else `None` (e.g. `not_a_dict`, or `missing_field:request_id`
        itself). Rejection entries NEVER carry the original record or any of
        its other fields -- a record rejected for carrying `cwd` (a file
        path) must not have that path ride back out through the rejection
        channel; every future disallowed field rides the same channel, so
        this is enforced structurally here rather than resting on task 03
        remembering to strip it.

    Raises `ValueError` ONLY for an unusable ENVELOPE:
      - `batch` is not a list.
      - `batch` has more than `MAX_BATCH_SIZE` records.

    Every other problem -- a missing required field, an unparseable `ts`
    (`invalid_ts`), a non-numeric, fractional, or negative token count, an
    unknown field (including `cwd`), a
    disallowed `entrypoint` or `query_source`, or two records in the same
    batch sharing `(session_id, request_id)` -- is a PER-RECORD rejection.
    One malformed record must never cost the rest of a batch its billing:
    task 06 drops a whole batch after its retry bound, so an
    all-or-nothing validator would silently discard every valid record
    behind one bad one.
    """
    if not isinstance(batch, list):
        raise ValueError(
            f"transcript batch must be a list, got {type(batch).__name__}")
    if len(batch) > MAX_BATCH_SIZE:
        raise ValueError(
            f"transcript batch of {len(batch)} exceeds MAX_BATCH_SIZE "
            f"({MAX_BATCH_SIZE})")

    accepted: list[dict] = []
    rejected: list[dict] = []
    seen_request_ids: set[tuple] = set()

    for index, record in enumerate(batch):
        reason = _validate_record(record)
        if reason is not None:
            rejected.append(_reject(index, record, reason))
            continue

        # Records are cumulative streaming snapshots ONLY before task 06's
        # client-side collapse; by the time they reach here there must be
        # exactly one per (session_id, request_id). A second one sharing that
        # pair is a client defect -- reject it rather than summing, since
        # summing cumulative snapshots over-bills by ~2.28x.
        #
        # Stripped exactly like `otel_store.insert_datapoint` strips
        # `request_id` before hashing it into `transcript_key` -- an
        # unstripped dedupe key here would let `["rq1", " rq1 "]` both pass
        # this check (they compare unequal as raw strings), then collide
        # silently at insert time once the store strips and hashes them to
        # the identical key, with INSERT OR IGNORE dropping the second one
        # with no error anywhere.
        dedupe_key = (
            str(record["session_id"]).strip(),
            str(record["request_id"]).strip(),
        )
        if dedupe_key in seen_request_ids:
            rejected.append(_reject(index, record, "duplicate_request_id"))
            continue
        seen_request_ids.add(dedupe_key)

        accepted.append(_normalize_record(record))

    return accepted, rejected


# ---------------------------------------------------------------------------
# Timestamp handling -- the `ts` COLUMN format (unrelated to transcript_key,
# which no longer depends on time; see otel_store.py's transcript_key).
# ---------------------------------------------------------------------------

def _ts_to_unix_nano(ts: str) -> int:
    """Parse the payload's `ts` (ISO-8601 UTC, optional milliseconds, `Z`
    suffix) into integer Unix nanoseconds."""
    s = ts.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1_000_000_000)


def _unix_nano_to_ts(nano: int) -> str:
    """Format Unix nanoseconds as the store's UTC-second `ts` column string.

    Deliberately the same format `otel_store._ns_to_iso` produces
    (`%Y-%m-%dT%H:%M:%SZ`) so `attribute.py`'s lexicographic as-of join works
    unchanged for transcript-sourced rows.
    """
    dt = datetime.fromtimestamp(nano / 1_000_000_000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Mapping: one validated record -> up to four token_usage rows + one
# cost_usage row.
# ---------------------------------------------------------------------------

def map_record(record: dict, rating: RatingService | None = None) -> dict:
    """Map one validated, normalized record (as returned in
    `validate_batch`'s `accepted` list) to the store rows it becomes.

    Returns:
        {
          "ts": <store ts-column string>,
          "token_rows": [ {kwargs for OtelStore.insert_datapoint}, ... ],
          "cost_row": { kwargs for OtelStore.insert_cost_datapoint },
        }

    `token_rows` holds ZERO to FOUR rows -- a token type whose count is zero
    or absent is omitted entirely (never written as a zero row). Exactly one
    `cost_row` is always produced, computed via `RatingService.raw_cost`
    (matching `bill.py:96`'s `rates.billed(...) / markup` convention: same
    value, no markup, no double round-trip through a multiply-then-divide).

    Does not call the store. Does not apply markup -- `bill.py` owns markup;
    this emits raw, pre-markup cost.
    """
    rating = rating or RatingService()

    nano = _ts_to_unix_nano(record["ts"])
    ts = _unix_nano_to_ts(nano)
    repo_raw = record.get("repo_raw") or ""
    repo = normalize_remote(repo_raw)

    # Fields shared by every row this record produces. Deliberately excludes
    # token_type/tokens/entrypoint (token rows only) and cost_usd/cost_source
    # (cost row only) so each row dict below is exactly the keyword set its
    # target insert_* method accepts -- no stray kwargs.
    base = dict(
        session_id=record["session_id"],
        repo=repo,
        repo_raw=repo_raw,
        user_email=record.get("user_email") or "",
        user_id=record.get("user_id") or "",
        org_id=record.get("org_id") or "",
        model=record["model"],
        query_source=record["query_source"],
        time_unix_nano=nano,
        usage_source=USAGE_SOURCE,
        request_id=record["request_id"],
    )

    token_rows = []
    total_cost = 0.0
    for field, token_type in TOKEN_TYPE_BY_FIELD.items():
        tokens = int(record.get(field) or 0)
        if tokens <= 0:
            continue
        row = dict(base)
        row["token_type"] = token_type
        row["tokens"] = tokens
        row["entrypoint"] = ALLOWED_ENTRYPOINT
        token_rows.append(row)
        total_cost += rating.raw_cost(record["model"], token_type, tokens)

    cost_row = dict(base)
    cost_row["cost_usd"] = total_cost
    cost_row["cost_source"] = COST_SOURCE

    return {"ts": ts, "token_rows": token_rows, "cost_row": cost_row}
