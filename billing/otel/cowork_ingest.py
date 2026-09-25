"""Pure OTLP/JSON payload parser for Claude Cowork telemetry.

This module has NO I/O and NO store access -- it takes an already-JSON-
parsed `ExportMetricsServiceRequest` dict and returns which rows are ready
for `CoworkStore.insert_datapoint` / `CoworkStore.insert_cost_datapoint`
(task 01) versus which datapoints/metrics were rejected and why. It mirrors
`transcript.py`'s pure-payload-contract pattern: this module decides
accept/reject, the caller (task 03's live receiver) owns the store write.

Task 03 (live receiver) and task 04 (reporting) both consume this module's
return shape directly, so the key names below are FROZEN by this task:

    {
      "token_rows": [ {kwargs for CoworkStore.insert_datapoint}, ... ],
      "cost_rows": [ {kwargs for CoworkStore.insert_cost_datapoint}, ... ],
      "metrics_seen": [ <str>, ... ],   # sorted, deduped metric names seen
                                          # across every resourceMetrics entry,
                                          # accepted or rejected -- same
                                          # debugging purpose as receiver.py's
                                          # ingest_metrics_payload's own
                                          # metrics_seen field. ONLY `str`
                                          # names are recorded: a non-string
                                          # `name` (int, float, bool, tuple,
                                          # list, ...) is skipped so the
                                          # final `sorted()` can never hit a
                                          # mixed-type comparison TypeError.
      "rejections": [ {"reason": <str>, "detail": <str>}, ... ],
    }

**FAIL-CLOSED IS THE CORE CONTRACT OF THIS MODULE.** Every value extracted
from the payload is treated as adversarial: wrong JSON type, unhashable,
non-finite, out of range, or simply absent. Every extraction step below is
wrapped so that a malformed VALUE degrades to "skip this attribute" / "reject
this datapoint" / "reject this metric", and a malformed CONTAINER (a field
that should be a list or dict but isn't) degrades to an explicit rejection
entry rather than a silent drop. Nothing but a non-dict `payload` itself may
ever raise out of `parse_cowork_payload` -- see the envelope-vs-record
section below.

`reason` strings (the prefixes a caller should match on):

    "unrecognized_service_name:<value or 'absent'>"
        -- a resourceMetrics entry's service.name resource attribute was not
           exactly KNOWN_SERVICE_NAME. One rejection per metric encountered
           under that entry (the mismatch is resource-level, so there is
           nothing datapoint-specific to report).
    "unrecognized_metric:<name>"
        -- inside a service.name="cowork" entry, a metric other than
           TOKEN_METRIC/COST_METRIC. One rejection per datapoint under that
           metric (when its dataPoints shape is itself well-formed; see
           "malformed_datapoints" below for the alternative).
    "malformed_datapoint:<field>"
        -- an individual datapoint under TOKEN_METRIC/COST_METRIC whose
           numeric value or timestamp is missing, non-numeric, of an
           unexpected JSON type, a bool masquerading as a number, non-finite
           (NaN/+-Infinity), fractional (for an integer-only field),
           negative, or out of the range this module (or the store) can
           safely hold; OR whose string-typed row field carries a value
           SQLite cannot bind (see "String row fields" below). `<field>` is
           one of "asInt", "asDouble", "time_unix_nano", "datapoint" (the
           dataPoint entry itself was not a dict), or the name of a string
           row field: "session_id", "repo", "user_email", "user_id",
           "org_id", "model", "query_source", "token_type". See "Numeric
           validation" and "String row fields" below for the exact rules.
    "malformed_resource_metrics" / "malformed_scope_metrics" / "malformed_metrics" / "malformed_datapoints"
        -- a resourceMetrics/scopeMetrics/metrics/dataPoints (or the sum/
           gauge object dataPoints lives under) field was PRESENT but not
           the list/dict shape OTLP requires. One rejection per such
           container, and parsing continues with that container treated as
           empty.
    "malformed_resource_metrics_entry" / "malformed_scope_metrics_entry" / "malformed_metric"
        -- an individual entry inside one of those lists was not a dict.
           One rejection per bad entry; that entry is skipped.

Envelope-vs-record distinction (mirroring `transcript.validate_batch`'s own
split): `parse_cowork_payload` RAISES `TypeError` only when `payload` itself
is not a dict -- an unusable envelope, nothing to iterate at all. EVERY
other malformed shape -- a non-list resourceMetrics/scopeMetrics/metrics/
dataPoints, a non-dict entry inside one of those lists, an unparseable
attribute (bad `value` shape, unhashable `key`, non-numeric/overflowing
`intValue`/`doubleValue`), or a malformed datapoint value/timestamp -- is a
per-record rejection. Parsing always finishes the rest of the payload; one
bad record/attribute/metric never poisons the batch.

Numeric validation (deliberately stricter than "does it convert without
raising", because a value that raises no exception can still be un-billable
or un-insertable garbage):
  - A JSON `true`/`false` is NEVER accepted as a numeric value anywhere
    (Python's `bool` is an `int` subclass -- `isinstance(True, int)` is
    True -- so this must be checked explicitly, first, everywhere a number
    is parsed).
  - A token count (`asInt`, or `asDouble` as a fallback) must be a whole
    number: an integer, an integer-formatted string, or a float with no
    fractional part. `3.7` is rejected, not truncated.
  - **A STRING for an integer field must be integer-formatted** (optional
    sign, decimal digits only -- `_INT_STRING_RE`). A float-formatted
    string such as `"1767312000000000001.0"` or `"1.767312000000000001e18"`
    is REJECTED outright, never parsed via `int(float(s))`: float has only
    53 bits of mantissa, so that round trip silently yields
    `1767312000000000000` -- a DIFFERENT value from the one sent, which for
    a timestamp also changes the row's dedup key. Accepting "3.0"-style
    whole-valued float strings buys nothing on the OTLP wire (int64 fields
    are string-encoded decimal integers there) and costs correctness above
    2**53, so the simpler, safer rule is to reject the whole class.
  - For the same reason a genuine JSON float (a Python `float`) for an
    integer field is accepted only when its magnitude is <= 2**53
    (`_MAX_EXACT_FLOAT_INT`) -- the largest range in which every integer
    is exactly representable, so `int(f)` is guaranteed to equal the value
    the sender's JSON encoder actually held. A whole-valued float above
    that bound has already lost precision on the wire and is rejected.
  - A token count must be >= 0 and must fit SQLite's signed 64-bit INTEGER
    column (`tokens INTEGER` in cowork_store.py's schema) -- SQLITE_INT64_MAX
    below. A value outside that range is rejected here, BEFORE it ever
    reaches `CoworkStore.insert_datapoint`, where it would otherwise raise
    `OverflowError` at bind time.
  - A cost value (`asDouble`, or `asInt` as a fallback) must be a FINITE
    float (`math.isfinite`) and >= 0. NaN or +-Infinity is rejected, never
    stored -- a stored NaN silently becomes SQL NULL and a stored Infinity
    poisons every `SUM(cost_usd)` downstream with no error raised anywhere,
    which is worse than an outright rejection.
  - A datapoint's timestamp (`timeUnixNano`, falling back to
    `startTimeUnixNano` -- see the two-tier note just below) must be a
    whole, non-negative number no larger than `MAX_TIME_UNIX_NANO` (chosen
    so `datetime.fromtimestamp` in `cowork_store._ns_to_iso` can always
    represent it without raising at insert time -- year 3000 UTC, safely
    inside the platform C runtime's working range; see that constant's own
    comment for why `datetime.max`'s theoretical year-9999 bound is NOT
    safe to use here). A negative or
    absurdly large timestamp (a 30-digit string, say) is rejected here
    rather than surfacing as an insert-time crash.
  - `int(...)`/`float(...)` conversions are wrapped in
    `(TypeError, ValueError, OverflowError)` -- OverflowError is
    reproducible via `int(huge_string)` -> `float(...)` on an out-of-range
    magnitude, or via a wire-level `Infinity`/`NaN` JSON literal (which
    `json.loads` parses to a Python float by default, matching how
    `receiver.py` itself parses request bodies) being converted onward.

**Timestamp two-tier fallback -- deliberately kept, clarified here because
the task file's "missing `timeUnixNano` entirely" wording needed this
resolution:** `timeUnixNano` absent but `startTimeUnixNano` present is NOT
treated as "missing entirely" -- the datapoint is accepted using
`startTimeUnixNano`, exactly matching `receiver.py`'s own existing
convention (`dp.get("timeUnixNano") or dp.get("startTimeUnixNano") or 0`).
Only when BOTH fields are absent (or both are unparseable) is the datapoint
rejected as `malformed_datapoint:time_unix_nano`. This module never applies
receiver.py's trailing `or 0` fallback, though: a datapoint with neither
timestamp field is fail-closed REJECTED here, not silently timestamped at
the Unix epoch the way receiver.py's OTEL pipeline (a file this goal must
never touch) still does today.

String row fields (`session_id`, `repo`, `repo_raw`, `user_email`,
`user_id`, `org_id`, `model`, `query_source`, `token_type`) are guaranteed
to be genuine `str` values in every returned row -- see `_str_field`. The
OTLP attribute layer (`_attr_value`) can legitimately hand back an `int`
(from `intValue`, unbounded -- a 30-digit `intValue` is a valid Python int
that SQLite cannot bind), a `float`, a `bool`, or -- because `boolValue` is
passed through unchecked, matching receiver.py -- ANY JSON value including
a list or dict. Every scalar (`str`/`int`/`float`/`bool`) is coerced with
`str()` when the row is built, exactly as receiver.py's `_common` does, so
the stored spelling is decided here and not by SQLite's TEXT affinity. Any
NON-scalar (list, dict, or anything else) in one of those fields REJECTS
that datapoint as `malformed_datapoint:<row field name>` -- a `model` of
`[1]` is malformed telemetry, and silently storing it as the string "[1]"
would corrupt a bill with a value nobody sent. This is approach (b) from
the fix-cycle brief: enforced at row construction, not at `_attr_value`,
so a bad datapoint-level attribute is an explicit, visible rejection rather
than a silent fall-back to the field's default (which is what tightening
`_attr_value` to drop the attribute would have produced).

`session_id` sentinel handling (mirrors receiver.py's own `_common`
convention, and the same previously-shipped defect it documents fixing):
a datapoint/resource attribute `session.id` that is present but falsy
(`0`, `""`) is coerced with `str()` and kept as its own distinct value --
it is NEVER collapsed into the same sentinel as a genuinely ABSENT
`session.id`. Only a truly missing `session.id` (the merged attribute dict
has no such key -- `_attr_value`/`_attrs` returned nothing for it) maps to
the `_SESSION_ID_ABSENT` sentinel string below.

Repo attribution: deliberately NOT resolved here. Per this goal's design
(see `cowork_store.py`'s module docstring and `billing/otel/cowork_attribute.py`),
Cowork rows store `repo`/`repo_raw` verbatim and unresolved; resolution
happens later, at report time. This module does not call
`billing.otel.normalize.normalize_remote` (or anything else) on a `repo`
attribute -- both `repo` and `repo_raw` in every returned row are the same
raw, unnormalized string read off the merged attributes (or `""` if absent).
`terminal.type` is read off the resource attributes only for use in a
rejection's `detail` string; it is NEVER included in a returned row dict,
since `CoworkStore.insert_datapoint`/`insert_cost_datapoint` (task 01's
frozen signatures) have no field for it.

**Deliberately duplicates a few lines of receiver.py's pure parsing helpers**
(`_attr_value`, `_attrs`, `_datapoints`-equivalent) as local, independent,
and considerably more defensive copies. This module must NEVER
`import billing.otel.receiver` for any reason: importing that module
executes `load_env()` and populates a module-level `AUTH_TOKEN` global as a
side effect, which would silently couple this module's behavior to the
existing `claude_code` pipeline's environment/secrets handling -- exactly
what this goal's isolation requirement forbids, even incidentally.
"""

