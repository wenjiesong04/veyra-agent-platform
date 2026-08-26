"""Configuration for the separate Community service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Self
from urllib.parse import urlsplit

from platformdirs import user_data_dir
from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

EnvironmentMode = Literal["development", "test", "production"]
_DEVELOPMENT_AUTH_HMAC_SECRET = "development-only-auth-secret-replace-before-production"


def _default_database_url() -> str:
    data_root = (
        Path(user_data_dir("Veyra Agent Platform", appauthor=False))
        / "v1"
        / "community"
    )
    return f"sqlite:///{data_root / 'app.sqlite3'}"


def _default_avatar_storage_root() -> Path:
    return (
        Path(user_data_dir("Veyra Agent Platform", appauthor=False))
        / "v1"
        / "community"
        / "avatars"
    )


class CommunitySettings(BaseSettings):
    """Environment-backed settings for the Community service."""

    model_config = SettingsConfigDict(
        env_prefix="VEYRA_COMMUNITY_",
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
    avatar_storage_root: Path = Field(default_factory=_default_avatar_storage_root)
    mode: EnvironmentMode = Field(
        default="development",
        validation_alias=AliasChoices(
            "VEYRA_COMMUNITY_MODE",
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
    auth_hmac_secret: SecretStr = Field(
        default=SecretStr(_DEVELOPMENT_AUTH_HMAC_SECRET),
        validation_alias=AliasChoices(
            "VEYRA_AUTH_HMAC_SECRET",
            "VEYRA_AUTH_SESSION_SECRET",
            "VEYRA_AUTH_SIGNING_KEY",
        ),
    )
    session_ttl_minutes: int = Field(default=15, ge=5, le=60)
    refresh_ttl_days: int = Field(default=30, ge=1, le=90)
    public_origin: str | None = Field(
        default=None,
        validation_alias=AliasChoices("VEYRA_COMMUNITY_ORIGIN", "VEYRA_PUBLIC_ORIGIN"),
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
        if self.mode == "production":
            if not self.database_url.lower().startswith("postgresql+psycopg://"):
                raise ValueError(
                    "production Community mode requires a postgresql+psycopg:// URL"
                )
            if self.build_sha.strip().lower() in {"", "unknown"}:
                raise ValueError(
                    "production Community mode requires a concrete VEYRA_BUILD_SHA"
                )
            if (
                self.auth_hmac_secret.get_secret_value()
                == _DEVELOPMENT_AUTH_HMAC_SECRET
            ):
                raise ValueError(
                    "production Community mode requires VEYRA_AUTH_HMAC_SECRET"
                )
            if self.public_origin is None:
                raise ValueError(
                    "production Community mode requires VEYRA_COMMUNITY_ORIGIN"
                )
        if len(self.auth_hmac_secret.get_secret_value().encode("utf-8")) < 32:
            raise ValueError("auth HMAC secret must contain at least 32 bytes")
        return self

    @field_validator("public_origin")
    @classmethod
    def _normalize_public_origin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("public origin must be an http(s) origin without a path")
        return f"{parsed.scheme}://{parsed.netloc}"

    @property
    def environment(self) -> EnvironmentMode:
        """Expose the mode under the deployment-oriented name as well."""

        return self.mode

    @property
    def secure_cookies(self) -> bool:
        """Use Secure cookies outside local development and test environments."""

        return self.mode == "production"
