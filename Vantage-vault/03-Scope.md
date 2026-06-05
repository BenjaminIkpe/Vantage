---
title: Scope — MoSCoW
type: scope
status: locked
updated: 2026-05-28
---

# Scope

> [!NOTE] Purpose
> What's in, what's out, and why. MoSCoW = Must / Should / Could / Won't. Anything cut is recorded here *with a reason* — documented trade-offs matter, not silent gaps.

## Must — core requirements (all must be present)
- [ ] Keycloak authentication + RBAC — roles `sales_user`, `support_user`, `admin`. **Real Keycloak, no mocking.** Login or bearer-token validation.
- [ ] **RBAC enforced at the tool / data layer** (server-side), including ≥1 *denied* case — never in the LLM prompt. (→ ADR)
- [ ] LLM agent with **dynamic** tool selection (no hard-coded answers).
- [ ] Five tools (the core required set): `get_customer_profile` · `get_open_issues` · `summarise_issue_history` · **`update_issue`** · `create` / `update_next_action`. *(We shipped **11** — plus 3 browse tools (PR #21) and 2 admin-only fleet tools `get_high_risk_customers` / `detect_patterns` for the briefing (ADR-008); full list in [04-Architecture](04-Architecture.md).)*
- [ ] Query entry via **API** (a UI is a Should — see below).
- [ ] PostgreSQL — tables `customers`, `issues`, `issue_updates`, `next_actions`, `users` / `user_roles`, seeded with representative data.
- [ ] Redis — **multi-turn session memory** (backs story X1); documented Redis-vs-Postgres rationale.
- [ ] ≥1 MCP (Model Context Protocol) server.
- [ ] ≥1 reusable Skill — Customer Escalation Summary.
- [ ] Docker Compose — one command (`docker compose up`).
- [ ] Evaluation set (5–10 questions) + basic observability (tool logs, request/response traces, errors, latency).
- [ ] Documentation: README, architecture diagram, eval results, AI-usage notes.

## Should — clear value, do once Must is green
- [ ] **Minimal chat UI** — makes the live demo far stronger than curling an API. Kept deliberately simple; gracefully droppable to API + a demo script if time runs short.
  - **Chat-history sidebar (resume previous chats)** — a left rail listing the user's past conversations, click to pick up where they left off (like ChatGPT/Claude/etc.). Leverages our Redis session memory; needs per-user session listing (track session ids per user, since `session:{id}` is keyed by id alone today). Revisit when we build the UI.
- [ ] **Skill authoring via chat — the `/ask` "save this as a skill" trigger** (Flow 1 PR B). The authoring *endpoints* (`draft-from-session` + save) are **built** (PR #10); this is the conversational counterpart — in `/ask`, the agent composes the skill from the session and persists it via a local `save_skill` tool on confirm. Deferred to a Should so we lock the core requirements first.

## Could — nice-to-have, only if ahead
> [!NOTE] Post-Must/Should pickup (2026-06-01)
> With the Musts + core deliverables + Shoulds shipped, two Coulds shipped under **[ADR-008](05-Decisions/ADR-008-langgraph-proactive-path.md)** (hybrid LangGraph) and merged to `main` (PRs #38 + #39): the **bonus tracing** and the **proactive admin briefing**.

- [x] Bonus tracing — OpenTelemetry / LangSmith / Arize Phoenix (optional observability). **Shipped:** OTel→**Phoenix** (self-hosted, no egress) over the reactive loop *and* the briefing graph, plus **LangSmith** opt-in for the graph. (ADR-008.)
- [ ] **Flow 2 — guided Skill authoring** (interview + role-aware suggestions): the app asks what the skill should do and suggests options based on the user's role. The stretch beyond Flow 1, best with the UI.
- [ ] Second Redis use — caching customer lookups.
- [x] Streaming responses (demo polish) — SSE token-by-token via `/ask/stream`; `/briefing/stream` for the briefing.
- [x] **Proactive admin briefing — `GET /briefing`** (admin-only). One call → a ranked digest across **all** customers: who's High/Critical and why (composing today's Escalation Summary skill across the fleet — the *system* picks accounts to brief, contrasting with story **S7** where the user picks 2-3), plus **cross-customer pattern detection** that no per-customer flow can produce (e.g. *"4 accounts hit webhook errors this week — likely platform"*). Adds two new admin-only read tools (`get_high_risk_customers`, `detect_patterns`) — RBAC at the boundary, same as the other nine (11 tools total now) (see [10-Scaling](10-Scaling.md) §Where it strains). **Shipped under [ADR-008](05-Decisions/ADR-008-langgraph-proactive-path.md)** (merged, PR #38) as a **LangGraph** graph (fleet fan-out → patterns → draft) — and, because the graph gives us durable pause/resume cheaply, it now **pulls the draft → approve → route HITL forward** from Phase 2: the AI drafts next actions, the run pauses at an `interrupt()`, an admin approves in the UI, and the approver's token authorizes the real `create_next_action` write. **Still out of scope:** scheduling / a background worker, and persistent observation — those stay [11-Future](11-Future.md) Phase 2. The briefing is the synchronous, on-demand preview.

## Won't — this version (explicitly out, with reason)
- Production-grade Keycloak — we run *real* Keycloak but a dev realm; hardening, single sign-on (SSO), refresh-token flows are out.
- Multi-tenancy / horizontal scale.
- Real external data sources — seeded sample data only.
- Long-term / vector memory — the jobs don't need it.
- Field-level security beyond role-level RBAC.

---
> [!TIP] The discipline
> Commit to **Must**. Earn **Should / Could** only after Must is demoable end-to-end. The **Won't** list protects the timeline — and documents deliberate trade-offs.
