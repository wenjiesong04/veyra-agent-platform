"""Process-environment configuration for the Runtime model provider."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeSettings(BaseSettings):
    """Keep Runtime credentials separate from Factory generation credentials."""

    model_config = SettingsConfigDict(
        env_prefix="VEYRA_RUNTIME_",
        env_ignore_empty=True,
        populate_by_name=True,
        extra="ignore",
    )

    provider_type: str = "openai_compatible"
    model_base_url: str = "https://api.moonshot.cn/v1"
    model_id: str = "kimi-k3"
    model_api_key_env: str = "MOONSHOT_API_KEY"
    reasoning_effort: Literal["low", "high", "max"] = "high"
    max_completion_tokens: int = Field(default=8_192, ge=256, le=65_536)
    timeout_seconds: float = Field(default=90.0, gt=0, le=300)
    allow_process_environment_key: bool = True

    @field_validator("model_base_url")
    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Runtime model base URL must be an HTTP(S) URL")
        if parsed.path.endswith("/chat/completions"):
            raise ValueError("Runtime model base URL must stop at the API version")
        return normalized

    @field_validator("provider_type", "model_id", "model_api_key_env")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Runtime model configuration must not be empty")
        return normalized
