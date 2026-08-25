from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from veyra_agent_platform.contracts.agent import HARD_MAX_NODES, HARD_MAX_TRANSITIONS, AgentBlueprint, AgentSource, ProjectManifest
from veyra_agent_platform.contracts.canonical import file_hash
from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.local.domain.agent_definition import compile_agent_definition

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "contracts" / "fixtures"
PROJECT_FIXTURE = FIXTURES / "project"


def read_json_yaml(path: Path) -> dict[str, object]:
    # JSON is valid YAML and keeps the bootstrap fixtures parser-independent.
    return json.loads(path.read_text(encoding="utf-8"))


def blueprint_data_from_source(source: dict[str, object]) -> dict[str, object]:
    nodes = source["nodes"]  # type: ignore[assignment]
    return {
        "schema_version": source["schema_version"], "goal": source["description"],
        "inputs": source["inputs"], "outputs": source["outputs"], "nodes": nodes,
        "transitions": source["transitions"],
        "required_capabilities": {
            "component_types": list(dict.fromkeys(node["component_type"] for node in nodes)),  # type: ignore[union-attr]
            "tool_refs": [node["uses"] for node in nodes if node["component_type"] == "Tool"],  # type: ignore[union-attr]
        },
        "requested_permissions": source["extensions"]["veyra"]["permissions"],  # type: ignore[index]
        "verification": source["extensions"]["veyra"]["verification"],  # type: ignore[index]
        "ui_suggestions": source["ui"],
    }


