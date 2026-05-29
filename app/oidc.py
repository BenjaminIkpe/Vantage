"""OIDC Authorization Code + PKCE flow against Keycloak (BFF pattern; ADR-002 hardening).

The Backend-for-Frontend pattern: tokens are exchanged and stored **server-side** in Redis,
indexed by an httpOnly Secure SameSite cookie. The browser never sees the access token, so
XSS-stealing-the-token is structurally off the table — strictly better than localStorage *or*
sessionStorage (OWASP 2024-25). The MCP server still re-verifies the forwarded token at the
tool boundary (ADR-003), so the security model is layered, not perimeter-only.

This module owns only the protocol mechanics (PKCE generation, authorize-URL building,
code→token exchange, logout). The session-cookie + Redis storage lives in `app/session.py`;
the FastAPI endpoints (`/auth/login`, `/auth/callback`, `/auth/logout`, `/auth/whoami`) live
in `app/main.py`. `app/security.py` still owns the JWT verification on the resulting token,
so the same code path is used at both edges (API gate + MCP boundary; ADR-002/003).

ROPC stays enabled on the same Keycloak client for the eval harness / smoke tests — the
auth-code flow is **additive**, not a replacement (the API's `authed` dependency accepts a
Bearer header OR the session cookie). RFC 9700 (2024) deprecated ROPC for production user
logins; we keep it only for automated test clients and document the split in 09-Security.
"""
import base64
import hashlib
import os
import secrets
from urllib.parse import urlencode

import httpx

CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "vantage-api")
CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "vantage-secret")
REALM = os.getenv("KEYCLOAK_REALM", "vantage")

# Internal URL the *server* uses to call Keycloak (backchannel — token exchange, logout).
# Container-to-container on the Compose network; never the URL the browser visits.
KEYCLOAK_INTERNAL_URL = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")

# Public URL the *browser* uses to reach Keycloak's login page (frontchannel). Defaults to
# localhost for local dev; override to a Codespaces-/proxy-forwarded URL when the browser
# accesses Keycloak from outside the Compose network.
KEYCLOAK_PUBLIC_URL = os.getenv("KEYCLOAK_PUBLIC_URL", "http://localhost:8080")


def gen_pkce() -> tuple[str, str]:
    """Generate a PKCE (RFC 7636) verifier + S256 challenge.

    The verifier is the secret the server stashes; the challenge is the hashed value the
    browser carries to Keycloak. Keycloak re-hashes our verifier at token exchange and
    rejects the swap if it doesn't match — proves the code redemption came from the same
    flow as the authorize redirect, even if the redirect_uri itself was hijacked.
    """
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def gen_state() -> str:
    """Cryptographically-random opaque CSRF token for the OAuth `state` param."""
    return secrets.token_urlsafe(32)


def gen_sid() -> str:
    """Opaque server-side session id for the cookie value (BFF — never a JWT)."""
    return secrets.token_urlsafe(32)


def authorize_url(redirect_uri: str, state: str, code_challenge: str,
                  login_hint: str | None = None, prompt: str | None = None) -> str:
    """Build the Keycloak authorize endpoint URL the browser should be redirected to.

    `login_hint` pre-fills the username on Keycloak's form (used by the role-switcher to
    suggest the target persona). `prompt=login` forces Keycloak to re-authenticate even
    when its SSO cookie still has a valid session — without it, clicking 'switch to admin'
    would silently sign you back in as the *current* user via SSO. Together they make
    the role-switcher a real identity swap, not a cosmetic flip.
    """
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": "openid profile email",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if login_hint:
        params["login_hint"] = login_hint
    if prompt:
        params["prompt"] = prompt
    return f"{KEYCLOAK_PUBLIC_URL}/realms/{REALM}/protocol/openid-connect/auth?{urlencode(params)}"


async def exchange_code(code: str, redirect_uri: str, code_verifier: str) -> dict:
    """POST to Keycloak's token endpoint to exchange the auth code for tokens.

    Server-to-server call over the *internal* URL (backchannel). Returns the token payload
    `{access_token, refresh_token, expires_in, id_token, ...}` on success; raises on failure.
    """
    url = f"{KEYCLOAK_INTERNAL_URL}/realms/{REALM}/protocol/openid-connect/token"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code_verifier": code_verifier,
        })
        resp.raise_for_status()
        return resp.json()


async def revoke_session(refresh_token: str) -> None:
    """Best-effort Keycloak logout — revokes the refresh token at the IDP so a stolen
    refresh token can't be used again. Errors are swallowed: we always clear our own
    session/cookie regardless of upstream availability."""
    if not refresh_token:
        return
    url = f"{KEYCLOAK_INTERNAL_URL}/realms/{REALM}/protocol/openid-connect/logout"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "refresh_token": refresh_token,
            })
    except Exception:
        pass
