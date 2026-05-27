"""FastAPI auth adapter — wraps the pure verifier in security.py as request dependencies.

The token verification itself (signature/issuer/expiry, T1) lives in security.py so the
MCP server can reuse it without pulling in FastAPI. This module adds only the web layer:
bearer extraction, the 401 translation, and the role-gate dependency factory (T2).
See Vantage-vault/09-Security.md.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from security import Principal, verify_access_token  # re-exported for callers

_bearer = HTTPBearer()


def verify_token(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> Principal:
    """Verify the bearer token (delegates to security.verify_access_token); 401 on failure."""
    try:
        return verify_access_token(creds.credentials)
    except Exception as exc:  # bad signature / issuer / expiry / malformed
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token: {exc}",
        )


class Authed:
    """A verified caller plus the raw token, so the API can forward it to the MCP server."""

    def __init__(self, principal: Principal, token: str):
        self.principal = principal
        self.token = token


def authed(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> Authed:
    """Gate the request (verify the token) and hand back the token to forward downstream.

    The API verifies here to fail fast (don't run the agent for an unauthenticated caller);
    the MCP server re-verifies the forwarded token at the tool boundary (ADR-002/003).
    """
    return Authed(verify_token(creds), creds.credentials)


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
