You are the evaluator subagent. Read: .claude/agents/evaluator.md

Fresh spawn. CURRENT_DATETIME: 2026-09-16T19:30-04:00

Also read `.claude/skills/task-criteria/SKILL.md` and apply it.

## Task

Evaluate task 06 of `otel-export-loss-reduction` against its **9** acceptance criteria.
Verdict: **PASS**, **PASS (with notes)**, or **NEEDS FIXES** / **REJECT**.

`eval_depth: full` — this edits the `/v1/metrics` ingest path that every OTLP row in the
billing database flows through, and the value being changed is an input to `dp_key`.

## Files to Read

- `_goals/otel-export-loss-reduction/06-otlp-session-id-coercion.md` — the task, the
  measured reproduction table, the settled `dp_key` analysis, and its 9 criteria
- `_goals/otel-export-loss-reduction/spawns/15-context.md` — the package
- `billing/otel/receiver.py` via `git diff`
- `billing/otel/otel_store.py` — `dp_key`'s interpolation form (read-only)

## The change

`_common` now reads `"session_id": str(a.get("session.id") or "unknown"),` — the `str()`
wraps the whole expression, so it applies after the `or` fallback.

## Read criterion 1 carefully before evaluating it

**The orchestrator corrected criterion 1 after implementation, because the original was
wrong.** It claimed all five reproduced double-bills would be fixed. Measured, coercion
fixes only **two**:

| wrapper | stored after fix | transcript id | match |
|---|---|---|---|
| `doubleValue 1e20` | `'1e+20'` | `'1e+20'` | yes |
| `boolValue true` | `'True'` | `'True'` | yes |
| `intValue "0123"` | `'123'` | `'0123'` | **no** |
| `intValue "+123"` | `'123'` | `'+123'` | **no** |
| `doubleValue 42.0` | `'42.0'` | `'42'` | **no** |

The three survivors have a different root cause: `_attr_value` does
`int(v["intValue"])`, so `'0123'` is destroyed to `123` in **Python**, before SQLite is
involved. Coercion cannot recover a spelling the parse already discarded.

**Verify this correction is itself correct** — that is the first thing to check. If the
three survivors could in fact be closed by something in this task's fence, say so.

## Verify by execution

1. **Criterion 1** — the two fixed cases exclude correctly, driving real OTLP JSON payloads
   rather than Python-constructed dicts, with `COUNT(*)` over **both** `token_usage` and
   `cost_usage` unchanged.
2. **Criterion 2** — the four already-correct wrappers still work: `stringValue` UUID,
   `stringValue` padded, `intValue "123"`, absent/unknown.
3. **Criterion 3** — `typeof(session_id)` is `'text'` and the stored value equals
   `str(<python value>)` for all nine wrappers.
4. **Criterion 4 — `dp_key` invariance.** This is the criterion that makes the task safe.
   Assert the literal `dp_key` for a `boolValue true` datapoint is the same before and after
   the change, and that re-ingesting the same datapoint twice still yields exactly one row.
   Do not accept the reasoning alone; measure it.
5. **Criterion 5** — an ordinary `stringValue` UUID session's stored value is byte-identical
   to the pre-fix value. The coercion must be a no-op on the real case.
6. **Criterion 6** — the `or` fallback's falsy semantics are unchanged: absent, `0`,
   `false`, `""` all still store `'unknown'`.
7. **Criterion 7** — `user_email={"a":1}` still produces `store_error:ProgrammingError`, and
   the pre-existing test asserting it still passes unmodified.
8. **Criterion 9** — `do_POST`, `_authorized`, `_presented_token`, `_read_body`,
   `_attr_value`, `_attrs`, `ingest_session_repo_payload`,
   `ingest_transcript_usage_payload` and the `/healthz` handler are byte-identical to their
   end-of-task-03 state. The implementer claims it verified this by construction and by
   diffing outside those regions; check it yourself, ideally by extracting each function
   from git and comparing.

## Also confirm

- The **residual comment states BOTH residuals**: (i) the fix is not retroactive for rows
  already stored, and (ii) it closes only the divergences SQLite caused, naming
  `_attr_value`'s parse as the reason three cases survive. A comment that implies the fix is
  complete is a finding — that framing is exactly what this goal has been burned by.
- Coerce, not reject: no OTLP datapoint is dropped.
- No per-type formatting branch was added. The point was to stop two conversions existing,
  not to add a third.
- `otel_store.py`, `transcript.py` and everything under `tests/` untouched by this task.
- Criterion 8: the five-file selection is **8 failed, 166 passed** (orchestrator-measured
  after task 04's fix cycle). A ninth is a finding. Note three of the eight are hook-side
  and owned by task 05.

## Rules

Evaluate only — **no repository writes**. Scratch files in your scratchpad, never `data/`.
Do **not** run the full suite.
Model: claude-opus-5 · tier: frontier.
Keep the report compact — findings over narration.

## Output

```
VERDICT: PASS | PASS (with notes) | NEEDS FIXES | REJECT
MODEL: <model>

## Criterion 1's correction
[Is the orchestrator's corrected claim accurate? Could the three survivors be closed
in-fence?]

## Criteria
[One line per criterion 1-9: MET / NOT MET, "executed" or "read only".]

## Independent reproductions
[Results of items 1-8, with the dp_key values you measured.]

## Residual honesty
[Does the comment state both residuals without implying completeness?]

## Findings
[BLOCKING / NON-BLOCKING, 3 lines max each.]

### Footprint
files_read: <N> (~<C> chars)
```
