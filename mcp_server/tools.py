"""Agent tools — each is a standalone, typed, RBAC-checked function using
parameterised SQL (04-Architecture; ADR-002/003; 09-Security T2/T3).

Reads are allowed for every authenticated role; write tools check the role from the
verified token (re-verified at the MCP boundary) before acting — a disallowed call makes
no database change, returns a structured `denied`, and is logged by the caller (ADR-002,
T2). Tools never invent data: a missing customer returns `not_found`, near-identical names
return `ambiguous`.
"""
from db import execute, query
from security import Principal

_CUSTOMER_COLS = "id, name, account_ref, region, postcode, segment, tier"

# Legal issue statuses (schema CHECK). Validated before a status write so a bad value is a
# clean `error`, not a database exception.
_ISSUE_STATUSES = ("open", "in_progress", "pending", "resolved", "closed")

# "Open" per 04-Architecture (the get_open_issues filter). Passed as a bound
# parameter via `= ANY(%s)`, never interpolated into the SQL string (T3).
OPEN_STATUSES = ["open", "in_progress", "pending"]


def _resolve_customer(name: str) -> dict:
    """Resolve a customer *name* (or partial name) to exactly one row.

    The single place customer disambiguation lives, shared by every tool that
    takes a customer name. Returns one of:
      {"status": "found", "customer": {...}}
      {"status": "ambiguous", "candidates": [{...}, ...]}   # e.g. the Lumen twins (E2)
      {"status": "not_found", "query": name}                # e.g. 'Zzzz Holdings' (E1)
    """
    exact = query(
        f"SELECT {_CUSTOMER_COLS} FROM customers WHERE lower(name) = lower(%s)",
        (name,),
    )
    if len(exact) == 1:
        return {"status": "found", "customer": exact[0]}

    like = query(
        f"SELECT {_CUSTOMER_COLS} FROM customers WHERE name ILIKE %s ORDER BY name",
        (f"%{name}%",),
    )
    if not like:
        return {"status": "not_found", "query": name}
    if len(like) == 1:
        return {"status": "found", "customer": like[0]}
    return {"status": "ambiguous", "candidates": like}


def get_customer_profile(name: str, principal: Principal) -> dict:
    """Look up a customer by name. Any authenticated role may read."""
    return _resolve_customer(name)


def get_open_issues(name: str, principal: Principal) -> dict:
    """List a customer's open issues (status ∈ open/in_progress/pending).

    Resolves the customer name first (so a wrong or ambiguous name never silently
    returns the wrong customer's issues), then returns the open issues most-urgent
    first (priority, then age). A real customer with none open returns an empty list
    rather than not_found (edge case E3). Any authenticated role may read.

    Returns one of:
      {"status": "found", "customer": {id,name,account_ref}, "open_issues": [...], "open_count": N}
      {"status": "ambiguous", "candidates": [...]}   # E2 — caller should disambiguate
      {"status": "not_found", "query": name}         # E1 — no such customer
    """
    resolved = _resolve_customer(name)
    if resolved["status"] != "found":
        return resolved

    customer = resolved["customer"]
    issues = query(
        """
        SELECT i.id, i.title, i.category, i.status, i.priority,
               i.created_at, i.updated_at, u.display_name AS assigned_to
        FROM issues i
        LEFT JOIN users u ON u.id = i.assigned_to
        WHERE i.customer_id = %s AND i.status = ANY(%s)
        ORDER BY CASE i.priority
                   WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                   WHEN 'medium'   THEN 2 WHEN 'low'  THEN 3
                 END,
                 i.created_at ASC
        """,
        (customer["id"], OPEN_STATUSES),
    )
    return {
        "status": "found",
        "customer": {k: customer[k] for k in ("id", "name", "account_ref")},
        "open_issues": issues,
        "open_count": len(issues),
    }


def summarise_issue_history(issue_id: int, principal: Principal) -> dict:
    """Return an issue plus its full audit trail AND any recorded next actions on it.

    The *tool* returns the grounded record; the agent does the summarising — so the
    summary is always anchored to real updates and real directives, never invented.
    Returning next actions here is the read path for them (A1 "visible on read") and
    lets the agent discover their ids to drive update_next_action. Any authenticated
    role may read (the write boundary is admin-only; reading the issue's record is open).

    Returns one of:
      {"status": "found", "issue": {...}, "updates": [...], "next_actions": [...]}
      {"status": "not_found", "issue_id": id}
    """
    issue = query(
        """
        SELECT i.id, i.title, i.description, i.category, i.status, i.priority,
               i.created_at, i.updated_at, c.name AS customer_name,
               c.account_ref, u.display_name AS assigned_to
        FROM issues i
        JOIN customers c ON c.id = i.customer_id
        LEFT JOIN users u ON u.id = i.assigned_to
        WHERE i.id = %s
        """,
        (issue_id,),
    )
    if not issue:
        return {"status": "not_found", "issue_id": issue_id}

    updates = query(
        """
        SELECT up.id, up.body, up.update_type, up.created_at,
               au.display_name AS author
        FROM issue_updates up
        LEFT JOIN users au ON au.id = up.author_id
        WHERE up.issue_id = %s
        ORDER BY up.created_at ASC
        """,
        (issue_id,),
    )
    next_actions = query(
        """
        SELECT na.id, na.description, na.due_date, na.status,
               na.created_at, na.updated_at, u.display_name AS created_by
        FROM next_actions na
        LEFT JOIN users u ON u.id = na.created_by_id
        WHERE na.issue_id = %s
        ORDER BY na.created_at ASC
        """,
        (issue_id,),
    )
    return {"status": "found", "issue": issue[0], "updates": updates, "next_actions": next_actions}