from __future__ import annotations

import math
import re

#: The only `service.name` resource-attribute value this module accepts.
#: Anything else (including absent) is rejected. `receiver.py`'s existing
#: `claude_code` handling has no such filter and is untouched by this module.
KNOWN_SERVICE_NAME = "cowork"

#: The two metric names this module recognizes, per the goal's documented
#: assumption that Cowork reuses Claude Code's OTLP metric names and is
#: disambiguated purely by `service.name`. Defined as constants (not
#: repeated magic strings) so that assumption is visible and changeable in
#: exactly one place if real Cowork traffic proves it wrong.
TOKEN_METRIC = "claude_code.token.usage"
COST_METRIC = "claude_code.cost.usage"

#: Sentinel stored for a genuinely ABSENT session.id attribute. A present-
#: but-falsy value (0, "") is coerced with str() and kept as ITS OWN string
#: -- never collapsed into this sentinel. See module docstring.
_SESSION_ID_ABSENT = "unknown"

#: SQLite's signed 64-bit INTEGER column bound. `cowork_store.py`'s `tokens`
#: column is INTEGER; a Python int outside this range raises OverflowError
#: from the sqlite3 module at bind time, not before -- validated here so a
#: row this module returns can always actually be inserted.
SQLITE_INT64_MAX = 2**63 - 1

