Phase 3 cycle 3 — RESUMED evaluator. CURRENT_DATETIME: 2026-09-16T15:30-04:00

This is the **final** cycle; `phases.ladder: escalate`, so a NEEDS REVISION here escalates
to the user rather than looping. Weight that: distinguish "this will produce wrong bills or
silently do nothing" from "this could be phrased better."

All three cycle-2 blocking findings and all three non-blocking were accepted. I verified
C1, C2 and C3 against source myself before accepting — `invoice.py:215`/`:224-225`, the
independent `receiver.py:163`/`:176` branches, the `:509-511` short-circuit preceding
`:529`, and `install_ts` at `:647-649` all check out exactly as you reported.

## Applied

**C1 — guard table scope.** `02-store-reads.md`: `sessions_with_otlp_rows` now returns a
session with at least one `usage_source='otlp'` row in **`token_usage` OR `cost_usage`**,
with your `invoice.py` and `receiver.py` citations in the requirement text as the reason.
`last_ingest_at` likewise reads the greatest `MAX(ingested_at)` across both tables (your
NON-BLOCKING-6). To keep criterion 6's statement count meaningful, both tables are required
to be covered in **one** statement per chunk via `UNION`, not two queries. Two new criteria:
**02.13** — a session whose only OTLP row is in `cost_usage`, built via
`insert_cost_datapoint` **alone**, *is* returned (the double-billing criterion); **02.14** —
`last_ingest_at()` reflects a `cost_usage` row newer than every `token_usage` row.
Propagated: `03.10` now runs twice, once with OTLP rows in `token_usage` and once with the
only OTLP row in `cost_usage`; `04.17` now asserts the `cost_usage` count as well as
`token_usage`; goal.md gained a matching success criterion; `05-tests.md` gained mutation
**(f)** "narrow the guard back to `token_usage` only" and a trap bullet warning that 02.13
and 02.14 pass vacuously if the fixture also inserts a token row.

**C2 — replay no-op.** Part C now clears **three** things, not two: `resolved`,
`examined_mtime`, and the watermark — with the state key corrected to `install_ts` and a
note that `install_epoch` is a derived local. A dedicated requirement bullet explains the
`:509-511`-before-`:529` ordering and states explicitly that omitting `examined_mtime`
makes the replay a production no-op that still passes a test whose fixture left it at
`None`. **04.13** now *requires* the fixture to set `examined_mtime` to each file's real
current mtime. `05-tests.md` gained mutation **(g)** "omit `examined_mtime` from the reset,
which criterion 13 must catch."

**C3 — interrupted replay.** A new requirement makes the state reset **permanent**, never
restored after the pass, with your batch/`stop_due_to_transport` reasoning recorded.
**04.14** now has both halves: (a) no double-replay, **and** (b) the un-shipped remainder
still ships on the next run — with a note that (a) alone passes either way. goal.md gained
"An interrupted replay finishes on a later run rather than losing its remainder."

**NB4 — the contradiction you predicted I would introduce.** Confirmed and corrected in
goal.md's favour of task 04: the replay clears **all** per-file state including desktop,
and goal.md now carries the reason (a flat `resolved` list has no entrypoint, so selective
clearing would require re-parsing every transcript — the thing the watermark prevents) plus
the safety argument (`transcript_key` drops the re-shipped desktop record; the cost is one
wasted POST). The Discovery Summary's "for `cli`/`claude-vscode` only" phrasing is gone.
The pre-N5 "without being marked processed" success criterion is now phrased as `resolved`
/ `examined_mtime`.

**NB5 — `rewrite_semantics`.** Split per owned file: `whole-file` for the three new test
files, `targeted-insertion` for `COVERAGE_MAP.md` and the three pre-existing test files
under the surgical fence.

**Your dry-run steelman — partially adopted, and I want you to push back if the rebuttal is
weak.** Task 04 now requires logging the **intended volume before the first POST** (files
eligible, groups eligible, records to ship), so a zero-shipping replay is visible at the
moment it happens rather than inferred from a tally afterwards. I did **not** adopt a full
human-gated two-step, on the grounds that the hook runs unattended on `SessionEnd` across a
fleet of laptops with no operator in the loop, so the guards rather than a review step have
to be what makes the writes safe. If you think that rebuttal does not hold, say so plainly.

Counts re-verified by grep: task 01 = 7, task 02 = **14**, task 03 = 19, task 04 = 18,
total **58**, reflected in `05-tests.md`'s objective, its requirements line, and criterion 6.

## What I need

1. Do C1, C2 and C3 now actually close, or did a fix move the problem? C1 touched the
   contract task, so check its propagation into 03.10, 04.17 and the goal criterion is
   complete and consistent.
2. The `UNION`-per-chunk requirement is new. Does it break criterion 6 or 7's statement
   arithmetic, or the `SQLITE_MAX_VARIABLE_NUMBER` reasoning (the same 500 ids now appear
   twice in one statement — is the 500 chunk still right, or does it need halving)?
3. Any **new** defect from these revisions.
4. Your ruling on the dry-run rebuttal.
5. If you reach APPROVED/PASS, say so unambiguously — the orchestrator will begin Phase 4
   immediately on your verdict.

Same rules: evaluate only, no repository writes, no full-suite run.

## Output

Same format. Verdict line first. If NEEDS REVISION, mark each finding with whether it is
**bill-correctness**, **silent-no-op**, or **cosmetic**, so escalation to the user can be
scoped honestly.
