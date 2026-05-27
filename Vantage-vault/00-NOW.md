---
title: NOW — Vantage cursor
type: cursor
status: active
updated: 2026-05-27
---

# NOW — where we are

> [!NOTE] How this file works
> Cursor: the single source of truth for where the project is right now. Overwritten each session. Start here. (Plain Markdown links, GitHub-renderable.)

**Project:** Vantage — agentic enterprise assistant for *Acme Operations* (a B2B payments platform). EY Applied AI Engineer take-home.
**Deadline:** 2026-06-02. One-hour panel follows.
**Status:** ✅ **Slice 0 + 1a DONE** — full stack (Keycloak + Redis + API) running in **GitHub Codespaces**; **auth gate validated end-to-end** (JWT verified, role extracted, forged/missing tokens → 401).

## Parallel build (worktrees, disjoint files)
- **Track A — infra/API** (`track/infra`, this dir): devcontainer, docker-compose (db/redis/keycloak/api), Keycloak realm, FastAPI auth gate. **Running.**
- **Track B — data** (`track/data`, `/Users/benji/code/Vantage-data`): schema + seed, validating against local Postgres.
- Next integration: merge Track B so the DB + tools come online.

## Proven in the Codespace
- `docker compose up` → Keycloak + Redis + API.
- `/health` ok; `/ready` green (redis + keycloak).
- `support` → token → `/whoami` → `{username: support, roles: [support_user]}`. No/tampered token → **401**.

## Decisions: ADR-001…007 ([05-Decisions](05-Decisions/)) · Security model: [09-Security](09-Security.md)

## Next 3 moves
1. **Merge Track B (data)** → `db/schema.sql` + `db/seed.sql` into the running stack (Postgres init).
2. **Build the 5 tools** (`get_customer_profile`, `get_open_issues`, `summarise_issue_history`, `update_issue`, `create`/`update_next_action`) — each RBAC-checked (T2), parameterised SQL (T3), exposed via the MCP server.
3. **Agent loop** (Claude tool-calling) wiring the tools, behind the auth gate.

## Open questions
- Track B status — coordinate the merge (it owns `db/`, `scripts/`).
- Demo-day rehearsal on Codespaces (idle timeout 90m set; screen-recording fallback).
