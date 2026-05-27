"""Agent loop — a minimal single-agent tool-calling loop (ADR-001), now an MCP client.

Claude is given the tools *discovered from the MCP server* (ADR-003) plus the caller's role
for context; it decides which tools to call; we forward each call to the MCP server over
Streamable HTTP **with the user's bearer token**, so the server re-verifies it and enforces
RBAC inside the tool (ADR-002 / 09-Security T2,T4). RBAC is never in the prompt — the model
may propose any tool, but the tool (behind MCP) disposes. A `trace` of tool calls is returned
for observability. One MCP session is opened per request and torn down at the end.
"""
import json
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from llm import MODEL, aclient
from security import Principal

MAX_STEPS = 5
MCP_URL = os.getenv("MCP_URL", "http://mcp:8001/mcp")


def _system_prompt(principal: Principal) -> str:
    return (
        "You are Vantage, an internal assistant for Acme Operations staff (Acme is a B2B "
        f"payments platform). The current user's role is: {', '.join(principal.roles) or 'unknown'}. "
        "Answer operational questions using the tools provided. Ground every answer in tool "
        "results — never invent customers or data. If a customer is not found, say so plainly; "
        "if the name is ambiguous, list the candidates and ask which one is meant. You may take "
        "several steps: resolve the customer, list their open issues, then read an issue's "
        "history when the question needs the detail behind it. When the user asks you to record "
        "something (update an issue, set a next action), attempt the appropriate tool — do not "
        "decide yourself whether their role permits it. Permissions are enforced by the tools; "
        "if a tool returns a denial, relay it plainly and do not retry."
    )


def _payload(result) -> dict:
    """Extract a tool's JSON payload from an MCP CallToolResult (structured first)."""
    if result.isError:
        return {"error": result.content[0].text if result.content else "tool error"}
    if result.structuredContent is not None:
        return result.structuredContent
    if result.content:
        return json.loads(result.content[0].text)
    return {}


async def run_agent(query: str, token: str, principal: Principal,
                    history: list[dict] | None = None, system: str | None = None,
                    allowed_tools: list[str] | None = None, max_steps: int = MAX_STEPS) -> dict:
    """Run the tool-calling loop for one query against the MCP server; return {"answer","trace"}.

    `history` is the prior conversation (Anthropic messages) for multi-turn context (story X1).
    `system` overrides the default prompt (used by the Skill runner to inject a skill's
    instructions). `allowed_tools` restricts the discovered tools to a named subset (a skill's
    whitelist — least privilege on top of RBAC). Defaults preserve the plain /ask behaviour.
    """
    system_prompt = system or _system_prompt(principal)
    trace: list[dict] = []
    async with streamablehttp_client(MCP_URL, headers={"Authorization": f"Bearer {token}"}) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # Tool list + schemas come from MCP discovery — not hard-coded here (ADR-003).
            tools = [
                {"name": t.name, "description": t.description or "", "input_schema": t.inputSchema}
                for t in (await session.list_tools()).tools
                if allowed_tools is None or t.name in allowed_tools
            ]
            messages: list[dict] = [*(history or []), {"role": "user", "content": query}]

            for _ in range(max_steps):
                resp = await aclient().messages.create(
                    model=MODEL,
                    max_tokens=1024,
                    system=system_prompt,
                    tools=tools,
                    messages=messages,
                )
                if resp.stop_reason == "tool_use":
                    messages.append({"role": "assistant", "content": resp.content})
                    results = []
                    for block in resp.content:
                        if block.type == "tool_use":
                            out = _payload(await session.call_tool(block.name, block.input))
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
