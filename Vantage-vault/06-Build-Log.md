---
title: Build Log
type: build-log
status: active
updated: 2026-05-27
---

# Build Log

> [!NOTE] Purpose
> Thin-slice plan + dated progress + the AI-usage log. The AI-usage table feeds Deliverable 5 and the panel's AI-tooling questions (brief §4.9) — fill it as you go.

## Thin-slice plan (de-risk first; one full path before widening)
- [x] **Slice 0 — infra skeleton.** Codespace (Docker) + `docker compose up` with Keycloak + Redis. ✅
- [x] **Slice 1a — auth gate.** FastAPI API; full Keycloak JWT verification; `/health` `/ready` `/whoami`; forged/missing tokens → 401. ✅
- [ ] **Slice 1b — data + one read tool.** Merge Track B (schema + seed); `get_customer_profile` end-to-end.
- [ ] **Slice 2 — MCP + remaining reads.** Custom MCP server (HTTP); `get_open_issues`, `summarise_issue_history`; RBAC per tool.
- [ ] **Slice 3 — writes + RBAC denial + session.** `update_issue`, `create`/`update_next_action`; denial case; Redis session memory.
- [ ] **Slice 4 — the Skill.** Customer Escalation Summary.
- [ ] **Slice 5 — prove + present.** Eval set (5–10) + observability; then the Should: minimal chat UI.

## Progress log (newest first)
### 2026-05-27 (cont.)
- ✅ **Auth gate validated end-to-end** in the Codespace: Keycloak+Redis+API up; `support` user token → `/whoami` returns verified username + role; no/tampered tokens → 401.
- API skeleton built: `/health`, `/ready` (redis+keycloak), `/whoami`; JWT verification (RS256/JWKS, issuer, expiry; `alg:none` rejected).
- **Host pivot Azure → Codespaces** (Azure SKU-locked across all regions). Fixed Codespace Docker via the **universal image** (the docker-in-docker feature wouldn't install on a python base).

### 2026-05-27
- Repo scaffolded + pushed; two parallel tracks (infra + data). Full design locked (Frame, Stories, Scope, Architecture, ADR-001…006).
### 2026-05-26
- Vault scaffolded.

## AI-usage log
| Date | Task delegated to AI | How I reviewed / validated | Issues caught |
| --- | --- | --- | --- |
| 2026-05-26 | Scaffold the vault | Checked vs the brief's deliverables | none |
| 2026-05-27 | Research + reason through architecture | Web-searched best practice; chose the simpler option (tool-loop, not LangGraph) | AI leaned heavier first; corrected via the brief |
| 2026-05-27 | Draft business context | Cross-checked vs the brief | removed an "expense-management/persona" detail bled in from another project |
| 2026-05-27 | Drive Azure VM provisioning (CLI) | Read errors; ran region/quota diagnostics | caught my own zsh loop bug; diagnosed real cause = new-subscription SKU lockdown → pivoted to Codespaces |
| 2026-05-27 | Codespace + Docker setup | Inspected creation logs; checked docker presence | docker-in-docker feature failed on python base → switched to universal image |
| 2026-05-27 | Auth gate (JWT verification) | Tested with valid / missing / tampered tokens | caught Keycloak **issuer mismatch** (frontend vs backchannel host) → fixed with KC_HOSTNAME + KEYCLOAK_ISSUER; tampered-token test confirms signature rejection |
