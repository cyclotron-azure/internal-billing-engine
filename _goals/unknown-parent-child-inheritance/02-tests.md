# Task 02: Tests for ancestor-of-real-repo inheritance

## Objective

`tests/test_attribute_inheritance.py` exists and pins the inheritance rule from task 01
with outcome-verifying tests against a real temp SQLite store (no mocks of the SQL).

## Dependencies

- Task 01 (inheritance in `attribute.py`)

```yaml
# --- task ownership contract ---
writes:
  - tests/test_attribute_inheritance.py
  - billing/otel/attribute.py   # TEMPORARY exception for the mutation check only (criterion 2): every edit MUST be reverted; the final tree has no change to this path
reads:
  - billing/otel/attribute.py        # resolved_repo / attribution_source / resolved_view
  - billing/otel/otel_store.py       # insert_session_repo / insert_datapoint / insert_cost_datapoint
  - tests/test_attribute.py          # helper/fixture patterns (_fetch_repos/_fetch_sources, DESKTOP_NANO); not edited
  - tests/conftest.py                # tmp_db_path fixture; not edited
depends_on:
  - "01-attribute-inheritance"
owner: test-writer
rewrite_semantics: whole-file
eval_depth: light
```

## Requirements (exhaustive — the evaluator verifies every item)

Each test seeds a temp `OtelStore` (use `tmp_db_path`), inserts timeline rows via
`insert_session_repo`, datapoints via `insert_datapoint` AND `insert_cost_datapoint`, then
reads `resolved_repo` + `attribution_source` through `resolved_view`. Datapoint timestamps
use `time_unix_nano` consistent with timeline `ts` strings (see `tests/test_attribute.py`).
Use a small helper to build the cases; use raw-string or properly escaped Windows paths (a
bare `'\'` / `'\d'` in a normal Python string is a bug in the TEST).

- [ ] **Nate:** unknown `C:\dev\wealthspire` row first, real `C:\dev\wealthspire\src\Ticketing.Frontend`
      row later; a datapoint whose effective row is the unknown row -> real repo, source
      `timeline`; a datapoint after the child row -> real repo (its own row).
- [ ] **Forward-only:** datapoint whose ts precedes the first timeline row (effective row is
      the FIRST row, unknown) with a qualifying real row later -> real repo.
- [ ] **Reverse stays unknown:** real parent row `C:\dev\repoR`, later unknown CHILD row
      `C:\dev\repoR\tools\gen` (a child path that is NOT itself blocked and not a container
      name, so the only reason for `unknown` is the direction rule) -> `unknown`.
- [ ] **Derek:** unknown `...\Code\Dashnoard` and real `...\Code\src\orbit-local`-style
      unrelated row -> `unknown`.
- [ ] **Distinct repos:** two qualifying real rows (different repos) -> `unknown`; two
      qualifying rows with the SAME repo -> that repo.
- [ ] **Scope of session:** only-unknown session -> `unknown`; a real row in ANOTHER session
      never leaks.
- [ ] **Preservation (named tests):** (a) real row M at `C:\dev\mono` (a project-level,
      NON-blocked path, so the test exercises the distinct-repo / unknown-only logic and not the
      blocklist), real row S (other repo) at `C:\dev\mono\sub`: datapoint with effective row M
      resolves to M, effective row S to S;
      (b) a real effective row with a related unknown row keeps its repo; (c) no timeline rows
      + stored real repo -> `wrapper`, and an unknown effective row never falls back to the
      wrapper tag even when the stored repo is real.
- [ ] **Normalisation:** case-insensitive (`C:\DEV\WealthSpire` vs `c:\dev\wealthspire\SRC`),
      separator mix (`C:\dev\x` vs `C:/dev/x/sub`), trailing separators.
- [ ] **Prefix lookalike:** unknown `C:\dev\wealth` vs real `C:\dev\wealthspire\x` -> `unknown`.
- [ ] **Wildcards inert:** paths containing `%`, `_`, `[` (e.g. unknown `C:\proj\a_b` vs real
      `C:\proj\axb\c`; unknown `C:\proj\a%` vs real `C:\proj\abc\c`) -> `unknown`.
