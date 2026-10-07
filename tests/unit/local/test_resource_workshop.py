from __future__ import annotations

from pathlib import Path

import pytest

from veyra_agent_platform.contracts.capability import CapabilityRequirement
from veyra_agent_platform.local.resources import ResourceCatalog, ResourceWorkshop
from veyra_agent_platform.local.resources.resource_factory import (
    ResourceFactory,
    ResourceFactoryError,
    skill_instruction_for,
)
from veyra_agent_platform.local.resources.workshop import ResourceWorkshopError


def test_workshop_draft_is_quarantined_and_not_factory_selectable(
    tmp_path: Path,
) -> None:
    overlay = tmp_path / "overlays"
    catalog = ResourceCatalog(overlay_root=overlay)
    workshop = ResourceWorkshop(overlay, catalog)

    created = workshop.create_draft(
        confirm=True,
        kind="tool",
        requested_reference="veyra.tool.github.read@1.0.0",
        name="GitHub Read proposal",
    )

    resource = created["resource"]
    assert created["executable"] is False
    assert resource["availability"] == "quarantined"
    assert resource["factory_selectable"] is False
    assert resource["runtime_status"] == "runtime_not_supported"
    assert resource["origin"] == "workshop"
    listed = catalog.resources(availability="quarantined")["resources"]
    assert any(item["reference"] == resource["reference"] for item in listed)
    snapshot = {item["reference"] for item in catalog.factory_snapshot()}
    assert resource["reference"] not in snapshot


def test_factory_scaffold_requires_actual_method_at_direct_workshop_approval(
    tmp_path: Path,
) -> None:
    from veyra_agent_platform.contracts.resource_factory import ResourceFactoryPlan
    from veyra_agent_platform.local.resources.factory_strategy import (
        classify_factory_strategy,
    )

    catalog = ResourceCatalog(overlay_root=tmp_path / "overlays")
    workshop = ResourceWorkshop(tmp_path / "overlays", catalog)
    factory = ResourceFactory(workshop, catalog)
    requirement = CapabilityRequirement(capability="priority_comparison_method")
    strategy = classify_factory_strategy(requirement)
    planned = ResourceFactoryPlan.from_dict(
        {"capability": requirement.capability, **strategy.to_dict()}
    )
    scaffold = factory.ensure_skill_draft(planned, requirement)
    resource_id, version = scaffold.draft["resource_id"], scaffold.draft["version"]
    original_hash = scaffold.draft["content_hash"]

    for instruction in [None, skill_instruction_for(requirement.capability)]:
        with pytest.raises(ResourceWorkshopError) as caught:
            workshop.approve_skill(resource_id, version, instruction)
        assert caught.value.code == "workshop_instruction_required"
        current = catalog.detail(resource_id, version)
        assert current["content_hash"] == original_hash
        assert current["availability"] == "quarantined"
        assert current["factory_selectable"] is False
    with pytest.raises(ResourceWorkshopError) as enabled:
        workshop.set_skill_enabled(resource_id, version, enabled=True)
    assert enabled.value.code == "workshop_instruction_required"
    assert catalog.detail(resource_id, version)["content_hash"] == original_hash

    instruction = (
        "Purpose\n"
        "Compare the provided options using the customer's ordered priorities.\n\n"
        "When to use\n"
        "Use when two options and the customer's priorities are supplied.\n\n"
        "Procedure\nList the evidence for each priority, then order options "
        "lexicographically by those priorities.\n\n"
        "Expected output\n"
        "An ordered comparison table with supporting facts and missing values.\n\n"
        "Constraints\nUse supplied facts only and mark unknown values explicitly.\n\n"
        "Failure handling\n"
        "Ask for the priority order before comparing if it is missing."
    )
    approved = workshop.approve_skill(resource_id, version, instruction)["resource"]
    assert approved["availability"] == "ready"
    assert approved["spec"]["instruction"] == instruction
    assert approved["spec"]["instruction_status"] == "provided"
    assert approved["spec"]["validation_passed"] is True
    approved_hash = approved["content_hash"]
    again = workshop.approve_skill(resource_id, version)["resource"]
    assert again["content_hash"] == approved_hash
    with pytest.raises(ResourceWorkshopError) as changed:
        workshop.approve_skill(resource_id, version, instruction + "\nNew criterion.")
    assert changed.value.code == "workshop_skill_revision_required"
    assert catalog.detail(resource_id, version)["content_hash"] == approved_hash

    with pytest.raises(ResourceFactoryError) as stale_factory:
        factory.ensure_skill_draft(scaffold, requirement, instruction=instruction)
    assert stale_factory.value.code == "factory_skill_revision_required"
    assert catalog.detail(resource_id, version)["content_hash"] == approved_hash


def test_direct_user_authored_workshop_instruction_keeps_its_approval_behavior(
    tmp_path: Path,
) -> None:
    catalog = ResourceCatalog(overlay_root=tmp_path / "overlays")
    workshop = ResourceWorkshop(tmp_path / "overlays", catalog)
    instruction = (
        "Compare only the facts supplied by the customer; ask for missing facts."
    )
    created = workshop.create_draft(
        confirm=True,
        kind="skill",
        requested_reference="veyra.skill.customer-comparison@1.0.0",
        instruction=instruction,
    )["resource"]
    approved = workshop.approve_skill(created["resource_id"], created["version"])[
        "resource"
    ]
    assert approved["availability"] == "ready"
    assert approved["spec"]["instruction"] == instruction
