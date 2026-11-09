"""One read-only model review request with safe progress and protocol receipts."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from time import monotonic
from typing import Any, TypeVar

from .client import RuntimeModelClient, RuntimeProviderError
from .finalization import ReviewProtocolError

T = TypeVar("T")


def request_model_review(
    model: Any,
    prompt: str,
    user_content: Any,
    schema: Mapping[str, Any],
    *,
    phase: str,
    is_running: Callable[[], bool],
    emit: Callable[[str | None, str, dict[str, Any]], None],
    parse: Callable[[str], T],
    observation: Callable[[T], dict[str, Any]],
    metadata: Mapping[str, Any] | None = None,
) -> T:
    from .service import RuntimeError, _RunAbandoned

    if not is_running():
        raise _RunAbandoned()
    emit(
        "model",
        "finalization.started",
        {
            **(metadata or {}),
            "phase": phase,
            "evidence_kind": "model_assessment",
            "independent_verification": False,
            "request_content_bytes": len(prompt.encode())
            + len(json.dumps(user_content, ensure_ascii=False).encode()),
        },
    )
    started = monotonic()
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_content},
    ]
    try:
        if isinstance(model, RuntimeModelClient):
            completion = model.complete_review(
                messages,
                on_progress=lambda progress: emit(
                    "model",
                    "finalization.progress",
                    {"phase": phase, **progress, "published": False},
                ),
                is_cancelled=lambda: not is_running(),
                schema=schema,
            )
        else:
            complete = getattr(
                model,
                "complete_review",
                getattr(model, "complete_action", model.complete),
            )
            completion = complete(messages)
    except RuntimeProviderError as exc:
        if not is_running():
            raise _RunAbandoned() from exc
        emit(
            "model",
            "finalization.failed",
            {
                "phase": phase,
                "code": exc.code,
                "message": str(exc),
                "provider_diagnostic": exc.diagnostic,
                "elapsed_ms": round((monotonic() - started) * 1000),
                "published": False,
            },
        )
        raise RuntimeError(exc.code, str(exc)) from exc
    if not is_running():
        raise _RunAbandoned()
    try:
        result = parse(completion.content)
    except ValueError as exc:
        emit(
            "model",
            "finalization.failed",
            {
                "phase": phase,
                "code": "agent_finalization_review_invalid",
                "message": str(exc),
                "diagnostic": exc.diagnostic
                if isinstance(exc, ReviewProtocolError)
                else {"category": "invalid_review", "location": "/"},
                "review_protocol": getattr(completion, "review_protocol", None),
                "elapsed_ms": round((monotonic() - started) * 1000),
                "published": False,
            },
        )
        raise RuntimeError("agent_finalization_review_invalid", str(exc)) from exc
    emit(
        "model",
        "finalization.completed",
        {
            **observation(result),
            "phase": phase,
            "elapsed_ms": round((monotonic() - started) * 1000),
            "review_protocol": getattr(completion, "review_protocol", None),
            "published": False,
        },
    )
    return result
