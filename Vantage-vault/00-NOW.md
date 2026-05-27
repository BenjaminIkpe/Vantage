---
title: NOW — Vantage cursor
type: cursor
status: active
updated: 2026-05-27
---

# NOW — where we are

> [!NOTE] How this file works
> This is the cursor: the single source of truth for *where the project is right now*. It is **overwritten** each working session, not appended. Start here every time.

**Project:** Vantage — agentic enterprise assistant for *Acme Operations* (a B2B payments platform). EY Applied AI Engineer take-home.
**Deadline:** 2026-06-02. One-hour panel follows.
**Status:** Design locked; **BUILD in progress** on two parallel tracks. Host **pivoted Azure → GitHub Codespaces** (Azure subscription was SKU-locked — see ADR-007).

## Parallel build (git worktrees, disjoint file ownership)
- **Track A — infra** (`track/infra`, this repo dir): `.devcontainer/`, `docker-compose.yml`, `keycloak/`, `app/`, `.env.example`.
- **Track B — data** (`track/data`, `/Users/benji/code/Vantage-data`): `db/schema.sql`, `scripts/generate_seed.py`, `db/seed.sql` — validating against a local Postgres.
- Merge both → `main`; run the full stack in a Codespace.

## Decisions (locked)
- **[ADR-001](05-Decisions/ADR-001-agent-framework.md)** — simple tool-calling loop, not LangGraph; model-agnostic.
- **[ADR-002](05-Decisions/ADR-002-rbac-tool-boundary.md)** — RBAC in each tool; Keycloak = source of truth.
- **[ADR-003](05-Decisions/ADR-003-mcp-server.md)** — custom MCP server, 5 tools, HTTP (stdio fallback).
- **[ADR-004](05-Decisions/ADR-004-environment.md)** — ~~Azure VM~~ **superseded** ↓
- **[ADR-005](05-Decisions/ADR-005-seed-data.md)** — committed static seed, Faker + Claude.
- **[ADR-006](05-Decisions/ADR-006-memory-split.md)** — Redis for session; Postgres for the record.
- **[ADR-007](05-Decisions/ADR-007-environment-codespaces.md)** — **GitHub Codespaces** (docker-in-docker); portable stack unchanged.

## Next 3 moves
1. **Track A:** author `docker-compose.yml` + Keycloak realm (roles + test users) + API stub — these don't need Docker to *write*. Then create a Codespace on `track/infra` to *run/test* (Keycloak first).
2. **Track B:** finish `schema.sql` + seed, validated against local Postgres.
3. **Merge** both tracks → `main`; full `docker compose up` in the Codespace.

## Open questions / blockers
- Azure SKU/quota-increase request — *optional, parallel*. If it clears before the 2nd, the same portable stack can move to Azure for the demo. Not blocking.
- Demo-day rehearsal on Codespaces (set a long idle timeout; keep a screen-recording fallback).
- Role mapping (sales→`sales_user`, support→`support_user`, operations→`admin`) — assumption to confirm.

---
> [!TIP] Vault conventions
> Standard relative Markdown links, not wiki-links (renders on GitHub too). Frontmatter `type` groups notes. GitHub-compatible callouts (`NOTE`/`TIP`/`WARNING`/`IMPORTANT`).
