"""Application configuration.

Single source of truth for every tunable. Values come from environment
variables (or a root .env file); see .env.example for documentation of
each field.
"""
import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    APP_NAME: str = "Zed Downloader"

    # Core connections
    DATABASE_URL: str
    # REDIS_URL may embed the password (redis://:PASS@redis:6379/0). Redis is
    # not exposed outside the compose network, and the installer additionally
    # sets a password (defense in depth).
    REDIS_URL: str
    REDIS_PASSWORD: str = ""

    # Security
    JWT_SECRET: str
    JWT_ACCESS_TTL_MINUTES: int = 30
    JWT_REFRESH_TTL_DAYS: int = 7
    ENCRYPTION_KEY: str | None = None
    # Doubles as the X-Internal-Secret value for bot -> api calls.
    TELEGRAM_WEBHOOK_SECRET: str = "change-me"

    # Telegram
    BOT_TOKEN: str = ""
    BOT_USERNAME: str = ""
    # Self-hosted telegram-bot-api server (e.g. http://telegram-api:8081).
    # Empty = the official api.telegram.org, which caps bot uploads at ~50 MB.
    TELEGRAM_API_URL: str = ""

    # Owner admin seeded on first start (see app/seed.py)
    OWNER_ADMIN_EMAIL: str = "admin@example.com"
    OWNER_ADMIN_PASSWORD: str = "change-me"
    OWNER_TELEGRAM_ID: int = 0

    # Download limits / behaviour
    MAX_FILE_SIZE_MB: int = 1900
    MAX_DURATION_SECONDS: int = 7200
    DOWNLOAD_TIMEOUT_SECONDS: int = 600
    FREE_DOWNLOADS_PER_DAY: int = 3
    TEMP_DIR: str = "/tmp/zed-downloads"

    # Payments
    ZARINPAL_MERCHANT_ID: str = ""
    ZARINPAL_SANDBOX: bool = True
    PAYMENT_CALLBACK_BASE_URL: str = ""

    # Rate limiting: per-identity download-request throttle (Redis-backed
    # sliding window). Applies independently to the telegram user and, in
    # groups, the chat.
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_MAX_REQUESTS: int = 5
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Reliable queue (Redis Streams): how many times a job may be reclaimed
    # after a worker died mid-processing before it is dead-lettered, and how
    # long a pending (unacked) entry must idle before another worker reclaims it.
    QUEUE_MAX_DELIVERIES: int = 3
    QUEUE_RECLAIM_IDLE_MS: int = 600_000  # 10 minutes

    # Ads: send a random weighted active ad around downloads.
    ADS_ENABLED: bool = True
    ADS_PLACEMENT: str = "after"  # before | after | both

    # Misc
    DOMAIN: str = ""
    # Comma-separated allowed origins for the admin panel. Default is
    # restrictive (same-origin only): production MUST set this to the panel's
    # public origin (the installer sets https://$DOMAIN). "*" is allowed only
    # as an explicit, deliberate opt-out — see cors_origins_list.
    CORS_ORIGINS: str = ""

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() in ("prod", "production")

    ENV: str = "production"

    # The official Bot API rejects bot uploads bigger than ~50 MB.
    OFFICIAL_BOT_API_UPLOAD_CAP_MB: int = 50

    @property
    def max_file_size_bytes(self) -> int:
        """Effective download size cap. Clamped to the official Bot API's
        upload limit unless a self-hosted TELEGRAM_API_URL is configured —
        otherwise files between 50 MB and MAX_FILE_SIZE_MB would be fully
        downloaded only to always fail at upload."""
        effective_mb = self.MAX_FILE_SIZE_MB
        if not self.TELEGRAM_API_URL:
            effective_mb = min(effective_mb, self.OFFICIAL_BOT_API_UPLOAD_CAP_MB)
        return effective_mb * 1024 * 1024

    @property
    def cors_origins_list(self) -> list[str]:
        """Explicit allowed origins. An empty setting means same-origin only
        (no cross-origin access) — NOT a wildcard. In production the panel is
        served from the same host via Caddy, so cross-origin access is not
        needed; a developer can set CORS_ORIGINS=http://localhost:5173 for the
        Vite dev server, or CORS_ORIGINS=* to deliberately allow any origin."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def cors_allow_credentials(self) -> bool:
        # The CORS spec forbids credentials with a "*" origin; browsers reject
        # it. Only allow credentials when origins are explicitly enumerated.
        return self.cors_origins_list != ["*"] and bool(self.cors_origins_list)

    @property
    def payment_callback_base(self) -> str:
        if self.PAYMENT_CALLBACK_BASE_URL:
            return self.PAYMENT_CALLBACK_BASE_URL.rstrip("/")
        return f"https://{self.DOMAIN}" if self.DOMAIN else ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_version() -> str:
    """Return the app version safely in BOTH a repo checkout and the Docker
    image. Never index parents[n] directly: in the image __file__ is
    /app/app/config.py, which only has three parents, so parents[3] raised
    IndexError and crashed app import (uvicorn never bound → /health 120s
    timeout). We iterate parents instead."""
    env_version = os.environ.get("APP_VERSION")
    if env_version:
        return env_version

    current = Path(__file__).resolve()
    candidates = [Path("/app/VERSION"), Path.cwd() / "VERSION"]
    candidates += [parent / "VERSION" for parent in current.parents]

    for candidate in candidates:
        try:
            if candidate.is_file():
                value = candidate.read_text(encoding="utf-8").strip()
                if value:
                    return value
        except OSError:
            continue

    return "1.0.0"
