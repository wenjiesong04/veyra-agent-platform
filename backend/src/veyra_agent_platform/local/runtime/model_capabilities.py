"""Runtime model modality profile. Separate from Builder ProviderCapabilityProfile.

Exact model ids only. Substring guessing is forbidden.
Known text-only models stay closed for image input. Vision models and any
other user-bound Runtime model stay open so the Provider can accept or reject.
Audio/video adapters are a separate Runtime gap, not a model-id guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from veyra_agent_platform.local.runtime.config import RuntimeSettings

CapabilityState = Literal["supported", "unsupported", "unknown"]
ProfileSource = Literal["static_profile", "unknown"]

_MOONSHOT_HOSTS = frozenset({"api.moonshot.cn", "api.moonshot.ai"})
_TEXT_ONLY_MODELS = frozenset({"kimi-k2", "moonshot-v1-8k", "moonshot-v1-32k"})
_VISION_MODELS = frozenset(
    {
        "kimi-k3",
        "kimi-k2.6",
        "kimi-k2.7-code",
        "kimi-k2.7-code-highspeed",
    }
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


def runtime_model_capabilities(settings: RuntimeSettings) -> RuntimeModelCapabilities:
    host = (urlsplit(settings.model_base_url).hostname or "").casefold()
    model_id = settings.model_id.strip()
    key = model_id.casefold()
    moonshot = host in _MOONSHOT_HOSTS
    provider = "moonshot" if moonshot else "unknown"
    if key in _TEXT_ONLY_MODELS and moonshot:
        return RuntimeModelCapabilities(
            provider=provider,
            model_id=model_id,
            text_input="supported",
            image_input="unsupported",
            video_input="unsupported",
            audio_input="unsupported",
            structured_json_output="supported",
            source="static_profile",
        )
    if key in _VISION_MODELS and moonshot:
        return RuntimeModelCapabilities(
            provider=provider,
            model_id=model_id,
            text_input="supported",
            image_input="supported",
            video_input="unsupported",
            audio_input="unsupported",
            structured_json_output="supported",
            source="static_profile",
        )
    return RuntimeModelCapabilities(
        provider=provider,
        model_id=model_id,
        text_input="supported",
        image_input="supported",
        video_input="unsupported",
        audio_input="unsupported",
        structured_json_output="unknown",
        source="unknown",
    )
