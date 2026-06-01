"""Vantage MCP server — the nine named tools exposed over MCP (Streamable HTTP).

Why MCP (ADR-003): the agent *discovers and calls named tools*, never raw SQL. This
server owns the database (only it holds DATABASE_URL) and re-verifies the caller's
Keycloak token at the tool boundary (ADR-002 — role from the verified token, never a
client header), so even a fully prompt-injected agent can't exceed the caller's
permissions or run arbitrary SQL (09-Security T3/T4). *The LLM proposes; the tool disposes.*

Flow: the API forwards the user's bearer token → the SDK's bearer middleware calls
KeycloakVerifier (same JWKS/issuer as the API) → a verified VantageToken carries the
realm roles → each tool reads it via get_access_token() and checks the role before
touching Postgres. A missing/invalid token is rejected with 401 by the transport.

Exposes eleven tools — three reads, three browse/list (paginated), three RBAC-checked
writes, and two admin-only fleet aggregates (the proactive briefing's reads, ADR-008) —
each discovered and called by the agent (or the briefing graph) via MCP discovery.
"""
import logging
import os

from mcp.server.fastmcp import FastMCP
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.auth.middleware.auth_context import get_access_token

from security import Principal, verify_access_token
from tools import (
    create_next_action,
    detect_patterns,
    get_customer_profile,
    get_high_risk_customers,
    get_open_issues,
    list_customers,
    list_issues,
    list_next_actions,
    summarise_issue_history,
    update_issue,
    update_next_action,
)

logging.basicConfig(level=logging.INFO)
_audit_log = logging.getLogger("vantage.audit")

ISSUER = os.getenv("KEYCLOAK_ISSUER", "http://localhost:8080/realms/vantage")
PORT = int(os.getenv("MCP_PORT", "8001"))
# Advertised resource identifier (OAuth metadata); the real check is KeycloakVerifier.
RESOURCE_URL = os.getenv("MCP_RESOURCE_URL", f"http://localhost:{PORT}/mcp")


class VantageToken(AccessToken):
    """An AccessToken carrying the verified Keycloak identity + realm roles.

    The bearer middleware stores whatever the verifier returns (as-is), so subclassing
    lets the realm roles ride through to the tool via get_access_token().
    """

    username: str
    roles: list[str]
    subject: str | None = None  # token `sub`, for write attribution


class KeycloakVerifier(TokenVerifier):
    """Re-verify the forwarded Keycloak JWT at the MCP boundary (ADR-002/003)."""

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            principal = verify_access_token(token)
        except Exception:
            return None  # transport replies 401 — no tool ever runs
        return VantageToken(
            token=token,
            client_id=principal.username,
            scopes=principal.roles,  # realm roles surfaced as scopes for the framework
            username=principal.username,
            roles=principal.roles,
            subject=principal.subject,
        )


mcp = FastMCP(
    "vantage-tools",
    host="0.0.0.0",
    port=PORT,
    token_verifier=KeycloakVerifier(),
    auth=AuthSettings(issuer_url=ISSUER, resource_server_url=RESOURCE_URL),
)


def _principal() -> Principal:
    """The verified caller for the current MCP request (set by the bearer middleware)."""
    tok = get_access_token()
    if not isinstance(tok, VantageToken):  # auth is required, so this is defensive
        raise RuntimeError("no authenticated principal on the request")
    return Principal(username=tok.username, roles=tok.roles, subject=tok.subject)


def _audit(tool: str, principal: Principal, target, result: dict) -> dict:
    """Log a write attempt + its decision for the audit trail — identifiers and action only,
    never the token or free-text bodies (09-Security T7). Returns the result unchanged."""
    _audit_log.info(
        "tool=%s user=%s roles=%s target=%s decision=%s",
        tool, principal.username, principal.roles, target, result.get("status"),
    )
    return result


@mcp.tool(
    name="get_customer_profile",
    description=(
        "Look up a customer by name (or partial name). Returns the profile when exactly "
        "one matches, a list of candidates when the name is ambiguous, or not_found when "
        "no customer matches. Always use this to resolve a customer before answering "
        "questions about them — never guess a customer."
    ),
)
def _get_customer_profile(name: str) -> dict:
    return get_customer_profile(name, _principal())


