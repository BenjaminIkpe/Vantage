---
title: Frame — problem & outcome
type: frame
status: locked
updated: 2026-05-27
---

# Frame

> [!NOTE] Purpose
> What we are paid to deliver and how we'll know we succeeded. Feeds the README. Synthesised from the locked [02-User-Stories](02-User-Stories.md).

## The client & the problem
*Client: Acme Operations (mid-sized enterprise).*

> Acme's internal users — sales, support, operations — answer operational questions ("show me open issues for Client X, summarise the latest status, and suggest the next action") by navigating multiple systems by hand. Slow, repetitive, and hard to audit.

These split into two jobs: **reactive support** (work the issue queue) and **proactive account management** (watch account health and risk). Vantage serves both.

## What Acme does (business context)
*(The brief leaves Acme's business open; we define it concretely so the data, demo, and risk model are coherent — see [ADR-005](05-Decisions/ADR-005-seed-data.md).)*

**Acme is a B2B payments & billing platform** ("Stripe-for-SMBs"): payment processing, payouts, and billing infrastructure delivered to online businesses via an API + dashboard.

- **Acme's customers:** online businesses, marketplaces, and subscription/SaaS companies that use Acme to take payments, pay out, and manage billing.
- **Acme's internal teams (our users):** support (resolves customer issues), sales/account management (owns relationships, renewals, growth), operations/admin (oversight + compliance coordination).
- **Vantage's role:** the internal **copilot** these teams use to *find, understand, and act on* what's happening with a customer. It does **not** fix the underlying payment/integration problems — humans do. (Decision-support, not remediation; see [03-Scope](03-Scope.md).)

## The outcome we're paid to deliver
> Acme's support and account teams get one secure assistant that answers in plain English across systems they'd otherwise check by hand — whether a support rep picking up an issue (open issues, history, recording the fix) or an account manager checking an account's health and risk before a client call. Every answer is grounded in Acme's own records and traceable to source; every action is gated by the user's role and logged. The result: faster, more consistent customer handling, and an auditable trail of who saw and changed what.

## Definition of Done (DoD)
- [ ] Runs end-to-end with one command (`docker compose up`).
- [ ] All required components present and wired together.
- [ ] Agent selects tools dynamically; answers grounded in the database; unhappy paths (not-found, ambiguous name) handled **without inventing data**.
- [ ] Holds context across a multi-turn session (Redis).
- [ ] RBAC demonstrably enforced — including at least one *denied* case.
- [ ] Eval set (5–10 questions) passes, with documented results.
- [ ] Every design choice defensible in the panel (logged as ADRs).

## Primary users
Roles: `sales_user`, `support_user`, `admin`. Full detail in [02-User-Stories](02-User-Stories.md).
