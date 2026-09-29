"""OpenAI-compatible Runtime model client with an injectable transport."""

from __future__ import annotations

import binascii
import ipaddress
import json
from base64 import b64decode
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

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


MAX_GENERATED_IMAGE_BYTES = 20_000_000
_IMAGE_SUFFIXES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


@dataclass(frozen=True)
class GeneratedImage:
    """Image bytes returned by an image model; never written to run events."""

    contents: bytes
    media_type: str

    @property
    def suffix(self) -> str:
        return _IMAGE_SUFFIXES.get(self.media_type, ".png")


def sniff_image(contents: bytes) -> str | None:
    if contents.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if contents.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if contents.startswith(b"RIFF") and contents[8:12] == b"WEBP":
        return "image/webp"
    if contents.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    return None


def _image_from_bytes(contents: bytes) -> GeneratedImage:
    if not contents or len(contents) > MAX_GENERATED_IMAGE_BYTES:
        raise RuntimeProviderError(
            "image_generation_invalid", "The image model returned an unusable image"
        )
    media_type = sniff_image(contents)
    if media_type is None:
        raise RuntimeProviderError(
            "image_generation_invalid", "The image model did not return an image"
        )
    return GeneratedImage(contents=contents, media_type=media_type)


def _public_https_url(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        return False
    host = parts.hostname.casefold()
    if host == "localhost" or host.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
    )


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
        headers = {"Authorization": f"Bearer {api_key}"}
        if settings.provider_type == "anthropic":
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            }
        self._client = http_client or httpx.Client(
            base_url=settings.model_base_url,
            headers=headers,
            timeout=settings.timeout_seconds,
        )

    def models(self) -> Sequence[str]:
        try:
            response = self._client.get(
                "/v1/models"
                if self.settings.provider_type == "anthropic"
                else "/models"
            )
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

    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        response_format: Mapping[str, Any] | None = None,
    ) -> RuntimeCompletion:
        body = self._request_body(messages, response_format=response_format)
        _assert_provider_safe_messages(messages)
        try:
            response = self._client.post(
                "/v1/messages"
                if self.settings.provider_type == "anthropic"
                else "/chat/completions",
                json=body,
            )
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
            content = _response_content(payload, self.settings.provider_type)
            if not isinstance(content, str) or not content.strip():
                raise ValueError("missing assistant content")
            return RuntimeCompletion(
                content=content,
                finish_reason=_finish_reason(payload, self.settings.provider_type),
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

    def stream(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        response_format: Mapping[str, Any] | None = None,
    ) -> Iterator[str]:
        """Yield assistant deltas when the provider supports streaming."""
        body = self._request_body(messages, response_format=response_format)
        body["stream"] = True
        _assert_provider_safe_messages(messages)
        try:
            with self._client.stream(
                "POST",
                "/v1/messages"
                if self.settings.provider_type == "anthropic"
                else "/chat/completions",
                json=body,
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
                        content = _stream_content(payload, self.settings.provider_type)
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

    def generate_images(
        self, prompt: str, *, count: int = 1, size: str | None = None
    ) -> list[GeneratedImage]:
        """OpenAI-compatible POST /images/generations; b64_json or URL replies."""

        if self.settings.provider_type == "anthropic":
            raise RuntimeProviderError(
                "image_generation_unsupported",
                "This provider does not offer an image generation endpoint",
            )
        body: dict[str, Any] = {
            "model": self.settings.model_id,
            "prompt": prompt,
            "n": max(1, count),
        }
        if size:
            body["size"] = size
        try:
            response = self._client.post(
                "/images/generations",
                json=body,
                timeout=max(self.settings.timeout_seconds, 180.0),
            )
        except httpx.TimeoutException as exc:
            raise RuntimeProviderError(
                "runtime_timeout", "Image generation timed out"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeProviderError(
                "runtime_unavailable", "Image generation service is unavailable"
            ) from exc
        _raise_for_provider(response)
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeProviderError(
                "runtime_invalid_response",
                "Image generation returned an invalid response",
            ) from exc
        items: Any = []
        if isinstance(payload, dict):
            items = payload.get("data") or payload.get("images") or []
        images: list[GeneratedImage] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            encoded = item.get("b64_json")
            if isinstance(encoded, str) and encoded:
                images.append(_image_from_bytes(_decode_base64(encoded)))
                continue
            url = item.get("url")
            if isinstance(url, str) and url:
                images.append(self._image_from_url(url))
        return images

    def _image_from_url(self, url: str) -> GeneratedImage:
        if url.startswith("data:image/") and ";base64," in url:
            return _image_from_bytes(_decode_base64(url.split(";base64,", 1)[1]))
        if not _public_https_url(url):
            raise RuntimeProviderError(
                "image_generation_invalid",
                "The image model returned a non-public image URL",
            )
        try:
            # A fresh client: the provider API key must not reach the CDN host.
            with (
                httpx.Client(timeout=60.0, follow_redirects=True) as client,
                client.stream("GET", url) as response,
            ):
                if not response.is_success:
                    raise RuntimeProviderError(
                        "image_generation_invalid",
                        "The generated image could not be downloaded",
                    )
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > MAX_GENERATED_IMAGE_BYTES:
                        raise RuntimeProviderError(
                            "image_generation_invalid",
                            "The generated image is too large",
                        )
                    chunks.append(chunk)
        except httpx.HTTPError as exc:
            raise RuntimeProviderError(
                "runtime_unavailable", "The generated image could not be downloaded"
            ) from exc
        return _image_from_bytes(b"".join(chunks))

    def _request_body(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        response_format: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.settings.provider_type == "anthropic":
            system = "\n\n".join(
                str(item.get("content") or "")
                for item in messages
                if item.get("role") == "system"
            )
            body: dict[str, Any] = {
                "model": self.settings.model_id,
                "messages": [
                    dict(item) for item in messages if item.get("role") != "system"
                ],
                "max_tokens": self.settings.max_completion_tokens,
            }
            if system:
                body["system"] = system
            return body
        body = {
            "model": self.settings.model_id,
            "messages": [dict(message) for message in messages],
            "reasoning_effort": self.settings.reasoning_effort,
            "max_completion_tokens": self.settings.max_completion_tokens,
        }
        if response_format:
            body["response_format"] = dict(response_format)
        return body


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
            "provider_type": self.settings.provider_type,
            "model_id": self.settings.model_id,
            "model_base_url": self.settings.model_base_url,
            "model_api_key_env": self.settings.model_api_key_env,
            "reasoning_effort": self.settings.reasoning_effort,
            "allow_process_environment_key": (
                self.settings.allow_process_environment_key
            ),
            "user_provided_only": not self.settings.allow_process_environment_key,
        }

    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        response_format: Mapping[str, Any] | None = None,
    ) -> RuntimeCompletion:
        if not self.configured:
            raise RuntimeProviderNotConfigured()
        transport = self._transport()
        self._ensure_model(transport)
        completion: RuntimeCompletion = _call_with_response_format(
            transport.complete, messages, response_format
        )
        return completion

    def stream(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        response_format: Mapping[str, Any] | None = None,
    ) -> Iterator[str]:
        if not self.configured:
            raise RuntimeProviderNotConfigured()
        transport = self._transport()
        self._ensure_model(transport)
        stream = getattr(transport, "stream", None)
        if callable(stream):
            yield from _call_with_response_format(stream, messages, response_format)
            return
        yield _call_with_response_format(
            transport.complete, messages, response_format
        ).content

    def generate_images(
        self, prompt: str, *, count: int = 1, size: str | None = None
    ) -> list[GeneratedImage]:
        """Image models are often absent from /models, so no list check here."""

        if not self.configured:
            raise RuntimeProviderNotConfigured()
        generate = getattr(self._transport(), "generate_images", None)
        if not callable(generate):
            raise RuntimeProviderError(
                "image_generation_unsupported",
                "The bound Runtime model cannot generate images",
            )
        return list(generate(prompt, count=count, size=size))

    def validate(self) -> None:
        """Verify credentials and the model through the provider model list."""
        if not self.configured:
            raise RuntimeProviderNotConfigured()
        self._ensure_model(self._transport())

    def list_models(self) -> tuple[str, ...]:
        """List models without sending a generation request."""
        if not self.configured:
            raise RuntimeProviderNotConfigured()
        return tuple(self._transport().models())

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


def _call_with_response_format(
    fn: Any,
    messages: Sequence[Mapping[str, Any]],
    response_format: Mapping[str, Any] | None,
) -> Any:
    if response_format is None:
        return fn(messages)
    try:
        return fn(messages, response_format=response_format)
    except TypeError:
        return fn(messages)


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


def _decode_base64(encoded: str) -> bytes:
    try:
        return b64decode(encoded, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeProviderError(
            "image_generation_invalid", "The image model returned invalid base64"
        ) from exc


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


def _response_content(payload: Any, provider_type: str) -> str | None:
    if provider_type == "anthropic":
        content = payload.get("content") if isinstance(payload, dict) else None
        if isinstance(content, list):
            return "".join(
                str(item.get("text") or "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("choices"), list):
        return None
    choices = payload["choices"]
    if not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    return message.get("content") if isinstance(message, dict) else None


def _finish_reason(payload: Any, provider_type: str) -> str | None:
    if provider_type == "anthropic":
        return (
            str(payload.get("stop_reason"))
            if isinstance(payload, dict) and payload.get("stop_reason")
            else None
        )
    if isinstance(payload, dict) and isinstance(payload.get("choices"), list):
        choices = payload["choices"]
        if choices and isinstance(choices[0], dict):
            return choices[0].get("finish_reason")
    return None


def _stream_content(payload: Any, provider_type: str) -> str | None:
    if provider_type == "anthropic":
        delta = payload.get("delta") if isinstance(payload, dict) else None
        return delta.get("text") if isinstance(delta, dict) else None
    if not isinstance(payload, dict) or not isinstance(payload.get("choices"), list):
        return None
    choices = payload["choices"]
    if not choices or not isinstance(choices[0], dict):
        return None
    delta = choices[0].get("delta", {})
    return delta.get("content") if isinstance(delta, dict) else None
