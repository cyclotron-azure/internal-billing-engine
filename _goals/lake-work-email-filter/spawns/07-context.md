Fix cycle 1 for task 03 (README), resuming implementer a2b820f3121f7c302. Write fence: README.md only.
Fixes required (evaluator, spawns/06-report.md):
1. README ~426-429 ("Collision correction ... Totals now match invoice.py"): qualify — totals match invoice.py for exported (allowed-domain and `unknown`) usage; since the work-domain filter, lake totals are lower than invoice.py by the excluded personal-domain usage.
2. README ~430-432 (your new bullet): add invoice.py to the local figures that do not change, and state the expected lake-vs-invoice.py gap.
3. README ~712-714 (Harden step 4): change the assertion to compare Fabric totals with invoice.py totals restricted to allowed-domain and `unknown` users (or state that per-month totals should differ by exactly the excluded personal-domain usage).
4. Minor: ~348-349 also mention whitespace-only and literal `unknown` (any case) user values are kept.
Also grep README (and only README) for any other statement asserting lake/Fabric totals equal invoice.py/bill.py/otel.db totals and fix those too. Surgical edits; report line refs and a Footprint block.
