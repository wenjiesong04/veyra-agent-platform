"""Small OpenAI-compatible Kimi K3 client with an injectable transport."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from veyra_agent_platform.local.secrets import (
    MODEL_SECRET_REF,
    SecretStore,
    resolve_secret,
)

from .capability_profile import (
    ProviderCapabilityProfile,
    derive_provider_capability_profile,
)
from .config import FactorySettings

logger = logging.getLogger(__name__)
_REDACT = re.compile(r"(?i)(bearer\s+\S+|sk-[A-Za-z0-9._-]+|moonshot-[A-Za-z0-9._-]+)")
_ERROR_PATH = re.compile(r"At path '([^']{1,200})'")
_DEFAULT_READ_TIMEOUT = object()
_CONNECT_TIMEOUT_SECONDS = 20.0


def visible_json_field(payload: str, key: str) -> str:
    """Return the current text of a JSON string field, including a partial value."""

    marker = f'"{key}"'
    start = payload.find(marker)
    if start < 0:
        return ""
    colon = payload.find(":", start + len(marker))
    if colon < 0:
        return ""
    index = colon + 1
    while index < len(payload) and payload[index] in " \n\r\t":
        index += 1
    if index >= len(payload) or payload[index] != '"':
        return ""
    index += 1
    chars: list[str] = []
    while index < len(payload):
        char = payload[index]
        if char == "\\":
            if index + 1 >= len(payload):
                break
            escaped = payload[index + 1]
            chars.append(
                {
                    "n": "\n",
                    "t": "\t",
                    "r": "\r",
                    '"': '"',
                    "\\": "\\",
                    "/": "/",
                }.get(escaped, escaped)
            )
            index += 2
            continue
        if char == '"':
            break
        chars.append(char)
        index += 1
    return "".join(chars)


def completion_timeout(read_seconds: float | None) -> httpx.Timeout:
    """Bound connection setup. A missing read limit waits for the model reply."""

    connect = _CONNECT_TIMEOUT_SECONDS
    if read_seconds is None:
        return httpx.Timeout(connect=connect, read=None, write=None, pool=connect)
    bounded = max(read_seconds, connect)
    return httpx.Timeout(bounded)


class FactoryProviderError(RuntimeError):
    """A safe, user-visible provider failure without credentials or raw bodies."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


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
    request_id: str | None = None


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
        """List visible model ids. Listing is not a capability proof."""

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
        read_timeout: float | None | object = _DEFAULT_READ_TIMEOUT,
        on_visible: Callable[[str], None] | None = None,
    ) -> KimiCompletion:
        body: dict[str, Any] = {
            "model": self.settings.model_id,
            "messages": [dict(message) for message in messages],
            "max_completion_tokens": self.settings.max_completion_tokens,
        }
        profile = derive_provider_capability_profile(self.settings)
        if profile.reasoning_effort:
            body["reasoning_effort"] = self.settings.reasoning_effort
        if response_format is not None:
            body["response_format"] = dict(response_format)
        if read_timeout is _DEFAULT_READ_TIMEOUT:
            timeout = completion_timeout(self.settings.timeout_seconds)
        elif read_timeout is None:
            timeout = completion_timeout(None)
        elif isinstance(read_timeout, int | float):
            timeout = completion_timeout(float(read_timeout))
        else:
            timeout = completion_timeout(self.settings.timeout_seconds)
        if on_visible is not None:
            return self._stream_completion(body, timeout, on_visible)
        try:
            response = self._client.post(
                "/chat/completions", json=body, timeout=timeout
            )
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
                request_id=_safe_completion_id(payload.get("id")),
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

    def _stream_completion(
        self,
        body: dict[str, Any],
        timeout: httpx.Timeout,
        on_visible: Callable[[str], None],
    ) -> KimiCompletion:
        streamed = dict(body)
        streamed["stream"] = True
        content_parts: list[str] = []
        finish_reason: str | None = None
        request_id: str | None = None
        shown = ""
        last_emit = 0.0
        try:
            with self._client.stream(
                "POST", "/chat/completions", json=streamed, timeout=timeout
            ) as response:
                _raise_for_provider(response)
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    payload = json.loads(data)
                    request_id = request_id or _safe_completion_id(payload.get("id"))
                    choice = payload["choices"][0]
                    if isinstance(choice, dict) and choice.get("finish_reason"):
                        finish_reason = str(choice["finish_reason"])
                    delta = choice.get("delta") if isinstance(choice, dict) else None
                    piece = delta.get("content") if isinstance(delta, dict) else None
                    if isinstance(piece, str) and piece:
                        content_parts.append(piece)
                        visible = visible_json_field("".join(content_parts), "message")
                        now = time.monotonic()
                        if (
                            visible
                            and visible != shown
                            and (
                                len(visible) - len(shown) >= 12
                                or now - last_emit >= 0.12
                            )
                        ):
                            shown = visible
                            last_emit = now
                            on_visible(visible)
        except httpx.TimeoutException as exc:
            raise FactoryProviderError(
                "factory_timeout", "Factory model request timed out"
            ) from exc
        except httpx.HTTPError as exc:
            raise FactoryProviderError(
                "factory_unavailable", "Factory model service is unavailable"
            ) from exc
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
        content = "".join(content_parts)
        visible = visible_json_field(content, "message")
        if visible and visible != shown:
            on_visible(visible)
        if not content.strip():
            raise FactoryProviderError(
                "factory_invalid_response",
                "Factory model service returned an invalid completion",
            )
        return KimiCompletion(
            content=content,
            assistant_message={"role": "assistant", "content": content},
            finish_reason=finish_reason,
            request_id=request_id,
        )


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

    def capability_profile(self) -> ProviderCapabilityProfile:
        return derive_provider_capability_profile(self.settings)

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
        read_timeout: float | None | object = _DEFAULT_READ_TIMEOUT,
        on_visible: Callable[[str], None] | None = None,
    ) -> KimiCompletion:
        transport = self._transport()
        if isinstance(transport, HttpKimiTransport) and on_visible is not None:
            return transport.complete(
                messages,
                response_format=response_format,
                read_timeout=read_timeout,
                on_visible=on_visible,
            )
        if (
            isinstance(transport, HttpKimiTransport)
            and read_timeout is not _DEFAULT_READ_TIMEOUT
        ):
            return transport.complete(
                messages,
                response_format=response_format,
                read_timeout=read_timeout,
            )
        return transport.complete(messages, response_format=response_format)


