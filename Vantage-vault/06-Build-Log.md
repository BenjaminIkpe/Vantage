---
title: Build Log
type: build-log
status: active
updated: 2026-05-27
---

# Build Log

> [!NOTE] Purpose
> Thin-slice plan + dated progress + the AI-usage log (feeds Deliverable 5 / panel §4.9).

## Thin-slice plan
- [x] **Slice 0 — infra skeleton.** Codespace + Keycloak + Redis. ✅
- [x] **Slice 1a — auth gate.** Full JWT verification; forged/missing → 401. ✅
- [x] **Integration — full stack on `main`.** Both tracks merged; db loads seed (12/40/132/14); both roles authenticate. ✅
- [ ] **Slice 1b — first read tool.** `get_customer_profile` end-to-end through the agent.
- [ ] **Slice 2 — MCP + remaining reads.** Custom MCP server (HTTP); `get_open_issues`, `summarise_issue_history`; RBAC per tool.
- [ ] **Slice 3 — writes + RBAC denial + session.** `update_issue`, `create`/`update_next_action`; denial case; Redis session.
- [ ] **Slice 4 — the Skill.** Customer Escalation Summary.
- [ ] **Slice 5 — prove + present.** Evals + observability; minimal UI.

## Progress log (newest first)
### 2026-05-27 (cont.)
- ✅ **Full stack integrated on `main`** — merged Track B (data, PR #1) + Track A (infra) → main. `docker compose up` runs db+redis+keycloak+api; **seed loads (12/40/132/14)**; `support`/`admin-user` authenticate.
- Reviewed Track B's code (schema + hybrid seed + CI): on-design (ADR-002/005). **Caught + fixed a cross-track identity mismatch** — realm user ids/emails ≠ seed `keycloak_id` → aligned so token→users joins for attribution.
- ✅ Auth gate validated (Slice 1a); host pivot Azure→Codespaces (universal image).

### 2026-05-27
- Repo + two parallel tracks; full design locked (ADR-001…006).
### 2026-05-26
- Vault scaffolded.

## AI-usage log
| Date | Task delegated to AI | How I reviewed / validated | Issues caught |
| --- | --- | --- | --- |
| 2026-05-26 | Scaffold vault | vs the brief's deliverables | none |
| 2026-05-27 | Architecture research | web-searched best practice; chose tool-loop over LangGraph | AI leaned heavier first |
| 2026-05-27 | Business context | vs the actual brief | removed a cross-project "persona" detail |
| 2026-05-27 | Azure provisioning (CLI) | read errors; ran region/quota diagnostics | my own zsh loop bug; real cause = new-subscription SKU lockdown → pivoted to Codespaces |
| 2026-05-27 | Codespace Docker | inspected creation logs | docker-in-docker feature failed on python base → universal image |
| 2026-05-27 | Auth gate (JWT) | tested valid / missing / tampered tokens | Keycloak issuer mismatch → frontend/backchannel fix |
| 2026-05-27 | Data-track review + integrate | read schema/generator; ran full stack; verified counts + auth | realm/seed identity mismatch → reconciled before it bit the write tools |
