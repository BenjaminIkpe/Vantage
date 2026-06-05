---
title: Security posture & threat model
type: security
status: active
updated: 2026-05-27
---

# Security posture & threat model

> [!NOTE] Purpose
> Build "above board" for a security-sensitive app: threat-model with an attacker's eye, bake defences into every slice, and be explicit about dev-vs-production hardening. Documented in the README; it informs the dev→prod hardening plan.

## On the Keycloak "JDBC ResultSet leaked" warning
**Benign.** It's logged by Keycloak's *own* connection pool (Agroal) during its Liquibase schema-init against the **H2 dev database** — inside Keycloak's bootstrap, not our code, and it doesn't affect token issuance or security. It does, however, correctly flag that we run Keycloak in **dev mode**, which has insecure-by-design conveniences — tracked below.

## Threats → mitigations (built into the slices)
| # | Threat | Mitigation |
|---|---|---|
| T1 | Token forgery / unverified tokens | API **fully verifies the JWT**: signature vs Keycloak JWKS, issuer, audience, expiry; reject `alg:none`. Never trust a decoded-but-unverified token. |
| T2 | Broken access control / privilege escalation | **RBAC enforced server-side in each tool** (ADR-002); role read from the **verified token**, never a client header. Every mutating tool checks before acting; the denial path is tested. |
| T3 | SQL injection | **Parameterised queries only**; no string-built SQL; no raw-SQL tool (why we rejected the generic Postgres MCP — ADR-003). |
| T4 | Prompt injection (malicious text inside issue data) | The **LLM is not a trust boundary**: tool-layer RBAC + parameterised SQL mean even a fully-hijacked agent can't exceed the caller's permissions or run arbitrary SQL. Scope tool inputs; validate outputs; keep secrets out of the model's context. |
| T5 | Cross-customer data leakage | Tools scope to the requested customer; no tool returns unrelated customers' data. |
| T6 | Secrets exposure | Secrets via env / `.env` (git-ignored); `.env.example` is placeholders only; no real keys committed. |
| T7 | Sensitive data in logs | Audit/tool logs record identifiers + actions — **not** tokens or full PII. |

## Dev-mode now → production hardening
- Keycloak `start-dev` + H2 → production `start` + a real DB + TLS + persistence.
- ROPC / `directAccessGrantsEnabled` (dev token-fetch) → **authorization-code flow**.
- `redirectUris` / `webOrigins: ["*"]` → explicit allow-lists.
- Temporary admin + dev passwords → real admin + strong secrets via a secrets manager.
- HTTP → HTTPS/TLS; Keycloak behind a proxy, not internet-exposed.
- Add: rate limiting, request-size limits, dependency/image scanning.
