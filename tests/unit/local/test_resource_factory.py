from __future__ import annotations

from pathlib import Path

import pytest

from veyra_agent_platform.contracts.capability import CapabilityRequirement
from veyra_agent_platform.contracts.resource_factory import ResourceFactoryPlan
from veyra_agent_platform.local.builder.agent_composer import compose_loop_agent
from veyra_agent_platform.local.builder.capability_requirements import (
    derive_capability_requirements,
)
from veyra_agent_platform.local.builder.specification import infer_agent_specification
from veyra_agent_platform.local.resources import ResourceCatalog, ResourceWorkshop
from veyra_agent_platform.local.resources.factory_validation import snapshot_identity
from veyra_agent_platform.local.resources.resolver import ResourceResolver
from veyra_agent_platform.local.resources.resource_factory import (
    ResourceFactory,
    ResourceFactoryError,
)

_SKILL_CAP = "structured_comparison_method"
_SKILL_TEXT = (
    "创建一个 Agent。capability: structured_comparison_method。"
    "它需要一种当前目录里没有的结构化比较方法。"
)
_LOOKUP_TEXT = "创建一个 Agent。capability: mock_status_lookup。"
_HTTP_WRAPPER = {
    "base_adapter": "veyra.runtime.http.request",
    "allowed_hosts": ["127.0.0.1"],
    "methods": ["GET"],
    "path_prefix": "/status",
    "port": 8765,
    "scheme": "http",
    "input_schema": {"code": "string"},
    "output_schema": {"body": "string", "status": "integer"},
    "timeout_ms": 2000,
    "max_response_bytes": 8192,
}


def _factory(
    tmp_path: Path,
) -> tuple[ResourceFactory, ResourceCatalog, ResourceWorkshop]:
    overlay = tmp_path / "overlays"
    catalog = ResourceCatalog(overlay_root=overlay)
    workshop = ResourceWorkshop(overlay, catalog)
    return ResourceFactory(workshop, catalog), catalog, workshop


def _resolve(catalog: ResourceCatalog, text: str, *, owned: list | None = None):
    spec = infer_agent_specification(text)
    requirements = derive_capability_requirements(spec, text)
    plan = ResourceResolver(catalog).resolve(
        spec,
        requirements,
        project_resources=owned or [],
        requirement_text=text,
    )
    return spec, requirements, plan


def test_skill_draft_validate_publish_resolver_and_composer(tmp_path: Path) -> None:
    factory, catalog, _workshop = _factory(tmp_path)
    spec, _requirements, missing_plan = _resolve(catalog, _SKILL_TEXT)
    assert any(item.capability == _SKILL_CAP for item in missing_plan.missing_required)

    planned = factory.plan_missing(missing_plan, proposal_id="proposal-skill")[0]
    assert planned.status == "generatable"
    assert planned.strategy == "skill_instruction"
    operation_id = planned.operation_id

    drafted = factory.ensure_skill_draft(
        planned, CapabilityRequirement(capability=_SKILL_CAP, required=True)
    )
    assert drafted.draft is not None
    assert drafted.draft["availability"] == "quarantined"
    assert drafted.draft["factory_selectable"] is False
    assert drafted.draft["origin"] == "workshop"
    assert "factory" in drafted.draft["tags"]
    assert drafted.validation["passed"] is True
    assert drafted.snapshot_hash == snapshot_identity(drafted.draft)
    listed = catalog.resources(availability="quarantined")["resources"]
    assert any(item["reference"] == drafted.draft["reference"] for item in listed)
    snapshot = {item["reference"] for item in catalog.factory_snapshot()}
    assert drafted.draft["reference"] not in snapshot

    same = factory.ensure_skill_draft(
        drafted, CapabilityRequirement(capability=_SKILL_CAP, required=True)
    )
    assert same.snapshot_hash == drafted.snapshot_hash
    assert same.operation_id == operation_id
    assert same.draft["resource_id"] == drafted.draft["resource_id"]

    with pytest.raises(ResourceFactoryError) as unpublished:
        factory.publish(drafted, confirm=False)
    assert unpublished.value.code == "factory_confirmation_required"

    with pytest.raises(ResourceFactoryError) as tampered:
        factory.publish(drafted, confirm=True, snapshot_hash="0" * 64)
    assert tampered.value.code == "factory_snapshot_mismatch"

    published = factory.publish(drafted, confirm=True)
    assert published.published is not None
    assert published.published["availability"] == "ready"
    assert published.published["factory_selectable"] is True
    assert published.published["version"] == "0.0.1"
    digest = published.published["content_hash"]
    again = factory.publish(published, confirm=True)
    assert again.published["content_hash"] == digest
    assert again.published["resource_id"] == published.published["resource_id"]

    _spec, _reqs, found = _resolve(catalog, _SKILL_TEXT)
    selected = [item for item in found.selected if _SKILL_CAP in item.capabilities]
    assert selected
    assert selected[0].kind == "skill"
    assert selected[0].bind_status == "will_bind"
    assert selected[0].reference == published.published["reference"]
    assert not any(item.capability == _SKILL_CAP for item in found.missing_required)

    source = compose_loop_agent(spec, found, requirement=_SKILL_TEXT)
    assert published.published["reference"] in source.skill_refs
    assert source.lock[published.published["reference"]] == digest


