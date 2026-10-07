"""Sanitize provider model-list rows into metadata-only descriptors."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from .contracts import (
    CAPABILITY_NAME_SET,
    CapabilityEvidence,
    CapabilityEvidenceSource,
    CapabilityStatus,
    ModelCapability,
    ModelMetadata,
    ProviderModelDescriptor,
)


def descriptor_from_provider_row(value: Any) -> ProviderModelDescriptor | None:
    """Accept only documented, safe fields from a Provider /models row.

    Model ids and endpoint names do not imply capability support. Capabilities
    are retained only when the Provider explicitly supplies a recognized
    capability key with a boolean or supported/unsupported value.
    """
    if not isinstance(value, Mapping):
        return None
    model_id = value.get("id", value.get("provider_model_id"))
    if not isinstance(model_id, str):
        return None
    model_id = model_id.strip()
    if not model_id or len(model_id) > 512:
        return None
    name = value.get("display_name")
    display_name = name.strip() if isinstance(name, str) and name.strip() else model_id
    display_name = display_name[:200]
    metadata = ModelMetadata.from_mapping(value)
    capabilities = _provider_capabilities(value.get("capabilities"))
    return ProviderModelDescriptor(
        provider_model_id=model_id,
        display_name=display_name,
        metadata=metadata,
        capabilities=capabilities,
    )


def normalize_provider_models(values: Any) -> tuple[ProviderModelDescriptor, ...]:
    """Normalize IDs, descriptors, or raw response objects deterministically."""
    if values is None or isinstance(values, str | bytes | bytearray):
        raise ValueError("Provider model list must be a sequence")
    try:
        rows = list(values)
    except TypeError as exc:
        raise ValueError("Provider model list must be a sequence") from exc
    deduplicated: dict[str, ProviderModelDescriptor] = {}
    for value in rows:
        descriptor: ProviderModelDescriptor | None
        if isinstance(value, ProviderModelDescriptor):
            descriptor = _normalize_descriptor(value)
        elif isinstance(value, str):
            descriptor = descriptor_from_provider_row({"id": value})
        else:
            descriptor = descriptor_from_provider_row(value)
        if descriptor is not None:
            deduplicated[descriptor.provider_model_id] = descriptor
    return tuple(deduplicated[key] for key in sorted(deduplicated))


def _normalize_descriptor(value: ProviderModelDescriptor) -> ProviderModelDescriptor:
    return descriptor_from_provider_row(
        {
            "id": value.provider_model_id,
            "display_name": value.display_name,
            **value.metadata.to_dict(),
            "capabilities": {
                name: capability.status.value
                for name, capability in value.capabilities.items()
                if name in CAPABILITY_NAME_SET
                and capability.status is not CapabilityStatus.UNKNOWN
            },
        }
    ) or ProviderModelDescriptor(value.provider_model_id, value.display_name)


def _provider_capabilities(value: Any) -> dict[str, ModelCapability]:
    if not isinstance(value, Mapping):
        return {}
    observed_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    result: dict[str, ModelCapability] = {}
    for raw_name, raw_status in value.items():
        if not isinstance(raw_name, str) or raw_name not in CAPABILITY_NAME_SET:
            continue
        status = _explicit_status(raw_status)
        if status is None:
            continue
        result[raw_name] = ModelCapability(
            status=status,
            evidence=CapabilityEvidence(
                source=CapabilityEvidenceSource.PROVIDER_METADATA,
                observed_at=observed_at,
                detail="Provider model metadata explicitly declared this capability.",
            ),
        )
    return result


def _explicit_status(value: Any) -> CapabilityStatus | None:
    if value is True or value == "supported":
        return CapabilityStatus.SUPPORTED
    if value is False or value == "unsupported":
        return CapabilityStatus.UNSUPPORTED
    return None
