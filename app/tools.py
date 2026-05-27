"""Agent tools — each is a standalone, typed, RBAC-checked function using
parameterised SQL (04-Architecture; ADR-002/003; 09-Security T2/T3).

Reads are allowed for every authenticated role; write tools (later) check the
role from the verified token before acting. Tools never invent data: a missing
customer returns `not_found`, near-identical names return `ambiguous`.
"""
from db import query
from auth import Principal

_CUSTOMER_COLS = "id, name, account_ref, region, postcode, segment, tier"


def get_customer_profile(name: str, principal: Principal) -> dict:
    """Look up a customer by name. Any authenticated role may read.

    Returns one of:
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
