"""Resolve which repo a usage datapoint should bill to.

The wrapper stamps `repo=` once, at session launch, into OTEL_RESOURCE_ATTRIBUTES.
OTEL resource attributes are immutable for the process lifetime, so that tag is
frozen for the whole session — a developer who starts in one client's repo and
`cd`s into another's mid-session has ALL of it billed to the first.

The fix is a second signal. A `CwdChanged` hook (see deploy/claude-repo-tag.py)
records `(session_id, ts, repo)` every time the working directory changes, and
this module joins that timeline back onto the usage datapoints:

    for each datapoint, the repo is the timeline entry with the greatest
    ts <= datapoint.ts, for the same session_id            ("as-of" join)

Why this works on the data we already store:
  - every datapoint carries `session_id` and `ts` (the OTLP `timeUnixNano`,
    not receipt time) -> both join keys already exist
  - Claude Code metrics use DELTA temporality, so each datapoint is the
    increment for its own interval -> attributing an increment to whichever
    repo was active then is arithmetically sound
  - `repo` is NOT part of `dp_key`, so resolution is a derived label:
    re-running it never breaks dedupe, and a corrected/late-arriving timeline
    retroactively fixes past bills with no re-ingest

Resolution is therefore done at QUERY time, not ingest time. The stored
`repo`/`repo_raw` columns keep the wrapper's original value untouched.

Fallback chain, most to least trustworthy:

    timeline        the hook told us where the session was at that moment
                    (including an `unknown` effective row that INHERITED a
                    real repo -- see "Ancestor inheritance" below)
    desktop-scratch  a desktop (transcript-sourced) session that has NO
                     billable repo -- the session's own timeline entries
                     (if any) all carry repo='unknown', so there is nothing
                     for the timeline branch to bill to. Distinguished from
                     `no_remote`/`absent` because it is diagnostic of the
                     desktop surface specifically, not the OTLP wrapper path.
    wrapper         no timeline for this session; use the launch-time repo= tag
    no_remote       wrapper ran but the directory had no git remote (unbillable)
    absent          no repo attribute arrived at all — the session never
                     passed through the wrapper (non-CLI surface, or a
                     bypassed install)

`no_remote`, `absent`, and `desktop-scratch` all normalize to the 'unknown'
repo but mean very different things operationally, so they're reported
separately.

Ancestor inheritance (query time only, nothing persisted)
---------------------------------------------------------
When the effective timeline row (as-of, else the session's first) is
repo='unknown', the datapoint inherits a real repo ONLY IF that row's cwd is a
project-level folder that is the SAME as, or an ANCESTOR of, the cwd of
qualifying real-repo rows in the same session, and those rows name exactly ONE
repo. Example: a session starts in `C:/dev/wealthspire` (no remote, holds
sub-repos) then `cd`s into `C:/dev/wealthspire/src/Ticketing.Frontend` (real
repo R): usage before the `cd` bills to R.

  - Direction is ancestor-only: a real row ABOVE the unknown folder never
    qualifies (an unknown child of a real repo stays unknown).
  - Any qualifying row counts, before OR after the datapoint. Zero distinct
    repos, or two or more, -> stays 'unknown' (strict: never a likely guess).
  - Rows with event='DirectoryAdded' never serve as the real-repo anchor.
  - The literal session_id 'unknown' (receiver placeholder, may pool unrelated
    users) never inherits.
  - The unknown folder must be project-level. Blocked anchors: empty/roots
    (drive, '/', '~', mount roots, Git-Bash drive, UNC host/share), home
    folders, top-level folders under a root, and generic containers
    (`_CONTAINER_NAMES`, onedrive*, visual studio *).
  - Paths are compared lower-cased and separator-normalised, by equality /
    `substr` only (never as LIKE/GLOB patterns). SQLite `lower()` is ASCII-only,
    so non-ASCII case differences under-inherit (conservative).
  - A non-unknown effective row keeps its own repo; no timeline row at all
    falls to the wrapper tag, exactly as before.
  - Retroactive by design: a late or corrected timeline changes past results.
"""

from __future__ import annotations

TIMELINE_TABLE = "session_repo_timeline"

