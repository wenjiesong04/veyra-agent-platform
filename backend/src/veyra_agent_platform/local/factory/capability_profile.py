"""Declare Factory provider structured-output capabilities without probing.

The profile is derived from the configured Factory base URL. It is not a live
`/v1/models` structured-output probe, host secret readiness, or a successful Run.
Unknown OpenAI-compatible hosts fail closed: json_object only, no Moonshot
schema projection, and no reasoning_effort.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from .config import FactorySettings
from .structured_schema import project_moonshot_json_schema

ProviderFamily = Literal["moonshot", "openai_compatible"]
StructuredOutput = Literal["json_schema", "json_object"]
SchemaFlavor = Literal["moonshot_mfjs", "none"]
ProfileSource = Literal["host_defaults"]

_MOONSHOT_HOSTS = frozenset({"api.moonshot.cn", "api.moonshot.ai"})
_MOONSHOT_SUFFIXES = (".moonshot.cn", ".moonshot.ai")


@dataclass(frozen=True)
class ProviderCapabilityProfile:
    provider_family: ProviderFamily
    structured_output: StructuredOutput
    schema_flavor: SchemaFlavor
    strict_json_schema: bool
    json_object_fallback: bool
    reasoning_effort: bool
    source: ProfileSource
    probed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "provider_family": self.provider_family,
            "structured_output": self.structured_output,
            "schema_flavor": self.schema_flavor,
            "strict_json_schema": self.strict_json_schema,
            "json_object_fallback": self.json_object_fallback,
            "reasoning_effort": self.reasoning_effort,
            "source": self.source,
            "probed": self.probed,
        }


def derive_provider_capability_profile(
    settings: FactorySettings,
) -> ProviderCapabilityProfile:
    if _moonshot_host(settings.model_base_url):
        return ProviderCapabilityProfile(
            provider_family="moonshot",
            structured_output="json_schema",
            schema_flavor="moonshot_mfjs",
            strict_json_schema=True,
            json_object_fallback=True,
            reasoning_effort=True,
            source="host_defaults",
            probed=False,
        )
    return ProviderCapabilityProfile(
        provider_family="openai_compatible",
        structured_output="json_object",
        schema_flavor="none",
        strict_json_schema=False,
        json_object_fallback=False,
        reasoning_effort=False,
        source="host_defaults",
        probed=False,
    )


def structured_response_format(
    profile: ProviderCapabilityProfile,
    *,
    name: str,
    schema: Mapping[str, Any],
) -> dict[str, Any]:
    if profile.structured_output != "json_schema":
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


def _moonshot_host(base_url: str) -> bool:
    hostname = urlsplit(base_url).hostname or ""
    host = hostname.casefold().rstrip(".")
    return host in _MOONSHOT_HOSTS or host.endswith(_MOONSHOT_SUFFIXES)
