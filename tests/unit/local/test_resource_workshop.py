from __future__ import annotations

from pathlib import Path

from veyra_agent_platform.local.resources import ResourceCatalog, ResourceWorkshop


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
