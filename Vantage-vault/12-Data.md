---
title: Data — what's in the seed and why
type: data
status: active
updated: 2026-05-28
---

# Data — what's in the seed and why

> [!NOTE] Purpose
> A tour of the committed dataset that lives in `db/seed.sql` — what's actually in the database when `docker compose up` finishes, why each row is shaped that way, and what the assistant uses it for. Design rationale in [ADR-005](05-Decisions/ADR-005-seed-data.md); schema in [04-Architecture §Data model](04-Architecture.md). This doc is the *contents tour*.

## At a glance
| | |
|---|---|
| Users (one per role) | **3** — Priya (sales), Marcus (support), Dana (admin) |
| Customers | **12** — 4 scenario-rigged, 8 templated normals |
| Issues | **40** — 26 currently open (`open` / `in_progress` / `pending`) |
| Issue updates (history) | **132** — every issue has 3-6 chronological entries |
| Next actions (admin directives) | **14** — mostly open, some done/cancelled |

## How it was generated
Hybrid ([ADR-005](05-Decisions/ADR-005-seed-data.md)), embedded as a static committed seed (no runtime LLM dependency):
- **Faker (seeded, pinned 40.19.1)** owns *structure* — UK postcodes/regions, `ACME-#####` refs, date offsets, amount fills, weighted enums.
- **Claude (during development) authored the text** — issue descriptions and multi-update histories. Scenario-critical accounts (hero + twins + zero-open) are bespoke narratives; the 8 "normal" customers draw from a per-category template bank with Faker fills so they read distinct.

Determinism: `scripts/generate_seed.py` produces a byte-identical `seed.sql` from the pinned Faker version + a fixed RNG seed (`SEED = 20260527`). The data-ci suite asserts this — drift fails the build.

Dates: relative SQL expressions (`now() ± interval '<n> days'`), so the *relationships* (long-unresolved, due-soon, just-updated) hold whenever the seed loads — the demo never goes stale and eval ground truth stays stable.

## The customers — picked, not random
Each customer plants a specific behaviour for the assistant to exhibit.

| Customer | Tag | What it tests |
|---|---|---|
| **Velocity Marketplace** | **hero** | Escalation Summary on a clearly High/Critical account: KYC hold blocking go-live + repeated payout failures + critical webhook outage + multiple high/critical opens. *4 open issues → also powers the multi-turn "the second one" follow-up (X1).* |
| **Lumen Commerce** vs **Lumen Commerce Group** | **E2 twins** | Ambiguous name resolution. Same root, **different `account_ref` and region** — the assistant must disambiguate or list candidates, never silently guess. |
| **Calm Waters Subscriptions** | **E3 zero-open** | The "no open issues" path. Real customer with a real (resolved) history; nothing currently open. The assistant must say "no open issues", not fabricate. |
| **"Zzzz Holdings" / "Globex Foobar"** | **E1 absent** | Deliberately *not in the DB*. Querying must return "not found", never an invented record. |
| 8 others (Pinebrook Retail, Aperture Studios, Saffron Foods Online, Harbor Freight Digital, Meridian SaaS, Beacon Health Tech, Quartz Talent, Tindall & Crowe Books) | **normal** | A realistic background queue: 2-4 issues each, mixed status/priority from a weighted distribution. No second all-critical account — the hero stands out. |

## Velocity (the hero) — anatomy
The account that carries the entire Escalation Summary demo:

| Priority | Status | Category | Issue |
|---|---|---|---|
| critical | in_progress | onboarding_compliance | KYC review blocking marketplace go-live (~96 days old) |
| critical | open | integration | Webhook delivery failing — signature mismatch after key rotation |
| high | in_progress | payments | Repeated payout failures to connected accounts |
| medium | pending | performance | Dashboard latency during the settlement window |
| low | resolved | billing | Disputed platform fee on the April invoice |

The KYC issue is the showpiece — five chronological updates over ~90 days, each authored by Marcus (support) or Dana (admin), telling a coherent EDD / UBO / sanctions-clearance story. **That's the literal input to `summarise_issue_history`.**

## How the data feeds the application

| Table | What the app does with it |
|---|---|
| `users` | RBAC + write attribution. `role` mirrors Keycloak (display only — live check is the token, [ADR-002](05-Decisions/ADR-002-rbac-tool-boundary.md)); `keycloak_id` joins to the JWT subject. |
| `customers` | `get_customer_profile` — name/ref/region/segment/tier. `account_ref` + `region` are what make the E2 twins separable. |
| `issues` | `get_open_issues` — the "open = `open` / `in_progress` / `pending`" filter is the seed's open-vs-closed split (26 vs 14). |
| `issue_updates` | `summarise_issue_history` — the corpus the assistant condenses. The hero's five-step KYC arc is the canonical input. |
| `next_actions` | `create_next_action` / `update_next_action` (admin-only). Seeded directives on Velocity demonstrate admin escalation directives. |

## The CI safety net (`data-ci`)
`db/tests/test_data_layer.py` — 18 pytest cases run on every PR touching `db/` or `scripts/`:
- **Every role** present (sales / support / admin).
- **Volume in range** (customers 10-14, issues 35-45, updates 100-160, next-actions 10-20).
- **E1** — absent names not present.
- **E2** — at least two `Lumen Commerce%` rows with distinct `account_ref`.
- **E3** — Calm Waters exists, has issues, zero open.
- **Hero** — Velocity has ≥1 critical open and ≥3 open total.
- **Chronology** — no update predates its issue; `updated_at ≥ created_at`; every issue has history; no future timestamps.
- **`next_actions` admin-owned** — `created_by` role is always `admin`.
- **No orphan FKs** (FKs enforce, but assert anyway).
- **`seed.sql` matches the generator output exactly** — regenerates via pinned Faker, compares byte-for-byte. Drift = fail.

Validated against a throwaway Postgres before merge; a negative-control test confirms the suite actually fails when a scenario is broken.

## Bottom line
> The seed is small (40 issues) but *purpose-built*: every scenario the brief asks the assistant to handle has a specific customer staging it, and the data-ci suite holds the line so the scenarios don't silently degrade. Schema + ADR explain the *design*; this doc explains the *contents*.
