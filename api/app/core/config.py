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
    gemini_model: str = "gemini-3.5-flash-lite"  # 2.5-flash is deprecated (shutdown 2026-12-01)
    llm_settings_file: str = ".env.llm.json"  # what the Admin page saved; dev login only
    # "none" = no login; "local" = users in users_file, works on the closed network
    auth_provider: str = "none"
    users_file: str = "/data/auth/users.json"
    cookie_secure: bool = False  # true when the UI is served over HTTPS
    # Names under these domains count as inside the closed network (comma list, e.g. "corp.example")
    internal_domains: str = ""
    # LDAP / Active Directory login (read-only: search and bind). Empty URL = off.
    ldap_url: str = ""  # ldap://dc01.corp.example:389 or ldaps://dc01.corp.example:636
    ldap_start_tls: bool = False
    ldap_ca_file: str = ""  # PEM file of the internal CA, inside the container
    ldap_bind_dn: str = ""  # service account; empty = anonymous search
    ldap_bind_password: str = ""
    ldap_base_dn: str = ""
    ldap_user_filter: str = "(|(sAMAccountName={username})(uid={username}))"
    ldap_admin_group: str = ""  # group DN whose members are admins
    ldap_technician_group: str = ""
    ldap_default_role: str = "viewer"  # viewer, technician, or none (= members of the groups only)
    # SSO over OpenID Connect (on-prem AD FS, Keycloak...). Empty issuer = off.
    sso_issuer: str = ""
    sso_client_id: str = ""
    sso_client_secret: str = ""
    sso_scopes: str = "openid profile email"
    sso_groups_claim: str = "groups"
    sso_admin_group: str = ""
    sso_technician_group: str = ""
    sso_default_role: str = "viewer"
    sso_label: str = "SSO"
    sso_redirect_url: str = ""  # empty = <this server>/api/v1/auth/sso/callback
    sso_ca_file: str = ""
    # What the Admin page saved for LDAP and SSO, over the values above (secrets write-only)
    auth_settings_file: str = "/data/auth/auth-settings.json"
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
