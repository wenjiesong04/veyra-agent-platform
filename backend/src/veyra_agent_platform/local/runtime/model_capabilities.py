"""Runtime model modality profile. Separate from Builder ProviderCapabilityProfile.

Unknown is not treated as supported. Model id substring guessing is forbidden.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from veyra_agent_platform.local.runtime.config import RuntimeSettings

CapabilityState = Literal["supported", "unsupported", "unknown"]
ProfileSource = Literal["static_profile", "unknown"]

_MOONSHOT_HOSTS = frozenset({"api.moonshot.cn", "api.moonshot.ai"})
_KIMI_TEXT_MODELS = frozenset(
    {"kimi-k3", "kimi-k2", "moonshot-v1-8k", "moonshot-v1-32k"}
)


@dataclass(frozen=True)
class RuntimeModelCapabilities:
    provider: str
    model_id: str
    text_input: CapabilityState
    image_input: CapabilityState
    structured_json_output: CapabilityState
    source: ProfileSource

    def to_dict(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "text_input": self.text_input,
            "image_input": self.image_input,
            "structured_json_output": self.structured_json_output,
            "source": self.source,
        }


def runtime_model_capabilities(settings: RuntimeSettings) -> RuntimeModelCapabilities:
    host = (urlsplit(settings.model_base_url).hostname or "").casefold()
    model_id = settings.model_id.strip()
    if host in _MOONSHOT_HOSTS and model_id.casefold() in _KIMI_TEXT_MODELS:
        return RuntimeModelCapabilities(
            provider="moonshot",
            model_id=model_id,
            text_input="supported",
            image_input="unsupported",
            structured_json_output="supported",
            source="static_profile",
        )
    if host in _MOONSHOT_HOSTS:
        return RuntimeModelCapabilities(
            provider="moonshot",
            model_id=model_id,
            text_input="supported",
            image_input="unknown",
            structured_json_output="unknown",
            source="unknown",
        )
    return RuntimeModelCapabilities(
        provider="unknown",
        model_id=model_id,
        text_input="supported",
        image_input="unknown",
        structured_json_output="unknown",
        source="unknown",
    )
