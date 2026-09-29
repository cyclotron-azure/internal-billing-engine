**Model (self-reported)**: claude-opus-5-5 (Opus 5.5; the package requested claude-opus-5)

VERDICT: PASS (with notes)
## Verdict: PASS (with notes)
**Score**: 4/5

The amended criteria can be met, and the current export.py meets them. The code is unchanged since my previous review.

### What I verified
- export.py is unchanged since the previous verdict → ✅ Verified. Its mtime is still 2026-09-28 11:46:34, the same as at the first review, and its SHA-256 is D2FFC345…61BB2. `git status --short` is the same as before: ` M billing/otel/export.py`, ` M client-package.zip` (last written 09-25, before this task), `?? _goals/...`, `?? billing/otel/project_label.py`. `git diff --stat` is still 68 lines on export.py. `git diff --quiet HEAD -- attribute.py invoice.py bill.py normalize.py tests README.md` exits 0.
- Amended Requirement "Collision correction" (02-export-breakdown.md:42-45) → ✅ Verified. I extended my collision store with:
  - `[1m]` and dated-snapshot (`-20250929`, `-20251001`) models on attributed and unknown rows;
  - NULL, `""` and literal `"unknown"` user emails;
  - a second month (Feb) with an `opus-4-8[1m]` / `opus-4-8` pair;
  - a transcript row with cost_source=rate_card.

  Across all 6 keys, the new export equals the database per (day, resolved_repo, normalized model, coalesced user): `True`. The old export equals the database: `False`. It dropped usage on 4 keys, for example acme-web/sonnet-5/a@x.com: DB 2050 / $21.50, old 1000 / $10.00, new 2050 / $21.50. Summary rows equal the database per (day, bill, user): `True`.
- Amended goal criterion "export equals invoice.py per (repo, model, period)" → ✅ Verified. I compared line-item sums inside each period with `invoice.gather()` (tokens, and actual_cost + estimated_cost):
  - 2026-01: new == invoice `True` over 3 keys, including globex's rate_card row and `unknown`. Old == invoice `False`: acme-web/sonnet-5 invoice 2090 / $21.90, old 1007 / $10.07.
  - 2026-02: new == invoice `True`. Old `False`: 500 / $5.00 vs 300 / $3.00.
- Amended unknown-split conservation (against the database; :55-58) → ✅ Verified. The unknown key sums to DB 5940 / $59.50 on the collision store, and equals the single pre-change row (940 / $9.50) on the collision-free store.
- Amended AC3 → ✅ Verified on both branches: DB totals on the collision store, and on the collision-free store `line totals old==new: True` with DB, old and new all at 1160 / 12.7.
- AC2 (attributed rows identical on a collision-free store) → ✅ Verified again. Summary and line items both show attributed `identical=True`, with the `timeline`/`local:Dashnoard`, `absent`/"" and `no_remote`/"" split.
- AC1 → ✅ Verified in the previous run. The headers and field lists are unchanged and `prefix ok True True`; export.py itself is unchanged.
- AC4 → ✅ Verified in the previous run, and the code is unchanged. At 24k datapoints, 25% unknown: best 2.14, median 1.85 (best-of-3 2.53); 0%: 1.40 / 1.63; 50%: 2.89 / 2.06. At 80k: 1.82 / 1.69, 1.63 / 1.55, 2.07 / 1.97.
- AC5 → ✅ Verified. `python -m pytest tests/test_export.py tests/test_attribute.py tests/test_invoice.py -q` gave `25 passed in 2.40s`.
- Unchanged from the previous verification, since the code is identical → ✅:
  - attribution_source is evaluated only for unknown rows (counting UDF: 0 / 6,000 / 12,000 calls, equal to the unknown row counts);
  - resolved_view runs once per table and load_session_labels once per build;
  - a build runs 4 SELECTs and makes 0 changes to the database;
  - stdlib only, single connection;
  - the "is unknown" test uses resolved_repo;
  - the label is isolated from name_of.
- Auto-fail triggers: none fired. No third-party import, no secret, no second connection or thread, nothing persisted, no bypass of normalize, no auth code, no invoice records mutated, no live service.

### Issues found
None blocking. The previous two majors are resolved:
1. The `+=` change on attributed rows is now the specified behaviour ("Collision correction", 02-export-breakdown.md:42-45; goal.md:61-64, 90-95), and the user accepted it.
2. The conservation criterion and AC3 are restated against the database, can be met, and are met.

### Notes (non-blocking)
- **[minor]** export.py:6-7. The docstring grain lines still understate the grain for unknown rows. This was left as is by the orchestrator's decision and routed to task 03 for the README. Minor because it is prose and changes no output.
- **[minor, spec-mandated]** A real repo whose bill name resolves to `unknown` produces a `repo=unknown` summary row with a blank `attribution_source`. Task 03 is to document the `repo='unknown' AND attribution_source<>''` filter. Minor because the task explicitly requires this behaviour.
- **[minor]** The CASE guards cost 1.4–1.6× even at 0% unknown, and at 24k datapoints the 50% ratio (ungated) reached 2.89 best. The gated 25% ratio is comfortably inside 3×. `AS MATERIALIZED` is the permitted optimisation if this matters.
- **[minor]** There is no in-repo test of the collision correction yet. Task 04 owns it ([1m], dated snapshot, NULL vs "" email, against the database and invoice.py). Until then, only my scratch checks protect it from regression.
- Scratch evidence is in the session scratchpad at `ev09\recheck.py`. The seeding error I hit on the first run was in my own script (it passed request_id for OTLP rows), not in the code under review.

### Footprint
files_read: 3 (~13000 chars) this round (10-context.md, the amended 02-export-breakdown.md section, and a goal.md grep); plus export.py and invoice.py from the previous round, already verified unchanged
commands_run: 5
