---
title: NOW — Vantage cursor
type: cursor
status: active
updated: 2026-05-27
---

# NOW — where we are

> [!NOTE] Cursor — overwritten each session; start here. Plain Markdown links (GitHub-renderable).

**Project:** Vantage — agentic assistant for *Acme Operations* (B2B payments). EY Applied AI Engineer take-home.
**Deadline:** 2026-06-02. One-hour panel follows.
**Status:** ✅ **All 5 tools live + RBAC denial proven (Slice 3 PR A done).** The agent is an **MCP client** discovering 5 named tools from a custom **MCP server** (own Compose service, Streamable HTTP). API holds **no DB access**; the MCP boundary **re-verifies the forwarded Keycloak token** and each tool enforces RBAC (ADR-002/003). Write tools gate on role: a denied call writes nothing, returns structured `denied`, and is audit-logged.

## Proven (Codespace, `main`)
- `docker compose up` → db+redis+keycloak+**mcp**+api healthy; seed 12/40/132/14; auth (support/admin) + 401 on bad tokens.
- **`POST /ask`** (auth-gated), validated live as `support`, every answer flowing API → agent (MCP client) → MCP server (re-verify + RBAC) → Postgres:
  - "open issues for Velocity Marketplace" → 4 open, critical→high→medium (one MCP tool call).
  - **Headline:** "open issues for Velocity, summarise the most urgent, suggest a next action" → agent chained `get_open_issues` → `summarise_issue_history` over MCP; grounded escalation summary (quotes real update bodies — EDD case CDD-4821) + next action. Proves **dynamic tool selection** (ADR-001).
  - "Calm Waters Subscriptions" → "no open issues" (E3). Earlier: "Lumen"→ambiguous (E2) · "Zzzz"→not found (E1).
  - **RBAC denial (S3/SU3) proven end-to-end:** as `sales`, "add a note to issue 3" → agent *attempts* `update_issue` (no self-gating) → tool returns `denied` → agent relays the refusal; trace `update_issue->denied`. As `support`, same request → `update_issue->updated` (written + timestamped). Deterministic matrix in `smoke_test.py`: support-updates / sales-denied / admin-next-action / support-denied / admin-updates-next-action.
  - `POST /ask` with no/invalid token → **401**; `smoke_test.py` confirms the MCP server itself rejects a bad token before any tool runs.
  - Tool-call `trace` on every answer + server-side **audit log** per write (user/roles/target/decision; identifiers only, T7).
- Tools (5 of 5): reads `get_customer_profile`, `get_open_issues`, `summarise_issue_history` (open to any role); writes `update_issue` (support+admin), `create_next_action` / `update_next_action` (admin). Discovered via MCP; parameterised SQL; writes attributed via `users.keycloak_id = token sub`. Live in `mcp_server/` (dir named to avoid shadowing the `mcp` SDK; compose service is `mcp`).

## Repo / flow
- `main` protected (PR + `ci` required; admin-bypass). `ci.yml` on every PR; `data-ci.yml` on data PRs. Build = feature branch → PR → CI → merge.

## Decisions: ADR-001…007 ([05-Decisions](05-Decisions/)) · Security: [09-Security](09-Security.md)

## Next moves (via PR flow)
1. **Redis multi-turn memory** (Slice 3 PR B, story X1) — `/ask` takes a `session_id`; agent loads/saves conversation history in Redis (`session:{id}`, ~1h TTL) so "the second one" / "what next?" resolve in context; a fresh session carries nothing. Lives in the API/agent layer (ADR-006), not the MCP server. *(Sketch for sign-off first.)*
2. **Escalation Summary Skill** (Slice 4) → **evals** (5–10) + observability (Slice 5) → minimal **UI**.

## Open questions
- Redis session_id contract: client-provided vs server-issued; what to store (full messages vs rolling/summarised within token budget).
- Demo-day rehearsal on Codespaces (idle 90m; screen-recording fallback; note: hit a transient Docker-in-Docker "file exists" shim error — `docker compose down --remove-orphans` then `up` clears it).
