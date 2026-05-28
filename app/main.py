"""Vantage API — auth-gated entry point. See Vantage-vault/04-Architecture.md."""
import os
from pathlib import Path

import httpx
import redis as redis_lib
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import oidc
from auth import Authed, Principal, authed, verify_token
from agent import run_agent
from security import verify_access_token
from session import (
    consume_oauth_state,
    delete_auth_session,
    load_auth_session,
    load_history,
    load_tools,
    record_tools,
    resolve_session_id,
    save_turn,
    store_auth_session,
    store_oauth_state,
)
from skills import draft_from_session, get_skill, load_skills, run_skill, save_skill

app = FastAPI(title="Vantage API")

# Static chat UI — lifted from the Claude Design handoff (see Vantage-vault/04-Architecture.md
# § "The UI"). Mocked routing in web/app.js will be replaced by real backend calls (auth-code
# OIDC, streaming /ask/stream, /sessions, /skills/*) in the next PR.
_WEB_DIR = Path(__file__).parent / "web"
if _WEB_DIR.is_dir():
    app.mount("/web", StaticFiles(directory=_WEB_DIR), name="web")

    @app.get("/")
    def root():
        return FileResponse(_WEB_DIR / "index.html")

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
def whoami(caller: Authed = Depends(authed)):
    """The current caller's identity + roles. Accepts either a Bearer header (programmatic
    clients) or the `vantage_sid` session cookie (browser UI). Proves JWT verification +
    role extraction (T1/T2)."""
    return {"username": caller.principal.username, "roles": caller.principal.roles}


# --- OIDC Authorization Code + PKCE flow (BFF; ADR-002 / 09-Security hardening) ---------
# Browser hits /auth/login → redirect to Keycloak. Keycloak redirects back to /auth/callback
# with `code` + `state`. We exchange the code for tokens server-side, store them in Redis,
# set an httpOnly cookie naming the server-side session. The access token never reaches
# the browser. /auth/logout clears both ends. /auth/whoami is the UI's bootstrap call.

_COOKIE_NAME = "vantage_sid"
_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
_COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")


def _public_base(request: Request) -> str:
    """The public-facing API URL the browser sees (used to build the redirect_uri).

    Respects `X-Forwarded-Proto` / `X-Forwarded-Host` so it works behind Codespaces' HTTPS
    forward and any reverse proxy.
    """
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "localhost:8000")
    return f"{proto}://{host}"


@app.get("/auth/login")
def auth_login(request: Request):
    """Start the OIDC Auth-Code + PKCE flow — redirect the browser to Keycloak's login."""
    code_verifier, code_challenge = oidc.gen_pkce()
    state = oidc.gen_state()
    redirect_uri = f"{_public_base(request)}/auth/callback"
    store_oauth_state(state, {"code_verifier": code_verifier, "redirect_uri": redirect_uri})
    return RedirectResponse(oidc.authorize_url(redirect_uri, state, code_challenge), status_code=302)


@app.get("/auth/callback")
async def auth_callback(code: str, state: str):
    """Keycloak redirected the browser back with `code` + `state`. Exchange + set cookie."""
    stored = consume_oauth_state(state)
    if not stored:
        raise HTTPException(status_code=400, detail="invalid or expired OAuth state")
    try:
        tokens = await oidc.exchange_code(code, stored["redirect_uri"], stored["code_verifier"])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"token exchange failed: {exc}")

    access_token = tokens["access_token"]
    # Verify here so a malformed token surfaces immediately (and the same verifier the MCP
    # boundary uses — no trust-on-issuance).
    try:
        principal = verify_access_token(access_token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"received-token verify failed: {exc}")

    sid = oidc.gen_sid()
    ttl = int(tokens.get("expires_in", 3600))
    store_auth_session(sid, {
        "access_token": access_token,
        "refresh_token": tokens.get("refresh_token", ""),
        "username": principal.username,
        "roles": principal.roles,
        "subject": principal.subject,
    }, ttl=ttl)

    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie(
        _COOKIE_NAME, sid,
        httponly=True, secure=_COOKIE_SECURE, samesite=_COOKIE_SAMESITE, path="/", max_age=ttl,
    )
    return resp


