"""Vantage API — auth-gated entry point. See Vantage-vault/04-Architecture.md."""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import redis as redis_lib
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import oidc
from auth import Authed, Principal, authed, verify_token
import json as _json

from agent import generate_title, run_agent, run_agent_streaming, suggest_followups
from security import verify_access_token
from session import (
    consume_oauth_state,
    delete_auth_session,
    delete_user_session,
    load_auth_session,
    load_history,
    load_tools,
    record_tools,
    record_user_session,
    resolve_session_id,
    save_turn,
    set_session_title,
    store_auth_session,
    store_oauth_state,
    user_owns_session,
    user_sessions,
)
from skills import draft_from_session, get_skill, load_skills, run_skill, save_skill

logger = logging.getLogger("vantage.api")

import telemetry  # OTel -> Phoenix tracing for the loop + the graph (guarded; safe to import)

# The proactive briefing graph (ADR-008) is optional and isolated behind a guarded import: if
# LangGraph isn't installed, the rest of the API (reactive loop, UI, auth) is wholly unaffected
# and only /briefing is disabled.
try:
    import briefing_graph
    _BRIEFING_AVAILABLE = True
except Exception:  # pragma: no cover - import-time guard
    briefing_graph = None
    _BRIEFING_AVAILABLE = False
    logger.exception("briefing graph unavailable (LangGraph not installed?) — /briefing disabled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Give the briefing graph a durable Redis (Stack) checkpointer for its HITL pause/resume;
    fall back to an in-process saver if the Redis path fails, so a checkpointer hiccup can never
    stop the api from starting (ADR-008). Redis, not Postgres: the api stays free of the
    system-of-record (ADR-003), and a paused run is ephemeral working memory (ADR-006)."""
    telemetry.setup_tracing()  # OTel -> Phoenix (+ LangSmith if keyed); before any model call
    cp_cm = None
    if _BRIEFING_AVAILABLE:
        try:
            try:
                from langgraph.checkpoint.redis.aio import AsyncRedisSaver
            except Exception:
                from langgraph.checkpoint.redis import AsyncRedisSaver
            cp_cm = AsyncRedisSaver.from_conn_string(os.getenv("REDIS_URL", "redis://redis:6379/0"))
            checkpointer = await cp_cm.__aenter__()
            await checkpointer.asetup()
            logger.info("briefing checkpointer: Redis (durable)")
        except Exception:
            logger.exception("Redis checkpointer unavailable; using in-process saver (non-durable)")
            if cp_cm is not None:
                try:
                    await cp_cm.__aexit__(None, None, None)
                except Exception:
                    pass
                cp_cm = None
            from langgraph.checkpoint.memory import MemorySaver
            checkpointer = MemorySaver()
        briefing_graph.init(checkpointer)
    try:
        yield
    finally:
        if cp_cm is not None:
            try:
                await cp_cm.__aexit__(None, None, None)
            except Exception:
                pass


app = FastAPI(title="Vantage API", lifespan=lifespan)

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

# The demo's three fixed personas (sales / support / admin). /auth/switch only ever targets
# one of these, so validating against this allow-list keeps an attacker-supplied `username`
# out of the 302 redirect (defence in depth — CodeQL py/url-redirection).
_SWITCHABLE_PERSONAS = {"priya.nair", "marcus.webb", "dana.okafor"}


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
def auth_login(request: Request, login_hint: str | None = None, prompt: str | None = None):
    """Start the OIDC Auth-Code + PKCE flow — redirect the browser to Keycloak's login.

    Optional `login_hint` pre-fills the username; `prompt=login` forces re-auth (used by
    the role-switcher in the UI to make 'switch to admin' a real identity swap, not a
    silent SSO bounce back as the same user).
    """
    code_verifier, code_challenge = oidc.gen_pkce()
    state = oidc.gen_state()
    redirect_uri = f"{_public_base(request)}/auth/callback"
    store_oauth_state(state, {"code_verifier": code_verifier, "redirect_uri": redirect_uri})
    return RedirectResponse(
        oidc.authorize_url(redirect_uri, state, code_challenge,
                           login_hint=login_hint, prompt=prompt),
        status_code=302,
    )


@app.get("/auth/switch")
async def auth_switch(username: str, vantage_sid: str | None = Cookie(default=None)):
    """Role-switch helper: clear the current BFF session and redirect to Keycloak with
    `prompt=login` + `login_hint=<persona>` so the user re-authenticates as a different
    persona (real JWT, real roles). The role-switcher menu in the UI hits this endpoint
    instead of flipping a client-side variable — that one was cosmetic and misled viewers
    into thinking they'd escalated privilege when they hadn't (security was fine, UX wasn't).
    """
    if username not in _SWITCHABLE_PERSONAS:
        raise HTTPException(status_code=400, detail="unknown persona")
    from urllib.parse import quote
    if vantage_sid:
        # Best-effort revoke the Keycloak refresh token + delete our session blob so the
        # old identity is fully gone before the new one is minted.
        sess = load_auth_session(vantage_sid)
        if sess and sess.get("refresh_token"):
            try:
                await oidc.revoke_session(sess["refresh_token"])
            except Exception:
                pass
        delete_auth_session(vantage_sid)
    target = f"/auth/login?prompt=login&login_hint={quote(username)}"
    resp = RedirectResponse(target, status_code=302)
    resp.delete_cookie(_COOKIE_NAME, path="/")
    return resp


@app.get("/auth/callback")
async def auth_callback(code: str, state: str):
    """Keycloak redirected the browser back with `code` + `state`. Exchange + set cookie."""
    stored = consume_oauth_state(state)
    if not stored:
        raise HTTPException(status_code=400, detail="invalid or expired OAuth state")
    try:
        tokens = await oidc.exchange_code(code, stored["redirect_uri"], stored["code_verifier"])
    except Exception:
        logger.exception("OIDC token exchange failed")
        raise HTTPException(status_code=502, detail="token exchange failed")

    access_token = tokens["access_token"]
    # Verify here so a malformed token surfaces immediately (and the same verifier the MCP
    # boundary uses — no trust-on-issuance).
    try:
        principal = verify_access_token(access_token)
    except Exception:
        logger.exception("received-token verification failed")
        raise HTTPException(status_code=401, detail="received-token verification failed")

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
    # Index this session under the calling user so it appears in the sidebar history.
    # The first turn sets the title (subsequent turns just bump last_updated).
    record_user_session(caller.principal.username, session_id, req.query)
    return {**result, "session_id": session_id}


@app.post("/ask/stream")
async def ask_stream(req: AskRequest, caller: Authed = Depends(authed)):
    """Streaming `/ask` via Server-Sent Events. Same agent loop, same persistence — but
    the UI sees tokens (and tool calls) as they happen. Event types:
      `session`     → `{session_id}` (sent first; UI adopts it for a new chat)
      `text`        → `{delta}` (token-level text)
      `tool_start`  → `{tool, input}`
      `tool_end`    → `{tool, status, ms}`
      `done`        → `{trace, elapsed_ms}` (final)
      `error`       → `{detail}` (caught exception mid-stream)

    The eval harness keeps using the non-streaming `/ask` (deterministic for assertions);
    this endpoint is the UI surface.
    """
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="query must be a non-empty string")
    session_id = resolve_session_id(req.session_id)
    history = load_history(session_id)

    async def event_stream():
        answer_parts: list[str] = []
        trace: list[dict] = []
        # Send the session id first so the UI can adopt it before any content arrives.
        yield f"event: session\ndata: {_json.dumps({'session_id': session_id})}\n\n"
        try:
            async for event in run_agent_streaming(
                req.query, token=caller.token, principal=caller.principal, history=history,
            ):
                if event["type"] == "text":
                    answer_parts.append(event["delta"])
                if event["type"] == "done":
                    trace = event.get("trace", [])
                yield f"event: {event['type']}\ndata: {_json.dumps(event, default=str)}\n\n"
        except Exception:
            logger.exception("error in /ask/stream (session=%s)", session_id)
            yield f"event: error\ndata: {_json.dumps({'detail': 'internal error — please try again'})}\n\n"
        finally:
            # Persist regardless of whether the stream finished cleanly — partial answers
            # are still real conversation context.
            answer = "".join(answer_parts)
            if answer:
                save_turn(session_id, req.query, answer)
                record_tools(session_id, [t["tool"] for t in trace])
                record_user_session(caller.principal.username, session_id, req.query)

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


# --- Assistive endpoints (suggested follow-ups) -----------------------------------------


class FollowupsRequest(BaseModel):
    query: str
    answer: str


@app.post("/followups")
async def followups(req: FollowupsRequest, caller: Authed = Depends(authed)):
    """Up to 3 short, ready-to-send next queries for the exchange the user just saw, tailored to
    the caller's role (never an action the role can't perform). Returns {"suggestions": []} on
    any failure — never 500 — so the UI degrades silently."""
    try:
        suggestions = await suggest_followups(req.query, req.answer, caller.principal)
    except Exception:
        logger.exception("followups generation failed")
        suggestions = []
    return {"suggestions": suggestions}


# --- Per-user session history (chat-history sidebar) ------------------------------------


@app.get("/sessions")
def list_sessions(caller: Authed = Depends(authed)):
    """The current user's chat history for the sidebar. Newest first."""
    return {"sessions": user_sessions(caller.principal.username)}


@app.get("/sessions/{session_id}")
def get_session(session_id: str, caller: Authed = Depends(authed)):
    """Return one session's full message history for the chat to replay it. 404 if the caller
    doesn't own this session (prevents cross-user history reads — defence in depth even though
    session ids are 32-char unguessable already)."""
    if not user_owns_session(caller.principal.username, session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return {
        "session_id": session_id,
        "messages": load_history(session_id),
        "tools_used": load_tools(session_id),
    }


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str, caller: Authed = Depends(authed)):
    """Remove a session from the user's sidebar + delete its data. Idempotent."""
    if not delete_user_session(caller.principal.username, session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return {"status": "deleted", "session_id": session_id}


class TitleRequest(BaseModel):
    query: str
    answer: str


@app.post("/sessions/{session_id}/title")
async def set_title(session_id: str, req: TitleRequest, caller: Authed = Depends(authed)):
    """Generate and persist a concise (<= 6 word) title from the session's first exchange. 404 if
    the caller doesn't own the session. On LLM failure, falls back to the truncated first query.
    The title is stored on the session record (Redis), so GET /sessions reflects it immediately."""
    if not user_owns_session(caller.principal.username, session_id):
        raise HTTPException(status_code=404, detail="session not found")
    title = await generate_title(req.query, req.answer)  # never raises; returns a fallback
    set_session_title(session_id, title)
    return {"title": title}


@app.get("/skills")
def list_skills(caller: Authed = Depends(authed)):
    """List the available reusable Skills (any authenticated role). See app/skills.py."""
    return {"skills": [
        {"name": s.name, "description": s.description, "parameters": s.parameters,
         "allowed_tools": s.allowed_tools}
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
async def draft_skill(req: DraftFromSessionRequest, caller: Authed = Depends(authed)):
    """Turn a finished session into a reusable skill DRAFT (Flow 1). Not saved — review it, then
    POST /skills to keep it. Any authenticated role may author (a skill can't exceed its caller's
    permissions; RBAC stays in the tools). The caller must own the session being drafted from."""
    if not user_owns_session(caller.principal.username, req.session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return await draft_from_session(load_history(req.session_id), load_tools(req.session_id), req.name)


class SaveSkillRequest(BaseModel):
    name: str
    instructions: str
    description: str = ""
    parameters: list[dict] = []
    allowed_tools: list[str] = []


@app.post("/skills")
def create_skill(req: SaveSkillRequest, caller: Authed = Depends(authed)):
    """Persist an authored skill (the reviewed draft). Returns the saved skill."""
    try:
        skill = save_skill(req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "saved", "name": skill.name, "allowed_tools": skill.allowed_tools}


# --- proactive admin briefing (ADR-008; LangGraph fan-out + HITL approval) ---------------


class ApproveRequest(BaseModel):
    approved_ids: list[int] = []  # draft_ids the admin approved; the rest are skipped


def _require_admin(caller: Authed) -> None:
    """403 unless the caller is an admin. Defence in depth — the briefing's MCP tools are
    admin-only at the boundary too, so this just fails fast with a clear message."""
    if "admin" not in caller.principal.roles:
        raise HTTPException(status_code=403, detail="briefing is admin-only")


@app.get("/briefing")
async def briefing(caller: Authed = Depends(authed)):
    """Run the proactive fleet briefing (admin only): rank high-risk accounts, compose the
    escalation-summary skill across them, detect cross-customer patterns, and DRAFT next actions.
    The run pauses at a human-in-the-loop gate (`pending_approval: true`); POST the approved
    draft_ids to /briefing/{id}/approve to write them. RBAC stays enforced at every tool — this
    endpoint only gates the entry point.
    """
    if not _BRIEFING_AVAILABLE:
        raise HTTPException(status_code=503, detail="briefing unavailable (LangGraph not installed)")
    _require_admin(caller)
    briefing_id = oidc.gen_sid()
    try:
        return await briefing_graph.start_briefing(briefing_id, caller.principal, caller.token)
    except Exception as exc:
        logger.exception("briefing failed")
        raise HTTPException(status_code=502, detail=f"briefing error: {exc}")


@app.post("/briefing/{briefing_id}/approve")
async def briefing_approve(briefing_id: str, req: ApproveRequest, caller: Authed = Depends(authed)):
    """Approve drafted next actions from a paused briefing (admin only). Resumes the graph and
    writes each approved draft via create_next_action with THIS admin's token — the approval IS
    the authorisation, enforced at the MCP boundary. 404 if the briefing id is unknown/expired."""
    if not _BRIEFING_AVAILABLE:
        raise HTTPException(status_code=503, detail="briefing unavailable (LangGraph not installed)")
    _require_admin(caller)
    try:
        result = await briefing_graph.approve_briefing(
            briefing_id, caller.principal, caller.token, req.approved_ids)
    except Exception as exc:
        logger.exception("briefing approve failed")
        raise HTTPException(status_code=502, detail=f"approve error: {exc}")
    if result is None:
        raise HTTPException(status_code=404, detail="briefing not found or expired")
    return result
