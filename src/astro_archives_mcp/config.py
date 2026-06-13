from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STABLE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8000
    deployment: Literal["local", "adl", "tacc"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Slice-A: NoAuth only. BearerTokenProvider / OIDC arrive in later slices.
    auth_mode: Literal["none"] = "none"
    # Slice 5: async TAP family.
    tap_sync_timeout_seconds: float = 20.0
    job_ttl_seconds: int = 3600
    # Slice D: schema knowledge.
    schema_kb_staleness_days: int = 90
