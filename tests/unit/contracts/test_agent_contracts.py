from __future__ import annotations

import json
import unittest
from pathlib import Path

from veyra_agent_platform.contracts.agent import AgentBlueprint, AgentSource, ProjectManifest
from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.local.domain.agent_definition import compile_agent_definition

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "contracts" / "fixtures"


def read_json_yaml(path: Path) -> dict[str, object]:
    # JSON is valid YAML and keeps the bootstrap fixtures parser-independent.
    return json.loads(path.read_text(encoding="utf-8"))


class AgentContractTests(unittest.TestCase):
    def test_project_manifest_has_stable_uuid_and_multiple_agents(self) -> None:
        manifest = ProjectManifest.from_dict(read_json_yaml(FIXTURES / "project.vproject.yaml"))
        self.assertEqual(manifest.project_id, "01a03795-a5b0-7234-ba76-5c5f0e029334")
        self.assertEqual(len(manifest.agents), 3)

    def test_handwritten_agent_fixtures_are_valid_and_cover_all_components(self) -> None:
        component_types: set[str] = set()
        for path in sorted((FIXTURES / "valid").glob("*.vagent.yaml")):
            source = AgentSource.from_dict(read_json_yaml(path))
            component_types.update(node.component_type.value for node in source.nodes)
            self.assertEqual(len(source.source_hash), 64)
            self.assertEqual(source.file_hash, source.source_hash)
            self.assertEqual(len(source.behavior_hash), 64)
            self.assertEqual(len(source.lock_hash), 64)
        self.assertEqual(component_types, {"Start", "Agent", "Tool", "Condition", "Transform", "HumanApproval", "Verifier", "Output"})

    def test_layout_affects_source_hash_not_behavior_hash(self) -> None:
        data = read_json_yaml(FIXTURES / "valid" / "github-triage.vagent.yaml")
        original = AgentSource.from_dict(data)
        data["ui"]["positions"]["start"]["x"] = 99  # type: ignore[index]
        moved = AgentSource.from_dict(data)
        self.assertNotEqual(original.source_hash, moved.source_hash)
        self.assertEqual(original.behavior_hash, moved.behavior_hash)
        self.assertEqual(original.lock_hash, moved.lock_hash)

    def test_blueprint_compile_preserves_requested_permissions_without_expansion(self) -> None:
        source_data = read_json_yaml(FIXTURES / "valid" / "approval-gate.vagent.yaml")
        blueprint = AgentBlueprint.from_dict({
            "schema_version": source_data["schema_version"],
            "goal": source_data["description"],
            "inputs": source_data["inputs"],
            "outputs": source_data["outputs"],
            "nodes": source_data["nodes"],
            "transitions": source_data["transitions"],
            "requested_permissions": source_data["extensions"]["veyra"]["permissions"],  # type: ignore[index]
            "verification": source_data["extensions"]["veyra"]["verification"],  # type: ignore[index]
        })
        definition = compile_agent_definition(blueprint, agent_id="approval-gate", name="Approval Gate", description="A gate.", runtime_profile="veyra-runtime-profile/1", secret_refs=[], lock=source_data["lock"], ui=source_data["ui"])  # type: ignore[arg-type]
        self.assertEqual(definition.source.permissions, blueprint.requested_permissions)
        self.assertEqual(definition.source_hash, definition.source.source_hash)

    def test_adversarial_agent_fixtures_fail_closed(self) -> None:
        for path in sorted((FIXTURES / "invalid").glob("*.vagent.yaml")):
            with self.subTest(path=path.name), self.assertRaises(ContractValidationError):
                AgentSource.from_dict(read_json_yaml(path))
