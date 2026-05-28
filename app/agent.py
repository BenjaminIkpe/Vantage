"""Agent loop — a minimal single-agent tool-calling loop (ADR-001), an MCP client over
Streamable HTTP and an OpenAI-compatible LLM client (any provider via base_url, ADR-001).

Claude (or any swapped-in model) is given the tools **discovered from the MCP server**
(ADR-003) plus the caller's role for context; it decides which tools to call; we forward each
call to the MCP server **with the user's bearer token**, so the server re-verifies it and
enforces RBAC inside the tool (ADR-002 / 09-Security T2,T4). RBAC is never in the prompt —
the model may propose any tool, but the tool (behind MCP) disposes. A `trace` of tool calls
(with per-tool ms) + total `elapsed_ms` is returned for observability. One MCP session per
request; torn down at the end.

Message shapes follow OpenAI Chat-Completions (the 2025-26 multi-provider lingua franca):
the system prompt is the first `system` message; tool calls come back as `tool_calls` on
the assistant turn; tool results are appended as `role: "tool"` messages keyed by tool_call_id.
"""
import json
import os
import time

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
        "results — never invent customers or data. **Do not use emojis** anywhere in your "
        "responses (no 🔴 🟢 🟡 📋 ⚠️ ✅ ❌ etc.). Write plain text: 'Critical' not '🔴 Critical', "
        "'Resolved' not '✅ Resolved'. The UI styles status keywords with proper icons; emoji "
        "output looks unprofessional. If a customer is not found, say so plainly; "
        "if the name is ambiguous, list the candidates and ask which one is meant. You may take "
        "several steps: resolve the customer, list their open issues, then read an issue's "
        "history when the question needs the detail behind it. When the user wants to browse or "
        "explore (no specific customer or issue id in mind — e.g. 'who are our customers', "
        "'show me critical issues', 'what's overdue'), use the list_* tools (list_customers, "
        "list_issues, list_next_actions) with filters and pagination. When the user asks you "
        "to record something (update an issue, set a next action), attempt the appropriate "
        "tool — do not decide yourself whether their role permits it. Permissions are enforced "
        "by the tools; if a tool returns a denial, relay it plainly and do not retry."
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


def _mcp_tool_to_openai(t) -> dict:
    """Convert an MCP-discovered tool to the OpenAI function-tool shape."""
    return {
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description or "",
            "parameters": t.inputSchema,
        },
    }


async def run_agent(query: str, token: str, principal: Principal,
                    history: list[dict] | None = None, system: str | None = None,
                    allowed_tools: list[str] | None = None, max_steps: int = MAX_STEPS) -> dict:
    """Run the tool-calling loop for one query against the MCP server; return
    {"answer", "trace", "elapsed_ms"}.

    `history` is the prior conversation (OpenAI messages) for multi-turn context (story X1).
    `system` overrides the default prompt (used by the Skill runner to inject a skill's
    instructions). `allowed_tools` restricts the discovered tools to a named subset (a skill's
    whitelist — least privilege on top of RBAC). Defaults preserve plain /ask behaviour.
    """
    system_prompt = system or _system_prompt(principal)
    trace: list[dict] = []
    started = time.perf_counter()

    def _elapsed_ms() -> int:
        return round((time.perf_counter() - started) * 1000)

    async with streamablehttp_client(MCP_URL, headers={"Authorization": f"Bearer {token}"}) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # Tool list + schemas come from MCP discovery — not hard-coded here (ADR-003).
            mcp_tools = (await session.list_tools()).tools
            tools = [
                _mcp_tool_to_openai(t) for t in mcp_tools
                if allowed_tools is None or t.name in allowed_tools
            ]
            messages: list[dict] = [
                {"role": "system", "content": system_prompt},
                *(history or []),
                {"role": "user", "content": query},
            ]

            for _ in range(max_steps):
                resp = await aclient().chat.completions.create(
                    model=MODEL,
                    max_tokens=1024,
                    tools=tools,
                    messages=messages,
                )
                msg = resp.choices[0].message
                if msg.tool_calls:
                    # Append the assistant turn (with tool_calls) verbatim so the model sees
                    # its own decision on the next iteration.
                    messages.append({
                        "role": "assistant",
                        "content": msg.content,
                        "tool_calls": [
                            {"id": tc.id, "type": "function",
                             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                            for tc in msg.tool_calls
                        ],
                    })
                    # Execute each tool call; append a `role: "tool"` result keyed by tool_call_id.
                    for tc in msg.tool_calls:
                        t0 = time.perf_counter()
                        try:
                            args = json.loads(tc.function.arguments or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        out = _payload(await session.call_tool(tc.function.name, args))
                        trace.append({
                            "tool": tc.function.name, "input": args, "result": out,
                            "ms": round((time.perf_counter() - t0) * 1000),
                        })
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(out, default=str),
                        })
                    continue
                # Final answer.
                return {"answer": msg.content or "", "trace": trace, "elapsed_ms": _elapsed_ms()}

    return {"answer": "Stopped after the step limit without a final answer.",
            "trace": trace, "elapsed_ms": _elapsed_ms()}


