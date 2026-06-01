"""Proactive admin briefing — a LangGraph StateGraph (ADR-008), the hybrid's *second*
execution shape alongside the reactive tool-calling loop in app/agent.py.

Why a graph here and not the loop: this flow hits the revisit trigger ADR-001 wrote down —
**parallel fan-out** (brief the high-risk fleet at once), a **human-in-the-loop approval gate**
(the AI drafts next actions; an admin approves before any write), and **durable pause/resume**
across that gate. The loop serves reactive /ask; this graph serves GET /briefing. Tools, RBAC,
MCP, and the seeded escalation-summary skill all carry over unchanged — the graph is just
another MCP client carrying the caller's token.

Shape:
    plan ─▶ summarise_one (map: one task per high-risk customer, fanned out with Send)
         ─▶ detect ─▶ draft ─▶ approval (interrupt) ─▶ route ─▶ END

- plan:          get_high_risk_customers (admin-only MCP tool) picks who to brief.
- summarise_one: per customer, compose the seeded `escalation-summary` skill (the narrative)
                 + pull structured open issues (to ground the drafts). Runs in parallel.
- detect:        detect_patterns (admin-only MCP tool) — cross-customer clusters.
- draft:         one LLM call drafts a concrete next action per account, each tied to a REAL
                 open issue_id (validated against what we fetched — never a hallucinated id).
- approval:      interrupt() — hands the drafts to the caller and pauses the run durably.
- route:         on resume, write each APPROVED draft via the existing create_next_action MCP
                 tool, using the *approving admin's* token — so RBAC at the boundary authorises
                 the write as that admin. The HITL approval and the privileged write are one act.

Checkpointer: injected via init() from the API's lifespan — a durable Redis (Stack) saver in
normal operation (langgraph-checkpoint-redis), so a run paused at the gate survives between
GET /briefing and POST /briefing/{id}/approve (and across an api restart). Redis, not Postgres:
the api is deliberately free of the system-of-record (ADR-003), and a paused run is ephemeral
working memory (ADR-006). If init() is never called, we lazily fall back to an in-process saver
so the module is still usable in isolation.
"""
import json
import operator
import os
import re
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send, Command, interrupt

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from agent import _payload, complete
from security import Principal
from skills import get_skill, run_skill

MCP_URL = os.getenv("MCP_URL", "http://mcp:8001/mcp")
ESCALATION_SKILL = "escalation-summary"
DEFAULT_BRIEF_LIMIT = int(os.getenv("BRIEFING_LIMIT", "5"))


class BriefingState(TypedDict, total=False):
    # inputs (set when the run starts)
    token: str
    username: str
    roles: list[str]
    subject: str | None
    limit: int
    window_days: int | None
    # accumulated as the graph runs
    customers: list[dict]
    coverage: dict
    summaries: Annotated[list[dict], operator.add]  # reducer: parallel map tasks append
    patterns: list[dict]
    drafts: list[dict]
    approvals: dict
    results: list[dict]


async def _call_tool(name: str, args: dict, token: str) -> dict:
    """One direct MCP tool call with the caller's token forwarded — the server re-verifies it
    and the tool enforces RBAC (ADR-002/003). Same call path as the agent, for a single call."""
    async with streamablehttp_client(MCP_URL, headers={"Authorization": f"Bearer {token}"}) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            return _payload(await session.call_tool(name, args))


# --- nodes -------------------------------------------------------------------


async def plan(state: BriefingState) -> dict:
    """Pick the high-risk fleet slice to brief (admin-only MCP read)."""
    res = await _call_tool(
        "get_high_risk_customers", {"limit": state.get("limit", DEFAULT_BRIEF_LIMIT)}, state["token"]
    )
    customers = res.get("customers", []) if res.get("status") == "ok" else []
    coverage = {k: res.get(k) for k in ("briefed_count", "total_count", "has_more", "note")}
    return {"customers": customers, "coverage": coverage}


def fan_out(state: BriefingState):
    """Map: one summarise_one task per high-risk customer, run in parallel via Send. If the
    fleet is clean (no high-risk accounts), skip straight to pattern detection."""
    customers = state.get("customers") or []
    if not customers:
        return "detect"
    return [
        Send("summarise_one", {
            "name": c["name"],
            "customer_id": c.get("id"),
            "token": state["token"],
            "username": state["username"],
            "roles": state["roles"],
            "subject": state.get("subject"),
        })
        for c in customers
    ]


