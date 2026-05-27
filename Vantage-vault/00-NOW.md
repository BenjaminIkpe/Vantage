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
**Status:** ✅ **Three read tools live** — `POST /ask` runs a Claude tool-calling loop that *dynamically chains* `get_customer_profile` → `get_open_issues` → `summarise_issue_history`, validated end-to-end against the seeded data (the headline multi-tool query works).

## Proven (Codespace, `main`)
- `docker compose up` → db+redis+keycloak+api healthy; seed 12/40/132/14; auth (support/admin) + 401 on bad tokens.
- **`POST /ask`** (auth-gated), validated live as `support`:
  - "open issues for Velocity Marketplace" → 4 open, ordered critical→high→medium (one tool call).
  - **Headline:** "open issues for Velocity, summarise the most urgent, suggest a next action" → agent chained all 3 read tools; grounded escalation summary (quotes real update bodies — EDD case CDD-4821) + next action. Proves **dynamic tool selection** (ADR-001).
  - "Calm Waters Subscriptions" → "no open issues" (E3, no fabrication). Earlier: "Lumen"→ambiguous (E2) · "Zzzz"→not found (E1).
  - Tool-call `trace` returned on every answer (observability).
- Tools (3 of 5): `get_customer_profile`, `get_open_issues`, `summarise_issue_history` — all parameterised SQL; reads open to any authenticated role; customer-name tools share one `_resolve_customer` (E1/E2 in one place).

## Repo / flow
- `main` protected (PR + `ci` required; admin-bypass). `ci.yml` on every PR; `data-ci.yml` on data PRs. Build = feature branch → PR → CI → merge.

## Decisions: ADR-001…007 ([05-Decisions](05-Decisions/)) · Security: [09-Security](09-Security.md)

## Next moves (via PR flow)
1. **Custom MCP server** (HTTP) — the other half of Slice 2: expose the 3 read tools over MCP as its own Compose service; agent consumes them *via MCP* (the brief's MCP **Must**; ADR-003). Key integration point: thread the verified role across the boundary (ADR-002/003). stdio is the documented fallback.
2. **Write tools** — `update_issue`, `create`/`update_next_action` — + the RBAC **denial** case + **Redis** multi-turn session memory (story X1).
3. **Escalation Summary Skill** → **evals** (5–10) + observability → minimal **UI**.

## Open questions
- MCP not yet wired — the 3 read tools are in-process (PR #4); it's a Must, so it's the immediate next move.
- Demo-day rehearsal on Codespaces (idle 90m; screen-recording fallback).
