**Model (self-reported)**: claude-fable-5-1
## Task Complete: Task 01 extra fix cycle — quoted-identifier aliases in `_fmt`

### Requirements checklist
- [x] Req 1 — inner names derived from a sanitised bare form of the alias; caller's alias used verbatim everywhere else — `billing/otel/attribute.py` `_fmt` (lines ~117-135); proven by `alias_chk5.py` QUOTED lines all `same` and `alias_chk6_quoted.py` 19 quoted aliases x 2 tables x 4 forms, problems: 0. No new import (`isascii()/isalnum()` comprehension; module imports remain only `from __future__ import annotations`).
- [x] Req 2 — collision-proof argument below; mechanically verified by the sanitiser section of `alias_chk6_quoted.py` (`sanitiser violations: 0`) over 28 aliases including `"a""b"`, `"'x'"`, `'lit'`, non-ASCII, `""`, `"1x"`, 250-char, `"_t__i"`, `"t__i"`, `"_t__ar"`, `"__i"`.
- [x] Req 3 — `_fmt` docstring rewritten to describe the sanitised derivation and the length argument; the three stale comments/docstrings that said `{alias}__ar` / `{alias}__i` (module comment above `_AS_OF`, `_inherit_table` docstring, `resolved_repo` docstring, `resolved_view` inline comment) updated to match.
- [x] Req 4 — `alias_chk5.py`: `problems: 0`, all 5 QUOTED lines `same` for new and orig. Extended check `eval06/alias_chk6_quoted.py` (new, scratchpad): all 19 quoted aliases OK in bare view, CTE, standalone, and column list, for both tables.
- [x] Req 5 — `alias_chk3.py` problems: 0; `func2.py` 124/124, 0 view-vs-standalone disagreements; `regress2.py` 0/0/23 vs orig, 0 vs model, attribution_source mismatches {}, view!=standalone 0, row-count mismatches none; `regress2_noties.py` 0/0, model 0, view 0; `regress4.py` 0/0/23, model 0, view 0; `regress4_nullheavy.py` 12,460 datapoints, 18 vs orig (all inheritances), model 0, view 0; `newrisk3.py` sections 1-4 identical to the previous cycle (3 SAME, cols == table+2 for both tables incl. CTE, 150/150/150, order-independent, 12/12 consumers identical); rung 2 `136 passed in 12.49s`; perf within the absolute limit (below).

### Files changed
- `C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine\billing\otel\attribute.py` — `_fmt` only (plus four comment/docstring lines). 23 insertions, 12 deletions vs the backup `scratchpad\attribute_v6_bb56eb2.py`. No SQL template, function body, signature or behaviour outside `_fmt` changed.

### Exact edit (code)
Before:
```python
    return {"tl": TIMELINE_TABLE, "a": alias, "ar": f"{alias}__ar",
            "i": f"{alias}__i"}
```
After:
```python
    base = "_" + "".join(c if (c.isascii() and c.isalnum()) or c == "_"
                         else "_" for c in alias)
    return {"tl": TIMELINE_TABLE, "a": alias, "ar": base + "__ar",
            "i": base + "__i"}
```
`_fmt` docstring now states: caller's alias used verbatim for `{a}`; `ar`/`i` are `_` + alias with every char outside `[0-9A-Za-z_]` REPLACED by `_` + `__ar`/`__i`; always valid unquoted identifiers; strictly longer than the dequoted caller name so never equal; `ar != i` by suffix. Comment edits: module comment above `_AS_OF` ("`_<alias>__ar` ... bare, quoted, bracketed, backticked"), `_inherit_table` docstring ("`_<sanitised alias>__i`"), `resolved_repo` docstring ("The `_fmt(alias)['i']` lookup"), `resolved_view` comment ("`{i}.v` is NULL only when...").

### Collision-proof argument
Let A be the Python string the caller passes and Q the identifier name SQLite reads from it (A itself if bare; A with the delimiters stripped and doubled quotes collapsed if `"…"`, `[…]`, `` `…` `` or `'…'`). Always `len(Q) <= len(A)` (stripping only removes characters). The sanitiser maps each character of A to exactly one character, so `len(S) == len(A)`. Hence `len(_ + S + __i) = len(A) + 4 > len(Q)` and `len(_ + S + __ar) = len(A) + 5 > len(Q)`. SQLite identifier equality is case-insensitive string equality on the dequoted names; two names of different length are never equal regardless of case or quoting. So neither inner name can equal the caller's alias for ANY A: bare, quoted (`"t"`, `"_t__i"`, `"t__i"`, `"_t__ar"`), with embedded quotes (`"a""b"`: Q has 3 chars, inner has 10/11), string-literal aliases (`'lit'`, `"'x'"`), non-ASCII (each non-ASCII char becomes one `_`, length preserved), empty (`""` -> Q is empty, inner is `___i`/`___ar`), digit-leading (`"1x"` -> `_1x__i`, valid because of the `_` prefix), or 250+ chars (SQLite has no identifier length limit short of the SQL length limit). `ar` and `i` share the prefix `_S` and differ only in the suffix `__ar` vs `__i`, so `ar != i` under case-insensitive comparison. Both inner names consist only of `[0-9A-Za-z_]` and start with `_`, so they are always valid bare identifiers and can never be a reserved keyword (SQLite keywords never start with `_`). The caller-visible `{alias}.*` in `resolved_view` therefore never expands over `rid`/`v`, which the column-list checks confirm.

