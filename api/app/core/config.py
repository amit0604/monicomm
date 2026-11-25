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
    llm_timeout_s: float = 120.0
    pcap_data_dir: str = "/data/pcap"
    pcap_max_upload_mb: int = 500
    # "ollama" = local, the only option on the closed network; "gemini" = dev-only (env=dev)
    llm_provider: str = "ollama"
    gemini_api_key: str = ""  # local .env only, never in git
    gemini_model: str = "gemini-2.5-flash"
    llm_settings_file: str = ".env.llm.json"  # what the Admin page saved; dev login only
    # "none" = no login; "local" = users in users_file, works on the closed network
    auth_provider: str = "none"
    users_file: str = "/data/auth/users.json"
    cookie_secure: bool = False  # true when the UI is served over HTTPS
    investigator_ingest_dir: str = ""  # empty = listener off
    investigator_data_dir: str = "/data/investigator"
    investigator_window_s: int = 120
    investigator_poll_s: float = 5.0
    link_util_warn: float = 0.8  # link load warning (Analyzer, Investigator, Mapper); critical 1.0
    analyzer_data_dir: str = "/data/analyzer"
    investigator_ref_bw_mbps: float = 100000.0  # estimated link cost = ref_bw / ifHighSpeed


@lru_cache
def get_settings() -> Settings:
    return Settings()
