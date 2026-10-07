"""Wire-safe contracts for configured model profiles and their capabilities."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class CapabilityStatus(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class CapabilityEvidenceSource(StrEnum):
    PROVIDER_METADATA = "provider_metadata"
    PROVIDER_ADAPTER = "provider_adapter"
    ACTIVE_PROBE = "active_probe"
    USER_DECLARED = "user_declared"
    INFERRED = "inferred"


class ModelVerificationState(StrEnum):
    UNKNOWN = "unknown"
    DECLARED = "declared"
    VERIFIED = "verified"
    FAILED = "failed"
    STALE = "stale"


class ModelResolutionStatus(StrEnum):
    ALREADY_BOUND = "already_bound"
    WILL_BIND = "will_bind"
    NEEDS_SETUP = "needs_setup"
    MISSING_CAPABILITY = "missing_capability"
    UNSUPPORTED = "unsupported"


CAPABILITY_NAMES = (
    "text_input",
    "image_input",
    "audio_input",
    "video_input",
    "text_generation",
    "image_generation",
    "image_editing",
    "audio_generation",
    "video_generation",
    "structured_output",
    "tool_calling",
    "reasoning",
    "speech_to_text",
    "text_to_speech",
    "embeddings",
    "reranking",
)
CAPABILITY_NAME_SET = frozenset(CAPABILITY_NAMES)
_ROLE_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")


@dataclass(frozen=True)
class CapabilityEvidence:
    source: CapabilityEvidenceSource
    observed_at: str
    detail: str | None = None

    def to_dict(self) -> dict[str, str]:
        result = {"source": self.source.value, "observed_at": self.observed_at}
        if self.detail:
            result["detail"] = self.detail
        return result


@dataclass(frozen=True)
class ModelCapability:
    status: CapabilityStatus = CapabilityStatus.UNKNOWN
    evidence: CapabilityEvidence | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "evidence": self.evidence.to_dict() if self.evidence else None,
        }


@dataclass(frozen=True)
class ModelMetadata:
    """Safe descriptive metadata, kept separate from executable capabilities."""

    context_window: int | None = None
    max_output_tokens: int | None = None
    modalities: tuple[str, ...] = ()
    provider_family: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> ModelMetadata:
        if not isinstance(value, Mapping):
            return cls()
        context_window = _positive_int(value.get("context_window"))
        max_output_tokens = _positive_int(value.get("max_output_tokens"))
        modalities_raw = value.get("modalities")
        modalities = (
            tuple(
                sorted(
                    {
                        item.strip().lower()
                        for item in modalities_raw
                        if isinstance(item, str)
                        and item.strip().lower() in {"text", "image", "audio", "video"}
                    }
                )
            )
            if isinstance(modalities_raw, list | tuple | set)
            else ()
        )
        provider_family = value.get("provider_family")
        if not isinstance(provider_family, str) or not provider_family.strip():
            provider_family = None
        else:
            provider_family = provider_family.strip()[:80]
        return cls(
            context_window=context_window,
            max_output_tokens=max_output_tokens,
            modalities=modalities,
            provider_family=provider_family,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.context_window is not None:
            result["context_window"] = self.context_window
        if self.max_output_tokens is not None:
            result["max_output_tokens"] = self.max_output_tokens
        if self.modalities:
            result["modalities"] = list(self.modalities)
        if self.provider_family is not None:
            result["provider_family"] = self.provider_family
        return result


@dataclass(frozen=True)
class ModelVerification:
    state: ModelVerificationState = ModelVerificationState.UNKNOWN
    source: CapabilityEvidenceSource | None = None
    verified_at: str | None = None
    last_checked_at: str | None = None
    stale_reason: str | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "source": self.source.value if self.source else None,
            "verified_at": self.verified_at,
            "last_checked_at": self.last_checked_at,
            "stale_reason": self.stale_reason,
            "error_code": self.error_code,
        }


@dataclass(frozen=True)
class ProviderModelDescriptor:
    """Sanitized model-list row; raw Provider responses never enter persistence."""

    provider_model_id: str
    display_name: str
    metadata: ModelMetadata = field(default_factory=ModelMetadata)
    capabilities: Mapping[str, ModelCapability] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelProfile:
    model_profile_id: str
    provider_connection_id: str
    provider_type: str
    provider_label: str
    provider_model_id: str
    display_name: str
    enabled: bool
    listed: bool
    metadata: ModelMetadata
    capabilities: Mapping[str, ModelCapability]
    verification: ModelVerification
    capability_revision: int
    capability_digest: str
    discovered_at: str | None
    created_at: str
    updated_at: str
    connection_readiness: str
    registry_ready: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_profile_id": self.model_profile_id,
            "provider_connection_id": self.provider_connection_id,
            "provider_type": self.provider_type,
            "provider_label": self.provider_label,
            "provider_model_id": self.provider_model_id,
            "display_name": self.display_name,
            "enabled": self.enabled,
            "listed": self.listed,
            "metadata": self.metadata.to_dict(),
            "capabilities": {
                name: self.capabilities.get(name, ModelCapability()).to_dict()
                for name in CAPABILITY_NAMES
            },
            "verification": self.verification.to_dict(),
            "capability_revision": self.capability_revision,
            "capability_digest": self.capability_digest,
            "discovered_at": self.discovered_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "connection_readiness": self.connection_readiness,
            "registry_ready": self.registry_ready,
        }


@dataclass(frozen=True)
class ModelRoleDefault:
    role: str
    model_profile_id: str
    provider_connection_id: str
    provider_model_id: str
    capability_digest: str
    capability_revision: int
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "model_profile_id": self.model_profile_id,
            "provider_connection_id": self.provider_connection_id,
            "provider_model_id": self.provider_model_id,
            "capability_digest": self.capability_digest,
            "capability_revision": self.capability_revision,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ModelCapabilityRequirement:
    slot: str
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    reason: str = ""
    source: str = ""
    required_for_run: bool = True
    actor_id: str | None = None

    def __post_init__(self) -> None:
        if not self.slot.strip():
            raise ValueError("Model requirement slot must not be empty")
        required = _capability_names(self.required, "required")
        optional = _capability_names(self.optional, "optional")
        if set(required) & set(optional):
            raise ValueError("Model capability cannot be both required and optional")
        object.__setattr__(self, "required", required)
        object.__setattr__(self, "optional", optional)

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "required": list(self.required),
            "optional": list(self.optional),
            "reason": self.reason,
            "source": self.source,
            "actor_id": self.actor_id,
        }


@dataclass(frozen=True)
class ModelResolutionIssue:
    code: str
    message: str
    missing: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()
    unsupported: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "missing": list(self.missing),
            "unknown": list(self.unknown),
            "unsupported": list(self.unsupported),
        }


@dataclass(frozen=True)
class ModelResolution(ModelCapabilityRequirement):
    status: ModelResolutionStatus = ModelResolutionStatus.NEEDS_SETUP
    selected_model_profile_id: str | None = None
    selected_model_display_name: str | None = None
    selected_provider_label: str | None = None
    issue: ModelResolutionIssue | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **super().to_dict(),
            "status": self.status.value,
            "selected_model_profile_id": self.selected_model_profile_id,
            "selected_model_display_name": self.selected_model_display_name,
            "selected_provider_label": self.selected_provider_label,
            "issue": self.issue.to_dict() if self.issue else None,
        }


def default_capabilities(
    *, source: CapabilityEvidenceSource | None = None, observed_at: str | None = None
) -> dict[str, ModelCapability]:
    if source is None or observed_at is None:
        return {name: ModelCapability() for name in CAPABILITY_NAMES}
    evidence = CapabilityEvidence(source=source, observed_at=observed_at)
    return {name: ModelCapability(evidence=evidence) for name in CAPABILITY_NAMES}


def capability_map_to_dict(
    value: Mapping[str, ModelCapability],
) -> dict[str, dict[str, Any]]:
    return {
        name: value.get(name, ModelCapability()).to_dict() for name in CAPABILITY_NAMES
    }


def _capability_names(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(values))
    invalid = [name for name in normalized if name not in CAPABILITY_NAME_SET]
    if invalid:
        raise ValueError(f"Unknown {field_name} model capabilities: {invalid}")
    return normalized


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return int(value)