@mcp.tool(
    name="get_open_issues",
    description=(
        "List a customer's OPEN support issues (open, in_progress, or pending), most "
        "urgent first. Takes a customer name and resolves it the same way as "
        "get_customer_profile, so it returns not_found for an unknown name and a list of "
        "candidates for an ambiguous one — in those cases ask which customer is meant "
        "rather than guessing. A known customer with nothing open returns an empty list "
        "(say plainly that they have no open issues). Each issue includes its id, which "
        "you can pass to summarise_issue_history for the detail behind it."
    ),
)
def _get_open_issues(name: str) -> dict:
    return get_open_issues(name, _principal())


@mcp.tool(
    name="summarise_issue_history",
    description=(
        "Fetch one issue plus its full audit trail (every update, oldest first) AND any "
        "recorded next actions on it, by issue id. Use it to explain how an issue evolved, "
        "to ground an escalation summary, or to find next-action ids before calling "
        "update_next_action. Get the issue id from get_open_issues. Returns not_found for "
        "an unknown id. Summarise only from what's returned; never invent history."
    ),
)
def _summarise_issue_history(issue_id: int) -> dict:
    return summarise_issue_history(issue_id, _principal())


# --- browse / list tools (read; all roles) ----------------------------------
# Use these when the user wants to *explore* without naming a specific customer or id —
# 'who are our customers', 'show me critical issues', 'what next actions are overdue'.
# All paginated with sensible defaults; return total_count + has_more so the agent can
# fetch the next page if the user asks.


@mcp.tool(
    name="list_customers",
    description=(
        "List customers across the platform with optional filters, paginated. Use this when "
        "the user wants to BROWSE or EXPLORE customers without naming one — e.g. 'who are "
        "our customers', 'show me Enterprise accounts', 'customers in Scotland', 'list my "
        "portfolio'. Filters: `q` (partial name OR account_ref), `region`, `segment` "
        "(SMB/Mid-Market/Enterprise), `tier` (standard/premium/strategic), `account_manager` "
        "(partial display name). Returns customers sorted alphabetically by name, plus "
        "`total_count` and `has_more` for pagination. Do not use when the user names a "
        "specific customer — use get_customer_profile or get_open_issues instead."
    ),
)
def _list_customers(q: str | None = None, region: str | None = None,
                    segment: str | None = None, tier: str | None = None,
                    account_manager: str | None = None,
                    limit: int = 20, offset: int = 0) -> dict:
    return list_customers(_principal(), q=q, region=region, segment=segment, tier=tier,
                          account_manager=account_manager, limit=limit, offset=offset)


@mcp.tool(
    name="list_issues",
    description=(
        "List issues across ALL customers with optional filters, paginated. Use for "
        "cross-customer triage and exploration — e.g. 'all critical open issues', 'my "
        "open issues' (with assigned_to=user's name), 'integration backlog', 'pending "
        "tickets'. Filters: `status` (open/in_progress/pending/resolved/closed, plus the "
        "convenience value 'open' which matches any open-bucket value), `priority`, "
        "`category`, `customer` (partial name), `assigned_to` (partial display name). "
        "Sorted critical→low priority, then oldest-first. Returns issues with their "
        "customer attached. Use get_open_issues instead when the user names a single "
        "customer; use this when the customer is unspecified or it's a cross-customer query."
    ),
)
def _list_issues(status: str | None = None, priority: str | None = None,
                 category: str | None = None, customer: str | None = None,
                 assigned_to: str | None = None,
                 limit: int = 20, offset: int = 0) -> dict:
    return list_issues(_principal(), status=status, priority=priority, category=category,
                       customer=customer, assigned_to=assigned_to, limit=limit, offset=offset)


@mcp.tool(
    name="list_next_actions",
    description=(
        "List recorded next actions (admin directives) across all issues/customers, "
        "paginated. Use for admin oversight — e.g. 'what next actions are overdue', "
        "'show me open admin work', 'next actions Dana has created'. Filters: `status` "
        "(open/done/cancelled), `overdue` (true → open items past their due_date), "
        "`customer` (partial name), `created_by` (partial display name). Sorted by "
        "status (open first) then due_date ascending."
    ),
)
def _list_next_actions(status: str | None = None, overdue: bool = False,
                       customer: str | None = None, created_by: str | None = None,
                       limit: int = 20, offset: int = 0) -> dict:
    return list_next_actions(_principal(), status=status, overdue=overdue,
                             customer=customer, created_by=created_by,
                             limit=limit, offset=offset)


