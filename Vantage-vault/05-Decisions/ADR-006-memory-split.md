---
title: ADR-006 — Memory split: Redis for session, PostgreSQL for the system of record
type: adr
status: accepted
date: 2026-05-27
revisit-by:
supersedes:
---

# ADR-006 — Memory split: Redis for session/working memory, PostgreSQL as the system of record

**Status:** accepted
**Date:** 2026-05-27

## Context
The brief requires Redis for ≥1 of {session memory, preferences, cached lookups, recent tool results} **and a documented Redis-vs-Postgres rationale.** We chose multi-turn session memory (story X1) as the Redis use. LLMs are stateless — each request rebuilds the conversation context — so session/working memory is ephemeral and read constantly, whereas business records must be durable, related, queryable, and audited.

## Decision
**Redis = ephemeral session / working memory (reconstructible):**
- Multi-turn conversation history + recent tool outputs for the current session (story X1).
- Keyed per session (`session:{session_id}`), with a **TTL** (~1 hour) so abandoned sessions self-clean; conversation kept as a rolling buffer within the token budget.
- *(Could, time-permitting)* cache-aside for `get_customer_profile` — short TTL + invalidate on write.

**PostgreSQL = the durable system of record (ACID, audited):**
- `customers`, `issues`, `issue_updates`, `next_actions`, `users` — anything that must survive a restart, be related/queried, and be auditable.

**Rule:** never put the system of record in Redis. If Redis is wiped, we lose only in-flight session context — never business data.

## Alternatives considered
- **Everything in Postgres (incl. session).** Genuinely viable at this scale — for a single-user demo Postgres could hold session too, with one fewer moving part. Rejected because (a) the brief requires Redis, and (b) session/working memory is exactly what Redis is built for — the clean separation of transient speed from durable truth.
- **Everything in Redis.** Rejected — no ACID durability/auditability; the brief's records must persist and be traceable.

## Consequences
- ✅ Clean separation: transient speed (Redis) vs durable truth (Postgres); satisfies the brief and documents the rationale.
- ✅ Session auto-expiry via TTL; a Redis outage degrades gracefully (lose context, not data).
- ✅ Strong panel answer to "why Redis vs Postgres, and what did you put where?"
- ⚠️ Honest scale note: Redis isn't a performance *necessity* at demo scale — it's the right *tool* for session memory and a brief requirement, not a perf claim. (Good candour for the panel.)
- ⚠️ Two stores to run — accepted; both are standard Compose services.
