---
title: NOW — Vantage cursor
type: cursor
status: active
updated: 2026-05-27
---

# NOW — where we are

> [!NOTE] Cursor — overwritten each session; start here. Plain Markdown links (GitHub-renderable).

**Project:** Vantage — agentic assistant for *Acme Operations* (B2B payments). EY Applied AI Engineer take-home.
**Deadline:** 2026-06-02. One-hour panel follows.
**Status:** ✅ **MCP wired (Slice 2 done)** — the agent is now an **MCP client**: it *discovers* the 3 read tools from a custom **MCP server** (own Compose service, Streamable HTTP) and calls them by name. The API holds **no DB access**; tools run behind the MCP boundary, which **re-verifies the forwarded Keycloak token** and enforces RBAC per tool (ADR-002/003).

## Proven (Codespace, `main`)
- `docker compose up` → db+redis+keycloak+**mcp**+api healthy; seed 12/40/132/14; auth (support/admin) + 401 on bad tokens.
- **`POST /ask`** (auth-gated), validated live as `support`, every answer flowing API → agent (MCP client) → MCP server (re-verify + RBAC) → Postgres:
  - "open issues for Velocity Marketplace" → 4 open, critical→high→medium (one MCP tool call).
  - **Headline:** "open issues for Velocity, summarise the most urgent, suggest a next action" → agent chained `get_open_issues` → `summarise_issue_history` over MCP; grounded escalation summary (quotes real update bodies — EDD case CDD-4821) + next action. Proves **dynamic tool selection** (ADR-001).
  - "Calm Waters Subscriptions" → "no open issues" (E3). Earlier: "Lumen"→ambiguous (E2) · "Zzzz"→not found (E1).
  - `POST /ask` with no/invalid token → **401**; MCP `smoke_test.py` also confirms the MCP server itself rejects a bad token before any tool runs.
  - Tool-call `trace` returned on every answer (observability).
- Tools (3 of 5): `get_customer_profile`, `get_open_issues`, `summarise_issue_history` — discovered via MCP; parameterised SQL; reads open to any authenticated role; customer-name tools share one `_resolve_customer` (E1/E2 in one place). Live in `mcp_server/` (dir named to avoid shadowing the `mcp` SDK; compose service is `mcp`).

## Repo / flow
- `main` protected (PR + `ci` required; admin-bypass). `ci.yml` on every PR; `data-ci.yml` on data PRs. Build = feature branch → PR → CI → merge.

## Decisions: ADR-001…007 ([05-Decisions](05-Decisions/)) · Security: [09-Security](09-Security.md)

## Next moves (via PR flow)
1. **Write tools** (Slice 3) — `update_issue` (support+admin), `create`/`update_next_action` (admin) — added to the **MCP server** (they appear to the agent via discovery automatically). Brings the **RBAC denial** case (sales→update, support→next-action: denied + logged, S3/SU3) — the role is already re-verified at the MCP boundary, so the tool just checks it. + **Redis** multi-turn session memory (story X1).
2. **Escalation Summary Skill** (Slice 4) → **evals** (5–10) + observability (Slice 5) → minimal **UI**.

## Open questions
- Write-tool RBAC denial is the first place a tool gates on role — confirm the denial surfaces cleanly through the agent's answer (not just an exception) and is logged (T7: identifiers, not tokens).
- Demo-day rehearsal on Codespaces (idle 90m; screen-recording fallback).