# --- write tools (RBAC-checked inside the tool; every attempt audited) -------


@mcp.tool(
    name="update_issue",
    description=(
        "Add a note to an issue and/or change its status (requires the support or admin "
        "role). Pass issue_id and a note, a new status (open/in_progress/pending/resolved/"
        "closed), or both. Writes an attributable, timestamped update. Returns status "
        "'denied' if the caller's role may not update issues — relay that refusal to the "
        "user; do not retry. Returns 'not_found' for an unknown issue."
    ),
)
def _update_issue(issue_id: int, note: str | None = None, status: str | None = None) -> dict:
    principal = _principal()
    result = update_issue(issue_id, principal, note=note, status=status)
    return _audit("update_issue", principal, f"issue={issue_id} status={status!r}", result)


@mcp.tool(
    name="create_next_action",
    description=(
        "Create a formal next action on an issue (requires the admin role). Pass issue_id, "
        "a description, and optionally a due_date (YYYY-MM-DD). Returns status 'denied' if "
        "the caller is not an admin — relay that refusal to the user; do not retry. Returns "
        "'not_found' for an unknown issue. (Sales/support may receive a next action as "
        "advice, but only an admin can record one.)"
    ),
)
def _create_next_action(issue_id: int, description: str, due_date: str | None = None) -> dict:
    principal = _principal()
    result = create_next_action(issue_id, principal, description=description, due_date=due_date)
    return _audit("create_next_action", principal, f"issue={issue_id}", result)


@mcp.tool(
    name="update_next_action",
    description=(
        "Update a next action's status (open/done/cancelled), description, or due_date by "
        "next_action_id (requires the admin role). Returns status 'denied' if the caller is "
        "not an admin — relay that refusal; do not retry. Returns 'not_found' for an "
        "unknown id."
    ),
)
def _update_next_action(next_action_id: int, status: str | None = None,
                        description: str | None = None, due_date: str | None = None) -> dict:
    principal = _principal()
    result = update_next_action(next_action_id, principal, status=status,
                                description=description, due_date=due_date)
    return _audit("update_next_action", principal, f"next_action={next_action_id} status={status!r}", result)


# --- proactive briefing aggregates (admin-only reads; access audited, ADR-008) -----------
# These power GET /briefing's LangGraph run. Admin-only at the same boundary as the writes
# (the fleet-wide view is privileged oversight); the access is audited like a write so the
# 'who saw the whole portfolio' question has an answer too (T7).


@mcp.tool(
    name="get_high_risk_customers",
    description=(
        "Admin only. Rank the customers most at risk by their OPEN issues — those with at "
        "least one critical or high open issue — most critical first. Use this to pick which "
        "accounts a fleet-wide briefing should cover. Returns each account's open critical / "
        "high / total counts, plus how many high-risk accounts exist in total (so you can say "
        "'top N of M'). Returns status 'denied' for non-admin callers; relay that and do not "
        "retry. It reads only what an admin could already pull — it just aggregates it."
    ),
)
def _get_high_risk_customers(limit: int = 5) -> dict:
    principal = _principal()
    result = get_high_risk_customers(principal, limit=limit)
    return _audit("get_high_risk_customers", principal, f"limit={limit}", result)


@mcp.tool(
    name="detect_patterns",
    description=(
        "Admin only. Detect cross-customer patterns among OPEN issues: categories that are "
        "open at two or more distinct customers — a platform-level signal no single-customer "
        "view can produce (e.g. 'webhook/integration errors across 4 accounts -> likely a "
        "platform incident'). Optionally pass window_days to narrow to recently-created issues; "
        "omit it to consider all open issues. Returns status 'denied' for non-admins; relay it "
        "and do not retry."
    ),
)
def _detect_patterns(window_days: int | None = None, min_customers: int = 2) -> dict:
    principal = _principal()
    result = detect_patterns(principal, window_days=window_days, min_customers=min_customers)
    return _audit("detect_patterns", principal, f"window_days={window_days}", result)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