#: Token counts must be non-negative -- see module docstring's "Numeric
#: validation" section for why a negative count is rejected rather than
#: silently stored.
_MIN_TOKENS = 0

#: Bounds a `time_unix_nano` value must fall within to guarantee
#: `cowork_store._ns_to_iso`'s `datetime.fromtimestamp` call can represent it
#: without raising at insert time. `datetime`'s own documented range extends
#: to year 9999, but `fromtimestamp` is backed by the platform C runtime's
#: `localtime`/`gmtime`, which on Windows raises `OSError: [Errno 22]
#: Invalid argument` well below that (empirically, seconds much past
#: ~3001-01-19 UTC already fail there, confirmed by probing this exact
#: environment -- the failure is platform-specific, not merely theoretical).
#: 3000-01-01T00:00:00Z is comfortably inside the working range on every
#: platform this codebase runs on and is a round, easy-to-reason-about
#: boundary. Lower bound is the Unix epoch itself, matching `transcript.py`'s
#: own EPOCH_FLOOR_NANO convention (a pre-epoch timestamp is rejected
#: outright here rather than accepted -- see module docstring's Numeric
#: validation section, point on negative timestamps).
MAX_TIME_UNIX_NANO = 32_503_680_000_000_000_000  # 3000-01-01T00:00:00Z
_MIN_TIME_UNIX_NANO = 0

