"""Agent tools — each is a standalone, typed, RBAC-checked function using
parameterised SQL (04-Architecture; ADR-002/003; 09-Security T2/T3).

Reads are allowed for every authenticated role; write tools (later) check the
role from the verified token before acting. Tools never invent data: a missing
customer returns `not_found`, near-identical names return `ambiguous`.
"""
from db import query
from auth import Principal

_CUSTOMER_COLS = "id, name, account_ref, region, postcode, segment, tier"

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
    """Return an issue plus its full audit trail, oldest update first.

    The *tool* returns the grounded history; the agent does the summarising — so the
    summary is always anchored to real updates, never invented. Any authenticated
    role may read.

    Returns one of:
      {"status": "found", "issue": {...}, "updates": [{author, body, update_type, created_at}, ...]}
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
    return {"status": "found", "issue": issue[0], "updates": updates}
