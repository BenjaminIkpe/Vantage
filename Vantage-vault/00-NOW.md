---
title: NOW — Vantage cursor
type: cursor
status: active
updated: 2026-05-29
---

# NOW — where we are

> [!NOTE] Cursor — overwritten each session; start here. Plain Markdown links (GitHub-renderable).

**Project:** Vantage — agentic assistant for *Acme Operations* (B2B payments). EY Applied AI Engineer take-home.
**Deadline:** 2026-06-02 (4 days). One-hour panel follows.
**Status:** ✅✅✅ **All brief Musts + the graded deliverables + the Should items shipped.** Auth/RBAC (+denial), 9 tools (incl. 3 browse) via a custom MCP server, dynamic agent (MCP client), Postgres seed, Redis multi-turn memory, the reusable Escalation Summary Skill + user-authored Skills, Docker one-command — **plus** the **eval set (13/13)** + **robustness suite (30/30)**, **observability** (trace + per-tool/total latency + write audit logs), full **README + diagram + AI-usage notes**, and **the chat UI is now real end-to-end**: OIDC Auth-Code + PKCE + BFF cookie (PR #18), Alpine.js + Tailwind front-end wired to `/ask/stream` + `/sessions` + `/skills/*` (PR #20), live SSE streaming with token deltas + tool-call events (PR #22), and **persona logins + real role switch + reasoning-in-trace + the "answer disappears" fix** (PR #23). The **75-test Playwright UI suite** passes against the deployed Codespace stack. Remaining is panel-prep + recording.

## Proven (Codespace, `main`)
- `docker compose up` → db+redis+keycloak+mcp+api healthy; seed 12/40/132/14; auth (3 personas) + 401 on bad tokens.
- **Personas (live):** logging in via the BFF flow is now real human names — `priya.nair` / `priya` (sales), `marcus.webb` / `marcus` (support), `dana.okafor` / `dana` (admin). Match the seed personas in [02-User-Stories](02-User-Stories.md). The UI's "Sign in as another persona" menu hits `GET /auth/switch?username=<persona>` → BFF clears the Redis session + revokes the Keycloak refresh token + drops the cookie → 302 to `/auth/login?prompt=login&login_hint=<persona>` → Keycloak forces re-auth → new JWT with the new realm roles. **A real identity swap, not a cosmetic flip.**
- **`POST /ask`** (auth-gated, validated live as each persona) and **`POST /ask/stream`** (SSE — the UI surface): every answer flows API → agent (MCP client) → MCP server (re-verify + RBAC) → Postgres. Tool-call `trace` on every answer + server-side **audit log** per write (user/roles/target/decision; identifiers only, T7).
  - Hero query "open issues for Velocity, summarise the most urgent, suggest a next action" → 3-tool chain → grounded escalation summary; trace shows `get_customer_profile → get_open_issues → summarise_issue_history` with per-tool ms.
  - **Multi-turn (X1):** Redis-backed; "summarise the second one" resolves to issue #3.
  - **Grounding edges (E1/E2/E3):** Zzzz→not_found; Lumen→ambiguous (lists candidates); Calm Waters→no open issues. No invention.
  - **RBAC end-to-end:** sales→denied (no write), support→updated, admin→create/update next actions. Deterministic matrix in `mcp_server/smoke_test.py`. RBAC at the **tool boundary**, never the prompt (ADR-002).
  - **Skill (S2):** `POST /skills/escalation-summary/run {customer}` as sales → Velocity=Critical / Calm Waters=Low / Zzzz=not-found; only the 2 whitelisted reads touched.
  - **Skill authoring (Flow 1):** session → `draft-from-session` → parameterised draft → save → run for a new account.
  - **User-story acceptance walkthrough (13/13)** + **robustness suite (30/30)** + **eval set (13/13)** all green.
- **UI shipped + verified by a 75-test Playwright suite (`tests/ui/test_ui.py`)** spanning 14 categories: auth + basic chat + streaming + markdown + multi-turn + sidebar + skills + RBAC + layout + theme + keyboard + a11y + edge-cases + browse-tools. **All 75 passing** against the deployed Codespace.
  - **Streaming**: SSE `text` / `tool_start` / `tool_end` / `done` events; UI renders tokens as they arrive; "calling X(…)" indicator while a tool is in flight.
  - **Reasoning in the trace**: per-message `timeline` interleaves the model's pre-tool narration (italic "thought" blocks) with the tool-call pills. Click **show thinking** to expand. Only the *final-iteration* text remains in the answer area — preface narration is retracted on `tool_start` (system prompt nudges the model to write 1–2 sentence intent before each call).
  - **"Answer disappears" bug fixed**: `loadSessions()` now MERGES (preserve existing chat objects by id, add new ids, drop removed ones) instead of wholesale-replacing `this.chats` — the prior behaviour wiped just-streamed assistant turns from memory.
  - **No emojis in agent output**: system prompt forbids them; defensive `EMOJI_RE` strip in `renderMd()` as belt-and-braces. Verified emoji-free.
- Tools (9 of 9): reads `get_customer_profile`, `get_open_issues`, `summarise_issue_history` (any role); writes `update_issue` (support+admin), `create_next_action` / `update_next_action` (admin); **browse** `list_customers`, `list_issues`, `list_next_actions` (filterable + paginated, PR #21). Discovered via MCP; parameterised SQL; writes attributed via `users.keycloak_id = token sub`. Live in `mcp_server/`.

## Repo / flow
- `main` protected (PR + `ci` required; admin-bypass for docs/cursor only). Last 5 PRs merged on `main`: #18 (OIDC + BFF), #20 (UI ↔ real backend), #21 (browse tools), #22 (SSE streaming), #23 (personas + role switch + reasoning + fixes). All CI green incl. CodeQL × 3.
- Build flow: feature branch → PR → CI → merge. Never edit code on `main` directly.

## Decisions: ADR-001…007 ([05-Decisions](05-Decisions/)) · Security: [09-Security](09-Security.md) · Scaling/RAG: [10-Scaling](10-Scaling.md)

## Next moves (panel-prep, all Could)
1. **Panel-day rehearsal** — record a screen-capture as a fallback in case Codespaces is flaky on the day; rehearse the 5-minute demo path (login as Marcus → hero query → "show thinking" panel → role-switch to Dana → write a next action → role-switch to Priya → see denial → save-as-skill).
2. **Optional polish** (skip if time is short): OpenTelemetry / Phoenix tracing export; cache-aside for `get_customer_profile`; `/ask` "save this as a skill" trigger (Flow 1 PR B) as a local agent tool; Flow 2 (guided/interview skill authoring with role-aware suggestions).
3. **Panel-prep doc** — re-read [08-Panel-Prep](08-Panel-Prep.md) and pad the answers for "where would this break first under scale" and "show me where RBAC is enforced".

## Open questions
- Stretch: is it worth recording a 2-min "guided tour" video to embed in the submission README, or rely on the live demo?
- Demo-day fallback: confirm screen-recording rig + a second Codespace as warm standby (90m idle timeout — `gh codespace ssh` keeps it alive).
