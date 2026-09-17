You are the implementer subagent. Read: .claude/agents/implementer.md

Task 04 FIX CYCLE 2 — **fresh spawn with model rotation** (cycle 1 was a resume; cycles 2-3
are fresh and pin a different model family).
CURRENT_DATETIME: 2026-09-16T19:50-04:00

## Context

Task 04 of `otel-export-loss-reduction` is essentially complete. Its evaluator verified
**18 of 19** criteria by execution, including every hard one: the quarantine trap (run 1
withheld with `resolved == []` and `examined_mtime == None`, run 2 ships), the
resolved-vs-withheld asymmetry, `too_recent` being non-resolving while other reasons
resolve, flag-before-POST proven durable by crashing the POST, permanence, pre-install
exclusion for both `cli` and `claude-desktop`, one shipping path, exit 0 across six
adversarial paths, and byte-identical copies. It also confirmed by end-to-end measurement
that **a replay cannot bill anything twice** — a re-shipped desktop record returns
`inserted: 0, duplicate: 5` and leaves the row counts unchanged.

**One criterion failed, and it defeats the purpose of the thing it measures.**

## The defect

`client-package/claude-transcript-usage.py:900` (and the `deploy/` copy):

```python
for _record, file_key, request_id, _ts in chunk:
    if request_id in too_recent_ids:
        continue  # non-resolving -- stays pending for a later run
    _mark_resolved(state, file_key, request_id)
    pending_by_file[file_key].discard(request_id)
    state["envelope_retries"].pop(_record_retry_key(file_key, request_id), None)
    shipped_count += 1      # <-- counts RESOLVED, not ACCEPTED
```

`shipped_count` increments for every record that gets resolved, and the only `continue`
above it is `too_recent`. So a record the server **permanently rejected** —
`session_has_otlp`, `invalid_entrypoint`, `invalid_session_id` — is counted as shipped.

Measured by the evaluator: a fixture of one `cli` record rejected `session_has_otlp`
produces

```json
{"shipped": 1, "rejected_by_reason": {"session_has_otlp": 1}, "replay_performed": true}
```

with **zero** records accepted. A fixture of three, two rejected, reports `shipped: 3`.

Why this is blocking rather than cosmetic: criterion 16 and the Part C requirement exist
specifically so that "this shipped and recovered nothing" is a **visible** outcome. The
persisted `state` tallies are the only surface anyone reads on a laptop — the stdout log
goes nowhere. As written, a zero-recovery replay reports recovery, which is the failure mode
the requirement was written to prevent, inverted. The accepted count is not even derivable
by arithmetic: with one `too_recent` and one `session_has_otlp`,
`shipped(1) - sum(rejected)(2) = -1`.

## Required fix

1. **Count only genuinely accepted records.** Build the **full** rejected-id set from
   `rejections` — not just `too_recent_ids` — and do not count those toward
   `shipped_count`. Keep resolution semantics **exactly** as they are: `too_recent` stays
   non-resolving, every other reason stays resolving. Only the tally changes.
2. **Add a `deferred` count** for the `too_recent` records, so the persisted numbers
   reconcile against each other:
   `intended.records_to_ship == shipped + sum(rejected_by_reason.values()) + deferred`.
   Without something like this the tallies cannot be cross-checked, which is most of their
   value. Put it in the same `cli_backfill_last_run` dict.
3. Re-verify with a **fully-rejected** fixture that `cli_backfill_last_run["shipped"] == 0`.
   That is the assertion that fails today.

## Write fence — unchanged

```
client-package/claude-transcript-usage.py
deploy/claude-transcript-usage.py
```

Both copies byte-identical (current sha256
`53dbf8f8b4a2492d88dcaa26a0c6cab5a9efdf285402f6d4846ccf32fa90c8c1`). Nothing under
`tests/`, nothing under `billing/`.

## Do not regress — all of this is verified by execution

The quarantine trap and its `resolved`/`examined_mtime` assertions; the
resolved-vs-withheld asymmetry for missing / non-string / out-of-set entrypoints;
`too_recent` non-resolving and every other reason resolving; the two-item replay reset
(`resolved` + `examined_mtime`, **never** `install_ts`); flag-before-POST durability under a
raising POST; the remainder shipping on the next run; pre-install exclusion; the single
shipping path; `entrypoint` passed verbatim with no placeholder ever substituted for a
missing `session_id`; the 1800s client window; exit 0 on every path including a
denied-write state directory; `ast.parse` clean on both copies; and the docstring/comment
text explaining why the watermark reset was deliberately removed.

The intended-volume log and `cli_backfill_replay_intended` are already correct and
persisted pre-POST — leave them alone.

## Model

requested: claude-fable-5-1 · tier: light · rotation: **cycle 2, different family**

## Rules

- Minimal diff: a rejected-id set, a guarded counter, and one new tally key.
- Do not change which records get resolved. Resolution and counting are separate concerns
  and only the second is wrong.
- Keep always-exit-0, one shipping path, stdlib only, both copies byte-identical.
- Do not edit any test. The current five-file baseline is **8 failed, 166 passed**, all
  eight owned by task 05. A ninth is a finding — report it, do not fix it.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Fix
[The rejected-id set, the guarded counter, the new key.]

## Reproduction (verbatim)
[a) fully-rejected fixture -> shipped == 0 with the rejected_by_reason breakdown.
 b) mixed fixture (one accepted, one session_has_otlp, one too_recent) -> the four numbers,
    and the reconciliation identity shown to hold.]

## Verification
[`python -m pytest tests/test_transcript_hook.py -q` -> result.]
[The two sha256 digests.]

## Anything else the fix touched
["None" is valid.]

### Footprint
files_read: <N> (~<C> chars)
```
