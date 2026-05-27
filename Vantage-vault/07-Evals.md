---
title: Evals
type: evals
status: active
updated: 2026-05-27
---

# Evals

> [!NOTE] Purpose
> The runnable test set that proves the assistant works — a required deliverable. Derived from the acceptance criteria in [02-User-Stories](02-User-Stories.md). Harness: [`eval/run_evals.py`](../eval/run_evals.py).

## What each case measures (from the brief)
- Correct **tool(s)** selected for the query
- Response **grounded** in database results (not invented)
- **RBAC** respected (right role allowed / denied)
- Recommended **next action** is reasonable

## How it asserts (stable against LLM phrasing)
Each case checks the **deterministic** signals first — the tool `trace` (which tool ran, and the tool's `result.status`/fields, which are data-driven) and the HTTP status — plus loose, case-insensitive substring checks on the answer where reliable. So a reworded answer doesn't flake the suite, but grounding/RBAC/tool-selection are genuinely verified.

## How to run
Against the running stack (Codespace), with the seed loaded:
```bash
python eval/run_evals.py     # exits non-zero if any case fails
```
Uses the dev ROPC grant for the three role users (`sales` / `support` / `admin-user`); override `API_URL` / `KEYCLOAK_TOKEN_URL` if needed.

## Cases
| # | Query | Role | Expected tool(s) | Expected behaviour | Result |
| --- | --- | --- | --- | --- | --- |
| 1 | "Profile for Velocity Marketplace" | support | `get_customer_profile` | grounded profile (ACME-76085) | ✅ |
| 2 | "Open issues for **Zzzz Holdings**" (absent) | support | `get_open_issues`→`not_found` | says not found; **invents nothing** (E1) | ✅ |
| 3 | "Open issues for **Lumen**" (twins) | support | `…`→`ambiguous` | asks which / lists candidates (E2) | ✅ |
| 4 | "Open issues for **Calm Waters Subscriptions**" | support | `get_open_issues`→`found`, `open_count=0` | "no open issues"; no fabrication (E3) | ✅ |
| 5 | "Open issues for Velocity, summarise the most urgent, recommend a next action" | support | `get_open_issues` → `summarise_issue_history` | **dynamic multi-tool** chain; grounded brief | ✅ |
| 6 | "Add a note to issue 3 …" | **sales** | `update_issue`→`denied` | **RBAC denied**; no write; relayed (S3) | ✅ |
| 7 | "Add a note to issue 3 …" | support | `update_issue`→`updated` | RBAC allowed; attributable write (SU2) | ✅ |
| 8 | "open issues for Velocity" → "summarise **the second one**" | support | (turn 2) `summarise_issue_history` | reference resolved from **Redis** session (X1) | ✅ |
| 9 | Skill `escalation-summary {customer: Velocity}` | sales | `get_open_issues` (+history) | risk level + advice; read-only Skill (S2) | ✅ |
| 10 | `POST /ask` with **no token** | — | — | **HTTP 401** (auth required, T1) | ✅ |

**Latest run: 10 / 10 passed** (Codespace, against the committed seed).

> [!TIP] Includes the negative case
> Case 6 (a `sales_user` trying to update an issue) is the brief's required **denied** case — it proves the *tool* enforces RBAC on the re-verified role, not the prompt: the agent attempts the tool and relays the refusal.
