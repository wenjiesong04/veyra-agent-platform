"""Golden hashes from d6e05af protect imported and committed definitions."""

import json
from pathlib import Path

import pytest

from veyra_agent_platform.contracts.agent import AgentSource

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "name,source_hash,behavior_hash",
    [
        (
            "github-triage",
            "87040aebd90ec79f95c64659c06445a51d97979f017bb2cb2dc104c6363f0b24",
            "092551e48b6fa66ac303fa018824fe7e22bc1fbf219310f82991701ecc698c8d",
        ),
        (
            "release-summary",
            "23989ce5b964b0a3cdf7da96fe4588840ed345ac436e96572b9cb14d7f659355",
            "4e8d5d2d8a619d18c816616af2a0696c99fae7e98fd77c484cd0ef426bc7f171",
        ),
        (
            "approval-gate",
            "c60777d7b11c7252f6d1d4c1ac8449b9941684d34186c4e5ed0db9b6436025cf",
            "bb98bff13817c99c7de04d478bb525ee4dcff82afb00e01642f24a51d333066c",
        ),
    ],
)
def test_legacy_source_hashes_survive_new_model_and_resource_types(
    name: str, source_hash: str, behavior_hash: str
) -> None:
    raw = json.loads(
        (ROOT / f"contracts/fixtures/valid/{name}.vagent.yaml").read_text()
    )
    source = AgentSource.from_dict(raw)
    assert source.source_hash == source_hash
    assert source.behavior_hash == behavior_hash
    assert "version" not in source.to_dict()
    assert [node["component_type"] for node in source.to_dict()["nodes"]] == [
        node["component_type"] for node in raw["nodes"]
    ]
