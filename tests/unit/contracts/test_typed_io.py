from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.typed_io import (
    looks_like_artifact_ref,
    parse_typed_field,
    parse_typed_fields,
    typed_fields_to_wire,
    value_matches_field,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "contracts" / "fixtures" / "valid" / "github-triage.vagent.yaml"


def test_legacy_compact_string_map_parses_and_round_trips() -> None:
    fields = parse_typed_fields({"text": "string", "count": "integer"}, "inputs")
    assert fields["text"].type == "string"
    assert fields["text"].required is True
    assert fields["count"].type == "integer"
    assert typed_fields_to_wire(fields) == {"text": "string", "count": "integer"}


def test_legacy_agent_source_keeps_compact_wire_and_behavior_hash() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source = AgentSource.from_dict(data)
    dumped = source.to_dict()
    assert dumped["inputs"] == data["inputs"]
    assert dumped["outputs"] == data["outputs"]
    again = AgentSource.from_dict(dumped)
    assert again.behavior_hash == source.behavior_hash
    assert again.source_hash == source.source_hash


def test_rich_scalar_descriptor_compacts_when_equivalent() -> None:
    field = parse_typed_field({"type": "string", "required": True}, "inputs.text")
    assert field.to_wire() == "string"


def test_optional_and_multiple_stay_rich() -> None:
    fields = parse_typed_fields(
        {
            "budget": {"type": "number", "required": False},
            "photos": {"type": "image", "multiple": True},
        },
        "inputs",
    )
    assert typed_fields_to_wire(fields) == {
        "budget": {"type": "number", "required": False},
        "photos": {"type": "artifact", "artifact_kind": "image", "multiple": True},
    }


def test_compact_image_is_an_artifact_field() -> None:
    field = parse_typed_field("image", "inputs.photo")
    assert field.type == "artifact"
    assert field.artifact_kind == "image"
    assert field.accepted_media_types == ("image/*",)
    assert field.to_wire() == "image"


def test_artifact_descriptor_and_json_schema() -> None:
    fields = parse_typed_fields(
        {
            "photo": {
                "type": "artifact",
                "artifact_kind": "image",
                "description": "商品图片",
                "accepted_media_types": ["image/png", "image/jpeg"],
            },
            "metadata": {
                "type": "object",
                "json_schema": {"type": "object", "required": ["sku"]},
            },
        },
        "inputs",
    )
    wire = typed_fields_to_wire(fields)
    assert wire["photo"]["artifact_kind"] == "image"
    assert wire["photo"]["accepted_media_types"] == ["image/png", "image/jpeg"]
    assert wire["metadata"]["json_schema"]["required"] == ["sku"]


def test_unknown_legacy_type_is_rejected() -> None:
    with pytest.raises(ContractValidationError, match="not supported"):
        parse_typed_field("blob", "inputs.file")


def test_artifact_kind_is_required_for_artifact_type() -> None:
    with pytest.raises(ContractValidationError, match="artifact_kind"):
        parse_typed_field({"type": "artifact"}, "outputs.report")


def test_media_types_are_rejected_on_scalars() -> None:
    with pytest.raises(ContractValidationError, match="accepted_media_types"):
        parse_typed_field(
            {"type": "string", "accepted_media_types": ["text/plain"]},
            "inputs.text",
        )


def test_legacy_agent_source_accepts_rich_inputs() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["inputs"] = {
        "repository": {"type": "string", "required": True},
        "issue": "string",
    }
    source = AgentSource.from_dict(data)
    assert source.inputs["repository"].compact_type == "string"
    assert source.to_dict()["inputs"] == {"repository": "string", "issue": "string"}


def test_artifact_ref_shape_rejects_bytes_and_paths() -> None:
    valid = {
        "kind": "artifact",
        "artifact_id": "art_1",
        "media_type": "image/png",
        "filename": "product.png",
    }
    assert looks_like_artifact_ref(valid)
    assert looks_like_artifact_ref({"$artifact": "art_1"})
    assert not looks_like_artifact_ref({"$artifact": "art_1", "path": "/tmp"})
    assert not looks_like_artifact_ref("product.png")
    assert not looks_like_artifact_ref({**valid, "base64": "aaaa"})
    assert not looks_like_artifact_ref({**valid, "path": "/tmp/product.png"})


def test_value_matches_field_does_not_collapse_image_to_string() -> None:
    field = parse_typed_field("image", "inputs.photo")
    assert not value_matches_field(field, "a photo")
    assert value_matches_field(
        field,
        {
            "kind": "artifact",
            "artifact_id": "art_1",
            "media_type": "image/png",
            "filename": "product.png",
        },
    )
    assert not value_matches_field(
        field,
        {
            "kind": "artifact",
            "artifact_id": "art_1",
            "media_type": "application/pdf",
            "filename": "product.pdf",
        },
    )


def test_multiple_artifact_fields_need_a_list_of_refs() -> None:
    field = parse_typed_field({"type": "image", "multiple": True}, "inputs.photos")
    ref = {
        "kind": "artifact",
        "artifact_id": "art_1",
        "media_type": "image/jpeg",
        "filename": "a.jpg",
    }
    assert value_matches_field(field, [ref, deepcopy(ref)])
    assert not value_matches_field(field, ref)
