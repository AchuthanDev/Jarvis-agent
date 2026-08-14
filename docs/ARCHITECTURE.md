# Architecture

See [`TARGET_ARCHITECTURE.md`](TARGET_ARCHITECTURE.md) for the full target design and
[`MIGRATION.md`](MIGRATION.md) for how the legacy codebase maps onto it.

## Current Implementation (Phase 3)

```
browser / curl ──> FastAPI (apps/api) ──> conversation context
                        │                       └──> agent loop
                        │                              ├── core.llm providers
                        │                              ├── core.tools registry
                        │                              ├── core.security permissions
                        │                              └── core.audit records
                        ├──> PostgreSQL 16 (database/)
                        └──> Redis 7 (health/presence foundation)

Deployment: docker compose — jarvis-api, postgres, redis
Entrypoint: docker/entrypoint.sh runs `alembic upgrade head`, then uvicorn.
```

### API surface (Phase 3)

| Endpoint | Description |
|---|---|
| `GET /api/health/live` | Liveness: process up, returns app/version/environment. |
| `GET /api/health/ready` | Readiness: checks DB (`SELECT 1`) + Redis (`PING`); 200 ready / 503 degraded. |
| `POST /api/chat` | Non-streaming chat; returns `{conversation_id, reply}`. |
| `POST /api/chat/stream` | Server-sent-events chat (`start` / `delta` / `done` / `error`). |
| `GET /api/conversations` | List conversations (newest first). |
| `POST /api/conversations` | Create an empty conversation. |
| `GET /api/conversations/{id}/messages` | Full message history for a conversation. |
| `GET /docs` | OpenAPI interactive docs. |
| `GET /` | Static dashboard UI (served by FastAPI). |

### Layers

- `core/config.py` — pydantic-settings; every value overridable by environment / `.env`.
- `core/logging.py` — structured JSON logging (python-json-logger).
- `core/llm/` — `LLMProvider` interface + providers (OpenAI-compatible, Gemini, Groq, Ollama)
  + `registry.create_provider()` factory driven by `LLM_PROVIDER` / `LLM_MODEL` / `LLM_BASE_URL`.
- `core/agent/` — provider-neutral JSON tool-call protocol, parser, and bounded act/observe loop.
- `core/tools/` — typed tool metadata, JSON Schema validation, registry, built-in tools.
- `core/security/` — permission policy that gates tool execution independently of the model.
- `core/audit/` — sanitized tool-call and audit-log persistence.
- `core/conversation/` — system prompt + persistence/history assembly for chat.
- `database/base.py` — declarative base + naming convention + column mixins.
- `database/models.py` — full core schema (13 tables; see below).
- `database/session.py` — async engine/session factory, FastAPI `get_db` dependency.
- `database/alembic/` — migration pipeline; schema is changed only via migrations.
- `apps/api/main.py` — `create_app()` factory; CORS; router registration; mounts dashboard.
- `apps/api/deps.py` — shared dependencies (`get_db`, `get_llm`).
- `apps/api/routers/health.py` — health endpoints.
- `apps/api/routers/chat.py` — chat + conversation endpoints.
- `apps/dashboard/` — static chat UI served at `/` (index.html, app.js, style.css).

### Schema (Phase 3)

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

`core/memory`, `core/events`, `integrations/*`, `voice/*`, `device_agents/*`,
`apps/worker`, `android-agent`.
