from __future__ import annotations

import pytest

from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.resource import (
    ComponentClass,
    PackageEnvelope,
    ProjectOwnedResource,
    ResourceKind,
    ResourceManifest,
    ResourceRef,
    component_storage_path,
)


def test_resource_ref_is_id_and_version_never_a_path() -> None:
    ref = ResourceRef.from_string("01a03795-a5b0-7234-ba76-5c5f0e029334@1.2.0")
    assert ref.as_ref() == "01a03795-a5b0-7234-ba76-5c5f0e029334@1.2.0"
    with pytest.raises(ContractValidationError):
        ResourceRef.from_string("agents/translator/agent.vagent.yaml")


def test_component_manifest_requires_primitive_or_composite_class() -> None:
    base = {
        "schema_version": "1.0",
        "kind": "component",
        "resource_id": "01a03795-a5b0-7234-ba76-5c5f0e029334",
        "version": "1.0.0",
        "slug": "review-block",
        "name": "Review block",
        "description": "Composite review cluster",
        "component_class": "composite",
    }
    manifest = ResourceManifest.from_dict(base)
    assert manifest.component_class is ComponentClass.COMPOSITE
    with pytest.raises(ContractValidationError):
        ResourceManifest.from_dict({**base, "component_class": None})
    del base["component_class"]
    with pytest.raises(ContractValidationError):
        ResourceManifest.from_dict(base)
    with pytest.raises(ContractValidationError):
        ResourceManifest.from_dict(
            {**base, "kind": "agent", "component_class": "primitive"}
        )


def test_composite_component_lives_under_class_folder() -> None:
    listing = ProjectOwnedResource.from_dict(
        {
            "kind": "component",
            "resource_id": "01a03795-a5b0-7234-ba76-5c5f0e029334",
            "slug": "review-block",
            "version": "1.0.0",
            "component_class": "composite",
            "path": "components/composite/review-block",
        },
        expected_kind=ResourceKind.COMPONENT,
    )
    assert listing.path == component_storage_path(
        ComponentClass.COMPOSITE, "review-block"
    )
    with pytest.raises(ContractValidationError):
        ProjectOwnedResource.from_dict(
            {
                "resource_id": "01a03795-a5b0-7234-ba76-5c5f0e029334",
                "slug": "review-block",
                "version": "1.0.0",
                "component_class": "composite",
                "path": "components/review-block",
            },
            expected_kind=ResourceKind.COMPONENT,
        )


def test_package_envelope_carries_component_class() -> None:
    envelope = PackageEnvelope.from_dict(
        {
            "schema_version": "1.0",
            "kind": "component",
            "resource_id": "01a03795-a5b0-7234-ba76-5c5f0e029334",
            "version": "1.0.0",
            "name": "Review block",
            "component_class": "composite",
            "dependencies": ["01a03795-a5b0-7f61-a971-4c55cead5f27@1.0.0"],
        }
    )
    assert envelope.component_class is ComponentClass.COMPOSITE
    assert envelope.to_dict()["component_class"] == "composite"
