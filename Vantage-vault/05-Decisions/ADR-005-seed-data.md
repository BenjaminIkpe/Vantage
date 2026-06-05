---
title: ADR-005 — Seed data: committed static seed, generated via Faker + Claude
type: adr
status: accepted
date: 2026-05-27
revisit-by:
supersedes:
---

# ADR-005 — Seed data: a committed static seed, generated hybrid (Faker + Claude)

**Status:** accepted
**Date:** 2026-05-27

## Context
We need the database seeded with representative data sufficient to exercise all capabilities, plus an eval set with stable ground truth. Data must fit our 5-table schema, exercise all 11 tools + the Escalation Summary Skill, and plant specific eval scenarios.

## Decision
**Generate a hybrid synthetic dataset once, review it, and commit it as a static seed file** (SQL/JSON) in the repo; the DB loads it on `docker compose up`.
- **Faker (seeded)** owns the *structure* — customers, issues, foreign keys, dates, statuses, priorities — guaranteeing referential integrity and reproducibility.
- **Claude** owns the *text* — realistic issue descriptions and believable multi-update histories (what the agent must summarise).
- Domain = Acme as a B2B payments platform ([01-Frame](../01-Frame.md)); categories + risk per [04-Architecture](../04-Architecture.md).
- **Planted eval scenarios:** E1 (a customer name deliberately absent → "not found"), E2 (two near-identical customers), E3 (a customer with zero open issues), plus a clearly High/Critical account for the escalation story.
- Volume (committed seed): 12 customers, 40 issues, 132 issue-updates, 14 next-actions, one user per role.

## Alternatives considered
- **Pure LLM-generated dataset.** Rejected — LLMs don't preserve referential integrity across tables and can invent unrealistic values. Used only for text, inside a Faker-owned structure.
- **Public dataset (Kaggle/HuggingFace).** Rejected as the basis — won't fit our schema/roles, licensed non-commercial, can't be shaped to the eval cases. May *borrow* realistic ticket categories for believability.
- **Generate fresh at runtime.** Rejected — non-deterministic, slow, adds an LLM dependency to startup. A static committed seed is reproducible and identical across environments.

## Consequences
- ✅ Reproducible + identical data for the demo, evals, and any environment; no runtime LLM dependency.
- ✅ Realistic enough for the agent to summarise/reason; integrity guaranteed by code.
- ✅ Eval ground truth is baked in and hand-tuned.
- ⚠️ The generation script is a one-time dev tool; if the schema changes, regenerate + re-commit the seed.
