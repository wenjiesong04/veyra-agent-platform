from __future__ import annotations

import json
from pathlib import Path

import pytest

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.local.runtime.client import (
    RuntimeProviderError,
    _assert_provider_safe_messages,
)
from veyra_agent_platform.local.runtime.config import RuntimeSettings
from veyra_agent_platform.local.runtime.model_capabilities import (
    RuntimeModelCapabilities,
    runtime_model_capabilities,
)
from veyra_agent_platform.local.runtime.service import (
    RuntimeError,
    _agent_user_content,
    _runtime_modality_readiness,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "contracts" / "fixtures" / "valid" / "approval-gate.vagent.yaml"


def _source(**overrides: object) -> AgentSource:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data.update(overrides)
    return AgentSource.from_dict(data)


def _supported() -> RuntimeModelCapabilities:
    return RuntimeModelCapabilities(
        provider="scripted",
        model_id="vision-test",
        text_input="supported",
        image_input="supported",
        structured_json_output="supported",
        source="static_profile",
    )


def test_kimi_k3_image_input_is_unsupported() -> None:
    profile = runtime_model_capabilities(
        RuntimeSettings(
            model_base_url="https://api.moonshot.cn/v1",
            model_id="kimi-k3",
        )
    )
    assert profile.image_input == "unsupported"
    assert profile.source == "static_profile"


def test_unknown_image_input_is_not_supported() -> None:
    profile = runtime_model_capabilities(
        RuntimeSettings(
            model_base_url="https://api.example.test/v1",
            model_id="mystery-model",
        )
    )
    assert profile.image_input == "unknown"
    assert profile.image_input != "supported"


def test_image_agent_readiness_fails_for_kimi_k3() -> None:
    source = _source(inputs={"photo": "image"})
    profile = runtime_model_capabilities(RuntimeSettings())
    check = _runtime_modality_readiness(source, True, profile)
    assert check["ready"] is False
    assert check["code"] == "runtime_model_incompatible"
    assert check["detail"] == "Runtime model does not support image input"


def test_unknown_image_support_is_incompatible() -> None:
    source = _source(inputs={"photo": "image"})
    check = _runtime_modality_readiness(
        source,
        True,
        RuntimeModelCapabilities(
            provider="unknown",
            model_id="mystery-model",
            text_input="supported",
            image_input="unknown",
            structured_json_output="unknown",
            source="unknown",
        ),
    )
    assert check["ready"] is False
    assert check["code"] == "runtime_model_incompatible"


def test_audio_is_unsupported_modality() -> None:
    source = _source(inputs={"clip": "audio"})
    check = _runtime_modality_readiness(source, True, _supported())
    assert check["ready"] is False
    assert check["code"] == "unsupported_modality"


def test_user_content_keeps_text_when_no_image() -> None:
    source = _source()
    content = _agent_user_content(source, {"request": "hello"}, _supported())
    assert content == "request: hello"


def test_supported_image_parts_use_artifact_url_not_host_path() -> None:
    source = _source(inputs={"photo": "image"})
    ref = {
        "kind": "artifact",
        "artifact_id": "art_demo",
        "media_type": "image/png",
        "filename": "product.png",
    }
    content = _agent_user_content(source, {"photo": ref}, _supported())
    assert isinstance(content, list)
    image = content[1]["image_url"]
    assert image["url"] == "artifact://art_demo"
    dumped = json.dumps(content)
    assert "file:" not in dumped
    assert "/Users" not in dumped
    assert "product.png" in dumped


def test_unsupported_image_content_fails_before_provider() -> None:
    source = _source(inputs={"photo": "image"})
    ref = {
        "kind": "artifact",
        "artifact_id": "art_demo",
        "media_type": "image/png",
        "filename": "product.png",
    }
    profile = runtime_model_capabilities(RuntimeSettings())
    with pytest.raises(RuntimeError, match="does not support image input") as caught:
        _agent_user_content(source, {"photo": ref}, profile)
    assert caught.value.code == "runtime_model_incompatible"


def test_http_boundary_rejects_host_and_artifact_urls() -> None:
    with pytest.raises(RuntimeProviderError) as caught:
        _assert_provider_safe_messages(
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": "file:///tmp/secret.png"},
                        }
                    ],
                }
            ]
        )
    assert caught.value.code == "runtime_request_invalid"
    with pytest.raises(RuntimeProviderError):
        _assert_provider_safe_messages(
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": "artifact://art_demo"},
                        }
                    ],
                }
            ]
        )
