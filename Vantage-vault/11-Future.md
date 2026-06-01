---
title: Future — where Vantage goes next (the proactive observer paradigm)
type: future
status: active
updated: 2026-05-28
---

# Future — where Vantage goes next

> [!NOTE] Purpose
> Panel-grade answer to *"if you kept building, where does this go?"* — the natural Phase 2 direction (proactive / context-aware), what it'd take, what we'd push back on, and why the architecture already accommodates it. Cross-refs: [03-Scope §Could](03-Scope.md), [04-Architecture](04-Architecture.md), [ADR-002](05-Decisions/ADR-002-rbac-tool-boundary.md), [ADR-003](05-Decisions/ADR-003-mcp-server.md), [10-Scaling](10-Scaling.md).

## Short answer
**Vantage today is a reactive copilot** — a user asks, the agent answers. The natural Phase 2 — the direction industry tools (ServiceNow, Atlassian, Moveworks) have moved — is a **continuous observer with human-in-the-loop proposals**: the AI watches the DB, surfaces signals nobody asked for yet, and proposes work for humans to approve. The Could-scoped admin briefing endpoint (see [03-Scope](03-Scope.md)) is the on-demand *teaser* of this paradigm; the full thing is what's below.

## The paradigm shift

| | Today (reactive) | Phase 2 (proactive) |
|---|---|---|
| Trigger | a user query | a scheduled scan / a DB change |
| Posture | request → tool → answer | continuous observation + push |
| Cross-customer view | none (per-account tools) | first-class (fleet patterns) |
| Audience | the user who asked | role-aware push (each role sees their slice) |
| Action loop | agent proposes, user acts | agent proposes, **admin approves**, system routes |

It is *not* a different agent design — it is the **same tools, same RBAC, same skills**, called by a **background runner acting as a scheduled user**, with one extra step on the way out: a proposal a human approves.

## The four layers (each adds on top of the previous)
1. **Persistent context awareness.** A background runner periodically scans the DB and runs the Escalation Summary skill (and others) across all customers; deltas (e.g. Velocity went Medium→Critical overnight) are flagged. Storage: one small new table (`observations` / `signals`) keyed by `customer_id` + signal type, so the system knows what it's already surfaced.
2. **Cross-customer pattern detection.** Aggregations the per-account flow is structurally blind to: clusters by category in a window (4 customers with webhook errors → "likely platform"), spikes in failed payouts, slow-burn KYC backlogs. New (admin-only) tool: `detect_patterns(window)` — same MCP boundary, parameterised SQL.
3. **Role-aware push surfacing.** Sales sees account-level risks; support sees clusters in their queue; admin sees platform signals. Reuses the role from the token; the *channel* is new (UI inbox, email/Slack/Teams). Push respects the same RBAC the pull does — a signal can never expose data the role couldn't have pulled.
4. **Propose → approve → route.** AI drafts a `next_action` (or a Sev-N incident) in a *pending* state; an admin approves/rejects; the system writes the real `next_action` row via the existing tool and routes the work (Slack to a team channel, ticket-system webhook). Schema: a `next_action_drafts` table or a `pending` enum value on `next_actions`. Approval flow + audit trail. *(The **approve → write** half is now previewed on-demand by `/briefing` via the LangGraph `interrupt()` gate — [ADR-008](05-Decisions/ADR-008-langgraph-proactive-path.md); what stays Phase 2 here is the durable pending-state schema and the outward **routing** to Slack/ticket webhooks.)*

## Honest pushbacks
- **Trust is the hard part, not detection.** Counting critical issues is easy. Getting humans to act on AI signals at the *right rate* — not rubber-stamping, not ignoring — is the unsolved UX/governance problem ServiceNow is still working through. Phase 2 needs confidence scoring, reasoning traces (we already produce one — [00-NOW](00-NOW.md)), and an explicit *"why this matters now"* per signal.
- **Acme is B2B payments, not internal IT.** ServiceNow/Moveworks operate inside one company; Acme's tickets involve **external customers**. Vantage doesn't shorten the *fix* — Acme's platform team still ships it — only **detection-to-decision**. Still high value (4 customer tickets prevented by one upstream incident caught early), but the framing matters: Vantage stays a copilot for *Acme staff*, not an autonomous remediator.
- **Auto-action is still out.** The agent never performs privileged actions without an admin approving. The *"LLM proposes, the tool disposes"* rule from [ADR-002](05-Decisions/ADR-002-rbac-tool-boundary.md) holds — the admin is the new "tool".

## Why our design ages well into this
- **Tools are named and contained ([ADR-003](05-Decisions/ADR-003-mcp-server.md)).** A background runner is just another MCP client; the new aggregate tool sits behind the same RBAC boundary as the existing five.
- **RBAC lives in the tools ([ADR-002](05-Decisions/ADR-002-rbac-tool-boundary.md)).** A scheduled "service" caller carries a role (a service account with limited rights). The boundary it crosses is identical to a human's.
- **Postgres is the system of record ([ADR-006](05-Decisions/ADR-006-memory-split.md)).** The observer reads the same store; observations join back to existing ids; no parallel data plane.
- **Skills are prompt + tool whitelist.** Phase 2 mostly *composes new skills* over slightly more tools — not new agent code. User-authored skills (already shipped in Flow 1) point in the same direction: the system gets more **configurable**, not more **bespoke**.

## What today's `/briefing` (Could) is, and isn't
*(Built under [ADR-008](05-Decisions/ADR-008-langgraph-proactive-path.md) as a hybrid **LangGraph** path — the loop still serves reactive `/ask`.)*
- **Is:** the on-demand demo of fleet view + cross-customer patterns, generated synchronously when an admin calls it — **plus a thin slice of layer 4 pulled forward**: the graph drafts next actions, pauses at an `interrupt()`, an admin approves in the UI, and the *approver's* token authorizes the real `create_next_action` write (durable pause/resume via a Redis checkpointer). So the **propose → approve → route** loop is *previewed* end-to-end, for the accounts the briefing surfaces.
- **Isn't:** the **persistent/scheduled observer** (still no background worker — the briefing is on-demand, not a continuous scan), the **role-aware push channels** (still admin-only, pull not push), or **cross-run signal memory** (no `observations` table yet — each briefing is stateless beyond its own paused run). Those remain Phase 2.

## Where the data lives in production
The observer paradigm above assumes Vantage can scan the data continuously. In production, that data actually lives across Acme's existing platforms (Zendesk, Salesforce, Persona, …). [13-Integration](13-Integration.md) walks through how the **scoped-context-graph** pattern reconciles *"we don't own the data"* with *"we observe continuously"* — and how our MCP design absorbs that without changing anything above the tool boundary.

## Bottom line
> The architecture we built for the brief generalises into the proactive paradigm without rework: the same MCP tools called by a background runner, one new table for observations, one new tool for cross-customer aggregates, and a propose-approve-route layer on top. The hard problem isn't the wiring — it's the trust UX and the *"Acme is not internal IT"* framing. The Could-scoped admin briefing endpoint demonstrates the *shape* of the proactive idea on top of today's reactive tools.
