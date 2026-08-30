"""Process-environment configuration for the Factory model provider."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class FactorySettings(BaseSettings):
    """Keep Factory credentials separate from user Agent Runtime credentials."""

    model_config = SettingsConfigDict(
        env_prefix="VEYRA_FACTORY_",
        env_ignore_empty=True,
        populate_by_name=True,
        extra="ignore",
    )

    model_base_url: str = "https://api.moonshot.ai/v1"
    model_id: str = "kimi-k3"
    model_api_key_env: str = "MOONSHOT_API_KEY"
    reasoning_effort: Literal["low", "high", "max"] = "high"
    max_completion_tokens: int = Field(default=16_384, ge=1_024, le=65_536)
    timeout_seconds: float = Field(default=90.0, gt=0, le=300)
    repair_attempts: int = Field(default=3, ge=1, le=3)

    @field_validator("model_base_url")
    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Factory model base URL must be an HTTP(S) URL")
        if parsed.path.endswith("/chat/completions"):
            raise ValueError("Factory model base URL must stop at the API version")
        return normalized

    @field_validator("model_id", "model_api_key_env")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Factory model configuration must not be empty")
        return normalized
