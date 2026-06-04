---
title: ADR-004 — Dev & demo environment: Azure VM, portable compose stack
type: adr
status: superseded by ADR-007
date: 2026-05-27
revisit-by:
supersedes:
---

# ADR-004 — Dev & demo environment: an Azure VM running a host-agnostic Docker Compose stack

> [!WARNING] Superseded by [ADR-007](ADR-007-environment-codespaces.md)
> The Azure subscription was SKU-locked (new-subscription restriction) — VM creation failed across all regions/sizes. Host pivoted to GitHub Codespaces. The *portability* principle below still holds and is why the pivot was painless.

**Status:** superseded by ADR-007
**Date:** 2026-05-27

## Context
The stack must run via `docker compose up`, with a live end-to-end demo. Local Docker isn't viable (laptop disk constraint). Builder has Azure credits and dislikes Codespaces' auto-suspend.

## Decision
Run on **a single Azure Linux VM with Docker + Docker Compose** — the VM is just the Docker *host*. **Keep the compose stack fully portable:** no Azure-native services, no Azure-specific config; anyone can clone the repo and `docker compose up` on any Docker host.

- VM ~8 GB (e.g. B2ms); **deallocate when idle** to conserve credits.
- Dev via VS Code Remote-SSH into the VM.
- For the demo: the VM stays running (no auto-suspend), connect from laptop and demo; keep a screen-recording fallback.

## Alternatives considered
- **Local Docker Desktop.** Rejected — laptop disk constraint.
- **GitHub Codespaces.** Free and viable, but auto-suspends/restarts the terminal (builder preference against); Azure credits available anyway.
- **Azure-native (Container Apps / AKS).** Rejected — re-architects away from `docker compose up`, more complexity, and couples the system to Azure.

## Consequences
- ✅ Satisfies `docker compose up` and the live-demo requirement; no local disk needed.
- ✅ Portable stack → anyone can run it anywhere; not Azure-locked. Strong design point.
- ✅ Always-on host → no cold-start surprise during the demo.
- ⚠️ Internet dependency during the demo + must remember to deallocate the VM (cost). Mitigations: rehearse the flow; screen-recording fallback.
- ⚠️ Dev happens on the VM (Remote-SSH) — a small workflow shift, sorted at setup (Slice 0).
