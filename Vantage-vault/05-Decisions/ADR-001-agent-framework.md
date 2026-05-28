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

## Context
We're building Vantage, an agentic assistant. The brief (§4.1) requires the agent to **select tools dynamically** based on the query — "prompt-only solutions that bypass tool use will not satisfy." So it must be the *agent* pattern (LLM-driven tool selection), not a hard-coded workflow.

The flow is simple: **ask → LLM picks tool(s) → tool runs (with an RBAC check) → answer.** Five flat tools, no inter-tool dependencies, no parallelism, no human-in-the-loop (HITL), no long-running/durable execution.

Constraints: a 7-day build; must be defensible in a 1-hour panel where *engineering judgement* is graded, not just whether it runs; builder prefers model-agnostic and is not deeply technical (so explainability matters).

The decision: how to structure the agent loop — a minimal hand-written tool-calling loop, or an orchestration framework (LangGraph).

## Decision
Build a **minimal single-agent tool-calling loop** on the model's native tool use. The LLM chooses tools; each tool enforces RBAC server-side and queries Postgres; results return to the model until it answers. **Not LangGraph.**

Two constraints baked in from day one:
- **Model-agnostic** — the model call goes through `app/llm.py`, which uses the **OpenAI Python SDK with a swappable `base_url`** (the 2025-26 multi-provider lingua franca: Anthropic, Bedrock, OpenRouter, Together, Groq, Gemini all expose OpenAI-compatible endpoints). Swapping provider is **one env-var of work** (`LLM_BASE_URL` + `LLM_MODEL` + `LLM_API_KEY`); no code change. **LiteLLM considered and rejected** — March 2026 PyPI supply-chain compromise (versions 1.82.7/1.82.8 exfiltrated LLM credentials), plus documented streaming + tool-calling bugs across providers and ~40ms per-call overhead. **Gateway pattern (Portkey / Vercel AI Gateway / Bifrost)** is the right answer at governance/observability scale — deferred until volume demands it (out of scope for a single-host demo).
- **Designed for a contained LangGraph migration later** — tools are standalone functions exposed via the MCP server; session state is explicit and serializable (in Redis); the loop lives in one module. A future move to LangGraph swaps only the orchestration layer; tools, data, RBAC, MCP, and evals all carry over.

## Alternatives considered
- **LangGraph (graph orchestration).** *Rejected for v1.* Its value-adds — durable execution, HITL, parallelism, complex branching/retry — none apply to a single-agent, five-tool, request/response flow. It would add abstraction we'd have to explain and defend with no benefit, against Anthropic's own guidance to avoid unnecessary framework layers. Reserved for if the flow grows (see revisit trigger). Reference point: a separate, more complex agent design (parallel screening + a human sign-off gate) *did* warrant LangGraph — this doesn't.
- **Hard-coded workflow (fixed tool sequence).** *Rejected* — conflicts with the brief's "must select tools dynamically" requirement.

## Consequences
- ✅ Maximally explainable — the loop describes in one breath; ideal for the panel's judgement assessment.
- ✅ Minimal dependencies, fast to build, easy to debug.
- ✅ Tools, RBAC, MCP server, and evals are all framework-neutral and reusable.
- ✅ Strong panel narrative: right-sizing demonstrated; "why not LangGraph?" and "how would it evolve?" both have ready answers.
- ⚠️ We hand-write the loop (small) and session handling (via Redis) rather than inheriting them from a framework — accepted, and isolated in one module so it stays swappable.
- ⚠️ No built-in checkpointing / pause-resume — fine, because no story needs it; if one arises, that's the trigger to revisit (above).
