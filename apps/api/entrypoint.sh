#!/bin/sh
# Container entrypoint. Role argument: "api" | "worker" | anything else = exec verbatim.
set -e

ROLE="${1:-api}"

echo "[entrypoint] role=$ROLE — waiting for database..."
python - <<'PY'
import asyncio
import sys

from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings


async def wait() -> int:
    engine = create_async_engine(get_settings().DATABASE_URL)
    for attempt in range(60):
        try:
            async with engine.connect():
                pass
            await engine.dispose()
            print("[entrypoint] database is ready")
            return 0
        except Exception as exc:
            print(f"[entrypoint] db not ready (attempt {attempt + 1}/60): {type(exc).__name__}")
            await asyncio.sleep(2)
    return 1


sys.exit(asyncio.run(wait()))
PY

case "$ROLE" in
  api)
    echo "[entrypoint] applying migrations..."
    alembic upgrade head
    echo "[entrypoint] seeding..."
    python -m app.seed
    echo "[entrypoint] starting uvicorn..."
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
    ;;
  worker)
    echo "[entrypoint] starting download worker..."
    exec python -m app.workers.runner
    ;;
  *)
    exec "$@"
    ;;
esac
