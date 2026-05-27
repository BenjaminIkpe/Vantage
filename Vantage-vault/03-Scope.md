---
title: Scope — MoSCoW
type: scope
status: locked
updated: 2026-05-27
---

# Scope

> [!NOTE] Purpose
> What's in, what's out, and why. MoSCoW = Must / Should / Could / Won't. Anything cut is recorded here *with a reason* — assessors reward documented trade-offs, not silent gaps.

## Must — required by the brief (all must be present)
- [ ] Keycloak authentication + RBAC — roles `sales_user`, `support_user`, `admin`. **Real Keycloak, no mocking.** Login or bearer-token validation.
- [ ] **RBAC enforced at the tool / data layer** (server-side), including ≥1 *denied* case — never in the LLM prompt. (→ ADR)
- [ ] LLM agent with **dynamic** tool selection (no hard-coded answers).
- [ ] Five tools: `get_customer_profile` · `get_open_issues` · `summarise_issue_history` · **`update_issue`** *(5th)* · `create` / `update_next_action`.
- [ ] Query entry via **API** (a UI is a Should — see below).
- [ ] PostgreSQL — tables `customers`, `issues`, `issue_updates`, `next_actions`, `users` / `user_roles`, seeded with representative data.
- [ ] Redis — **multi-turn session memory** (backs story X1); documented Redis-vs-Postgres rationale.
- [ ] ≥1 MCP (Model Context Protocol) server.
- [ ] ≥1 reusable Skill — Customer Escalation Summary.
- [ ] Docker Compose — one command (`docker compose up`).
- [ ] Evaluation set (5–10 questions) + basic observability (tool logs, request/response traces, errors, latency).
- [ ] Deliverables: README, architecture diagram, eval results, AI-usage notes.

## Should — clear value, do once Must is green
- [ ] **Minimal chat UI** — makes the live demo far stronger than curling an API. Kept deliberately simple; gracefully droppable to API + a demo script if time runs short.
  - **Chat-history sidebar (resume previous chats)** — a left rail listing the user's past conversations, click to pick up where they left off (like ChatGPT/Claude/etc.). Leverages our Redis session memory; needs per-user session listing (track session ids per user, since `session:{id}` is keyed by id alone today). Revisit when we build the UI.
- [ ] **Skill authoring via chat — the `/ask` "save this as a skill" trigger** (Flow 1 PR B). The authoring *endpoints* (`draft-from-session` + save) are **built** (PR #10); this is the conversational counterpart — in `/ask`, the agent composes the skill from the session and persists it via a local `save_skill` tool on confirm. Deferred to a Should so we lock the graded deliverables first.

## Could — nice-to-have, only if ahead
- [ ] Bonus tracing — OpenTelemetry / LangSmith / Arize Phoenix (stated bonus in the brief).
- [ ] **Flow 2 — guided Skill authoring** (interview + role-aware suggestions): the app asks what the skill should do and suggests options based on the user's role. The stretch beyond Flow 1, best with the UI.
- [ ] Second Redis use — caching customer lookups.
- [ ] Streaming responses (demo polish).
- [ ] Cross-account oversight listing tool for `admin` (e.g. "all high-risk accounts").

## Won't — this version (explicitly out, with reason)
- Production-grade Keycloak — we run *real* Keycloak but a dev realm; hardening, single sign-on (SSO), refresh-token flows are out.
- Multi-tenancy / horizontal scale.
- Real external data sources — seeded sample data only.
- Long-term / vector memory — the jobs don't need it.
- Field-level security beyond role-level RBAC.

---
> [!TIP] The discipline
> Commit to **Must**. Earn **Should / Could** only after Must is demoable end-to-end. The **Won't** list protects the 7 days — and is what you cite in the panel as deliberate trade-offs.
