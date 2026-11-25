"""App settings, read from environment variables (see .env.example)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MONICOMM_", env_file=".env", extra="ignore")

    env: str = "prod"  # dev must be set explicitly (it unlocks the dev-only options below)
    demo_data: bool = False  # dashboard demo data, works only with env=dev
    database_url: str = "postgresql://monicomm:monicomm@db:5432/monicomm"
    redis_url: str = "redis://queue:6379/0"
    llm_base_url: str = "http://llm:11434"
    llm_model: str = "qwen2.5:7b"
    # "ollama" = local, the only option on the closed network; "gemini" = dev-only (env=dev)
    llm_provider: str = "ollama"
    gemini_api_key: str = ""  # local .env only, never in git
    gemini_model: str = "gemini-2.5-flash"


@lru_cache
def get_settings() -> Settings:
    return Settings()
