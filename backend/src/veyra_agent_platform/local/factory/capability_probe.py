"""Bounded synthetic structured-output probe. Never uses user or Project data.

Probe order:

1. minimal strict JSON Schema (`ok: boolean`)
2. `json_object` only after schema / response_format incompatibility
3. otherwise record unknown / unsupported without retrying

HTTP 401, 403, 429, 5xx, timeouts, and unknown 4xx do not infer
`strict_json_schema = false`. `/models` is never called here.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from .capability_profile import (
    PROBE_USER_CONTENT,
    ProfileStatus,
    ProviderCapabilityProfile,
    classify_provider_error,
    no_capability_downgrade,
    probe_strict_response_format,
)
from .client import FactoryProviderError, KimiCompletion

CompleteFn = Callable[..., KimiCompletion]
PROBE_MESSAGES: tuple[dict[str, str], ...] = (
    {"role": "user", "content": PROBE_USER_CONTENT},
)


def probe_provider_capabilities(
    complete: CompleteFn,
    previous: ProviderCapabilityProfile,
    *,
    now: str,
) -> ProviderCapabilityProfile:
    """Run at most two synthetic completions against the current identity."""

    _assert_synthetic_only(PROBE_MESSAGES)
    try:
        completion = complete(
            PROBE_MESSAGES,
            response_format=probe_strict_response_format(previous),
        )
    except FactoryProviderError as exc:
        error_class = classify_provider_error(
            exc.code, message=str(exc), details=exc.details
        )
        if no_capability_downgrade(error_class):
            return _keep_truth(previous, now, error_class)
        if error_class not in {
            "schema_incompatible",
            "response_format_unsupported",
        }:
            return _keep_truth(previous, now, error_class)
        return _probe_json_object(complete, previous, now)
    if _probe_payload_ok(completion.content):
        return replace(
            previous,
            structured_output="json_schema",
            strict_json_schema=True,
            json_object_fallback=previous.provider_family == "moonshot",
            strict_json_schema_support="supported",
            source="probe",
            status="known",
            checked_at=now,
            probed=True,
            error_class=None,
        )
    return _keep_truth(previous, now, "invalid_response")


def _probe_json_object(
    complete: CompleteFn,
    previous: ProviderCapabilityProfile,
    now: str,
) -> ProviderCapabilityProfile:
    try:
        completion = complete(
            PROBE_MESSAGES,
            response_format={"type": "json_object"},
        )
    except FactoryProviderError as exc:
        error_class = classify_provider_error(
            exc.code, message=str(exc), details=exc.details
        )
        if no_capability_downgrade(error_class):
            return _keep_truth(previous, now, error_class)
        if error_class in {"schema_incompatible", "response_format_unsupported"}:
            return replace(
                previous,
                structured_output="json_object",
                strict_json_schema=False,
                json_object_fallback=False,
                strict_json_schema_support="unsupported",
                json_object_support="unsupported",
                source="probe",
                status="known",
                checked_at=now,
                probed=True,
                error_class=error_class,
            )
        return _keep_truth(previous, now, error_class)
    if _probe_payload_ok(completion.content):
        return replace(
            previous,
            structured_output="json_object",
            strict_json_schema=False,
            json_object_fallback=False,
            strict_json_schema_support="unsupported",
            json_object_support="supported",
            source="fallback",
            status="known",
            checked_at=now,
            probed=True,
            error_class=None,
        )
    return _keep_truth(previous, now, "invalid_response")


def _keep_truth(
    previous: ProviderCapabilityProfile,
    now: str,
    error_class: str,
) -> ProviderCapabilityProfile:
    status: ProfileStatus
    if error_class in {"rate_limited", "provider_failure", "timeout"}:
        status = "inconclusive"
    else:
        status = "failed"
    return replace(
        previous,
        status=status,
        checked_at=now,
        probed=False,
        error_class=error_class,
    )


def _probe_payload_ok(content: str) -> bool:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return False
    return isinstance(parsed, dict) and isinstance(parsed.get("ok"), bool)


def _assert_synthetic_only(messages: Sequence[Mapping[str, Any]]) -> None:
    if tuple(dict(item) for item in messages) != tuple(PROBE_MESSAGES):
        raise ValueError("capability probe may only send the synthetic prompt")
