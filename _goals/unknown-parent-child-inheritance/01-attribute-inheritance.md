# Task 01: Ancestor-of-real-repo inheritance in resolved_repo (pure SQL)

## Objective

`billing/otel/attribute.py` resolves a datapoint whose effective timeline row is
`'unknown'` to a real repo when, and only when, that row's cwd is a project-level folder
that is the same as, or an ANCESTOR of, the cwd of qualifying real-repo rows in the same
session that all name ONE repo. All public signatures and every consumer are unchanged.

## Dependencies

- none

```yaml
# --- task ownership contract ---
writes:
  - billing/otel/attribute.py
reads:
  - billing/otel/otel_store.py        # session_repo_timeline schema + ix_timeline_session; not edited
  - tests/test_attribute.py           # existing behavior that must keep passing; not edited
  - billing/otel/project_label.py     # imports TIMELINE_TABLE; its CONTAINER_DIRS/_OUTER_NAMES define the container vocabulary; not edited
depends_on: []
owner: implementer
rewrite_semantics: whole-file
eval_depth: full
# full: attribute.py's resolved_repo/attribution_source/resolved_view are consumed by
# bill.py, invoice.py, reconcile.py, export.py, project_label.py and
# deploy/unknown-report.py; task 02 tests it but testing does not lower the depth.
```

## Requirements (exhaustive — the evaluator verifies every item)

Notation: `u` = the effective timeline row; `x` = another row of the SAME session;
`N(c)` = normalised path.

- [ ] **Effective row (unchanged selection).** The datapoint's effective row is the as-of
      row (`ts <= datapoint.ts`, latest) else the session's first row, else none. Both
      selections get a deterministic final tie-break (`rowid DESC` for as-of, `rowid ASC`
      for first) so ties are never arbitrary. `u.repo` and `u.cwd` MUST come from the SAME
      row (select the row once, e.g. by rowid, and read both columns from it); two
      independent ORDER BY subqueries are not allowed for the pair.
- [ ] **Behavior preserved.** Today's result is `COALESCE(as_of_repo, first_repo, {alias}.repo)`.
      This is PRESERVED exactly when `u.repo <> 'unknown'` (the row's own repo, no inheritance
      logic applied, even if related rows name other repos) and when no timeline row exists
      (falls to `{alias}.repo`, the wrapper tag).
- [ ] **Inheritance only for an unknown effective row.** When `u` exists and `u.repo =
      'unknown'` the result is the inherited repo if one exists, else `'unknown'` (NOT the
      wrapper tag, as today).
- [ ] **Inherited repo** = the single distinct `x.repo` among rows `x` of the SAME session
      with `x.repo <> 'unknown'`, `ifnull(x.event,'') <> 'DirectoryAdded'`, and
      `Descends(x, u)` (below). Zero distinct repos, or two or more -> no inheritance
      (`'unknown'`). Any qualifying row counts, before OR after the datapoint ts.
- [ ] **session_id guard.** If the datapoint's `session_id = 'unknown'` (the receiver's
      placeholder), no inheritance: the result is `'unknown'` when `u` is unknown.
- [ ] **Normalisation** `N(c) = lower(rtrim(trim(replace(ifnull(c,''), '\', '/')), '/'))`.
      In the Python source the backslash literal MUST survive into the SQL as the
      single-backslash literal `'\'`: write it as a raw string (`r"replace(c, '\', '/')"`) or
      as `'\\'` inside a normal Python string. `'\\\\'` in a normal string yields TWO backslashes
      in the SQL and silently disables separator handling (so does a bare `'\'` in a normal
      string, which becomes an empty literal). Verify with a test.
- [ ] **Descends(x, u)** is exactly:
      `nonempty(N(u)) AND nonempty(N(x)) AND (N(x) = N(u) OR substr(N(x), 1, length(N(u)) + 1)
      = N(u) || '/')`. The outer parentheses are REQUIRED (an empty `N(u)` must never descend
      to every absolute path).
      Direction is fixed: the real row `x` is the same as or BELOW the unknown row `u`. A real
      row that is an ANCESTOR of `u` NEVER qualifies. Comparison is by equality / `substr`
      only: path text is never used as a `LIKE`/`GLOB` PATTERN (paths contain `%`, `_`,
      `[`). `C:\dev\wealth` is NOT an ancestor of `C:\dev\wealthspire\x`.
