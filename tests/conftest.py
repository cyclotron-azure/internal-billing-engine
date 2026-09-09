"""Shared pytest fixtures for internal-billing-engine tests.

Built by task 00 of the `desktop-usage-capture` goal, BEFORE any production file
in that goal was touched. Two things live here for that reason:

1. A frozen, pre-task-01 copy of `otel_store.SCHEMA` (see LEGACY_SCHEMA below),
   so task 01's migration test exercises the real legacy path. This is copied
   VERBATIM as a string literal, not imported, because task 01 changes the
   value `otel_store.SCHEMA` points to -- importing it would silently turn this
   "legacy" fixture into the new schema and destroy the migration test's value.
2. Synthetic transcript / OTLP fixtures that later tasks (01-07) build their
   targeted tests on top of, plus the published "correct" totals those tests
   assert against instead of re-deriving (and re-deriving wrongly).

Every fixture that needs a database uses `tmp_path`. Nothing here ever touches
`data/otel.db` or any path two tests could race on.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from billing.otel.otel_store import OtelStore

# ---------------------------------------------------------------------------
# 1. Legacy (pre-task-01) schema -- frozen verbatim from
#    billing/otel/otel_store.py lines 19-122, as it existed before task 01
#    added `usage_source` / `entrypoint` (token_usage) and `usage_source` /
#    `cost_source` (cost_usage). DO NOT replace this with
#    `from billing.otel.otel_store import SCHEMA` -- see module docstring.
# ---------------------------------------------------------------------------

LEGACY_SCHEMA = """
CREATE TABLE IF NOT EXISTS token_usage (
  dp_key TEXT PRIMARY KEY,          -- dedupe key (dims + timestamp)
  ts TEXT,                          -- data point time (UTC)
  session_id TEXT,
  repo TEXT,                        -- normalized repo key (attribution unit)
  repo_raw TEXT,                    -- original OTEL_RESOURCE_ATTRIBUTES repo value
  user_email TEXT,
  user_id TEXT,
  org_id TEXT,
  model TEXT,
  token_type TEXT,                  -- input | output | cacheRead | cacheCreation
  query_source TEXT,                -- main | subagent | auxiliary
  tokens INTEGER,
  ingested_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_token_repo ON token_usage(repo);

CREATE TABLE IF NOT EXISTS cost_usage (
  dp_key TEXT PRIMARY KEY,          -- dedupe key (dims + timestamp)
  ts TEXT,
  session_id TEXT,
  repo TEXT,
  repo_raw TEXT,
  user_email TEXT,
  user_id TEXT,
  org_id TEXT,
  model TEXT,
  query_source TEXT,
  cost_usd REAL,                    -- Anthropic's actual USD for this datapoint
  ingested_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_cost_repo ON cost_usage(repo);

CREATE TABLE IF NOT EXISTS session_repo_timeline (
  session_id TEXT,                  -- joins to token_usage.session_id / cost_usage.session_id
  ts TEXT,                          -- UTC second when this repo became active
                                    -- (SAME format as token_usage.ts so the
                                    --  as-of join can compare lexicographically)
  seq INTEGER,                      -- ms-within-second, orders events inside one second
  repo TEXT,                        -- normalized repo key ('unknown' if no remote)
  repo_raw TEXT,                    -- original git remote URL
  cwd TEXT,                         -- working directory that produced it
  event TEXT,                       -- SessionStart | CwdChanged | DirectoryAdded | SessionEnd
  ingested_at TEXT,
  PRIMARY KEY (session_id, ts, seq, repo)   -- a byte-identical replay of one
                                            -- POST is a no-op; separate hook
                                            -- firings carry distinct seq and
                                            -- are kept as separate entries
);
CREATE INDEX IF NOT EXISTS ix_timeline_session ON session_repo_timeline(session_id, ts);

CREATE TABLE IF NOT EXISTS repo_name_map (
  repo TEXT PRIMARY KEY,            -- normalized repo key
  bill_name TEXT,                   -- OPTIONAL override billing name
                                    -- (defaults to the short repo name if absent)
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS invoices (
  invoice_number TEXT PRIMARY KEY,
  bill_name TEXT,                  -- billing entity: the repo name (or its override)
  period_start TEXT,
  period_end TEXT,
  currency TEXT,
  actual_cost REAL,                -- summed claude_code.cost.usage for the period
  markup REAL,
  total_billed REAL,               -- actual_cost * markup
  tokens INTEGER,
  status TEXT,                     -- draft | issued
  generated_at TEXT
);
CREATE TABLE IF NOT EXISTS invoice_line_items (
  invoice_number TEXT,
  repo TEXT,
  model TEXT,
  tokens INTEGER,
  actual_cost REAL,
  billed_amount REAL
);
CREATE INDEX IF NOT EXISTS ix_lineitem_inv ON invoice_line_items(invoice_number);

-- Durable outbox for asynchronous delivery of invoice CSVs to Fabric OneLake.
-- invoice.py enqueues a 'pending' row per file; billing.otel.fabric_sync ships
-- it with retry/backoff and flips it to 'sent'. Nothing is lost on a crash.
CREATE TABLE IF NOT EXISTS fabric_outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT,                       -- 'summary' | 'line_items'
  period_start TEXT,
  period_end TEXT,
  local_path TEXT,                 -- source CSV on disk
  onelake_path TEXT,               -- destination path under the Lakehouse's Files/
  table_name TEXT,                 -- optional Delta table to load into ('' = files only)
  status TEXT,                     -- pending | sent | failed
  attempts INTEGER DEFAULT 0,
  next_attempt_at TEXT,            -- earliest UTC time to (re)try
  last_error TEXT,
  enqueued_at TEXT,
  sent_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_outbox_status ON fabric_outbox(status, next_attempt_at);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


@pytest.fixture
def tmp_db_path(tmp_path) -> str:
    """A path to a SQLite database file under tmp_path. The file does not exist
    yet -- OtelStore(path) or sqlite3.connect(path) create it on first use.
    Never data/otel.db, never a path two tests could race on."""
    return str(tmp_path / "otel.db")


@pytest.fixture
def legacy_schema_db_path(tmp_path) -> str:
    """Build a database at the CURRENT (pre-task-01) schema -- LEGACY_SCHEMA,
    frozen above -- and return its path. `PRAGMA table_info(token_usage)` on
    this database lacks `usage_source` and `entrypoint`; task 01's migration
    test exercises its ALTER TABLE path against this fixture, not an
    already-correct schema."""
    path = str(tmp_path / "legacy_otel.db")
    conn = sqlite3.connect(path)
    try:
        conn.executescript(LEGACY_SCHEMA)
        conn.commit()
    finally:
        conn.close()
    return path


# ---------------------------------------------------------------------------
# 2. Synthetic transcript fixtures -- raw Claude Code on-disk JSONL shape.
#
# A real assistant row looks like (fields per goal.md's Phase 1 discovery):
#   sessionId, requestId, isSidechain, entrypoint, cwd, gitBranch, timestamp,
#   apiBlockIndex, message{id, model, stop_reason, usage{input_tokens,
#   output_tokens, cache_creation_input_tokens, cache_read_input_tokens}}
# ---------------------------------------------------------------------------

def _usage_row(
    *,
    session_id: str,
    request_id: str,
    message_id: str,
    api_block_index: int | None,
    stop_reason: str | None,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int,
    cache_read_input_tokens: int,
    model: str = "claude-sonnet-5",
    entrypoint: str = "claude-desktop",
    is_sidechain: bool = False,
    cwd: str = "/home/dev/acme-web",
    git_branch: str = "main",
    timestamp: str = "2026-01-01T00:00:00.000Z",
) -> dict:
    """Build one raw transcript row. `api_block_index=None` OMITS the field
    entirely (matching the real "absent" case task 06 criterion 1f exercises),
    rather than writing a JSON null."""
    row: dict = {
        "type": "assistant",
        "sessionId": session_id,
        "requestId": request_id,
        "isSidechain": is_sidechain,
        "entrypoint": entrypoint,
        "cwd": cwd,
        "gitBranch": git_branch,
        "timestamp": timestamp,
        "message": {
            "id": message_id,
            "model": model,
            "stop_reason": stop_reason,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
            },
        },
    }
    if api_block_index is not None:
        row["apiBlockIndex"] = api_block_index
    return row


# --- identifiers reused across the tree ------------------------------------

SESSION_A_ID = "sess-desktop-a"          # main session, project_dir_a
SESSION_B_ID = "sess-desktop-b"          # second session, project_dir_b (cross-dir sweep)
AGENT_1_ID = "11111111"                  # subagent under SESSION_A_ID

# --- cumulative multi-block group: dominant real shape ---------------------
# Constant input/cache, growing output; terminal block = highest apiBlockIndex.
# Modelled exactly on the real observed pair in goal.md / 00-test-scaffold.md.
MULTI_BLOCK_REQUEST_ID = "req-multiblock-001"
MULTI_BLOCK_MESSAGE_ID = "msg-multiblock-001"
MULTI_BLOCK_INPUT = 2
MULTI_BLOCK_CACHE_CREATION = 13984
MULTI_BLOCK_CACHE_READ = 35774
MULTI_BLOCK_OUTPUT_PARTIAL = 5        # apiBlockIndex=0, stop_reason=None (in-flight snapshot)
MULTI_BLOCK_OUTPUT_TERMINAL = 209     # apiBlockIndex=1, stop_reason='tool_use' (correct total)

# --- exact-duplicate pair: the ONLY real claude-desktop shape observed ------
# Both rows carry a NON-NULL stop_reason -- proves stop_reason alone cannot
# select the terminal block; highest apiBlockIndex must.
DUPLICATE_REQUEST_ID = "req-duplicate-001"
DUPLICATE_MESSAGE_ID = "msg-duplicate-001"
DUPLICATE_INPUT = 10
DUPLICATE_OUTPUT = 543
DUPLICATE_CACHE_CREATION = 1000
DUPLICATE_CACHE_READ = 2000

# --- sidechain (subagent) group, one level under project_dir_a -------------
SIDECHAIN_REQUEST_ID = "req-sidechain-001"
SIDECHAIN_MESSAGE_ID = "msg-sidechain-001"
SIDECHAIN_INPUT = 3
SIDECHAIN_OUTPUT = 50
SIDECHAIN_CACHE_CREATION = 500
SIDECHAIN_CACHE_READ = 1500

# --- second project directory: an unrelated session, for the cross-dir sweep
SECOND_PROJECT_REQUEST_ID = "req-project-b-001"
SECOND_PROJECT_MESSAGE_ID = "msg-project-b-001"

# --- published expected totals ---------------------------------------------
# The TERMINAL block's values, selected by highest apiBlockIndex -- neither
# the sum (over-bills) nor the first block (under-bills). Tasks 02/06/07
# assert exact equality against these instead of re-deriving them.
EXPECTED_MAIN_ONLY_TOTALS = {
    "input_tokens": MULTI_BLOCK_INPUT + DUPLICATE_INPUT,
    "output_tokens": MULTI_BLOCK_OUTPUT_TERMINAL + DUPLICATE_OUTPUT,
    "cache_creation_input_tokens": MULTI_BLOCK_CACHE_CREATION + DUPLICATE_CACHE_CREATION,
    "cache_read_input_tokens": MULTI_BLOCK_CACHE_READ + DUPLICATE_CACHE_READ,
}
EXPECTED_MAIN_ONLY_TOTAL_TOKENS = sum(EXPECTED_MAIN_ONLY_TOTALS.values())

EXPECTED_SIDECHAIN_ONLY_TOTALS = {
    "input_tokens": SIDECHAIN_INPUT,
    "output_tokens": SIDECHAIN_OUTPUT,
    "cache_creation_input_tokens": SIDECHAIN_CACHE_CREATION,
    "cache_read_input_tokens": SIDECHAIN_CACHE_READ,
}
EXPECTED_SIDECHAIN_ONLY_TOTAL_TOKENS = sum(EXPECTED_SIDECHAIN_ONLY_TOTALS.values())

EXPECTED_COMBINED_TOTAL_TOKENS = (
    EXPECTED_MAIN_ONLY_TOTAL_TOKENS + EXPECTED_SIDECHAIN_ONLY_TOTAL_TOKENS
)
assert EXPECTED_COMBINED_TOTAL_TOKENS > EXPECTED_MAIN_ONLY_TOTAL_TOKENS, (
    "combined must be strictly greater than main-only -- if this ever trips, "
    "the sidechain group's tokens have been zeroed out above"
)


def _build_projects_tree(root: Path) -> dict:
    """Build the REAL nested projects layout:

        <root>/
          project-acme-web/
            sess-desktop-a.jsonl                              <- main transcript
            sess-desktop-a/subagents/agent-11111111.jsonl     <- sidechain, one level deeper
          project-globex-api/
            sess-desktop-b.jsonl                               <- second project dir

    The nesting is load-bearing (see task 00 requirement 2 / task 06 criterion
    1d-bis): a flat glob of project-acme-web/*.jsonl must find fewer files than
    a recursive walk of `root`.
    """
    project_dir_a = root / "project-acme-web"
    project_dir_b = root / "project-globex-api"
    project_dir_a.mkdir(parents=True)
    project_dir_b.mkdir(parents=True)

    main_path = project_dir_a / f"{SESSION_A_ID}.jsonl"
    sidechain_dir = project_dir_a / SESSION_A_ID / "subagents"
    sidechain_dir.mkdir(parents=True)
    sidechain_path = sidechain_dir / f"agent-{AGENT_1_ID}.jsonl"
    second_project_path = project_dir_b / f"{SESSION_B_ID}.jsonl"

    main_rows = [
        _usage_row(
            session_id=SESSION_A_ID, request_id=MULTI_BLOCK_REQUEST_ID,
            message_id=MULTI_BLOCK_MESSAGE_ID, api_block_index=0,
            stop_reason=None, input_tokens=MULTI_BLOCK_INPUT,
            output_tokens=MULTI_BLOCK_OUTPUT_PARTIAL,
            cache_creation_input_tokens=MULTI_BLOCK_CACHE_CREATION,
            cache_read_input_tokens=MULTI_BLOCK_CACHE_READ,
            timestamp="2026-01-01T21:19:53.999Z",
        ),
        _usage_row(
            session_id=SESSION_A_ID, request_id=MULTI_BLOCK_REQUEST_ID,
            message_id=MULTI_BLOCK_MESSAGE_ID, api_block_index=1,
            stop_reason="tool_use", input_tokens=MULTI_BLOCK_INPUT,
            output_tokens=MULTI_BLOCK_OUTPUT_TERMINAL,
            cache_creation_input_tokens=MULTI_BLOCK_CACHE_CREATION,
            cache_read_input_tokens=MULTI_BLOCK_CACHE_READ,
            timestamp="2026-01-01T21:20:00.187Z",
        ),
        _usage_row(
            session_id=SESSION_A_ID, request_id=DUPLICATE_REQUEST_ID,
            message_id=DUPLICATE_MESSAGE_ID, api_block_index=0,
            stop_reason="end_turn", input_tokens=DUPLICATE_INPUT,
            output_tokens=DUPLICATE_OUTPUT,
            cache_creation_input_tokens=DUPLICATE_CACHE_CREATION,
            cache_read_input_tokens=DUPLICATE_CACHE_READ,
            timestamp="2026-01-01T21:21:00.000Z",
        ),
        _usage_row(
            session_id=SESSION_A_ID, request_id=DUPLICATE_REQUEST_ID,
            message_id=DUPLICATE_MESSAGE_ID, api_block_index=1,
            stop_reason="end_turn", input_tokens=DUPLICATE_INPUT,
            output_tokens=DUPLICATE_OUTPUT,
            cache_creation_input_tokens=DUPLICATE_CACHE_CREATION,
            cache_read_input_tokens=DUPLICATE_CACHE_READ,
            timestamp="2026-01-01T21:21:00.050Z",
        ),
    ]
    # Deliberately malformed trailing line -- transcripts are appended live;
    # the last line may be a partial write. No trailing newline, on purpose.
    main_path.write_text(
        "\n".join(json.dumps(r) for r in main_rows)
        + "\n{\"sessionId\": \"sess-desktop-a\", \"truncated mid-writ",
        encoding="utf-8",
    )

    sidechain_rows = [
        _usage_row(
            session_id=SESSION_A_ID, request_id=SIDECHAIN_REQUEST_ID,
            message_id=SIDECHAIN_MESSAGE_ID, api_block_index=0,
            stop_reason="end_turn", input_tokens=SIDECHAIN_INPUT,
            output_tokens=SIDECHAIN_OUTPUT,
            cache_creation_input_tokens=SIDECHAIN_CACHE_CREATION,
            cache_read_input_tokens=SIDECHAIN_CACHE_READ,
            is_sidechain=True, timestamp="2026-01-01T21:22:00.000Z",
        ),
    ]
    sidechain_path.write_text(
        "\n".join(json.dumps(r) for r in sidechain_rows) + "\n", encoding="utf-8",
    )

    second_rows = [
        _usage_row(
            session_id=SESSION_B_ID, request_id=SECOND_PROJECT_REQUEST_ID,
            message_id=SECOND_PROJECT_MESSAGE_ID, api_block_index=0,
            stop_reason="end_turn", input_tokens=7, output_tokens=99,
            cache_creation_input_tokens=250, cache_read_input_tokens=900,
            cwd="/home/dev/globex-api", git_branch="develop",
            timestamp="2026-01-01T21:25:00.000Z",
        ),
    ]
    second_project_path.write_text(
        "\n".join(json.dumps(r) for r in second_rows) + "\n", encoding="utf-8",
    )

    return {
        "projects_root": root,
        "project_dir_a": project_dir_a,
        "project_dir_b": project_dir_b,
        "main_path": main_path,
        "sidechain_path": sidechain_path,
        "second_project_path": second_project_path,
    }


@pytest.fixture
def projects_tree(tmp_path) -> dict:
    """The nested projects tree described in `_build_projects_tree`, rooted
    under tmp_path. A FLAT glob of `project_dir_a` (`*.jsonl`) finds only
    `main_path` (1 file); a recursive walk of `projects_root` finds
    `main_path` + `sidechain_path` + `second_project_path` (3 files) -- proving
    the fixture actually reproduces the nesting task 06's hook must walk."""
    root = tmp_path / "claude_projects"
    return _build_projects_tree(root)


@pytest.fixture
def transcript_expected_totals() -> dict:
    """Published expected totals for `projects_tree`'s desktop-billable groups
    (query_source='main' / 'subagent', entrypoint='claude-desktop' only --
    the entrypoint-mix and second-project-dir rows are not counted here).
    Combined is strictly greater than main-only; see the module-level assert
    above for the enforced invariant."""
    return {
        "main_only": dict(EXPECTED_MAIN_ONLY_TOTALS, total=EXPECTED_MAIN_ONLY_TOTAL_TOKENS),
        "sidechain_only": dict(
            EXPECTED_SIDECHAIN_ONLY_TOTALS, total=EXPECTED_SIDECHAIN_ONLY_TOTAL_TOKENS
        ),
        "combined_total": EXPECTED_COMBINED_TOTAL_TOKENS,
    }


# --- entrypoint mix: claude-desktop / cli / claude-vscode + malformed line --

ENTRYPOINT_MIX_ENTRYPOINTS = ("claude-desktop", "cli", "claude-vscode")


def _build_entrypoint_mix_file(path: Path) -> None:
    rows = [
        _usage_row(
            session_id=f"sess-{ep}", request_id=f"req-{ep}", message_id=f"msg-{ep}",
            api_block_index=0, stop_reason="end_turn", input_tokens=1, output_tokens=1,
            cache_creation_input_tokens=0, cache_read_input_tokens=0,
            entrypoint=ep, timestamp="2026-01-01T21:30:00.000Z",
        )
        for ep in ENTRYPOINT_MIX_ENTRYPOINTS
    ]
    path.write_text(
        "\n".join(json.dumps(r) for r in rows)
        + "\n{\"entrypoint\": \"cli\", \"truncated mid-writ",
        encoding="utf-8",
    )


@pytest.fixture
def entrypoint_mix_transcript(tmp_path) -> Path:
    """A single transcript file carrying one record per entrypoint
    (claude-desktop, cli, claude-vscode) plus a deliberately malformed
    trailing line -- for tests of entrypoint filtering (task 02/03/06)."""
    path = tmp_path / "entrypoint_mix.jsonl"
    _build_entrypoint_mix_file(path)
    return path


# --- in-flight session: trailing group holds only apiBlockIndex=0 ----------

INFLIGHT_SESSION_ID = "sess-inflight-001"
INFLIGHT_REQUEST_ID = "req-inflight-001"
INFLIGHT_MESSAGE_ID = "msg-inflight-001"
INFLIGHT_INPUT = 4
INFLIGHT_CACHE_CREATION = 800
INFLIGHT_CACHE_READ = 1600
INFLIGHT_OUTPUT_PARTIAL = 5
INFLIGHT_OUTPUT_TERMINAL = 209


def _inflight_partial_row() -> dict:
    return _usage_row(
        session_id=INFLIGHT_SESSION_ID, request_id=INFLIGHT_REQUEST_ID,
        message_id=INFLIGHT_MESSAGE_ID, api_block_index=0,
        stop_reason=None, input_tokens=INFLIGHT_INPUT,
        output_tokens=INFLIGHT_OUTPUT_PARTIAL,
        cache_creation_input_tokens=INFLIGHT_CACHE_CREATION,
        cache_read_input_tokens=INFLIGHT_CACHE_READ,
        timestamp="2026-01-01T21:40:00.000Z",
    )


def _inflight_terminal_row() -> dict:
    return _usage_row(
        session_id=INFLIGHT_SESSION_ID, request_id=INFLIGHT_REQUEST_ID,
        message_id=INFLIGHT_MESSAGE_ID, api_block_index=1,
        stop_reason="tool_use", input_tokens=INFLIGHT_INPUT,
        output_tokens=INFLIGHT_OUTPUT_TERMINAL,
        cache_creation_input_tokens=INFLIGHT_CACHE_CREATION,
        cache_read_input_tokens=INFLIGHT_CACHE_READ,
        timestamp="2026-01-01T21:40:06.200Z",
    )


@pytest.fixture
def inflight_transcript(tmp_path) -> dict:
    """A transcript whose only request group holds JUST apiBlockIndex=0 (an
    in-flight session) -- the terminal row is returned separately (as both a
    dict and pre-serialized JSONL text) so a test can append it and re-parse,
    exercising task 06's in-flight completeness rule."""
    path = tmp_path / "inflight_session.jsonl"
    path.write_text(json.dumps(_inflight_partial_row()) + "\n", encoding="utf-8")
    return {
        "path": path,
        "terminal_row": _inflight_terminal_row(),
        "terminal_row_json": json.dumps(_inflight_terminal_row()) + "\n",
    }


# ---------------------------------------------------------------------------
# 3. Seeded OTLP rows -- built on the CURRENT (not frozen-legacy) schema.
#
# THIS is the fixture that backs tests/golden/bill_otlp_baseline.txt. It must
# NOT be the frozen legacy-schema fixture above: once task 04 adds a
# usage_source branch, replaying a legacy-schema baseline would raise
# `OperationalError: no such column` instead of comparing bill.py's output.
# ---------------------------------------------------------------------------

# Fixed instant used for every seeded row: 2026-01-01T00:00:00Z. No wall-clock.
BASE_NANO = 1_767_225_600_000_000_000

SEEDED_SESSIONS = [
    dict(
        session_id="sess-otlp-001",
        repo="github.com/cyclotron/acme-web",
        repo_raw="git@github.com:Cyclotron/Acme-Web.git",
        user_email="alice@cyclotron.com", user_id="u-alice", org_id="org-cyclotron",
        model="claude-sonnet-5", query_source="main",
        cost_usd=10.0,
        tokens={"input": 100000, "output": 50000, "cacheRead": 200000, "cacheCreation": 30000},
        timeline_event=True,
    ),
    dict(
        session_id="sess-otlp-002",
        repo="github.com/cyclotron/globex-api",
        repo_raw="https://github.com/Cyclotron/Globex-Api.git",
        user_email="bob@cyclotron.com", user_id="u-bob", org_id="org-cyclotron",
        model="claude-opus-4-8", query_source="main",
        cost_usd=20.0,
        tokens={"input": 150000, "output": 80000, "cacheRead": 50000, "cacheCreation": 20000},
        timeline_event=False,
    ),
    dict(
        session_id="sess-otlp-003",
        repo="unknown", repo_raw="",
        user_email="", user_id="", org_id="",
        model="claude-haiku-4-5", query_source="main",
        cost_usd=5.0,
        tokens={"input": 5000, "output": 2000, "cacheRead": 1000, "cacheCreation": 500},
        timeline_event=False,
    ),
]


def seed_otlp_rows(store: OtelStore) -> None:
    """Seed deterministic OTLP-shaped token_usage/cost_usage/session_repo_timeline
    rows onto `store` (built on the CURRENT schema). Every id, timestamp, and
    amount is a fixed literal -- no wall-clock, no random ids -- so a bill.py
    run against this data is byte-identical across repeated captures. Used by
    attribution/billing tests and by the golden baseline capture script.
    """
    for i, s in enumerate(SEEDED_SESSIONS):
        nano = BASE_NANO + i * 1_000_000_000
        store.insert_cost_datapoint(
            session_id=s["session_id"], repo=s["repo"], repo_raw=s["repo_raw"],
            user_email=s["user_email"], user_id=s["user_id"], org_id=s["org_id"],
            model=s["model"], query_source=s["query_source"], cost_usd=s["cost_usd"],
            time_unix_nano=nano,
        )
        for token_type, tokens in s["tokens"].items():
            store.insert_datapoint(
                session_id=s["session_id"], repo=s["repo"], repo_raw=s["repo_raw"],
                user_email=s["user_email"], user_id=s["user_id"], org_id=s["org_id"],
                model=s["model"], token_type=token_type, query_source=s["query_source"],
                tokens=tokens, time_unix_nano=nano,
            )
        if s["timeline_event"]:
            store.insert_session_repo(
                session_id=s["session_id"], ts="2026-01-01T00:00:00Z", seq=0,
                repo=s["repo"], repo_raw=s["repo_raw"], cwd="/home/dev/acme-web",
                event="SessionStart",
            )
    store.commit()


@pytest.fixture
def seeded_otlp_db_path(tmp_path) -> str:
    """A database file, built on the CURRENT schema, seeded with
    `seed_otlp_rows`. This is the fixture that backs the golden `bill.py`
    baseline -- see the module note above for why it must not be the frozen
    legacy-schema fixture."""
    path = str(tmp_path / "seeded_otlp.db")
    store = OtelStore(path)
    seed_otlp_rows(store)
    store.close()
    return path
