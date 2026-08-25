"""Configuration for the local desktop service."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from platformdirs import user_data_dir
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_database_url() -> str:
    data_root = (
        Path(user_data_dir("Veyra Agent Platform", appauthor=False)) / "v1" / "local"
    )
    return f"sqlite+aiosqlite:///{data_root / 'app.sqlite3'}"


class LocalSettings(BaseSettings):
    """Environment-backed settings for the local service."""

    model_config = SettingsConfigDict(
        env_prefix="VEYRA_LOCAL_",
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    service_name: str = "local"
    host: str = "127.0.0.1"
    port: int = Field(default=8771, ge=1, le=65535)
    log_level: Literal["critical", "error", "warning", "info", "debug", "trace"] = (
        "info"
    )
    database_url: str = Field(default_factory=_default_database_url)
