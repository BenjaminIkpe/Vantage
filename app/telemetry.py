"""Observability tracing — OpenTelemetry -> Arize Phoenix (self-hosted, no egress), with
LangSmith wired as an opt-in second backend. This is the brief's bonus tracing (03-Scope
Could; ADR-008).

Both execution shapes are traced from one place: OpenInference auto-instruments the OpenAI
SDK (every model call in app/llm.py — so the reactive loop *and* the briefing's draft/skill
calls) and LangChain/LangGraph (the briefing graph's nodes). Spans export over OTLP to the
Phoenix service inside the compose stack — nothing leaves the host. LangSmith is emitted to
automatically by LangGraph/LangChain, but only when LANGSMITH_API_KEY is set (it's a hosted
service); Phoenix needs no key and is the default-on, enterprise-safe backend.

Guarded: any failure here is logged and swallowed. Tracing must never break the app.
"""
import logging
import os

logger = logging.getLogger("vantage.telemetry")
_initialised = False


def setup_tracing() -> None:
    """Idempotently wire OTel -> Phoenix + the OpenInference instrumentors. Call once at
    startup, before the first model/graph call. No-op if TRACING_ENABLED is not 'true'."""
    global _initialised
    if _initialised:
        return
    _initialised = True

    if os.getenv("TRACING_ENABLED", "true").lower() != "true":
        logger.info("tracing disabled (TRACING_ENABLED != true)")
        return

    try:
        from phoenix.otel import register

        endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006").rstrip("/")
        register(
            project_name=os.getenv("PHOENIX_PROJECT_NAME", "vantage"),
            endpoint=f"{endpoint}/v1/traces",
            auto_instrument=True,  # enable installed OpenInference instrumentors (openai + langchain)
            batch=True,
        )
        langsmith = "on" if os.getenv("LANGSMITH_API_KEY") else "off (no LANGSMITH_API_KEY)"
        logger.info("tracing -> Phoenix at %s (OpenInference: openai + langchain); LangSmith %s",
                    endpoint, langsmith)
    except Exception:
        logger.exception("tracing setup failed; continuing without tracing")
