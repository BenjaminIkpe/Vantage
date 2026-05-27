# Vantage — Claude context

Vantage is a grounded, **agentic** enterprise assistant for the fictional client **Acme Operations** (a B2B payments platform), built for the EY Applied AI Engineer take-home. This file bootstraps a fresh session — read the cursor first.

## Read first
1. **[`Vantage-vault/00-NOW.md`](Vantage-vault/00-NOW.md)** — the cursor: current status, what's proven, decisions, and the **next moves**. Always start here.
2. As needed: `Vantage-vault/` — Frame, User-Stories, Scope, Architecture, ADRs (`05-Decisions/`), Security (`09-Security.md`), Build-Log.

## How we work (conventions)
- **Build flow:** every code change is `feature branch → PR → CI → merge`. `main` is protected (PR + the `ci` check required; admin-bypass kept for docs/cursor only). **Never edit code on `main` directly.**
- **Host:** runs in a **GitHub Codespace** (Docker-in-Docker), not locally (laptop disk constraint). `docker compose up` → db + redis + keycloak + api. Drive the Codespace from the laptop with `gh codespace ssh --codespace <name> -- bash -lc '<cmd>'` (gh needs the `codespace` scope).
- **Secrets:** `.env` is git-ignored and holds `ANTHROPIC_API_KEY` — it lives **in the Codespace**, never committed.
- **Git:** absolute dates; **no `Co-Authored-By` lines** in commits.

## Architecture (one line each — see the ADRs)
- Agent = a **minimal tool-calling loop** (Claude), not LangGraph (ADR-001); model-agnostic via `app/llm.py` (lazy client).
- **RBAC enforced inside each tool, never in the prompt** (ADR-002); Keycloak issues roles; the API verifies the JWT.
- Tools should be exposed via a **custom MCP server** (ADR-003) — *not yet wired; currently in-process*.
- **Codespaces** host (ADR-007 supersedes the Azure ADR-004); the compose stack stays portable.
- Data: **Postgres** (system of record) + **Redis** (session); seed is committed + Faker/Claude-generated (ADR-005).
- Security threat model + dev→prod hardening: `Vantage-vault/09-Security.md`.

## Resume
Read `00-NOW.md`, take the next move it lists, and work on a feature branch → PR. Tools to drive things: `gh` (repo, PRs, Codespace), `docker compose` (in the Codespace).
