---
title: User Stories
type: stories
status: locked
updated: 2026-05-27
---

# User Stories

> [!NOTE] Purpose
> Who uses Vantage, what they need, and how we'll know each works. The **acceptance criteria** here become the eval cases in [07-Evals](07-Evals.md). This file holds **functional (user-facing) stories only** — see the note at the bottom for where non-functional requirements (MCP, Docker, eval) live.

**Template:** *As a* `[role]`, *I want* `[capability]`, *so that* `[outcome]`. *Acceptance:* `[observable, testable check]`.

> [!NOTE] Role-mapping assumption
> The brief names three staff types (sales, support, operations) and three roles (`sales_user`, `support_user`, `admin`). We map sales→`sales_user`, support→`support_user`, operations→`admin`. Reasonable, but an interpretation — confirm / log as an ADR.

## `sales_user` — account management, read-only
*Brief §4.4: read-only access to customer and issue data.*

- **S1 — Prep for a client call.** As a sales user, I want a customer's profile and all their open issues, so I walk into the conversation informed.
  *Accept:* returns the profile + **only that customer's** open issues; offers no write actions.
- **S2 — Account health check.** As a sales user, I want a risk summary of an account, so I can act before things escalate.
  *Accept:* the Escalation Summary Skill returns a **risk level** (Low/Medium/High/Critical) + a recommended next action (as *advice*) + any missing info; **persists nothing**.
- **S3 — Boundary (negative).** As a sales user, if I try to update an issue or create a next action, I'm refused.
  *Accept:* the attempt is **denied with a clear message**, no database change occurs, and the attempt is logged.

## `support_user` — reactive support, read + update issues
*Brief §4.4: read and update access for issues.*

- **SU1 — Pick up an issue.** As a support user, I want a customer's open issues and the full history of a specific one, so I can take it on cold.
  *Accept:* returns the open-issue list, then the **chronological history + current status** of the chosen issue.
- **SU2 — Record the work.** As a support user, I want to add a note and change an issue's status, so the record reflects what I did.
  *Accept:* `update_issue` writes an `issue_updates` entry and/or status change, **attributable to me and timestamped**, visible on the next read.
- **SU3 — Boundary (negative).** As a support user, if I try to create a formal next action, I'm refused.
  *Accept:* denied with a clear message; no database change; logged.

## `admin` — operations, full access
*Brief §4.4: full access, including creating and updating next actions.*

- **A1 — Set the directive.** As an admin, I want to create and update the next action on an issue, so the team has a clear, recorded instruction.
  *Accept:* `create_next_action` writes a `next_actions` row linked to the issue (attributable + timestamped); `update_next_action` changes it; visible on read.
- **A2 — Full visibility.** As an admin, I want everything support can do across all customers, with no role denials.
  *Accept:* all read + issue-update tools succeed regardless of customer; next-action tools available.

## Cross-cutting

- **X1 — Follow-up in context (this story justifies Redis).** As any user, I want to ask follow-ups that build on the previous turn ("…now summarise the second issue" → "what should I do next?"), so I don't re-state context.
  *Accept:* within a session, references like "the second one" / "that issue" resolve from **short-term memory (Redis)**; a fresh session does not carry the old context.

## Edge cases (prove answers are *grounded*)

- **E1 — Customer not found.** "Show issues for Zzzz Ltd" (doesn't exist).
  *Accept:* agent states no matching customer was found; **does not invent** a customer or issues.
- **E2 — Ambiguous name.** Two similar customers (e.g. "Acme" vs "Acme Group").
  *Accept:* agent **asks to disambiguate** or lists the candidates; does not silently guess.
- **E3 — No open issues.** Customer exists, nothing open.
  *Accept:* agent says "no open issues"; does not fabricate.

## The headline capability (decomposed)
> "Show me open issues for Client X, summarise the latest status, and suggest the next action."

A multi-tool query — proves **dynamic tool selection**: `get_open_issues` → `summarise_issue_history` → *suggest* a next action (advice; *persisting* it is admin-only via `create_next_action`).

## Role × tool matrix

| Tool | sales | support | admin |
|---|---|---|---|
| get_customer_profile (read) | ✅ | ✅ | ✅ |
| get_open_issues (read) | ✅ | ✅ | ✅ |
| summarise_issue_history (read) | ✅ | ✅ | ✅ |
| **update_issue** (write) — *5th tool* | 🚫 | ✅ | ✅ |
| create / update_next_action (write) | 🚫 | 🚫 | ✅ |
| Escalation Summary Skill (read synthesis) | ✅ | ✅ | ✅ |

---
> [!NOTE] Functional vs non-functional — where the other components live
> This file is **functional** (user-facing) stories. The remaining required components are **non-functional** and do not get user stories:
> - **MCP (Model Context Protocol)** — *how* tools are exposed to the agent → [04-Architecture](04-Architecture.md) + an ADR.
> - **Docker Compose** — *how* it's delivered (one command) → Definition of Done in [01-Frame](01-Frame.md) + [03-Scope](03-Scope.md).
> - **Eval + observability** — *how* we prove the above → [07-Evals](07-Evals.md), generated from the acceptance criteria above.
