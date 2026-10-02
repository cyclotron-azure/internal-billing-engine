You are the implementer subagent. Read: .claude/agents/implementer.md

CURRENT_DATETIME: 2026-10-02T09:00:00-10:00

## Task
EXTRA FIX CYCLE (user-authorized after the 3-cycle limit; the user chose "fix it properly") for task 01
(`_goals/unknown-parent-child-inheritance/01-attribute-inheritance.md`), fresh context.
`billing/otel/attribute.py` (uncommitted; hash bb56eb27449e8d9a41d80879f993068cdbbfea36) implements the
full feature; the evaluator verified every functional AC, strictness, ~35k randomized datapoints,
view-vs-standalone equivalence, perf (absolute limit) and 69 bare-identifier aliases. ONE gap remains:
**quoted-identifier aliases** (`'"x y"'`, `'"order"'`, `'[sp ace]'`, `` '`bt`' ``, `'"t"'`) used to work
in the ORIGINAL module and now raise `OperationalError: near "__i": syntax error`, because the derived
inner names are built by string concatenation `f"{alias}__ar"` / `f"{alias}__i"` (attribute.py `_fmt`,
~lines 116-125), which renders `"x y"__i`. Do NOT redesign; fix this one gap with minimal edits.
Project root: C:\Users\ZaneChing\OneDrive - Cyclotron Inc\projects\internal-billing-engine

## Requirements
1. Derive the inner names (`ar` and `i`) from a SANITISED BARE form of the caller's alias so they are
   always valid unquoted identifiers, whatever the caller's alias looks like: e.g.
   `base = "_" + re.sub(r"[^0-9A-Za-z_]", "_", alias)` then `base + "__ar"` / `base + "__i"`.
   (`re` is stdlib; adding `import re` is allowed ONLY if you need it - alternatively use a
   comprehension/`str.translate`/`isalnum` to avoid a new import. No third-party import.)
   The caller's own alias must still be used verbatim wherever the caller's alias is referenced
   (`{table} {alias}`, `{alias}.session_id`, `{alias}.*`, ...), so quoted/bracketed/backticked
   aliases keep working exactly as in the original.
2. **Collision-proof by construction.** Argue (in the report) why neither inner name can equal the
   caller's alias under SQLite's identifier rules (case-insensitive; a quoted identifier equals the
   same bare name), and why `ar != i`. Hint: the prefix `_` plus the `__ar`/`__i` suffix makes each
   inner name strictly longer than the caller's alias with quotes stripped, if the sanitiser
   replaces (does not drop) characters; verify this holds for your sanitiser, including aliases
   that are SQL string literals (`"'x'"`), have embedded quotes (`'"a""b"'`), are non-ASCII, empty
   after sanitising, start with a digit, or are 200+ chars.
3. Update the `_fmt` docstring so it is TRUE (it currently claims "whatever the caller's alias is").
4. Acceptance: the evaluator's `eval06/alias_chk5.py` must report `problems: 0` AND every QUOTED line
   must show `same` (new == orig == default rows, and the view's `SELECT *` column list == table
   columns + `resolved_repo` + `attribution_source`) for both tables and all three forms
   (bare view, `WITH r AS (...)`, standalone). Extend a check of your own with extra quoted
   aliases: `"x y"`, `"order"`, `[sp ace]`, `` `bt` ``, `"t"`, `"a""b"`, `'lit'` (SQL string-literal
   alias, if SQLite accepts it as an alias; note it if not even the ORIGINAL accepts it), a
   non-ASCII quoted alias, and a quoted alias equal to a would-be inner name (e.g. `"_t__i"` /
   `"t__i"`). If the ORIGINAL module rejects an alias form, the new code is not required to accept it.
5. Re-verify nothing else moved: `alias_chk3.py` (`problems: 0`), `func2.py` 124/124,
   `regress2.py`, `regress2_noties.py`, `regress4.py`, `regress4_nullheavy.py`, `newrisk3.py` sections
   1-4 (same results as the previous cycle: view==standalone 0 diffs, 0 differences vs the
   updated model, `diffs where ORIGINAL was not unknown: 0`), the rung-2 command, and the
   per-process perf check (absolute limit <= 1.0 s per 100k datapoints; edit renames aliases only,
   so expect noise-level change; report export token and bill token at least, on
   `eval06/perf_eval.db`).

## Files to Read
- _goals/unknown-parent-child-inheritance/01-attribute-inheritance.md
- _goals/unknown-parent-child-inheritance/spawns/12-report.md (the evaluator's single remaining issue)
- billing/otel/attribute.py (whole file; the working-tree version to edit)
- scratchpad `eval06/`: alias_chk5.py, alias_chk3.py, alias_chk4_impl.py, func2.py, regress2.py,
  regress2_noties.py, regress4.py, regress4_nullheavy.py, newrisk3.py, perf_drive.py, perf_one.py
- CLAUDE.md

## Write fence
ONLY: `billing/otel/attribute.py` (scratchpad for everything else; scratchpad dir:
C:\Users\ZANECH~1\AppData\Local\Temp\claude\C--Users-ZaneChing-OneDrive---Cyclotron-Inc-projects-internal-billing-engine\efecdfb4-de1b-4a6f-9f68-641f5525f749\scratchpad\)

## Model
requested: claude-fable-5-1 · tier: light role, rotated to a different model line · rotation: extra cycle (user-authorized)

## Rules
- Test ladder rungs 1-2 only. Rung 2 = `python -m pytest tests/test_attribute.py tests/test_bill.py tests/test_invoice.py tests/test_reconcile.py tests/test_export.py tests/test_export_unattributed.py tests/test_integration_desktop.py -q`. NEVER the full suite.
- Stdlib only; no third-party import; no tests/README/consumer edits; no new table/column/index; no
  registered SQLite functions; path text never used as a LIKE/GLOB pattern.
- NEVER run `git checkout`, `git restore`, `git stash` or `git reset` on any repo path: the work is
  uncommitted. FIRST copy the current `billing/otel/attribute.py` to the scratchpad
  (`attribute_v6_bb56eb2.py`). To compare with the original use `scratchpad/attribute_orig.py`.
- Do not commit. Do not touch the VM, deploy/, client-package/.
- If a clean fix is not possible, STOP and report; do not weaken behavior.

## Output
Report: exact edits (before/after snippets), the collision-proof argument, `alias_chk5.py` output
(`problems: 0`, QUOTED lines `same`), your extended quoted-alias check, results of the other scripts,
rung-2 result, perf numbers (export token and bill token at least), `git status --short`, new
`git hash-object billing/otel/attribute.py`, anything you could not do, and a `### Footprint` block
(`files_read: <N> (~<C> chars)`).
