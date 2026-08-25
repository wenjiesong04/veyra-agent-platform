"""Configuration for the separate Community service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Self

from platformdirs import user_data_dir
from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

EnvironmentMode = Literal["development", "test", "production"]


def _default_database_url() -> str:
    data_root = (
        Path(user_data_dir("Veyra Agent Platform", appauthor=False))
        / "v1"
        / "community"
    )
    return f"sqlite:///{data_root / 'app.sqlite3'}"


class CommunitySettings(BaseSettings):
    """Environment-backed settings for the Community service."""

    model_config = SettingsConfigDict(
        env_prefix="VEYRA_COMMUNITY_",
        env_file=".env",
        env_ignore_empty=True,
        populate_by_name=True,
        extra="ignore",
    )

    service_name: str = "community"
    host: str = "127.0.0.1"
    port: int = Field(default=8772, ge=1, le=65535)
    log_level: Literal["critical", "error", "warning", "info", "debug", "trace"] = (
        "info"
    )
    database_url: str = Field(default_factory=_default_database_url)
    mode: EnvironmentMode = Field(
        default="development",
        validation_alias=AliasChoices(
            "VEYRA_COMMUNITY_MODE",
            "VEYRA_COMMUNITY_ENVIRONMENT",
        ),
    )
    app_version: str = Field(
        default="0.1.0",
        validation_alias=AliasChoices(
            "VEYRA_APP_VERSION",
            "VEYRA_COMMUNITY_APP_VERSION",
        ),
    )
    build_sha: str = Field(
        default="unknown",
        validation_alias=AliasChoices(
            "VEYRA_BUILD_SHA",
            "VEYRA_COMMUNITY_BUILD_SHA",
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_environment_name(cls, values: Any) -> Any:
        if (
            isinstance(values, dict)
            and "environment" in values
            and "mode" not in values
        ):
            normalized = dict(values)
            normalized["mode"] = normalized.pop("environment")
            return normalized
        return values

    @model_validator(mode="after")
    def _validate_production_database(self) -> Self:
        if self.mode == "production" and not self.database_url.lower().startswith(
            ("postgresql://", "postgresql+psycopg://")
        ):
            raise ValueError(
                "production Community mode requires an explicit PostgreSQL URL"
            )
        return self

    @property
    def environment(self) -> EnvironmentMode:
        """Expose the mode under the deployment-oriented name as well."""

        return self.mode