#: The only string spelling accepted for an INTEGER field (`asInt`,
#: `timeUnixNano`, `startTimeUnixNano`): optional sign, ASCII decimal digits,
#: nothing else -- exactly how OTLP/JSON encodes an int64. Deliberately
#: stricter than `int(s)`, which also accepts `"1_000"` underscores, and
#: deliberately excludes every float spelling (`"3.0"`, `"1e18"`), because
#: parsing those via `int(float(s))` silently loses precision above 2**53.
#: See module docstring's "Numeric validation".
_INT_STRING_RE = re.compile(r"[+-]?[0-9]+")

#: Largest magnitude at which every integer is exactly representable as an
#: IEEE-754 double. A genuine JSON float for an integer field is accepted
#: only within this bound; above it `int(f)` cannot be trusted to equal the
#: value the sender actually held. See module docstring's "Numeric validation".
_MAX_EXACT_FLOAT_INT = 2**53

#: Python types `str()` may safely coerce into a string row field. Anything
#: else (list, dict, ...) reaching a string field rejects the datapoint --
#: see module docstring's "String row fields".
_STR_FIELD_SCALARS = (str, int, float, bool)


# ---------------------------------------------------------------------------
# Local, independent, defensive copies of receiver.py's pure OTLP/JSON
# parsing helpers. Read receiver.py for reference only -- do NOT import it.
# See module docstring for why.
# ---------------------------------------------------------------------------

