"""Capability requirements describe what an Agent needs, not which resource."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .common import (
    ContractValidationError,
    require_list,
    require_mapping,
    require_string,
)

SideEffect = Literal["none", "read", "write"]
NetworkNeed = Literal["none", "required"]
FilesystemNeed = Literal["none", "read", "write"]
ApprovalNeed = Literal["none", "required"]

_SIDE_EFFECTS = {"none", "read", "write"}
_NETWORK = {"none", "required"}
_FILESYSTEM = {"none", "read", "write"}
_APPROVAL = {"none", "required"}


@dataclass(frozen=True)
class CapabilityRequirement:
    """A capability the Agent needs. Never binds a catalog resource ID."""

    capability: str
    required: bool = True
    input_types: tuple[str, ...] = ()
    output_types: tuple[str, ...] = ()
    side_effect: SideEffect = "none"
    network: NetworkNeed = "none"
    filesystem: FilesystemNeed = "none"
    approval: ApprovalNeed = "none"
    model_capability: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "capability": self.capability,
            "required": self.required,
            "input_types": list(self.input_types),
            "output_types": list(self.output_types),
            "side_effect": self.side_effect,
            "network": self.network,
            "filesystem": self.filesystem,
            "approval": self.approval,
        }
        if self.model_capability:
            payload["model_capability"] = self.model_capability
        return payload

    @classmethod
    def from_dict(cls, data: Any) -> CapabilityRequirement:
        item = require_mapping(data, "capability requirement")
        capability = require_string(item.get("capability"), "capability")
        required = item.get("required", True)
        if not isinstance(required, bool):
            raise ContractValidationError(
                "capability requirement.required must be boolean"
            )
        side_effect = str(item.get("side_effect") or "none")
        network = str(item.get("network") or "none")
        filesystem = str(item.get("filesystem") or "none")
        approval = str(item.get("approval") or "none")
        if side_effect not in _SIDE_EFFECTS:
            raise ContractValidationError(
                "capability requirement.side_effect is invalid"
            )
        if network not in _NETWORK:
            raise ContractValidationError("capability requirement.network is invalid")
        if filesystem not in _FILESYSTEM:
            raise ContractValidationError(
                "capability requirement.filesystem is invalid"
            )
        if approval not in _APPROVAL:
            raise ContractValidationError("capability requirement.approval is invalid")
        model = item.get("model_capability")
        if model is not None:
            model = require_string(model, "model_capability")
        return cls(
            capability=capability,
            required=required,
            input_types=_string_tuple(item.get("input_types") or [], "input_types"),
            output_types=_string_tuple(item.get("output_types") or [], "output_types"),
            side_effect=side_effect,  # type: ignore[arg-type]
            network=network,  # type: ignore[arg-type]
            filesystem=filesystem,  # type: ignore[arg-type]
            approval=approval,  # type: ignore[arg-type]
            model_capability=model,
        )


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    items = require_list(value, field)
    return tuple(
        require_string(item, f"{field}[{index}]") for index, item in enumerate(items)
    )
