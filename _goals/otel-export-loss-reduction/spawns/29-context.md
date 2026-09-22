You are the test-writer subagent. Read: .claude/agents/test-writer.md

CURRENT_DATETIME: 2026-09-21T12:20-04:00

## Task

Two things: fix `tests/COVERAGE_MAP.md`, which Phase 5's cycle-2 audit found regressed
(this goal's own fix cycles reintroduced 4 dead node ids and left 2 new criteria with zero
map rows); and write the regression test for the sixth double-billing path, which just
landed in `billing/otel/receiver.py`.

## Part 1 — `tests/COVERAGE_MAP.md` corrections

Five exact lines, confirmed by grep against the current suite:

**Line 279** — `test_01_ac01_all_four_config_sources_carry_10000_dev_selftest_keeps_5000`
no longer exists. Repoint to
`test_01_ac01_surviving_config_sources_carry_10000_dev_selftest_keeps_5000` and reword the
criterion text from "All four config sources" to "Surviving config sources
(`deploy/managed-settings.json`, `client-package/configure.py`)" — the old text now
describes a write-set that no longer exists.

**Line 280** — `test_01_ac02_managed_settings_and_pilot_settings_carry_string_10000` no
longer exists. Repoint to `test_01_ac02_managed_settings_carries_string_10000` and reword
"managed-settings.json / pilot-package/settings.json" to just "managed-settings.json".

**Line 282** — `test_01_ac04_install_sh_parses_and_emits_valid_json_with_new_value` was
deleted outright; `pilot-package/install.sh` no longer exists and
`client-package/install.sh` never wrote a JSON heredoc, so there is no surviving
equivalent. Mark this row a **GAP** per the file's own stated contract (an unmapped
criterion "is listed as a GAP, not omitted" — check the file's header for its exact GAP
formatting convention and match it). Do not invent a test for a mechanism that no longer
exists anywhere in the codebase.

**Line 366** — `test_06_ac06_falsy_or_absent_session_id_stores_unknown` no longer exists
and the criterion text ("Absent/falsy `session.id` still stores `unknown`") is now
**factually inverted** by the fix — falsy-but-present values no longer store `unknown`.
Split this one row into two, matching the two tests that replaced it:
- `test_06_ac06_present_but_falsy_session_id_keeps_own_spelling` — criterion text:
  "Present-but-falsy `session.id` (0, False, 0.0, '') keeps its own `str()` spelling, not
  `unknown`"
- `test_06_ac11_genuinely_absent_session_id_still_stores_unknown` — criterion text:
  "Genuinely absent `session.id` still stores `unknown` (unchanged)"

**Line 134** — `test_build_contents_includes_transcript_hook` no longer exists; it was
renamed to `test_build_contents_excludes_retired_transcript_hook` (confirmed present).
This one is **pre-existing staleness, not introduced by this goal's work** — but it's in
the file you're fixing, so repoint it while you're here. Judge from the new name whether
the criterion text ("client-package build ... includes transcript hook" or similar) needs
inverting too — the name change ("includes" -> "excludes retired") suggests the assertion
direction flipped; read the test body to confirm before rewording the criterion text.

**Add two new rows** for criteria 06.10 and 06.11 (see `06-otlp-session-id-coercion.md`
for their exact text) citing:
- 06.10 -> `test_06_ac10_falsy_session_id_now_correctly_excludes_matching_cli_record`
- 06.11 -> `test_06_ac11_genuinely_absent_session_id_still_stores_unknown` (same test as
  the line-366 split above — one test can satisfy two citations if that's accurate; check
  whether the existing test already covers both 06.6-repointed and 06.11, or whether you
  need to add a distinct row).

**Before you finish, re-derive the file's own summary counts** (mapped / dead / GAPs /
unreferenced) from what you've actually written, and correct them if they're wrong — that
counting mismatch is exactly the class of error this goal has been burned by twice now
(a self-reported "0 dead ids" that wasn't checked against the actual collected suite).

## Part 2 — the sixth-path regression test

New requirement/criteria: read `06-otlp-session-id-coercion.md`'s most recent section
(search for "Residual (iv)" cross-reference or the merge-clobber description — the
implementer's fix-cycle-3 report describes the exact mechanism if the task file itself
hasn't been amended with a formal criterion yet; if it hasn't, add one — a new criterion
06.12, "the merge-level None-clobber fix", with the same rigor as 06.10/06.11).

Add to `tests/test_receiver_health.py`:

**`test_06_ac12_unparseable_datapoint_wrapper_does_not_clobber_resource_level_session_id`**
— this is the actual proof the bug is fixed, matching the real production data flow (not
a shortcut through `_common` directly with hand-built dicts — go through the real HTTP
ingest path, the same way `test_06_ac10` does):

1. POST an OTLP metrics payload where the **resource** carries a real-looking UUID
   `session.id` (`stringValue`), and the **datapoint** also carries a `session.id`
   attribute, but with an **unrecognized wrapper** — `{"arrayValue": {"values": []}}` is
   the simplest. Assert the stored `token_usage.session_id` is the **resource-level UUID**,
   not `'unknown'`.
2. Post a `cli` transcript record for that same UUID session. Assert it is rejected
   `session_has_otlp`, with `SELECT COUNT(*)` over both `token_usage` and `cost_usage`
   unchanged before vs. after — this is the actual double-billing check, not just the
   stored-value check in step 1 alone.
3. **Prove it would have failed pre-fix.** State in a comment or docstring how you know —
   either point at the fix-cycle-3 report's A/B reproduction (resource UUID + unparseable
   datapoint wrapper -> pre-fix `'unknown'`, post-fix the real UUID), or reason about it
   directly the way `test_06_ac10`'s docstring already does. Do not just assert it passes
   against current code and call it done — that's the exact gap that let the sixth path
   ship undetected through the last audit cycle.
4. Add a fourth wrapper variant test or parametrize — the fix covers `arrayValue`,
   `kvlistValue`, `bytesValue`, and an empty `{}` wrapper; at minimum parametrize over two
   of these to show the fix isn't narrowly patched to one shape.

Also add the **control** the fix-cycle report already ran manually — confirm it as a real
test, not just trust the report: a datapoint that provides its own genuine falsy value
(`intValue "0"`) still correctly overrides the resource level (this is `test_06_ac10`'s
existing setup, so check whether it already proves this or needs a small addition).

## Write fence

```
tests/COVERAGE_MAP.md
tests/test_receiver_health.py
```

Nothing else.

## Model

requested: claude-sonnet-5 · tier: light · rotation: n/a

## Rules

- Do not weaken an assertion to make it pass.
- Every store/fixture `tmp_path`-scoped; no live network.
- Run the **full suite** at the end, not a subset. Report the count.
- Re-verify every node id you write or leave in the map actually collects — do not trust a
  name you typed; grep the suite for it after writing.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Coverage map fixes
[Each of the 6 corrected/added rows, verbatim final text. The re-derived summary counts.]

## Sixth-path regression test
[The test(s), and your proof that they'd have failed pre-fix -- be specific, not just
"logically it should have."]

## Verification
[Full suite -> result. Must be green.]
[A fresh COVERAGE_MAP self-check: mapped count, dead ids (should be 0 introduced by this
goal -- note if the pre-existing one at line 134 is now also fixed), unreferenced tests.]

## Anything else touched
["None" is valid.]

### Footprint
files_read: <N> (~<C> chars)
```
