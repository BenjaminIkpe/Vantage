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
We expose tools via ≥1 MCP (Model Context Protocol) server, and it's worth being explicit about *why MCP* and *how it separates tools from agent logic*. Our tools — eleven today (3 reads, 3 writes, 3 browse, 2 admin-only fleet) — touch Postgres and must enforce RBAC (ADR-002). Two sub-decisions: what kind of server, and which transport.

## Decision
**A custom MCP server exposing our named, typed, RBAC-checked tools** — five at decision time (`get_customer_profile`, `get_open_issues`, `summarise_issue_history`, `update_issue`, `create`/`update_next_action`), since grown to **eleven** (+ `list_customers`/`list_issues`/`list_next_actions` browse, PR #21; + `get_high_risk_customers`/`detect_patterns` admin-only fleet, ADR-008). The agent never sees or writes raw SQL.

**Transport: Streamable HTTP**, with the MCP server as its own Docker Compose service. **stdio is the documented fallback** if the cross-boundary auth proves painful — a contained switch (per ADR-001), since tools and RBAC don't move.

## Alternatives considered
- **Generic Postgres/SQL MCP server (off-the-shelf).** Rejected — exposes arbitrary SQL, bypasses our RBAC boundary, inflates blast radius. Anthropic's reference Postgres MCP server was **deprecated (July 2025) after a SQL-injection vulnerability** that bypassed its read-only mode. Named, parameterized tools are the documented-secure pattern.
- **stdio transport as primary.** Reasonable and simpler (no network; role passed in-process), but HTTP makes the client–server separation a visible Compose service (better diagram/demo). Kept as the fallback.

## Consequences
- ✅ Secure by design — no raw SQL, RBAC enforced per tool, agent never holds DB credentials (smaller blast radius).
- ✅ Tools decoupled and reusable — the agent *discovers* them; also the LangGraph migration bridge (ADR-001).
- ✅ Clear "why MCP" and "why not a database MCP server" rationale, with a current, concrete security example.
- ⚠️ HTTP adds one integration point: threading the verified role from API → MCP server. If painful, drop to stdio (fallback above).
- Note: on the dev/demo host ([ADR-007](ADR-007-environment-codespaces.md): GitHub Codespaces with Docker-in-Docker) this HTTP is container-to-container on the compose stack's private network — not internet-exposed.
