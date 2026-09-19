"""Project-scoped conversational Factory and Kimi provider boundary."""

from .capability_profile import (
    ProviderCapabilityProfile,
    derive_provider_capability_profile,
)
from .client import (
    FactoryProviderError,
    FactoryProviderNotConfigured,
    KimiClient,
    KimiCompletion,
    KimiTransport,
)
from .config import FactorySettings
from .service import FactoryError, FactoryService

__all__ = [
    "FactoryError",
    "FactoryProviderError",
    "FactoryProviderNotConfigured",
    "FactoryService",
    "FactorySettings",
    "KimiClient",
    "KimiCompletion",
    "KimiTransport",
    "ProviderCapabilityProfile",
    "derive_provider_capability_profile",
]
