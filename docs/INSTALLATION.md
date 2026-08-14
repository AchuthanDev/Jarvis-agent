# Installation

JARVIS targets a Debian home server via Docker Compose. This guide covers the server
installation. (A client/macOS dev note is included at the end.)

## Prerequisites

- Debian 12 (or equivalent Linux) with Docker Engine and the Compose plugin:

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
```

- `git`, `curl` (to verify health endpoints).

## 1. Get the code

```bash
git clone https://github.com/your-org/jarvis.git
cd jarvis
```

## 2. Configure

```bash
cp .env.example .env
nano .env
```

Required changes:

| Variable | Value |
|---|---|
| `POSTGRES_PASSWORD` | a strong random password |
| `JARVIS_SECRET_KEY` | a random string ≥ 32 chars |

Generate both with:

```bash
openssl rand -base64 32
```

Optional (later phases): `LLM_*`, `HOME_ASSISTANT_*`.

> **Never commit `.env`.** It is gitignored.

## 3. Start

```bash
docker compose up -d --build
```

The API container applies pending Alembic migrations on startup, then serves on
port `8000`.

## 4. Verify

```bash
curl http://localhost:8000/api/health/live
# {"status":"ok","app":"JARVIS","version":"0.1.0","environment":"dev"}

curl http://localhost:8000/api/health/ready
# {"status":"ready","checks":{"database":{"ok":true},"redis":{"ok":true}}}
```

OpenAPI docs: `http://<server-ip>:8000/docs`

## 5. Logs & maintenance

```bash
docker compose logs -f                 # follow logs
docker compose down                    # stop
docker compose down -v                 # stop AND delete data volumes (irreversible)
make migrate                           # apply migrations manually
```

## Upgrades

```bash
git pull
docker compose up -d --build
```

Migrations run automatically; schema changes are applied in order.

## Development machine (Windows/macOS)

The repository is developed on a Windows machine against a UNC network share, so Docker
bind mounts are unavailable there. In that environment:

- Rebuild images after code changes: `docker compose build jarvis-dev jarvis-api`
- Run tests: `docker compose run --rm jarvis-dev pytest`
- Run lint: `docker compose run --rm jarvis-dev ruff check apps core database tests`

On a Linux host (or any path Docker can bind-mount), uncomment the `volumes: ["./:/app"]`
entry under `jarvis-api` in `docker-compose.yml` for live code iteration, and you can
generate migrations directly with `make new-migration name="..."`
(running as the dev container's root user).
