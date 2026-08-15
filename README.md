# JARVIS

A personal, distributed AI operating layer. JARVIS runs as a central brain on a home
server and coordinates device agents (Windows, Android, browser, Home Assistant, …),
voice, memory, tools, and long-running tasks.

This is a ground-up redesign of the classic `GauravSingh9356/J.A.R.V.I.S` voice script
(now preserved under [`legacy/`](legacy/README.md)). See
[`docs/MIGRATION.md`](docs/MIGRATION.md) for what is kept, refactored, replaced, and removed.

> **Status: Phase 5 push-to-talk checkpoint** — Windows text/device control has
> passed real laptop validation. The Windows voice client is ready for manual
> push-to-talk testing; wake-word mode is intentionally held until that passes.
> Follow progress in [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Quick Start (Debian server)

Prerequisites: Docker Engine + Docker Compose plugin.

```bash
# 1. Clone
git clone https://github.com/your-org/jarvis.git && cd jarvis

# 2. Configure
cp .env.example .env
#   then edit .env:
#     - POSTGRES_PASSWORD   (required)
#     - JARVIS_SECRET_KEY   (recommended: random 32+ chars)

# 3. Start
docker compose up -d --build

# 4. Verify
curl http://localhost:8000/api/health/live     # {"status":"ok", ...}
curl http://localhost:8000/api/health/ready    # database + redis checks
```

Database migrations run automatically on container startup. Interactive docs:
<http://localhost:8000/docs>.

## Project Layout

```text
apps/api        FastAPI backend
core/           config, logging, LLM providers, conversations, tools, devices, permissions, audit
database/       SQLAlchemy models + Alembic migrations
device_agents/  platform companion agents (Windows started; Android later)
docs/           architecture, migration, roadmap, security, protocols
docker/         image definitions
tests/          pytest suite
scripts/        local validation utilities
legacy/         original J.A.R.V.I.S source (preserved)
```

Full target structure: [`docs/TARGET_ARCHITECTURE.md`](docs/TARGET_ARCHITECTURE.md).

## Common Commands

```bash
docker compose up -d          # start
docker compose down           # stop (add -v to drop volumes)
docker compose logs -f        # logs
make test                     # run tests in the dev container
make lint                     # run ruff
make new-migration name="x"   # autogenerate an Alembic migration
make migrate                  # apply migrations
python scripts/test_windows_tool.py --help  # direct Windows device tool test
```

Windows voice client commands live in `device_agents/windows`:

```powershell
.\install-voice.ps1
.\voice.ps1 --list-devices
.\voice.ps1 --push-to-talk
```

## Configuration

Configuration is environment-driven via `.env` (see `.env.example`). Never commit
real credentials. Key variables:

| Variable | Purpose |
|---|---|
| `POSTGRES_PASSWORD` | Postgres password (used by the container and connection string) |
| `DATABASE_URL` | Async SQLAlchemy URL (overridden to the `postgres` service in Compose) |
| `REDIS_URL` | Redis URL (overridden to the `redis` service in Compose) |
| `LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` | AI provider |
| `JARVIS_SECRET_KEY` | Application signing secret |
| `TOOLS_ENABLED` / `TOOL_MAX_AUTONOMOUS_RISK` | Tool-calling gate and autonomous risk threshold |
| `DEVICE_REGISTRATION_SECRET` | Bootstrap secret for registering companion agents |
| `ADMIN_API_TOKEN` | Optional token for direct device command testing |
| `DEFAULT_WINDOWS_DEVICE` / `WINDOWS_DEVICE_ALIASES` | Optional Windows device resolution hints |

## Development

- Run tests/lint: `make test`, `make lint` (uses the `jarvis-dev` Docker image).
- The repository lives on a Windows UNC share, so the dev container does **not** bind-mount
  the repo; rebuild images after changing code (`docker compose build`).
- On the Debian server, uncomment the `volumes: ["./:/app"]` bind mount in
  `docker-compose.yml` under `jarvis-api` for live code iteration.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/INSTALLATION.md`](docs/INSTALLATION.md)
- [`docs/DEVICE_PROTOCOL.md`](docs/DEVICE_PROTOCOL.md)
- [`docs/WINDOWS_AGENT.md`](docs/WINDOWS_AGENT.md)
- [`docs/VOICE.md`](docs/VOICE.md)
- [`docs/ANDROID_AGENT.md`](docs/ANDROID_AGENT.md) *(Phase 9)*
- [`docs/SECURITY.md`](docs/SECURITY.md)
- [`docs/TOOLS.md`](docs/TOOLS.md)
- [`docs/MEMORY.md`](docs/MEMORY.md) *(Phase 6)*
- [`docs/MIGRATION.md`](docs/MIGRATION.md)
- [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)

## License

MIT — original project by GauravSingh9356; preserved under `legacy/`.
