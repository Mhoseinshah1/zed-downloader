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
    REDIS_URL: str

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

    # Misc
    DOMAIN: str = ""
    CORS_ORIGINS: str = "*"

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
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

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
    """Semver from the repo-root VERSION file, with fallbacks for containers
    where the file is outside the build context."""
    candidates = [
        Path(__file__).resolve().parents[3] / "VERSION",  # repo checkout
        Path("/app/VERSION"),  # docker image, if copied
    ]
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.read_text().strip()
        except OSError:
            continue
    return os.environ.get("APP_VERSION", "1.0.0")
