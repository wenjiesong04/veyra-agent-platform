"""One streamed text request, aggregated privately until normal completion."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from time import monotonic
from typing import Any, NoReturn

import httpx

from .client import (
    RuntimeCompletion,
    RuntimeProviderError,
    _completion_diagnostic,
    _finish_reason,
    _raise_for_provider,
    _response_content,
)
from .config import RuntimeSettings

Progress = Callable[[dict[str, Any]], None]
MAX_EVENT_BYTES = 1_000_000
MAX_ERROR_BYTES = 16_384
_LINE_BREAK = re.compile(r"\r\n|\r|\n")


class _TextContent:
    def __init__(self, provider: str, max_bytes: int) -> None:
        self.provider = provider
        self.max_bytes = max_bytes
        self.parts: list[str] = []
        self.content_bytes = 0
        self.events = 0
        self.finish: str | None = None
        self.completed = False

    def invalid(
        self,
        message: str = "Model stream was incomplete or invalid",
        *,
        diagnostic: dict[str, Any] | None = None,
    ) -> NoReturn:
        raise RuntimeProviderError(
            "runtime_invalid_response",
            message,
            diagnostic={
                "event_count": self.events,
                "content_bytes": self.content_bytes,
                **(diagnostic or {}),
            },
        )

    def append(self, value: Any) -> None:
        if value is None:
            return
        if not isinstance(value, str) or self.finish is not None:
            self.invalid()
        self.content_bytes += len(value.encode())
        if self.content_bytes > self.max_bytes:
            self.invalid("Model response exceeded its configured output envelope")
        self.parts.append(value)

    def finish_with(self, reason: Any) -> None:
        if not isinstance(reason, str):
            self.invalid()
        if reason in {"length", "max_tokens"}:
            raise RuntimeProviderError(
                "runtime_output_truncated",
                "The model reached its output limit before completing its response",
                diagnostic={"finish_reason": reason},
            )
        normal = "end_turn" if self.provider == "anthropic" else "stop"
        if reason != normal:
            self.invalid("Model stream did not finish with a normal text response")
        self.finish = reason

    def consume(self, data: str) -> None:
        self.events += 1
        if data == "[DONE]":
            if self.finish != "stop":
                self.invalid()
            self.completed = True
            return
        try:
            payload = json.loads(data)
        except (TypeError, ValueError):
            self.invalid()
            return
        if not isinstance(payload, dict):
            self.invalid()
        if payload.get("error") or payload.get("type") == "error":
            error = payload.get("error", {})
            code = (
                error.get("code") or error.get("type")
                if isinstance(error, dict)
                else ""
            )
            status = (
                429
                if isinstance(code, str)
                and code in {"rate_limit_error", "rate_limit_exceeded"}
                else 500
            )
            _raise_for_provider(httpx.Response(status, json=payload))
        if self.provider == "anthropic":
            kind = payload.get("type")
            if kind == "content_block_start":
                block = payload.get("content_block", {})
                if isinstance(block, dict) and block.get("type") == "text":
                    self.append(block.get("text"))
            elif kind == "content_block_delta":
                delta = payload.get("delta", {})
                if isinstance(delta, dict) and delta.get("type") == "text_delta":
                    self.append(delta.get("text"))
            elif kind == "message_delta":
                delta = payload.get("delta", {})
                if isinstance(delta, dict) and delta.get("stop_reason") is not None:
                    self.finish_with(delta["stop_reason"])
            elif kind == "message_stop":
                if self.finish != "end_turn":
                    self.invalid()
                self.completed = True
            # Thinking, signatures, ping and metadata are never retained or exposed.
            return
        choices = payload.get("choices")
        if choices == [] and isinstance(payload.get("usage"), dict):
            return
        if (
            not isinstance(choices, list)
            or len(choices) != 1
            or not isinstance(choices[0], dict)
        ):
            self.invalid()
        choice = choices[0]
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            self.invalid()
        if (
            delta.get("refusal")
            or delta.get("tool_calls")
            or delta.get("function_call")
        ):
            self.invalid("Model stream did not return a text response")
        self.append(delta.get("content"))
        if choice.get("finish_reason") is not None:
            self.finish_with(choice["finish_reason"])
            # Normal finish_reason also supports endpoints without a DONE event.
            self.completed = True

    def result(self) -> RuntimeCompletion:
        content = "".join(self.parts)
        if not self.completed:
            self.invalid()
        if not content.strip():
            self.invalid(
                diagnostic={
                    "content_empty": True,
                    "content_type": "text" if self.parts else "missing",
                    "finish_reason": self.finish,
                    "has_tool_calls": False,
                    "has_refusal": False,
                }
            )
        return RuntimeCompletion(content=content, finish_reason=self.finish)


def _events(response: httpx.Response, check: Callable[[], None]) -> Iterator[str]:
    lines: list[str] = []
    size = 0
    buffer = ""

    def frame(line: str) -> str | None:
        nonlocal lines, size
        if not line:
            data = "\n".join(lines) if lines else None
            lines, size = [], 0
            return data
        if line.startswith("data:"):
            value = line[5:].removeprefix(" ")
            size += len(value.encode())
            if size > MAX_EVENT_BYTES:
                raise RuntimeProviderError(
                    "runtime_invalid_response", "Model stream event was too large"
                )
            lines.append(value)
        return None

    # Check network chunks, not completed lines: an unterminated line is not progress.
    for chunk in response.iter_text():
        check()
        buffer += chunk
        while match := _LINE_BREAK.search(buffer):
            if match[0] == "\r" and match.end() == len(buffer):
                break
            line, buffer = buffer[: match.start()], buffer[match.end() :]
            if len(line.encode()) > MAX_EVENT_BYTES:
                raise RuntimeProviderError(
                    "runtime_invalid_response", "Model stream line was too large"
                )
            data = frame(line)
            if data is not None:
                yield data
        if len(buffer.encode()) > MAX_EVENT_BYTES:
            raise RuntimeProviderError(
                "runtime_invalid_response", "Model stream line was too large"
            )
    if buffer:
        data = frame(buffer.removesuffix("\r"))
        if data is not None:
            yield data
    if lines:
        yield "\n".join(lines)


def _bounded_body(
    response: httpx.Response,
    limit: int,
    check: Callable[[], None],
    *,
    truncate: bool = False,
) -> bytes:
    parts = bytearray()
    for chunk in response.iter_bytes():
        check()
        if not truncate and len(parts) + len(chunk) > limit:
            raise RuntimeProviderError(
                "runtime_invalid_response",
                "Model response exceeded its configured output envelope",
            )
        parts.extend(chunk[: limit - len(parts)])
        if truncate and len(parts) >= limit:
            break
    return bytes(parts)


def complete_text_stream(
    client: httpx.Client,
    settings: RuntimeSettings,
    body: dict[str, Any],
    *,
    read_timeout_seconds: float,
    max_duration_seconds: float,
    on_progress: Progress | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> RuntimeCompletion:
    started = monotonic()
    content = _TextContent(settings.provider_type, settings.max_completion_tokens * 32)
    last_progress = -1.0
    last_phase = ""
    last_cancel_check = -1.0

    def check(*, force_cancel: bool = False) -> None:
        nonlocal last_cancel_check
        elapsed = monotonic() - started
        if is_cancelled is not None and (
            force_cancel or elapsed - last_cancel_check >= 0.2
        ):
            last_cancel_check = elapsed
            if is_cancelled():
                raise RuntimeProviderError(
                    "runtime_cancelled", "Model request was cancelled"
                )
        if elapsed >= max_duration_seconds:
            raise RuntimeProviderError(
                "runtime_timeout",
                "Model request exceeded its total duration",
                diagnostic={
                    "timeout_phase": "deadline",
                    "timeout_seconds": max_duration_seconds,
                },
            )

    def progress(phase: str) -> None:
        nonlocal last_progress, last_phase
        check(force_cancel=phase == "completed")
        elapsed = monotonic() - started
        if on_progress and (phase != last_phase or elapsed - last_progress >= 1):
            on_progress(
                {
                    "status": phase,
                    "elapsed_ms": round(elapsed * 1000),
                    "event_count": content.events,
                    "content_bytes": content.content_bytes,
                }
            )
            last_progress, last_phase = elapsed, phase

    def received_chunk() -> None:
        progress("receiving_result" if content.content_bytes else "receiving")

    timeout = httpx.Timeout(settings.timeout_seconds, read=read_timeout_seconds)
    response_metadata: dict[str, Any] = {}
    check(force_cancel=True)
    try:
        with client.stream(
            "POST",
            "/v1/messages"
            if settings.provider_type == "anthropic"
            else "/chat/completions",
            json={**body, "stream": True},
            headers={"Accept-Encoding": "identity"},
            timeout=timeout,
        ) as response:
            media = (
                response.headers.get("content-type", "")
                .split(";", 1)[0]
                .strip()
                .lower()
            )
            encoding = (
                response.headers.get("content-encoding", "identity").strip().lower()
            )
            response_metadata = {
                "http_status": response.status_code,
                "response_content_type": media
                if media in {"text/event-stream", "application/json"}
                else "other",
                "response_content_encoding": encoding
                if encoding in {"identity", "gzip", "deflate", "br", "zstd"}
                else "other",
            }
            check()
            if not response.is_success:
                error = _bounded_body(response, MAX_ERROR_BYTES, check, truncate=True)
                try:
                    _raise_for_provider(
                        httpx.Response(
                            response.status_code,
                            headers={"content-type": media},
                            content=error,
                        )
                    )
                except RuntimeProviderError as exc:
                    exc.diagnostic.update(response_metadata)
                    raise
            _raise_for_provider(response)
            progress("connected")
            if media == "application/json":
                # Some compatible gateways ignore stream=True. Parse this same response,
                # never submit a second billable request as a protocol fallback.
                raw = _bounded_body(response, content.max_bytes, received_chunk)
                try:
                    payload = json.loads(raw)
                except (TypeError, ValueError):
                    content.invalid()
                diagnostic = _completion_diagnostic(payload, settings.provider_type)
                reason = _finish_reason(payload, settings.provider_type)
                choices = payload.get("choices") if isinstance(payload, dict) else None
                raw_reason = (
                    payload.get("stop_reason")
                    if settings.provider_type == "anthropic"
                    and isinstance(payload, dict)
                    else choices[0].get("finish_reason")
                    if isinstance(choices, list)
                    and choices
                    and isinstance(choices[0], dict)
                    else None
                )
                if raw_reason is not None and not isinstance(raw_reason, str):
                    content.invalid()
                if reason is not None:
                    content.finish_with(reason)
                if diagnostic.get("has_tool_calls") or diagnostic.get("has_refusal"):
                    content.invalid(diagnostic=diagnostic)
                text = _response_content(payload, settings.provider_type)
                if not isinstance(text, str) or not text.strip():
                    content.invalid(diagnostic=diagnostic)
                progress("completed")
                return RuntimeCompletion(text, reason)
            if media != "text/event-stream":
                content.invalid("Model service returned an unsupported response type")
            for data in _events(response, received_chunk):
                content.consume(data)
                progress("receiving_result" if content.content_bytes else "receiving")
                if content.completed:
                    break
            result = content.result()
            progress("completed")
            return result
    except httpx.TimeoutException as exc:
        phase = next(
            (
                name
                for kind, name in (
                    (httpx.ReadTimeout, "read"),
                    (httpx.ConnectTimeout, "connect"),
                    (httpx.WriteTimeout, "write"),
                    (httpx.PoolTimeout, "pool"),
                )
                if isinstance(exc, kind)
            ),
            "unknown",
        )
        raise RuntimeProviderError(
            "runtime_timeout",
            "Runtime model request timed out",
            diagnostic={
                "timeout_phase": phase,
                "timeout_seconds": timeout.as_dict().get(phase),
                "event_count": content.events,
                "content_bytes": content.content_bytes,
            },
        ) from None
    except httpx.DecodingError:
        raise RuntimeProviderError(
            "runtime_invalid_response",
            "The model response could not be decoded; check HTTP content encoding",
            diagnostic={
                "category": "response_decoding",
                **response_metadata,
                "event_count": content.events,
                "content_bytes": content.content_bytes,
            },
        ) from None
    except httpx.HTTPError:
        raise RuntimeProviderError(
            "runtime_unavailable", "Runtime model service is unavailable"
        ) from None
