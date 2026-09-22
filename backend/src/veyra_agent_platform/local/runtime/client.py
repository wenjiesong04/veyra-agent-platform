"""OpenAI-compatible Runtime model client with an injectable transport."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from veyra_agent_platform.local.secrets import (
    MODEL_SECRET_REF,
    SecretStore,
    resolve_secret,
)

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


class RuntimeModelStreamingTransport(Protocol):
    def stream(self, messages: Sequence[Mapping[str, Any]]) -> Iterator[str]: ...


class HttpRuntimeTransport:
    """Call the provider HTTP API without loading a Project .env file."""

    def __init__(
        self,
        settings: RuntimeSettings,
        *,
        http_client: httpx.Client | None = None,
        secret_store: SecretStore | None = None,
        secret_ref: str = MODEL_SECRET_REF,
    ) -> None:
        self.settings = settings
        api_key = resolve_secret(
            secret_store,
            secret_ref,
            settings.model_api_key_env,
            allow_environment=settings.allow_process_environment_key,
        )
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
        _assert_provider_safe_messages(messages)
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

    def stream(self, messages: Sequence[Mapping[str, Any]]) -> Iterator[str]:
        """Yield assistant deltas when the provider supports streaming."""
        body: dict[str, Any] = {
            "model": self.settings.model_id,
            "messages": [dict(message) for message in messages],
            "reasoning_effort": self.settings.reasoning_effort,
            "max_completion_tokens": self.settings.max_completion_tokens,
            "stream": True,
        }
        _assert_provider_safe_messages(messages)
        try:
            with self._client.stream(
                "POST", "/chat/completions", json=body
            ) as response:
                _raise_for_provider(response)
                emitted = False
                for line in response.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    try:
                        payload = json.loads(data)
                        choice = payload["choices"][0]
                        delta = choice.get("delta", {})
                        content = (
                            delta.get("content") if isinstance(delta, dict) else None
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
                            "Runtime model service returned an invalid stream",
                        ) from exc
                    if isinstance(content, str) and content:
                        emitted = True
                        yield content
                if not emitted:
                    raise RuntimeProviderError(
                        "runtime_invalid_response",
                        "Runtime model service returned an empty stream",
                    )
        except httpx.TimeoutException as exc:
            raise RuntimeProviderError(
                "runtime_timeout", "Runtime model request timed out"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeProviderError(
                "runtime_unavailable", "Runtime model service is unavailable"
            ) from exc


class RuntimeModelClient:
    """Host-side Runtime profile. Production must not use a shared process key."""

    def __init__(
        self,
        settings: RuntimeSettings,
        transport: RuntimeModelTransport | None = None,
        *,
        secret_store: SecretStore | None = None,
        secret_ref: str = MODEL_SECRET_REF,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self._secret_store = secret_store
        self._secret_ref = secret_ref
        self._http: HttpRuntimeTransport | None = None
        self._model_checked = False

    @property
    def configured(self) -> bool:
        if self.transport is not None:
            return True
        return bool(
            resolve_secret(
                self._secret_store,
                self._secret_ref,
                self.settings.model_api_key_env,
                allow_environment=self.settings.allow_process_environment_key,
            )
        )

    @property
    def secret_store(self) -> SecretStore | None:
        return self._secret_store

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
        self._ensure_model(transport)
        return transport.complete(messages)

    def stream(self, messages: Sequence[Mapping[str, Any]]) -> Iterator[str]:
        if not self.configured:
            raise RuntimeProviderNotConfigured()
        transport = self._transport()
        self._ensure_model(transport)
        stream = getattr(transport, "stream", None)
        if callable(stream):
            yield from stream(messages)
            return
        yield transport.complete(messages).content

    def validate(self) -> None:
        """Verify credentials and the model through the provider model list."""
        if not self.configured:
            raise RuntimeProviderNotConfigured()
        self._ensure_model(self._transport())

    def _ensure_model(self, transport: RuntimeModelTransport) -> None:
        if self._model_checked:
            return
        models = transport.models()
        if self.settings.model_id not in models:
            raise RuntimeProviderError(
                "runtime_model_unavailable",
                f"Configured Runtime model {self.settings.model_id} is not available",
            )
        self._model_checked = True

    def _transport(self) -> RuntimeModelTransport:
        if self.transport is not None:
            return self.transport
        if self._http is None:
            self._http = HttpRuntimeTransport(
                self.settings,
                secret_store=self._secret_store,
                secret_ref=self._secret_ref,
            )
        return self._http


def _assert_provider_safe_messages(messages: Sequence[Mapping[str, Any]]) -> None:
    """Reject host paths and internal artifact URLs at the HTTP boundary."""

    for message in messages:
        content = message.get("content")
        if isinstance(content, str) or not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, Mapping):
                continue
            image = part.get("image_url")
            url = ""
            if isinstance(image, str):
                url = image
            elif isinstance(image, Mapping):
                url = str(image.get("url") or "")
            if not url:
                continue
            lowered = url.casefold()
            if lowered.startswith(("file:", "artifact:")) or url.startswith("/"):
                raise RuntimeProviderError(
                    "runtime_request_invalid",
                    "Runtime model image parts cannot use host or artifact URLs",
                )


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
