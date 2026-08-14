FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install runtime dependencies first (stable build cache).
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY apps ./apps
COPY core ./core
COPY database ./database
COPY tests ./tests

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

RUN adduser --disabled-password --gecos "" jarvis

FROM base AS api
USER jarvis
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS dev
RUN pip install --no-cache-dir ".[dev]"
CMD ["pytest", "tests"]
