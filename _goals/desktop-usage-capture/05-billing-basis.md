# Task 05: Billing basis — honest actual-vs-estimated reporting

## Objective

`bill.py` and `invoice.py` account for rate-derived desktop cost correctly, label it honestly, and warn
when the double-billing guard is breached. Today `bill.py` picks a basis globally: if ANY `cost_usage`
row exists it bills from `cost_usage` and prints "basis: ACTUAL cost from claude_code.cost.usage". With
desktop rows present as `cost_source='rate_card'`, that label would present estimates as
Anthropic-reported actuals on a client invoice.

## Dependencies

- 00 (the pre-change golden baseline), 01 (`cost_source`), 04 (the `desktop-scratch` value)

```yaml
# --- task ownership contract ---
writes:
  - billing/otel/bill.py
  - billing/otel/invoice.py
  - tests/test_bill.py
  - tests/test_invoice.py
reads:
  - billing/otel/attribute.py
  - billing/otel/otel_store.py
  - billing/otel/rating.py
  - tests/conftest.py
  - tests/golden/bill_otlp_baseline.txt
depends_on:
  - "00-test-scaffold"
  - "01-store-schema"
  - "04-attribution"
owner: implementer
rewrite_semantics: targeted-insertion
eval_depth: full
```

## Requirements (exhaustive — the evaluator verifies every item)

**Billing correctness**

- [ ] Desktop usage actually bills. A store with both OTLP cost rows and transcript rate-card rows
      produces a total including both. Desktop usage silently billing zero is the exact failure this
      goal exists to prevent.
- [ ] `bill.py` reports the actual and rate-card portions separately, so a reader sees how much is
      Anthropic-reported and how much is estimated at placeholder rates.
- [ ] **The split lines are emitted CONDITIONALLY — only when rate-card rows exist** — exactly as the
      `desktop-scratch` line is scoped. Unconditional emission would change output for OTLP-only stores
      and break criterion 1's golden byte-match, making the requirement and the criterion unsatisfiable
      together.
- [ ] The basis label is accurate in all three states — only actual, only rate-card, and mixed. A mixed
      store must never be labelled simply "ACTUAL".
- [ ] `--basis rates` keeps its existing meaning: force the rate-card estimate for everything. Note it
      reads only `token_usage` and never `cost_usage`, so it cannot re-rate already-rated rows — confirm
      this holds after the change rather than assuming it.
- [ ] Markup is applied exactly once. Task 02 stores raw pre-markup cost; `bill.py:96` computes
      `rates.billed(...)/markup` for its estimate and applies `base * markup` later. Verify no path
      double-applies it.
- [ ] The ATTRIBUTION SOURCE breakdown includes `desktop-scratch` as its own line when such rows exist.

**The double-billing detector**

- [ ] `bill.py` emits a prominent warning when any `session_id` carries BOTH `usage_source='otlp'` and
      `usage_source='transcript'` token rows. The client-side and server-side filters both test the
      identical predicate (`entrypoint == 'claude-desktop'`), so they are not independent defenses: one
      upstream change — the desktop app gaining an OTLP exporter, or the entrypoint string changing —
      defeats both at once and double-bills a client silently on a live invoice. This detector is the
      only thing that would surface that.
- [ ] The warning names the affected session ids so the condition can be investigated, and does not
      itself alter the billed total — it reports, it does not silently correct.

**Invoice**

- [ ] `invoice.py` distinguishes actual from estimated cost in its rendered `.txt` output, **derived at
      generation time from `cost_usage.cost_source`**. Do NOT add a persisted column for the split —
      task 01 freezes no such column and this task may not modify the schema.
- [ ] **The same distinction reaches `summary.csv` and `line_items.csv`.** `invoice.py` writes these
      beside the `.txt` in the same client-facing `invoices/` directory, and `summary.csv` carries an
      `actual_cost_usd` column. Rate-card estimates landing in a column named "actual" is the exact
      mislabelling this task exists to prevent, and the `.txt` alone does not cover it. `export.py`'s
      lake CSVs remain Out of Scope per `goal.md` — these two are a different pair of files, written by
      the file this task owns.
