# Goal: unattributed-usage-breakdown

## Problem Statement

The Fabric-bound lake tables (`claudeusagesummary`, `claudeusagelineitems`) report every
unattributed datapoint as the single value `repo = unknown`. That hides two different
things: *why* the usage is unattributed (the hook never fired, the directory has no git
remote, a desktop scratch session, or a timeline row that itself says `unknown`) and
*what project* the developer was actually working in. `billing/otel/attribute.py` already
computes the "why" (`attribution_source`) but `billing/otel/export.py` drops it. The
timeline already stores the "what" (`session_repo_timeline.cwd`) but nothing turns it
into a privacy-safe label. On 2026-09-28 it took three rounds of live SQL on the
production VM to explain two users' `unknown` spikes (derek.mcconnell, sumit.bhatia),
both of which turned out to be real work in folders with no git remote. That diagnosis
should be readable straight from the Fabric tables.

## Discovery Summary (Phase 1 Q&A)

- **Split scope:** only rows whose `resolved_repo` is `unknown` split by class. Rows
  billed to a real repo keep today's grain and values exactly; the new columns are blank
  on them.
- **Where:** both existing tables, `claudeusagesummary` and `claudeusagelineitems`. No
  new table.
- **New columns:** `attribution_source` (one of `timeline`, `no_remote`, `absent`,
  `desktop-scratch`, and `wrapper` if it ever occurs on an unknown row) and
  `unattributed_project` (e.g. `local:Dashnoard`). Both are grouping keys on unknown
  rows. Appended at the END of each field list so no existing column changes position.
- **Label value:** the project's ROOT folder name only (user answer: "just the root
  should be recorded"; confirmed `Dashnoard`, not `Dashnoard/OfficeDashboard/backend`).
  Subfolders and everything above the root are dropped.
- **Deep start:** if a session starts inside a subfolder, walk up to the project top
  using the session's own cwd history and the common container folders (`Code`, `src`,
  `source`, `repos`, `projects`, `dev`, `git`, `GitHub`, `workspace`). The exact rule
  (outer vs in-project containers) is the Phase 3 revision below and task 01's algorithm.
- **Outside root:** cwds outside the session's root (Derek's `src\orbit-local`) still
  get the session's root label. The label is per session.
- **Privacy:** never export a full path. A label is one folder name and is never a
  drive letter, `Users`/`home`, a username, or a `OneDrive*` folder. The final rule set
  (see the Phase 3 decisions below and task 01) is:
  - a start inside the home / OneDrive / container zone with no project folder →
    `local:(home)`;
  - a folder directly inside home is allowed as a label (so a company sync root shows
    the org name);
  - any Claude-internal folder (including `~/.claude/projects/<slug>/...`, which has no
    session_id in it) → `local:(scratchpad)`, and the slug never leaks;
  - anything still path-like, a `OneDrive*` name, or the username → `local:(other)`.
- **Phase 3 revision decisions (user, 2026-09-28):**
  - Container folders (`src`, `Code`, …) are OUTER only directly under the home /
    drive / OneDrive level; inside a project they point back to their parent
    (`C:\Cyclotron\proj\src\components\ui` → `local:proj`).
  - A folder directly inside a home folder is allowed as a label (`C:\Users\Derek\orbit`
    → `local:orbit`; a session started exactly in a sync root like
    `C:\Users\Derek\Cyclotron Inc` shows the org name).
  - A final allowlist guard replaces anything still path-like (contains `:`, starts with
    `.`, a `C--` project slug, `OneDrive`, or the username) with `local:(other)`.
  - Any Claude-internal directory (`.claude\...`, `Temp\claude\...`) counts as a
    scratchpad whether or not a `scratchpad` folder is present.
- **Diagnostic only:** `resolved_repo`, invoices and `repo_name_map` are unaffected, and
  the label never becomes a repo key. Tokens and costs are unaffected apart from the
  collision correction below.
- **Collision correction (Phase 4 decision, user, 2026-09-28):** the pre-change export
  overwrote (rather than summed) groups that collapse onto one row after model
  normalization or user-email coalescing, silently dropping usage. The user accepted
  summing them (matching `invoice.py` / `bill.py`), even though some Fabric totals rise.
- **Query time:** computed from data already stored, never persisted, no hook/client
  change; covers historical data retroactively (CLAUDE.md hard constraint). The root is
  derived once per session, not per datapoint.
- **Consumers:** a Power BI report reads these tables. Only unknown rows change grain;
  README must say so, so the report can be checked.
- **bill.py:** out of scope (user answered "No, exports only").
- **Rollout context:** all developers are on the opt-in `client-package/` track; no MDM.
- **Phase 6 (docs):** yes. Task 03 owns correcting `fabric/README.md`'s column lists
  (today they say `bill_name` where the headers are `repo`, and `bill_name, repo` where
  the line-item headers are `repo, repo_key`); Phase 6 verifies it and sweeps any other
  docs, but does not redo it.
- **Phase 7 (PR):** no. Changes stay uncommitted on the current branch.
- **Ladder:** escalate.

## Success Criteria

- [ ] Both exported CSVs carry `attribution_source` and `unattributed_project` as their
      last two columns; all earlier columns are unchanged in name and order.
- [ ] For every row billed to a real repo, all pre-existing column values except
      `generated_at`, and the row count, are identical to the pre-change export of the
      same store, EXCEPT where the pre-change export dropped colliding groups (see
      below); the two new columns are empty.