async def summarise_one(work: dict) -> dict:
    """Per customer (a Send payload): compose the seeded escalation-summary skill (narrative)
    + fetch structured open issues (for grounded drafting). One customer's failure degrades to
    a noted entry rather than failing the whole briefing."""
    name = work["name"]
    token = work["token"]
    principal = Principal(username=work["username"], roles=work["roles"], subject=work.get("subject"))
    entry: dict = {"customer": name, "customer_id": work.get("customer_id")}
    try:
        issues = await _call_tool("get_open_issues", {"name": name}, token)
        open_issues = issues.get("open_issues", []) if issues.get("status") == "found" else []
        entry["open_count"] = issues.get("open_count", len(open_issues))
        entry["top_issue"] = open_issues[0] if open_issues else None
    except Exception as exc:
        entry["top_issue"] = None
        entry["error"] = f"open-issues lookup failed: {exc}"
    try:
        skill = get_skill(ESCALATION_SKILL)
        if skill is not None:
            res = await run_skill(skill, {"customer": name}, token=token, principal=principal)
            entry["summary"] = res.get("answer", "")
        else:
            entry["summary"] = ""
    except Exception as exc:
        entry["summary"] = ""
        entry["error"] = f"{entry.get('error', '')}; skill failed: {exc}".strip("; ")
    return {"summaries": [entry]}


async def detect(state: BriefingState) -> dict:
    """Cross-customer pattern detection (admin-only MCP read)."""
    try:
        res = await _call_tool("detect_patterns", {"window_days": state.get("window_days")}, state["token"])
        patterns = res.get("patterns", []) if res.get("status") == "ok" else []
    except Exception:
        patterns = []
    return {"patterns": patterns}


_DRAFT_SYSTEM = (
    "You are Vantage drafting suggested next actions for an Acme Operations admin to review and "
    "approve (Acme is a B2B payments platform). You are given the highest-risk accounts (each "
    "with its single most urgent OPEN issue and that issue's id), short per-account summaries, "
    "and any cross-customer patterns. Propose AT MOST ONE concrete next action per account, each "
    "tied to one of the provided issue_ids. Be specific and operational — what to do and what it "
    "concerns. Write plain text, no emojis. Return ONLY a JSON array; each element: "
    '{"customer": str, "issue_id": int, "description": str, "due_date": "YYYY-MM-DD" or null, '
    '"rationale": str}. Use ONLY issue_ids from the provided list. Return [] if nothing warrants '
    "action."
)


