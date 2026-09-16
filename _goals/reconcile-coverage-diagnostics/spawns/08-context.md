You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-09-16T11:05-04:00

## Task

Execute task 03 of the `reconcile-coverage-diagnostics` goal: the output rendering and CLI
flags in `billing/reconcile.py`.

**Your specification is `_goals/reconcile-coverage-diagnostics/03-reconcile-output.md`.
Read it in full before writing anything and follow it exactly.** It has 16 numbered
acceptance criteria plus 7b and 7c — 18 items in total — and its requirements are
exhaustive.

**The terminal output is the deliverable here, not just the code.** Tasks 01 and 02 built
plumbing; this task is the part a human reads next to an invoice. A number that is
correct but mislabeled is a worse outcome than a missing feature, because someone will
bill a client from it.

## Requirements

All requirements are in the task file: CLI flags, the exact-integer column, the
always-printed defect sections, `--daily`, `--by-surface`, two carried-over cleanups from
task 02's evaluation, and Preserved behavior. Work from the file. Shape of the work:

- Three `argparse` flags — `--by-surface`, `--daily`, `--detail` (implies both).
- `run()` gains two **keyword-only** parameters; every existing call shape keeps working.
- An exact-integer column beside every `ftok()` figure, thousands-separated.
- A module-level width constant, sized to the **global maximum across all flag
  combinations** — the six-column `--daily` row is the widest line. Prose must wrap to it.
- `UNMAPPED TOKEN TYPES` and `DEDUPE DROPS` print whenever a funnel prints, regardless of
  flags.
- Each `--by-surface` sub-block ends with a `TOTAL` row whose share reads `100.00%`.

### The two things most likely to go wrong

1. **The `DEDUPE DROPS` section must not let the measurement state suppress a real
   count.** This was a genuine contradiction in an earlier draft of the plan and it was
   fixed for a reason: `by_type` can legitimately be non-empty while `measurement` is
   `"none"` or `"partial"` — a replayed export records drops dated to the day they
   describe, and an interrupted first epoch write leaves the epoch absent while later
   drops commit. The measurement state selects the **wording**; it never decides whether
   counts appear. Criteria 7b and 7c exist to catch a regression here.
2. **The `--by-surface` header must say it is a share of captured and NOT coverage.** The
   truth side has no surface dimension, so a per-surface percentage has no denominator. An
   unlabeled percentage there reads as coverage on an invoice review. Criterion 12 asserts
   both literal strings.

## Tasks 01 and 02 are complete and evaluated

Task 01 PASSED 5/5; task 02 PASSED with all 16 criteria verified by observation. The
"What task 02 actually returns" section in your task file lists the **verified** return
shapes — build against those, not against prose elsewhere. Two details that will bite if
you assume otherwise:

- `captured`/`tagged` always carry all four CANON keys including zeros. `unmapped` omits
  zeros and is `{}` when empty.
- NULL **and empty-string** dimension values both coalesce to `"(none)"`, and in
  `unmapped` a NULL `token_type`, an empty-string one, and a literal `"(none)"` all
  collapse into one key. Do not render `"(none)"` as though it can only mean "absent".

Your task file also carries **two required cleanups** carried over from task 02's
evaluation (a dead `DEDUPE_EPOCH_META_KEY` import to drop, and a falsy-epoch guard to make
consistent). Do both; they are small and in your file.

## Files to Read

- `_goals/reconcile-coverage-diagnostics/03-reconcile-output.md` — your spec. First, fully.
- `billing/reconcile.py` — the whole file, post-task-02. Note `run`, `_print_funnel`,
  `ftok`, `pct`, and task 02's seven aggregation functions.
- `billing/otel/otel_store.py` — task 01's `dedupe_epoch` semantics (an ISO8601 timestamp
  written by the insert path), for the wording of the unmeasured and partial cases.
- `README.md` — the `reconcile.py` bullet and the pilot "Coverage" bullet, which describe
  this output. Ground truth; Phase 6 syncs it, so do **not** edit it here, but read it so
  your section names and wording do not contradict it.
- `.claude/skills/test-ladder/SKILL.md` — rungs 1–2 only.

## Write fence

```
billing/reconcile.py
```

The only path you may modify. Do **not** touch `billing/otel/otel_store.py` (task 01,
complete), any test file (task 04's fence), or `README.md` (Phase 6 owns it). Scratch
scripts and fixtures go in your session scratchpad directory, never in the repo, never in
`data/`.

## Model

requested: claude-sonnet-5 · tier: light · rotation: n/a (first attempt)

## Rules

- **Stdlib only.** No third-party import may enter `billing/`.
- Do **not** recompute any aggregate. Consume task 02's functions. If a number you need is
  not in their return value, **report that** rather than querying the database from a
  print helper.
- Do **not** add `--json`, an exit-code threshold, or any machine-readable mode — out of
  scope by explicit decision.
- Do **not** change `ftok()` or `pct()` behavior. `pct()` already returns `"n/a"` on a zero
  denominator; rely on it rather than reimplementing division.
- The no-analytics-rows early return (`run()`'s `if result is None:` branch) and the
  `except AnalyticsError` branch keep their current output exactly. Do not add the new
  sections to either. Do not confuse the `if result is None:` branch with the success
  branch immediately after it, which you **do** modify.
- `store.close()` must still be called on every return path, including new ones.
- Climb test-ladder rungs 1–2 only. **Do NOT run `python -m pytest -q`** (rung 3). Your
  targeted command is `python -m pytest tests/test_otel_store.py -q`.
- If a requirement seems wrong or impossible, implement nothing on a guess: report the
  conflict.

## Output

```
MODEL: <the model you are actually running as>
STATUS: completed | blocked

## What changed
[Each edit to billing/reconcile.py by symbol name, including the two carried-over
cleanups.]

## Acceptance criteria
[One line per criterion 1-16 plus 7b and 7c: how your implementation satisfies it, or NOT
YET if it depends on task 04's tests.]

## REQUIRED: captured output
Paste the full verbatim stdout of each of these runs against a scratchpad fixture
containing OTLP + transcript rows, an unmapped token type, a NULL entrypoint, a NULL
query_source, at least one dedupe drop, and three distinct days:
  1. default (no flags)
  2. --daily
  3. --by-surface
  4. --detail
  5. one run per DEDUPE DROPS state 1, 2 and 3 (vary the epoch meta value)
  6. one run showing a non-empty by_type under a non-"full" measurement state
     (counts_outside_measurement True) -- the criterion 7b/7c case
This output IS the deliverable. Paste it, do not summarize it.

## Width check
[The width constant you chose, the longest line in a --detail run, and confirmation that
every ===/--- rule is that same length and no line exceeds it.]

## Verification
- `python -m pytest tests/test_otel_store.py -q` -> [exact result line]

## Deviations / concerns
[Anything you could not do as specified, or where the spec is ambiguous. "None" is valid.]

### Footprint
files_read: <N> (~<C> chars)     # C as digits only, no thousands separators
```
