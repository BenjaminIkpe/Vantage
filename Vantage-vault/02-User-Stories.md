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
- **S4 — Pre-renewal risk flag.** As a sales user, before a renewal call I want to know if the account is at risk, so I walk in informed.
  *Accept:* returns a risk level + the contributing real issues; **persists nothing**; if no open issues, says "Low / no concerns" rather than inventing risk.
- **S5 — What's changed since last check.** As a sales user, I want to see the *recent* updates on a customer's issues, so I can give them a current status.
  *Accept:* surfaces the most-recent updates (ordered by time) read from the issue history; never invents activity.
- **S6 — Category-filtered open issues.** As a sales user, I want only a customer's *compliance* (or *payments*, or *integration*) open issues, so I focus the call on one thread.
  *Accept:* agent uses `get_open_issues` then filters by the requested category in its answer; returns "none in that category" honestly when there are none.
- **S7 — Multi-account portfolio glance.** As a sales user, before back-to-back calls I want a quick health summary across two or three accounts, so I prep efficiently.
  *Accept:* per-account brief; not-found / ambiguous names handled **per account** (the run doesn't fail on one bad name); never invents an account.
- **S8 — Cross-team handoff brief.** As a sales user, I want a one-paragraph brief I can paste to support or compliance when handing off an issue, so the receiver has context.
  *Accept:* a paste-ready brief grounded in the issue + history (no invention); **persists nothing**.
- **S9 — Visible directives (admin's plan).** As a sales user, when an admin has recorded next actions on a customer's issues, I want to *see* them, so my message to the client matches what ops is already doing.
  *Accept:* surfaces the issue's `next_actions` via `summarise_issue_history` (read only); never creates or updates them.

## `support_user` — reactive support, read + update issues
*Brief §4.4: read and update access for issues.*

- **SU1 — Pick up an issue.** As a support user, I want a customer's open issues and the full history of a specific one, so I can take it on cold.
  *Accept:* returns the open-issue list, then the **chronological history + current status** of the chosen issue.
- **SU2 — Record the work.** As a support user, I want to add a note and change an issue's status, so the record reflects what I did.
  *Accept:* `update_issue` writes an `issue_updates` entry and/or status change, **attributable to me and timestamped**, visible on the next read.
- **SU3 — Boundary (negative).** As a support user, if I try to create a formal next action, I'm refused.
  *Accept:* denied with a clear message; no database change; logged.
- **SU4 — Customer triage glance.** As a support user, I want a customer's open issues ordered by priority, so I tackle the most urgent first.
  *Accept:* `get_open_issues` returns them critical→high→medium→low; assignment + status visible.
- **SU5 — Take an issue (mark in progress).** As a support user, when I pick up an open issue I want to move it to `in_progress` with a starting note, so the queue and the audit trail reflect that I'm on it.
  *Accept:* `update_issue` writes a status_change row to `in_progress` + the note; attributable + timestamped; visible on next read.
- **SU6 — Close with a resolution note.** As a support user, when I've fixed an issue I want to add the resolution note and set status `resolved` in one go.
  *Accept:* `update_issue` writes both (one update row recording the transition with the resolution body); visible on next read.
- **SU7 — Catch up after a colleague's update.** As a support user, when a colleague has just updated an issue I'm working on, I want the *latest* state and the recent notes, so I'm caught up before continuing.
  *Accept:* `summarise_issue_history` returns updates oldest→newest with current status; nothing invented.
- **SU8 — See the admin's directive on my issue.** As a support user, when I open an issue I'm working, I want to also see any `next_actions` an admin has set, so my work aligns with the formal directive.
  *Accept:* `summarise_issue_history` returns the issue's `next_actions` (PR #13); support has read access (write boundary stays admin-only).
- **SU9 — Focused queue by category.** As a support user, I want only the *integration* (or *payments*, etc.) open issues for a customer, so I work to my expertise.
  *Accept:* agent filters the `get_open_issues` result to the requested category; "none in that category" is an honest answer.

## `admin` — operations, full access
*Brief §4.4: full access, including creating and updating next actions.*

- **A1 — Set the directive.** As an admin, I want to create and update the next action on an issue, so the team has a clear, recorded instruction.
  *Accept:* `create_next_action` writes a `next_actions` row linked to the issue (attributable + timestamped); `update_next_action` changes it; visible on read.
- **A2 — Full visibility.** As an admin, I want everything support can do across all customers, with no role denials.
  *Accept:* all read + issue-update tools succeed regardless of customer; next-action tools available.
- **A3 — Cancel a next action.** As an admin, when a next action is no longer relevant I want to mark it `cancelled` (rather than delete it), so the record reflects the decision.
  *Accept:* `update_next_action(status='cancelled')` on the right id; visible on next read; the row stays for the audit trail.
- **A4 — Extend a deadline.** As an admin, I want to push a next action's `due_date` out without changing its description, so plans adjust without rewriting history.
  *Accept:* `update_next_action(due_date=...)` only changes the date; description/status unchanged; `updated_at` reflects the change.
- **A5 — Record the directive after support's work.** As an admin, after support has noted progress on an issue, I want to record the formal next action for the team to execute.
  *Accept:* `create_next_action` writes an attributable, timestamped row; visible on the issue's next read.
- **A6 — Cross-customer work in one sitting.** As an admin, I want to write notes and set next actions across several customers in one session without re-authenticating or hitting denials.
  *Accept:* every write succeeds; the trace shows the right tools per customer; no role denials.

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
- **E4 — Whitespace-tolerant name.** A name typed with leading/trailing spaces (`"  Velocity Marketplace  "`) should still resolve.
  *Accept:* the lookup trims and resolves correctly; an obvious typo isn't punished with a "not found".
- **E5 — Case-insensitive name.** Lower, upper, and mixed case names resolve identically.
  *Accept:* `velocity marketplace` and `VELOCITY MARKETPLACE` and `Velocity Marketplace` all return the same customer.
- **E6 — Idempotent status update.** Asking to resolve an issue that's already `resolved` should not error.
  *Accept:* `update_issue(status='resolved')` succeeds idempotently (status stays resolved; an audit row records the no-op transition).
- **E7 — Update a non-existent issue.** Asking to update `update_issue(issue_id=99999)` should not crash.
  *Accept:* tool returns `{"status": "not_found", "issue_id": 99999}`; agent relays it plainly.

## The headline capability (decomposed)
> "Show me open issues for Client X, summarise the latest status, and suggest the next action."

A multi-tool query — proves **dynamic tool selection**: `get_open_issues` → `summarise_issue_history` → *suggest* a next action (advice; *persisting* it is admin-only via `create_next_action`).

## Role × tool matrix

| Tool | sales | support | admin |
|---|---|---|---|
| get_customer_profile (read) | ✅ | ✅ | ✅ |
| get_open_issues (read) | ✅ | ✅ | ✅ |
| summarise_issue_history (read) | ✅ | ✅ | ✅ |
| list_customers · list_issues · list_next_actions (browse, read) | ✅ | ✅ | ✅ |
| **update_issue** (write) | 🚫 | ✅ | ✅ |
| create / update_next_action (write) | 🚫 | 🚫 | ✅ |
| get_high_risk_customers · detect_patterns (admin-only fleet) | 🚫 | 🚫 | ✅ |
| Escalation Summary Skill (read synthesis) | ✅ | ✅ | ✅ |

---
> [!NOTE] Functional vs non-functional — where the other components live
> This file is **functional** (user-facing) stories. The remaining required components are **non-functional** and do not get user stories:
> - **MCP (Model Context Protocol)** — *how* tools are exposed to the agent → [04-Architecture](04-Architecture.md) + an ADR.
> - **Docker Compose** — *how* it's delivered (one command) → Definition of Done in [01-Frame](01-Frame.md) + [03-Scope](03-Scope.md).
> - **Eval + observability** — *how* we prove the above → [07-Evals](07-Evals.md), generated from the acceptance criteria above.