def _parse_json_array(raw: str) -> list:
    """Tolerant parse of the model's reply into a list — accepts a bare JSON array or a ```json
    fenced one. Returns [] on anything else (the briefing then proposes no drafts)."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


async def draft(state: BriefingState) -> dict:
    """One LLM call drafts a concrete next action per high-risk account, each tied to a real
    open issue_id. Drafts referencing an id we did not fetch are dropped — grounding holds even
    for proposals, so we never draft (or later write) against an invented issue."""
    summaries = state.get("summaries", [])
    valid: dict[int, dict] = {}
    lines: list[str] = []
    for s in summaries:
        ti = s.get("top_issue")
        if ti and ti.get("id") is not None:
            valid[int(ti["id"])] = {"customer": s["customer"], "issue": ti}
            lines.append(
                f"- {s['customer']}: issue_id={ti['id']} | priority={ti.get('priority', '?')} | "
                f"{ti.get('title', '')} | summary: {(s.get('summary') or '').strip()[:300]}"
            )
    if not lines:
        return {"drafts": []}
    patterns = state.get("patterns", [])
    pat_text = "; ".join(
        f"{p.get('category')} open at {p.get('customer_count')} accounts "
        f"({', '.join((p.get('customers') or [])[:5])})"
        for p in patterns
    ) or "none"
    user = (
        "High-risk accounts and their most urgent open issue:\n" + "\n".join(lines)
        + f"\n\nCross-customer patterns: {pat_text}\n\nDraft the next actions now."
    )
    try:
        raw = await complete(_DRAFT_SYSTEM, user, max_tokens=900)
    except Exception:
        return {"drafts": []}
    drafts: list[dict] = []
    for d in _parse_json_array(raw):
        if not isinstance(d, dict):
            continue
        try:
            iid = int(d.get("issue_id"))
        except (TypeError, ValueError):
            continue
        if iid not in valid:
            continue
        drafts.append({
            "draft_id": len(drafts),
            "customer": valid[iid]["customer"],
            "issue_id": iid,
            "issue_title": valid[iid]["issue"].get("title"),
            "description": str(d.get("description", "")).strip(),
            "due_date": d.get("due_date") or None,
            "rationale": str(d.get("rationale", "")).strip(),
        })
    return {"drafts": drafts}


async def approval(state: BriefingState) -> dict:
    """Human-in-the-loop gate. With drafts to review, pause the run (interrupt) and hand them to
    the caller; the resume value carries the admin's decision. No drafts -> nothing to approve,
    fall straight through."""
    drafts = state.get("drafts") or []
    if not drafts:
        return {"approvals": {"approved_ids": []}}
    decision = interrupt({"action": "approve_next_actions", "drafts": drafts})
    return {"approvals": decision or {"approved_ids": []}}


async def route(state: BriefingState) -> dict:
    """Write each APPROVED draft via the existing create_next_action MCP tool, using the
    approving admin's token — RBAC at the boundary authorises the write as that admin (the
    approval IS the authorisation). Unapproved drafts are skipped; nothing else is written."""
    approvals = state.get("approvals") or {}
    approved_ids = set(approvals.get("approved_ids") or [])
    approver = approvals.get("approver") or {}
    token = approver.get("token") or state["token"]  # demo fallback: the original admin
    results: list[dict] = []
    for d in state.get("drafts") or []:
        if d["draft_id"] not in approved_ids:
            results.append({"draft_id": d["draft_id"], "status": "skipped"})
            continue
        try:
            res = await _call_tool("create_next_action", {
                "issue_id": d["issue_id"],
                "description": d["description"],
                "due_date": d.get("due_date"),
            }, token)
            results.append({
                "draft_id": d["draft_id"], "issue_id": d["issue_id"],
                "status": res.get("status"), "next_action": res.get("next_action"),
            })
        except Exception as exc:
            results.append({"draft_id": d["draft_id"], "status": "error", "detail": str(exc)})
    return {"results": results}


# --- graph build + lifecycle -------------------------------------------------


def build_graph(checkpointer):
    """Compile the briefing graph with the given checkpointer (durable Redis saver in prod;
    an in-process saver as the fallback)."""
    g = StateGraph(BriefingState)
    g.add_node("plan", plan)
    g.add_node("summarise_one", summarise_one)
    g.add_node("detect", detect)
    g.add_node("draft", draft)
    g.add_node("approval", approval)
    g.add_node("route", route)
    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", fan_out, ["summarise_one", "detect"])
    g.add_edge("summarise_one", "detect")  # fan-in: detect runs once after all map tasks
    g.add_edge("detect", "draft")
    g.add_edge("draft", "approval")
    g.add_edge("approval", "route")
    g.add_edge("route", END)
    return g.compile(checkpointer=checkpointer)


_GRAPH = None


def init(checkpointer) -> None:
    """Compile + cache the graph with the injected checkpointer (called from the API lifespan)."""
    global _GRAPH
    _GRAPH = build_graph(checkpointer)


def _graph():
    """The compiled graph; lazily fall back to an in-process saver if init() was never called."""
    global _GRAPH
    if _GRAPH is None:
        from langgraph.checkpoint.memory import MemorySaver
        _GRAPH = build_graph(MemorySaver())
    return _GRAPH


def _config(briefing_id: str) -> dict:
    return {"configurable": {"thread_id": briefing_id}}


async def start_briefing(briefing_id: str, principal: Principal, token: str,
                         limit: int | None = None, window_days: int | None = None) -> dict:
    """Run the graph to the approval gate and return the digest + drafts. `pending_approval` is
    True when the run paused at interrupt() (there are drafts to approve)."""
    graph = _graph()
    config = _config(briefing_id)
    await graph.ainvoke({
        "token": token,
        "username": principal.username,
        "roles": principal.roles,
        "subject": principal.subject,
        "limit": limit or DEFAULT_BRIEF_LIMIT,
        "window_days": window_days,
    }, config)
    snap = await graph.aget_state(config)
    vals = snap.values
    return {
        "briefing_id": briefing_id,
        "pending_approval": bool(snap.next),
        "coverage": vals.get("coverage", {}),
        "summaries": vals.get("summaries", []),
        "patterns": vals.get("patterns", []),
        "drafts": vals.get("drafts", []),
        "results": vals.get("results", []),
    }


async def approve_briefing(briefing_id: str, principal: Principal, token: str,
                           approved_ids: list[int]) -> dict | None:
    """Resume a paused briefing with the admin's approval and write the approved next actions
    (the approver's token authorises each write). Returns None for an unknown/expired briefing."""
    graph = _graph()
    config = _config(briefing_id)
    snap = await graph.aget_state(config)
    if not snap.values:
        return None  # unknown thread_id -> 404
    if not snap.next:
        # already completed (or had nothing to approve) — idempotent re-call
        return {"briefing_id": briefing_id, "pending_approval": False,
                "results": snap.values.get("results", []), "already_resolved": True}
    await graph.ainvoke(Command(resume={
        "approved_ids": list(approved_ids or []),
        "approver": {
            "token": token,
            "username": principal.username,
            "roles": principal.roles,
            "subject": principal.subject,
        },
    }), config)
    snap2 = await graph.aget_state(config)
    return {
        "briefing_id": briefing_id,
        "pending_approval": bool(snap2.next),
        "drafts": snap2.values.get("drafts", []),
        "results": snap2.values.get("results", []),
    }
