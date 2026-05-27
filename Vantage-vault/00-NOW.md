---
title: NOW — Vantage cursor
type: cursor
status: active
updated: 2026-05-27
---

# NOW — where we are

> [!NOTE] How this file works
> This is the cursor: the single source of truth for *where the project is right now*. It is **overwritten** each working session, not appended. Start here every time.

**Project:** Vantage — agentic enterprise assistant for the fictional client *Acme Operations*, modelled as a **B2B payments platform** (EY Applied AI Engineer take-home).
**Deadline:** 2026-06-02 (submission). One-hour panel session follows.
**Status:** Day 1 — ✅ **DESIGN LOCKED** (6 ADRs + full data model + business context). Next session = **build**.

## Vault map

| File | Purpose | State |
| --- | --- | --- |
| [01-Frame](01-Frame.md) | Problem, business context, outcome, DoD | ✅ locked |
| [02-User-Stories](02-User-Stories.md) | Each role's needs + acceptance criteria | ✅ locked |
| [03-Scope](03-Scope.md) | Must / Should / Could / Won't | ✅ locked |
| [04-Architecture](04-Architecture.md) | Design + data model + memory split | ✅ locked (diagram renders in build) |
| [05-Decisions](05-Decisions/) | ADRs — the *why* of every choice | ADR-001…006 ✅ |
| [06-Build-Log](06-Build-Log.md) | Thin-slice plan + progress + AI-usage | ▶ build starts here |
| [07-Evals](07-Evals.md) | Test questions + expected results | from acceptance criteria |
| [08-Panel-Prep](08-Panel-Prep.md) | Demo script + likely Q&A (not submitted) | draft |

## Design decisions (all locked)
- **[ADR-001](05-Decisions/ADR-001-agent-framework.md)** — simple tool-calling loop, not LangGraph; model-agnostic.
- **[ADR-002](05-Decisions/ADR-002-rbac-tool-boundary.md)** — RBAC in each tool; Keycloak = source of truth.
- **[ADR-003](05-Decisions/ADR-003-mcp-server.md)** — custom MCP server, 5 tools, HTTP (stdio fallback).
- **[ADR-004](05-Decisions/ADR-004-environment.md)** — Azure VM, portable compose stack.
- **[ADR-005](05-Decisions/ADR-005-seed-data.md)** — committed static seed, Faker + Claude.
- **[ADR-006](05-Decisions/ADR-006-memory-split.md)** — Redis for session; Postgres for the record.

## Next 3 moves (build — slice plan in [06-Build-Log](06-Build-Log.md))
1. **Slice 0** — provision the Azure VM; `docker compose up` skeleton with **Keycloak first** (hardest infra; de-risk).
2. **Slice 1** — Postgres schema + Faker/Claude seed; one read tool end-to-end through the agent loop.
3. **Slice 2** — custom MCP server over HTTP + the read tools, RBAC enforced.

## Open questions / blockers
- Role mapping (sales→`sales_user`, support→`support_user`, operations→`admin`) — assumption to confirm / log.
- Demo-day path (Azure VM + forwarded ports) needs rehearsing; keep a screen-recording fallback (ADR-004).
- API framework assumed **FastAPI** — confirm at Slice 0.

---
> [!TIP] Vault conventions
> Standard relative Markdown links (`[text](file.md)`), **not** wiki-links — so notes render in both Obsidian and on GitHub (the deliverable is a GitHub repo). Frontmatter `type` groups notes. Callouts use the GitHub-compatible set (`NOTE`, `TIP`, `WARNING`, `IMPORTANT`).
