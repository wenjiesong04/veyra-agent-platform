from __future__ import annotations

from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.resources.readiness import ResourceReadiness


class _HostModel:
    configured = False
    secret_store = None


def _model_component(readiness: ResourceReadiness) -> dict[str, object]:
    listed = readiness.resources(kind="component", availability=None)["resources"]
    return next(item for item in listed if item["name"] == "Model")


def test_model_component_stays_pending_without_runtime_provider() -> None:
    readiness = ResourceReadiness(ResourceCatalog(), _HostModel(), (), None)
    model = _model_component(readiness)
    assert model["availability"] == "requires_configuration"
    assert model["runtime_status"] == "runtime_not_configured"


def test_model_component_ready_when_user_runtime_provider_is_mapped() -> None:
    readiness = ResourceReadiness(
        ResourceCatalog(),
        _HostModel(),
        (),
        None,
        model_configured=lambda: True,
    )
    model = _model_component(readiness)
    assert model["availability"] == "ready"
    assert model["runtime_status"] == "supported"
    assert model["configuration_requirements"][0]["satisfied"] is True
