#!/usr/bin/env python3
"""Generate db/seed.sql for Vantage — a committed, static, hybrid seed (ADR-005).

This is a one-time *dev tool*, not a runtime dependency. It emits plain SQL that
Postgres loads on init (after db/schema.sql). Re-run it only when the schema or the
desired data changes, then commit the regenerated db/seed.sql.

Hybrid generation (ADR-005):
  * Faker (seeded)  owns STRUCTURE — postcodes, regions, account refs, monetary
    amounts, transaction ids, and the date offsets — guaranteeing reproducibility.
  * Claude          owns TEXT — the issue descriptions and the multi-update
    histories the agent must summarise. Those were authored by Claude during
    development and are embedded below as a curated content bank, so regeneration
    stays deterministic and offline (ADR-005: "no runtime LLM dependency").

Determinism: a fixed seed drives both Faker and the stdlib RNG, so running this
script always produces a byte-identical db/seed.sql.

Dates: emitted as RELATIVE SQL expressions (now() ± interval '<n> days'). The
*relationships* (issue age, "long-unresolved", due-soon) are fixed and stable for
eval ground truth, while the wall-clock anchor floats so the demo never goes stale.

Planted eval scenarios (shaped to 02-User-Stories / 07-Evals):
  * E1  — a customer name deliberately ABSENT (see ABSENT_CUSTOMER_NAMES); querying
          it must yield "not found", never an invented record.
  * E2  — two near-identical customers ("Lumen Commerce" vs "Lumen Commerce Group"),
          distinguishable only by account_ref + region → forces disambiguation.
  * E3  — a customer with ZERO open issues ("Calm Waters Subscriptions"): real,
          but every issue is resolved/closed.
  * HERO — one clearly High/Critical account ("Velocity Marketplace"): an open KYC
          hold blocking go-live, repeated payout failures, and a critical
          integration outage — the Escalation Summary story.

Usage:
    python scripts/generate_seed.py            # writes db/seed.sql
    python scripts/generate_seed.py --stdout   # prints to stdout instead

Requires: Faker (pip install 'faker==40.19.1'). No database connection needed.
Faker output is version-stable, so the committed seed is reproducible only against
the pinned version; data-ci pins the same version and fails if the seed drifts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from faker import Faker
except ImportError:  # pragma: no cover - dev-tool guard
    sys.exit("Faker is required: pip install faker")

import random

SEED = 20260527
OUT_PATH = Path(__file__).resolve().parents[1] / "db" / "seed.sql"

# A name that must NOT exist, so the "customer not found" path (E1) is exercised.
ABSENT_CUSTOMER_NAMES = ["Zzzz Holdings Ltd", "Globex Foobar Inc"]

fake = Faker("en_GB")
Faker.seed(SEED)
rng = random.Random(SEED)

UK_REGIONS = [
    "Greater London", "South East", "South West", "East of England",
    "West Midlands", "North West", "Yorkshire", "Scotland", "Wales",
]

# =============================================================================
# SQL emission helpers
# Each "value cell" is rendered to a SQL fragment string up-front, so the row
# builders below can mix string literals with relative-date expressions freely.
# =============================================================================


def q(value) -> str:
    """A SQL string literal (single quotes doubled), or NULL for None."""
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def lit(value) -> str:
    """A bare integer literal, or NULL for None."""
    return "NULL" if value is None else str(int(value))


def ago(days: int, hours: int = 0) -> str:
    """Timestamp `days`/`hours` in the past, as a relative SQL expression."""
    parts = [f"{int(days)} days"]
    if hours:
        parts.append(f"{int(hours)} hours")
    return "now() - interval '" + " ".join(parts) + "'"


def date_ago(days: int) -> str:
    return f"(now() - interval '{int(days)} days')::date"


def date_ahead(days: int) -> str:
    return f"(now() + interval '{int(days)} days')::date"


# =============================================================================
# Reference data
# =============================================================================

# Stable Keycloak subject ids — Track A copies these into the dev realm (or the
# app joins users on `email`, which matches the realm usernames). One user per role.
USERS = [
    # id, keycloak_id (uuid), display_name, email, role, created_days_ago
    (1, "11111111-1111-4111-8111-111111111111", "Priya Nair",  "sales@acme.test",   "sales_user",    420),
    (2, "22222222-2222-4222-8222-222222222222", "Marcus Webb", "support@acme.test", "support_user",  400),
    (3, "33333333-3333-4333-8333-333333333333", "Dana Okafor", "admin@acme.test",   "admin",         440),
]
SALES_ID, SUPPORT_ID, ADMIN_ID = 1, 2, 3

# Customers. `tag` marks the planted scenarios; account_ref + region are what make
# the E2 twins separable. account_manager is the single sales_user (Priya).
# id, name, segment, tier, tag
CUSTOMERS = [
    (1,  "Velocity Marketplace",        "Enterprise", "strategic", "hero"),
    (2,  "Lumen Commerce",              "Mid-Market", "premium",   "twin_a"),
    (3,  "Lumen Commerce Group",        "Enterprise", "strategic", "twin_b"),
    (4,  "Calm Waters Subscriptions",   "SMB",        "standard",  "no_open"),
    (5,  "Pinebrook Retail",            "Mid-Market", "premium",   "normal"),
    (6,  "Tindall & Crowe Books",       "SMB",        "standard",  "normal"),
    (7,  "Aperture Studios",            "SMB",        "standard",  "normal"),
    (8,  "Saffron Foods Online",        "Mid-Market", "premium",   "normal"),
    (9,  "Harbor Freight Digital",      "Enterprise", "strategic", "normal"),
    (10, "Meridian SaaS",               "Mid-Market", "premium",   "normal"),
    (11, "Beacon Health Tech",          "Mid-Market", "premium",   "normal"),
    (12, "Quartz Talent",               "SMB",        "standard",  "normal"),
]

OPEN_STATUSES = ("open", "in_progress", "pending")


# =============================================================================
# Claude-authored content
# -----------------------------------------------------------------------------
# HERO + twin + no-open issues are bespoke, hand-authored narratives (the data the
# agent will actually be asked to summarise). Each issue dict carries its full
# update history. `updates` items are (days_ago, update_type, author_id, body).
# =============================================================================

def bespoke_issues():
    """Return the curated issues for the planted-scenario customers."""
    issues = []  # each: dict(customer_id, title, desc, category, status, priority,
    #                         assignee, created, updates=[(days_ago, type, author, body)])

    # ---- HERO: Velocity Marketplace (id 1) — clearly High/Critical -----------
    issues.append(dict(
        customer_id=1, category="onboarding_compliance",
        status="in_progress", priority="critical", assignee=SUPPORT_ID, created=96,
        title="KYC review blocking marketplace go-live",
        desc=("Enhanced due-diligence on the marketplace entity is outstanding; go-live for "
              "connected-account payouts is blocked until compliance signs off. Incorporation "
              "docs are in, but UBO verification for two beneficial owners is still pending."),
        updates=[
            (94, "note", SUPPORT_ID, "Raised with compliance. Need certified UBO documents for the two >25% beneficial owners plus a proof of trading address."),
            (88, "note", SUPPORT_ID, "Customer uploaded the incorporation certificate and one UBO passport. Second UBO (overseas) document still missing."),
            (60, "status_change", ADMIN_ID, "Status -> in_progress. Compliance opened formal EDD case CDD-4821; awaiting sanctions/PEP screening."),
            (30, "note", SUPPORT_ID, "Sanctions screen returned clear. Outstanding: certified second-UBO ID and a source-of-funds questionnaire. Chased the customer."),
            (9,  "note", ADMIN_ID, "Go-live target is slipping. Flagged to the account manager — this is now the critical blocker on the account."),
        ],
    ))
    issues.append(dict(
        customer_id=1, category="payments",
        status="in_progress", priority="high", assignee=SUPPORT_ID, created=34,
        title="Repeated payout failures to connected accounts",
        desc=("Three consecutive daily payout batches to connected accounts have partially "
              "failed, returning funds to the platform balance. Sellers are chasing missing "
              "settlements and the customer is escalating."),
        updates=[
            (33, "note", SUPPORT_ID, "Confirmed batches PB-9051/9052/9053 each failed on a subset of accounts at the banking partner."),
            (28, "note", SUPPORT_ID, "Pattern: failures cluster on accounts onboarded last month — name/account-holder mismatch on the mandate."),
            (16, "status_change", SUPPORT_ID, "Status -> in_progress. Payments engineering reproducing against the partner sandbox; customer asked to re-verify payee details for the affected sellers."),
            (4,  "note", ADMIN_ID, "Still recurring on the latest batch. Keeping high priority until two clean payout cycles are observed."),
        ],
    ))
    issues.append(dict(
        customer_id=1, category="integration",
        status="open", priority="critical", assignee=SUPPORT_ID, created=6,
        title="Webhook delivery failing — signature mismatch after key rotation",
        desc=("Since the customer rotated their API signing secret, all webhook deliveries are "
              "rejected at their endpoint with signature-verification errors. Order fulfilment "
              "is stalled because their system never receives payment_succeeded events."),
        updates=[
            (6, "note", SUPPORT_ID, "Reproduced: deliveries return HTTP 401 'invalid signature' from the customer endpoint. They appear to still verify against the old secret."),
            (5, "note", SUPPORT_ID, "Confirmed the new signing secret is live our side. Advised they redeploy with the rotated secret and check for clock skew on the timestamp tolerance."),
            (3, "note", SUPPORT_ID, "Customer redeployed one service; a second worker still uses the cached old secret. Awaiting their full rollout — outage continues."),
        ],
    ))
    issues.append(dict(
        customer_id=1, category="performance",
        status="pending", priority="medium", assignee=SUPPORT_ID, created=15,
        title="Dashboard latency during the settlement window",
        desc=("The customer reports the reporting dashboard takes 20-40s to load between 23:00 "
              "and 00:00 UTC, overlapping the nightly settlement run."),
        updates=[
            (15, "note", SUPPORT_ID, "Correlated the slow window with heavy settlement-report queries on their account. Suggested narrower date ranges and the export API for bulk pulls."),
            (12, "status_change", SUPPORT_ID, "Status -> pending. Asked the customer to confirm whether the workaround helps before we weigh a query-plan change."),
        ],
    ))
    issues.append(dict(
        customer_id=1, category="billing",
        status="resolved", priority="low", assignee=SUPPORT_ID, created=72,
        title="Disputed platform fee on the April invoice",
        desc="Customer queried a platform fee line on the April invoice they believed had been waived under a promo.",
        updates=[
            (71, "note", SUPPORT_ID, "Checked the contract: the fee waiver expired end of March, so April was billed correctly."),
            (66, "note", ADMIN_ID, "Goodwill: approved a one-off 50% credit for April given the onboarding friction."),
            (64, "status_change", ADMIN_ID, "Status -> resolved. Credit note CN-2207 issued; customer accepted."),
        ],
    ))

    # ---- E2 twin A: Lumen Commerce (id 2) ------------------------------------
    issues.append(dict(
        customer_id=2, category="billing",
        status="open", priority="medium", assignee=SUPPORT_ID, created=11,
        title="Invoice total higher than expected",
        desc="Customer asks why the latest invoice is ~18% higher than last month; suspects an unexpected charge.",
        updates=[
            (11, "note", SUPPORT_ID, "Itemised the invoice for them: the rise is overage on processed volume above the plan threshold."),
            (8,  "note", SUPPORT_ID, "Shared the volume breakdown; customer reviewing internally before we adjust the plan tier."),
        ],
    ))
    issues.append(dict(
        customer_id=2, category="integration",
        status="in_progress", priority="medium", assignee=SUPPORT_ID, created=20,
        title="Intermittent webhook retries on refund events",
        desc="A fraction of refund webhooks are delivered twice; customer wants to confirm idempotency handling.",
        updates=[
            (20, "note", SUPPORT_ID, "Explained at-least-once delivery and the event id for de-duplication."),
            (14, "status_change", SUPPORT_ID, "Status -> in_progress. Customer adding an idempotency check; will confirm once deployed."),
        ],
    ))
    issues.append(dict(
        customer_id=2, category="access",
        status="resolved", priority="low", assignee=SUPPORT_ID, created=40,
        title="Help rotating a leaked restricted API key",
        desc="Customer accidentally committed a restricted key to a public repo and needed it rotated.",
        updates=[
            (40, "note", SUPPORT_ID, "Revoked the exposed key immediately and issued a replacement restricted key."),
            (39, "status_change", SUPPORT_ID, "Status -> resolved. Confirmed no unauthorised use in the logs; advised on secret scanning."),
        ],
    ))

    # ---- E2 twin B: Lumen Commerce Group (id 3) ------------------------------
    issues.append(dict(
        customer_id=3, category="payments",
        status="open", priority="high", assignee=SUPPORT_ID, created=5,
        title="Payout delayed beyond the expected schedule",
        desc="A scheduled payout has not arrived two business days past the expected date; customer needs settlement confirmation.",
        updates=[
            (5, "note", SUPPORT_ID, "Traced the payout: held by an automated risk review after an unusual volume spike."),
            (2, "note", SUPPORT_ID, "Risk review cleared; payout re-queued. Advised the customer of the new arrival window."),
        ],
    ))
    issues.append(dict(
        customer_id=3, category="onboarding_compliance",
        status="pending", priority="medium", assignee=SUPPORT_ID, created=18,
        title="Additional KYC documents requested for a new entity",
        desc="Customer is adding a second trading entity and compliance has requested supporting documents.",
        updates=[
            (18, "note", SUPPORT_ID, "Listed the required documents for the new entity (certificate, director ID, address proof)."),
            (13, "status_change", SUPPORT_ID, "Status -> pending. Awaiting the customer's document upload."),
        ],
    ))
    issues.append(dict(
        customer_id=3, category="performance",
        status="closed", priority="low", assignee=SUPPORT_ID, created=80,
        title="One-off slow API responses during a provider incident",
        desc="Elevated API latency reported during a known upstream provider incident.",
        updates=[
            (80, "note", SUPPORT_ID, "Linked to the upstream incident; latency recovered once the provider resolved it."),
            (78, "status_change", SUPPORT_ID, "Status -> closed. No action needed our side; shared the incident post-mortem link."),
        ],
    ))

    # ---- E3: Calm Waters Subscriptions (id 4) — ZERO open issues -------------
    issues.append(dict(
        customer_id=4, category="billing",
        status="resolved", priority="low", assignee=SUPPORT_ID, created=50,
        title="Proration question on a mid-cycle plan change",
        desc="Customer wanted to understand how a mid-cycle upgrade would be prorated.",
        updates=[
            (50, "note", SUPPORT_ID, "Walked through the proration maths with a worked example."),
            (48, "status_change", SUPPORT_ID, "Status -> resolved. Customer happy; no billing change required."),
        ],
    ))
    issues.append(dict(
        customer_id=4, category="access",
        status="closed", priority="medium", assignee=SUPPORT_ID, created=90,
        title="SSO setup for the dashboard",
        desc="Customer configured SAML SSO for their team's dashboard access.",
        updates=[
            (90, "note", SUPPORT_ID, "Provided the SAML metadata and attribute-mapping guide."),
            (86, "note", SUPPORT_ID, "Customer completed setup; verified a test login end to end."),
            (85, "status_change", SUPPORT_ID, "Status -> closed. SSO live for their team."),
        ],
    ))
    issues.append(dict(
        customer_id=4, category="integration",
        status="resolved", priority="low", assignee=SUPPORT_ID, created=120,
        title="Sandbox webhook test not firing",
        desc="Customer's sandbox endpoint was not receiving test webhooks during integration.",
        updates=[
            (120, "note", SUPPORT_ID, "Their sandbox URL was unreachable from our egress; they opened the firewall rule."),
            (118, "status_change", SUPPORT_ID, "Status -> resolved. Test events delivered successfully."),
        ],
    ))

    return issues


# -----------------------------------------------------------------------------
# Templated content for the "normal" customers. Claude-authored category arcs;
# Faker fills the {placeholders} so each instance reads distinctly. `arc` is the
# investigation narrative (notes); a closing status_change is appended to match
# whatever terminal status the issue is given.
# -----------------------------------------------------------------------------
TEMPLATES = {
    "integration": [
        dict(title="Webhook endpoint returning {code} errors",
             desc="Customer's endpoint is returning {code} for a portion of webhook deliveries, so some events are not being processed.",
             arc=["Confirmed {pct}% of deliveries to their endpoint returned {code} over the last 24h.",
                  "Likely a timeout on their side under load; advised returning 2xx fast and processing async.",
                  "Customer is tuning their handler to ack quickly and queue processing; monitoring the error rate."]),
        dict(title="API returning {code} on the {endpoint} endpoint",
             desc="Calls to the {endpoint} endpoint intermittently return {code}; customer wants to know if it is on their side or ours.",
             arc=["Reproduced intermittently; correlated with a missing idempotency key on retries.",
                  "Shared a request id ({req}) and the correct retry pattern.",
                  "Customer is adding the idempotency key on their retry path; will confirm once deployed."]),
    ],
    "payments": [
        dict(title="Failed payout batch {batch}",
             desc="Payout batch {batch} totalling GBP {amount} to {n} connected accounts failed at the banking partner; funds returned to the balance.",
             arc=["Confirmed batch {batch} failed with partner response {code}.",
                  "Root cause was an account-holder name mismatch on {n} accounts.",
                  "Customer is correcting the remaining payee details so we can re-run the affected accounts."]),
        dict(title="Customer disputing a card payment for GBP {amount}",
             desc="A cardholder has disputed a GBP {amount} payment; the customer needs help compiling evidence for the chargeback.",
             arc=["Explained the dispute timeline and the evidence types that win this reason code.",
                  "Helped assemble the evidence pack ({req}).",
                  "Submitted the evidence for the GBP {amount} dispute ahead of the deadline; awaiting the issuer's decision."]),
    ],
    "onboarding_compliance": [
        dict(title="KYC documents requested before activation",
             desc="Compliance has requested KYC documents before the account can be fully activated for live processing.",
             arc=["Listed the required documents (incorporation, director ID, address proof).",
                  "Customer uploaded the documents.",
                  "Documents passed to compliance; awaiting their review before activation."]),
        dict(title="Source-of-funds questionnaire outstanding",
             desc="A source-of-funds questionnaire is outstanding on the account following a routine review.",
             arc=["Sent the questionnaire and explained why it is required for their volume band.",
                  "Customer returned the completed questionnaire.",
                  "Questionnaire under review with compliance; no further input needed from the customer for now."]),
    ],
    "billing": [
        dict(title="Query on the {month} invoice",
             desc="Customer has a question about a line item on their {month} invoice and wants it explained before paying.",
             arc=["Itemised the {month} invoice and explained the queried line.",
                  "Shared the detailed breakdown.",
                  "Customer is reviewing the breakdown with their finance team."]),
        dict(title="Request to change billing cycle to {month}",
             desc="Customer asked to move their billing anchor date and understand the proration impact.",
             arc=["Confirmed the new anchor date and calculated the one-off proration.",
                  "Shared the prorated amount with the customer.",
                  "Customer approved the proration; preparing to apply the change."]),
    ],
    "access": [
        dict(title="Locked out of the dashboard after an SSO change",
             desc="An admin user is locked out of the dashboard following a change to the customer's SSO configuration.",
             arc=["Identified a broken attribute mapping after their IdP change.",
                  "Guided them to the corrected mapping.",
                  "Customer is applying the fix in their IdP; will confirm a test login."]),
        dict(title="Request for a new restricted API key with scoped permissions",
             desc="Customer needs a restricted API key scoped to read-only reporting for a new internal tool.",
             arc=["Confirmed the exact scopes required for read-only reporting.",
                  "Prepared the restricted key with those scopes.",
                  "Customer is wiring the new key into their reporting tool."]),
    ],
    "performance": [
        dict(title="Slow report generation for large date ranges",
             desc="Generating reports across large date ranges is slow for the customer during business hours.",
             arc=["Reproduced the slowness on wide ranges.",
                  "Recommended the export API for bulk pulls instead of the dashboard.",
                  "Customer is trialling the export API for their bulk pulls."]),
        dict(title="Elevated API latency from the {region} region",
             desc="Customer reports elevated API latency for requests originating from the {region} region.",
             arc=["Measured added round-trip latency from {region}; explained current regional routing.",
                  "Advised connection reuse and shared the latency guidance.",
                  "Customer is testing connection reuse from {region} and gathering follow-up numbers."]),
    ],
}

# Terminal status -> closing status_change body.
CLOSING_LINE = {
    "in_progress": "Status -> in_progress. Actively working it with the customer.",
    "pending":     "Status -> pending. Awaiting the customer's response.",
    "resolved":    "Status -> resolved. Fix confirmed; customer satisfied.",
    "closed":      "Status -> closed. No further action required.",
}

# Realistic status / priority mix for normal customers (no second all-critical
# account — the hero stays the standout). Weighted draws.
NORMAL_STATUSES = (
    ["open"] * 3 + ["in_progress"] * 3 + ["pending"] * 2 + ["resolved"] * 4 + ["closed"] * 2
)
NORMAL_PRIORITIES = (
    ["low"] * 4 + ["medium"] * 5 + ["high"] * 2  # 'critical' reserved for the hero
)


def templated_issues():
    """Generate 2-4 issues for each 'normal' customer from the category templates."""
    issues = []
    months = ["January", "February", "March", "April", "May"]
    endpoints = ["/v1/charges", "/v1/payouts", "/v1/refunds", "/v1/customers"]
    codes = ["HTTP 500", "HTTP 502", "HTTP 429", "HTTP 401", "HTTP 400"]

    for cust in CUSTOMERS:
        cid, tag = cust[0], cust[4]
        if tag != "normal":
            continue
        n_issues = rng.randint(2, 4)
        cats = rng.sample(list(TEMPLATES.keys()), k=min(n_issues, len(TEMPLATES)))
        for category in cats:
            tpl = rng.choice(TEMPLATES[category])
            fills = dict(
                code=rng.choice(codes),
                pct=rng.choice([5, 8, 12, 20, 35]),
                endpoint=rng.choice(endpoints),
                req="req_" + fake.bothify("??????##"),
                batch="PB-" + fake.numerify("####"),
                amount=f"{rng.randint(2, 480) * 100:,}",
                n=rng.randint(2, 60),
                month=rng.choice(months),
                region=rng.choice(["EU", "US-East", "APAC", "US-West"]),
            )
            status = rng.choice(NORMAL_STATUSES)
            priority = rng.choice(NORMAL_PRIORITIES)
            created = rng.randint(4, 150)

            # Build the history: template notes, then a terminal status_change if
            # the issue moved past plain 'open'. Update times strictly decrease
            # (more recent) and stay within (0, created).
            updates = []
            note_times = sorted(
                {rng.randint(1, max(2, created - 1)) for _ in range(len(tpl["arc"]))},
                reverse=True,
            )
            while len(note_times) < len(tpl["arc"]):
                note_times.append(max(1, note_times[-1] - rng.randint(1, 4)))
            for body_tpl, days_ago in zip(tpl["arc"], note_times):
                author = rng.choice([SUPPORT_ID, ADMIN_ID])
                updates.append((days_ago, "note", author, body_tpl.format(**fills)))
            if status != "open":
                term_days = max(1, min(note_times) - 1) if note_times else 1
                updates.append((term_days, "status_change",
                                rng.choice([SUPPORT_ID, ADMIN_ID]), CLOSING_LINE[status]))

            issues.append(dict(
                customer_id=cid, category=category, status=status, priority=priority,
                assignee=rng.choice([SUPPORT_ID, ADMIN_ID]), created=created,
                title=tpl["title"].format(**fills), desc=tpl["desc"].format(**fills),
                updates=updates,
            ))
    return issues


# -----------------------------------------------------------------------------
# Next actions (admin-owned). Attached to the more important / open issues, a few
# already done or cancelled. created_by is always the admin (RBAC: ADR-002).
# Each: (issue_index_0based, description, status, due_offset_days[+future/-past]).
# The hero's open issues get explicit, escalation-style directives.
# -----------------------------------------------------------------------------
def build_next_actions(issues):
    """Return next_actions referencing issues by their 1-based id (= index+1)."""
    actions = []

    def find(customer_id, title_contains):
        for idx, iss in enumerate(issues):
            if iss["customer_id"] == customer_id and title_contains.lower() in iss["title"].lower():
                return idx + 1  # 1-based issue id
        return None

    # Hero (Velocity) — explicit escalation directives.
    hero_specs = [
        ("KYC review", "Escalate EDD case CDD-4821 to the compliance lead; obtain the certified second-UBO ID and source-of-funds questionnaire from the customer.", "open", 3),
        ("Repeated payout failures", "Open a Sev-2 bridge with payments engineering; require two clean payout cycles before downgrading priority.", "open", 2),
        ("Webhook delivery failing", "Confirm with the customer that every worker has redeployed with the rotated signing secret; verify deliveries return 2xx.", "open", 1),
        ("Disputed platform fee", "Confirm credit note CN-2207 has cleared on the next invoice.", "done", -50),
    ]
    for title_contains, desc, status, due in hero_specs:
        iid = find(1, title_contains)
        if iid:
            actions.append((iid, desc, status, due))

    # A spread of next actions across other customers' open issues.
    open_other = [
        (idx + 1, iss) for idx, iss in enumerate(issues)
        if iss["customer_id"] != 1 and iss["status"] in OPEN_STATUSES
    ]
    rng.shuffle(open_other)
    generic = [
        "Chase the customer for the outstanding information and update the issue.",
        "Schedule a follow-up call with the account contact this week.",
        "Confirm the workaround resolved the problem before closing.",
        "Review with the team at the next triage and reassign if needed.",
        "Document the resolution steps in the customer's account notes.",
        "Verify the fix in production and notify the customer.",
    ]
    target_total = 14  # hero contributes ~4 -> ~14-15 total
    for i, (iid, iss) in enumerate(open_other):
        if len(actions) >= target_total:
            break
        status = "open"
        if i % 6 == 5:
            status = "cancelled"
        due = rng.choice([2, 3, 5, 7, 10, 14])
        actions.append((iid, generic[i % len(generic)], status, due))

    return actions


# =============================================================================
# Assembly — build rows and render the SQL file.
# =============================================================================

def build():
    issues = bespoke_issues() + templated_issues()

    # Assign issue ids (1-based, in list order) and flatten updates / next actions.
    issue_rows = []
    update_rows = []
    next_actions = build_next_actions(issues)

    update_id = 0
    for idx, iss in enumerate(issues):
        iid = idx + 1
        created = iss["created"]
        upd = sorted(iss["updates"], key=lambda u: u[0], reverse=True)  # oldest first
        # The issue is created at hour 23 of its day (earliest point) and updates
        # take hours 0..22 of theirs, so an update can never precede its issue —
        # even one logged on the same day it was raised. days_ago is clamped to the
        # issue's own day for the same reason. updated_at = the most recent update.
        most_recent = None  # (total_hours_ago, days, hour)
        for days_ago, utype, author, body in upd:
            update_id += 1
            d = min(days_ago, created)
            hour = (update_id * 7) % 23
            update_rows.append((update_id, iid, author, body, utype, d, hour))
            total = d * 24 + hour
            if most_recent is None or total < most_recent[0]:
                most_recent = (total, d, hour)
        upd_days, upd_hour = (most_recent[1], most_recent[2]) if most_recent else (created, 22)
        issue_rows.append((
            iid, iss["customer_id"], iss["title"], iss["desc"], iss["category"],
            iss["status"], iss["priority"], iss["assignee"], created, upd_days, upd_hour,
        ))

    return issues, issue_rows, update_rows, next_actions


def render(issues, issue_rows, update_rows, next_actions) -> str:
    out = []
    w = out.append

    n_open = sum(1 for r in issue_rows if r[5] in OPEN_STATUSES)
    w("-- Vantage — committed static seed (GENERATED by scripts/generate_seed.py).")
    w("-- Do not edit by hand: change the generator and re-run, then commit this file.")
    w("--")
    w("-- Hybrid provenance (ADR-005): Faker (seeded) owns structure; Claude authored the")
    w("-- issue text + multi-update histories. Deterministic + offline (no runtime LLM).")
    w("-- Loaded by Postgres AFTER db/schema.sql. Dates are relative to load time.")
    w("--")
    w(f"-- Volume: {len(USERS)} users (one per role) · {len(CUSTOMERS)} customers · "
      f"{len(issue_rows)} issues ({n_open} open) · {len(update_rows)} updates · "
      f"{len(next_actions)} next actions.")
    w("--")
    w("-- Planted eval scenarios:")
    w(f"--   E1  not-found  : query an ABSENT name, e.g. {ABSENT_CUSTOMER_NAMES[0]!r} "
      f"or {ABSENT_CUSTOMER_NAMES[1]!r} — no such customer exists.")
    w("--   E2  ambiguous  : 'Lumen Commerce' (id 2) vs 'Lumen Commerce Group' (id 3) — "
      "same name root, different account_ref + region.")
    w("--   E3  no-open     : 'Calm Waters Subscriptions' (id 4) — exists, every issue resolved/closed.")
    w("--   HERO High/Crit : 'Velocity Marketplace' (id 1) — open KYC hold blocking go-live, "
      "repeated payout failures, critical webhook outage.")
    w("")
    w("BEGIN;")
    w("")

    # --- users ---
    w("-- users: Acme internal operators. role mirrors Keycloak (attribution only; ADR-002).")
    w("INSERT INTO users (id, keycloak_id, display_name, email, role, created_at) VALUES")
    rows = [
        f"  ({uid}, {q(kid)}, {q(name)}, {q(email)}, {q(role)}, {ago(days)})"
        for (uid, kid, name, email, role, days) in USERS
    ]
    w(",\n".join(rows) + ";")
    w("")

    # --- customers ---
    w("-- customers: Acme's customers. account_ref + region disambiguate the E2 twins.")
    w("INSERT INTO customers (id, name, account_ref, region, postcode, segment, tier, account_manager_id, created_at) VALUES")
    rows = []
    used_refs = set()
    for (cid, name, segment, tier, _tag) in CUSTOMERS:
        ref = "ACME-" + fake.numerify("#####")
        while ref in used_refs:
            ref = "ACME-" + fake.numerify("#####")
        used_refs.add(ref)
        region = rng.choice(UK_REGIONS)
        postcode = fake.postcode()
        created = rng.randint(120, 700)
        rows.append(
            f"  ({cid}, {q(name)}, {q(ref)}, {q(region)}, {q(postcode)}, "
            f"{q(segment)}, {q(tier)}, {SALES_ID}, {ago(created)})"
        )
    w(",\n".join(rows) + ";")
    w("")

    # --- issues ---
    w("-- issues: \"open\" = status IN ('open','in_progress','pending').")
    w("INSERT INTO issues (id, customer_id, title, description, category, status, priority, assigned_to, created_at, updated_at) VALUES")
    rows = []
    for (iid, cust, title, desc, cat, status, prio, assignee, created, upd_days, upd_hour) in issue_rows:
        rows.append(
            f"  ({iid}, {cust}, {q(title)}, {q(desc)}, {q(cat)}, {q(status)}, "
            f"{q(prio)}, {lit(assignee)}, {ago(created, 23)}, {ago(upd_days, upd_hour)})"
        )
    w(",\n".join(rows) + ";")
    w("")

    # --- issue_updates ---
    w("-- issue_updates: append-only history the agent summarises.")
    w("INSERT INTO issue_updates (id, issue_id, author_id, body, update_type, created_at) VALUES")
    rows = [
        f"  ({uid}, {iid}, {lit(author)}, {q(body)}, {q(utype)}, {ago(days, hour)})"
        for (uid, iid, author, body, utype, days, hour) in update_rows
    ]
    w(",\n".join(rows) + ";")
    w("")

    # --- next_actions ---
    w("-- next_actions: admin-owned directives (created_by = admin; RBAC at the tool, ADR-002).")
    w("INSERT INTO next_actions (id, issue_id, created_by_id, description, due_date, status, created_at, updated_at) VALUES")
    rows = []
    for naid, (iid, desc, status, due) in enumerate(next_actions, start=1):
        due_sql = date_ahead(due) if due >= 0 else date_ago(-due)
        created = ago(rng.randint(1, 20))
        rows.append(
            f"  ({naid}, {iid}, {ADMIN_ID}, {q(desc)}, {due_sql}, {q(status)}, {created}, {created})"
        )
    w(",\n".join(rows) + ";")
    w("")

    # --- reset identity sequences past the explicit ids so the app can insert ---
    w("-- Advance identity sequences past the seeded ids (we set ids explicitly above).")
    for table in ("users", "customers", "issues", "issue_updates", "next_actions"):
        w(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
          f"(SELECT COALESCE(MAX(id), 1) FROM {table}));")
    w("")
    w("COMMIT;")
    w("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Generate Vantage db/seed.sql")
    ap.add_argument("--stdout", action="store_true", help="print to stdout instead of writing the file")
    args = ap.parse_args()

    issues, issue_rows, update_rows, next_actions = build()
    sql = render(issues, issue_rows, update_rows, next_actions)

    if args.stdout:
        sys.stdout.write(sql)
    else:
        OUT_PATH.write_text(sql)
        n_open = sum(1 for r in issue_rows if r[5] in OPEN_STATUSES)
        print(f"Wrote {OUT_PATH.relative_to(OUT_PATH.parents[1])}: "
              f"{len(USERS)} users, {len(CUSTOMERS)} customers, {len(issue_rows)} issues "
              f"({n_open} open), {len(update_rows)} updates, {len(next_actions)} next actions.")


if __name__ == "__main__":
    main()
