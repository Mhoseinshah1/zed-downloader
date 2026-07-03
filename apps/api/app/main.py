"""FastAPI application: CORS, routers, /health."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings, get_version
from app.routes import admin_catalog, admin_users, auth, dashboard, internal, payments

app = FastAPI(title="Zed Downloader API", version=get_version())

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    os.makedirs(get_settings().TEMP_DIR, exist_ok=True)


app.include_router(auth.router)
app.include_router(internal.router)
app.include_router(dashboard.router)
app.include_router(admin_users.router)
app.include_router(admin_catalog.router)
app.include_router(payments.admin_router)
app.include_router(payments.public_router)


@app.get("/health", tags=["misc"])
async def health() -> dict:
    return {"status": "ok", "version": get_version()}
