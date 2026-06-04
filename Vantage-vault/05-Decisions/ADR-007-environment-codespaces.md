---
title: ADR-007 — Dev & demo environment: GitHub Codespaces (supersedes ADR-004)
type: adr
status: accepted
date: 2026-05-27
revisit-by:
supersedes: ADR-004
---

# ADR-007 — Dev & demo environment: GitHub Codespaces

**Status:** accepted (supersedes ADR-004)
**Date:** 2026-05-27

## Context
ADR-004 chose an Azure VM (the builder has credits and disliked Codespaces' auto-suspend). On attempting to provision, the subscription returned `SkuNotAvailable — Capacity Restrictions` for **every** VM size tried (D2s_v5, B2ms, B2s) across **every** region (uksouth, northeurope, ukwest, eastus). A uniform, total block like that is the well-known **new-subscription SKU lockdown** — Azure restricts brand-new / free subscriptions from deploying standard VMs until the account has billing history. Not transient capacity; not beatable by trying more sizes.

## Decision
Pivot the dev & demo host to **GitHub Codespaces** — a cloud dev environment on the repo, with **Docker-in-Docker** so `docker compose up` runs in the cloud (no local Docker / disk). A `.devcontainer/devcontainer.json` makes the repo Codespaces-ready (Python 3.12 base + docker-in-docker + forwarded ports 8000 / 8080).

The compose stack stays **fully portable** — ADR-004's core principle holds; Codespaces is just the host. Anyone can still `docker compose up` anywhere.

Mitigate the auto-suspend annoyance via a longer idle timeout in Codespaces settings.

## Alternatives considered
- **Azure VM (ADR-004).** Blocked by the new-subscription SKU lockdown. *Parallel option:* file an Azure SKU/quota-increase request; if approved before the deadline, the same portable stack can move to Azure for the demo. Not blocking the build on it.
- **Local Docker.** Still ruled out (laptop disk).
- **Azure Container Instances.** Doesn't run docker-compose cleanly; not worth the adaptation.

## Consequences
- ✅ Unblocked immediately; runs the same portable compose stack; no quota fight.
- ✅ Clear decision narrative: tried Azure, hit a real constraint, diagnosed it, pivoted cleanly **because the stack was host-agnostic by design** (ADR-004's portability principle paid off).
- ⚠️ Codespaces auto-suspends on idle (the original gripe) — mitigated via the idle-timeout setting; demo rehearsal still required.
- ⚠️ Docker-dependent work runs *in* the Codespace, not on the laptop — full-stack run/test happens there (infra files can still be authored locally).
- Note: the empty `vantage-rg` is left in Azure (no cost) in case the SKU request clears.
