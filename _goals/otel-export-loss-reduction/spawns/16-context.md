Task 04 FIX CYCLE 1 — resumed implementer. CURRENT_DATETIME: 2026-09-16T19:15-04:00

Your task 04 work is good and nearly all of it stands. Parts A and B look right, the
quarantine correctly reuses the existing `withheld` mechanism, `too_recent` is
non-resolving, the two copies are byte-identical, the replay is flag-gated with the flag
written before the first POST, and your Evidence (d) demonstrates exactly the AC3 trap the
task warned about — withheld with `resolved: []` and `examined_mtime: null` on run 1, then
shipping on run 2. That was the single most important requirement and you got it right.

**You were also right to flag the `test_ac7e_forward_only_install_watermark` tension rather
than paper over it.** You correctly identified that a real machine and a synthetic "fresh
install" fixture are indistinguishable by the replay flag alone, and you said you could not
satisfy both that test and Part C as written. That was the correct call, and the spec was
wrong, not your implementation.

## One change: the watermark reset is removed from Part C

**Do not reset `state["install_ts"]`.** The replay now clears exactly **two** things:
`files[*]["resolved"]` and `files[*]["examined_mtime"]`.

Why, measured after your report: `install_ts` is set to *now* on the first run
(`:752-753`), so every transcript written **after** installation already passes the
`:543-545` watermark check. What actually blocked recovery was `resolved` and
`examined_mtime` — not the watermark. So resetting it adds nothing to this goal's target
(post-install sessions whose OTLP export never flushed) and instead unlocks
**pre-installation** history, for `claude-desktop` as well as CLI. That usage was never
captured by OTLP either, because the tool was not installed yet, so billing it now would
expand client invoices retroactively rather than recover lost telemetry. The user decided
to drop it.

This resolves the tension you found rather than trading a test away for it: the
forward-only watermark keeps its original purpose, and
`test_ac7e_forward_only_install_watermark` should now pass **unmodified**.

## What to do

1. Remove the `state["install_ts"] = _REPLAY_INSTALL_TS_FLOOR` assignment (`:776`) and the
   `_REPLAY_INSTALL_TS_FLOOR` constant (`:504`) if nothing else uses it. Leave the
   `:543-545` watermark check and `install_epoch` derivation exactly as they were.
2. Update the Part C comment and the module docstring, which currently say the replay
   resets the watermark. Replace that with the reason it deliberately does **not** — a
   future reader will otherwise "restore" it as an oversight. State that pre-installation
   usage stays unbilled on purpose.
3. Keep everything else in Part C exactly as you built it: the flag, the two cleared
   items, flag-before-POST, permanence, the pre-POST intended-volume log, and the persisted
   tallies.
4. New criterion **04.19** now pins this: a `cli` group whose timestamp predates
   `install_ts` must **not** ship, even on the replay run. Criterion 13 additionally
   asserts `install_ts` is unchanged by the replay, and its fixture now sets `install_ts`
   *earlier* than the fixtures' timestamps (post-install history, which is what the replay
   exists to recover). Task 05 writes those tests — not you.

## Expected test outcome after your change

`tests/test_transcript_hook.py::test_ac7e_forward_only_install_watermark` should pass
again. Your other two breaks stand and are correct — task 05 owns inverting them:
- `:109-122` `test_ac1_only_desktop_entrypoint_ships`
- `:489-503` `test_ac6_running_twice_ships_each_record_once`

**If `ac7e` still fails after removing the reset, stop and report it** — that would mean
something else in your implementation also defeats the watermark, which is a finding.

On the baseline confusion in your report: you were right and my number was stale. I told
you 6 failed / 168 passed, but task 06 was concurrently editing `receiver.py` while you
edited the hook, so neither of you could see a clean baseline. Current ground truth on the
five-file selection is **9 failed, 165 passed**. Expect **8 failed** after your fix.

## Write fence — unchanged

```
client-package/claude-transcript-usage.py
deploy/claude-transcript-usage.py
```

Both copies byte-identical. Nothing under `tests/`, nothing under `billing/`.

## Model

requested: claude-sonnet-5 · tier: light · rotation: cycle 1 (resumed, no rotation)

## Rules

- Minimal diff: remove the reset, remove the now-unused constant, correct the comments.
- Do not touch the `:543-545` watermark check or the `install_epoch` local.
- Keep always-exit-0, the single shipping path, stdlib-only, and byte-identical copies.
- Do not edit any test.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Change
[What you removed, and the corrected comment verbatim.]

## Verification
[`python -m pytest tests/test_transcript_hook.py -q` -> result, and explicitly whether
test_ac7e_forward_only_install_watermark now PASSES.]
[Replay still works: the intended-volume log and tallies for a post-install fixture, plus
a pre-install group confirmed NOT shipped.]
[The two sha256 digests.]

## Anything else the change touched
["None" is valid.]

### Footprint
files_read: <N> (~<C> chars)
```
