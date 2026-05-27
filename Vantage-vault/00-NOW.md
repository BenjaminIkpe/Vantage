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
**Status:** ✅ **Agentic core live** — `POST /ask` runs a Claude tool-calling loop over `get_customer_profile`, validated end-to-end against the seeded data.

## Proven (Codespace, `main`)
- `docker compose up` → db+redis+keycloak+api healthy; seed 12/40/132/14; auth (support/admin) + 401 on bad tokens.
- **`POST /ask`** (auth-gated): "Velocity"→grounded profile · "Lumen"→asks which (E2, no guess) · "Zzzz"→not found (E1, no invention). Tool-call `trace` returned (observability).
- Tools: `get_customer_profile` (parameterised SQL; RBAC in the tool).

## Repo / flow
- `main` protected (PR + `ci` required; admin-bypass). `ci.yml` on every PR; `data-ci.yml` on data PRs. Build = feature branch → PR → CI → merge.

## Decisions: ADR-001…007 ([05-Decisions](05-Decisions/)) · Security: [09-Security](09-Security.md)

## Next moves (via PR flow)
1. **Remaining read tools** — `get_open_issues`, `summarise_issue_history` — then stand up the **custom MCP server** (HTTP) and have the agent consume tools *via MCP* (the brief's MCP **Must**; ADR-003).
2. **Write tools** — `update_issue`, `create`/`update_next_action` — + the RBAC **denial** case + **Redis** multi-turn session memory (story X1).
3. **Escalation Summary Skill** → **evals** (5–10) + observability → minimal **UI**.

## Open questions
- MCP not yet wired — tools are currently in-process; it's a Must, so do it with the next tools.
- Demo-day rehearsal on Codespaces (idle 90m; screen-recording fallback).
