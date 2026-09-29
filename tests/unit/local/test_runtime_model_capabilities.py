from __future__ import annotations

import json
from pathlib import Path

import pytest

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.typed_io import parse_typed_fields
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
    _bind_blank_approval_condition,
    _model_writes_agent_outputs,
    _readiness_profile_source,
    _runtime_modality_readiness,
    _runtime_response_format,
    _with_output_contract,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "contracts" / "fixtures" / "valid" / "approval-gate.vagent.yaml"


def _source(**overrides: object) -> AgentSource:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data.update(overrides)
    return AgentSource.from_dict(data)


def _graph_source(**overrides: object) -> AgentSource:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    extensions = json.loads(json.dumps(data["extensions"]))
    extensions["veyra"]["verification"] = {"required": False, "checks": []}
    data["extensions"] = extensions
    data.update(overrides)
    return AgentSource.from_dict(data)


def _supported() -> RuntimeModelCapabilities:
    return RuntimeModelCapabilities(
        provider="scripted",
        model_id="vision-test",
        text_input="supported",
        image_input="supported",
        video_input="unsupported",
        audio_input="unsupported",
        structured_json_output="supported",
        source="static_profile",
    )


def test_kimi_k3_image_input_is_supported() -> None:
    profile = runtime_model_capabilities(
        RuntimeSettings(
            model_base_url="https://api.moonshot.cn/v1",
            model_id="kimi-k3",
        )
    )
    assert profile.image_input == "supported"
    assert profile.video_input == "unsupported"
    assert profile.source == "static_profile"


def test_other_user_runtime_models_accept_image_input() -> None:
    profile = runtime_model_capabilities(
        RuntimeSettings(
            model_base_url="https://api.openai.com/v1",
            model_id="gpt-4o",
        )
    )
    assert profile.image_input == "supported"
    assert profile.source == "unknown"


def test_known_text_only_moonshot_models_reject_image_input() -> None:
    profile = runtime_model_capabilities(
        RuntimeSettings(
            model_base_url="https://api.moonshot.cn/v1",
            model_id="moonshot-v1-8k",
        )
    )
    assert profile.image_input == "unsupported"
    assert profile.source == "static_profile"


def test_readiness_profile_source_maps_binding_origins() -> None:
    assert _readiness_profile_source("explicit") == "agent"
    assert _readiness_profile_source("project") == "project"
    assert _readiness_profile_source("user_default") == "default"
    assert _readiness_profile_source("default") == "default"


def test_image_agent_readiness_passes_for_kimi_k3() -> None:
    source = _source(inputs={"photo": "image"})
    profile = runtime_model_capabilities(RuntimeSettings())
    check = _runtime_modality_readiness(source, True, profile)
    assert check["ready"] is True
    assert check["code"] == "ready"


def test_image_agent_readiness_fails_for_text_only_model() -> None:
    source = _source(inputs={"photo": "image"})
    check = _runtime_modality_readiness(
        source,
        True,
        runtime_model_capabilities(
            RuntimeSettings(
                model_base_url="https://api.moonshot.cn/v1",
                model_id="kimi-k2",
            )
        ),
    )
    assert check["ready"] is False
    assert check["code"] == "runtime_model_incompatible"


def test_pdf_document_and_file_inputs_are_ready() -> None:
    profile = runtime_model_capabilities(RuntimeSettings())
    for kind in ("pdf", "document", "file"):
        check = _runtime_modality_readiness(
            _source(inputs={"brief": kind}), True, profile
        )
        assert check["ready"] is True


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


def test_text_only_image_content_fails_before_provider() -> None:
    source = _source(inputs={"photo": "image"})
    ref = {
        "kind": "artifact",
        "artifact_id": "art_demo",
        "media_type": "image/png",
        "filename": "product.png",
    }
    profile = runtime_model_capabilities(
        RuntimeSettings(
            model_base_url="https://api.moonshot.cn/v1",
            model_id="moonshot-v1-32k",
        )
    )
    with pytest.raises(RuntimeError, match="does not support image input") as caught:
        _agent_user_content(source, {"photo": ref}, profile)
    assert caught.value.code == "runtime_model_incompatible"


