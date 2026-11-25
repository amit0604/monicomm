"""App settings, read from environment variables (see .env.example)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MONICOMM_", env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql://monicomm:monicomm@db:5432/monicomm"
    redis_url: str = "redis://queue:6379/0"
    llm_base_url: str = "http://llm:11434"
    llm_model: str = "qwen2.5:7b"
    llm_timeout_s: float = 120.0
    pcap_data_dir: str = "/data/pcap"
    pcap_max_upload_mb: int = 500


@lru_cache
def get_settings() -> Settings:
    return Settings()
