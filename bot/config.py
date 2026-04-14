from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Required
    telegram_bot_token: str

    # Access control — empty list disables the check (all users allowed)
    allowed_user_ids: list[int] = []

    # Webhook mode when set; polling fallback when absent
    webhook_url: str | None = None
    webhook_secret: str | None = None

    # LLM (optional — bot works without these)
    openai_api_key: str | None = None
    ollama_base_url: str | None = None

    # Storage
    data_dir: Path = Path("/data")

    # Embedding + clustering
    embedding_model: str = "all-MiniLM-L6-v2"
    dbscan_epsilon: float = 0.3
    dbscan_min_samples: int = 2

    # Scheduling
    scheduler_timezone: str = "UTC"

    # Per-user defaults (overridable via /settings)
    cooldown_days: int = 14

    # Logging
    log_level: str = "INFO"

    @property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.data_dir}/wdwgn.db"

    @property
    def db_url_sync(self) -> str:
        """Synchronous SQLite URL for APScheduler SQLAlchemyJobStore."""
        return f"sqlite:///{self.data_dir}/wdwgn.db"

    @property
    def chroma_path(self) -> Path:
        return self.data_dir / "chroma"
