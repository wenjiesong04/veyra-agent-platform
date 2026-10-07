"""Runtime modality view backed only by a verified Model Registry profile.

RuntimeSettings describe a connection target, not model capabilities. Unknown
or missing Registry evidence therefore remains unknown; model names and host
names are never used to infer support.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from veyra_agent_platform.local.runtime.config import RuntimeSettings

CapabilityState = Literal["supported", "unsupported", "unknown"]
ProfileSource = Literal["registry", "unknown", "static_profile"]
_VERIFIED_EVIDENCE = frozenset(
    {"provider_metadata", "provider_adapter", "active_probe"}
)


@dataclass(frozen=True)
class RuntimeModelCapabilities:
    provider: str
    model_id: str
    text_input: CapabilityState
    image_input: CapabilityState
    video_input: CapabilityState
    audio_input: CapabilityState
    structured_json_output: CapabilityState
    source: ProfileSource

    def to_dict(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "text_input": self.text_input,
            "image_input": self.image_input,
            "video_input": self.video_input,
            "audio_input": self.audio_input,
            "structured_json_output": self.structured_json_output,
            "source": self.source,
        }


def runtime_model_capabilities(
    settings: RuntimeSettings, profile: Any | None = None
) -> RuntimeModelCapabilities:
    """Adapt a verified Registry profile for the legacy Runtime content helper.

    The helper still uses ``unsupported`` to avoid serializing a declared image
    into a model request. All run/readiness authorization is performed by the
    Registry-backed preflight in RuntimeService.
    """

    if profile is not None:
        ready = (
            getattr(profile, "registry_ready", False) is True
            and getattr(profile, "enabled", False) is True
        )
        capability_map = getattr(profile, "capabilities", {})

        def value(name: str) -> CapabilityState:
            if not ready or not isinstance(capability_map, Mapping):
                return "unknown"
            record = capability_map.get(name)
            status = (
                record.get("status")
                if isinstance(record, Mapping)
                else getattr(record, "status", None)
            )
            status = getattr(status, "value", status)
            evidence = (
                record.get("evidence")
                if isinstance(record, Mapping)
                else getattr(record, "evidence", None)
            )
            if status not in {"supported", "unsupported", "unknown"}:
                return "unknown"
            evidence_source = (
                evidence.get("source")
                if isinstance(evidence, Mapping)
                else getattr(evidence, "source", None)
            )
            evidence_source = getattr(evidence_source, "value", evidence_source)
            if evidence_source not in _VERIFIED_EVIDENCE:
                return "unknown"
            if status == "supported":
                return "supported"
            if status == "unsupported":
                return "unsupported"
            return "unknown"

        return RuntimeModelCapabilities(
            provider=str(getattr(profile, "provider_type", "registry")),
            model_id=str(getattr(profile, "provider_model_id", settings.model_id)),
            text_input=value("text_input"),
            image_input=value("image_input"),
            video_input=value("video_input"),
            audio_input=value("audio_input"),
            structured_json_output=value("structured_output"),
            source="registry" if ready else "unknown",
        )
    return RuntimeModelCapabilities(
        provider="unknown",
        model_id=settings.model_id.strip(),
        text_input="unknown",
        image_input="unknown",
        video_input="unsupported",
        audio_input="unsupported",
        structured_json_output="unknown",
        source="unknown",
    )
