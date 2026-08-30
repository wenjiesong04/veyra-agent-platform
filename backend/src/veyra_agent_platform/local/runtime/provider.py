"""Provider boundary for local Agent model nodes."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeProviderError(RuntimeError):
    """A safe provider failure that can be shown in Run evidence."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RuntimeProviderNotConfigured(RuntimeProviderError):
    def __init__(self) -> None:
        super().__init__(
            "runtime_provider_not_configured",
            "Configure an LLM API key before running an Agent model node",
        )


class RuntimeSettings(BaseSettings):
    """Runtime credentials are separate from the Factory provider settings."""

    model_config = SettingsConfigDict(
        env_prefix="VEYRA_RUNTIME_",
        env_ignore_empty=True,
        populate_by_name=True,
        extra="ignore",
    )

    model_base_url: str = "https://api.moonshot.ai/v1"
    model_id: str = "kimi-k3"
    model_api_key_env: str = "MOONSHOT_API_KEY"
    max_completion_tokens: int = Field(default=16_384, ge=1_024, le=65_536)
    timeout_seconds: float = Field(default=90.0, gt=0, le=300)

    @field_validator("model_base_url", "model_id", "model_api_key_env")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized:
            raise ValueError("Runtime model configuration must not be empty")
        return normalized


@dataclass(frozen=True)
class RuntimeCompletion:
    content: str


class RuntimeModelClient:
    """Call one configured OpenAI-compatible model without persisting secrets."""

    def __init__(self, settings: RuntimeSettings | None = None) -> None:
        self.settings = settings or RuntimeSettings()

    @property
    def configured(self) -> bool:
        return bool(os.environ.get(self.settings.model_api_key_env, "").strip())

    def complete(
        self,
        *,
        model_ref: str,
        system_prompt: str,
        values: dict[str, Any],
    ) -> RuntimeCompletion:
        api_key = os.environ.get(self.settings.model_api_key_env, "").strip()
        if not api_key:
            raise RuntimeProviderNotConfigured()
        model = self.settings.model_id if model_ref == "model.primary" else model_ref
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(values, ensure_ascii=False, sort_keys=True),
                },
            ],
            "max_completion_tokens": self.settings.max_completion_tokens,
        }
        try:
            response = httpx.post(
                f"{self.settings.model_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=body,
                timeout=self.settings.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise RuntimeProviderError(
                "runtime_timeout", "Agent model request timed out"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeProviderError(
                "runtime_provider_unavailable", "Agent model service is unavailable"
            ) from exc
        if response.status_code == 401:
            raise RuntimeProviderError(
                "runtime_provider_unauthorized", "Agent model credentials were rejected"
            )
        if response.status_code == 429:
            raise RuntimeProviderError(
                "runtime_rate_limited", "Agent model service is rate limited"
            )
        if response.status_code >= 500:
            raise RuntimeProviderError(
                "runtime_provider_error", "Agent model service failed"
            )
        if not response.is_success:
            raise RuntimeProviderError(
                "runtime_request_invalid", "Agent model request was rejected"
            )
        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except (
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise RuntimeProviderError(
                "runtime_invalid_response", "Agent model returned an invalid response"
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeProviderError(
                "runtime_invalid_response", "Agent model returned an empty response"
            )
        return RuntimeCompletion(content=content.strip())
