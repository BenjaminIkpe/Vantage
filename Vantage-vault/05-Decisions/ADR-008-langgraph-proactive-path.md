---
title: ADR-008 — LangGraph for the proactive/HITL path (hybrid, not a rewrite)
type: adr
status: accepted
date: 2026-06-01
revisit-by: "if a third execution shape appears, or if the reactive loop ever needs durable/parallel/HITL features (then reconsider unifying on the graph)"
supersedes:
amends: ADR-001
---

# ADR-008 — Introduce LangGraph for the proactive/HITL path (hybrid)

**Status:** accepted
**Date:** 2026-06-01

## Context
[ADR-001](ADR-001-agent-framework.md) chose a **minimal tool-calling loop, not LangGraph**, and was explicit that this was a *right-sizing* call for a single-agent, five-tool, request→response flow — with a written **revisit trigger**:

> *"when a required flow needs pause/resume, human-in-the-loop approval, parallel/multi-agent execution, or durable long-running runs."*

We are now building the **proactive admin briefing** (`GET /briefing`) — a Could in [03-Scope](../03-Scope.md) and the on-demand teaser of the Phase-2 observer in [11-Future](../11-Future.md). That feature hits **every clause** of the trigger at once:
- **parallel execution** — fan the Escalation Summary skill out across the high-risk fleet, not one customer at a time;
- **human-in-the-loop approval** — the AI *drafts* next actions; an admin approves before anything is written (the *"LLM proposes, the admin disposes"* extension of [ADR-002](ADR-002-rbac-tool-boundary.md));
- **durable pause/resume** — the run pauses at the approval gate and resumes (possibly minutes later) to perform the write.

The reactive `/ask` path has none of these needs and is shipped, fast, and maximally explainable. So the decision is **not** "loop vs graph" globally — it is *where* each belongs.

## Decision
Go **hybrid**: keep the minimal loop for the reactive path; introduce a **LangGraph `StateGraph` for the proactive briefing path only**. This is the contained migration ADR-001 said we'd designed for — tools, data, RBAC, MCP, and evals all carry over unchanged; only a new orchestration layer is added, alongside (not in place of) the loop.

The briefing graph: `plan → fan_out (map, per-customer Escalation Summary skill) → detect_patterns (reduce) → draft_actions → interrupt() (admin approval) → route (writes)`. Four design choices keep it consistent with the rest of the system:

- **Nodes call the *existing* MCP tools and skills** — the graph is just another MCP client carrying a token. RBAC stays at the tool boundary (ADR-002); no privileged path bypasses it. The fan-out literally *composes the seeded `escalation-summary` skill across the fleet*, exactly as [11-Future](../11-Future.md) predicted.
- **Checkpointer = Redis (Stack), not Postgres.** The HITL pause/resume needs a durable, prod-grade checkpoint store (an in-process saver would die on restart and can't be shared across workers — a demo crutch, not shippable). Postgres is LangGraph's usual choice, but the `api` service deliberately holds **no `DATABASE_URL`** (ADR-003: "the API holds no DB access") and the RBAC story leans on that — so the checkpoint must not live in the system of record. Redis is already our ephemeral working-memory tier (ADR-006), the api already talks to it, and a paused run *is* working memory — so **`langgraph-checkpoint-redis`** is the architecturally-correct fit. It needs the RediSearch / RedisJSON modules, so the shared `redis` service moves to **`redis/redis-stack-server`** (a strict superset — session memory and the Playwright suite are unaffected). The briefing falls back to an in-process saver if the Redis path ever fails, so a checkpointer hiccup can't sink the demo — but the default path is the real, durable one.
- **The approving admin's token authorizes the write.** On resume, `create_next_action` is called with the *approver's* fresh token, so the MCP boundary authorizes the privileged write **as that admin**. The HITL approval and the RBAC-checked write become the same act — and token-expiry-across-the-pause is a non-issue.
- **No second LLM client.** The graph's LLM nodes reuse the existing `app/llm.py` adapter (OpenAI-SDK + `base_url`), so the one-env-var provider swap from ADR-001 still holds and we add **no** new LLM dependency — only `langgraph` (+ its Redis checkpointer). The reactive loop imports neither.

## Alternatives considered
- **Hand-roll it: `asyncio.gather` for fan-out + a `pending` enum / drafts table for approval.** *Rejected.* It works, but you end up **re-implementing durable checkpointing, the interrupt protocol, and resume** by hand — which is precisely what LangGraph standardises (and what EY uses it for). Choosing the graph *here*, where the trigger genuinely fires, is the honest answer to *"why a framework now?"* — and the contrast with the loop is the point.
- **Rip-and-replace: reimplement the reactive loop in LangGraph too.** *Rejected.* It would **contradict ADR-001's right-sizing** (our strongest engineering-judgement narrative), pay the abstraction tax on a trace/debug story that is currently crystal-clear, and buy **zero** functionality on a five-iteration, one-decision flow. "Loop for reactive, graph for proactive" is the senior call.
- **Postgres checkpointer for stronger durability.** *Rejected for v1* — breaks the api's DB-free boundary (above). Phase 2 moves the observer into a **dedicated worker** service that *may* own a Postgres checkpointer while the api stays DB-free.

## Consequences
- ✅ **Honours ADR-001 instead of contradicting it** — the revisit trigger is named, shown firing, and acted on. The panel question *"why didn't you use LangGraph?"* becomes *"I used it exactly where it earns its place — here's the loop, here's the graph, and here's the line between them."*
- ✅ **Real LangGraph competence on display** — map/reduce fan-out via `Send`, a checkpointer, an `interrupt()` HITL gate, durable resume — not a toy rewrite.
- ✅ **The carry-over is the headline** — tools, RBAC, MCP, Postgres, Skills, and the entire reactive surface are untouched. That containment is the dividend ADR-001/003 were designed to pay.
- ✅ Earns a real Could (the briefing) and pairs with the tracing bonus (the graph traces cleanly to Phoenix/LangSmith — see [07-Evals](../07-Evals.md) / README).
- ⚠️ **Enlarges the dependency surface** (`langgraph` + `langgraph-checkpoint-redis`, plus the tracing instrumentation) — which cuts slightly against ADR-001's minimal-deps / supply-chain caution (the reason LiteLLM was rejected). Accepted because it's **isolated to one new module + the briefing path behind a guarded import**; the reactive loop keeps its tiny dependency footprint, and a briefing failure (or even a failed LangGraph import) can never take down `/ask` or the UI.
- ⚠️ **Two execution shapes to maintain.** Accepted: they share tools/RBAC/skills, and the seam is one module (`app/briefing_graph.py`) plus two endpoints.
- ⚠️ **Demo-stage risk** — built late, on a branch, additive. If it isn't demo-stable it simply isn't merged; `main` (the graded build) stays green.
