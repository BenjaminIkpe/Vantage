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
**Status:** ✅ Full stack running on `main`; CI + branch protection live; **first agent tool merged** (`get_customer_profile`). Dev flow (branch → PR → CI → merge) proven.

## Proven (Codespace, `main`)
- `docker compose up` → db + redis + keycloak + api healthy. Seed: 12/40/132/14.
- Auth: `support`/`admin-user` authenticate; forged/missing → 401.
- **`get_customer_profile`** (parameterised SQL, auth-gated): `Velocity`→found · `Lumen`→ambiguous (E2) · `Zzzz`→not_found (E1). ✅

## Repo / CI / flow
- `main` protected: PR + `ci` check required (strict; admin-bypass kept). `ci.yml` on every PR; `data-ci.yml` on data PRs.
- Build flow: feature branch → PR → CI green → merge. (Tool PR #2 merged this way.)

## Decisions: ADR-001…007 ([05-Decisions](05-Decisions/)) · Security: [09-Security](09-Security.md)

## Next 3 moves (via the PR flow)
1. **Agent loop** — Claude tool-calling that uses `get_customer_profile`, behind the auth gate; a `POST /ask` endpoint. ⚠️ **Needs `ANTHROPIC_API_KEY` in the Codespace** (`gh codespace secret set ANTHROPIC_API_KEY`, or Codespaces settings) — set this before the loop can run.
2. **Remaining read tools** (`get_open_issues`, `summarise_issue_history`) + the **custom MCP server** (HTTP) exposing them.
3. **Write tools** (`update_issue`, `create`/`update_next_action`) + the RBAC **denial** case + Redis session memory.

## Open questions
- Anthropic key for the Codespace (next-move prerequisite, above).
- Demo-day rehearsal on Codespaces (idle 90m; screen-recording fallback).
