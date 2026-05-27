# Vantage

An agentic enterprise assistant for **Acme Operations** (a B2B payments platform) — an internal **copilot** for support and account-management staff that retrieves, summarises, and recommends next actions across customer issues, securely and auditably. Built for the EY Applied AI Engineer technical assessment.

> Design & decisions live in [`Vantage-vault/`](Vantage-vault/) — start at `00-NOW.md`.

## Repo layout
- `app/` — API + agent loop
- `db/` — schema + seed (`schema.sql`, `seed.sql`)
- `scripts/` — tooling (e.g. seed generation)
- `keycloak/` — realm config (roles + test users)
- `eval/` — evaluation set + results
- `Vantage-vault/` — design vault (ADRs, architecture, user stories)

## Integration contract (parallel build)
Two independent tracks, **disjoint file ownership**, merged via branches:
- **Infra** (`track/infra`): `docker-compose.yml`, `Dockerfile*`, `keycloak/`, `.env.example`, `app/`.
- **Data** (`track/data`): `db/schema.sql`, `scripts/generate_seed.py`, `db/seed.sql`.
- The Postgres service loads `db/schema.sql` then `db/seed.sql` on init.

## Setup
_To follow as the build lands — single command: `docker compose up`._
