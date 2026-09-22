You are the implementer subagent, executing a Phase 6 fix cycle per
`.claude/skills/align-docs/SKILL.md`. Read that skill file first.

CURRENT_DATETIME: 2026-09-21T16:00-04:00

## Critical context — read this before touching anything

An earlier pass in this fix series told `client-package/INSTRUCTIONS.md` and
`client-package/ADMIN.md` that this package's transcript-recovery hook covers desktop,
CLI, and VS Code usage. **That is now wrong, and needs to be reversed, not extended
further.**

Read `client-package/configure.py` yourself, specifically the comment block above
`HOOK_EVENTS_BY_FILE` (~lines 52-73) and the `RETIRED_HOOK_FILES` tuple (~line 87). It
records a measured finding: a desktop session configured via this installer's own
`~/.claude/settings.json` write **does** export OTLP (contrary to earlier belief), and a
real session (`f315633b`) arrived twice — once via `otlp`, once via `transcript` — and
was flagged by `bill.py`'s double-billing detector. As a result,
`claude-transcript-usage.py` is **deliberately not shipped** by this package at all:
confirm in `client-package/build.py`'s `PACKAGE_FILES` (~line 57-60) that it's absent,
and in `configure.py` that install actively removes it from machines that have it
(`RETIRED_HOOK_FILES`).

The hook still exists in the repo and is still shipped by the **separate, MDM-managed
track** (`deploy/managed-settings.json` registers it — you don't need to verify this
yourself, it's confirmed elsewhere in this goal's record, but you may if you want).
**The user's explicit decision, just made:** document `client-package` as not including
this capability (MDM-only for now), and do not investigate or change whether the MDM
track has the same risk — that's out of scope for this fix.

## Fix 1 — reverse the false hook-install claims

**`client-package/ADMIN.md:38`**, the table row:
```
| `claude-transcript-usage.py` | The transcript-recovery hook that gets installed (desktop, CLI, VS Code) |
```
This is false — the file isn't installed by this package at all. Either remove the row
entirely (since it's not part of "what's in the package"), or change it to state plainly
that this file is **not** shipped here, with a one-clause pointer to why (measured
double-bill risk under this installer's own OTLP config) and where it does ship
(the MDM-managed track). Your call on removal vs. explicit non-inclusion note — pick
whichever fits this table's existing style better; explain your choice in your report.

**`client-package/INSTRUCTIONS.md`** — an earlier pass added text implying this package
recovers CLI/VS-Code usage (search for "transcript-recovery hook" and "CLI and VS Code
sessions" — you added/found these in a prior fix). Read the surrounding paragraphs in
full. Remove or correct every claim that this package's install includes CLI/VS-Code (or
desktop) transcript recovery. If the doc needs to say anything about it at all, one brief
sentence is enough: this package does not include transcript-based usage recovery
(removed 2026-09-10 after a measured double-billing risk); that capability is available
only through the org's MDM-managed rollout, not this opt-in install.

Read every remaining sentence in both files that mentions "desktop-usage hook",
"transcript-recovery hook", or `claude-transcript-usage.py` and confirm none of them still
imply it gets installed by this package. List everything you found and fixed.

## Fix 2 — three independent staleness items in `client-package/ADMIN.md`

- **Line ~176-178**: "The MDM/enforced path is `deploy/managed-settings.json` plus
  `deploy/claude-wrapper.sh`, and per README Phase 4.3 those two must ship *together*."
  Read `README.md` yourself around its "Four artifacts" section (search for "Four
  artifacts, not two") — it now documents **four** required artifacts, not two, and the
  phase numbering has moved. Correct this sentence to match what `README.md` actually
  says now (read it, don't guess the new phase number — find it).
- **Line ~139, ~141**: source citations pointing at the wrong lines.
  `receiver.py:290` for `HTTPServer` — read `billing/otel/receiver.py` yourself; the
  import is near the top and the actual `HTTPServer(...)` construction is much later
  (search for `HTTPServer((host, port)`). `otel_store.py:146` for `sqlite3.connect(path)`
  — read `billing/otel/otel_store.py`; line 146 is inside an unrelated `CREATE TABLE`
  string, the real connect call is elsewhere (search for `sqlite3.connect(`). Fix both
  citations to the real line numbers you find by reading.
- **Line ~126**: citations `receiver.py:243` and `:280` for "authorizes before reading
  the body" and "unknown paths acked" — read the file; these numbers currently land
  inside an unrelated comment block. Find the real `do_POST` authorization check and the
  real unknown-path handling and cite those lines instead.

## Fix 3 — `client-package/ADMIN.md:39`, stale VERSION

Currently says "(currently `1.2.1`)". Read `client-package/VERSION` — it says `1.3.0`.
Fix the parenthetical to match.

## Write fence

```
client-package/INSTRUCTIONS.md
client-package/ADMIN.md
```

Nothing else.

## Rules

- Read every cited line yourself before writing a claim or a citation — this exact file
  has now had two rounds of citations pointing at the wrong line. Verify, don't copy.
- Preserve accurate content; this is corrective editing, not a rewrite.
- Do not speculate about whether MDM has the same double-billing risk — out of scope,
  per explicit user decision.

## Output — terse

```
MODEL: <model>
STATUS: completed | blocked

## Fix 1 (verbatim: ADMIN.md row before/after, and every INSTRUCTIONS.md spot
before/after)

## Fix 2 (verbatim: all three corrections, with the real line numbers you found)

## Fix 3 (verbatim, before/after)

## Sweep confirmation
[Every remaining mention of the hook/transcript-recovery in both files, and whether
each is now accurate.]

### Footprint
files_read: <N> (~<C> chars)
```
