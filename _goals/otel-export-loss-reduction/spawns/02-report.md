CONDENSED STUB (token-constrained session). Full report in transcript.

VERDICT: NEEDS REVISION
MODEL: claude-opus-5

## Part C attack
transcript_key confirmed a genuine, stable replay guard (otel_store.py:226-228, rationale
:184-225; __cost__ sentinel :486). That half of the safety argument holds. Three gaps:

C1 BLOCKING (bill-correctness) -- the exclusion guard reads token_usage only
  (02-store-reads.md:50), but a transcript record inserts into cost_usage too and the cost
  side IS billed: invoice.py:215 cost_basis = actual_cost + estimated_cost, :216 billed =
  cost_basis * markup, :224-225 same for the total. The actual/rate_card split is
  presentational only. receiver.py iterates TOKEN_METRIC (:163) and COST_METRIC (:176) in
  INDEPENDENT branches, so a partial flush can leave OTLP rows in cost_usage and none in
  token_usage -- exactly the loss mode this goal targets. Such a session passes the guard,
  its transcript is accepted, a cost_source='rate_card' row lands beside the existing
  'actual' row, and transcript_key cannot stop it because it and dp_key are DESIGNED never
  to collide (otel_store.py:217-220). Client billed twice. Latent before Part C; Part C
  walks all of history through it unattended.

C2 BLOCKING (silent-no-op) -- Part C recovers nothing. :509-511 `if examined_mtime is not
  None and examined_mtime == current_mtime: ... continue` fires BEFORE the group loop that
  reads resolved at :529. Part C reset only resolved + the watermark. Every historical file
  has examined_mtime set and an unchanged mtime. Criterion 13's fixture did not pin
  examined_mtime, so it would pass against a production no-op.

C3 BLOCKING -- interrupted replay unrecoverable. Flag-before-POST stops double-replay but
  a full-history replay is many MAX_BATCH_SIZE batches and stop_due_to_transport
  (:735-738) ends a run early. Task 04 never said whether the install_ts reset (real key
  at :647-649; install_epoch is a derived local) persists. If restored, a replay dying on
  batch 3 of 80 permanently loses the remainder. Criterion 14 could not tell the difference.

Sub-questions answered: a session that already has transcript rows and is replayed is SAFE
(not excluded, falls through to transcript_key which dedupes exactly, incl. __cost__).
Clearing resolved for desktop loses nothing -- envelope_retries drops (:712-719) get
re-shipped/re-rejected/re-dropped: wasted, not lost.

## New facts verified
invoice.py:215/:216/:224-225 sum actual+rate_card into total_billed. :509-511 precedes
:529. Real state key is install_ts (:647-649). Task 02's guard and last_ingest_at were
both token_usage-only.

## NON-BLOCKING
N4 goal.md said the replay touches "only cli/claude-vscode state -- desktop resolution
   state is untouched" while task 04 clears EVERY resolved list and its safety argument is
   about desktop re-ships. Contradiction, and goal.md's version is unimplementable (flat
   resolved list carries no entrypoint).
N5 05-tests.md rewrite_semantics: whole-file contradicts its own surgical fence on three
   pre-existing test files. State semantics per owned file.
N6 last_ingest_at is also token_usage-only -> a receiver ingesting only cost datapoints
   reports stale on /healthz. Same root cause as C1.

## Criteria
04.13 passes for the wrong reason (examined_mtime). 04.14 one-sided. 04.17 needs the
cost_usage count. 02.8 / 03.10 must extend to cost-only OTLP sessions. Counts re-checked:
7+12+19+18 = 56 correct as of cycle 2.

## Fixes verified as landing, not moving
B3 gate (both halves, cr.1 now holds under both token states); cr.18's division of labour;
task 04's Background section (every citation checked accurate); N6-cycle1 resolved in the
safe direction; 04.3 names both state fields; 05.5 grep-shaped; testability-5 placement
split correct.

## Write sets
Still disjoint. Task 05's three new pre-existing files do not overlap tasks 03/04 (both
still forbid tests/) nor Phase 6 align-docs (markdown surfaces only).

## Devil's advocate
Steelman: Part C should be a two-step -- a dry-run pass reporting what it WOULD ship and
what the server WOULD exclude, human-reviewed, then the real pass. C1/C2/C3 are all
defects a dry-run surfaces for free and that criterion 16's post-hoc tally surfaces only
after the rows are written.
Pre-mortem: replay runs fleet-wide, dedupe_drops spikes as predicted so nobody looks
twice, the tally reads ~zero, and it is read as "the 10s interval already closed the gap"
rather than as C2.

### Footprint
files_read: 9 (~119000) this cycle; 20 (~297000) cumulative / commands_run: 6 this cycle