def _attr_value(v):
    """Parse one OTLP attribute `value` wrapper. Returns None for anything
    it can't confidently parse -- never raises, regardless of how malformed
    `v` is (not a dict, an unparseable numeric string, an overflowing
    number, a non-JSON-primitive wrapped value)."""
    if not isinstance(v, dict):
        return None
    try:
        if "stringValue" in v:
            sv = v["stringValue"]
            return sv if isinstance(sv, str) else str(sv)
        if "intValue" in v:
            raw = v["intValue"]
            if isinstance(raw, bool):
                return None
            return int(raw)
        if "doubleValue" in v:
            raw = v["doubleValue"]
            if isinstance(raw, bool):
                return None
            return float(raw)
        if "boolValue" in v:
            return v["boolValue"]
    except (TypeError, ValueError, OverflowError):
        return None
    return None


def _attrs(attr_list) -> dict:
    """Parse an OTLP attribute list into a flat dict, never emitting a None
    value for any key (a key whose value can't be parsed is dropped
    entirely rather than stored as None) -- mirrors receiver.py's own fixed
    behavior. Defensive against every layer being the wrong JSON type:
    `attr_list` not a list, an entry not a dict, `key` not hashable."""
    if not isinstance(attr_list, list):
        return {}
    result = {}
    for a in attr_list:
        if not isinstance(a, dict):
            continue
        v = _attr_value(a.get("value"))
        if v is None:
            continue
        key = a.get("key")
        try:
            result[key] = v
        except TypeError:
            # `key` isn't hashable (e.g. a list) -- skip this one attribute,
            # never let it crash the whole datapoint/resource.
            continue
    return result


def _extract_datapoints(metric: dict):
    """Returns `(datapoints, error)`. `error` is None on success, else a
    container-level rejection reason ("malformed_datapoints") -- `metric`'s
    `sum`/`gauge` field is present but not a dict, or its `dataPoints` field
    is present but not a list. Absence of `sum`/`gauge`/`dataPoints`
    entirely is NOT an error -- it just means zero datapoints."""
    container = metric.get("sum")
    if container is None:
        container = metric.get("gauge")
    if container is None:
        return [], None
    if not isinstance(container, dict):
        return [], "malformed_datapoints"
    dps = container.get("dataPoints")
    if dps is None:
        return [], None
    if not isinstance(dps, list):
        return [], "malformed_datapoints"
    return dps, None


def _merged_attrs(res_attrs: dict, dp: dict) -> dict:
    """Resource attrs merged with this datapoint's own attrs, datapoint
    winning on a shared key. Safe as a plain dict.update because `_attrs`
    above never returns a None value for any key."""
    merged = dict(res_attrs)
    merged.update(_attrs(dp.get("attributes") if isinstance(dp, dict) else None))
    return merged


def _session_id(merged: dict) -> str:
    raw = merged.get("session.id")
    return str(raw) if raw is not None else _SESSION_ID_ABSENT


def _reject(reason: str, detail: str) -> dict:
    return {"reason": reason, "detail": detail}


# ---------------------------------------------------------------------------
# Numeric parsing -- see module docstring's "Numeric validation" section.
# ---------------------------------------------------------------------------

def _to_whole_number(raw):
    """Parse `raw` into a Python int, requiring it to represent a WHOLE
    number with no fractional part, and rejecting bool and non-finite
    floats. Returns (value, ok); `ok` is False for anything this module
    won't trust as a token count or a timestamp.

    Precision rule (fix-cycle 2, issue C -- choice (a), reject outright):
    a string is accepted ONLY when it is integer-formatted
    (`_INT_STRING_RE`); there is deliberately NO `int(float(s))` fallback,
    because that round trip silently returns a different integer once the
    magnitude exceeds 2**53 (`"1767312000000000001.0"` -> 1767312000000000000).
    A genuine `float` is accepted only when whole AND within
    `_MAX_EXACT_FLOAT_INT`, for the same reason.
    """
    if isinstance(raw, bool):
        return None, False
    if isinstance(raw, int):
        return raw, True
    if isinstance(raw, float):
        if not math.isfinite(raw) or not raw.is_integer():
            return None, False
        if abs(raw) > _MAX_EXACT_FLOAT_INT:
            # Already lost precision on the wire -- int(raw) would be a
            # plausible-looking but wrong number. Reject, never guess.
            return None, False
        return int(raw), True
    if isinstance(raw, str):
        s = raw.strip()
        if not _INT_STRING_RE.fullmatch(s):
            return None, False
        try:
            return int(s), True
        except (TypeError, ValueError, OverflowError):
            return None, False
    return None, False


