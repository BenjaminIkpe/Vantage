"""FastAPI auth adapter — wraps the pure verifier in security.py as request dependencies.

The token verification itself (signature/issuer/expiry, T1) lives in security.py so the
MCP server can reuse it without pulling in FastAPI. This module adds the web layer:
bearer extraction, **OIDC session-cookie extraction (BFF pattern)**, the 401 translation,
and the role-gate dependency factory (T2). See Vantage-vault/09-Security.md.

The `authed` dependency accepts **either** auth method, in this order:
  1. `Authorization: Bearer <jwt>` header — for programmatic clients (eval harness, smoke
     test, curl). Backward-compatible with everything that worked before OIDC.
  2. `vantage_sid` httpOnly cookie — for the browser UI (server-side session lookup in
     Redis). The access token is never sent to the browser.
Both paths produce the same `Principal`; the MCP server sees the same access token forwarded
either way (ADR-002/003 — RBAC re-verified at the tool boundary regardless of front auth).
"""
from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from security import Principal, verify_access_token  # re-exported for callers
from session import load_auth_session

# auto_error=False so a missing Bearer doesn't 401 before we check the cookie. Both paths
# converge in `authed` below; either is a valid auth source.
_bearer = HTTPBearer(auto_error=False)
_bearer_required = HTTPBearer()  # for the legacy `verify_token` dep (Bearer-only)


def verify_token(creds: HTTPAuthorizationCredentials = Depends(_bearer_required)) -> Principal:
    """Bearer-only dependency (legacy / programmatic). Use `authed` for endpoints the UI hits."""
    try:
        return verify_access_token(creds.credentials)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token: {exc}",
        )


class Authed:
    """A verified caller plus the raw access token (so the API can forward it to MCP)."""

    def __init__(self, principal: Principal, token: str):
        self.principal = principal
        self.token = token


def authed(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    vantage_sid: str | None = Cookie(default=None),
) -> Authed:
    """Gate a request via Bearer header OR session cookie; 401 on neither.

    Bearer takes precedence (programmatic clients keep working). On the cookie path we
    re-verify the stored access token (same `verify_access_token` the MCP boundary uses) so
    a tampered/expired session can't silently slip through — no trust-on-store.
    """
    if creds is not None:
        try:
            return Authed(verify_access_token(creds.credentials), creds.credentials)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"invalid bearer token: {exc}",
            )

    if vantage_sid:
        sess = load_auth_session(vantage_sid)
        if not sess:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="session expired or invalid",
            )
        token = sess.get("access_token", "")
        try:
            principal = verify_access_token(token)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"invalid session token: {exc}",
            )
        return Authed(principal, token)

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")


def require_role(*allowed: str):
    """Dependency factory: allow only callers holding one of `allowed` realm roles (T2)."""

    def _checker(caller: Authed = Depends(authed)) -> Authed:
        if not any(role in caller.principal.roles for role in allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires one of roles: {list(allowed)}",
            )
        return caller

    return _checker
