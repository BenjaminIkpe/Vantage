---
title: Build Log
type: build-log
status: active
updated: 2026-05-27
---

# Build Log

> [!NOTE] Purpose
> Thin-slice plan + dated progress + the AI-usage log. The AI-usage table feeds Deliverable 5 and the panel's AI-tooling questions (brief §4.9) — fill it as you go, not at the end.

## Thin-slice plan (de-risk first; one full path before widening)
- [ ] **Slice 0 — infra skeleton.** Azure VM + `docker compose up` with **Keycloak** (login/token + one role check). Hardest infra; prove it first.
- [ ] **Slice 1 — data + one read path.** Postgres schema + seed (Faker+Claude); `get_customer_profile` end-to-end through the agent loop (CLI/API).
- [ ] **Slice 2 — MCP + remaining reads.** Custom MCP server over HTTP exposing the read tools; `get_open_issues`, `summarise_issue_history`; RBAC enforced in each tool.
- [ ] **Slice 3 — writes + RBAC denial + session.** `update_issue`, `create`/`update_next_action`; the *denied* case; Redis multi-turn session memory.
- [ ] **Slice 4 — the Skill.** Customer Escalation Summary (risk level + recommended action + missing info).
- [ ] **Slice 5 — prove + present.** Eval set (5–10) + observability (tool logs, traces, latency); then the Should: minimal chat UI.

## Progress log (newest first)
### 2026-05-27
- **Full design locked.** Business context (Acme = B2B payments platform), data model (5 tables), and ADRs 001–006: agent loop (not LangGraph), RBAC at the tool boundary, custom MCP over HTTP, Azure VM, seed strategy, Redis/Postgres split.
- Frame, User Stories, Scope locked earlier in the session.

### 2026-05-26
- Vault scaffolded (`00`–`08`).

## AI-usage log
| Date | Task delegated to AI | How I reviewed / validated | Issues caught |
| --- | --- | --- | --- |
| 2026-05-26 | Scaffold the documentation vault | Checked structure against the brief's deliverables; confirmed one-vault decision | none |
| 2026-05-27 | Research + reason through architecture (agent framework, MCP, RBAC, memory) | Web-searched current best practice for each; pushed back and chose the *simpler* option (tool-loop over LangGraph) on judgement | AI leaned toward a heavier framework first; corrected by mapping needs to the brief |
| 2026-05-27 | Draft business context / domain | Cross-checked against the actual brief text | Caught a conflation — an "expense-management/persona" detail had bled in from a different project; removed it (the brief leaves Acme's business open) |