def _to_finite_float(raw):
    """Parse `raw` into a Python float, rejecting bool and any non-finite
    result (NaN, +-Infinity). Returns (value, ok)."""
    if isinstance(raw, bool):
        return None, False
    if isinstance(raw, (int, float)):
        try:
            f = float(raw)
        except (TypeError, ValueError, OverflowError):
            return None, False
    elif isinstance(raw, str):
        try:
            f = float(raw.strip())
        except (TypeError, ValueError, OverflowError):
            return None, False
    else:
        return None, False
    if not math.isfinite(f):
        return None, False
    return f, True


def _token_value(dp: dict):
    """Returns (value, error_field). error_field is None on success."""
    if "asInt" in dp:
        raw, field = dp["asInt"], "asInt"
    elif "asDouble" in dp:
        raw, field = dp["asDouble"], "asDouble"
    else:
        return None, "asInt"
    value, ok = _to_whole_number(raw)
    if not ok:
        return None, field
    if value < _MIN_TOKENS or value > SQLITE_INT64_MAX:
        return None, field
    return value, None


def _cost_value(dp: dict):
    """Returns (value, error_field). error_field is None on success."""
    if "asDouble" in dp:
        raw, field = dp["asDouble"], "asDouble"
    elif "asInt" in dp:
        raw, field = dp["asInt"], "asInt"
    else:
        return None, "asDouble"
    value, ok = _to_finite_float(raw)
    if not ok:
        return None, field
    if value < 0:
        return None, field
    return value, None


def _time_unix_nano(dp: dict):
    """Returns (value, error_field). error_field is None on success.

    See module docstring's "Timestamp two-tier fallback" note: `timeUnixNano`
    absent but `startTimeUnixNano` present is a normal accept via fallback,
    not an error; only both-absent (or both-unparseable) is malformed.
    """
    raw = dp.get("timeUnixNano")
    if raw is None:
        raw = dp.get("startTimeUnixNano")
    if raw is None:
        return None, "time_unix_nano"
    value, ok = _to_whole_number(raw)
    if not ok:
        return None, "time_unix_nano"
    if value < _MIN_TIME_UNIX_NANO or value > MAX_TIME_UNIX_NANO:
        return None, "time_unix_nano"
    return value, None


def _str_field(merged: dict, key: str, default: str):
    """Read attribute `key` off `merged` as a genuine `str` for a string
    row field. Returns (value, ok).

    Absent -> `default`. A present scalar (`str`/`int`/`float`/`bool`) is
    coerced with `str()`; a present-but-falsy scalar (`""`, `0`, `False`)
    falls back to `default`, preserving this module's original
    `merged.get(key) or default` coalescing for every field except
    `session_id` (which has its own sentinel rules -- see `_session_id`).
    Anything else (list, dict, ...) is unbindable by sqlite3 and returns
    `(None, False)` so the caller rejects the datapoint. See module
    docstring's "String row fields".
    """
    raw = merged.get(key)
    if raw is None:
        return default, True
    if not isinstance(raw, _STR_FIELD_SCALARS):
        return None, False
    if not raw:
        return default, True
    return str(raw), True


def _session_id_field(merged: dict):
    """`session_id` with its sentinel semantics (see module docstring), but
    subject to the same unbindable-type rejection as every other string
    field. Returns (value, ok)."""
    raw = merged.get("session.id")
    if raw is None:
        return _SESSION_ID_ABSENT, True
    if not isinstance(raw, _STR_FIELD_SCALARS):
        return None, False
    return _session_id(merged), True


#: (row field name, merged-attribute key, default) for every string field
#: shared by token and cost rows. Order is irrelevant to correctness; the
#: first failing field names the rejection.
_BASE_STR_FIELDS = (
    ("user_email", "user.email", ""),
    ("user_id", "user.id", ""),
    ("org_id", "organization.id", ""),
    ("model", "model", "unknown"),
    ("query_source", "query_source", "main"),
)


