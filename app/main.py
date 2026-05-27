"""Vantage API — auth-gated entry point. See Vantage-vault/04-Architecture.md."""
import os

import httpx
import redis as redis_lib
from fastapi import Depends, FastAPI

from auth import Principal, verify_token
from tools import get_customer_profile

app = FastAPI(title="Vantage API")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")
REALM = os.getenv("KEYCLOAK_REALM", "vantage")


@app.get("/health")
def health():
    """Liveness: the process is up."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness: dependencies reachable (Redis + Keycloak)."""
    checks = {}
    try:
        redis_lib.from_url(REDIS_URL, socket_connect_timeout=2).ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"
    try:
        resp = httpx.get(f"{KEYCLOAK_URL}/realms/{REALM}", timeout=3)
        checks["keycloak"] = "ok" if resp.status_code == 200 else f"http {resp.status_code}"
    except Exception as exc:
        checks["keycloak"] = f"error: {exc}"
    healthy = all(v == "ok" for v in checks.values())
    return {"status": "ok" if healthy else "degraded", "checks": checks}


@app.get("/whoami")
def whoami(principal: Principal = Depends(verify_token)):
    """Proves end-to-end JWT verification + role extraction (T1/T2). Needs a valid token."""
    return {"username": principal.username, "roles": principal.roles}


@app.get("/customers")
def customer_lookup(name: str, principal: Principal = Depends(verify_token)):
    """Look up a customer by name — any authenticated role (read). Proves tool + DB + RBAC.

    Direct endpoint for now; the agent loop will call the same tool in the next slice.
    """
    return get_customer_profile(name, principal)
