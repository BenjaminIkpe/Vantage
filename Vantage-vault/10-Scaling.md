---
title: Scaling — does this still work at thousands of customers, or do we need RAG?
type: scaling
status: active
updated: 2026-05-28
---

# Scaling — does this still work at thousands of customers, or do we need RAG?

> [!NOTE] Purpose
> Panel-grade answer to *"what happens to Vantage when Acme has thousands of clients and a huge DB?"* — what scales as-is, what we'd change (same-paradigm), and **where RAG belongs (and where it doesn't)**. Cross-refs: [ADR-001](05-Decisions/ADR-001-agent-framework.md), [ADR-003](05-Decisions/ADR-003-mcp-server.md), [ADR-006](05-Decisions/ADR-006-memory-split.md), [03-Scope](03-Scope.md).

## Short answer
**Yes, it still works** at thousands of customers / a huge DB — and **no, RAG isn't the upgrade path for what we have**. RAG belongs **alongside** the existing tools, not in place of them.

## The core insight
Vantage is **structured retrieval via parameterised SQL tools**, not semantic search over documents. The two scale on completely different axes.

- A RAG system's bottleneck is **getting the *right slice* of a huge corpus into the prompt**, which is why it leans on embeddings + similarity search to assemble it.
- We don't have that problem because **our tools already return the right slice**. `get_open_issues(customer_id)` is an indexed parameterised lookup — the agent only ever sees one customer's open issues, never "the DB". **Context stays bounded regardless of total DB size.** That's the crucial property of tool-based retrieval, and it scales to millions of rows fine on indexed queries.

## What just keeps working as Acme grows
- **All exact/structured lookups by id or scoped filter** (profile, open issues for a customer, an issue's history + next actions). Bound by result size, not table size. Hot-path indexes already exist: `issues.customer_id`, `issues.status`, FKs, `customers.name`.
- **RBAC, MCP, agent loop, Skills** — none has a scale-dependent component. The boundary, the role re-verify, the per-Skill tool whitelist all hold.
- **Adding tables/relationships** doesn't change the contract; it changes individual tools.

## Where it strains — and the fixes are still same-paradigm
1. **Fuzzy name resolution.** `_resolve_customer` uses `ILIKE '%name%'` — at thousands of customers that's a full scan, and "Lumen" might match many. Fix: a **trigram index (`pg_trgm`)** for fast fuzzy search + ranking, or **full-text search (`tsvector`)** for free-text columns. Return top-N ranked candidates. Same SQL pattern, better index.
2. **Listing / aggregation** (e.g. admin's *"all high-risk accounts"*). Pagination, composite indexes, possibly **materialised views/rollups** for dashboards. Still SQL.
3. **Bounded tool outputs.** A customer with hundreds of issues would blow context. **The tool, not the model, decides the slice** — return top-N most-urgent + a paged view, summarise old history into a precomputed rollup, etc. The agent reasons over a deliberately bounded view.
4. **Under load.** Connection pooling (pgbouncer), **read replicas** for the read-heavy agent path, **Redis cache-aside** for hot lookups (already a Could in [03-Scope](03-Scope.md)).

## Where RAG *does* earn its place — complementary, not replacement
RAG (embeddings + vector search) is the right tool when the query is **semantic over unstructured text** and you can't express it as a filter. In Acme's world that's:
- *"Find issues **similar** to this one"* / *"customers complaining about settlement delays"* when "settlement" isn't a column or category — searching the **free-text description and update bodies**.
- A **support knowledge base / runbooks / past resolutions** the agent consults for suggestions.
- Semantic search across **audit-trail prose, contracts, or call transcripts**.

**How it'd slot in:** install **`pgvector`** in the same Postgres (no new datastore), embed the relevant text columns/docs, and expose **one more MCP tool** — `search_issues_semantic(query)` or `search_knowledge_base(query)` — **RBAC-checked like everything else**. The agent picks: exact/structured → SQL tools; *"like this"* → semantic tool. This is the **hybrid retrieval** pattern, and it slots in cleanly because we kept tools named and contained (ADR-003).

## Why our design ages well
Because tools are **named and contained**, every scaling/extension change happens **behind the MCP boundary**. Want fuzzy search? change `_resolve_customer`. Want semantic? add a new tool. Want bounded outputs? change the SQL. The **agent, contract, RBAC, and Skills don't change** — the agent just discovers the new/improved tool. That's the dividend of [ADR-003](05-Decisions/ADR-003-mcp-server.md)'s explicit *"no raw SQL, no generic Postgres MCP"* call — it was the right call for **security** (the deprecated reference Postgres MCP had a SQL-injection vuln), and it pays a second dividend in **graceful scaling**.

User-authored Skills also remain safe by construction at any scale: a Skill is *just a prompt + a tool whitelist*, RBAC stays in the tools, so even thousands of user-defined skills can't exceed callers' permissions.

## The honest non-data scaling concern
The scaling risk that *isn't* about data volume is **the agent side: tool selection at many tools**. If Acme grew to dozens or hundreds of tools across domains, putting them all in every prompt degrades tool-selection accuracy and inflates prompt cost. Real solutions:
- **Tool grouping / namespacing.**
- **Dynamic tool discovery / filtering** (filter to relevant tools per query — *retrieval over tools*).
- **Specialised agents** with smaller, focused toolsets.

MCP's `list_tools` makes this easier (we already discover dynamically). At 11 tools we're nowhere near it — but it's the next thing to flag in the panel.

## Bottom line
> The system scales to thousands of customers without changing the agent contract, because tool-based retrieval bounds context to a query-scoped slice — the database can grow; the prompt's shape doesn't. RAG isn't the upgrade path *for what we have*; it's an **additional capability** added as one more MCP tool (likely pgvector in-place) when retrieval becomes semantic over unstructured text. The genuine scaling worry isn't the DB — it's tool selection if the tool surface gets large, which has its own well-known patterns.
