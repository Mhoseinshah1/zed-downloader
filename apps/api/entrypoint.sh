#!/bin/sh
# Container entrypoint. Role argument: "api" | "worker" | anything else = exec verbatim.
#
# Design goals (learned the hard way from install failures):
#  - Never hang silently: distinguish "database not up yet" (retry) from
#    "database rejected us" (wrong password / missing DB / role) and fail FAST
#    with a loud, actionable message instead of spinning for 120s.
#  - Make migrate/seed failures obvious in `docker logs`, not invisible.
set -e

ROLE="${1:-api}"

echo "[entrypoint] role=$ROLE"

wait_for_db() {
    echo "[entrypoint] waiting for database..."
    python - <<'PY'
import asyncio
import sys

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

from app.config import get_settings

# Postgres SQLSTATEs that mean "the server answered and REJECTED us" — retrying
# will never help, so we fail fast with guidance instead of hanging.
FATAL_SQLSTATES = {
    "28P01": "invalid password for the database user",
    "28000": "invalid authorization (user/role rejected)",
    "3D000": "the target database does not exist",
    "42501": "insufficient privilege for the database user",
}
MAX_ATTEMPTS = 30      # ~60s of "not up yet" retries before giving up
RETRY_SLEEP = 2


def sqlstate_of(exc):
    cur = exc
    for _ in range(6):
        code = getattr(cur, "sqlstate", None)
        if code:
            return code
        cur = getattr(cur, "__cause__", None) or getattr(cur, "orig", None)
        if cur is None:
            break
    return None


async def wait() -> int:
    engine = create_async_engine(get_settings().DATABASE_URL)
    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                print("[entrypoint] database is ready")
                return 0
            except Exception as exc:  # noqa: BLE001
                code = sqlstate_of(exc)
                if code in FATAL_SQLSTATES:
                    print("")
                    print("=" * 72)
                    print(f"[entrypoint] FATAL: database rejected the connection ({code}: "
                          f"{FATAL_SQLSTATES[code]}).")
                    print("[entrypoint] This almost always means the Postgres data volume was")
                    print("[entrypoint] initialized with a DIFFERENT password than the current")
                    print("[entrypoint] .env (Postgres ignores POSTGRES_PASSWORD after first init).")
                    print("[entrypoint] Fix: reset the database volume, e.g.")
                    print("[entrypoint]     zed-downloader reset-db      (destroys DB data)")
                    print("[entrypoint]   or: docker compose ... down -v && ... up -d --build")
                    print("=" * 72)
                    return 3
                print(f"[entrypoint] db not ready (attempt {attempt}/{MAX_ATTEMPTS}: "
                      f"{type(exc).__name__}); retrying in {RETRY_SLEEP}s")
                await asyncio.sleep(RETRY_SLEEP)
        print("[entrypoint] FATAL: database did not become reachable in time.")
        return 1
    finally:
        await engine.dispose()


sys.exit(asyncio.run(wait()))
PY
}

case "$ROLE" in
  api)
    wait_for_db
    echo "[entrypoint] applying migrations (alembic upgrade head)..."
    if ! alembic upgrade head; then
        echo "[entrypoint] FATAL: alembic migration failed — see the traceback above." >&2
        exit 4
    fi
    echo "[entrypoint] seeding (idempotent)..."
    if ! python -m app.seed; then
        echo "[entrypoint] FATAL: seeding failed — see the traceback above." >&2
        exit 5
    fi
    echo "[entrypoint] starting uvicorn on 0.0.0.0:8000..."
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
    ;;
  worker)
    wait_for_db
    echo "[entrypoint] starting download worker..."
    exec python -m app.workers.runner
    ;;
  *)
    exec "$@"
    ;;
esac
