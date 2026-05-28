"""Thin LLM adapter — model-agnostic via the OpenAI Python SDK + a swappable `base_url`.

The OpenAI Chat-Completions API shape is the de-facto multi-provider lingua franca in 2025-26:
Anthropic, Bedrock, OpenRouter, Together, Groq, Gemini all expose OpenAI-compatible endpoints.
Swapping providers is **one env var of work** — no code change. Concrete examples:

    # Anthropic (default)
    LLM_BASE_URL=https://api.anthropic.com/v1/
    LLM_MODEL=claude-sonnet-4-6
    LLM_API_KEY=sk-ant-...        # or set ANTHROPIC_API_KEY (back-compat fallback)

    # OpenAI
    LLM_BASE_URL=https://api.openai.com/v1/
    LLM_MODEL=gpt-4o
    LLM_API_KEY=sk-...

    # OpenRouter (all providers behind one endpoint)
    LLM_BASE_URL=https://openrouter.ai/api/v1/
    LLM_MODEL=anthropic/claude-sonnet-4-6
    LLM_API_KEY=...

Considered and rejected: **LiteLLM** (a normalization library) — March 2026 PyPI supply-chain
compromise on versions 1.82.7 / 1.82.8 exfiltrated LLM credentials, plus documented
streaming + tool-calling bugs across providers and ~40ms per-call overhead. The OpenAI-SDK +
base_url pattern is lighter, well-tested, and what real multi-provider products ship.

Gateway pattern (Portkey, Vercel AI Gateway, Bifrost) is the right answer at governance/
observability scale — deferred until volume demands it (out of scope for a single-host demo).

Trade-off worth knowing: provider-specific extras (Anthropic's prompt caching, extended
thinking; OpenAI's responses API) live on each provider's native API, not in the compat layer.
Vantage uses none of these today; if we ever need one, reach for that provider's native SDK at
this single file boundary (ADR-001).

The async client is created **lazily** — importing this module needs no key (CI imports it).
"""
import os

from openai import AsyncOpenAI

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.anthropic.com/v1/")
MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

# Accept the new LLM_API_KEY env var first; fall back to ANTHROPIC_API_KEY so existing setups
# (and the dev .env) keep working unchanged.
_API_KEY_ENV = os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY")

_client: AsyncOpenAI | None = None


def aclient() -> AsyncOpenAI:
    """Return a cached async OpenAI-compatible client pointed at LLM_BASE_URL."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(base_url=LLM_BASE_URL, api_key=_API_KEY_ENV)
    return _client
