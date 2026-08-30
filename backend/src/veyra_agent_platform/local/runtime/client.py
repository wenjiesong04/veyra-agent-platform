"""OpenAI-compatible Runtime model client with an injectable transport."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .config import RuntimeSettings


class RuntimeProviderError(RuntimeError):
    """A safe, user-visible provider failure without credentials or raw bodies."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RuntimeProviderNotConfigured(RuntimeProviderError):
    def __init__(self) -> None:
        super().__init__(
            "runtime_not_configured",
            "Runtime model provider is not configured",
        )


@dataclass(frozen=True)
class RuntimeCompletion:
    content: str
    finish_reason: str | None


class RuntimeModelTransport(Protocol):
    def models(self) -> Sequence[str]: ...

    def complete(self, messages: Sequence[Mapping[str, Any]]) -> RuntimeCompletion: ...


class HttpRuntimeTransport:
    """Call the provider HTTP API without loading a Project .env file."""

    def __init__(
        self,
        settings: RuntimeSettings,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        api_key = os.environ.get(settings.model_api_key_env, "").strip()
        if http_client is None and not api_key:
            raise RuntimeProviderNotConfigured()
        self._client = http_client or httpx.Client(
            base_url=settings.model_base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=settings.timeout_seconds,
        )

    def models(self) -> Sequence[str]:
        try:
            response = self._client.get("/models")
        except httpx.TimeoutException as exc:
            raise RuntimeProviderError(
                "runtime_timeout", "Runtime model request timed out"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeProviderError(
                "runtime_unavailable", "Runtime model service is unavailable"
            ) from exc
        _raise_for_provider(response)
        try:
            payload = response.json()
            models = payload["data"]
            return tuple(
                item["id"]
                for item in models
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeProviderError(
                "runtime_invalid_response",
                "Runtime model service returned an invalid model list",
            ) from exc

    def complete(self, messages: Sequence[Mapping[str, Any]]) -> RuntimeCompletion:
        body: dict[str, Any] = {
            "model": self.settings.model_id,
            "messages": [dict(message) for message in messages],
            "reasoning_effort": self.settings.reasoning_effort,
            "max_completion_tokens": self.settings.max_completion_tokens,
        }
        try:
            response = self._client.post("/chat/completions", json=body)
        except httpx.TimeoutException as exc:
            raise RuntimeProviderError(
                "runtime_timeout", "Runtime model request timed out"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeProviderError(
                "runtime_unavailable", "Runtime model service is unavailable"
            ) from exc
        _raise_for_provider(response)
        try:
            payload = response.json()
            choice = payload["choices"][0]
            message = choice["message"]
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, str) or not content.strip():
                raise ValueError("missing assistant content")
            return RuntimeCompletion(
                content=content,
                finish_reason=choice.get("finish_reason")
                if isinstance(choice, dict)
                else None,
            )
        except (
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise RuntimeProviderError(
                "runtime_invalid_response",
                "Runtime model service returned an invalid completion",
            ) from exc


class RuntimeModelClient:
    """Host-side Runtime profile. Production must not use a shared process key."""

    def __init__(
        self,
        settings: RuntimeSettings,
        transport: RuntimeModelTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self._http: HttpRuntimeTransport | None = None
        self._model_checked = False

    @property
    def configured(self) -> bool:
        if self.transport is not None:
            return True
        if not self.settings.allow_process_environment_key:
            return False
        return bool(os.environ.get(self.settings.model_api_key_env, "").strip())

    def status(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "configured": self.configured,
            "model_id": self.settings.model_id,
            "model_base_url": self.settings.model_base_url,
            "model_api_key_env": self.settings.model_api_key_env,
            "reasoning_effort": self.settings.reasoning_effort,
            "allow_process_environment_key": (
                self.settings.allow_process_environment_key
            ),
            "user_provided_only": not self.settings.allow_process_environment_key,
        }

    def complete(self, messages: Sequence[Mapping[str, Any]]) -> RuntimeCompletion:
        if not self.configured:
            raise RuntimeProviderNotConfigured()
        transport = self._transport()
        if not self._model_checked:
            models = transport.models()
            if self.settings.model_id not in models:
                raise RuntimeProviderError(
                    "runtime_model_unavailable",
                    f"Configured Runtime model {self.settings.model_id} "
                    "is not available",
                )
            self._model_checked = True
        return transport.complete(messages)

    def _transport(self) -> RuntimeModelTransport:
        if self.transport is not None:
            return self.transport
        if self._http is None:
            self._http = HttpRuntimeTransport(self.settings)
        return self._http


def _raise_for_provider(response: httpx.Response) -> None:
    if response.is_success:
        return
    if response.status_code == 401:
        raise RuntimeProviderError(
            "runtime_unauthorized", "Runtime model credentials were rejected"
        )
    if response.status_code == 429:
        raise RuntimeProviderError(
            "runtime_rate_limited", "Runtime model service is rate limited"
        )
    if response.status_code >= 500:
        raise RuntimeProviderError(
            "runtime_provider_error", "Runtime model service failed"
        )
    raise RuntimeProviderError(
        "runtime_request_invalid", "Runtime model request was rejected"
    )