# --- write tools (RBAC-checked) ----------------------------------------------
# The role arrives already re-verified at the MCP boundary; these tools gate on it and
# attribute the write to the acting user. A disallowed call returns `denied` and writes
# nothing; the MCP server logs the attempt (ADR-002 / 09-Security T2).


def _denied(principal: Principal, *allowed: str) -> dict | None:
    """Return a structured denial if the caller lacks an allowed role, else None."""
    if any(role in principal.roles for role in allowed):
        return None
    return {
        "status": "denied",
        "reason": f"requires one of roles: {list(allowed)}; you have: {principal.roles}",
    }


def _acting_user_id(principal: Principal) -> int | None:
    """Resolve the acting user's users.id for attribution (keycloak_id = token sub)."""
    rows = query("SELECT id FROM users WHERE keycloak_id = %s", (principal.subject,))
    return rows[0]["id"] if rows else None


def update_issue(issue_id: int, principal: Principal,
                 note: str | None = None, status: str | None = None) -> dict:
    """Add a note to an issue and/or change its status (support or admin only, SU2).

    Writes an attributable, timestamped `issue_updates` row; a status change also updates
    the issue. Returns `denied` (no change) for sales; `not_found` for an unknown issue;
    `error` if neither note nor status is given or the status is invalid.
    """
    if denial := _denied(principal, "support_user", "admin"):
        return denial
    if not note and not status:
        return {"status": "error", "reason": "provide a note, a new status, or both"}
    if status and status not in _ISSUE_STATUSES:
        return {"status": "error", "reason": f"invalid status; must be one of {list(_ISSUE_STATUSES)}"}

    author_id = _acting_user_id(principal)
    if author_id is None:
        return {"status": "error", "reason": "acting user not found for attribution"}

    current = query("SELECT id, status FROM issues WHERE id = %s", (issue_id,))
    if not current:
        return {"status": "not_found", "issue_id": issue_id}
    old_status = current[0]["status"]

    if status:
        update_type = "status_change"
        body = note or f"Status changed from {old_status} to {status}."
        execute("UPDATE issues SET status = %s, updated_at = now() WHERE id = %s", (status, issue_id))
    else:
        update_type, body = "note", note

    written = execute(
        """
        INSERT INTO issue_updates (issue_id, author_id, body, update_type)
        VALUES (%s, %s, %s, %s)
        RETURNING id, issue_id, body, update_type, created_at
        """,
        (issue_id, author_id, body, update_type),
    )
    return {
        "status": "updated",
        "issue_id": issue_id,
        "new_status": status or old_status,
        "update": written[0],
    }


def create_next_action(issue_id: int, principal: Principal,
                       description: str, due_date: str | None = None) -> dict:
    """Create a formal next action on an issue (admin only, A1).

    Writes an attributable, timestamped `next_actions` row (status 'open'). Returns `denied`
    (no change) for non-admins; `not_found` for an unknown issue.
    """
    if denial := _denied(principal, "admin"):
        return denial
    creator_id = _acting_user_id(principal)
    if creator_id is None:
        return {"status": "error", "reason": "acting user not found for attribution"}
    if not query("SELECT id FROM issues WHERE id = %s", (issue_id,)):
        return {"status": "not_found", "issue_id": issue_id}

    written = execute(
        """
        INSERT INTO next_actions (issue_id, created_by_id, description, due_date)
        VALUES (%s, %s, %s, %s)
        RETURNING id, issue_id, description, due_date, status, created_at
        """,
        (issue_id, creator_id, description, due_date),
    )
    return {"status": "created", "next_action": written[0]}


def update_next_action(next_action_id: int, principal: Principal,
                       status: str | None = None, description: str | None = None,
                       due_date: str | None = None) -> dict:
    """Update a next action's status/description/due date (admin only, A1).

    Returns `denied` (no change) for non-admins; `not_found` for an unknown id; `error` if
    nothing to change or the status is invalid.
    """
    if denial := _denied(principal, "admin"):
        return denial
    if status and status not in ("open", "done", "cancelled"):
        return {"status": "error", "reason": "invalid status; must be one of ['open', 'done', 'cancelled']"}
    if status is None and description is None and due_date is None:
        return {"status": "error", "reason": "provide a status, description, or due_date to change"}
    if not query("SELECT id FROM next_actions WHERE id = %s", (next_action_id,)):
        return {"status": "not_found", "next_action_id": next_action_id}

    # Build a COALESCE update so unspecified fields keep their current value (all bound, T3).
    written = execute(
        """
        UPDATE next_actions
        SET status      = COALESCE(%s, status),
            description = COALESCE(%s, description),
            due_date    = COALESCE(%s, due_date),
            updated_at  = now()
        WHERE id = %s
        RETURNING id, issue_id, description, due_date, status, updated_at
        """,
        (status, description, due_date, next_action_id),
    )
    return {"status": "updated", "next_action": written[0]}
