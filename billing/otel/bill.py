"""Aggregate OTEL-attributed usage into a per-repo bill.

Usage bills to the repo it was done in (the short repo name); an optional
override map can rename or group repos (see billing.otel.repos).

Bills on Claude Code's own reported cost (`claude_code.cost.usage`) — the
actual USD Anthropic charges — marked up. The rate-card estimate (RatingService
on token counts) is shown alongside as a cross-check. Usage from sessions with
no git remote lands in the `unknown` bucket and is called out (unattributable).

If no cost data has been captured yet (token-only store), it falls back to the
rate-card as the billing basis and says so.

    python -m billing.otel.bill                 # bill on actual cost x markup
    python -m billing.otel.bill --basis rates    # force rate-card basis
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from .attribute import resolved_view
from .normalize import normalize_model, repo_name
from .otel_store import OtelStore
from .rating import RatingService

UNATTRIBUTED = "unknown"  # sessions with no git remote -> not tied to a repo


def ftok(n) -> str:
    n = n or 0
    if n >= 1_000_000_000:
        return f"{n/1e9:.2f}B"
    if n >= 1_000_000:
        return f"{n/1e6:.1f}M"
    if n >= 1_000:
        return f"{n/1e3:.1f}K"
    return str(n)


def rule(ch="-", n=68):
    print(ch * n)


def run(db: str | None = None, markup: float = 1.50, basis: str = "actual"):
    store = OtelStore(db) if db else OtelStore()
    rates = RatingService(markup=markup)
    mapping = store.get_mapping()
    name_of = lambda repo: mapping.get(repo) or repo_name(repo)

    # Repo is RESOLVED per datapoint against the session->repo timeline, so a
    # session that moved between repos splits across them instead of billing
    # entirely to wherever it launched. Falls back to the wrapper's launch-time
    # tag when no timeline exists. See billing.otel.attribute.
    #
    # cost_source is carried through so actual (OTLP claude_code.cost.usage)
    # and rate-card (desktop transcript, task 02/04) rows can be billed
    # together but reported/labelled separately -- see the split below.
    cost_rows = store.db.execute(
        f"WITH r AS ({resolved_view('cost_usage')}) "
        "SELECT resolved_repo AS repo, model, cost_source, SUM(cost_usd) c FROM r "
        "GROUP BY resolved_repo, model, cost_source").fetchall()
    actual_rows = [r for r in cost_rows if r["cost_source"] == "actual"]
    desktop_rc_rows = [r for r in cost_rows if r["cost_source"] == "rate_card"]
    # have_cost = real Anthropic-reported actual cost exists, NOT merely "some
    # row exists in cost_usage" -- a desktop/transcript-only store also has
    # cost_usage rows (cost_source='rate_card'), and those must NOT flip this
    # to True or the basis label below would print "ACTUAL" over an estimate.
    have_cost = bool(actual_rows)
    has_desktop_rc = bool(desktop_rc_rows)

    # Rate-card estimate per repo x model (from token counts).
    token_rows = store.db.execute(
        f"WITH r AS ({resolved_view('token_usage')}) "
        "SELECT resolved_repo AS repo, model, token_type, SUM(tokens) tok FROM r "
        "GROUP BY resolved_repo, model, token_type").fetchall()

    # How much of the bill each signal is carrying, and which sessions moved.
    source_rows = store.db.execute(
        f"WITH r AS ({resolved_view('token_usage')}) "
        "SELECT attribution_source, SUM(tokens) tok FROM r "
        "GROUP BY attribution_source ORDER BY tok DESC").fetchall()
    multi_repo = store.multi_repo_sessions()

    # Double-billing guard: a session_id carrying BOTH otlp and transcript
    # usage_source token rows means the client-side (wrapper) and server-side
    # (desktop-entrypoint) filters both failed on the same session -- see
    # module note in the task doc. This only REPORTS; it must never change
    # what gets summed into any *_by_name total above/below.
    overlap_sessions = [
        r["session_id"] for r in store.db.execute(
            "SELECT session_id FROM token_usage GROUP BY session_id "
            "HAVING SUM(usage_source = 'otlp') > 0 "
            "AND SUM(usage_source = 'transcript') > 0"
        ).fetchall()
    ]

    if basis == "actual" and not have_cost:
        basis = "rates"

    actual_by_name = defaultdict(float)
    actual_by_name_model = defaultdict(lambda: defaultdict(float))
    desktop_rc_by_name = defaultdict(float)
    desktop_rc_by_name_model = defaultdict(lambda: defaultdict(float))
    ratecard_by_name = defaultdict(float)
    ratecard_by_name_model = defaultdict(lambda: defaultdict(float))
    tokens_by_name = defaultdict(int)
    repos_by_name = defaultdict(set)
    unattributed = set()

    for r in actual_rows:
        nm = name_of(r["repo"])
        actual_by_name[nm] += r["c"] or 0
        actual_by_name_model[nm][normalize_model(r["model"])] += r["c"] or 0
        repos_by_name[nm].add(r["repo"])
        if r["repo"] == UNATTRIBUTED:
            unattributed.add(r["repo"])

    # Desktop transcript rows already carry a rate-card estimate in cost_usd
    # (task 02's transcript.map_record computes it via RatingService.raw_cost,
    # no markup) -- read it as-is here rather than re-deriving from
    # token_usage, so it is never rated twice.
    for r in desktop_rc_rows:
        nm = name_of(r["repo"])
        desktop_rc_by_name[nm] += r["c"] or 0
        desktop_rc_by_name_model[nm][normalize_model(r["model"])] += r["c"] or 0
        repos_by_name[nm].add(r["repo"])
        if r["repo"] == UNATTRIBUTED:
            unattributed.add(r["repo"])

    for r in token_rows:
        nm = name_of(r["repo"])
        est = rates.billed(r["model"], r["token_type"], r["tok"]) / markup  # raw, pre-markup
        ratecard_by_name[nm] += est
        ratecard_by_name_model[nm][normalize_model(r["model"])] += est
        tokens_by_name[nm] += r["tok"] or 0
        repos_by_name[nm].add(r["repo"])
        if r["repo"] == UNATTRIBUTED:
            unattributed.add(r["repo"])

    use_actual = basis == "actual"
    if use_actual:
        # Combine actual + desktop rate-card into one billable total per name
        # -- both are already pre-markup USD, so this is a plain sum, not a
        # re-rating. Markup is applied exactly once, below, to the combined
        # `base`. When there is no desktop rate-card data at all (the OTLP-
        # only golden-baseline case), desktop_rc_by_name is empty and this is
        # identical to `actual_by_name` alone.
        cost_by_name = defaultdict(float)
        cost_by_name_model = defaultdict(lambda: defaultdict(float))
        for nm in set(actual_by_name) | set(desktop_rc_by_name):
            cost_by_name[nm] = actual_by_name.get(nm, 0.0) + desktop_rc_by_name.get(nm, 0.0)
            for model, amt in actual_by_name_model.get(nm, {}).items():
                cost_by_name_model[nm][model] += amt
            for model, amt in desktop_rc_by_name_model.get(nm, {}).items():
                cost_by_name_model[nm][model] += amt
    else:
        # --basis rates: re-derive EVERYTHING from token_usage counts, exactly
        # as before. This never reads cost_usage, so it cannot double-rate
        # the transcript rows that cost_usage already carries a rate-card
        # estimate for.
        cost_by_name = ratecard_by_name
        cost_by_name_model = ratecard_by_name_model

    print("=" * 68)
    print("PER-REPO BILL  (OTEL repo-attributed Claude Code usage)")
    if use_actual:
        if has_desktop_rc:
            # A mixed store must never be labelled simply "ACTUAL" -- part of
            # this total is a placeholder-rate estimate, not an
            # Anthropic-reported cost.
            print(f"basis: MIXED — ACTUAL cost.usage + RATE-CARD estimate "
                  f"(desktop, placeholder rates)  x{markup:.2f} markup")
        else:
            print(f"basis: ACTUAL cost from claude_code.cost.usage  x{markup:.2f} markup")
    else:
        print(f"basis: RATE-CARD estimate (placeholder rates)   x{markup:.2f} markup"
              + ("" if have_cost else "   [no cost data captured yet]"))
    print("=" * 68)

    grand_basis = grand_billed = 0.0
    for name in sorted(cost_by_name, key=lambda c: (c == UNATTRIBUTED, -cost_by_name[c])):
        base = cost_by_name[name]
        billed = base * markup
        grand_basis += base
        grand_billed += billed
        print(f"\n{name}")
        rule()
        print(f"  repos:  {', '.join(sorted(repos_by_name[name]))}")
        print(f"  tokens: {ftok(tokens_by_name[name])}")
        for model, amt in sorted(cost_by_name_model[name].items(), key=lambda x: -x[1]):
            print(f"    {model:<32} ${amt:>10,.4f}")
        # Split lines are emitted CONDITIONALLY -- only when rate-card rows
        # exist anywhere in the store -- so an OTLP-only store's output is
        # untouched (golden baseline).
        if use_actual and has_desktop_rc:
            print(f"  {'  actual (claude_code.cost.usage)':<34} "
                  f"${actual_by_name.get(name, 0.0):>10,.4f}")
            print(f"  {'  rate-card estimate (desktop)':<34} "
                  f"${desktop_rc_by_name.get(name, 0.0):>10,.4f}")
        print(f"  {'cost basis':<34} ${base:>10,.4f}")
        print(f"  {'BILLED (x%.2f)' % markup:<34} ${billed:>10,.4f}")

    rule("=")
    print(f"{'GRAND TOTAL cost basis':<36} ${grand_basis:>10,.4f}")
    print(f"{'GRAND TOTAL billed':<36} ${grand_billed:>10,.4f}")

    # Cross-check: actual vs rate-card (only meaningful when we have both)
    if have_cost:
        rc = sum(ratecard_by_name.values())
        ac = sum(actual_by_name.values())
        print(f"\ncross-check  actual=${ac:,.4f}  rate-card=${rc:,.4f}"
              + (f"  (rate-card is {rc/ac:.2f}x actual)" if ac else ""))

    # Attribution provenance — which signal produced each repo label.
    SOURCE_NOTE = {
        "timeline": "hook timeline (mid-session switches attributed)",
        "wrapper":  "wrapper launch tag only (no timeline for that session)",
        "no_remote": "wrapper ran outside a git repo -> unbillable",
        "absent":   "no repo attribute at all -> session bypassed the wrapper",
        "desktop-scratch": "desktop session with no billable repo -> unattributed "
                            "(billable, review before invoicing)",
    }
    if source_rows:
        total_tok = sum(r["tok"] or 0 for r in source_rows) or 1
        # Widened dynamically -- 'desktop-scratch' (15 chars) is wider than
        # the historical 11-char column, and widening it unconditionally
        # would ragged-wrap every OTLP-only report for no reason. Computed
        # from what's actually present so the OTLP-only golden baseline
        # (whose longest source is 'timeline', 8 chars) prints at the exact
        # same width -- 11 -- it always has.
        src_w = max(11, max(len(r["attribution_source"]) for r in source_rows) + 1)
        print("\nATTRIBUTION SOURCE")
        rule()
        for r in source_rows:
            src, tok = r["attribution_source"], r["tok"] or 0
            print(f"  {src:<{src_w}} {ftok(tok):>8}  {tok/total_tok*100:>5.1f}%"
                  f"  {SOURCE_NOTE.get(src, '')}")

    if overlap_sessions:
        print(f"\n⚠⚠ DOUBLE-BILLING RISK ({len(overlap_sessions)} session(s)) — "
              f"BOTH otlp AND transcript usage_source token rows:")
        for sid in sorted(overlap_sessions):
            print(f"     {sid}")
        print("   The wrapper's client-side filter and the receiver's server-side")
        print("   filter both test entrypoint == 'claude-desktop' -- the SAME")
        print("   predicate, so one upstream change (desktop app gains an OTLP")
        print("   exporter, or the entrypoint string changes) defeats both at once")
        print("   and silently double-bills these sessions. This total is NOT")
        print("   adjusted for it -- investigate before invoicing.")

    if multi_repo:
        print(f"\n⚠  MULTI-REPO SESSIONS ({len(multi_repo)}) — usage split across repos:")
        for sid, repos in sorted(multi_repo.items()):
            print(f"     {sid[:8]}  {' + '.join(repos)}")
        print("   Split by the timeline's as-of join. Review before invoicing —")
        print("   a switch inside one 60s export interval lands wholly on one side.")

    if unattributed:
        print("\n⚠  UNATTRIBUTED usage -> 'unknown' bucket, not tied to any repo.")
        print("   'no_remote' = ran outside a git repo (genuinely unbillable).")
        print("   'absent'    = no repo tag arrived; the session never passed")
        print("                 through the wrapper (non-CLI surface, or a bad")
        print("                 install). That usage IS billable but unattributed.")

    store.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--markup", type=float, default=1.50)
    ap.add_argument("--basis", choices=["actual", "rates"], default="actual",
                    help="actual = claude_code.cost.usage; rates = RatingService estimate")
    args = ap.parse_args()
    run(args.db, args.markup, args.basis)


if __name__ == "__main__":
    main()
