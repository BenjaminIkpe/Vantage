"""Redis-backed multi-turn session memory (story X1; ADR-006).

Ephemeral *working* memory — the conversation so far — kept in Redis, never the system of
record (that's Postgres). Keyed `session:{id}` with a rolling cap and a TTL refreshed on each
turn, so abandoned sessions self-clean. We store the conversation as plain user/assistant
**text** turns (not the within-request tool_use/tool_result blocks): the final answers carry
the context a follow-up needs ("now summarise the second one"), and text is trivially
serialisable. A Redis outage degrades gracefully — we lose context for the turn, never data.
"""
import json
import os
import uuid

import redis as redis_lib

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
# Default 7 days so the sidebar holds a useful history (the UI's Today/Yesterday/Last-7-days
# grouping). Per-turn refresh keeps active sessions alive indefinitely.
TTL_SECONDS = int(os.getenv("SESSION_TTL", "604800"))
MAX_MESSAGES = int(os.getenv("SESSION_MAX_MESSAGES", "20"))  # rolling cap (user+assistant)
TITLE_MAX = 80                                               # chars; sidebar title truncation

_client: redis_lib.Redis | None = None


def _redis() -> redis_lib.Redis:
    global _client
    if _client is None:
        _client = redis_lib.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
    return _client


def new_session_id() -> str:
    return uuid.uuid4().hex


def resolve_session_id(provided: str | None) -> str:
    """Use a client-provided id (length-capped to keep the Redis key sane) or mint a new one."""
    if provided and provided.strip():
        return provided.strip()[:64]
    return new_session_id()


def load_history(session_id: str) -> list[dict]:
    """Prior conversation turns as Anthropic messages ([{role, content}]); [] if none/unavailable."""
    try:
        raw = _redis().get(f"session:{session_id}")
        return json.loads(raw) if raw else []
    except Exception:
        return []  # Redis down → no memory this turn, but the request still works


def save_turn(session_id: str, user_query: str, assistant_answer: str) -> None:
    """Append this turn (user + assistant) to the rolling history and refresh the TTL."""
    try:
        history = load_history(session_id)
        history.append({"role": "user", "content": user_query})
        history.append({"role": "assistant", "content": assistant_answer})
        history = history[-MAX_MESSAGES:]
        _redis().set(f"session:{session_id}", json.dumps(history), ex=TTL_SECONDS)
    except Exception:
        pass  # best-effort; losing session memory must never fail the request


def record_tools(session_id: str, tool_names: list[str]) -> None:
    """Accumulate the set of tools used this session — the basis for a drafted skill's
    allowed_tools (Flow 1: a skill does what you just did, with the tools you just used)."""
    if not tool_names:
        return
    try:
        key = f"session:{session_id}:tools"
        _redis().sadd(key, *tool_names)
        _redis().expire(key, TTL_SECONDS)
    except Exception:
        pass


def load_tools(session_id: str) -> list[str]:
    """The distinct tools used in this session, sorted; [] if none/unavailable."""
    try:
        return sorted(_redis().smembers(f"session:{session_id}:tools"))
    except Exception:
        return []


# --- OIDC auth-session storage (BFF pattern; see app/oidc.py) -----------------------------
# `oauth_state:{state}` holds the PKCE code_verifier + redirect_uri between /auth/login and
# /auth/callback (~5 min TTL — covers a slow login). `auth_session:{sid}` holds the
# verified access token + identity, keyed by the httpOnly cookie value (TTL = token expiry).
# The access token never reaches the browser.

OAUTH_STATE_TTL = 300        # 5 min
AUTH_SESSION_TTL = 3600      # 1 hour default; overridden by token expires_in


def store_oauth_state(state: str, data: dict, ttl: int = OAUTH_STATE_TTL) -> None:
    try:
        _redis().set(f"oauth_state:{state}", json.dumps(data), ex=ttl)
    except Exception:
        pass


