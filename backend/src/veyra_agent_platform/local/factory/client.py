"""Small OpenAI-compatible Kimi K3 client with an injectable transport."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from veyra_agent_platform.local.secrets import (
    MODEL_SECRET_REF,
    SecretStore,
    resolve_secret,
)

from .config import FactorySettings


class FactoryProviderError(RuntimeError):
    """A safe, user-visible provider failure without credentials or raw bodies."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class FactoryProviderNotConfigured(FactoryProviderError):
    def __init__(self) -> None:
        super().__init__(
            "factory_provider_not_configured",
            "Factory model provider is not configured",
        )


@dataclass(frozen=True)
class KimiCompletion:
    """Only final content is persisted; assistant_message is chain-local."""

    content: str
    assistant_message: dict[str, Any]
    finish_reason: str | None


class KimiTransport(Protocol):
    def models(self) -> Sequence[str]: ...

    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        response_format: Mapping[str, Any] | None = None,
    ) -> KimiCompletion: ...


class HttpKimiTransport:
    """Use the provider's HTTP API without loading a Project .env file."""

    def __init__(
        self,
        settings: FactorySettings,
        *,
        http_client: httpx.Client | None = None,
        secret_store: SecretStore | None = None,
        secret_ref: str = MODEL_SECRET_REF,
    ) -> None:
        self.settings = settings
        api_key = resolve_secret(secret_store, secret_ref, settings.model_api_key_env)
        if http_client is None and not api_key:
            raise FactoryProviderNotConfigured()
        self._client = http_client or httpx.Client(
            base_url=settings.model_base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=settings.timeout_seconds,
        )

    def models(self) -> Sequence[str]:
        try:
            response = self._client.get("/models")
        except httpx.TimeoutException as exc:
            raise FactoryProviderError(
                "factory_timeout", "Factory model request timed out"
            ) from exc
        except httpx.HTTPError as exc:
            raise FactoryProviderError(
                "factory_unavailable", "Factory model service is unavailable"
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
            raise FactoryProviderError(
                "factory_invalid_response",
                "Factory model service returned an invalid model list",
            ) from exc

    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        response_format: Mapping[str, Any] | None = None,
    ) -> KimiCompletion:
        body: dict[str, Any] = {
            "model": self.settings.model_id,
            "messages": [dict(message) for message in messages],
            "reasoning_effort": self.settings.reasoning_effort,
            "max_completion_tokens": self.settings.max_completion_tokens,
        }
        if response_format is not None:
            body["response_format"] = dict(response_format)
        try:
            response = self._client.post("/chat/completions", json=body)
        except httpx.TimeoutException as exc:
            raise FactoryProviderError(
                "factory_timeout", "Factory model request timed out"
            ) from exc
        except httpx.HTTPError as exc:
            raise FactoryProviderError(
                "factory_unavailable", "Factory model service is unavailable"
            ) from exc
        _raise_for_provider(response)
        try:
            payload = response.json()
            choice = payload["choices"][0]
            message = choice["message"]
            content = message.get("content")
            if (
                not isinstance(message, dict)
                or not isinstance(content, str)
                or not content.strip()
            ):
                raise ValueError("missing assistant content")
            return KimiCompletion(
                content=content,
                assistant_message=dict(message),
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
            raise FactoryProviderError(
                "factory_invalid_response",
                "Factory model service returned an invalid completion",
            ) from exc


class KimiClient:
    """Discover a configured model before each generation chain."""

    def __init__(
        self,
        settings: FactorySettings,
        transport: KimiTransport | None = None,
        *,
        secret_store: SecretStore | None = None,
        secret_ref: str = MODEL_SECRET_REF,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self._secret_store = secret_store
        self._secret_ref = secret_ref
        self._http: HttpKimiTransport | None = None

    @property
    def configured(self) -> bool:
        return self.transport is not None or bool(
            resolve_secret(
                self._secret_store,
                self._secret_ref,
                self.settings.model_api_key_env,
            )
        )

    def _transport(self) -> KimiTransport:
        if self.transport is not None:
            return self.transport
        if self._http is None:
            self._http = HttpKimiTransport(
                self.settings,
                secret_store=self._secret_store,
                secret_ref=self._secret_ref,
            )
        return self._http

    def ensure_model(self) -> None:
        models = self._transport().models()
        if self.settings.model_id not in models:
            raise FactoryProviderError(
                "factory_model_unavailable",
                f"Configured Factory model {self.settings.model_id} is not available",
            )

    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        response_format: Mapping[str, Any] | None = None,
    ) -> KimiCompletion:
        return self._transport().complete(messages, response_format=response_format)


def _raise_for_provider(response: httpx.Response) -> None:
    if response.is_success:
        return
    if response.status_code == 401:
        raise FactoryProviderError(
            "factory_unauthorized", "Factory model credentials were rejected"
        )
    if response.status_code == 429:
        raise FactoryProviderError(
            "factory_rate_limited", "Factory model service is rate limited"
        )
    if response.status_code >= 500:
        raise FactoryProviderError(
            "factory_provider_error", "Factory model service failed"
        )
    raise FactoryProviderError(
        "factory_request_invalid", "Factory model request was rejected"
    )