# Generic container / outer-folder names (compared lower-cased against the LAST
# path segment). The first fourteen mirror project_label.CONTAINER_DIRS /
# _OUTER_NAMES; `work, clients, temp, tmp, appdata` are added strictness.
# `onedrive*` and `visual studio *` are prefix rules, rendered separately.
_CONTAINER_NAMES = (
    "code", "src", "source", "repos", "projects", "dev", "git", "github",
    "workspace", "desktop", "documents", "downloads", "library", "cloudstorage",
    "work", "clients", "temp", "tmp", "appdata",
)
# Bare parents of home folders ('.../users', '.../home').
_HOME_PARENTS = ("users", "home")
# Mount roots: '<prefix><one segment>' is a root anchor.
_MOUNT_PREFIXES = ("/mnt/", "/media/", "/volumes/")

# Repo active at the datapoint's own timestamp. {col} is the selected column
# (repo for the NULL-ness tests in attribution_source, rowid for resolution).
# {ar} is the correlated inner alias; `_fmt` derives it from a sanitised form
# of the caller's alias (`_<alias>__ar`) so it can never equal the caller's
# alias, whatever that looks like (bare, quoted, bracketed, backticked).
# `repo DESC` / `repo ASC` are the deterministic final tie-breaks: the primary
# key is (session_id, ts, seq, repo), so the order is total, and ordering by the
# key's tail lets SQLite read the answer straight off the PK index (no sort).
_AS_OF = """(SELECT {ar}.{col} FROM {tl} {ar}
              WHERE {ar}.session_id = {a}.session_id AND {ar}.ts <= {a}.ts
              ORDER BY {ar}.ts DESC, {ar}.seq DESC, {ar}.repo DESC LIMIT 1)"""

# The session's earliest known row. Covers a datapoint whose ts slightly
# precedes the first hook event (export-interval rounding, small clock skew):
# the session must have started somewhere, and the timeline is a better source
# than the frozen launch tag.
_FIRST = """(SELECT {ar}.{col} FROM {tl} {ar}
              WHERE {ar}.session_id = {a}.session_id
              ORDER BY {ar}.ts ASC, {ar}.seq ASC, {ar}.repo ASC LIMIT 1)"""


def _fmt(alias: str) -> dict:
    """Template fields for `_AS_OF` / `_FIRST` given the caller's row alias.

    The caller's alias is used verbatim wherever the caller's row is
    referenced (`{a}`), so quoted, bracketed or backticked aliases work as
    they always did. The two aliases the generated SQL introduces in the
    caller's scope (`ar` correlated lookup, `i` joined `_inherit_table()`) are
    derived from a SANITISED bare form of it: `_` + the alias with every
    character outside `[0-9A-Za-z_]` replaced by `_` (never dropped), plus a
    distinct suffix (`__ar` / `__i`). Each is therefore always a valid
    unquoted identifier, and each is strictly LONGER than the name SQLite
    reads from the caller's alias (quotes stripped), so neither can equal it
    (SQLite compares identifiers case-insensitively, but never two names of
    different length); and `ar` differs from `i` in its suffix.
    """
    base = "_" + "".join(c if (c.isascii() and c.isalnum()) or c == "_"
                         else "_" for c in alias)
    return {"tl": TIMELINE_TABLE, "a": alias, "ar": base + "__ar",
            "i": base + "__i"}


def _norm(col: str) -> str:
    """SQL: normalised path N(c): backslashes to '/', trimmed, trailing '/'
    removed, lower-cased (ASCII only).

    The backslash literal must reach SQLite as a single-character literal
    (hence the raw string below), otherwise separator handling is silently
    disabled.
    """
    return r"lower(rtrim(trim(replace(ifnull(" + col + r", ''), '\', '/')), '/'))"


def _blocked(n: str, p: str, last: str, k: str) -> str:
    """SQL boolean: normalised path `n` is NOT a project-level folder.

    `p` is n up to and including its last '/', `last` its final segment and
    `k` the number of '/' characters in n (all precomputed once per row).
    Only equality, substr, IN and GLOB with FIXED literal patterns are used;
    path text is never a pattern. `GLOB '*'` matches '/', hence the `k` tests.
    """
    names = ", ".join(f"'{x}'" for x in _CONTAINER_NAMES + _HOME_PARENTS)
    parts = [
        f"{n} = ''",                                  # empty
        f"{n} = '~'",                                 # home shorthand
        f"{n} = '/root'",                             # root's home
        f"{n} GLOB '[a-z]:'",                         # drive root
        f"({n} GLOB '[a-z]:/*' AND {k} = 1)",         # x:/seg
        f"({n} GLOB '/*' AND {k} = 1)",               # /seg, /c
        f"({n} GLOB '/[a-z]/*' AND {k} = 2)",         # /c/seg
    ]
    for pre in _MOUNT_PREFIXES:                       # root or top-level
        parts.append(f"({n} GLOB '{pre}*' AND {k} <= 3)")
    # UNC: //host, //host/share, //host/share/seg (4 slashes at most)
    parts.append(f"({n} GLOB '//*' AND {k} <= 4)")
    parts.append(f"substr({p}, -7) = '/users/'")      # home folder
    parts.append(f"substr({p}, -6) = '/home/'")
    parts.append(f"{last} IN ({names})")              # generic container
    parts.append(f"{last} GLOB 'onedrive*'")
    parts.append(f"{last} GLOB 'visual studio *'")
    return "(" + " OR ".join(parts) + ")"