def test_http_wrapper_publish_is_discovered_by_resolver(tmp_path: Path) -> None:
    factory, catalog, _workshop = _factory(tmp_path)
    spec, _requirements, missing_plan = _resolve(catalog, _LOOKUP_TEXT)
    planned = next(
        item
        for item in factory.plan_missing(missing_plan, wrappers={})
        if item.capability == "mock_status_lookup"
    )
    assert planned.status == "requires_user_configuration"
    configured = factory.plan_missing(
        missing_plan, wrappers={"mock_status_lookup": _HTTP_WRAPPER}
    )[0]
    drafted = factory.ensure_wrapper_draft(
        configured,
        CapabilityRequirement(capability="mock_status_lookup", required=True),
        _HTTP_WRAPPER,
    )
    assert drafted.draft["kind"] == "tool"
    assert drafted.draft["spec"]["adapter"] == "veyra.runtime.http.request"
    assert drafted.draft["spec"]["wrapper_kind"] == "tool_wrapper"
    assert "url" not in drafted.draft["spec"]["input_schema"]
    published = factory.publish(drafted, confirm=True)
    _spec, _reqs, found = _resolve(catalog, _LOOKUP_TEXT)
    selected = [
        item for item in found.selected if "mock_status_lookup" in item.capabilities
    ]
    assert selected
    assert selected[0].kind == "tool"
    assert selected[0].bind_status == "will_bind"
    source = compose_loop_agent(spec, found, requirement=_LOOKUP_TEXT)
    assert published.published["reference"] in source.lock
    assert "127.0.0.1" in source.permissions.network_hosts
    assert published.published["resource_id"] in source.permissions.tools


def test_unsafe_wrapper_never_writes_an_overlay(tmp_path: Path) -> None:
    factory, catalog, _workshop = _factory(tmp_path)
    spec = infer_agent_specification("capability: run_arbitrary_shell")
    plan = ResourceResolver(catalog).resolve(
        spec,
        derive_capability_requirements(spec, "capability: run_arbitrary_shell"),
        requirement_text="capability: run_arbitrary_shell",
    )
    planned = factory.plan_missing(plan)[0]
    assert planned.status == "unsupported"
    with pytest.raises(ResourceFactoryError) as caught:
        factory.ensure_wrapper_draft(
            planned,
            CapabilityRequirement(capability="run_arbitrary_shell", required=True),
            {"base_adapter": "veyra.runtime.shell.exec"},
        )
    assert caught.value.code == "factory_unsupported"
    overlays = list((tmp_path / "overlays" / "workshop").glob("*/node.yaml"))
    assert overlays == []


def test_skill_revision_is_a_new_version(tmp_path: Path) -> None:
    factory, catalog, _workshop = _factory(tmp_path)
    _spec, _reqs, missing_plan = _resolve(catalog, _SKILL_TEXT)
    planned = factory.plan_missing(missing_plan)[0]
    drafted = factory.ensure_skill_draft(
        planned, CapabilityRequirement(capability=_SKILL_CAP, required=True)
    )
    published = factory.publish(drafted, confirm=True)
    first_hash = published.published["content_hash"]
    instruction = drafted.draft["spec"]["instruction"].replace(
        "Restate the criteria implied by the capability name.",
        "Restate comparison criteria using only provided facts.",
    )
    revised = factory.revise_skill(
        published.published["resource_id"],
        published.published["version"],
        instruction,
        confirm=True,
    )
    assert revised["draft"]["version"] == "0.0.2"
    assert revised["draft"]["availability"] == "quarantined"
    current = catalog.detail(
        published.published["resource_id"], published.published["version"]
    )
    assert current["content_hash"] == first_hash
    assert current["spec"]["instruction"] != revised["draft"]["spec"]["instruction"]


def test_disabled_skill_is_not_selected(tmp_path: Path) -> None:
    factory, catalog, workshop = _factory(tmp_path)
    _spec, _reqs, missing_plan = _resolve(catalog, _SKILL_TEXT)
    drafted = factory.ensure_skill_draft(
        factory.plan_missing(missing_plan)[0],
        CapabilityRequirement(capability=_SKILL_CAP, required=True),
    )
    published = factory.publish(drafted, confirm=True)
    workshop.set_enabled(
        published.published["resource_id"],
        published.published["version"],
        enabled=False,
    )
    disabled = catalog.detail(
        published.published["resource_id"], published.published["version"]
    )
    assert disabled["availability"] == "disabled"
    assert disabled["factory_selectable"] is False
    _spec, _reqs, found = _resolve(catalog, _SKILL_TEXT)
    assert any(item.capability == _SKILL_CAP for item in found.missing_required)
    assert not any(_SKILL_CAP in item.capabilities for item in found.selected)


def test_plan_roundtrip_keeps_snapshot(tmp_path: Path) -> None:
    factory, _catalog, _workshop = _factory(tmp_path)
    _spec, _reqs, missing_plan = _resolve(_catalog, _SKILL_TEXT)
    drafted = factory.ensure_skill_draft(
        factory.plan_missing(missing_plan, proposal_id="session-1")[0],
        CapabilityRequirement(capability=_SKILL_CAP, required=True),
    )
    restored = ResourceFactoryPlan.from_dict(drafted.to_dict())
    assert restored.proposal_id == "session-1"
    assert restored.operation_id == drafted.operation_id
    assert restored.snapshot_hash == drafted.snapshot_hash
    assert restored.draft["spec"]["instruction"] == drafted.draft["spec"]["instruction"]
    assert restored.validation == drafted.validation
