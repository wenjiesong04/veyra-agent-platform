"""OpenAI-compatible Runtime model client with an injectable transport."""

from __future__ import annotations

import binascii
import ipaddress
import json
import struct
import zlib
from base64 import b64decode, b64encode
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from veyra_agent_platform.local.models.contracts import ProviderModelDescriptor
from veyra_agent_platform.local.models.discovery import normalize_provider_models
from veyra_agent_platform.local.secrets import (
    MODEL_SECRET_REF,
    SecretStore,
    resolve_secret,
)

from .config import RuntimeSettings
from .image_protocols import (
    IMAGE_PROTOCOL_FALLBACKS,
    ImageProtocol,
    ImageRequest,
    image_references,
    image_request,
)


class RuntimeProviderError(RuntimeError):
    """A safe, user-visible provider failure without credentials or raw bodies."""

    def __init__(
        self, code: str, message: str, *, diagnostic: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.diagnostic = diagnostic or {}


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
        self._image_protocol: ImageProtocol = "openai_images"
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
        return tuple(model.provider_model_id for model in self.discover_models())

    def discover_models(self) -> Sequence[ProviderModelDescriptor]:
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
        if response.status_code in {404, 405}:
            raise RuntimeProviderError(
                "runtime_model_discovery_unavailable",
                "Provider model discovery is unavailable at this endpoint",
            )
        _raise_for_provider(response)
        try:
            payload = response.json()
            models = payload["data"]
            if not isinstance(models, list):
                raise TypeError("model list is not an array")
            return normalize_provider_models(models)
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
        payload: Any = None
        try:
            payload = response.json()
            finish_reason = _finish_reason(payload, self.settings.provider_type)
            if finish_reason in {"length", "max_tokens"}:
                raise RuntimeProviderError(
                    "runtime_output_truncated",
                    "The model reached its output limit before completing an action. "
                    "No action from this response was executed.",
                    diagnostic=_completion_diagnostic(
                        payload, self.settings.provider_type
                    ),
                )
            content = _response_content(payload, self.settings.provider_type)
            if not isinstance(content, str) or not content.strip():
                raise ValueError("missing assistant content")
            return RuntimeCompletion(
                content=content,
                finish_reason=finish_reason,
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
                diagnostic=_completion_diagnostic(payload, self.settings.provider_type),
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
        """Call a supported image protocol using the provider's default size."""

        if self.settings.provider_type == "anthropic":
            raise RuntimeProviderError(
                "image_generation_unsupported",
                "This provider does not offer an image generation endpoint",
            )
        if self._image_protocol == "image_chat" and (count != 1 or size is not None):
            raise RuntimeProviderError(
                "runtime_parameters_unsupported",
                "This image endpoint requires one image with default dimensions",
            )
        request = image_request(
            self.settings.model_base_url,
            self.settings.model_id,
            prompt,
            count=count,
            size=size,
            protocol=self._image_protocol,
        )
        while True:
            try:
                response = self._image_response(request)
                break
            except RuntimeProviderError as exc:
                # Only a missing route may negotiate another protocol. Model,
                # parameter, quota, permission and output failures never retry
                # a potentially billable generation request.
                next_protocol = IMAGE_PROTOCOL_FALLBACKS.get(request.protocol)
                if exc.code != "runtime_endpoint_not_found" or next_protocol is None:
                    raise
                if next_protocol == "image_chat" and (count != 1 or size is not None):
                    raise RuntimeProviderError(
                        "runtime_parameters_unsupported",
                        "This image endpoint requires one image "
                        "with default dimensions",
                    ) from None
            request = image_request(
                self.settings.model_base_url,
                self.settings.model_id,
                prompt,
                count=count,
                size=size,
                protocol=next_protocol,
            )
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeProviderError(
                "runtime_invalid_response",
                "Image generation returned an invalid response",
            ) from exc
        references = image_references(payload, request.protocol)
        if not references:
            raise RuntimeProviderError(
                "runtime_invalid_response", "Image generation returned no image"
            )
        images = [
            _image_from_bytes(_decode_base64(item.value))
            if item.base64_encoded
            else self._image_from_url(item.value)
            for item in references
        ]
        self._image_protocol = request.protocol
        return images

    def _image_response(self, request: ImageRequest) -> httpx.Response:
        try:
            response = self._client.post(
                request.path,
                json=request.body,
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
        return response

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
        host = (urlsplit(self.settings.model_base_url).hostname or "").lower()
        extended_parameters = self.settings.provider_type in {
            "openai",
            "moonshot",
            "openrouter",
        } or host in {
            "api.openai.com",
            "api.moonshot.cn",
            "api.moonshot.ai",
            "openrouter.ai",
        }
        body = {
            "model": self.settings.model_id,
            "messages": [dict(message) for message in messages],
        }
        if extended_parameters:
            body["reasoning_effort"] = self.settings.reasoning_effort
            body["max_completion_tokens"] = self.settings.max_completion_tokens
        else:
            body["max_tokens"] = self.settings.max_completion_tokens
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
        transport: Any = self._transport()
        self._ensure_model(transport)
        completion: RuntimeCompletion = _call_with_response_format(
            transport.complete, messages, response_format
        )
        return completion

    def complete_action(
        self, messages: Sequence[Mapping[str, Any]]
    ) -> RuntimeCompletion:
        """Use a known Provider's JSON mode for the Agent action contract.

        Unknown compatible endpoints retain the text protocol; they must not
        receive parameters whose support has not been established.
        """
        host = (urlsplit(self.settings.model_base_url).hostname or "").lower()
        known_json = self.settings.provider_type in {
            "openai",
            "moonshot",
            "openrouter",
        } or host in {
            "api.openai.com",
            "api.moonshot.cn",
            "api.moonshot.ai",
            "openrouter.ai",
        }
        return self.complete(
            messages, response_format={"type": "json_object"} if known_json else None
        )

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

    def discover_models(self) -> tuple[ProviderModelDescriptor, ...]:
        """Return only sanitized model-list metadata; never generate content."""
        if not self.configured:
            raise RuntimeProviderNotConfigured()
        transport = self._transport()
        discover = getattr(transport, "discover_models", None)
        if callable(discover):
            return normalize_provider_models(discover())
        return normalize_provider_models(transport.models())

    def probe_text_generation(self) -> None:
        """Explicitly test one selected model with a fixed, bounded message.

        This deliberately bypasses `/models` membership so users of a
        compatible Provider with no listing endpoint can verify a manually
        entered model ID. The generated response is discarded by this method.
        """
        if not self.configured:
            raise RuntimeProviderNotConfigured()
        completion = self._transport().complete(
            ({"role": "user", "content": "Reply with exactly OK."},)
        )
        if (
            not isinstance(completion, RuntimeCompletion)
            or not isinstance(completion.content, str)
            or not completion.content.strip()
        ):
            raise RuntimeProviderError(
                "runtime_invalid_response",
                "Runtime model service returned an invalid probe response",
            )

    def probe_structured_output(self) -> None:
        """Explicitly verify JSON-object response formatting with a tiny reply."""
        if not self.configured:
            raise RuntimeProviderNotConfigured()
        messages = (
            {
                "role": "user",
                "content": 'Reply with exactly the JSON object {"ok":true}.',
            },
        )
        transport: Any = self._transport()
        try:
            completion = transport.complete(
                messages,
                response_format={"type": "json_object"},
            )
        except TypeError as exc:
            raise RuntimeProviderError(
                "capability_probe_unavailable",
                "The configured Runtime adapter cannot probe structured output.",
            ) from exc
        try:
            payload = json.loads(completion.content)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeProviderError(
                "runtime_invalid_response",
                "The structured-output probe did not return a JSON object.",
            ) from exc
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise RuntimeProviderError(
                "runtime_invalid_response",
                "The structured-output probe did not return the requested object.",
            )

    def probe_image_input(self) -> None:
        """Send one generated 1x1 red PNG and discard the model response."""
        if not self.configured:
            raise RuntimeProviderNotConfigured()
        png = _tiny_solid_png(255, 0, 0)
        encoded = b64encode(png).decode("ascii")
        if self.settings.provider_type == "anthropic":
            content: list[dict[str, Any]] = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": encoded,
                    },
                },
                {
                    "type": "text",
                    "text": "What is the dominant color? Reply with one word.",
                },
            ]
        else:
            content = [
                {
                    "type": "text",
                    "text": "What is the dominant color? Reply with one word.",
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{encoded}"},
                },
            ]
        completion = self._transport().complete(({"role": "user", "content": content},))
        if (
            not isinstance(completion, RuntimeCompletion)
            or not completion.content.strip()
        ):
            raise RuntimeProviderError(
                "runtime_invalid_response",
                "The image-input probe returned an invalid response.",
            )

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
    from inspect import signature

    try:
        call_signature = signature(fn)
    except (ValueError, TypeError):
        # An opaque adapter has not established support for this parameter.
        return fn(messages)
    try:
        call_signature.bind(messages, response_format=response_format)
    except TypeError:
        return fn(messages)
    return fn(messages, response_format=response_format)


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