def _base_row(merged: dict) -> tuple[dict | None, str | None]:
    """Fields shared by a token row and a cost row -- everything except
    token_type/tokens (token rows only) and cost_usd (cost rows only).
    `repo`/`repo_raw` are deliberately the SAME raw, unresolved string --
    see module docstring.

    Returns (row, error_field); exactly one is not None. `error_field` is
    the row field whose attribute value could not be coerced to a genuine
    `str` (see `_str_field`)."""
    session_id, ok = _session_id_field(merged)
    if not ok:
        return None, "session_id"
    repo_raw, ok = _str_field(merged, "repo", "")
    if not ok:
        return None, "repo"
    row = dict(session_id=session_id, repo=repo_raw, repo_raw=repo_raw)
    for field, key, default in _BASE_STR_FIELDS:
        value, ok = _str_field(merged, key, default)
        if not ok:
            return None, field
        row[field] = value
    return row, None


def _string_field_rejection(kind: str, field: str) -> dict:
    return _reject(
        f"malformed_datapoint:{field}",
        f"{kind} datapoint attribute for {field} is not a string-coercible "
        "scalar (list/dict) -- SQLite cannot bind it")


def _build_token_row(res_attrs: dict, dp) -> tuple[dict | None, dict | None]:
    """Returns (row, rejection); exactly one is not None."""
    if not isinstance(dp, dict):
        return None, _reject("malformed_datapoint:datapoint",
                              "token dataPoint entry is not a dict")
    value, err = _token_value(dp)
    if err:
        return None, _reject(
            f"malformed_datapoint:{err}",
            "token datapoint numeric value missing, non-numeric, a bool, "
            "fractional, negative, non-finite, or out of range")
    nano, err = _time_unix_nano(dp)
    if err:
        return None, _reject(
            f"malformed_datapoint:{err}",
            "token datapoint has neither a usable timeUnixNano nor "
            "startTimeUnixNano (missing, non-numeric, negative, or out of "
            "range)")
    merged = _merged_attrs(res_attrs, dp)
    row, err = _base_row(merged)
    if err:
        return None, _string_field_rejection("token", err)
    token_type, ok = _str_field(merged, "type", "unknown")
    if not ok:
        return None, _string_field_rejection("token", "token_type")
    row["token_type"] = token_type
    row["tokens"] = value
    row["time_unix_nano"] = nano
    return row, None


def _build_cost_row(res_attrs: dict, dp) -> tuple[dict | None, dict | None]:
    """Returns (row, rejection); exactly one is not None."""
    if not isinstance(dp, dict):
        return None, _reject("malformed_datapoint:datapoint",
                              "cost dataPoint entry is not a dict")
    value, err = _cost_value(dp)
    if err:
        return None, _reject(
            f"malformed_datapoint:{err}",
            "cost datapoint numeric value missing, non-numeric, a bool, "
            "negative, or non-finite (NaN/Infinity)")
    nano, err = _time_unix_nano(dp)
    if err:
        return None, _reject(
            f"malformed_datapoint:{err}",
            "cost datapoint has neither a usable timeUnixNano nor "
            "startTimeUnixNano (missing, non-numeric, negative, or out of "
            "range)")
    merged = _merged_attrs(res_attrs, dp)
    row, err = _base_row(merged)
    if err:
        return None, _string_field_rejection("cost", err)
    row["cost_usd"] = value
    row["time_unix_nano"] = nano
    return row, None


def _get_list(container: dict, key: str, bad_reason: str):
    """Returns (list_value, rejection_or_None). A missing key is NOT an
    error (`([], None)`); a present-but-wrong-type value is (`([], reject)`)
    -- see module docstring's fail-closed container rule."""
    value = container.get(key)
    if value is None:
        return [], None
    if not isinstance(value, list):
        return [], _reject(bad_reason, f"{key!r} is present but not a list")
    return value, None


