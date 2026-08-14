# Architecture

See [`TARGET_ARCHITECTURE.md`](TARGET_ARCHITECTURE.md) for the full target design and
[`MIGRATION.md`](MIGRATION.md) for how the legacy codebase maps onto it.

## Current Implementation (Phase 1)

```
browser / curl ──> FastAPI (apps/api) ──> core.config (env-driven)
                        │
                        ├──> PostgreSQL 16 (database/)  SQLAlchemy async + Alembic
                        └──> Redis 7 (core config: redis_url)

Deployment: docker compose — jarvis-api, postgres, redis
Entrypoint: docker/entrypoint.sh runs `alembic upgrade head`, then uvicorn.
```

### API surface (Phase 1)

| Endpoint | Description |
|---|---|
| `GET /api/health/live` | Liveness: process up, returns app/version/environment. |
| `GET /api/health/ready` | Readiness: checks DB (`SELECT 1`) + Redis (`PING`); 200 ready / 503 degraded. |
| `GET /docs` | OpenAPI interactive docs. |

### Layers

- `core/config.py` — pydantic-settings; every value overridable by environment / `.env`.
- `core/logging.py` — structured JSON logging (python-json-logger).
- `database/base.py` — declarative base + naming convention + column mixins.
- `database/models.py` — full core schema (13 tables; see below).
- `database/session.py` — async engine/session factory, FastAPI `get_db` dependency.
- `database/alembic/` — migration pipeline; schema is changed only via migrations.
- `apps/api/main.py` — `create_app()` factory; CORS; router registration.
- `apps/api/routers/health.py` — health endpoints.

### Schema (Phase 1)

`users`, `devices`, `device_capabilities`, `conversations`, `messages`, `memories`,
`tasks`, `tool_calls`, `events`, `integrations`, `settings`, `permissions`,
`audit_logs` (+ `alembic_version`).

### Design decisions

1. **Configuration** is the single source of truth for environment wiring; nothing is
   hardcoded (credentials, IPs, paths).
2. **Migrations are the only way the schema changes.**
3. **Redis is included** because Phase 3+ requires device presence, pub/sub for events,
   and background queues — it is not decorative.
4. **Non-root container** (`jarvis` user); healthchecks; named network; named volumes;
   `restart: unless-stopped`.
5. **No secrets in the repo**: `.env` is gitignored; `docker-compose.yml` only references
   `POSTGRES_PASSWORD` from `.env`.

### Later phases add

`core/agent`, `core/llm` (provider abstraction), `core/tools` (registry + permission
enforcement), `core/memory`, `core/conversation`, `core/events`, `integrations/*`,
`voice/*`, `device_agents/*`, `apps/worker`, `apps/dashboard`.
