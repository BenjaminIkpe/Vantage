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
- [x] **Slice 0** — Codespace + Keycloak + Redis. ✅
- [x] **Slice 1a** — auth gate (JWT verify; forged/missing → 401). ✅
- [x] **Integration** — full stack on `main`; seed loads (12/40/132/14). ✅
- [x] **Slice 1b** — first tool (`get_customer_profile`) **+ agent loop** (`POST /ask`, Claude tool-calling); validated found/ambiguous/not-found. ✅
- [~] **Slice 2** — read tools `get_open_issues`, `summarise_issue_history` ✅ (PR #4); **custom MCP server** (HTTP) so the agent consumes tools via MCP — *next* (the brief's MCP Must).
- [ ] **Slice 3** — write tools (`update_issue`, `create`/`update_next_action`) + RBAC **denial** case + Redis session memory.
- [ ] **Slice 4** — Customer Escalation Summary Skill.
- [ ] **Slice 5** — evals (5–10) + observability; minimal UI.

## Progress log (newest first)
### 2026-05-27 (cont.)
- ✅ **Read tools 2 & 3** — `get_open_issues` + `summarise_issue_history` (PR #4). Shared `_resolve_customer` (get_customer_profile delegates to it — unchanged). Validated end-to-end on the Codespace: the headline query chained all 3 read tools into a grounded escalation summary; E3 zero-open clean; trace returned. (SQL also proven against the committed seed via a throwaway local Postgres while the Codespace was briefly billing-blocked.)
- ✅ **Agentic core working** — `POST /ask` runs a minimal Claude tool-calling loop (ADR-001) over `get_customer_profile`. Validated live: "Velocity"→grounded profile; "Lumen"→asks which (E2, no guess); "Zzzz"→not found (E1, no invention). Merged via PR #3.
- ✅ First tool `get_customer_profile` (PR #2); CI on every PR + branch protection live.
- ✅ Full stack integrated on `main`; auth gate; host pivot Azure→Codespaces.

### 2026-05-27
- Repo + two parallel tracks; full design locked (ADR-001…006).
### 2026-05-26
- Vault scaffolded.

## AI-usage log
| Date | Task delegated to AI | How I reviewed / validated | Issues caught |
| --- | --- | --- | --- |
| 2026-05-26 | Scaffold vault | vs the brief | none |
| 2026-05-27 | Architecture research | web-searched best practice; chose tool-loop over LangGraph | AI leaned heavier first |
| 2026-05-27 | Business context | vs the brief | removed a cross-project "persona" detail |
| 2026-05-27 | Azure provisioning (CLI) | read errors; region/quota diagnostics | my own zsh bug; real cause = SKU lockdown → Codespaces |
| 2026-05-27 | Codespace Docker | inspected creation logs | docker-in-docker feature failed → universal image |
| 2026-05-27 | Auth gate (JWT) | tested valid/missing/tampered tokens | Keycloak issuer mismatch → frontend/backchannel fix |
| 2026-05-27 | Data-track review + integrate | read schema/generator; ran full stack | realm/seed identity mismatch → reconciled |
| 2026-05-27 | Tool + agent loop | ran real /ask queries vs seeded data; checked tool trace | validated grounding (no invented data), E1/E2 behaviour, RBAC, lazy client keeps CI green |
