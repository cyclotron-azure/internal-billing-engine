You are the evaluator subagent, in **audit mode**. Read: .claude/agents/evaluator.md

Fresh spawn. CURRENT_DATETIME: 2026-09-21T17:15-04:00

## Task

Phase 6.5 — **narrowly-scoped confirmation pass**, not a fresh open-ended cycle. Cycle 3
(the max for this gate) found exactly one blocking item: `client-package/INSTRUCTIONS.md`
still promised a data field (whether a record "came from the desktop app") that only the
retired `claude-transcript-usage.py` hook ever populates — a residual instance of the
same correction that goal's escalation resolved. That one item is fixed. Your job is to
confirm it, and confirm nothing else regressed — not to re-run the open-ended sweep a
fourth time. Verdict: **APPROVED** or **ISSUES**.

## What was fixed

`client-package/INSTRUCTIONS.md`'s "What is collected" list had the "desktop-app usage
specifically, that it came from the desktop app" bullet removed (verified: `entrypoint`
is transcript-rows-only per `otel_store.py:35`'s schema comment, and the OTLP
`insert_datapoint` call in `receiver.py` never passes it). The "subagent" half of that
same bullet was kept, since `query_source` genuinely is always collected. A second, small
addition: `client-package/ADMIN.md`'s "What's in the package" table gained a row noting
`claude-transcript-usage.py` physically exists in the directory but is not shipped,
matching the table's existing pattern for other non-shipped files (`build.py`,
`.gitattributes`).

Orchestrator-confirmed: the bullet is gone, the new table row is present, full suite is
432 passed.

## What to verify

1. Read the actual current text of both edits yourself and confirm they're accurate
   against source (`otel_store.py:35`, `receiver.py`'s OTLP insert call).
2. Confirm the "subagent" claim that was **kept** is genuinely accurate (don't just trust
   that it survived — check it independently, since this audit's whole point across three
   cycles has been "don't trust what appears to have survived a rewrite").
3. Confirm nothing else in either file changed beyond these two edits —
   `git diff client-package/INSTRUCTIONS.md client-package/ADMIN.md` should show a small,
   targeted diff.
4. Run the full suite once yourself to reconfirm green.
5. This is explicitly **not** a mandate to re-sweep the whole doc set again. If you notice
   something in the course of the above, report it — but don't go looking for a fourth
   round of the same open-ended hunt.

## Rules

Evaluate only — **no repository writes**. Model: claude-opus-5 · tier: frontier.
Keep the report short — this is a narrow confirmation, not a full audit.

## Output

```
VERDICT: APPROVED | ISSUES
MODEL: <model>

## The fix
[Confirmed / not, how verified.]

## The kept "subagent" claim
[Confirmed accurate / not.]

## Diff scope
[Confirmed small and targeted / not.]

## Full suite
[Result.]

## Anything else noticed
[Or "nothing".]

### Footprint
files_read: <N> (~<C> chars)
```
