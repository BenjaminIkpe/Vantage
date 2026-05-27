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
**Status:** ✅ **Full stack INTEGRATED & running on `main`** in Codespaces — data + auth + API together. Parallel tracks converged.

## Proven (Codespace, `main`)
- `docker compose up` → db + redis + keycloak + api all healthy.
- **Seed loaded:** 12 customers · 40 issues · 132 updates · 14 next-actions.
- **Auth:** `support` → `support_user`, `admin-user` → `admin`; forged/missing tokens → 401. Realm user ids aligned to seed `keycloak_id` (token→users join ready for write-tool attribution).

## Branches
- `main` = integrated full stack (both tracks merged). **Build continues here.**
- `track/infra`, `track/data` = retired (merged).
- ⏳ Branch protection on `main` (require `data-ci`) — to set next.

## Decisions: ADR-001…007 ([05-Decisions](05-Decisions/)) · Security: [09-Security](09-Security.md)

## Next 3 moves
1. **Set branch protection** on `main` (require `data-ci`) — then changes go via PR.
2. **Build the 5 tools** (`get_customer_profile`, `get_open_issues`, `summarise_issue_history`, `update_issue`, `create`/`update_next_action`) — RBAC-checked at the tool (ADR-002), parameterised SQL (T3), against the seeded DB.
3. **MCP server** (custom, HTTP) exposing the tools → **agent loop** (Claude tool-calling) behind the auth gate.

## Open questions
- Demo-day rehearsal on Codespaces (idle 90m; screen-recording fallback).
