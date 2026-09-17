Phase 3 cycle 2 — RESUMED evaluator (same agent, delta prompt per the resume policy).
CURRENT_DATETIME: 2026-09-16T14:55-04:00

Your cycle-1 verdict was NEEDS REVISION. Every finding was accepted; none was argued with.
Re-read the five files and give a fresh verdict. Below is what changed and nothing else.

## Applied — blocking

**B1 (test lock-in).** Resolved by authorizing the inversion rather than forbidding it.
`05-tests.md` now owns a surgical write fence on `tests/test_transcript.py`,
`tests/test_receiver.py`, `tests/test_integration_desktop.py` — **only the four hunks you
identified, by file:line** — with a rule that each must keep `invalid_entrypoint` coverage
alive on a genuinely out-of-set entrypoint (`claude-web`). Tasks 03 and 04 are now each
required to *list every pre-existing test they break, with file:line*, and task 05
cross-checks its four against those lists; a break outside the four is a finding, not a
test to fix. goal.md gained a matching success criterion and its "full suite green" line
now demands the delta be accounted for explicitly.

**B2 (`too_recent` permanently lost).** Fixed two ways, both in `04-sweeper-cli-backfill.md`.
(1) The client window is now `BACKFILL_MIN_AGE_SECONDS = 1800`, deliberately twice the
server's 900s, so the server boundary is unreachable in practice — with your `:689-692`
citation in the comment as the reason. (2) `too_recent` is explicitly **non-resolving** on
the `outcome == "ok"` path, while `session_has_otlp` and `invalid_entrypoint` stay
resolving because they are permanent verdicts. New criterion 12 pins both halves in one
test. goal.md gained a success criterion.

**B3 (open-receiver detail leak).** `03-...md` now mandates the gate
`AUTH_TOKEN and self._authorized()`, both halves, with your `receiver.py:415` citation and
an explicit statement that on an open receiver detail is *never* served — intended, not a
gap. goal.md's `/healthz` success criterion says the same. Criterion 1 is to be tested
under **both** token states, pointed at the `no_auth` / `with_auth` fixtures at
`test_receiver.py:86-94`.

## Applied — non-blocking and criteria

- **N4** goal.md now cites `_common()` (:133-149), lists the real attribute set including
  `repo` and `timeUnixNano`, adds the `otel_store.py:395-408` corroboration, and states the
  claim's scope precisely: this repo proves `request_id` is *not readable and not
  persistable today*, **not** that Claude Code never emits one — with an instruction to
  revisit if one is ever confirmed on the wire. `05-tests.md` cites `_ExecuteSpy` at
  `tests/test_dedupe_counter.py:57` (not `test_reconcile.py`) and `_FakeClock` at `:80`.
- **N5** `04-...md` gained a "Background — the state file, exactly as it works today"
  section naming `resolved`, `examined_mtime`, `_mark_resolved`, the `:528-529` skip,
  `install_epoch` at `:543-545`, the trailing-group withhold at `:137`/`:547-551`/
  `:739-744`, resolve-on-200 at `:689-700`, and `transport_fail` at `:735-738`. The
  quarantine is now required to **reuse** the existing `withheld` mechanism, not invent a
  parallel one.
- **N6** resolved in the safe direction: an out-of-set or missing entrypoint **is** marked
  resolved (permanent, as today); only the quarantine skip leaves state unadvanced. Both
  are now separate criteria (5, 6) that assert the `resolved` membership.
- **02.11** rewritten. `PRAGMA data_version` and file size are explicitly **banned**, with
  your 8192->8192 / 1->1 demonstration recorded as the reason. Now requires an
  `_ExecuteSpy` write-verb assertion **and** a full-file SHA-256 after commit and close.
- **03.10** now counts both `token_usage` and `cost_usage`.
- **04.3** now names the mechanism — asserts `resolved` membership and `examined_mtime`
  by name.
- **05.5** replaced by grep-shaped criteria (now 5 and 7).
- **Testability 5** `03-...md` now splits placement: the constant and the two reason
  strings live in `transcript.py` (pure data), the age **comparison** lives in
  `receiver.py`, with `README.md:150`'s purity contract cited as the reason.
- **04->03 dependency** now carries your rationale explicitly as a "why this ordering is
  load-bearing" note.

## Applied — the scope gaps (S1/S2), which changed the goal

Your S1 was put to the user with your steelman ("ship 01 + /healthz, measure a week")
offered as one of three options. **The user chose to add a one-time historical replay.**
`04-...md` is now `eval_depth: full` and has a Part C:

- Gated on a state flag, written **atomically before the first POST** so a mid-replay crash
  cannot replay twice.
- The replay clears every `files[*]["resolved"]` list and resets the `install_epoch`
  watermark, for one pass only.
- Safety argument, which is the thing to attack hardest: re-shipped **desktop** records are
  dropped at the store by `transcript_key`, which exists as a replay guard by design;
  re-shipped **CLI** records are additionally gated by task 03's session-level exclusion.
  So the replay can only ever *add* rows for entirely-lost sessions. Worst case is one
  wasted re-POST of history.
- Exactly **one** shipping path — the replay is a state reset, not a second code path, so
  it still respects the quarantine and the entrypoint filter (criterion 15).
- **S2 answered:** recovery is now measurable. Criterion 16 requires records-shipped and
  rejected-by-reason tallies persisted in state, asserted against a known fixture, plus a
  flag that the replay occurred. A zero-recovery replay is a visible result.
- Accepted side effect, stated in goal.md's Out of Scope and task 04's docstring
  requirement: the replay will spike the previous goal's `dedupe_drops` counter and show a
  one-day cliff in `reconcile --detail`. The replay date is recorded so it can be
  attributed.

Criterion counts are now 7 + 12 + 19 + 18 = **56**, reflected in `05-tests.md` criterion 6.
Its mutation list grew to five, adding (d) make `too_recent` resolving and (e) move the
replay flag write to after the first POST.

## What I need from you now

1. **Attack Part C specifically.** It is new, it is the riskiest thing in the goal, and it
   did not exist when you last looked. Is the `transcript_key` + session-exclusion safety
   argument actually sufficient, or is there a path where the replay bills something twice?
   Consider in particular: cost rows; the `__cost__` sentinel; a session that has
   transcript rows already *and* is replayed; and whether clearing `resolved` for
   **desktop** groups can lose anything rather than merely waste a POST.
2. Confirm each applied fix above actually lands the finding, rather than moving it.
3. Whether the new write fence on three pre-existing test files creates any overlap with
   tasks 03/04 (both are forbidden from touching `tests/`) or with Phase 6 `align-docs`.
4. Any **new** defect introduced by these revisions. Revisions are where defects get
   introduced — the previous goal's cycle 2 found that a cycle-1 fix had created a
   contradiction.
5. Re-check criterion counts and the 56 total.

Do not re-report cycle-1 findings that are listed as applied above unless the fix is
wrong. Same rules as before: evaluate only, no repository writes, no full-suite run.

## Output

Same format as cycle 1, plus a leading `## Part C` section holding your attack on the
replay. Verdict line first.