def consume_oauth_state(state: str) -> dict | None:
    """Read-and-delete the stored PKCE state (one-shot; prevents replay)."""
    try:
        key = f"oauth_state:{state}"
        raw = _redis().get(key)
        if raw is None:
            return None
        _redis().delete(key)
        return json.loads(raw)
    except Exception:
        return None


def store_auth_session(sid: str, data: dict, ttl: int = AUTH_SESSION_TTL) -> None:
    try:
        _redis().set(f"auth_session:{sid}", json.dumps(data), ex=ttl)
    except Exception:
        pass


def load_auth_session(sid: str) -> dict | None:
    try:
        raw = _redis().get(f"auth_session:{sid}")
        return json.loads(raw) if raw else None
    except Exception:
        return None


def delete_auth_session(sid: str) -> None:
    try:
        _redis().delete(f"auth_session:{sid}")
    except Exception:
        pass


# --- Per-user session listing for the chat-history sidebar ------------------------------
# `user_sessions:{username}` is a sorted set: members are session ids, scores are the
# most-recent-turn timestamps so we can render Today / Yesterday / Last 7 days by reading
# the zset in reverse. The session's title (= the first user message, truncated) lives
# at `session:{id}:title`. Both follow the same TTL as the conversation itself.


def _now_ts() -> int:
    import time
    return int(time.time())


def record_user_session(username: str, session_id: str, first_user_text: str | None = None) -> None:
    """Index this session under the user (called from /ask on every turn). Sets the title
    on the first turn only (subsequent calls leave it alone — title = original prompt)."""
    if not username or not session_id:
        return
    try:
        r = _redis()
        zkey = f"user_sessions:{username}"
        tkey = f"session:{session_id}:title"
        ts = _now_ts()
        r.zadd(zkey, {session_id: ts})
        r.expire(zkey, TTL_SECONDS)
        if first_user_text and not r.exists(tkey):
            r.set(tkey, first_user_text[:TITLE_MAX], ex=TTL_SECONDS)
        elif r.exists(tkey):
            r.expire(tkey, TTL_SECONDS)
    except Exception:
        pass


def set_session_title(session_id: str, title: str) -> None:
    """Overwrite the stored title for a session (the LLM-generated title from the title
    endpoint). Persists to the same `session:{id}:title` key that `user_sessions` reads, so
    GET /sessions reflects it immediately and it survives reload. Best-effort — a Redis outage
    must never fail the request."""
    if not session_id or not title or not title.strip():
        return
    try:
        _redis().set(f"session:{session_id}:title", title.strip()[:TITLE_MAX], ex=TTL_SECONDS)
    except Exception:
        pass


def user_sessions(username: str) -> list[dict]:
    """List the user's sessions newest-first as `[{id, title, last_updated}]`."""
    if not username:
        return []
    try:
        r = _redis()
        # zrevrange + WITHSCORES → [(id, score), ...]; redis-py with decode_responses=True
        # returns strings + floats here.
        rows = r.zrange(f"user_sessions:{username}", 0, -1, desc=True, withscores=True)
        out = []
        for sid, score in rows:
            title = r.get(f"session:{sid}:title") or "(untitled)"
            out.append({"id": sid, "title": title, "last_updated": int(score)})
        return out
    except Exception:
        return []


def user_owns_session(username: str, session_id: str) -> bool:
    """Whether this session id is in the named user's index (access control for /sessions/{id})."""
    if not username or not session_id:
        return False
    try:
        return _redis().zscore(f"user_sessions:{username}", session_id) is not None
    except Exception:
        return False


def delete_user_session(username: str, session_id: str) -> bool:
    """Remove a session from the user's index and delete its data. Returns True if owned."""
    if not user_owns_session(username, session_id):
        return False
    try:
        r = _redis()
        r.zrem(f"user_sessions:{username}", session_id)
        r.delete(f"session:{session_id}", f"session:{session_id}:tools", f"session:{session_id}:title")
        return True
    except Exception:
        return False