- [ ] **Anchor blocklist (the unknown folder `u` must be project-level).** `u` is BLOCKED
      (no inheritance) when `N(u)` is any of:
      1. empty, or a root anchor: a drive root (`x:`), `/`, `~`, ANY mount root
         `/mnt/<anything>`, `/media/<anything>`, `/volumes/<anything>` (exactly one segment
         after the mount prefix), a Git-Bash drive root `/<letter>`, or a UNC host or share
         root (`//host` or `//host/share`: one or two segments after the leading `//`);
      2. a home folder: ends in `/users/<name>` or `/home/<name>`, or equals `/root`
         (and the bare parents `…/users`, `…/home`);
      3. a top-level folder directly under a root anchor (`x:/seg`, `/seg`,
         `/mnt/<x>/seg`, `/media/<x>/seg`, `/volumes/<x>/seg`, `/<letter>/seg`,
         `//host/share/seg`), e.g. `C:\Cyclotron`;
      4. a generic container whose LAST segment (lowercased) is one of
         `code, src, source, repos, projects, dev, git, github, workspace, desktop,
         documents, downloads, library, cloudstorage, work, clients, temp, tmp, appdata`,
         or starts with `onedrive` or `visual studio `.
      The first fourteen names mirror `project_label.CONTAINER_DIRS` / `_OUTER_NAMES`; the
      last five (`work, clients, temp, tmp, appdata`) are added strictness. Define the
      vocabulary ONCE as a module constant in `attribute.py` and render it into the SQL.
      Allowed building blocks: `length`/`substr`/`instr`/`replace`/`rtrim`/`trim`/`lower`/
      `ifnull`/equality/`IN (...)` with fixed names, and `GLOB`/`LIKE` ONLY with a fixed
      literal PATTERN (never path text as the pattern). Extracting the last segment of a path
      of any depth may use the `rtrim(n, replace(n, '/', ''))` idiom. NOTE: `GLOB` `*` matches
      `/`, so a pattern such as `'//[^/]*/[^/]*'` also matches deeper paths; the BLOCKED/ALLOWED
      example tables below are the arbiter.
      Required examples. BLOCKED: `C:\`, `/`, `~`, `/mnt/c`, `/mnt/data`, `/media/x`,
      `/volumes/disk`, `/c`, `\\srv`, `\\srv\share`, `\\srv\share\team`, `C:\Users\x`,
      `/home/x`, `/root`, `C:\dev`, `C:\Cyclotron`, `C:\Users\x\clients`, `C:\Users\x\Work`,
      `C:\Users\x\AppData\Local\Temp`, `/home/x/projects`,
      `C:\Users\x\OneDrive - Cyclotron Inc`, `C:\Users\x\OneDrive - Cyclotron Inc\Desktop`.
      ALLOWED: `C:\dev\wealthspire`, `C:\Users\x\OneDrive - Cyclotron Inc\Code\Dashnoard`,
      `C:\Users\x\proj`, `/home/x/proj`, `/srv/app/x`.
- [ ] **NULL safety.** NULL cwd/event/repo never raise and never cause an unintended
      inheritance (an exclusion-style CASE must not let NULL fall through to "inherit").
- [ ] **attribution_source** keeps its exact CASE order and semantics. `desktop-scratch`
      remains FIRST and keys off `resolved_repo(alias) = 'unknown'`; an inherited row has a
      timeline row so it reports `timeline`. The `timeline` branch condition
      (`AS_OF IS NOT NULL OR FIRST IS NOT NULL`) is unchanged.
- [ ] **Interface frozen:** `TIMELINE_TABLE`, `resolved_repo(alias="t")`,
      `attribution_source(alias="t")`, `resolved_view(table, alias="t")` keep names,
      parameters and return types (SQL string); the view's added columns are unchanged
      (`resolved_repo`, `attribution_source`). No new tables/columns/indexes; nothing persisted.
- [ ] **Alias safety:** works for any `alias`; inner subquery aliases must not collide with
      it; compiles when embedded in `WITH r AS (...)` (bill/invoice/export) and as a
      subquery (reconcile).
- [ ] **Stdlib only; no new imports** beyond what the file has.
- [ ] **Docstrings/comments:** update the module docstring's fallback-chain description and
      `resolved_repo`'s docstring: the ancestor-only rule, the anchor blocklist, the
      same-folder rule, the DirectoryAdded and session-id exclusions, ASCII-only `lower()`,
      and that it is query-time only. (README is updated by Phase 6; do not edit it.)
- [ ] **Performance gate.** Build a throwaway synthetic store in the scratchpad dir (NOT in
      the repo): >= 100,000 `token_usage` rows, >= 2,000 sessions, ~20 timeline rows per
      session, >= 30% of datapoints with an unknown effective row, PLUS one heavy-tail
      session (>= 300 timeline rows and >= 20,000 datapoints). Time a full scan of
      `resolved_view('token_usage')` (e.g. `SELECT resolved_repo, count(*) ... GROUP BY 1`)
      against a copy of the ORIGINAL `attribute.py` and the new one, each as the MEDIAN of 3
      runs on the same warm DB file. Report all timings. If new > 3 x original, STOP and
      report (do not ship a slower design silently).

## Acceptance Criteria

1. Nate: timeline rows (`C:\dev\wealthspire`, unknown, t1) then
   (`C:\dev\wealthspire\src\Ticketing.Frontend`, real repo R, t2); a datapoint whose effective
   row is the t1 row resolves to R, source `timeline` — verification: ad-hoc SQL via `OtelStore` in a temp DB (command output).
2. Reverse: real parent row, later unknown CHILD row; datapoint on the unknown row stays `unknown` — verification: command output.
3. Derek: `C:\u\OneDrive - Cyclotron Inc\Code\Dashnoard` (unknown) vs `C:\u\OneDrive - Cyclotron Inc\Code\src\orbit-local`-style unrelated real row stays `unknown` — verification: command output.
4. Two different qualifying real repos -> `unknown`; zero real rows -> `unknown`; a real row in another session never leaks — verification: command output.
5. Non-unknown effective row preserved: real row M at `C:\mono`, real row S (different repo) at `C:\mono\sub`; datapoint with effective row M still resolves to M (and effective row S to S). Real effective row with a related unknown row keeps its repo — verification: command output.
6. Prefix lookalike `C:\dev\wealth` (unknown) with a real row at `C:\dev\wealthspire\x` stays `unknown` — verification: command output.
7. Every BLOCKED and ALLOWED example in the anchor blocklist requirement behaves as listed (a mount root, a UNC host and a `\\srv\share\team` path included) (blocked anchors stay `unknown` even with a real descendant; allowed ones inherit) — verification: command output (table of path -> result).
8. `DirectoryAdded`-only real anchor does not inherit; session_id `'unknown'` never inherits; empty and NULL-cwd unknown rows never inherit — verification: command output (NULL cwd seeded with a raw `INSERT`).
9. Alias safety: `resolved_view('token_usage', alias='x')` inside `WITH r AS (...)` returns the same rows as the default alias on a seeded store — verification: command output.
10. Existing suites green: `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_invoice.py tests/test_reconcile.py tests/test_export.py tests/test_export_unattributed.py tests/test_integration_desktop.py -q` — verification: command output (rung 2).
11. Performance report with the three-run medians and ratio <= 3.0 — verification: command output.
12. Baseline-relative tree check: `git status --short` lists `M billing/otel/attribute.py` and the goal directory `?? _goals/unknown-parent-child-inheritance/` (pre-existing, untracked) and NOTHING else - no stray scratch, baseline-copy or benchmark files in the repo; record `git hash-object billing/otel/attribute.py` in the report as the hand-off hash for task 02 — verification: command output.

## Files to Read

- `README.md` — "attribute.py" bullet and fallback chain; the path-prefix notes around lines 380-410 (do not edit)
- `billing/otel/attribute.py` — current implementation
- `billing/otel/otel_store.py` — `session_repo_timeline` schema, `insert_session_repo`, `insert_datapoint`, `insert_cost_datapoint`
- `billing/otel/project_label.py` — container / outer vocabulary to mirror (do not import it)
- `tests/test_attribute.py` — existing contracts (a real launch that cd's into scratch stays unknown / `desktop-scratch`; a scratch launch that cd's into a real repo resolves to the real repo)
- `.claude/skills/test-ladder/SKILL.md`, `.claude/skills/python-performance-optimization/SKILL.md`

## Files to Create / Change

- `billing/otel/attribute.py` — implement the rule; update docstrings.

## Constraints

- Must: stdlib only; query-time only; valid SQL for any `alias`; no Python-side state.
- Must: preserve today's behavior exactly where the effective row is non-unknown or absent.
- Must NOT: edit tests, README, deploy/, client-package/, export.py or any consumer; add a
  table/column/index; register SQLite functions; use path text as a `LIKE`/`GLOB` pattern
  (a `GLOB`/`LIKE` whose PATTERN is a fixed literal, e.g. `GLOB '[a-z]:'`, is allowed);
  touch the VM.
- If an existing test fails because it encodes the OLD behavior, do not edit it: report the
  test id and why, so the orchestrator can amend the write fence.

## Verification

- Targeted: `python -m pytest tests/test_attribute.py -q`
- Impacted (rung 2): the command in criterion 10.
- Attach the ad-hoc SQL evidence for criteria 1-9 and the timings for criterion 11 in the report.
