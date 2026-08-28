"""Configuration for the local desktop service."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

from platformdirs import user_data_dir
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LocalEnvironmentMode = Literal["development", "test", "production", "release"]


def _default_database_url() -> str:
    data_root = (
        Path(user_data_dir("Veyra Agent Platform", appauthor=False)) / "v1" / "local"
    )
    return f"sqlite+aiosqlite:///{data_root / 'app.sqlite3'}"


def _default_project_storage_root() -> Path:
    """Return the application-managed root for newly created Projects."""
    return (
        Path(user_data_dir("Veyra Agent Platform", appauthor=False)) / "v1" / "projects"
    )


class LocalSettings(BaseSettings):
    """Environment-backed settings for the local service."""

    model_config = SettingsConfigDict(
        env_prefix="VEYRA_LOCAL_",
        env_ignore_empty=True,
        populate_by_name=True,
        extra="ignore",
    )

    service_name: str = "local"
    host: str = "127.0.0.1"
    port: int = Field(default=8771, ge=1, le=65535)
    log_level: Literal["critical", "error", "warning", "info", "debug", "trace"] = (
        "info"
    )
    database_url: str = Field(default_factory=_default_database_url)
    project_storage_root: Path = Field(default_factory=_default_project_storage_root)
    mode: LocalEnvironmentMode = Field(
        default="development",
        validation_alias=AliasChoices(
            "VEYRA_LOCAL_MODE",
            "VEYRA_ENVIRONMENT",
            "mode",
        ),
    )
    app_version: str = Field(
        default="0.1.0",
        validation_alias=AliasChoices("VEYRA_APP_VERSION", "app_version"),
    )
    build_sha: str = Field(
        default="unknown",
        validation_alias=AliasChoices("VEYRA_BUILD_SHA", "build_sha"),
    )
    model_base_url: str | None = None
    model_api_key: str | None = None

    @field_validator("host")
    @classmethod
    def _validate_loopback_host(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("local service host must be 127.0.0.1, ::1, or localhost")
        return normalized

    @model_validator(mode="after")
    def _validate_release_build_identity(self) -> Self:
        if self.mode in {
            "production",
            "release",
        } and self.build_sha.strip().lower() in {
            "",
            "unknown",
        }:
            raise ValueError(
                "local production/release mode requires a concrete VEYRA_BUILD_SHA"
            )
        return self

    @property
    def environment(self) -> LocalEnvironmentMode:
        """Expose the mode under the deployment-oriented name as well."""

        return self.mode
