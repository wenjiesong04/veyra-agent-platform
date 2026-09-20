"""Factory provider request-protocol facts for one Provider + Model + Endpoint.

This module answers only: what structured-output request protocol does this
configured Factory endpoint accept? It does not define Veyra Agent semantics.
Canonical Agent meaning remains AgentSemanticPlanV1 → SemanticPlanCompiler →
AgentBlueprint / AgentSource.

`/models` listing only proves a model id is visible. It is not evidence of
strict JSON Schema, `json_object`, `reasoning_effort`, or any schema keyword.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from .config import FactorySettings
from .structured_schema import project_moonshot_json_schema

PROBE_VERSION = "semantic-plan-ok-v1"
PROBE_USER_CONTENT = 'Return an object with field "ok".'
PROBE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}

ProviderFamily = Literal["moonshot", "openai_compatible"]
StructuredOutput = Literal["json_schema", "json_object"]
SchemaFlavor = Literal["moonshot_mfjs", "none"]
SchemaProfile = Literal["mfjs", "openai_json_schema", "unknown"]
EndpointKind = Literal["chat_completions", "responses", "compatible_chat"]
ProfileSource = Literal["static_known", "probe", "fallback"]
ProfileStatus = Literal["known", "unknown", "stale", "failed", "inconclusive"]
CapabilitySupport = Literal["supported", "unsupported", "unknown"]
ProviderErrorClass = Literal[
    "credentials",
    "forbidden",
    "rate_limited",
    "provider_failure",
    "timeout",
    "schema_incompatible",
    "response_format_unsupported",
    "request_invalid",
    "invalid_response",
    "structured_output_unsupported",
    "unknown",
]

_MOONSHOT_HOSTS = frozenset({"api.moonshot.cn", "api.moonshot.ai"})
_MOONSHOT_SUFFIXES = (".moonshot.cn", ".moonshot.ai")
_CAPABILITY_INFERENCE = frozenset(
    {"schema_incompatible", "response_format_unsupported"}
)
_NO_DOWNGRADE = frozenset(
    {
        "credentials",
        "forbidden",
        "rate_limited",
        "provider_failure",
        "timeout",
        "request_invalid",
        "invalid_response",
        "unknown",
    }
)
_FORBIDDEN_PROFILE_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "token",
        "secret",
        "password",
        "headers",
        "raw_response",
        "credential",
        "model_api_key_env",
    }
)


@dataclass(frozen=True)
class ProviderCapabilityProfile:
    provider_id: str
    provider_family: ProviderFamily
    model: str
    endpoint_kind: EndpointKind
    base_url_fingerprint: str
    structured_output: StructuredOutput
    schema_flavor: SchemaFlavor
    schema_profile: SchemaProfile
    strict_json_schema: bool
    json_object_fallback: bool
    reasoning_effort: bool
    supports_reasoning_effort: bool
    strict_json_schema_support: CapabilitySupport
    json_object_support: CapabilitySupport
    source: ProfileSource
    status: ProfileStatus
    checked_at: str | None
    probe_version: str
    probed: bool
    error_class: str | None = None

    @property
    def identity_key(self) -> str:
        material = "\n".join(
            (
                self.provider_id,
                self.model,
                self.endpoint_kind,
                self.base_url_fingerprint,
                self.probe_version,
            )
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "provider_id": self.provider_id,
            "provider_family": self.provider_family,
            "model": self.model,
            "endpoint_kind": self.endpoint_kind,
            "base_url_fingerprint": self.base_url_fingerprint,
            "structured_output": self.structured_output,
            "schema_flavor": self.schema_flavor,
            "schema_profile": self.schema_profile,
            "strict_json_schema": self.strict_json_schema,
            "json_object_fallback": self.json_object_fallback,
            "reasoning_effort": self.reasoning_effort,
            "supports_reasoning_effort": self.supports_reasoning_effort,
            "strict_json_schema_support": self.strict_json_schema_support,
            "json_object_support": self.json_object_support,
            "source": self.source,
            "status": self.status,
            "checked_at": self.checked_at,
            "probe_version": self.probe_version,
            "probed": self.probed,
            "error_class": self.error_class,
            "summary": self.summary(),
        }

    def to_storage_dict(self) -> dict[str, Any]:
        payload = dict(self.to_dict())
        payload.pop("summary", None)
        return payload

    def summary(self) -> dict[str, str]:
        if self.structured_output == "json_schema":
            output_label = "Strict JSON Schema"
        else:
            output_label = "JSON object"
        if (
            self.status == "known"
            and self.strict_json_schema_support == "unsupported"
            and self.json_object_support == "unsupported"
        ):
            output_label = "Typed unsupported"
        fallback_label = "Supported" if self.json_object_fallback else "Not used"
        schema_labels = {
            "mfjs": "MFJS",
            "openai_json_schema": "OpenAI JSON Schema",
            "unknown": "Unknown",
        }
        status_labels = {
            "known": "Known",
            "unknown": "Unknown",
            "stale": "Stale",
            "failed": "Failed",
            "inconclusive": "Inconclusive",
        }
        provider_labels = {
            "moonshot": "Moonshot",
            "openai_compatible": "OpenAI-compatible",
        }
        return {
            "provider": provider_labels.get(self.provider_id, self.provider_id),
            "model": self.model,
            "structured_output": output_label,
            "schema_profile": schema_labels[self.schema_profile],
            "json_object_fallback": fallback_label,
            "status": status_labels[self.status],
            "checked_at": self.checked_at or "",
            "error_class": self.error_class or "",
        }


def derive_provider_capability_profile(
    settings: FactorySettings,
) -> ProviderCapabilityProfile:
    fingerprint = base_url_fingerprint(settings.model_base_url)
    if _moonshot_host(settings.model_base_url):
        return ProviderCapabilityProfile(
            provider_id="moonshot",
            provider_family="moonshot",
            model=settings.model_id,
            endpoint_kind="chat_completions",
            base_url_fingerprint=fingerprint,
            structured_output="json_schema",
            schema_flavor="moonshot_mfjs",
            schema_profile="mfjs",
            strict_json_schema=True,
            json_object_fallback=True,
            reasoning_effort=True,
            supports_reasoning_effort=True,
            strict_json_schema_support="unknown",
            json_object_support="unknown",
            source="static_known",
            status="unknown",
            checked_at=None,
            probe_version=PROBE_VERSION,
            probed=False,
        )
    return ProviderCapabilityProfile(
        provider_id="openai_compatible",
        provider_family="openai_compatible",
        model=settings.model_id,
        endpoint_kind="chat_completions",
        base_url_fingerprint=fingerprint,
        structured_output="json_object",
        schema_flavor="none",
        schema_profile="unknown",
        strict_json_schema=False,
        json_object_fallback=False,
        reasoning_effort=False,
        supports_reasoning_effort=False,
        strict_json_schema_support="unknown",
        json_object_support="unknown",
        source="static_known",
        status="unknown",
        checked_at=None,
        probe_version=PROBE_VERSION,
        probed=False,
    )


def base_url_fingerprint(base_url: str) -> str:
    """Hash scheme+host+port+path only. Query strings are never stored."""

    parsed = urlsplit(base_url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    port = parsed.port
    if port is None or (
        (parsed.scheme == "https" and port == 443)
        or (parsed.scheme == "http" and port == 80)
    ):
        netloc = host
    else:
        netloc = f"{host}:{port}" if port is not None else host
    path = parsed.path.rstrip("/")
    canonical = f"{parsed.scheme.casefold()}://{netloc}{path}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def structured_response_format(
    profile: ProviderCapabilityProfile,
    *,
    name: str,
    schema: Mapping[str, Any],
) -> dict[str, Any]:
    if generate_structured_output(profile) != "json_schema":
        return {"type": "json_object"}
    payload: dict[str, Any] = dict(schema)
    if profile.schema_flavor == "moonshot_mfjs":
        payload = project_moonshot_json_schema(payload)
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": profile.strict_json_schema,
            "schema": payload,
        },
    }


def probe_strict_response_format(
    profile: ProviderCapabilityProfile,
) -> dict[str, Any]:
    payload: dict[str, Any] = dict(PROBE_SCHEMA)
    if profile.schema_flavor == "moonshot_mfjs":
        payload = project_moonshot_json_schema(payload)
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "capability_probe",
            "strict": True,
            "schema": payload,
        },
    }


def generate_structured_output(
    profile: ProviderCapabilityProfile,
) -> StructuredOutput | None:
    if profile.status == "known":
        if profile.strict_json_schema_support == "supported":
            return "json_schema"
        if profile.json_object_support == "supported":
            return "json_object"
        if (
            profile.strict_json_schema_support == "unsupported"
            and profile.json_object_support == "unsupported"
        ):
            return None
    return profile.structured_output


def allows_json_object_generate_fallback(
    profile: ProviderCapabilityProfile,
    *,
    code: str,
    message: str = "",
    details: Mapping[str, str] | None = None,
) -> bool:
    error_class = classify_provider_error(code, message=message, details=details)
    if error_class not in _CAPABILITY_INFERENCE:
        return False
    if profile.json_object_support == "unsupported":
        return False
    if profile.json_object_support == "supported":
        return True
    return profile.json_object_fallback


def classify_provider_error(
    code: str,
    *,
    message: str = "",
    details: Mapping[str, str] | None = None,
) -> ProviderErrorClass:
    if code == "factory_unauthorized":
        return "credentials"
    if code == "factory_forbidden":
        return "forbidden"
    if code == "factory_rate_limited":
        return "rate_limited"
    if code in {"factory_provider_error", "factory_unavailable"}:
        return "provider_failure"
    if code == "factory_timeout":
        return "timeout"
    if code == "factory_invalid_response":
        return "invalid_response"
    if code == "factory_structured_output_unsupported":
        return "structured_output_unsupported"
    if code != "factory_request_invalid":
        return "unknown"
    blob = _error_blob(message, details)
    if _is_schema_incompatible(blob):
        return "schema_incompatible"
    if _is_response_format_unsupported(blob):
        return "response_format_unsupported"
    return "request_invalid"


def no_capability_downgrade(error_class: str) -> bool:
    return error_class in _NO_DOWNGRADE


def assert_safe_profile_payload(payload: Mapping[str, Any]) -> None:
    for key in payload:
        folded = key.casefold()
        if folded in _FORBIDDEN_PROFILE_KEYS or "authorization" in folded:
            raise ValueError("capability profile must not persist credentials")


def _error_blob(message: str, details: Mapping[str, str] | None) -> str:
    facts = details or {}
    return " ".join(
        [
            message,
            str(facts.get("rejected_field") or ""),
            str(facts.get("bounded_message") or ""),
            str(facts.get("provider_error_type") or ""),
            str(facts.get("provider_error_code") or ""),
        ]
    ).casefold()


def _is_schema_incompatible(blob: str) -> bool:
    return (
        any(
            hint in blob
            for hint in (
                "flavored json schema",
                "moonshot flavored",
                "mfjs",
                "json_schema",
            )
        )
        and "unsupported" not in blob
    )


def _is_response_format_unsupported(blob: str) -> bool:
    if "response_format" not in blob:
        return False
    return any(
        hint in blob
        for hint in (
            "unsupported",
            "not supported",
            "invalid type",
            "unknown type",
        )
    )


def _moonshot_host(base_url: str) -> bool:
    hostname = urlsplit(base_url).hostname or ""
    host = hostname.casefold().rstrip(".")
    return host in _MOONSHOT_HOSTS or host.endswith(_MOONSHOT_SUFFIXES)
