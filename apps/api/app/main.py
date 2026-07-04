"""FastAPI application: CORS, routers, /health (liveness) + /ready (readiness)."""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings, get_version
from app.database import engine
from app.routes import (
    admin_catalog,
    admin_content,
    admin_downloads,
    admin_settings,
    admin_users,
    auth,
    dashboard,
    internal,
    payments,
)

log = logging.getLogger("zed.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: best-effort temp dir. Must never block the app from serving
    # /health — liveness is deliberately independent of everything external.
    try:
        os.makedirs(get_settings().TEMP_DIR, exist_ok=True)
    except OSError as exc:
        log.warning("could not create temp dir: %s", exc)
    yield


app = FastAPI(title="Zed Downloader API", version=get_version(), lifespan=lifespan)

_settings = get_settings()
# Restrictive by default: only the origins explicitly listed in CORS_ORIGINS
# are allowed. An empty list means no cross-origin access (the panel is served
# same-origin through Caddy in production). Credentials are only permitted
# with an explicit origin allow-list (never with "*").
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins_list,
    allow_credentials=_settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(internal.router)
app.include_router(dashboard.router)
app.include_router(admin_users.router)
app.include_router(admin_catalog.router)
app.include_router(admin_content.router)
app.include_router(admin_downloads.router)
app.include_router(admin_settings.router)
app.include_router(payments.admin_router)
app.include_router(payments.public_router)


@app.get("/health", tags=["misc"])
async def health() -> dict:
    """Liveness. Deliberately depends on NOTHING external (no DB, no Redis) so
    the container reports healthy as soon as the app is up — used by the Docker
    healthcheck and the installer's readiness probe."""
    return {"status": "ok", "version": get_version()}


@app.get("/ready", tags=["misc"])
async def ready() -> JSONResponse:
    """Readiness. Checks the database is reachable. Returns 503 when not, so it
    can gate real traffic without affecting the liveness/health signal."""
    database = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        log.warning("readiness DB check failed: %s", exc)
        database = "error"
    ok = database == "ok"
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ready" if ok else "not_ready", "database": database, "version": get_version()},
    )
