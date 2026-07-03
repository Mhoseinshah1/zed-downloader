"""Bot settings loaded from environment variables (single root .env)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration for the bot process.

    Field names map case-insensitively to the canonical env var names
    (BOT_TOKEN, BOT_USERNAME, API_BASE_URL, TELEGRAM_WEBHOOK_SECRET,
    RUN_MODE, WEBHOOK_BASE_URL, WEBHOOK_PORT).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    bot_token: str = ""
    bot_username: str = ""
    api_base_url: str = "http://api:8000"
    # NOTE: TELEGRAM_WEBHOOK_SECRET doubles as the internal API secret
    # (sent as X-Internal-Secret) and as the Telegram webhook secret_token.
    telegram_webhook_secret: str = ""
    run_mode: str = "polling"  # "polling" | "webhook"
    webhook_base_url: str = ""
    webhook_port: int = 8080


@lru_cache
def get_settings() -> Settings:
    return Settings()
