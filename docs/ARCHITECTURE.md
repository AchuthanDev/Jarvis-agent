# Architecture

See [`TARGET_ARCHITECTURE.md`](TARGET_ARCHITECTURE.md) for the full target design and
[`MIGRATION.md`](MIGRATION.md) for how the legacy codebase maps onto it.

## Current Implementation (Phase 5 push-to-talk checkpoint)

```
browser / curl ─┐
Windows voice ──┴──> FastAPI (apps/api) ──> conversation context
                           │                       └──> agent loop
                           │                              ├── core.llm providers
                           │                              ├── core.tools registry
                           │                              ├── core.security permissions
                           │                              └── core.audit records
                           ├──> /ws/device companion connections
                           ├──> PostgreSQL 16 (database/)
                           └──> Redis 7 (health/presence foundation)

Windows voice endpoint:
microphone -> energy VAD -> faster-whisper STT -> POST /api/chat -> Edge TTS -> speaker

Deployment: docker compose — jarvis-api, postgres, redis
Entrypoint: docker/entrypoint.sh runs `alembic upgrade head`, then uvicorn.
```

### API surface (Phase 4 in progress)

| Endpoint | Description |
|---|---|
| `GET /api/health/live` | Liveness: process up, returns app/version/environment. |
| `GET /api/health/ready` | Readiness: checks DB (`SELECT 1`) + Redis (`PING`); 200 ready / 503 degraded. |
| `POST /api/chat` | Non-streaming chat; returns `{conversation_id, reply}`. Voice clients may pass `source=voice`, `source_device_id`, `response_mode=voice`, and `X-JARVIS-DEVICE-TOKEN`. |
| `POST /api/chat/stream` | Server-sent-events chat (`start` / `delta` / `done` / `error`); supports the same voice metadata. |
| `GET /api/conversations` | List conversations (newest first). |
| `POST /api/conversations` | Create an empty conversation. |
| `GET /api/conversations/{id}/messages` | Full message history for a conversation. |
| `POST /api/devices/register` | Register a companion device with a one-time registration secret. |
| `GET /api/devices` | List registered devices and live presence. |
| `GET /api/devices/{id}` | Inspect one registered device without exposing credentials. |
| `POST /api/devices/{id}/commands` | Authenticated direct test endpoint for allowlisted device commands. |
| `WS /ws/device` | Authenticated companion-agent WebSocket. |
| `GET /docs` | OpenAPI interactive docs. |
| `GET /` | Static dashboard UI (served by FastAPI). |

### Layers

- `core/config.py` — pydantic-settings; every value overridable by environment / `.env`.
- `core/logging.py` — structured JSON logging (python-json-logger).
- `core/llm/` — `LLMProvider` interface + providers (OpenAI-compatible, Gemini, Groq, Ollama)
  + `registry.create_provider()` factory driven by `LLM_PROVIDER` / `LLM_MODEL` / `LLM_BASE_URL`.
- `core/agent/` — provider-neutral JSON tool-call protocol, parser, and bounded act/observe loop.
- `core/agent/prompt.py` — shared text/voice response-mode instructions; voice still uses the same agent loop.
- `core/tools/` — typed tool metadata, JSON Schema validation, registry, built-in tools.
- `core/security/` — permission policy that gates tool execution independently of the model.
- `core/audit/` — sanitized tool-call and audit-log persistence.
- `core/devices/` — device registration auth, persistence helpers, live connection manager.
- `core/conversation/` — system prompt + persistence/history assembly for chat.
- `database/base.py` — declarative base + naming convention + column mixins.
- `database/models.py` — full core schema (13 tables; see below).
- `database/session.py` — async engine/session factory, FastAPI `get_db` dependency.
- `database/alembic/` — migration pipeline; schema is changed only via migrations.
- `apps/api/main.py` — `create_app()` factory; CORS; router registration; mounts dashboard.
- `apps/api/deps.py` — shared dependencies (`get_db`, `get_llm`).
- `apps/api/routers/health.py` — health endpoints.
- `apps/api/routers/chat.py` — chat + conversation endpoints.
- `apps/api/routers/devices.py` — device registration, listing, command dispatch, WebSocket.
- `apps/dashboard/` — static chat + devices UI served at `/` (index.html, app.js, style.css).
- `device_agents/windows/` — Windows companion agent, PowerShell install/start/uninstall,
  local `.env` credential storage, and separated voice client modules.
- `device_agents/windows/voice/` — push-to-talk audio input, VAD, STT, chat client,
  TTS playback, and wake-word scaffolding.

### Schema (Phase 4)

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

approved wake-word mode, approval-based device pairing, `core/memory`, `core/events`,
`integrations/*`, Android agent, browser/mobile voice clients, `apps/worker`.
