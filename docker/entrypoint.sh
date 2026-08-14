#!/bin/sh
set -e

# Apply pending database migrations before serving traffic.
alembic -c database/alembic.ini upgrade head

exec "$@"