@app.get("/auth/logout")
async def auth_logout(vantage_sid: str | None = Cookie(default=None)):
    """Clear server-side session + cookie. Best-effort Keycloak refresh-token revoke."""
    if vantage_sid:
        sess = load_auth_session(vantage_sid)
        if sess and sess.get("refresh_token"):
            await oidc.revoke_session(sess["refresh_token"])
        delete_auth_session(vantage_sid)
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie(_COOKIE_NAME, path="/")
    return resp


@app.get("/auth/whoami")
def auth_whoami(caller: Authed = Depends(authed)):
    """Same shape as /whoami; explicit auth-namespace endpoint the UI calls on init."""
    return {"username": caller.principal.username, "roles": caller.principal.roles}


class AskRequest(BaseModel):
    query: str
    session_id: str | None = None  # omit to start a session; resend the returned id to continue


@app.post("/ask")
async def ask(req: AskRequest, caller: Authed = Depends(authed)):
    """Ask the agent. It reasons over the MCP tools (RBAC-gated) and answers from the data.

    The verified token is forwarded to the MCP server, which re-verifies it and enforces RBAC
    inside each tool (ADR-002/003). The API itself holds no database access. Conversation
    context for the session is loaded from / saved to Redis (story X1), so follow-ups resolve.
    """
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="query must be a non-empty string")
    session_id = resolve_session_id(req.session_id)
    try:
        result = await run_agent(
            req.query, token=caller.token, principal=caller.principal,
            history=load_history(session_id),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"agent error: {exc}")
    save_turn(session_id, req.query, result["answer"])
    record_tools(session_id, [t["tool"] for t in result.get("trace", [])])
    return {**result, "session_id": session_id}


@app.get("/skills")
def list_skills(principal: Principal = Depends(verify_token)):
    """List the available reusable Skills (any authenticated role). See app/skills.py."""
    return {"skills": [
        {"name": s.name, "description": s.description, "parameters": s.parameters}
        for s in load_skills().values()
    ]}


class SkillRunRequest(BaseModel):
    params: dict = {}


@app.post("/skills/{name}/run")
async def run_named_skill(name: str, req: SkillRunRequest, caller: Authed = Depends(authed)):
    """Invoke a Skill by name. It runs the agent loop restricted to the skill's tools, with the
    caller's token forwarded (RBAC still enforced per tool at the MCP boundary)."""
    skill = get_skill(name)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"unknown skill: {name}")
    try:
        return await run_skill(skill, req.params, token=caller.token, principal=caller.principal)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"skill error: {exc}")


class DraftFromSessionRequest(BaseModel):
    session_id: str
    name: str | None = None


@app.post("/skills/draft-from-session")
async def draft_skill(req: DraftFromSessionRequest, principal: Principal = Depends(verify_token)):
    """Turn a finished session into a reusable skill DRAFT (Flow 1). Not saved — review it, then
    POST /skills to keep it. Any authenticated role may author (a skill can't exceed its caller's
    permissions; RBAC stays in the tools)."""
    return await draft_from_session(load_history(req.session_id), load_tools(req.session_id), req.name)


class SaveSkillRequest(BaseModel):
    name: str
    instructions: str
    description: str = ""
    parameters: list[dict] = []
    allowed_tools: list[str] = []


@app.post("/skills")
def create_skill(req: SaveSkillRequest, principal: Principal = Depends(verify_token)):
    """Persist an authored skill (the reviewed draft). Returns the saved skill."""
    try:
        skill = save_skill(req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "saved", "name": skill.name, "allowed_tools": skill.allowed_tools}