def test_extracted_document_text_stays_in_prompt() -> None:
    source = _source(inputs={"brief": "document"})
    ref = {
        "kind": "artifact",
        "artifact_id": "art_doc",
        "media_type": "text/plain",
        "filename": "notes.txt",
    }
    content = _agent_user_content(
        source, {"brief": ref}, _supported(), {"brief": "圣诞晚会包装要点"}
    )
    assert isinstance(content, str)
    assert "notes.txt" in content
    assert "圣诞晚会包装要点" in content
    assert "art_doc" not in content


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


def test_structured_outputs_request_json_object() -> None:
    outputs = parse_typed_fields(
        {
            "final-packaging-design": "object",
            "image-generation-prompts": "array",
        },
        "outputs",
    )
    assert _runtime_response_format(outputs) == {"type": "json_object"}
    prompt = _with_output_contract("Analyze the item.", outputs)
    assert "final-packaging-design (object)" in prompt
    assert "image-generation-prompts (array)" in prompt


def test_single_string_output_does_not_force_json() -> None:
    outputs = parse_typed_fields({"result": "string"}, "outputs")
    assert _runtime_response_format(outputs) is None
    assert _with_output_contract("Reply plainly.", outputs) == "Reply plainly."


def test_only_the_model_before_output_writes_agent_fields() -> None:
    source = _graph_source(
        inputs={"request": "string", "decision": "string"},
        outputs={"final-design": "object", "prompts": "array"},
        nodes=[
            {"id": "start", "component_type": "Start"},
            {
                "id": "analyze",
                "component_type": "Model",
                "model_ref": "model.primary",
                "system_prompt": "Analyze.",
            },
            {
                "id": "finalize",
                "component_type": "Model",
                "model_ref": "model.primary",
                "system_prompt": "Finalize.",
            },
            {
                "id": "output",
                "component_type": "Output",
                "output_name": "final-design",
            },
        ],
        transitions=[
            {"from": "start", "port": "next", "to": "analyze"},
            {"from": "analyze", "port": "next", "to": "finalize"},
            {"from": "finalize", "port": "next", "to": "output"},
        ],
        ui={
            "positions": {
                "start": {"x": 0, "y": 0},
                "analyze": {"x": 120, "y": 0},
                "finalize": {"x": 240, "y": 0},
                "output": {"x": 360, "y": 0},
            }
        },
    )
    assert _model_writes_agent_outputs(source, "analyze") is False
    assert _model_writes_agent_outputs(source, "finalize") is True


def test_blank_approval_selects_the_confirm_branch() -> None:
    source = _graph_source(
        inputs={"decision": "string"},
        outputs={"result": "string"},
        nodes=[
            {"id": "start", "component_type": "Start"},
            {
                "id": "choose",
                "component_type": "HumanApproval",
                "prompt": "Confirm?",
            },
            {
                "id": "route",
                "component_type": "Condition",
                "expression": 'decision == "confirm"',
            },
            {"id": "output", "component_type": "Output", "output_name": "result"},
        ],
        transitions=[
            {"from": "start", "port": "next", "to": "choose"},
            {"from": "choose", "port": "approved", "to": "route"},
            {"from": "choose", "port": "rejected", "to": "output"},
            {"from": "route", "port": "true", "to": "output"},
            {"from": "route", "port": "false", "to": "output"},
        ],
        ui={
            "positions": {
                "start": {"x": 0, "y": 0},
                "choose": {"x": 120, "y": 0},
                "route": {"x": 240, "y": 0},
                "output": {"x": 360, "y": 0},
            }
        },
    )
    bound = _bind_blank_approval_condition(
        source, "route", "approved", {"decision": ""}
    )
    assert bound["decision"] == "confirm"
    kept = _bind_blank_approval_condition(
        source, "route", "approved", {"decision": "change the color"}
    )
    assert kept["decision"] == "change the color"
