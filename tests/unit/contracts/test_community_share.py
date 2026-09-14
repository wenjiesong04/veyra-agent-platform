from __future__ import annotations

import pytest

from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.resource import CommunityShareManifest

_ID = "018f5b6e-7abc-7def-8123-456789abcdef"


def _manifest(kind: str = "agent", import_mode: str = "local_agent") -> dict:
    return {
        "schema_version": "1.0",
        "kind": kind,
        "resource_id": _ID,
        "version": "1.0.0",
        "name": "Review Agent",
        "description": "A reviewable Community object.",
        "content_hash": "a" * 64,
        "dependencies": [],
        "import_mode": import_mode,
        "source_scope": "public",
        "agent_version_refs": [],
        "included_kinds": [],
    }


def test_share_manifest_round_trips_public_metadata() -> None:
    manifest = CommunityShareManifest.from_dict(_manifest())

    assert manifest.to_dict() == _manifest()
    assert "secret" not in manifest.to_dict()


@pytest.mark.parametrize(
    ("kind", "import_mode"),
    [
        ("workflow", "local_workflow"),
        ("project", "local_project"),
        ("component", "local_resource"),
        ("tool", "review_required"),
    ],
)
def test_share_manifest_has_explicit_import_boundary(
    kind: str, import_mode: str
) -> None:
    manifest = CommunityShareManifest.from_dict(_manifest(kind, import_mode))

    assert manifest.kind.value == kind
    assert manifest.import_mode.value == import_mode


def test_tool_cannot_claim_local_executable_import() -> None:
    with pytest.raises(ContractValidationError, match="import mode"):
        CommunityShareManifest.from_dict(_manifest("tool", "local_resource"))


def test_workflow_keeps_pinned_agent_versions_separate_from_catalog_dependencies() -> (
    None
):
    payload = _manifest("workflow", "local_workflow")
    payload["agent_version_refs"] = [f"{_ID}@{_ID}"]

    manifest = CommunityShareManifest.from_dict(payload)

    assert manifest.agent_version_refs == (f"{_ID}@{_ID}",)
    assert manifest.dependencies == ()


def test_project_declares_selected_content_kinds_explicitly() -> None:
    payload = _manifest("project", "local_project")
    payload["included_kinds"] = ["agent", "workflow", "component"]

    manifest = CommunityShareManifest.from_dict(payload)

    assert [value.value for value in manifest.included_kinds] == [
        "agent",
        "workflow",
        "component",
    ]


def test_share_manifest_rejects_private_scope_and_invalid_hash() -> None:
    private = _manifest()
    private["source_scope"] = "private"
    with pytest.raises(ContractValidationError, match="source_scope"):
        CommunityShareManifest.from_dict(private)

    invalid_hash = _manifest()
    invalid_hash["content_hash"] = "not-a-hash"
    with pytest.raises(ContractValidationError, match="SHA-256"):
        CommunityShareManifest.from_dict(invalid_hash)