def _raise_for_provider(response: httpx.Response) -> None:
    if response.is_success:
        return
    status_details = {"http_status": str(response.status_code)}
    logger.warning(
        "factory provider error status=%s",
        response.status_code,
    )
    if response.status_code == 401:
        raise FactoryProviderError(
            "factory_unauthorized",
            "Factory model credentials were rejected",
            details=status_details,
        )
    if response.status_code == 403:
        raise FactoryProviderError(
            "factory_forbidden",
            "Factory model request was forbidden",
            details=status_details,
        )
    if response.status_code == 429:
        raise FactoryProviderError(
            "factory_rate_limited",
            "Factory model service is rate limited",
            details=status_details,
        )
    if response.status_code >= 500:
        raise FactoryProviderError(
            "factory_provider_error",
            "Factory model service failed",
            details=status_details,
        )
    details = {**status_details, **_provider_error_facts(response)}
    logger.warning(
        "factory request rejected type=%s code=%s field=%s",
        details.get("provider_error_type"),
        details.get("provider_error_code"),
        details.get("rejected_field"),
    )
    raise FactoryProviderError(
        "factory_request_invalid",
        "Factory model request was rejected" + _diagnostic_suffix(details),
        details=details,
    )


def _provider_error_facts(response: httpx.Response) -> dict[str, str]:
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        return {}
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return {}
    facts: dict[str, str] = {}
    mapping = (
        ("type", "provider_error_type"),
        ("code", "provider_error_code"),
        ("param", "rejected_field"),
    )
    for source, destination in mapping:
        value = error.get(source)
        if isinstance(value, str) and value.strip():
            facts[destination] = value.strip()[:80]
    message = error.get("message")
    if not isinstance(message, str) or not message.strip():
        return facts
    cleaned = _REDACT.sub("<redacted>", " ".join(message.split()))
    if len(cleaned) > 240:
        cleaned = cleaned[:239] + "…"
    facts["bounded_message"] = cleaned
    match = _ERROR_PATH.search(message)
    if match is not None and "rejected_field" not in facts:
        facts["rejected_field"] = match.group(1)[:160]
    return facts


def _diagnostic_suffix(details: Mapping[str, str]) -> str:
    parts: list[str] = []
    error_type = details.get("provider_error_type")
    field = details.get("rejected_field")
    if error_type:
        parts.append(error_type)
    if field:
        parts.append(f"at {field}")
    if not parts:
        return ""
    return " [" + " ".join(parts) + "]"


def _safe_completion_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", cleaned):
        return None
    folded = cleaned.casefold()
    if folded.startswith("sk-") or "bearer" in folded:
        return None
    return cleaned
