"""Thin LLM adapter — the single place the model provider/model is chosen (ADR-001).

Swapping provider is contained here (plus the loop's response-block handling in
agent.py). The Anthropic client is created **lazily**, so importing the app needs no
API key — CI can import the module without a key; the key is only read at request time.
"""
import os

from anthropic import Anthropic

MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

_client: Anthropic | None = None


def client() -> Anthropic:
    """Return a cached Anthropic client (reads ANTHROPIC_API_KEY on first call)."""
    global _client
    if _client is None:
        _client = Anthropic()
    return _client
