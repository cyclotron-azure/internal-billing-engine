"""Decide whether a usage datapoint belongs to Cyclotron, at INGEST time.

Telemetry config is deployed per MACHINE (deploy/managed-settings.json, or the
client-package's ~/.claude/settings.json), so it applies to whichever Claude
account is signed in — including a developer's personal Pro/Max account on a
work laptop. Left unfiltered that usage is not merely noise:

  * it carries a personal email address into token_usage/cost_usage and, via
    export.py, into the CSVs shipped to the data lake — personal-account
    identities from personal sessions, persisted company-side; and
  * it carries `claude_code.cost.usage` that CYCLOTRON NEVER PAID (a personal
    subscription billed to the individual), which bill.py then marks up and
    puts on a client invoice. That is over-billing a client, not a rounding
    error.

So the filter runs in the receiver and non-Cyclotron datapoints are dropped
before they reach the store. Nothing personal is written to disk.

THIS IS A HYGIENE CONTROL, NOT A SECURITY BOUNDARY. `user.email` and
`organization.id` are self-reported OTEL attributes; the fleet token
authenticates a machine, not a user (see receiver.py). A determined developer
can forge them. The control that actually PREVENTS a personal login is
`forceLoginOrgUUID` in managed settings — see deploy/README.md. This is the
backstop for the surfaces and versions that key doesn't cover.

POLICY
  BILLING_ALLOWED_ORG_IDS      comma-separated Anthropic organization UUIDs.
                               The strong signal: a personal account has a
                               different org even when its email is a work
                               address. Empty = not enforced (and the receiver
                               warns at startup).
  BILLING_ALLOWED_EMAIL_DOMAINS  comma-separated email domains, default
                               'cyclotron.com'. Empty = not enforced.

  Both empty disables scope filtering entirely (everything is in scope).

VERDICTS
  in_scope       store it and bill it
  unknown_user   no usable user.email — STORED AND BILLED, bucketed as
                 'unknown' by export.py. Deliberately not dropped: if an
                 upstream change ever stops emitting user.email, dropping
                 would silently delete real revenue with no signal, whereas
                 a growing 'unknown' bucket is visible.
  out_of_scope   dropped, and counted in the scope_rejections ledger
"""

from __future__ import annotations

import os

from ..config import load_env

IN_SCOPE = "in_scope"
UNKNOWN_USER = "unknown_user"
OUT_OF_SCOPE = "out_of_scope"

DEFAULT_DOMAINS = "cyclotron.com"

_policy_cache = None


def _split(value: str, lower: bool = True) -> frozenset:
    parts = (p.strip() for p in (value or "").split(","))
    return frozenset((p.lower() if lower else p) for p in parts if p)


def policy() -> tuple:
    """(allowed_org_ids, allowed_domains), read once and cached.

    Read lazily rather than at import: receiver.py calls load_env() *after* its
    imports, so a module-level constant here would be computed before .env was
    loaded and would silently ignore the configured policy.
    """
    global _policy_cache
    if _policy_cache is None:
        load_env()
        _policy_cache = (
            # Org UUIDs are case-significant (org_017BoAXhqPPAikCCgiaTvzVU),
            # so they match exactly. Email domains are case-insensitive.
            _split(os.environ.get("BILLING_ALLOWED_ORG_IDS", ""), lower=False),
            _split(os.environ.get("BILLING_ALLOWED_EMAIL_DOMAINS", DEFAULT_DOMAINS)),
        )
    return _policy_cache


def reset_policy() -> None:
    """Drop the cached policy so a test can change the environment."""
    global _policy_cache
    _policy_cache = None


def email_domain(user_email: str) -> str:
    """The domain part, lowercased, or '' if there isn't a usable one."""
    email = (user_email or "").strip().lower()
    if "@" not in email:
        return ""
    domain = email.rsplit("@", 1)[1].strip()
    return domain


def classify(user_email: str, org_id: str) -> tuple:
    """(verdict, reason, domain) for one datapoint.

    `reason` is '' unless the verdict is out_of_scope. `domain` is returned so
    the caller can record WHICH domain was rejected without ever handling the
    local part of the address.
    """
    allowed_orgs, allowed_domains = policy()
    if not allowed_orgs and not allowed_domains:
        return IN_SCOPE, "", ""

    domain = email_domain(user_email)
    org = (org_id or "").strip()

    # Org first: it is the signal that survives a personal account registered
    # to a work email address, which the domain check alone would wave through.
    # An absent org_id can't be judged, so it falls through to the email check.
    if allowed_orgs and org and org not in allowed_orgs:
        return OUT_OF_SCOPE, "org", domain

    # No usable email: keep it (see VERDICTS above). A present-but-malformed
    # value counts as no email for the same reason — it is not evidence of a
    # personal account, so dropping it would trade a visible gap for silence.
    if not domain:
        return UNKNOWN_USER, "", ""

    if allowed_domains and domain not in allowed_domains:
        return OUT_OF_SCOPE, "domain", domain

    return IN_SCOPE, "", domain


def describe() -> str:
    """One line for the receiver's startup banner."""
    allowed_orgs, allowed_domains = policy()
    if not allowed_orgs and not allowed_domains:
        return "scope=OFF (all accounts accepted)"
    orgs = ",".join(sorted(allowed_orgs)) if allowed_orgs else "(any)"
    doms = ",".join(sorted(allowed_domains)) if allowed_domains else "(any)"
    return "scope orgs=%s domains=%s" % (orgs, doms)
