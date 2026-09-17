CONDENSED STUB (token-constrained session; full report in transcript). Verbatim policy
waived by the orchestrator as in the previous goal from spawn 08 onward.

VERDICT: NEEDS REVISION
MODEL: claude-opus-5

## Source facts
All 7 CONFIRMED except: (a) goal.md cites `_ctx()`, the real extractor is `_common()` at
receiver.py:133-149; (b) "no request id in the payload" is confirmed only as "not readable
/ not persistable today" -- otel_store.py:395-408 RAISES if request_id is passed with
usage_source='otlp'. Repo cannot prove Claude Code never emits one.
Baseline re-verified independently: 331 collected, 98 passed on the 3 touched files.

## Double-billing guard
No double-billing hole. All residuals fail in the under-bill direction. Exporter has no
disk spool, so a lost export never arrives late; transport_fail never advances state.
900s defensible; only competing gate is IDLE_THRESHOLD_SECONDS=30.0.

## Write sets & dependencies
Disjoint, verified pairwise. Only two sweeper copies exist (sha256 identical). All
depends_on real; 04->03 load-bearing for an unstated reason (ordering inversion would
burn every CLI record permanently via the resolve-on-200 path).

## BLOCKING
B1 four pre-existing tests pin cli/claude-vscode as rejected -> task 03 cr.18 + both
   no-edit rules + "331 green" mutually unsatisfiable. Authorize task 05 to rewrite them.
B2 server-side too_recent is permanently lost (resolve-on-200 at :689-700). New silent
   loss path in a loss-reduction goal. No criterion covers it.
B3 _authorized() returns True when AUTH_TOKEN unset (receiver.py:415) -> /healthz leaks
   detail to any prober on the documented open posture; cr.1 fails under the no_auth
   fixture. Gate detail on AUTH_TOKEN and self._authorized().

## NON-BLOCKING
N4 stale citations: _ctx->_common; _ExecuteSpy is at test_dedupe_counter.py:57 NOT
   test_reconcile.py; _FakeClock at :80 (cite it for the freeze-time requirement).
N5 task 04 under-specifies state mechanism: name withheld / examined_mtime /
   _mark_resolved, and the existing trailing-group withhold it must coexist with.
N6 task 04 self-contradicts: req.5 says entrypoint-skip behaves "as today" (= marked
   resolved), req.7 says entrypoint-skipped must NOT be marked processed. Pick one.

## Criteria defects
02.11 TAUTOLOGICAL -- demonstrated: PRAGMA data_version and file size are both unchanged
   across a same-connection INSERT+commit (8192->8192, 1->1).
03.10 add cost_usage to the count assertion. 05.5 is not a command. 04.3 ambiguous about
   its unit (state file has no session unit).
Sound: 02.6/02.7 arithmetic checked; 05.4 (7+12+19+12=50).

## Testability
transcript.py has NO clock and README.md:150 documents it as pure/no-I/O -- the quarantine
comparison cannot live there. Task 03 must place it in receiver.py.

## Scope gaps
S1 Backfill recovers almost no on-disk history: install_epoch watermark (:543-545) plus
   every CLI request_id already _mark_resolved'd by today's filter (:537-539) and resolved
   ids skipped forever (:529). Future sessions only.
S2 Tasks 01 and 04 partially cancel; no criterion quantifies expected recovery, so
   shipping a zero-recovery backfill would be undetectable.
Ruling on the request_id substitution: JUSTIFIED and goal.md is honest about it.

## Devil's advocate
Steelman: ship 01 + /healthz alone, measure a week, then decide on backfill.
Pre-mortem: interval cut lands, coverage ~90%, backfill recovers near-zero, nobody
notices because nothing measures recovered rows.

### Footprint
files_read: 14 (~178000 chars) / commands_run: 12
