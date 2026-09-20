"""App configuration — the single source of env truth (Playbook 2.5)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://finsight:finsight@localhost:5432/finsight"
    redis_url: str = "redis://localhost:6379"

    llm_provider: str = "mock"  # gemini | openai | mock
    llm_model: str = "gemini-2.5-flash"
    gemini_api_key: str = ""
    openai_base_url: str = ""
    openai_api_key: str = ""

    embedding_provider: str = "mock"  # gemini | local | mock
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768

    confidence_review_threshold: float = 0.85
    llm_assist_max_confidence: float = 0.75
    copilot_top_k: int = 8
    rrf_k: int = 60
    chunk_target_tokens: int = 650
    chunk_overlap: float = 0.15

    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000"

    jwt_secret: str = "change-me-32-chars-minimum"
    access_token_minutes: int = 30
    rate_limit_default: str = "60/minute"
    rate_limit_copilot: str = "10/minute"
    rate_limit_exports: str = "5/minute"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
