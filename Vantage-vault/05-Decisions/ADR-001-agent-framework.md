---
title: ADR-001 — Agent framework: simple tool-calling loop
type: adr
status: accepted
date: 2026-05-27
revisit-by: "when a required flow needs pause/resume, human-in-the-loop approval, parallel/multi-agent execution, or durable long-running runs"
supersedes:
---

# ADR-001 — Agent framework: a simple tool-calling loop, not LangGraph

**Status:** accepted
**Date:** 2026-05-27

> [!NOTE] Update (2026-05-30) — revisit trigger fired
> This ADR governs the **reactive `/ask` loop** and still stands for it. But the **proactive briefing** needs exactly what the revisit trigger named — parallel fan-out + human-in-the-loop + durable pause/resume — so that one path is built as a **LangGraph** graph: see [ADR-008](ADR-008-langgraph-proactive-path.md). The result is a deliberate **hybrid** (loop for reactive, graph where its triggers fire), not a reversal of this decision.

## Context
We're building Vantage, an agentic assistant. A core requirement is that the agent **select tools dynamically** based on the query — prompt-only solutions that bypass tool use don't qualify. So it must be the *agent* pattern (LLM-driven tool selection), not a hard-coded workflow.

The flow is simple: **ask → LLM picks tool(s) → tool runs (with an RBAC check) → answer.** Five flat tools, no inter-tool dependencies, no parallelism, no human-in-the-loop (HITL), no long-running/durable execution.

Constraints: a tight build timeline; the design must be clearly defensible — *engineering judgement* matters, not just whether it runs; builder prefers model-agnostic and values explainability.

The decision: how to structure the agent loop — a minimal hand-written tool-calling loop, or an orchestration framework (LangGraph).

## Decision
Build a **minimal single-agent tool-calling loop** on the model's native tool use. The LLM chooses tools; each tool enforces RBAC server-side and queries Postgres; results return to the model until it answers. **Not LangGraph.**

Two constraints baked in from day one:
- **Model-agnostic** — the model call goes through `app/llm.py`, which uses the **OpenAI Python SDK with a swappable `base_url`** (the 2025-26 multi-provider lingua franca: Anthropic, Bedrock, OpenRouter, Together, Groq, Gemini all expose OpenAI-compatible endpoints). Swapping provider is **one env-var of work** (`LLM_BASE_URL` + `LLM_MODEL` + `LLM_API_KEY`); no code change. **LiteLLM considered and rejected** — March 2026 PyPI supply-chain compromise (versions 1.82.7/1.82.8 exfiltrated LLM credentials), plus documented streaming + tool-calling bugs across providers and ~40ms per-call overhead. **Gateway pattern (Portkey / Vercel AI Gateway / Bifrost)** is the right answer at governance/observability scale — deferred until volume demands it (out of scope for a single-host demo).
- **Designed for a contained LangGraph migration later** — tools are standalone functions exposed via the MCP server; session state is explicit and serializable (in Redis); the loop lives in one module. A future move to LangGraph swaps only the orchestration layer; tools, data, RBAC, MCP, and evals all carry over.

## Alternatives considered
- **LangGraph (graph orchestration).** *Rejected for v1.* Its value-adds — durable execution, HITL, parallelism, complex branching/retry — none apply to a single-agent, five-tool, request/response flow. It would add abstraction we'd have to explain and defend with no benefit, against Anthropic's own guidance to avoid unnecessary framework layers. Reserved for if the flow grows (see revisit trigger) — **which it now has: the proactive briefing is built as a LangGraph graph ([ADR-008](ADR-008-langgraph-proactive-path.md))**. Reference point: a separate, more complex agent design (parallel screening + a human sign-off gate) *did* warrant LangGraph — this doesn't.
- **Hard-coded workflow (fixed tool sequence).** *Rejected* — conflicts with the dynamic-tool-selection requirement.

## Consequences
- ✅ Maximally explainable — the loop describes in one breath; ideal for maintainability and onboarding.
- ✅ Minimal dependencies, fast to build, easy to debug.
- ✅ Tools, RBAC, MCP server, and evals are all framework-neutral and reusable.
- ✅ Clear design rationale: right-sizing demonstrated; "why not LangGraph?" and "how would it evolve?" both have ready answers.
- ⚠️ We hand-write the loop (small) and session handling (via Redis) rather than inheriting them from a framework — accepted, and isolated in one module so it stays swappable.
- ⚠️ No built-in checkpointing / pause-resume — fine, because no story needs it; if one arises, that's the trigger to revisit (above).
