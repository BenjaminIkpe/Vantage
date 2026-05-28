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
**Status:** ✅✅ **All brief Musts done + the graded deliverables.** Auth/RBAC (+denial), 5 tools via a custom MCP server, dynamic agent (MCP client), API, Postgres seed, Redis multi-turn memory, the reusable Escalation Summary Skill, Docker one-command — **plus** the **eval set (10/10)**, **observability** (trace + per-tool/total latency + write audit logs), and a full **README + diagram + AI-usage notes**. Beyond the Must: users can **author their own Skills** from a finished session (Flow 1 endpoints). **Remaining is all Should/Could:** minimal **UI** (+ chat-history sidebar idea), the `/ask` save-as-skill trigger, Flow 2.

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
  - **User-story acceptance walkthrough (13/13)** + **robustness suite (30/30)** — 30 adversarial / edge probes (typo, single-char, all-caps, whitespace, non-ASCII, prompt-injection, out-of-scope, empty/long/SQL-shaped/special-char inputs, multi-turn weirdness, Skill edge cases). Caught real bugs along the way (next_actions read gap → PR #13; empty-query 502 → 400 in PR #15) and confirmed adversarial probes never produce a successful write as sales — the LLM is *not* the boundary.
- Tools (5 of 5): reads `get_customer_profile`, `get_open_issues`, `summarise_issue_history` (open to any role); writes `update_issue` (support+admin), `create_next_action` / `update_next_action` (admin). Discovered via MCP; parameterised SQL; writes attributed via `users.keycloak_id = token sub`. Live in `mcp_server/` (dir named to avoid shadowing the `mcp` SDK; compose service is `mcp`).

## Repo / flow
- `main` protected (PR + `ci` required; admin-bypass). `ci.yml` on every PR; `data-ci.yml` on data PRs. Build = feature branch → PR → CI → merge.

## Decisions: ADR-001…007 ([05-Decisions](05-Decisions/)) · Security: [09-Security](09-Security.md) · Scaling/RAG: [10-Scaling](10-Scaling.md)

## Next moves (all Should/Could — Musts are done)
1. **Minimal chat UI** (Should) — the live-demo multiplier. Include the **chat-history sidebar** (list past chats, resume from one) once core chat works; needs per-user session listing (track session ids per user). *Sketch the UI for sign-off when we start.*
2. **`/ask` "save this as a skill" trigger** (Should, Flow 1 PR B) — conversational counterpart to the authoring endpoints (local `save_skill` tool in the loop).
3. **Flow 2** (Could) — guided/interview skill authoring with role-aware suggestions.
4. Polish: bonus tracing (OpenTelemetry/Phoenix), streaming, cache-aside for `get_customer_profile`.

## Open questions
- `/ask` save-skill trigger: give the agent a local `save_skill` tool (clean, agentic) vs intent-routing in main.py (hacky). Lean local tool — means run_agent must dispatch local tools alongside MCP tools (only on the /ask path, not skill runs).
- Drafter param naming: LLM picks the param name (`account_name`); consider nudging toward conventional names (`customer`) for guessability.
- Demo-day rehearsal on Codespaces (idle 90m; screen-recording fallback; transient Docker-in-Docker "file exists" shim error → `docker compose down --remove-orphans` then `up`).