def _inherit_table(name: str) -> str:
    """SQL derived table `<name>(rid, v)`: every timeline row (by rowid) mapped
    to the repo it resolves to -- its own repo, or the inherited one. `name`
    is the join alias (`_fmt(alias)['i']`, i.e. `_<sanitised alias>__i`),
    derived from the caller's alias so `{alias}.*` never expands over this
    table's columns.

    It does not reference the datapoint, so SQLite builds it as a co-routine
    once per use and probes it through an automatic index on `rid`: the
    inheritance work is paid once per timeline row, never once per datapoint
    (`LIMIT -1` keeps SQLite from flattening it into the lookup). A row's own
    repo and its inherited value are always derived from the SAME row (rid).
    """
    blocked = _blocked("_m.n", "_m.p", "_m.l", "_m.k")
    return f"""(
    SELECT _r.rowid AS rid, _r.repo AS v FROM {TIMELINE_TABLE} _r
    WHERE _r.repo IS NOT 'unknown'
    UNION ALL
    SELECT _m.rid AS rid,
      CASE WHEN _m.sid IS NULL OR _m.sid = 'unknown' OR {blocked} THEN 'unknown'
           ELSE ifnull((
             SELECT CASE WHEN count(*) > 0 AND min(_x.repo) = max(_x.repo)
                         THEN min(_x.repo) END
             FROM (SELECT _rx.session_id AS sid, _rx.repo AS repo,
                          {_norm('_rx.cwd')} AS n
                   FROM {TIMELINE_TABLE} _rx
                   WHERE _rx.repo <> 'unknown'
                     AND ifnull(_rx.event, '') <> 'DirectoryAdded'
                   GROUP BY 1, 2, 3) _x
             WHERE _x.sid = _m.sid AND _x.n <> '' AND _m.n <> ''
               AND (_x.n = _m.n
                    OR substr(_x.n, 1, length(_m.n) + 1) = _m.n || '/')
           ), 'unknown') END AS v
    FROM (SELECT _q.rid AS rid, _q.sid AS sid, _q.n AS n,
                 _q.p AS p, substr(_q.n, length(_q.p) + 1) AS l,
                 length(_q.n) - length(replace(_q.n, '/', '')) AS k
          FROM (SELECT _w.rid AS rid, _w.sid AS sid,
                       _w.n AS n,
                       rtrim(_w.n, replace(_w.n, '/', '')) AS p
                FROM (SELECT _ru.rowid AS rid, _ru.session_id AS sid,
                             {_norm('_ru.cwd')} AS n
                      FROM {TIMELINE_TABLE} _ru
                      WHERE _ru.repo = 'unknown'
                      LIMIT -1) _w
                LIMIT -1) _q
          LIMIT -1) _m
    LIMIT -1
  ) {name}"""


def resolved_repo(alias: str = "t") -> str:
    """SQL expression: the repo this row bills to.

    The effective timeline row `u` is the as-of row (latest ts <= datapoint ts),
    else the session's first row; repo and cwd are both read from that ONE row
    (selected by rowid, with deterministic tie-breaks: repo DESC for as-of,
    repo ASC for first, after ts and seq -- the PK tail, so the order is total).

      - no timeline row            -> the wrapper's launch tag ({alias}.repo)
      - u.repo <> 'unknown'        -> u.repo, exactly as before (no inheritance)
      - u.repo = 'unknown'         -> the inherited repo, else 'unknown'

    Inherited repo: the single distinct repo among OTHER rows of the same
    session with repo <> 'unknown', event <> 'DirectoryAdded', whose cwd is the
    same as or BELOW u.cwd (ancestor-only: a real row above u never counts),
    provided u.cwd is a project-level folder (not a root, home, top-level
    folder or generic container; see `_blocked`) and the session_id is not
    the placeholder 'unknown'. Zero or 2+ distinct repos -> 'unknown'. Paths
    are lower-cased (ASCII-only `lower()`), separator-normalised, and compared
    by equality/substr only. Pure query-time SQL; nothing is persisted.

    The `_fmt(alias)['i']` lookup on the effective row is NULL only when there is no
    timeline row, or the effective row's repo is NULL; then fall back to the
    session's first row's RAW repo, then the wrapper tag, exactly like the
    original COALESCE chain and `resolved_view`.

    This standalone expression builds its own `_inherit_table()` per use; a statement
    that needs both columns should use `resolved_view`, which shares one.
    """
    f = _fmt(alias)
    eff = (f"COALESCE({_AS_OF.format(col='rowid', **f)}, "
           f"{_FIRST.format(col='rowid', **f)})")
    i = f["i"]
    return (f"COALESCE((SELECT {i}.v FROM {_inherit_table(i)} WHERE {i}.rid = {eff}), "
            f"{_FIRST.format(col='repo', **f)}, "
            f"{alias}.repo)")