async def run_agent_streaming(query: str, token: str, principal: Principal,
                              history: list[dict] | None = None, system: str | None = None,
                              allowed_tools: list[str] | None = None,
                              max_steps: int = MAX_STEPS):
    """Async generator version of `run_agent` — yields event dicts as they happen, so the
    UI can render tokens as the model produces them (story X1 polish; ChatGPT-style UX).

    Event shapes (all dicts; the SSE wrapper serialises them):
      `{type: "text",       delta: str}`               — token-level text deltas
      `{type: "tool_start", tool: str, input: dict}`   — about to call this MCP tool
      `{type: "tool_end",   tool: str, status: str, ms: int}` — tool returned
      `{type: "done",       trace: list, elapsed_ms: int, stopped?: bool}` — final event
      `{type: "error",      detail: str}`              — caught exception

    Same MCP session pattern as `run_agent`, same token forwarding, same RBAC re-verification.
    The only thing that changes is we use the OpenAI SDK's `stream=True` and accumulate
    tool_call deltas across chunks until `finish_reason="tool_calls"` lets us execute them.
    """
    system_prompt = system or _system_prompt(principal)
    trace: list[dict] = []
    started = time.perf_counter()

    def _elapsed_ms() -> int:
        return round((time.perf_counter() - started) * 1000)

    async with streamablehttp_client(MCP_URL, headers={"Authorization": f"Bearer {token}"}) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            mcp_tools = (await session.list_tools()).tools
            tools = [
                _mcp_tool_to_openai(t) for t in mcp_tools
                if allowed_tools is None or t.name in allowed_tools
            ]
            messages: list[dict] = [
                {"role": "system", "content": system_prompt},
                *(history or []),
                {"role": "user", "content": query},
            ]

            for _ in range(max_steps):
                stream = await aclient().chat.completions.create(
                    model=MODEL, max_tokens=1024, tools=tools, messages=messages, stream=True,
                )

                content_parts: list[str] = []
                tool_calls_acc: dict[int, dict] = {}
                finish_reason: str | None = None

                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    finish_reason = chunk.choices[0].finish_reason or finish_reason

                    if delta.content:
                        content_parts.append(delta.content)
                        yield {"type": "text", "delta": delta.content}

                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            slot = tool_calls_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                            if tc_delta.id:
                                slot["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    slot["name"] += tc_delta.function.name
                                if tc_delta.function.arguments:
                                    slot["arguments"] += tc_delta.function.arguments

                if tool_calls_acc:
                    # Stream complete; the model wants to call tools. Append the assistant
                    # turn with the tool_calls verbatim so the loop's next round sees its
                    # own decision (OpenAI shape).
                    tool_calls_list = [
                        {"id": tc["id"], "type": "function",
                         "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                        for tc in tool_calls_acc.values()
                    ]
                    messages.append({
                        "role": "assistant",
                        "content": "".join(content_parts) or None,
                        "tool_calls": tool_calls_list,
                    })

                    # Execute each tool call, emit start/end events as we go.
                    for tc in tool_calls_acc.values():
                        try:
                            args = json.loads(tc["arguments"] or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        yield {"type": "tool_start", "tool": tc["name"], "input": args}
                        t0 = time.perf_counter()
                        out = _payload(await session.call_tool(tc["name"], args))
                        ms = round((time.perf_counter() - t0) * 1000)
                        status = (out.get("status") if isinstance(out, dict) else "ok") or "ok"
                        trace.append({"tool": tc["name"], "input": args, "result": out, "ms": ms})
                        yield {"type": "tool_end", "tool": tc["name"], "status": status, "ms": ms}
                        messages.append({
                            "role": "tool", "tool_call_id": tc["id"],
                            "content": json.dumps(out, default=str),
                        })
                    continue

                # No tool_calls — the final answer has been streamed already.
                yield {"type": "done", "trace": trace, "elapsed_ms": _elapsed_ms()}
                return

    yield {"type": "done", "trace": trace, "elapsed_ms": _elapsed_ms(), "stopped": True}
