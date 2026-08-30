from __future__ import annotations

from veyra_agent_platform.local.resources import ResourceCatalog


def test_resource_catalog_has_unique_stable_references_and_hashes() -> None:
    catalog = ResourceCatalog()

    first = catalog.resources()["resources"]
    second = catalog.resources()["resources"]

    assert first == second
    assert len({resource["reference"] for resource in first}) == len(first)
    assert all(len(resource["content_hash"]) == 64 for resource in first)
    assert all(resource["content_hash"].islower() for resource in first)
    first[0]["spec"]["fields"].append("mutated")
    assert "mutated" not in catalog.resources()["resources"][0]["spec"]["fields"]


def test_component_catalog_status_and_legacy_projection_are_honest() -> None:
    catalog = ResourceCatalog()
    components = catalog.resources(kind="component")["resources"]

    agent = next(resource for resource in components if resource["name"] == "Agent")
    tool = next(resource for resource in components if resource["name"] == "Tool")

    assert agent["availability"] == "requires_configuration"
    assert agent["runtime_status"] == "runtime_not_configured"
    assert tool["availability"] == "design_only"
    assert tool["runtime_status"] == "runtime_not_supported"
    assert all(resource["factory_selectable"] for resource in components)
    assert catalog.components()[2] == {
        "type": "Tool",
        "fields": ["uses"],
        "output_ports": ["next"],
        "runtime_status": "runtime_not_supported",
    }
    tools = catalog.resources(kind="tool")["resources"]
    assert [resource["reference"] for resource in tools] == [
        "veyra.tool.filesystem.read@1.0.0"
    ]
    assert tools[0]["required_permissions"]["filesystem_read_roots"] == ["project"]


def test_skill_resources_await_runtime_provider_configuration() -> None:
    skills = ResourceCatalog().resources(kind="skill")["resources"]

    assert {skill["runtime_status"] for skill in skills} == {"runtime_not_configured"}
