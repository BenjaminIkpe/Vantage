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
**Status:** ✅ **Skill *authoring* live (Flow 1 endpoints).** Users turn a finished `/ask` session into a reusable skill: `POST /skills/draft-from-session` generalises the conversation (LLM parameterises the inputs, e.g. `{account_name}`; `allowed_tools` = the tools the session used) → `POST /skills` saves it to a volume → `POST /skills/{name}/run` reuses it for any input. Built on the generic **Skill runner** (Slice 4) + the seeded **Escalation Summary** (S2). Prior: all 5 tools + RBAC denial + Redis memory; agent is an MCP client; API holds no DB access; RBAC re-verified at the MCP boundary. **Next: the `/ask` natural-language authoring trigger (Flow 1 PR B), then evals + observability + UI + deliverables.**

## Proven (Codespace, `main`)
- `docker compose up` → db+redis+keycloak+**mcp**+api healthy; seed 12/40/132/14; auth (support/admin) + 401 on bad tokens.
- **`POST /ask`** (auth-gated), validated live as `support`, every answer flowing API → agent (MCP client) → MCP server (re-verify + RBAC) → Postgres:
  - "open issues for Velocity Marketplace" → 4 open, critical→high→medium (one MCP tool call).
  - **Headline:** "open issues for Velocity, summarise the most urgent, suggest a next action" → agent chained `get_open_issues` → `summarise_issue_history` over MCP; grounded escalation summary (quotes real update bodies — EDD case CDD-4821) + next action. Proves **dynamic tool selection** (ADR-001).
  - "Calm Waters Subscriptions" → "no open issues" (E3). Earlier: "Lumen"→ambiguous (E2) · "Zzzz"→not found (E1).
  - **RBAC denial (S3/SU3) proven end-to-end:** as `sales`, "add a note to issue 3" → agent *attempts* `update_issue` (no self-gating) → tool returns `denied` → agent relays the refusal; trace `update_issue->denied`. As `support`, same request → `update_issue->updated` (written + timestamped). Deterministic matrix in `smoke_test.py`: support-updates / sales-denied / admin-next-action / support-denied / admin-updates-next-action.
  - `POST /ask` with no/invalid token → **401**; `smoke_test.py` confirms the MCP server itself rejects a bad token before any tool runs.
  - Tool-call `trace` on every answer + server-side **audit log** per write (user/roles/target/decision; identifiers only, T7).
  - **Multi-turn (X1) proven:** on one `session_id`, "open issues for Velocity" → "summarise the second one" resolved to issue #3 (2nd row) via Redis context → "what next?" answered from context; a fresh `session_id` carried nothing over (asked which customer, no hallucination).
  - **Skill (S2) proven:** `POST /skills/escalation-summary/run {customer}` as `sales` → Velocity=Critical / Calm Waters=Low / Zzzz=not-found; grounded, persists nothing, only the 2 whitelisted read tools touched. `GET /skills` lists it.
  - **Skill authoring (Flow 1) proven:** a 2-turn session → `draft-from-session` produced a parameterised draft (`{account_name}`, allowed_tools = tools used) → saved → ran for a new account. Wrong param name correctly rejected.
- Tools (5 of 5): reads `get_customer_profile`, `get_open_issues`, `summarise_issue_history` (open to any role); writes `update_issue` (support+admin), `create_next_action` / `update_next_action` (admin). Discovered via MCP; parameterised SQL; writes attributed via `users.keycloak_id = token sub`. Live in `mcp_server/` (dir named to avoid shadowing the `mcp` SDK; compose service is `mcp`).

## Repo / flow
- `main` protected (PR + `ci` required; admin-bypass). `ci.yml` on every PR; `data-ci.yml` on data PRs. Build = feature branch → PR → CI → merge.

## Decisions: ADR-001…007 ([05-Decisions](05-Decisions/)) · Security: [09-Security](09-Security.md)

## Next moves (via PR flow)
1. **Skill authoring — Flow 1 PR B (`/ask` trigger):** in `/ask`, "save this as a skill" → the agent composes the skill from the session and, on confirm, persists it via a local `save_skill` tool (the conversational counterpart to the endpoints). (Flow 2 — interview + role-aware suggestions — remains the stretch, ideally with the UI.)
2. **Evals** (5–10, table in 07-Evals — derive from the proven scenarios) + **observability** write-up (trace + audit logs already emitted) → minimal **UI** → README/diagram/AI-usage deliverables.

## Open questions
- `/ask` save-skill trigger: give the agent a local `save_skill` tool (clean, agentic) vs intent-routing in main.py (hacky). Lean local tool — means run_agent must dispatch local tools alongside MCP tools (only on the /ask path, not skill runs).
- Drafter param naming: LLM picks the param name (`account_name`); consider nudging toward conventional names (`customer`) for guessability.
- Demo-day rehearsal on Codespaces (idle 90m; screen-recording fallback; transient Docker-in-Docker "file exists" shim error → `docker compose down --remove-orphans` then `up`).
