---
title: ADR-002 — RBAC enforced at the tool boundary
type: adr
status: accepted
date: 2026-05-27
revisit-by:
supersedes:
---

# ADR-002 — Role-based access control enforced at the tool boundary

**Status:** accepted
**Date:** 2026-05-27

## Context
Three roles with different rights (§4.4): `sales_user` (read-only), `support_user` (read + update issues), `admin` (full, incl. next actions). The agent is an LLM that dynamically chooses tools (ADR-001). We must enforce who-can-do-what reliably and provably (incl. a *denied* case), and explain it in the panel.

The danger: enforcing permissions in the LLM prompt ("don't let sales update"). **An LLM is not a security boundary** — it can be talked around or simply slip.

## Decision
Enforce RBAC **server-side, inside each tool — never in the prompt.** Flow:
- Keycloak authenticates the user and issues a token (JWT) carrying their role in its claims.
- The token is validated; the **verified role is propagated to the tool call.**
- Each tool declares the role(s) it requires and **checks before executing.** A disallowed call is refused with a clear message, makes no database change, and is logged.
- The agent acts **as the user** (carrying their role) — never as a god-mode service account.

This is the documented #1 MCP authorization pattern (tool-level RBAC). *The LLM proposes; the tool disposes.*

**Source of truth for roles:** the validated Keycloak token, always. A mirrored `users.role` column in Postgres exists only for attribution / display / seed — never for the live permission check. One source of truth for security.

## Alternatives considered
- **RBAC in the system prompt.** Rejected — not a security boundary; bypassable; not auditable.
- **One privileged DB account for all calls.** Rejected — no per-user accountability; can't enforce per-role rights or produce the audit trail.

## Consequences
- ✅ Security holds regardless of what the model does or is prompted into.
- ✅ Produces the brief's required *denied* case and an audit trail (who attempted what).
- ✅ Framework- and transport-agnostic — the check lives in the tool whether transport is stdio or HTTP, loop or LangGraph.
- ⚠️ The verified role must be threaded to every tool call (in-process for stdio; across the boundary for HTTP — see ADR-003). Accepted; it's the one integration point to get right.
