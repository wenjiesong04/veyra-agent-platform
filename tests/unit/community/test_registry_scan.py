from __future__ import annotations

import json
from pathlib import Path

import yaml

from veyra_agent_platform.community.registry.service import _scan_payload
from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.common import new_uuid7

ROOT = Path(__file__).resolve().parents[3]


def test_community_scan_reports_suspicious_paths_and_nonportable_dependencies() -> None:
    payload = json.loads(
        (
            ROOT / "contracts/fixtures/project/agents/github-triage/agent.vagent.yaml"
        ).read_text()
    )
    knowledge_ref = f"{new_uuid7()}@1.0.0"
    external_ref = "acme.skill.invoice-review@1.0.0"
    payload["description"] = "/Users/example/project"
    payload["extensions"]["veyra"]["knowledge_refs"] = [knowledge_ref]
    payload["extensions"]["veyra"]["skill_refs"] = [external_ref]
    payload["lock"].update({knowledge_ref: "c" * 64, external_ref: "d" * 64})
    source = AgentSource.from_dict(payload)

    scan = _scan_payload(yaml.safe_dump(source.to_dict()), source)
    warning_codes = {warning["code"] for warning in scan["warnings"]}

    assert scan["status"] == "warning"
    assert "path_reference_review" in warning_codes
    assert "knowledge_dependency_not_portable" in warning_codes
    assert "external_dependency_review" in warning_codes
    assert "/Users/example/project" not in json.dumps(scan)
