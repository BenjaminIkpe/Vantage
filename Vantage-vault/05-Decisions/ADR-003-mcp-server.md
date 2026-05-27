---
title: ADR-003 — MCP server: custom tools over HTTP (stdio fallback)
type: adr
status: accepted
date: 2026-05-27
revisit-by:
supersedes:
---

# ADR-003 — A custom MCP server exposing named tools, over HTTP (stdio fallback)

**Status:** accepted
**Date:** 2026-05-27

## Context
The brief requires ≥1 MCP (Model Context Protocol) server and asks us to explain *why MCP* and *how it separates tools from agent logic*. Our five tools touch Postgres and must enforce RBAC (ADR-002). Two sub-decisions: what kind of server, and which transport.

## Decision
**A custom MCP server exposing our five named, typed, RBAC-checked tools** (`get_customer_profile`, `get_open_issues`, `summarise_issue_history`, `update_issue`, `create`/`update_next_action`). The agent never sees or writes raw SQL.

**Transport: Streamable HTTP**, with the MCP server as its own Docker Compose service. **stdio is the documented fallback** if the cross-boundary auth proves painful — a contained switch (per ADR-001), since tools and RBAC don't move.

## Alternatives considered
- **Generic Postgres/SQL MCP server (off-the-shelf).** Rejected — exposes arbitrary SQL, bypasses our RBAC boundary, inflates blast radius. Anthropic's reference Postgres MCP server was **deprecated (July 2025) after a SQL-injection vulnerability** that bypassed its read-only mode. Named, parameterized tools are the documented-secure pattern.
- **stdio transport as primary.** Reasonable and simpler (no network; role passed in-process), but HTTP makes the client–server separation a visible Compose service (better diagram/demo; brief-aligned). Kept as the fallback.

## Consequences
- ✅ Secure by design — no raw SQL, RBAC enforced per tool, agent never holds DB credentials (smaller blast radius).
- ✅ Tools decoupled and reusable — the agent *discovers* them; also the LangGraph migration bridge (ADR-001).
- ✅ Strong "why MCP" and "why not a database MCP server" panel answers, with a current, concrete security example.
- ⚠️ HTTP adds one integration point: threading the verified role from API → MCP server. If painful, drop to stdio (fallback above).
- Note: on a single Azure VM (ADR-004) this HTTP is container-to-container on a private Docker network — not internet-exposed.
