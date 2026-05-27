"""Keycloak JWT verification — see Vantage-vault/09-Security.md (T1, T2)."""
import os

import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")  # internal (JWKS/backchannel)
REALM = os.getenv("KEYCLOAK_REALM", "vantage")
# Tokens carry Keycloak's *public* hostname in `iss` (KC_HOSTNAME); keys are fetched on the
# *internal* URL. Verifying against the right issuer while fetching keys internally is the
# Keycloak frontend/backchannel split (same as running it behind a reverse proxy).
ISSUER = os.getenv("KEYCLOAK_ISSUER", f"{KEYCLOAK_URL}/realms/{REALM}")
JWKS_URL = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/certs"

# PyJWKClient caches Keycloak's signing keys (fetched lazily on first verify).
_jwks_client = PyJWKClient(JWKS_URL)
_bearer = HTTPBearer()


class Principal:
    """The verified caller: identity + realm roles (the source of truth for RBAC)."""

    def __init__(self, username: str, roles: list[str]):
        self.username = username
        self.roles = roles


def verify_token(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> Principal:
    """Verify a Keycloak access token: RS256 signature (JWKS) + issuer + expiry (T1).

    Audience is not enforced here: Keycloak's default `aud` is "account" unless an
    audience mapper is configured, so verifying it is a production hardening item
    (09-Security). Signature/issuer/expiry verification is what defeats forged or
    tampered tokens, and `alg` is pinned to RS256 so `none` is never accepted.
    """
    token = creds.credentials
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],  # never allow "none"
            issuer=ISSUER,
            options={"verify_aud": False, "require": ["exp", "iat", "iss"]},
        )
    except Exception as exc:  # bad signature / issuer / expiry / malformed
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token: {exc}",
        )
    username = claims.get("preferred_username") or claims.get("sub", "unknown")
    roles = claims.get("realm_access", {}).get("roles", [])
    return Principal(username=username, roles=roles)


def require_role(*allowed: str):
    """Dependency factory: allow only callers holding one of `allowed` realm roles (T2)."""

    def _checker(principal: Principal = Depends(verify_token)) -> Principal:
        if not any(role in principal.roles for role in allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires one of roles: {list(allowed)}",
            )
        return principal

    return _checker
