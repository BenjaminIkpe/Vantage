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
TTL_SECONDS = int(os.getenv("SESSION_TTL", "3600"))        # ~1h; refreshed each turn
MAX_MESSAGES = int(os.getenv("SESSION_MAX_MESSAGES", "20"))  # rolling cap (user+assistant)

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
