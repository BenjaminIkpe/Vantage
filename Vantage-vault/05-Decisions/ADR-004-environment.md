---
title: ADR-004 — Dev & demo environment: Azure VM, portable compose stack
type: adr
status: accepted
date: 2026-05-27
revisit-by:
supersedes:
---

# ADR-004 — Dev & demo environment: an Azure VM running a host-agnostic Docker Compose stack

**Status:** accepted
**Date:** 2026-05-27

## Context
The brief requires the stack to run via `docker compose up`, plus a live end-to-end demo on the day. Local Docker isn't viable (laptop disk constraint). Builder has Azure credits and dislikes Codespaces' auto-suspend.

## Decision
Run on **a single Azure Linux VM with Docker + Docker Compose** — the VM is just the Docker *host*. **Keep the compose stack fully portable:** no Azure-native services, no Azure-specific config; anyone can clone the repo and `docker compose up` on any Docker host.

- VM ~8 GB (e.g. B2ms); **deallocate when idle** to conserve credits.
- Dev via VS Code Remote-SSH into the VM.
- Demo day: VM stays running (no auto-suspend), connect from laptop and demo; keep a screen-recording fallback.

## Alternatives considered
- **Local Docker Desktop.** Rejected — laptop disk constraint.
- **GitHub Codespaces.** Free and viable, but auto-suspends/restarts the terminal (builder preference against); Azure credits available anyway.
- **Azure-native (Container Apps / AKS).** Rejected — re-architects away from `docker compose up`, more complexity, and couples the deliverable to Azure.

## Consequences
- ✅ Satisfies `docker compose up` and the live-demo requirement; no local disk needed.
- ✅ Portable stack → an assessor can run it anywhere; not Azure-locked. Strong panel line.
- ✅ Always-on host → no cold-start surprise on demo day.
- ⚠️ Internet dependency on demo day + must remember to deallocate the VM (cost). Mitigations: rehearse the demo path; screen-recording fallback.
- ⚠️ Dev happens on the VM (Remote-SSH) — a small workflow shift, sorted at setup (Slice 0).
