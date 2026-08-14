# Development

## Environment

- Python 3.10+ (host dev), Python 3.12 (container).
- Package management: `pyproject.toml` (PEP 621). No `requirements.txt`.
- The project installs as **metadata + dependencies only** (`[tool.setuptools] packages = []`);
  source packages (`apps`, `core`, `database`, …) are imported from the repo root via
  `PYTHONPATH=/app` inside containers.

## Day-to-Day Loop (Docker)

Because the repo often lives on a UNC share (no bind mounts), code is baked into images:

```bash
docker compose build jarvis-dev jarvis-api   # after any code change
docker compose run --rm jarvis-dev pytest    # run tests
docker compose run --rm jarvis-dev ruff check apps core database tests
docker compose up -d --build jarvis-api      # run the API
```

On Linux hosts, uncomment the `./:/app` bind mount to skip rebuilds.

## Adding a migration

1. Edit `database/models.py`.
2. Generate: `docker compose run --rm jarvis-dev alembic -c database/alembic.ini revision --autogenerate -m "<name>"`
3. **On UNC hosts:** the file is generated inside the container, not on disk. Retrieve it
   with `docker cp`, or generate inside a `--no-rm` run container.
4. Review the generated file; then `docker compose exec -u root jarvis-api alembic -c database/alembic.ini upgrade head`.
5. Verify no drift: `docker compose exec -u root jarvis-api alembic -c database/alembic.ini check`.

## Quality gates (every phase)

- `pytest` green
- `ruff check apps core database tests` clean
- `alembic check` reports no drift
- `docker compose up -d` healthy, `/api/health/ready` = `ready`
- docs updated; secrets never committed

## Conventions

- Type hints everywhere; async where I/O is involved.
- No giant files/classes; domain logic separate from transport (API routers).
- Interfaces for external providers (LLM, STT, TTS, device agents).
- No global mutable business state; connection pools/engines excepted.
- Every significant action is auditable (`audit_logs` + structured logs).
- No silent exception swallowing; translate failures into user-friendly responses.
