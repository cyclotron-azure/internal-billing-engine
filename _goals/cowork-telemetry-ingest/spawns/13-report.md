Fix cycle 2 for task 02 (fresh spawn, claude-fable-5-1 per rotation policy). All 3 issues
addressed:

A [blocker] sorted(metrics_seen) crash on mixed-type names: fixed by skipping non-string
names entirely (not str()-coercing) so a metric literally named "5" stays distinguishable
from malformed int name 5. Tests for cowork path, rejected-service path, and mixed-set-in-one-
payload (the exact sorted() crash shape).
B [major] string row fields could end up list/dict/oversized-int: fixed at row-construction
time (approach b) -- scalars (str/int/float/bool) are str()-coerced matching receiver.py's
_common; non-scalars (list/dict) reject the datapoint as malformed_datapoint:<field> rather
than being silently stringified into garbage. Tests call real CoworkStore inserts for every
affected field.
C [major] float-formatted numeric strings losing precision: fixed by rejecting outright
(approach a) -- only [+-]?[0-9]+ accepted for integer fields; extended same reasoning to
whole-valued floats above 2**53 (already lossy on the wire). Tests cover both string and float
forms, plus the boundary at 2**53.

Verification: 149 passed (test_cowork_ingest.py alone, 54 pre-existing + 95 new), 618 passed
(full suite). Mutation-verified: removing each fix's guard causes the corresponding new tests
to fail (9/54/8 failures respectively when each fix reverted). git diff on receiver.py/
transcript.py empty; cowork_store.py untouched (read-only, confirmed by no Edit/Write issued
against it -- it's still untracked so git diff is vacuous for it).

Full report with exact line numbers and judgment-call reasoning in the completion notification
for agentId a0a4fcfc84bfddc66.
