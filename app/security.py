"""Keycloak token verification — the pure core, with no web-framework dependency.

Extracted from auth.py so it can be shared by *both* trust boundaries that must verify
the same Keycloak token (09-Security T1):
  * the API edge (app/auth.py wraps this in a FastAPI dependency to gate /ask), and
  * the MCP server (mcp/server.py re-verifies the forwarded token at the tool boundary,
    ADR-002/003 — role from the verified token, never a client header).

Keeping this FastAPI-free means the MCP image needs only `mcp`, `psycopg`, and `pyjwt`.
"""
import os

import jwt
from jwt import PyJWKClient

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")  # internal (JWKS/backchannel)
REALM = os.getenv("KEYCLOAK_REALM", "vantage")
# Tokens carry Keycloak's *public* hostname in `iss` (KC_HOSTNAME); keys are fetched on the
# *internal* URL. Verifying against the right issuer while fetching keys internally is the
# Keycloak frontend/backchannel split (same as running it behind a reverse proxy).
ISSUER = os.getenv("KEYCLOAK_ISSUER", f"{KEYCLOAK_URL}/realms/{REALM}")
JWKS_URL = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/certs"

# PyJWKClient caches Keycloak's signing keys (fetched lazily on first verify).
_jwks_client = PyJWKClient(JWKS_URL)


class Principal:
    """The verified caller: identity + realm roles (the source of truth for RBAC).

    `subject` is the token `sub` (Keycloak user id), used to attribute writes to the acting
    user via users.keycloak_id (ADR-002 attribution; see mcp_server/tools.py).
    """

    def __init__(self, username: str, roles: list[str], subject: str | None = None):
        self.username = username
        self.roles = roles
        self.subject = subject


def verify_access_token(token: str) -> Principal:
    """Verify a Keycloak access token and return the Principal; raise on any failure.

    Checks the RS256 signature against Keycloak's JWKS, the issuer, and expiry (T1).
    `alg` is pinned to RS256 so a forged `alg:none` token is never accepted. Audience is
    not enforced (Keycloak's default `aud` is "account" absent an audience mapper — a
    production hardening item, 09-Security). Raises `jwt`/lookup exceptions on a bad
    signature / issuer / expiry / malformed token; callers translate that to their own
    rejection (HTTP 401 at the API; a None AccessToken at the MCP boundary).
    """
    signing_key = _jwks_client.get_signing_key_from_jwt(token).key
    claims = jwt.decode(
        token,
        signing_key,
        algorithms=["RS256"],  # never allow "none"
        issuer=ISSUER,
        options={"verify_aud": False, "require": ["exp", "iat", "iss"]},
    )
    username = claims.get("preferred_username") or claims.get("sub", "unknown")
    roles = claims.get("realm_access", {}).get("roles", [])
    return Principal(username=username, roles=roles, subject=claims.get("sub"))