class AgentContractTests(unittest.TestCase):
    def test_project_manifest_has_stable_uuid_and_multiple_agents(self) -> None:
        manifest = ProjectManifest.from_dict(read_json_yaml(PROJECT_FIXTURE / "project.vproject.yaml"))
        self.assertEqual(manifest.project_id, "01a03795-a5b0-7234-ba76-5c5f0e029334")
        self.assertEqual(len(manifest.agents), 3)
        self.assertEqual(manifest.agents[0].slug, "github-triage")
        self.assertEqual(manifest.agents[0].path, "agents/github-triage")
        self.assertEqual(manifest.default_agent_id, manifest.agents[0].agent_id)
        self.assertEqual(manifest.resource_policy.max_concurrent_runs, 2)

    def test_project_fixture_instantiates_agent_directories_and_required_files(self) -> None:
        manifest = ProjectManifest.from_dict(read_json_yaml(PROJECT_FIXTURE / "project.vproject.yaml"))
        for entry in manifest.agents:
            directory = PROJECT_FIXTURE / entry.path
            source_path = directory / "agent.vagent.yaml"
            with self.subTest(slug=entry.slug):
                self.assertTrue(source_path.is_file())
                self.assertTrue((directory / "README.md").is_file())
                self.assertTrue((directory / "tests" / "agent.test.yaml").is_file())
                source = AgentSource.from_dict(read_json_yaml(source_path))
                self.assertEqual(source.agent_id, entry.agent_id)
                self.assertEqual(source.slug, entry.slug)
                self.assertEqual(entry.path, f"agents/{source.slug}")

    def test_handwritten_agent_fixtures_are_valid_and_cover_all_components(self) -> None:
        component_types: set[str] = set()
        for path in sorted((FIXTURES / "valid").glob("*.vagent.yaml")):
            source = AgentSource.from_dict(read_json_yaml(path))
            component_types.update(node.component_type.value for node in source.nodes)
            self.assertEqual(len(source.source_hash), 64)
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

    def test_behavior_hash_excludes_local_identity_and_presentation(self) -> None:
        source = read_json_yaml(FIXTURES / "valid" / "github-triage.vagent.yaml")
        original = AgentSource.from_dict(source)
        remapped = deepcopy(source)
        remapped["agent_id"] = "01a03795-a5b0-7f0b-896f-7b80026c5bbd"
        remapped["slug"] = "github-triage-fork"
        forked = AgentSource.from_dict(remapped)
        self.assertNotEqual(original.source_hash, forked.source_hash)
        self.assertEqual(original.behavior_hash, forked.behavior_hash)

    def test_raw_file_hash_is_text_based_and_separate_from_semantic_hashes(self) -> None:
        original_text = '{"description":"Résumé"}\r\n'
        changed_text = '{"description":"Résumé updated"}\n'
        self.assertEqual(file_hash(original_text), file_hash('{"description":"Re\u0301sume\u0301"}\n'))
        self.assertNotEqual(file_hash(original_text), file_hash(changed_text))
        source = read_json_yaml(FIXTURES / "valid" / "github-triage.vagent.yaml")
        original = AgentSource.from_dict(source)
        source["description"] = "Changed documentation only."
        documented = AgentSource.from_dict(source)
        self.assertNotEqual(original.source_hash, documented.source_hash)
        self.assertEqual(original.behavior_hash, documented.behavior_hash)

    def test_nested_contract_values_are_defensively_immutable(self) -> None:
        data = read_json_yaml(FIXTURES / "valid" / "github-triage.vagent.yaml")
        source = AgentSource.from_dict(data)
        hashes = (source.source_hash, source.behavior_hash, source.lock_hash)
        data["inputs"]["extra"] = "string"  # type: ignore[index]
        data["nodes"][4]["mapping"]["summary"] = "changed"  # type: ignore[index]
        data["ui"]["positions"]["start"]["x"] = 99  # type: ignore[index]
        data["lock"]["veyra.github.issue_search@1.0.0"] = "d" * 64  # type: ignore[index]
        self.assertEqual(hashes, (source.source_hash, source.behavior_hash, source.lock_hash))
        with self.assertRaises(TypeError):
            source.inputs["extra"] = "string"  # type: ignore[index]
        with self.assertRaises(TypeError):
            source.nodes[4].mapping["summary"] = "changed"  # type: ignore[index,union-attr]
        with self.assertRaises(TypeError):
            source.ui["positions"]["start"]["x"] = 99  # type: ignore[index]
        with self.assertRaises(TypeError):
            source.lock["veyra.github.issue_search@1.0.0"] = "d" * 64  # type: ignore[index]

    def test_blueprint_compile_preserves_requested_permissions_without_expansion(self) -> None:
        source_data = read_json_yaml(FIXTURES / "valid" / "approval-gate.vagent.yaml")
        blueprint = AgentBlueprint.from_dict(blueprint_data_from_source(source_data))
        definition = compile_agent_definition(blueprint, agent_id=source_data["agent_id"], slug=source_data["slug"], name="Approval Gate", description="A gate.", runtime_profile="veyra-runtime-profile/1", secret_refs=[], lock=source_data["lock"])  # type: ignore[arg-type]
        self.assertEqual(definition.source.permissions, blueprint.requested_permissions)
        self.assertEqual(definition.source.ui, blueprint.ui_suggestions)
        self.assertEqual(definition.source_hash, definition.source.source_hash)

    def test_adversarial_agent_fixtures_fail_closed(self) -> None:
        for path in sorted((FIXTURES / "invalid").glob("*.vagent.yaml")):
            with self.subTest(path=path.name), self.assertRaises(ContractValidationError):
                AgentSource.from_dict(read_json_yaml(path))

    def test_agent_identity_must_be_uuidv7_and_project_path_must_match_slug(self) -> None:
        source = read_json_yaml(FIXTURES / "valid" / "approval-gate.vagent.yaml")
        source["agent_id"] = "approval-gate"
        with self.assertRaises(ContractValidationError):
            AgentSource.from_dict(source)
        for path in ("agents/not-approval-gate", "agents\\approval-gate", "agents/approval-gate/extra", "agents/../approval-gate"):
            manifest = read_json_yaml(PROJECT_FIXTURE / "project.vproject.yaml")
            manifest["agents"][2]["path"] = path  # type: ignore[index]
            with self.subTest(path=path), self.assertRaises(ContractValidationError):
                ProjectManifest.from_dict(manifest)
        manifest = read_json_yaml(PROJECT_FIXTURE / "project.vproject.yaml")
        manifest["default_agent_id"] = "01a03795-a5b0-7f0b-896f-7b80026c5bbd"
        with self.assertRaises(ContractValidationError):
            ProjectManifest.from_dict(manifest)
        manifest = read_json_yaml(PROJECT_FIXTURE / "project.vproject.yaml")
        manifest["resource_policy"]["max_nodes_per_run"] = 0  # type: ignore[index]
        with self.assertRaises(ContractValidationError):
            ProjectManifest.from_dict(manifest)

    def test_draft_agent_identity_is_uuidv7_not_a_slug(self) -> None:
        source = read_json_yaml(FIXTURES / "valid" / "approval-gate.vagent.yaml")
        draft = {
            "schema_version": "1.0", "draft_id": "01a03795-a5b0-7a2a-8e4a-9795e831e9ec",
            "project_id": "01a03795-a5b0-7234-ba76-5c5f0e029334", "agent_id": "approval-gate", "revision": 0,
            "blueprint": blueprint_data_from_source(source),
        }
        from veyra_agent_platform.contracts.agent import AgentDraft
        with self.assertRaises(ContractValidationError):
            AgentDraft.from_dict(draft)

    def test_graph_rejects_cycle_and_incomplete_or_duplicate_ports(self) -> None:
        cyclic_blueprint = {
            "schema_version": "1.0", "goal": "Cycle test", "inputs": {"request": "string"}, "outputs": {"result": "string"},
            "nodes": [
                {"id": "start", "component_type": "Start"},
                {"id": "condition", "component_type": "Condition", "expression": "ok"},
                {"id": "transform", "component_type": "Transform", "mapping": {"result": "value"}},
                {"id": "output", "component_type": "Output", "output_name": "result"},
            ],
            "transitions": [
                {"from": "start", "port": "next", "to": "condition"},
                {"from": "condition", "port": "true", "to": "output"},
                {"from": "condition", "port": "false", "to": "transform"},
                {"from": "transform", "port": "next", "to": "condition"},
            ],
            "requested_permissions": {"network_hosts": [], "tools": []}, "verification": {"required": False, "checks": []},
            "required_capabilities": {"component_types": ["Start", "Condition", "Transform", "Output"], "tool_refs": []},
            "ui_suggestions": {"positions": {}},
        }
        with self.assertRaises(ContractValidationError):
            AgentBlueprint.from_dict(cyclic_blueprint)
        source = read_json_yaml(FIXTURES / "valid" / "github-triage.vagent.yaml")
        missing_port = deepcopy(source)
        missing_port["transitions"] = [edge for edge in source["transitions"] if not (edge["from"] == "has_evidence" and edge["port"] == "false")]  # type: ignore[index]
        with self.assertRaises(ContractValidationError):
            AgentSource.from_dict(missing_port)
        duplicate_port = deepcopy(source)
        duplicate_port["transitions"].append({"from": "has_evidence", "port": "true", "to": "no_action"})  # type: ignore[index]
        with self.assertRaises(ContractValidationError):
            AgentSource.from_dict(duplicate_port)

    def test_verifier_checks_must_match_declared_contract(self) -> None:
        source = read_json_yaml(FIXTURES / "valid" / "github-triage.vagent.yaml")
        source["extensions"]["veyra"]["verification"]["checks"].append("github.issue.authorized")  # type: ignore[index]
        with self.assertRaises(ContractValidationError):
            AgentSource.from_dict(source)

    def test_tool_uses_reference_must_be_exactly_locked(self) -> None:
        source = read_json_yaml(FIXTURES / "valid" / "github-triage.vagent.yaml")
        missing = deepcopy(source)
        missing["lock"] = {"veyra.runtime.profile@1.0.0": "d" * 64}
        with self.assertRaises(ContractValidationError):
            AgentSource.from_dict(missing)
        mismatch = deepcopy(source)
        mismatch["lock"] = {"veyra.github.issue_search@2.0.0": "d" * 64}
        with self.assertRaises(ContractValidationError):
            AgentSource.from_dict(mismatch)

    def test_outputs_must_be_declared_complete_and_single_producer(self) -> None:
        source = read_json_yaml(FIXTURES / "valid" / "github-triage.vagent.yaml")
        undeclared = deepcopy(source)
        undeclared["nodes"][-1]["output_name"] = "missing"  # type: ignore[index]
        with self.assertRaises(ContractValidationError):
            AgentSource.from_dict(undeclared)
        incomplete = deepcopy(source)
        incomplete["outputs"]["not_produced"] = "string"  # type: ignore[index]
        with self.assertRaises(ContractValidationError):
            AgentSource.from_dict(incomplete)
        duplicate = deepcopy(source)
        duplicate["nodes"][-1]["output_name"] = "result"  # type: ignore[index]
        with self.assertRaises(ContractValidationError):
            AgentSource.from_dict(duplicate)

    def test_blueprint_requires_capabilities_and_valid_ui_node_references(self) -> None:
        source = read_json_yaml(FIXTURES / "valid" / "approval-gate.vagent.yaml")
        blueprint = blueprint_data_from_source(source)
        blueprint.pop("required_capabilities")
        with self.assertRaises(ContractValidationError):
            AgentBlueprint.from_dict(blueprint)
        blueprint = blueprint_data_from_source(source)
        blueprint["required_capabilities"]["component_types"] = ["Start", "Output"]  # type: ignore[index]
        with self.assertRaises(ContractValidationError):
            AgentBlueprint.from_dict(blueprint)
        blueprint = blueprint_data_from_source(source)
        blueprint["ui_suggestions"]["positions"]["unknown_node"] = {"x": 0, "y": 0}  # type: ignore[index]
        with self.assertRaises(ContractValidationError):
            AgentBlueprint.from_dict(blueprint)

    def test_transform_mapping_and_graph_resource_bounds_fail_closed(self) -> None:
        source = read_json_yaml(FIXTURES / "valid" / "github-triage.vagent.yaml")
        transform = deepcopy(source)
        transform["nodes"][4]["mapping"]["summary"] = ""  # type: ignore[index]
        with self.assertRaises(ContractValidationError):
            AgentSource.from_dict(transform)
        oversized = {
            "schema_version": "1.0", "goal": "Bound test", "inputs": {"value": "string"}, "outputs": {"result": "string"},
            "nodes": [{"id": f"node_{index}", "component_type": "Start"} for index in range(HARD_MAX_NODES + 1)],
            "transitions": [], "required_capabilities": {"component_types": ["Start"], "tool_refs": []},
            "requested_permissions": {"network_hosts": [], "tools": []}, "verification": {"required": False, "checks": []}, "ui_suggestions": {"positions": {}},
        }
        with self.assertRaises(ContractValidationError):
            AgentBlueprint.from_dict(oversized)
        transitions = [{"from": "start", "port": "next", "to": "output"} for _ in range(HARD_MAX_TRANSITIONS + 1)]
        bounded = {
            "schema_version": "1.0", "goal": "Transition bound", "inputs": {"value": "string"}, "outputs": {"result": "string"},
            "nodes": [{"id": "start", "component_type": "Start"}, {"id": "output", "component_type": "Output", "output_name": "result"}],
            "transitions": transitions, "required_capabilities": {"component_types": ["Start", "Output"], "tool_refs": []},
            "requested_permissions": {"network_hosts": [], "tools": []}, "verification": {"required": False, "checks": []}, "ui_suggestions": {"positions": {}},
        }
        with self.assertRaises(ContractValidationError):
            AgentBlueprint.from_dict(bounded)
        manifest = read_json_yaml(PROJECT_FIXTURE / "project.vproject.yaml")
        manifest["resource_policy"]["max_nodes_per_run"] = HARD_MAX_NODES + 1  # type: ignore[index]
        with self.assertRaises(ContractValidationError):
            ProjectManifest.from_dict(manifest)