def parse_cowork_payload(payload: dict) -> dict:
    """Parse an OTLP/JSON `ExportMetricsServiceRequest` dict, routing
    Cowork token/cost datapoints into row dicts ready for
    `CoworkStore.insert_datapoint` / `CoworkStore.insert_cost_datapoint`,
    and everything else into `rejections`. See module docstring for the
    full return shape and rejection-reason vocabulary.

    Raises `TypeError` only when `payload` itself is not a dict -- an
    unusable envelope. Every other malformed shape is a per-record/per-
    container rejection; this function never raises for those and always
    finishes parsing the rest of the payload.
    """
    if not isinstance(payload, dict):
        raise TypeError(
            f"cowork payload must be a dict, got {type(payload).__name__}")

    token_rows: list[dict] = []
    cost_rows: list[dict] = []
    metrics_seen: set[str] = set()
    rejections: list[dict] = []

    resource_metrics, rej = _get_list(
        payload, "resourceMetrics", "malformed_resource_metrics")
    if rej is not None:
        rejections.append(rej)

    for rm in resource_metrics:
        if not isinstance(rm, dict):
            rejections.append(_reject(
                "malformed_resource_metrics_entry",
                "resourceMetrics entry is not a dict"))
            continue

        resource = rm.get("resource")
        res_attrs = (
            _attrs(resource.get("attributes"))
            if isinstance(resource, dict) else {}
        )
        service_name = res_attrs.get("service.name")
        terminal_type = res_attrs.get("terminal.type")
        mismatched_service = service_name != KNOWN_SERVICE_NAME
        value_label = service_name if service_name is not None else "absent"

        scope_metrics, rej = _get_list(
            rm, "scopeMetrics", "malformed_scope_metrics")
        if rej is not None:
            rejections.append(rej)

        for sm in scope_metrics:
            if not isinstance(sm, dict):
                rejections.append(_reject(
                    "malformed_scope_metrics_entry",
                    "scopeMetrics entry is not a dict"))
                continue

            metrics, rej = _get_list(sm, "metrics", "malformed_metrics")
            if rej is not None:
                rejections.append(rej)

            for metric in metrics:
                if not isinstance(metric, dict):
                    rejections.append(_reject(
                        "malformed_metric", "metrics entry is not a dict"))
                    continue

                name = metric.get("name")
                # Only a non-empty `str` is recorded in metrics_seen (fix-
                # cycle 2, issue A -- choice: SKIP, not str()-coerce). A
                # hashable non-string (5, 1.5, True, ("a",)) would insert
                # into the set fine and then crash the final `sorted()`
                # with a mixed-type '<' TypeError; an unhashable one (a
                # list) would crash `.add` itself. Skipping is preferred
                # over `str(name)` because a metric literally named "5"
                # must stay distinguishable from a malformed int name 5,
                # and metrics_seen is a debugging aid only -- a non-string
                # name can never match TOKEN_METRIC/COST_METRIC anyway, and
                # still surfaces through the rejection `detail` below.
                if isinstance(name, str) and name:
                    metrics_seen.add(name)

                if mismatched_service:
                    rejections.append(_reject(
                        f"unrecognized_service_name:{value_label}",
                        f"metric={name!r} terminal.type={terminal_type!r}"))
                    continue

                dps, dp_container_err = _extract_datapoints(metric)
                if dp_container_err is not None:
                    rejections.append(_reject(
                        dp_container_err,
                        f"metric={name!r} sum/gauge or dataPoints is "
                        "present but not the expected shape"))
                    continue

                if name == TOKEN_METRIC:
                    for dp in dps:
                        row, rejection = _build_token_row(res_attrs, dp)
                        if rejection is not None:
                            rejections.append(rejection)
                        else:
                            token_rows.append(row)
                elif name == COST_METRIC:
                    for dp in dps:
                        row, rejection = _build_cost_row(res_attrs, dp)
                        if rejection is not None:
                            rejections.append(rejection)
                        else:
                            cost_rows.append(row)
                else:
                    for _dp in dps:
                        rejections.append(_reject(
                            f"unrecognized_metric:{name}",
                            f"terminal.type={terminal_type!r}"))

    return {
        "token_rows": token_rows,
        "cost_rows": cost_rows,
        "metrics_seen": sorted(metrics_seen),
        "rejections": rejections,
    }