def _tiny_solid_png(red: int, green: int, blue: int) -> bytes:
    """Build a fixed one-pixel RGBA PNG for explicit image capability checks."""

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return (
            struct.pack(">I", len(payload))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    pixels = zlib.compress(bytes((0, red, green, blue, 255)))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", pixels)
        + chunk(b"IEND", b"")
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
        if (
            response.headers.get("content-type", "").split(";", 1)[0].lower()
            == "text/html"
        ):
            raise RuntimeProviderError(
                "runtime_endpoint_invalid", "The service address returned a web page"
            )
        return
    provider_code = _provider_error_category(response)
    if response.status_code == 401 or provider_code == "unauthorized":
        raise RuntimeProviderError(
            "runtime_unauthorized", "Runtime model credentials were rejected"
        )
    if response.status_code == 402 or provider_code == "balance":
        raise RuntimeProviderError(
            "runtime_insufficient_balance",
            "The model service account has insufficient balance or quota",
        )
    if response.status_code == 403:
        raise RuntimeProviderError(
            "runtime_permission_denied",
            "This key does not have permission to use the model service",
        )
    if provider_code == "model":
        raise RuntimeProviderError(
            "runtime_model_unavailable",
            "The model does not exist or is not available to this account",
        )
    if provider_code == "parameter":
        raise RuntimeProviderError(
            "runtime_parameters_unsupported",
            "The model service does not accept the request parameters",
        )
    if response.status_code in {404, 405}:
        raise RuntimeProviderError(
            "runtime_endpoint_not_found", "The model API endpoint was not found"
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


def _provider_error_category(response: httpx.Response) -> str | None:
    """Classify allowlisted error identifiers; never retain free-form messages."""
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    error = error if isinstance(error, dict) else payload
    candidates = (error.get("code"), error.get("type"))
    for candidate in candidates:
        if not isinstance(candidate, str) or len(candidate) > 100:
            continue
        code = "".join(
            character for character in candidate.lower() if character.isalnum()
        )
        if code in {
            "invalidapikey",
            "invalidkey",
            "invalidauthentication",
            "invalidapikeyerror",
        }:
            return "unauthorized"
        if code in {
            "arrearage",
            "insufficientquota",
            "insufficientcredits",
            "insufficientbalance",
            "creditbalanceinsufficient",
            "billinghardlimitreached",
        }:
            return "balance"
        if code in {"modelnotfound", "invalidmodel", "nosuchmodel"}:
            return "model"
        if code in {
            "invalidparameter",
            "unsupportedparameter",
            "modelnotsupported",
        } or code.startswith("invalidparameternotsupport"):
            return "parameter"
    # Some compatible gateways only identify a missing model in their message.
    # Inspect these fixed phrases solely to prevent unsafe endpoint retries; no
    # body text is stored, returned or placed in an exception.
    message = error.get("message")
    if isinstance(message, str):
        normalized = message[:2_000].lower()
        if (
            "model" in normalized
            and any(
                phrase in normalized
                for phrase in (
                    "not found",
                    "does not exist",
                    "not available",
                    "do not have access",
                )
            )
        ) or "no endpoints found for" in normalized:
            return "model"
    return None


def _completion_diagnostic(payload: Any, provider_type: str) -> dict[str, Any]:
    """Response shape only: never persist Provider text or hidden reasoning."""
    content = _response_content(payload, provider_type)
    reason = _finish_reason(payload, provider_type)
    result: dict[str, Any] = {
        "finish_reason": reason
        if reason
        in {
            "stop",
            "length",
            "tool_calls",
            "content_filter",
            "max_tokens",
            "end_turn",
            "tool_use",
        }
        else "unknown",
        "content_type": "text"
        if isinstance(content, str)
        else "missing"
        if content is None
        else "other",
        "content_empty": not bool(
            content.strip() if isinstance(content, str) else content
        ),
    }
    if isinstance(payload, dict):
        choices = payload.get("choices")
        message = (
            choices[0].get("message")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict)
            else None
        )
        if isinstance(message, dict):
            result["has_tool_calls"] = bool(message.get("tool_calls"))
            result["has_refusal"] = bool(message.get("refusal"))
        usage = payload.get("usage")
        if isinstance(usage, dict):
            for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
                value = usage.get(name)
                if isinstance(value, int) and 0 <= value < 10_000_000:
                    result[name] = value
    return result


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
            reason = choices[0].get("finish_reason")
            return reason if isinstance(reason, str) else None
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