- [ ] **Same folder:** unknown row and real row with identical cwd (project-level path) -> real repo.
- [ ] **Anchor blocklist, one named test per class**, each with a real descendant row so the
      only reason for `unknown` is the block: drive root `C:\`; `/`; `~`; mount roots `/mnt/c`,
      `/mnt/data`, `/media/x`, `/volumes/disk`; Git-Bash `/c`; UNC `\\srv` and `\\srv\share`;
      home `C:\Users\x` and `/home/x` and `/root`; top-level `C:\Cyclotron` and
      `\\srv\share\team`; containers `C:\dev`, `/home/x/projects`, `C:\Users\x\clients`,
      `C:\Users\x\Work`, `C:\Users\x\AppData\Local\Temp`, OneDrive root, OneDrive `Desktop`.
      Plus the ALLOWED set: `C:\dev\wealthspire`, OneDrive `...\Code\Dashnoard` with a real
      descendant, `C:\Users\x\proj`, `/home/x/proj`, `/srv/app/x` -> inherit.
- [ ] **Empty / NULL cwd:** empty-string cwd unknown row stays `unknown`; the NULL-cwd case is
      seeded with a RAW `INSERT` into `session_repo_timeline` (the store helper coerces None to
      `''`), and also stays `unknown` (with a qualifying real row present in the session).
- [ ] **DirectoryAdded:** a real row whose event is `DirectoryAdded` does NOT anchor
      inheritance; the same row with event `CwdChanged` does.
- [ ] **session_id 'unknown':** a session whose id is the literal `'unknown'` does not inherit.
- [ ] **desktop-scratch still wins:** a `usage_source='transcript'` session whose unknown rows
      have no qualifying real row -> `attribution_source == 'desktop-scratch'`; a transcript
      session that DOES inherit -> `timeline`.
- [ ] **Both tables:** the Nate, Derek and Preservation(a) cases are asserted on `cost_usage` too.
- [ ] **Alias:** `resolved_view('token_usage', alias='x')` yields the same resolved repos as
      the default alias on the Nate fixture.
- [ ] **Consumer smoke:** `export.build` (or `bill.py`'s aggregation) places the Nate
      session's tokens/cost under the real repo, not `unknown` (one end-to-end test).
- [ ] Deterministic: no network, no real time, nothing outside `tmp_path`.

## Acceptance Criteria

1. All listed cases exist as separately named tests and pass — verification: `python -m pytest tests/test_attribute_inheritance.py -v` output.
2. Mutation check (record in the task report; each mutant must turn at least one NAMED test red — name the test; every mutant MUST be reverted). FIRST record `git hash-object billing/otel/attribute.py` as H0 (it must equal the hand-off hash reported by task 01). Mutants: (a) **widen** — drop both the `+ 1` and the `|| '/'` in the descendant comparison -> prefix-lookalike test fails; (b) **direction** — also accept real rows that are ANCESTORS of the unknown row -> reverse test fails; (c) **blocklist** — remove the anchor blocklist -> blocklist tests fail; (d) **distinct** — replace the single-distinct-repo requirement with `MIN(repo)`/`LIMIT 1` -> distinct-repos test fails; (e) **unknown-only** — apply the inheritance logic to NON-unknown effective rows too, in the form "a non-unknown effective row with two or more distinct qualifying repos in its descendant set becomes `unknown`" (do NOT use the `COALESCE(inherited, own repo)` form: it is an equivalent mutant) -> Preservation (a) fails; (f) **wildcard** — compare with `N(x) LIKE N(u) || '/%'` instead of `substr` -> the wildcard tests fail. After the LAST revert, `git hash-object billing/otel/attribute.py` MUST equal H0 — verification: command output (the hashes).
3. Existing attribution suites still green — verification: `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_export_unattributed.py -q` output.
4. Baseline-relative tree check: `git status --short` lists exactly `M billing/otel/attribute.py` (task 01's change, hash H0 unchanged by this task), `?? tests/test_attribute_inheritance.py`, and the pre-existing `?? _goals/unknown-parent-child-inheritance/`, nothing else — verification: `git status --short` plus the H0 hash comparison.

## Files to Read

- `billing/otel/attribute.py`, `billing/otel/otel_store.py`, `tests/test_attribute.py`, `tests/conftest.py`
- `.claude/skills/python-testing-patterns/SKILL.md`, `.claude/skills/test-ladder/SKILL.md`

## Files to Create / Change

- `tests/test_attribute_inheritance.py` — new.
- `billing/otel/attribute.py` — temporary mutants only, reverted before the report (see the ownership block).

## Constraints

- Must: pytest only; no external services; reuse `tmp_db_path`; follow the helper style of `tests/test_attribute.py`.
- Must NOT: leave any change in production code; edit other tests; add a dependency; weaken an assertion to make a test pass. If a test exposes a defect in task 01, report it instead of editing `attribute.py`.

## Verification

- Rung 1: `python -m pytest tests/test_attribute_inheritance.py -v`
- Rung 2: `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_export_unattributed.py tests/test_invoice.py tests/test_reconcile.py -q`