- [ ] **Pre-existing invoice regeneration semantics are explicitly OUT OF SCOPE and must be left
      exactly as they are.** `invoice.py:83-86` already does `DELETE FROM invoice_line_items` +
      `INSERT OR REPLACE INTO invoices`; regenerating an invoice replaces it in place. Do not "fix" this,
      do not add immutability, and do not be failed for leaving it. It is shipped behavior outside this
      goal.

- [ ] No third-party import is added.

## Acceptance Criteria

1. A store with OTLP cost rows only produces `bill.py` output matching `tests/golden/bill_otlp_baseline.txt`
   captured by task 00 before any change — verification: unit test diffing against the golden file. This
   is the regression gate for the existing fleet.
2. A store with transcript rows only bills a non-zero total and labels the basis as rate-card —
   verification: unit test asserting total and label.
3. A mixed store bills the sum of both and states both portions — verification: unit test asserting
   total, actual portion, and estimated portion.
4. Markup appears exactly once in a transcript row's billed figure — verification: unit test computing
   the expected value independently from `RatingService` and the markup factor.
5. `--basis rates` on a mixed store rate-cards everything without double-counting the transcript rows'
   already-rated cost — verification: unit test. The sharpest correctness trap in the task.
6. `desktop-scratch` appears as its own line in the attribution breakdown when such rows exist —
   verification: unit test on captured output.
7. A session carrying both `otlp` and `transcript` token rows triggers the warning, and a store without
   such a session does not — verification: unit test both ways. A detector that never fires, or that
   fires constantly, is worse than none.
8. A generated invoice's `.txt` distinguishes actual from estimated cost — verification: unit test on the
   rendered output.
8b. `summary.csv` and `line_items.csv` do not report rate-card estimates under a column named as actual
   cost — verification: unit test reading both CSVs from a mixed store and asserting the estimated
   portion is either in its own column or explicitly labelled.
9. Regenerating an invoice behaves exactly as it does today — verification: unit test asserting the
   existing replace-in-place semantics still hold, proving they were not altered.

## Files to Read

- `billing/otel/bill.py` — the `have_cost` basis selection, the `/markup` rate-card derivation at line 96,
  the ATTRIBUTION SOURCE breakdown, and `resolved_view('cost_usage')` at line 57.
- `billing/otel/invoice.py` — invoice/line-item persistence at lines 83-86 (leave as-is), `.txt`
  rendering, and the `summary.csv` / `line_items.csv` writers.
- `billing/otel/attribute.py` — `resolved_view` and the `desktop-scratch` value from task 04.
- `billing/otel/otel_store.py` — the `cost_source` / `usage_source` columns and the `invoices` table shape.
- `billing/otel/rating.py` — placeholder rates; `DEFAULT_RATE` covers `claude-opus-5`.
- `tests/golden/bill_otlp_baseline.txt` and `tests/golden/README.md` — the pre-change baseline.
- `README.md` — "Typical OTEL flow"; the note that rates are placeholders.
- `.claude/skills/test-ladder/SKILL.md`

## Files to Create / Change

- `billing/otel/bill.py` — conditional actual/rate-card split, accurate basis labelling,
  `desktop-scratch` line, overlap detector.
- `billing/otel/invoice.py` — actual-vs-estimated distinction in the `.txt` AND in `summary.csv` /
  `line_items.csv`, derived not persisted.
- `tests/test_bill.py`, `tests/test_invoice.py` — the acceptance criteria above.

## Constraints

- Must: keep `--basis rates` working with its existing meaning.
- Must: apply markup exactly once; task 02 stores raw cost.
- Must: preserve existing output for OTLP-only stores — proven against the task-00 golden baseline.
- Must: derive the actual/estimated split at generation time, not from a new persisted column.
- Must NOT: add a third-party import; modify `attribute.py`, `otel_store.py`, or `export.py`;
  change the placeholder rate card; alter the `unknown` grouping semantics.
- Must NOT: change invoice regeneration semantics — explicitly out of scope.

## Verification

- Targeted test command: `python -m pytest tests/test_bill.py tests/test_invoice.py -v`