def attribution_source(alias: str = "t") -> str:
    """SQL expression: which signal produced the repo (see module docstring).

    `desktop-scratch` is checked FIRST, ahead of `timeline`: a desktop
    (transcript-sourced) session that never left a scratch directory still
    gets a timeline row (claude-repo-tag.py fires on SessionStart), but that
    row carries repo='unknown' -- so `resolved_repo()` also comes back
    'unknown' for it. If the timeline branch below were allowed to claim the
    row first (it matches on ANY timeline row, billable or not), a scratch
    session would misreport as 'timeline' despite billing nowhere. Keying on
    `usage_source = 'transcript'` (present on BOTH token_usage and
    cost_usage) rather than `entrypoint` (token_usage only) keeps this branch
    safe to prepare against cost_usage too.
    """
    f = _fmt(alias)
    return (
        f"CASE WHEN {alias}.usage_source = 'transcript' "
        f"       AND {resolved_repo(alias)} = 'unknown' THEN 'desktop-scratch' "
        f"     WHEN {_AS_OF.format(col='repo', **f)} IS NOT NULL "
        f"       OR {_FIRST.format(col='repo', **f)} IS NOT NULL THEN 'timeline' "
        f"     WHEN {alias}.repo_raw = '' THEN 'absent' "
        f"     WHEN {alias}.repo = 'unknown' THEN 'no_remote' "
        f"     ELSE 'wrapper' END"
    )


def resolved_view(table: str, alias: str = "t") -> str:
    """A SELECT over token_usage / cost_usage with two columns added:

        resolved_repo       the repo to bill (use this instead of `repo`)
        attribution_source  timeline | desktop-scratch | wrapper | no_remote | absent

    The original `repo` / `repo_raw` columns are preserved so the wrapper's
    launch-time tag stays available for reconciliation.

    Same results as `resolved_repo(alias)` / `attribution_source(alias)`, but
    built with ONE join: the effective timeline row's rowid is found once per
    datapoint and probed once in a single shared `_inherit_table()`, so a
    consumer that references `resolved_repo` several times (GROUP BY, CASE,
    SELECT list) does not repeat the lookup or rebuild the table.
    """
    f = _fmt(alias)
    eff = (f"COALESCE({_AS_OF.format(col='rowid', **f)}, "
           f"{_FIRST.format(col='rowid', **f)})")
    # `{i}.v` is NULL only when there is no timeline row, or the
    # effective row's repo is NULL; then fall back to the session's first row,
    # then the wrapper tag, exactly like the original COALESCE chain.
    i = f["i"]
    tl_repo = f"COALESCE({i}.v, {_FIRST.format(col='repo', **f)})"
    rr = f"COALESCE({i}.v, {_FIRST.format(col='repo', **f)}, {alias}.repo)"
    return (
        f"SELECT {alias}.*, {rr} AS resolved_repo, "
        f"CASE WHEN {alias}.usage_source = 'transcript' "
        f"       AND {rr} = 'unknown' THEN 'desktop-scratch' "
        f"     WHEN {tl_repo} IS NOT NULL THEN 'timeline' "
        f"     WHEN {alias}.repo_raw = '' THEN 'absent' "
        f"     WHEN {alias}.repo = 'unknown' THEN 'no_remote' "
        f"     ELSE 'wrapper' END AS attribution_source "
        f"FROM {table} {alias} "
        f"LEFT JOIN {_inherit_table(i)} ON {i}.rid = {eff}"
    )