- [ ] `unknown` rows split by (`attribution_source`, `unattributed_project`), and the sum
      of tokens and cost across the split rows equals the database total for that
      (day, model, user).
- [ ] Collision correction (user decision, 2026-09-28): where several raw models that
      `normalize_model` collapses (e.g. `[1m]`, dated snapshots, blank model), or
      NULL / `""` / `"unknown"` user emails, land on one export row, the export now SUMS
      them instead of keeping only the last group. Export totals per
      (day, repo, model, user) equal the database, and per (repo, model, period) equal
      `invoice.py`. Some Fabric totals rise where usage was previously dropped.
- [ ] A session launched in `...\Code\Dashnoard` or `...\Code\Dashnoard\OfficeDashboard\backend`
      is labelled `local:Dashnoard`; the Sumit shape
      (`C:\Cyclotron\Insights Agent\ai-presales-agent-main[\ai-presales-agent-main]`)
      is labelled `local:ai-presales-agent-main`; all 38 worked examples in task 01 hold.
- [ ] No `unattributed_project` or `attribution_source` cell contains a path separator,
      a drive letter, `Users`, a username, `OneDrive`, `.claude`, or a `C--` project
      slug. (Existing columns such as `repo` and `user_email` are out of this check.)
- [ ] `invoice.py` output and `resolved_repo` are unchanged.
- [ ] README.md and fabric/README.md describe the new columns, the class meanings, the
      label rule, and the grain change for unknown rows.

## Constraints

- Runtime is standard-library only; nothing new may be imported under `billing/`.
- SQLite is single-host, single-connection: no threads, no second connection, no pool.
- Repo attribution stays resolved at query time; nothing new is persisted, no schema
  change, no new table in `otel.db`.
- `resolved_view()` / `attribution_source()` in `attribute.py` are reused, not
  re-implemented or edited.
- The timeline is read once per export build to derive session labels (one SELECT, then
  Python grouping); no per-datapoint correlated subquery for labels.
- No change to hooks, `client-package/`, `deploy/`, `invoice.py`, `bill.py`,
  `normalize.py`, or the Fabric notebook.

```yaml
phases:
  align_docs: true
  pull_request: false
  ladder: escalate
```

## Risks and rollback

- **Rollback:** revert `billing/otel/export.py` (and delete `project_label.py`). The
  Fabric notebook uses `overwriteSchema`, so the next sync drops the two columns.
- **Wider audience:** folder-root names move from billing admins (who can already query
  `otel.db`) to whoever reads the Fabric tables / Power BI report. The client-package
  consent notice covers cwd collection; the label exposes only one folder name, never a
  path or username.
- **Accepted mislabels:** a session that visits a real ancestor folder outside the
  outer zone (e.g. `C:\Cyclotron`) takes that ancestor as its root; a session that
  starts in a real repo and then works in a no-remote folder labels those unknown rows
  with the start folder's name. The label is a hint, not a verdict.
- **Export cost:** grouping on `attribution_source` must not force its CASE expression
  on every attributed row (see task 02).

## Out of Scope

- `bill.py` console output.
- `invoice.py` / invoice line items.
- `is_own_scratchpad()` not matching the project-slug scratchpad layout (client hook
  change; follow-up).
- cwd-based attribution undercounting work done in another repo by absolute path
  (Derek's orbit worktree visits; follow-up).
- A `cost_source` column (pinned out of scope by an earlier goal; still out).
- Any change to the Fabric notebook or Power BI report.
- Committing, pushing, or opening a PR.

## Tasks (dependency order)

| # | Task file | Layer | Depends on |
|---|-----------|-------|------------|
| 01 | `01-project-label.md` | Attribution & normalization | — |
| 02 | `02-export-breakdown.md` | Export & lake sync | 01 |
| 03 | `03-readme-columns.md` | Docs (ground truth) | 02 |
| 04 | `04-tests.md` | tests | 01, 02, 03 |

Task 01 is the contract: it freezes the `billing/otel/project_label.py` interface that
task 02 consumes.

## Orchestration Progress: unattributed-usage-breakdown

### Phase 1: Alignment
- [x] Discovery questions asked (3 rounds)
- [x] Follow-up questions asked (label value vs earlier "capture all of this")
- [x] Summary presented to user
- [x] User confirmed understanding ("Yes", 2026-09-28)

### Phase 2: Goal Creation
- [x] goal.md created
- [x] Decision gates passed (label = root only; outside-root = session root)
- [x] Task files created

### Phase 3: Goal Evaluation
- [x] Evaluator invoked (attempt 1: NEEDS REVISION; attempt 2: NEEDS REVISION)
- [x] Final verdict: PASS (with notes), attempt 3

### Phase 4: Execution
| Task | Cycle 1 | Cycle 2 | Cycle 3 | Final Verdict |
|------|---------|---------|---------|---------------|
| 01-project-label | NEEDS FIXES | PASS (with notes) | - | ✅ |
| 02-export-breakdown | NEEDS FIXES (criteria; user chose Option A) | PASS (with notes) | - | ✅ |
| 03-readme-columns | NEEDS FIXES | PASS (with notes) | - | ✅ |
| 04-tests | PASS (with notes) | - | - | ✅ |

### Phase 5: Final Audit
- [x] Audit invoked (attempt 1)
- [x] Final verdict: APPROVED
- [x] Quality checks (rung 3) passed: 950 passed

### Phase 6: Align Docs
- [x] Doc audit APPROVED (6.3 folded into 6.5; README.md 3 edits)

### Phase 7: Pull Request
- skipped per goal.md (`pull_request: false`)
