---
title: NOW — Vantage cursor
type: cursor
status: active
updated: 2026-05-27
---

# NOW — where we are

> [!NOTE] Cursor — single source of truth; overwritten each session; start here. (Plain Markdown links, GitHub-renderable.)

**Project:** Vantage — agentic enterprise assistant for *Acme Operations* (B2B payments platform). EY Applied AI Engineer take-home.
**Deadline:** 2026-06-02. One-hour panel follows.
**Status:** ✅ Full stack integrated & running on `main` in Codespaces. CI + branch protection live. Ready to build the agent's tools.

## Proven (Codespace, `main`)
- `docker compose up` → db + redis + keycloak + api all healthy.
- Seed loaded: 12 customers · 40 issues · 132 updates · 14 next-actions.
- Auth: `support`→`support_user`, `admin-user`→`admin`; forged/missing tokens → 401.

## Repo / CI / flow
- `main` = integrated full stack. **Protected:** PR required + `ci` check must pass (strict; admin-bypass kept).
- **CI:** `ci.yml` (general — compose validate, deps, import/syntax) runs on **every PR into main**; `data-ci.yml` (deep data tests) runs on data PRs.
- **Build flow:** feature branch → PR → CI green → merge. (Docs/cursor may go via admin-bypass.)

## Decisions: ADR-001…007 ([05-Decisions](05-Decisions/)) · Security: [09-Security](09-Security.md)

## Next 3 moves (all via the PR flow)
1. **First tool — `get_customer_profile`**: a standalone, typed, RBAC-checked function (parameterised SQL) querying the seeded DB; wire it into a minimal **agent loop** (Claude tool-calling) behind the auth gate. Feature branch → PR.
2. **Remaining read tools** (`get_open_issues`, `summarise_issue_history`) + the **custom MCP server** (HTTP) exposing them.
3. **Write tools** (`update_issue`, `create`/`update_next_action`) + the RBAC **denial** case + Redis session memory.

## Open questions
- Demo-day rehearsal on Codespaces (idle 90m; screen-recording fallback).
- Required-check ruleset can later add `data-ci` + eval once those gate cleanly.
