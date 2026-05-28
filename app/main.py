"""Vantage API — auth-gated entry point. See Vantage-vault/04-Architecture.md."""
import os

import httpx
import redis as redis_lib
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from auth import Authed, Principal, authed, verify_token
from agent import run_agent
from session import load_history, load_tools, record_tools, resolve_session_id, save_turn
from skills import draft_from_session, get_skill, load_skills, run_skill, save_skill

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
    """Proves JWT verification + role extraction (T1/T2)."""
    return {"username": principal.username, "roles": principal.roles}


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
