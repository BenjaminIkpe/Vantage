---
title: Integration — Vantage embedded in Acme's existing stack
type: integration
status: active
updated: 2026-05-28
---

# Integration — what changes when Vantage is a copilot over Acme's existing platforms

> [!NOTE] Purpose
> Panel-grade answer to *"in production, where does the data come from and how much of this changes?"* — the realistic Acme stack, the federation-vs-context-graph choice that proactive observation forces (bridges [11-Future](11-Future.md)), what stays the same (most of it, thanks to ADR-003), what changes (the tool internals + a thin context graph), and the honest cost. Cross-refs: [04-Architecture](04-Architecture.md), [11-Future](11-Future.md), [12-Data](12-Data.md), [ADR-002](05-Decisions/ADR-002-rbac-tool-boundary.md), [ADR-003](05-Decisions/ADR-003-mcp-server.md), [10-Scaling](10-Scaling.md).

## Short answer
In production Vantage **doesn't own customer data** — it lives in Zendesk (tickets), Salesforce (accounts), Persona / Alloy (KYC), and the like. But the proactive observer in [11-Future](11-Future.md) needs to reason *across* those sources continuously, and you can't do that from pure federation. The 2026 industry has converged on a **scoped context graph**: a thin local store of cross-source relationships, computed signals, and embeddings — *not* a mirror — populated via connectors + webhooks, with source-side permissions re-checked at read. Our MCP-based design absorbs this without rewriting anything above the tool boundary.

## Realistic Acme stack (what they're already paying for)
A B2B payments platform Acme's size doesn't build a custom system of record — they assemble best-of-breed SaaS:

