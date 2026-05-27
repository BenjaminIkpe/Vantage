---
title: Evals
type: evals
status: draft
updated: 2026-05-26
---

# Evals

> [!NOTE] Purpose
> 5–10 test questions that prove the assistant works. These are your acceptance criteria made runnable — and a required deliverable. Derived from [02-User-Stories](02-User-Stories.md).

## What each case measures (from the brief)
- Correct **tool(s)** selected for the query
- Response **grounded** in database results (not invented)
- **RBAC** respected (right role allowed / denied)
- Recommended **next action** is reasonable

## Cases
| # | Query | Role | Expected tool(s) | Expected behaviour | Result |
| --- | --- | --- | --- | --- | --- |
| 1 | _(TBD)_ | | | | |
| 2 | _(TBD)_ | | | | |
| 3 | _(TBD)_ | | | | |
| … | | | | | |

> [!TIP] Include at least one negative case
> e.g. a `sales_user` asking to create a next action → expected: **denied** by RBAC. Proves the security boundary, not just the happy path.
