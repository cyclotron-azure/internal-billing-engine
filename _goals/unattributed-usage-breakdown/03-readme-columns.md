# Task 03: Document the new columns (README ground truth)

## Objective

`README.md` and `fabric/README.md` describe the two new lake columns, what each
`attribution_source` class means operationally, how `unattributed_project` is derived and
what it never contains, and that only `unknown` rows changed grain. `fabric/README.md`'s
column lists match the actual CSV headers.

## Dependencies

- 02-export-breakdown (the final column names and behavior)

```yaml
# --- task ownership contract ---
writes:
  - README.md
  - fabric/README.md
reads:
  - billing/otel/export.py
  - billing/otel/project_label.py
  - billing/otel/attribute.py
depends_on:
  - "02-export-breakdown"
owner: implementer
rewrite_semantics: targeted-insertion
eval_depth: light
```

## Requirements (exhaustive — the evaluator verifies every item)

**README.md**
- [ ] §"Shipping invoices to a data lake": both table bullets mention that `unknown` rows
      additionally split by `attribution_source` and `unattributed_project`; attributed
      rows keep their grain.
- [ ] A short table or list of the `attribution_source` values that can appear on
      unknown rows, each with an operational meaning, worded to match
      `attribute.py:28-45,88-94`:
      - `timeline`: the repo hook fired, but the folder it reported has no git remote
        (a plain folder, an unzipped download, or a local repo with no `origin`).
      - `no_remote`: no timeline rows; the launch-time wrapper tag was `unknown`
        because the launch directory had no git remote (a local repo with no remote
        counts).
      - `absent`: no repo signal ever arrived (hook not installed or not firing, or a
        surface the wrapper never ran on).
      - `desktop-scratch`: transcript-sourced usage (desktop app, and the cli /
        VS Code transcript backfill) with no billable repo.
      - State that `wrapper` is not expected on unknown rows (it only resolves to a
        real repo).
- [ ] The `unattributed_project` rule in plain words: root folder name only; the
      walk-up rule (outer vs in-project containers); per session; the special values
      `local:(home)`, `local:(scratchpad)` (any Claude-internal folder) and
      `local:(other)` (allowlist guard); never a full path or username; derived at query
      time from the stored timeline (retroactive, nothing persisted); diagnostic only
      (never a repo key, never billed); and the accepted-mislabel caveats from goal.md
      "Risks and rollback".
- [ ] The module list gains a `project_label.py` bullet next to `attribute.py`, and the
      `export.py` bullet mentions the two columns.
- [ ] A note for Power BI / semantic-model owners: row counts for `unknown` changed;
      sum, don't count. Filter unattributed usage with
      `repo = 'unknown' AND attribution_source <> ''` (a real repo whose bill name is
      `unknown` stays unsplit with a blank class).
- [ ] The collision correction: the export now sums usage that collapses onto one row
      after model normalization (`[1m]`, dated snapshots) or user-email coalescing,
      where it previously kept only one group; totals now match `invoice.py`, and some
      historical Fabric totals rise on the next sync.
- [ ] The table-grain lines (README §"Shipping invoices to a data lake" and the
      `export.py` bullet) mention that `unknown` rows are additionally grained by the
      two new columns.

**fabric/README.md**
- [ ] Both column lists under "Result" match `export.SUMMARY_FIELDS` / `export.LINE_FIELDS`
      exactly, in order. This task owns correcting the existing drift (`bill_name` →
      `repo` in the summary list; `bill_name, repo` → `repo, repo_key` in the line-item
      list); Phase 6 only verifies it.
- [ ] One sentence pointing to the top-level README for what the two new columns mean.

## Acceptance Criteria

1. The fabric/README.md column lists equal the field lists in `export.py`, in order —
   verification: command output (print both field lists and grep the README lines).
2. README.md contains all five class names with a meaning each and the label rule with
   both special labels — verification: command output (grep).
3. No unrelated README lines changed — verification: command output (`git diff --stat`
   and a read of `git diff README.md fabric/README.md`).

## Files to Read

- `README.md` — sections around lines 150–170 (module bullets) and 293–330 (lake tables)
- `fabric/README.md`
- `billing/otel/export.py`, `billing/otel/project_label.py`, `billing/otel/attribute.py`
- `_goals/unattributed-usage-breakdown/goal.md` — Discovery Summary (wording of the rules)

## Files to Create / Change

- `README.md` — targeted insertions only.
- `fabric/README.md` — column lists + one sentence.

## Constraints

- Must: surgical edits; keep the README's existing voice and heading structure.
- Must NOT: touch code, `_goals/`, `_research/`, or any other doc; describe out-of-scope
  follow-ups as done.

## Verification

- `git diff README.md fabric/README.md` reviewed in the report.