| Function | Realistic platform | What lives there |
|---|---|---|
| Support ticketing | **Zendesk** (or Intercom, Freshdesk, Front) | `issues` + `issue_updates` |
| CRM / account management | **Salesforce** (or HubSpot) | `customers` + account managers + renewal data |
| KYC / compliance | **Persona** / Alloy / Onfido / ComplyAdvantage | EDD cases (Velocity's CDD-4821 lives here, not in support) |
| Payments ops + analytics | data warehouse — Snowflake / BigQuery | settlement, payout, dispute aggregates |
| Internal handoffs | Slack / Microsoft Teams; PagerDuty for Sev | escalation channels |
| Knowledge base | Notion / Confluence / Guru | runbooks + past resolutions |

Our committed Postgres seed ([12-Data](12-Data.md)) is fixture-for-the-assessment; in production it becomes a scoped context graph (below), not the system of record.

## Federated query vs scoped context graph (and why proactive forces the graph)

| | Federated query (Salesforce Zero-Copy) | Scoped context graph (Atlassian Teamwork Graph, M365 Graph, Glean, Moveworks) |
|---|---|---|
| Where data is queried | live at source | local index, refreshed by webhooks + reconciliation |
| Freshness | best | seconds-to-minutes stale |
| Continuous observation | structurally impossible (no local state to delta against) | natural — it's what the graph is *for* |
| Cross-source joins | expensive fan-out | cheap local query |
| Permission model | always at source | local cache + re-check at source on read |
| Infra burden | low | substantial (connectors, sync, conflict resolution) |
| **Supports the [11-Future](11-Future.md) observer** | ❌ | ✅ |

The industry has converged on the graph for proactive use cases. ServiceNow's 2025-2026 acquisition of Moveworks was specifically to bring this capability inside the platform.

## What the graph actually holds (and what it doesn't)
A scoped context graph is **not a copy of every source**. For Vantage it would hold roughly:

- **Cross-source identity + relationships** — this Zendesk ticket ↔ this Salesforce account ↔ this Persona case. The joins no single source can do.
- **Computed signals per customer** — risk level, open critical count, long-unresolved flag, last-changed-state. Recomputed on event + nightly. The [11-Future](11-Future.md) `observations` table extended across sources.
- **Embedding index** over issue descriptions + update bodies, for similar-case retrieval (the slot [10-Scaling §Where RAG earns its place](10-Scaling.md) describes — slotted in here, not in place of structured tools).
- **An events log** of what the observer has already surfaced, keyed by `(customer, signal, version)` so it doesn't re-fire on stale data.

It does **not** hold:
- Every ticket body verbatim — fetch on demand.
- A live copy of Salesforce — the source stays canonical for accounts.
- Anything source-side ACLs say a Vantage caller can't see.

## The 2026 wrinkle: consuming upstream MCP servers
Source platforms have started exposing their own context layers **over MCP** — Atlassian's Teamwork Graph already exposes via MCP to Microsoft Copilot. The realistic shape isn't "Vantage writes 10 connectors":

```
Vantage  --MCP-->  Vantage's own MCP server  (today's 9 named tools)
         --MCP-->  Atlassian MCP server       (Teamwork Graph)
         --MCP-->  Salesforce / Zendesk MCP   (when they ship)
         --MCP-->  Acme's in-house ops MCP    (custom internal tools)
```

Vantage becomes an **MCP client of multiple specialised MCP servers**, with our own thin context graph on top for Acme-specific reasoning (cross-source joins, computed risk, signal deduplication) that no single source can provide. That dramatically reduces the "huge DB" burden the framing initially suggests.

## What stays the same vs what changes
The dividend of [ADR-003](05-Decisions/ADR-003-mcp-server.md) lands hardest here: the agent doesn't touch the data layer, only named tools.

| Layer | Today (assessment) | Production (Acme stack) | Change? |
|---|---|---|---|
| Agent loop ([ADR-001](05-Decisions/ADR-001-agent-framework.md)) | Claude + tools | Claude + tools | **none** |
| 5 tool names / signatures | `get_open_issues(customer)`… | `get_open_issues(customer)`… | **none** |
| RBAC at the tool boundary ([ADR-002](05-Decisions/ADR-002-rbac-tool-boundary.md)) | inside each tool | inside each tool | **none** |
| Skills (runner, whitelist, authoring) | unchanged | unchanged | **none** |
| Redis multi-turn memory | unchanged | unchanged | **none** |
| API contract (`/ask`, `/skills/*`) | unchanged | unchanged | **none** |
| Evals + observability | unchanged | unchanged | **none** |
| **Inside each tool** | parameterised SQL on our Postgres | call upstream MCP / source APIs + map results | **all integration logic** |
| **Postgres** | system of record | scoped context graph + signals + embeddings | **biggest shift** |
| **Auth to sources** | one DB connection | per-service OAuth, secrets manager, source-side ACL re-checks | **new** |

The entire integration story is contained **below the MCP boundary**.

## Data-shape adaptation (canonical schema + per-source mappers)
External platforms don't speak our schema. Zendesk's ticket:
- `status ∈ {new, open, pending, hold, solved, closed}` — different vocab
- `priority ∈ {low, normal, high, urgent}` — different vocab
- `tags` (free-form) instead of our enumerated `category`
- different identity model (`requester_id` + `organization_id`)

Pattern: a **canonical schema in code** (our current shape is the target) + **per-source mappers** (`ZendeskTicketMapper.to_internal(t) → Issue`) that normalise vocabulary, classify free-form tags to our category enum (rules-based, or LLM-assisted on first touch), and cache the mapping. Same for Salesforce → `Customer`, Persona → `KYC case`. Adapter tests + schema versioning catch source-side drift.

## Honest unseen problems (and how the industry handles each)

| Problem | Handling |
|---|---|
| **Stale data** | Webhook + periodic reconciliation; surface `data_age_seconds` on signals so the UI is honest; never use the cache for compliance-critical writes (those go to source live). |
| **Incorrect pulls / mapping errors** | Per-source adapter tests; schema versioning; canary records that should always parse; alert on adapter failures. |
| **Permission drift** | Cache is "fastest available", not authoritative. Re-check source ACLs at read time (Atlassian Rovo's pattern). Cheap — one source-API call validates a cached read. |
| **Source-of-truth conflicts** | Writes pass through to source and read-back to reconcile; explicit field-level policy ("Salesforce wins on account fields; Vantage's next_action wins until source acknowledges"). |
| **Schema drift** | Adapter contract tests run against the actual source API (canary); breakage alerts before user-visible failure. |
| **Cost / infra weight** | The genuine reason small companies *buy* Glean / Moveworks / Rovo instead of building. Connectors + sync + monitoring is real infra. |
| **Audit complexity** | Writes go to source; reads might come from cache; log at both layers, key by source-side IDs so the trail joins back. |

## Is this actually a great idea for a platform?
Honest, stage-dependent:

- **As a pattern** — yes, demonstrably. The 2026 industry has converged on it (Atlassian Teamwork Graph, M365 Graph, Glean, Moveworks, ServiceNow's acquisition of Moveworks for this exact capability). It works.
- **For Acme specifically** — depends on stage.
  - Startup (<$10M ARR): probably over-engineering vs. just using Zendesk + a thin AI feature in their existing tools. Buy Glean.
  - Mid-market ($50M+ ARR, dozens of ops staff): the ROI lands — cross-source observation pays for itself in incidents caught early.
  - Stripe-scale: table stakes; competitors will have it.
- **The risk to be honest about** — building it well takes 6-12 months of serious infra investment. The hard problem at scale isn't the wiring (that's solved); it's the **trust UX** on top of the signals (see [11-Future](11-Future.md) §Honest pushbacks).

## Why our design ages well into this
- **MCP boundary is the seam.** Replacing a tool's guts (SQL → upstream MCP call) doesn't touch the agent, RBAC, skills, or evals.
- **Named tools, not a generic SQL MCP.** The naive "agent talks to Postgres via a generic MCP" pattern would force a complete rewrite for production. Ours doesn't.
- **RBAC in the tools, not the prompt** ([ADR-002](05-Decisions/ADR-002-rbac-tool-boundary.md)). Layers on top of source-side ACLs cleanly — Keycloak gates *what the user can ask*; source credentials gate *how we fetch it*.
- **MCP-of-MCPs is native** — we already speak MCP both ways; consuming upstream MCP servers is the same protocol shift Atlassian made to integrate with Microsoft Copilot.
- **Postgres → context graph** is a substitution, not a rewrite. Schema changes (add `observations`, `cross_source_links`, `embeddings`); tool internals change; everything above stays.

## Bottom line
> Production Vantage doesn't own data, but it does own a **scoped context graph** — relationships, signals, embeddings — that makes proactive cross-source observation possible without becoming a parallel system of record. The integration logic lives entirely **below our MCP tool boundary**; the agent, RBAC, skills, and evals don't change. The expensive parts are connectors, sync, conflict resolution, and the trust UX — not the agent architecture we already built.
