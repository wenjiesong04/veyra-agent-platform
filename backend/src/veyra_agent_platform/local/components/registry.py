"""The closed built-in component registry exposed to Studio."""

from __future__ import annotations

from typing import Any


def component_registry() -> list[dict[str, Any]]:
    """Return the legacy Studio projection of Component Resources."""
    from veyra_agent_platform.local.resources import ResourceCatalog

    return ResourceCatalog().components()
