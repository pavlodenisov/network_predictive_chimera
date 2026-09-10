"""Single environment read-point (spec §39). Nothing else reads ``os.environ``."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """Accept the scheme-only URLs that hosted Postgres providers hand out
    (``postgres://…`` / ``postgresql://…``) and pin our driver (``+psycopg``).
    SQLite and already-qualified URLs pass through untouched."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Settings(BaseSettings):
    """Runtime configuration, sourced from environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    # --- database -------------------------------------------------------------
    database_url: str = Field(
        "sqlite+pysqlite:///./chimera.db",
        alias="DATABASE_URL",
        description="SQLAlchemy URL. SQLite by default; postgresql+psycopg://… for production.",
    )
    sql_echo: bool = Field(False, alias="CHIMERA_SQL_ECHO")

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        return normalize_database_url(v)

    # --- api ---------------------------------------------------------------
    api_host: str = Field("127.0.0.1", alias="CHIMERA_API_HOST")
    api_port: int = Field(8000, alias="CHIMERA_API_PORT")
    cors_origins: str = Field("http://localhost:3000", alias="CHIMERA_CORS_ORIGINS")
    dev_user: str = Field("analyst@chimera.local", alias="CHIMERA_DEV_USER")

    # --- llm extraction (optional) --------------------------------------------
    anthropic_api_key: str | None = Field(None, alias="ANTHROPIC_API_KEY")
    extractor: str = Field("rules", alias="CHIMERA_EXTRACTOR")  # rules | claude
    claude_model: str = Field("claude-sonnet-5", alias="CHIMERA_CLAUDE_MODEL")
    extraction_prompt_version: str = Field(
        "extract_v0.1", alias="CHIMERA_EXTRACTION_PROMPT_VERSION"
    )

    # --- pipeline / run metadata -------------------------------------------
    code_version: str = Field(
        "dev",
        validation_alias=AliasChoices("CHIMERA_CODE_VERSION", "RENDER_GIT_COMMIT", "SOURCE_COMMIT"),
    )
    config_dir: Path = Field(Path("./configs"), alias="CHIMERA_CONFIG_DIR")
    seeds_dir: Path = Field(Path("./db/seeds"), alias="CHIMERA_SEEDS_DIR")

    # --- observability ---------------------------------------------------
    log_level: str = Field("INFO", alias="CHIMERA_LOG_LEVEL")
    log_format: str = Field("console", alias="CHIMERA_LOG_FORMAT")  # console | json

    # --- news --------------------------------------------------------------
    rss_live: bool = Field(False, alias="CHIMERA_RSS_LIVE")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def llm_extraction_available(self) -> bool:
        return self.extractor == "claude" and bool(self.anthropic_api_key)

    @property
    def models_dir(self) -> Path:
        return self.config_dir / "models"

    @property
    def discovery_dir(self) -> Path:
        return self.config_dir / "discovery"

    @property
    def actions_dir(self) -> Path:
        return self.config_dir / "actions"

    @property
    def thesis_dir(self) -> Path:
        return self.config_dir / "thesis"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    """Clear the cache (used by tests that mutate the environment)."""
    get_settings.cache_clear()
    return get_settings()