### Verification
- `python alias_chk5.py` → `QUOTED new/orig` x5: all `same`; `aliases tried: 69 x2 tables x3 forms + cols; problems: 0`
- `python alias_chk6_quoted.py` (new) → 19 quoted aliases (`"x y"`, `"order"`, `[sp ace]`, `` `bt` ``, `"t"`, `"a""b"`, `'lit'`, `"ÄÖü ß"`, `"_t__i"`, `"t__i"`, `"_t__ar"`, `"__i"`, `"1x"`, 250-char quoted, `"%_["`, `"'x'"`, `[a]`, `"_"`, `""`) x 2 tables x (view, cte, standalone, cols): every line `orig=same new=same`; `problems: 0 sanitiser violations: 0`. Note: SQLite accepts `'lit'` (string literal) and `""` as aliases in both the ORIGINAL and the new module; nothing was rejected by the original that the new code rejects.
- `python alias_chk3.py` → `aliases tried: 30 x2 tables x3 forms + cols; problems: 0`
- `python func2.py` → `functional OK: 124 / 124`, `view-vs-standalone disagreements: 0 []`
- `python regress2.py` → noun 0/0, noqual 0/0, mixed new!=orig=23 new!=reference=0; attribution_source mismatches {}; view!=standalone 0 all modes; row-count mismatches []
- `python regress2_noties.py` → 0/0 both modes, model 0, view 0
- `python regress4.py` → same as regress2 (0/0/23, model 0, view 0)
- `python regress4_nullheavy.py` → 12,460 datapoints, new!=orig=18, new!=reference=0, view 0
- `python newrisk3.py` → §1 3x SAME; §2 cols == table+2 True / CTE True both tables; §3 150/150/150, view==standalone True, 0 diffs vs orig, insertion-order identical; §4 12/12 identical
- rung 2: `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_invoice.py tests/test_reconcile.py tests/test_export.py tests/test_export_unattributed.py tests/test_integration_desktop.py -q` → `136 passed in 12.49s`
- `python perf_drive.py perf_eval.db 2` (own process per statement/version, median of 3, two rounds; new s per 100k): export_scan_token orig 0.804/0.826 new 1.073/0.479 → **0.828 / 0.369**; bill_token orig 0.211/0.136 new 0.334/0.288 → **0.258 / 0.222**; export_scan_cost 0.318/0.308; bill_cost 0.213/0.231; bill_source 0.258/0.241; reconcile_totals 0.248/0.254; reconcile_daily 0.273/0.265. All <= 1.0 s per 100k (absolute limit). Numbers are lower than the evaluator's previous run (0.869/0.613) — machine was less loaded; the edit only renames aliases, so the change is noise.
- `git status --short` → ` M billing/otel/attribute.py` and `?? _goals/unknown-parent-child-inheritance/` only
- `git hash-object billing/otel/attribute.py` → `38d2db20fe79911ed9c9c6e49f714958ee527021` (was bb56eb27449e8d9a41d80879f993068cdbbfea36; backup at `scratchpad\attribute_v6_bb56eb2.py`)
- Import check → module imports: `['annotations']` only (no `re`, no third-party)
- No git checkout/restore/stash/reset used; no commit; nothing outside `billing/otel/attribute.py` in the repo touched.

### Notes for the evaluator
- Chose the comprehension over `re.sub` to avoid adding an import; semantics identical to `re.sub(r"[^0-9A-Za-z_]", "_", alias)` (non-ASCII letters are replaced, not kept, which keeps the inner names pure ASCII bare identifiers).
- `'lit'` and `""` are accepted as aliases by SQLite in both original and new, so they are in the extended check as positive cases rather than noted as rejected.
- perf_drive's `rows` column differs between orig and new (e.g. 28016 vs 28014) because inherited datapoints collapse into real-repo groups; same as previous cycles.
- Nothing left undone.

### Footprint
files_read: 7 (~56,000 chars): 13-context.md, 12-report.md, 01-attribute-inheritance.md, attribute.py, alias_chk5.py, perf_drive.py, perf_one.py (CLAUDE.md via system context)
commands_run: 5 (plus 1 new scratch file `eval06/alias_chk6_quoted.py`)
