"""Local Model Capability Registry contracts and storage services."""

from .contracts import (
    CAPABILITY_NAMES,
    CapabilityEvidence,
    CapabilityEvidenceSource,
    CapabilityStatus,
    ModelCapability,
    ModelCapabilityRequirement,
    ModelMetadata,
    ModelProfile,
    ModelResolution,
    ModelRoleDefault,
    ModelVerification,
    ProviderModelDescriptor,
)
from .registry import ModelRegistry, ModelRegistryError

__all__ = [
    "CAPABILITY_NAMES",
    "CapabilityEvidence",
    "CapabilityEvidenceSource",
    "CapabilityStatus",
    "ModelCapability",
    "ModelCapabilityRequirement",
    "ModelMetadata",
    "ModelProfile",
    "ModelRegistry",
    "ModelRegistryError",
    "ModelResolution",
    "ModelRoleDefault",
    "ModelVerification",
    "ProviderModelDescriptor",
]
