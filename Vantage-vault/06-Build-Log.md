---
title: Build Log
type: build-log
status: active
updated: 2026-05-27
---

# Build Log

> [!NOTE] Purpose
> Thin-slice plan + dated progress + the AI-usage log (feeds Deliverable 5 / panel §4.9).

## Thin-slice plan
- [x] **Slice 0** — Codespace + Keycloak + Redis. ✅
- [x] **Slice 1a** — auth gate (JWT verify; forged/missing → 401). ✅
- [x] **Integration** — full stack on `main`; seed loads (12/40/132/14). ✅
- [x] **Slice 1b** — first tool (`get_customer_profile`) **+ agent loop** (`POST /ask`, Claude tool-calling); validated found/ambiguous/not-found. ✅
- [x] **Slice 2** — read tools `get_open_issues`, `summarise_issue_history` (PR #4); **custom MCP server** (Streamable HTTP) + agent flipped to an **MCP client** (PR #5, #6). MCP Must met; API holds no DB access. ✅
- [x] **Slice 3** — write tools + RBAC **denial** case (PR #7); **Redis** multi-turn session memory (PR #8). ✅
- [~] **Slice 4** — reusable **Skill runner** + seeded **Escalation Summary** (PR #9); user **Skill authoring** Flow 1 endpoints — draft-from-session + save (PR #10); the `/ask` authoring trigger (Flow 1 PR B) — *next*. Differentiator beyond the Must.
- [ ] **Slice 5** — evals (5–10) + observability; minimal UI.

## Progress log (newest first)
### 2026-05-27 (cont.)
- ✅ **Skill authoring — Flow 1 endpoints (PR #10)** — turn a finished session into a reusable skill. `/ask` records each turn's tool trace into the session; `POST /skills/draft-from-session` has the LLM generalise the conversation (forced `propose_skill` tool: parameterises inputs like the customer → `{account_name}`), with `allowed_tools` set deterministically from the tools the session used; `POST /skills` saves it to a volume-backed dir (authored override seeded). Any role may author — safe because a skill is a prompt + tool whitelist (RBAC stays in the tools). Proven on the Codespace: session → draft → save → run for a new account.
- ✅ **Reusable Skill runner + Escalation Summary (Slice 4 Must)** — PR #9. Generic engine: a Skill is data (`skills_library/*.json`: name/description/instructions/params/allowed_tools); `run_skill` reuses the agent loop with the skill's instructions as system + tools restricted to its whitelist (least privilege on top of RBAC). Seeded **escalation-summary** (S2 rubric, read-only). Decided the "Skill" question with the user: same concept as Anthropic Agent Skills (packaged reusable capability) but file-based on our raw-API stack, not a `SKILL.md` the Claude runtime loads. Proven on the Codespace as `sales`: Velocity=Critical / Calm Waters=Low / Zzzz=not-found, only whitelisted tools used. **Next:** user Skill authoring (Flow 1 — generalise a finished session into a skill via the history + trace), agreed as the differentiator.
- ✅ **Redis multi-turn memory (Slice 3 PR B → Slice 3 done)** — `/ask` takes a `session_id` (server mints one if absent, returns it); the agent loads/saves the conversation in Redis (`session:{id}`, rolling cap + ~1h TTL), stored as plain user/assistant text turns; lives in the API/agent layer, degrades gracefully if Redis is down (ADR-006). PR #8. Proven on the Codespace: "open issues for Velocity" → "summarise the second one" resolved to issue #3 via context → "what next?" from context; a fresh session carried nothing.
- ✅ **Write tools + RBAC denial (Slice 3 PR A)** — `update_issue` (support+admin), `create`/`update_next_action` (admin) behind the MCP server (PR #7). All 5 tools now exist. Denial enforced **inside the tool** on the re-verified role; returns structured `denied` (no write) + server-side audit log (identifiers only, T7). Writes attributed via `users.keycloak_id = token sub`. Prompt updated so the agent does **not** self-gate (tries the tool, relays the denial) — keeps RBAC out of the prompt (ADR-002). Proven on the Codespace: deterministic role×tool matrix in `smoke_test.py` **and** end-to-end `/ask` (sales→denied-relayed, support→updated).
- ✅ **MCP wired (Slice 2 done)** — custom **MCP server** over Streamable HTTP as its own Compose service (PR #5), then the agent flipped to an **MCP client** that discovers + calls tools (PR #6). Role threaded by **forwarding the Keycloak JWT and re-verifying it at the MCP boundary** (SDK `TokenVerifier`; the bearer middleware 401s a bad token before any tool runs); used the SDK's native resource-server support after a quick introspection spike confirmed the subclassed token survives to the tool. DB access removed from the API (`db.py`/`tools.py` now live in `mcp_server/`; only `security.py` shared). Dir is `mcp_server/` to avoid shadowing the `mcp` SDK package. Validated live: 3 headline `/ask` queries via the MCP path + 401 on no token + `smoke_test.py` rejecting a bad token at the MCP server.
- ✅ **Read tools 2 & 3** — `get_open_issues` + `summarise_issue_history` (PR #4). Shared `_resolve_customer` (get_customer_profile delegates to it — unchanged). Validated end-to-end on the Codespace: the headline query chained all 3 read tools into a grounded escalation summary; E3 zero-open clean; trace returned. (SQL also proven against the committed seed via a throwaway local Postgres while the Codespace was briefly billing-blocked.)
- ✅ **Agentic core working** — `POST /ask` runs a minimal Claude tool-calling loop (ADR-001) over `get_customer_profile`. Validated live: "Velocity"→grounded profile; "Lumen"→asks which (E2, no guess); "Zzzz"→not found (E1, no invention). Merged via PR #3.
- ✅ First tool `get_customer_profile` (PR #2); CI on every PR + branch protection live.
- ✅ Full stack integrated on `main`; auth gate; host pivot Azure→Codespaces.

### 2026-05-27
- Repo + two parallel tracks; full design locked (ADR-001…006).
### 2026-05-26
- Vault scaffolded.

## AI-usage log
| Date | Task delegated to AI | How I reviewed / validated | Issues caught |
| --- | --- | --- | --- |
| 2026-05-26 | Scaffold vault | vs the brief | none |
| 2026-05-27 | Architecture research | web-searched best practice; chose tool-loop over LangGraph | AI leaned heavier first |
| 2026-05-27 | Business context | vs the brief | removed a cross-project "persona" detail |
| 2026-05-27 | Azure provisioning (CLI) | read errors; region/quota diagnostics | my own zsh bug; real cause = SKU lockdown → Codespaces |
| 2026-05-27 | Codespace Docker | inspected creation logs | docker-in-docker feature failed → universal image |
| 2026-05-27 | Auth gate (JWT) | tested valid/missing/tampered tokens | Keycloak issuer mismatch → frontend/backchannel fix |
| 2026-05-27 | Data-track review + integrate | read schema/generator; ran full stack | realm/seed identity mismatch → reconciled |
| 2026-05-27 | Tool + agent loop | ran real /ask queries vs seeded data; checked tool trace | validated grounding (no invented data), E1/E2 behaviour, RBAC, lazy client keeps CI green |
| 2026-05-27 | Read tools 2 & 3 | deep-dived the vault vs the design first; proved SQL on the committed seed (throwaway local PG) then end-to-end on the Codespace | confirmed shared `_resolve_customer` left `get_customer_profile` unchanged; E3 zero-open + headline chain grounded |
| 2026-05-27 | MCP server + agent-as-client | required a design sketch + sign-off before coding; introspection spike on the MCP SDK to ground the auth approach; smoke test + 3 /ask queries on the Codespace | chose forward-JWT + re-verify (not a trusted role header); renamed dir to avoid SDK package shadowing; 401 path confirmed |
| 2026-05-27 | Write tools + RBAC denial | design sketch + sign-off (denial as structured status; slice write vs Redis); deterministic role×tool matrix + end-to-end /ask on the Codespace | insisted the agent must *attempt* the tool (no prompt self-gating) so the denial is genuinely tool-enforced; audit logs identifiers only |
