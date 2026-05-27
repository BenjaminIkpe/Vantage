"""Vantage MCP server — the five named tools exposed over MCP (Streamable HTTP).

Why MCP (ADR-003): the agent *discovers and calls named tools*, never raw SQL. This
server owns the database (only it holds DATABASE_URL) and re-verifies the caller's
Keycloak token at the tool boundary (ADR-002 — role from the verified token, never a
client header), so even a fully prompt-injected agent can't exceed the caller's
permissions or run arbitrary SQL (09-Security T3/T4). *The LLM proposes; the tool disposes.*

Flow: the API forwards the user's bearer token → the SDK's bearer middleware calls
KeycloakVerifier (same JWKS/issuer as the API) → a verified VantageToken carries the
realm roles → each tool reads it via get_access_token() and checks the role before
touching Postgres. A missing/invalid token is rejected with 401 by the transport.

Currently exposes the three read tools; the write tools land in a later slice and will
appear to the agent automatically via MCP discovery.
"""
import os

from mcp.server.fastmcp import FastMCP
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.auth.middleware.auth_context import get_access_token

from security import Principal, verify_access_token
from tools import get_customer_profile, get_open_issues, summarise_issue_history

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
    return Principal(username=tok.username, roles=tok.roles)


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
        "Fetch one issue plus its full audit trail (every update, oldest first) by issue "
        "id — use it to explain how an issue evolved or to ground an escalation summary. "
        "Get the id from get_open_issues. Returns not_found for an unknown id. Summarise "
        "only from the updates returned; never invent history."
    ),
)
def _summarise_issue_history(issue_id: int) -> dict:
    return summarise_issue_history(issue_id, _principal())


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
