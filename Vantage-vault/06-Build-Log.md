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
- [ ] **Slice 0 — infra skeleton.** Codespace (docker-in-docker) + `docker compose up` with **Keycloak** (login/token + one role check). Hardest infra; prove it first.
- [ ] **Slice 1 — data + one read path.** Postgres schema + seed (Faker+Claude); `get_customer_profile` end-to-end through the agent loop.
- [ ] **Slice 2 — MCP + remaining reads.** Custom MCP server over HTTP; `get_open_issues`, `summarise_issue_history`; RBAC per tool.
- [ ] **Slice 3 — writes + RBAC denial + session.** `update_issue`, `create`/`update_next_action`; the *denied* case; Redis session memory.
- [ ] **Slice 4 — the Skill.** Customer Escalation Summary (risk + recommended action + missing info).
- [ ] **Slice 5 — prove + present.** Eval set (5–10) + observability; then the Should: minimal chat UI.

## Progress log (newest first)
### 2026-05-27
- **Build started, two parallel tracks** (worktrees): infra (`track/infra`) + data (`track/data`).
- Repo scaffolded + pushed to GitHub; base structure, `.gitignore`, README, `.env.example`.
- **Host pivot: Azure → Codespaces.** Azure subscription SKU-locked (VM create failed across all regions/sizes — new-subscription restriction). Pivoted to Codespaces; added `.devcontainer/`. ADR-004 superseded by ADR-007.
- **Earlier:** full design locked (Frame, Stories, Scope, Architecture, data model, ADR-001–006).

### 2026-05-26
- Vault scaffolded (`00`–`08`).

## AI-usage log
| Date | Task delegated to AI | How I reviewed / validated | Issues caught |
| --- | --- | --- | --- |
| 2026-05-26 | Scaffold the documentation vault | Checked structure against the brief's deliverables | none |
| 2026-05-27 | Research + reason through architecture | Web-searched best practice per decision; chose the *simpler* option (tool-loop over LangGraph) on judgement | AI leaned toward a heavier framework first; corrected via the brief |
| 2026-05-27 | Draft business context | Cross-checked vs the actual brief | Caught an "expense-management/persona" detail bleeding in from another project; removed it |
| 2026-05-27 | Drive Azure VM provisioning via CLI | Read the actual errors; ran a region/quota diagnostic before concluding | Caught **my own** zsh word-split bug in a retry loop (false "no capacity"); then correctly diagnosed the real cause = new-subscription SKU lockdown → pivoted to Codespaces |
