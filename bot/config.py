"""Centralized configuration. Loads from environment / .env file."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    bot_token: str
    bot_username: str = "WaifuGrabberBot"

    # Postgres
    database_url: str
    pg_pool_min: int = 10
    pg_pool_max: int = 30

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Webhook vs polling
    use_webhook: bool = False
    webhook_url: str = ""
    webhook_path: str = "/bot"
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8443

    # Game tuning
    spawn_msg_interval: int = 100
    spawn_time_floor: int = 300
    spawn_claim_window: int = 90
    guess_cooldown: int = 3
    trade_window: int = 60

    # Admin
    owner_id: int = 0

    # Logging
    log_level: str = "INFO"

    @property
    def webhook_secret(self) -> str:
        """Stable webhook secret derived from bot token."""
        import hashlib
        return hashlib.sha256(self.bot_token.encode()).hexdigest()[:32]


settings = Settings()  # type: ignore[call-arg]
