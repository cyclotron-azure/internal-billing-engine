# Goal: unknown-parent-child-inheritance

## Problem Statement

`billing/otel/attribute.py` resolves a datapoint's repo with an as-of join: the latest
`session_repo_timeline` row at or before the datapoint's `ts`. When that row's repo is
`'unknown'`, the datapoint bills to `unknown` even if the same session later moved into a
real repo that lives inside that very folder. Production evidence (2026-09-30, VM
`otel-data/otel.db`): nate.white's session started in `C:\dev\wealthspire` (no remote, a
project folder holding sub-repos) and then moved into
`C:\dev\wealthspire\src\Ticketing.Frontend` (real repo `wealthspire-ticketing`);
everything before the `cd` billed to `unknown`. The user wants this class recovered, but
under a STRICT no-misattribution rule: a likely-but-unproven repo is never assigned.

## Discovery Summary (Phase 1 Q&A, plus revision 1 decisions)

- **Rule (user, strict):** an `unknown` effective timeline row inherits a real repo ONLY
  when its `cwd` is path-related to the `cwd` of real-repo rows in the same session.
  Case-insensitive and separator-normalised (Windows/POSIX). Otherwise it stays `unknown`.
  User: "strictly avoid misattribution, even if it's a likely estimate."
- **Direction (user, revision 1, strictest):** the unknown folder must be an ANCESTOR of,
  or the SAME folder as, the real row's folder (real row is a descendant or equal). An
  unknown CHILD of a real repo's folder stays `unknown`: git walks up to the parent's
  remote, so an unknown child can only be a separate nested no-remote repo or a lookup
  flake, neither provably the parent's project.
- **Anchor scope (user, revision 1):** the unknown folder must be a PROJECT-LEVEL folder.
  Home folders, generic container folders, outer/sync folders, drive and filesystem
  roots, and top-level folders directly under a root can never inherit (exact blocklist in
  task 01). Nate's `C:\dev\wealthspire` still works: `wealthspire` is the project folder.
- **Which real rows (user choice):** ANY qualifying real row in the session, before or
  after the datapoint. If they name more than one distinct repo, the row stays `unknown`.
- **Must stay unknown (user's example):** Derek's session alternates between
  `...\Code\Dashnoard` (no remote) and `...\src\orbit-local` (real repo
  `github.com/cyclotron-security/orbit`). Unrelated folders, so Dashnoard rows stay unknown.
- **Mechanism (user choice, after a correction):** pure SQL inside `resolved_repo` (the
  path relation is expressible in SQLite: normalise with lower/replace/rtrim, compare with
  equality and `substr(...) = other || '/'`). NOT a Python-precomputed temp table, NOT a
  registered Python function. `resolved_view` / `resolved_repo` / `attribution_source`
  signatures AND every consumer (bill, invoice, reconcile, export, deploy/unknown-report.py)
  stay unchanged, with no stale state. A performance gate protects the approach; if it
  fails, escalate (the fallback is the precompute option).
- **Orchestrator-added conservative guards (flag to the user at delivery):**
  (a) the SAME folder counts as related (a folder cannot have two origins at once, so an
  `unknown` row at the same cwd as a real row is a git-lookup flake or a remote added
  mid-session); (b) `DirectoryAdded` timeline rows (extra directories, not a `cd`) never
  serve as the real-repo anchor; (c) the literal session id `'unknown'` (the receiver's
  placeholder for a missing id, which can pool unrelated users) never inherits;
  (d) SQLite `lower()` is ASCII-only, so non-ASCII case differences under-inherit
  (conservative; documented); (e) the anchor blocklist is a DENY-LIST, so a folder whose
  name is outside its vocabulary (for example `C:\Users\x\Acme`) can still inherit - an
  accepted residual that the user must knowingly accept at delivery (the vocabulary
  includes `work, clients, temp, tmp, appdata` as added strictness).
- **Attribution class:** a row resolved through inheritance reports `timeline`.
  `desktop-scratch` stays checked first and keys off `resolved_repo = 'unknown'`.
- **Phases:** Phase 6 docs alignment = YES. Phase 7 PR = NO. Ladder = escalate.
- **Deployment:** not touched. The VM runs stale code with an unresolved
  `docker-compose.yml` merge conflict; this goal changes repo code on the current branch
  only.

## Success Criteria

- [ ] Nate's case: session with timeline `C:\dev\wealthspire` (unknown) then
      `C:\dev\wealthspire\src\Ticketing.Frontend` (real repo R): datapoints whose effective
      row is the first row resolve to R, `attribution_source = 'timeline'`.
- [ ] Reverse case (real parent folder, unknown CHILD folder) stays `unknown`.
- [ ] Unrelated sibling folders (`...\Dashnoard` vs `...\src\orbit-local`) stay `unknown`.
- [ ] Two distinct qualifying real repos in one session leave the row `unknown`.
- [ ] A non-unknown effective row keeps its own repo even when related rows name other
      repos; a real effective row is never changed by a related unknown row.
- [ ] Home / container / outer / root / top-level anchors never inherit (task 01 blocklist).
- [ ] A session with no qualifying real-repo row stays `unknown`; `desktop-scratch` still
      wins for transcript sessions that stay unknown.
- [ ] Case-insensitive, `\`-vs-`/`, trailing-separator and prefix-lookalike
      (`C:\dev\wealth` vs `C:\dev\wealthspire`) handling is correct.
- [ ] Empty/NULL cwd never relates; `DirectoryAdded` rows never anchor; session_id
      `'unknown'` never inherits.
- [ ] Works for `token_usage` AND `cost_usage` via the unchanged `resolved_view`, for any alias.
- [ ] Every previously-passing test still passes (no regression in bill/invoice/
      reconcile/export/attribute suites); signatures of `resolved_repo`,
      `attribution_source`, `resolved_view` unchanged.
- [ ] Performance gate: on a synthetic store the resolved view over unknown-heavy data is
      not more than 3x slower than the pre-change baseline (median of 3 runs, including a
      heavy-tail session).
- [ ] Nothing is persisted; resolution stays at query time; runtime stdlib-only.

## Constraints

- Runtime is standard-library only; no new import in `billing/`.
- Repo attribution is resolved at QUERY time, never persisted (CLAUDE.md hard constraint).
- SQLite single-host/single-connection constraints unchanged; no new tables or columns.
- README.md is ground truth: it is updated in Phase 6 (docs), not in the code tasks.
- Retroactive by design: regenerating past invoices/exports re-resolves previously
  `unknown` usage to the inherited repo (and a late second related repo can flip it back).
  Flag this at delivery.
- Do not touch `deploy/`, `client-package/`, `docker-compose.yml`, or the VM.

```yaml
phases:
  align_docs: true
  pull_request: false
  ladder: escalate
```

## Out of Scope

- Fix B (folder -> bill-name mapping) and any new repo key for `local:<folder>`.
- Changing the hook (`claude-repo-tag.py`) or the client package.
- `cowork_attribute.py` and the Cowork pipeline (separate attribution path; will remain on
  the old rule, an accepted inconsistency to flag at delivery).
- `project_label.py` and the lake-table diagnostic columns (unchanged).
- Deployment/merge-conflict cleanup on the VM.

## Tasks (dependency order)

| # | Task file | Layer | Depends on |
|---|-----------|-------|------------|
| 01 | `01-attribute-inheritance.md` | Attribution & normalization | — |
| 02 | `02-tests.md` | tests | 01 |
