from __future__ import annotations

import json
from pathlib import Path

import pytest

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.local.runtime.service import RuntimeError, RuntimeService

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "contracts" / "fixtures" / "valid" / "approval-gate.vagent.yaml"


def _source(**overrides: object) -> AgentSource:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data.update(overrides)
    return AgentSource.from_dict(data)


def test_legacy_string_inputs_still_validate() -> None:
    source = _source()
    RuntimeService._validate_inputs(source, {"request": "hello"})


def test_image_input_rejects_plain_string() -> None:
    source = _source(inputs={"request": "image"})
    with pytest.raises(RuntimeError, match="must be a image") as caught:
        RuntimeService._validate_inputs(source, {"request": "not-an-image"})
    assert caught.value.code == "inputs_invalid"


def test_image_input_accepts_artifact_ref_shape() -> None:
    source = _source(inputs={"request": "image"})
    RuntimeService._validate_inputs(
        source,
        {
            "request": {
                "kind": "artifact",
                "artifact_id": "art_demo",
                "media_type": "image/png",
                "filename": "product.png",
            }
        },
    )


def test_pdf_output_rejects_string_as_pdf() -> None:
    source = _source(outputs={"decision": "pdf", "rejected": "string"})
    with pytest.raises(RuntimeError) as caught:
        RuntimeService._validated_outputs(
            source, {"decision": "this is a PDF", "rejected": "no"}
        )
    assert caught.value.code == "output_type_invalid"


def test_optional_input_may_be_omitted() -> None:
    source = _source(
        inputs={
            "request": "string",
            "budget": {"type": "number", "required": False},
        }
    )
    RuntimeService._validate_inputs(source, {"request": "hello"})
