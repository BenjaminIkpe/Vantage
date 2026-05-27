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
