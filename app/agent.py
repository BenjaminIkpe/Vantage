"""Agent loop — a minimal single-agent tool-calling loop (ADR-001: not LangGraph).

Claude is given the tools + the caller's role; it decides which tools to call; we
execute them (RBAC enforced *inside* each tool); results go back until Claude answers.
RBAC is never in the prompt — the model may propose any tool, but the tool itself checks
the verified role (ADR-002 / 09-Security T2, T4). A `trace` of tool calls is returned
for observability.
"""
import json

from llm import MODEL, client
from auth import Principal
from tools import get_customer_profile

MAX_STEPS = 5

TOOLS = [
    {
        "name": "get_customer_profile",
        "description": (
            "Look up a customer by name (or partial name). Returns the profile when exactly "
            "one matches, a list of candidates when the name is ambiguous, or not_found when "
            "no customer matches. Always use this to resolve a customer before answering "
            "questions about them — never guess a customer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Customer name or partial name."}
            },
            "required": ["name"],
        },
    },
]


def _dispatch(name: str, args: dict, principal: Principal) -> dict:
    if name == "get_customer_profile":
        return get_customer_profile(args.get("name", ""), principal)
    return {"error": f"unknown tool: {name}"}


def run_agent(query: str, principal: Principal, max_steps: int = MAX_STEPS) -> dict:
    """Run the tool-calling loop for one query; return {"answer", "trace"}."""
    system = (
        "You are Vantage, an internal assistant for Acme Operations staff (Acme is a B2B "
        f"payments platform). The current user's role is: {', '.join(principal.roles) or 'unknown'}. "
        "Answer operational questions using the tools provided. Ground every answer in tool "
        "results — never invent customers or data. If a customer is not found, say so plainly; "
        "if the name is ambiguous, list the candidates and ask which one is meant."
    )
    messages: list[dict] = [{"role": "user", "content": query}]
    trace: list[dict] = []

    for _ in range(max_steps):
        resp = client().messages.create(
            model=MODEL, max_tokens=1024, system=system, tools=TOOLS, messages=messages
        )
        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    out = _dispatch(block.name, block.input, principal)
                    trace.append({"tool": block.name, "input": block.input, "result": out})
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(out, default=str),
                    })
            messages.append({"role": "user", "content": results})
            continue
        answer = "".join(b.text for b in resp.content if b.type == "text")
        return {"answer": answer, "trace": trace}

    return {"answer": "Stopped after the step limit without a final answer.", "trace": trace}
