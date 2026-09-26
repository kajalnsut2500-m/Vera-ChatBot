from __future__ import annotations

import json
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VERA_", env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    model: str = "claude-sonnet-5"
    db_path: str = "./vera.db"
    team_name: str = "Team Vera"
    team_members: list[str] = ["Alice"]
    contact_email: str = "team@example.com"
    version: str = "1.0.0"
    log_level: str = "INFO"
    llm_timeout_seconds: int = 25

    @property
    def submitted_at(self) -> str:
        return "2026-09-26T00:00:00Z"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
