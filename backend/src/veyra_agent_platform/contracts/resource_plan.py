"""Server-owned ResourcePlan snapshot for Proposal, Apply, and composition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .capability import CapabilityRequirement
from .common import (
    ContractValidationError,
    require_list,
    require_mapping,
    require_string,
)

BindStatus = Literal[
    "already_bound",
    "will_bind",
    "needs_configuration",
    "unavailable",
    "missing",
]
RuntimeSupport = Literal["full", "partial", "none"]
KnowledgeStatus = Literal[
    "not_requested",
    "available",
    "missing",
    "requires_user_input",
]

_BIND = {
    "already_bound",
    "will_bind",
    "needs_configuration",
    "unavailable",
    "missing",
}
_SUPPORT = {"full", "partial", "none"}
_KNOWLEDGE = {
    "not_requested",
    "available",
    "missing",
    "requires_user_input",
}


@dataclass(frozen=True)
class PlannedResource:
    resource_id: str
    version: str
    content_hash: str
    kind: str
    capabilities: tuple[str, ...]
    reason: str
    bind_status: BindStatus
    reference: str
    name: str
    availability: str = "ready"
    runtime_status: str = "supported"
    runtime_support: RuntimeSupport = "full"
    factory_selectable: bool = True
    required_permissions: dict[str, Any] | None = None
    secret_ref: str | None = None
    adapter: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "resource_id": self.resource_id,
            "version": self.version,
            "content_hash": self.content_hash,
            "kind": self.kind,
            "capabilities": list(self.capabilities),
            "reason": self.reason,
            "bind_status": self.bind_status,
            "reference": self.reference,
            "name": self.name,
            "availability": self.availability,
            "runtime_status": self.runtime_status,
            "runtime_support": self.runtime_support,
            "factory_selectable": self.factory_selectable,
        }
        if self.required_permissions is not None:
            payload["required_permissions"] = dict(self.required_permissions)
        if self.secret_ref:
            payload["secret_ref"] = self.secret_ref
        if self.adapter:
            payload["adapter"] = self.adapter
        return payload

    @classmethod
    def from_dict(cls, data: Any) -> PlannedResource:
        item = require_mapping(data, "planned resource")
        status = require_string(item.get("bind_status"), "bind_status")
        support = str(item.get("runtime_support") or "full")
        if status not in _BIND:
            raise ContractValidationError("planned resource.bind_status is invalid")
        if support not in _SUPPORT:
            raise ContractValidationError("planned resource.runtime_support is invalid")
        capabilities = tuple(
            require_string(value, f"capabilities[{index}]")
            for index, value in enumerate(
                require_list(item.get("capabilities") or [], "capabilities")
            )
        )
        return cls(
            resource_id=require_string(item.get("resource_id"), "resource_id"),
            version=require_string(item.get("version"), "version"),
            content_hash=require_string(item.get("content_hash"), "content_hash"),
            kind=require_string(item.get("kind"), "kind"),
            capabilities=capabilities,
            reason=str(item.get("reason") or ""),
            bind_status=status,  # type: ignore[arg-type]
            reference=require_string(item.get("reference"), "reference"),
            name=str(item.get("name") or item.get("resource_id") or ""),
            availability=str(item.get("availability") or "ready"),
            runtime_status=str(item.get("runtime_status") or "supported"),
            runtime_support=support,  # type: ignore[arg-type]
            factory_selectable=bool(item.get("factory_selectable", True)),
            required_permissions=(
                dict(item["required_permissions"])
                if isinstance(item.get("required_permissions"), dict)
                else None
            ),
            secret_ref=(
                str(item["secret_ref"])
                if isinstance(item.get("secret_ref"), str) and item.get("secret_ref")
                else None
            ),
            adapter=str(item.get("adapter") or ""),
        )


@dataclass(frozen=True)
class MissingCapability:
    capability: str
    status: str = "missing"
    reason: str = ""
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "status": self.status,
            "reason": self.reason,
            "required": self.required,
        }

    @classmethod
    def from_dict(cls, data: Any) -> MissingCapability:
        item = require_mapping(data, "missing capability")
        return cls(
            capability=require_string(item.get("capability"), "capability"),
            status=str(item.get("status") or "missing"),
            reason=str(item.get("reason") or ""),
            required=bool(item.get("required", True)),
        )


@dataclass(frozen=True)
class KnowledgeBindingPlan:
    status: KnowledgeStatus
    selected_refs: tuple[str, ...] = ()
    source_count: int = 0
    documents: tuple[dict[str, Any], ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "selected_refs": list(self.selected_refs),
            "source_count": self.source_count,
            "documents": [dict(item) for item in self.documents],
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Any) -> KnowledgeBindingPlan:
        item = require_mapping(data, "knowledge binding plan")
        status = str(item.get("status") or "not_requested")
        if status not in _KNOWLEDGE:
            raise ContractValidationError("knowledge binding plan.status is invalid")
        refs = tuple(
            require_string(value, f"selected_refs[{index}]")
            for index, value in enumerate(
                require_list(item.get("selected_refs") or [], "selected_refs")
            )
        )
        documents = tuple(
            dict(require_mapping(value, f"documents[{index}]"))
            for index, value in enumerate(
                require_list(item.get("documents") or [], "documents")
            )
        )
        return cls(
            status=status,  # type: ignore[arg-type]
            selected_refs=refs,
            source_count=int(item.get("source_count") or len(refs)),
            documents=documents,
            reason=str(item.get("reason") or ""),
        )


@dataclass(frozen=True)
class ResourcePlan:
    selected: tuple[PlannedResource, ...] = ()
    already_bound: tuple[PlannedResource, ...] = ()
    will_bind: tuple[PlannedResource, ...] = ()
    needs_configuration: tuple[PlannedResource, ...] = ()
    missing_required: tuple[MissingCapability, ...] = ()
    optional_unresolved: tuple[MissingCapability, ...] = ()
    knowledge: KnowledgeBindingPlan = KnowledgeBindingPlan(status="not_requested")
    diagnostics: tuple[str, ...] = ()
    requirements: tuple[CapabilityRequirement, ...] = ()
    rejected_references: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "resource_plan.v1",
            "selected": [item.to_dict() for item in self.selected],
            "already_bound": [item.to_dict() for item in self.already_bound],
            "will_bind": [item.to_dict() for item in self.will_bind],
            "needs_configuration": [
                item.to_dict() for item in self.needs_configuration
            ],
            "missing_required": [item.to_dict() for item in self.missing_required],
            "optional_unresolved": [
                item.to_dict() for item in self.optional_unresolved
            ],
            "knowledge": self.knowledge.to_dict(),
            "diagnostics": list(self.diagnostics),
            "requirements": [item.to_dict() for item in self.requirements],
            "rejected_references": list(self.rejected_references),
        }

    @classmethod
    def from_dict(cls, data: Any) -> ResourcePlan:
        item = require_mapping(data, "resource plan")
        return cls(
            selected=_planned_tuple(item.get("selected") or [], "selected"),
            already_bound=_planned_tuple(
                item.get("already_bound") or [], "already_bound"
            ),
            will_bind=_planned_tuple(item.get("will_bind") or [], "will_bind"),
            needs_configuration=_planned_tuple(
                item.get("needs_configuration") or [], "needs_configuration"
            ),
            missing_required=_missing_tuple(
                item.get("missing_required") or [], "missing_required"
            ),
            optional_unresolved=_missing_tuple(
                item.get("optional_unresolved") or [], "optional_unresolved"
            ),
            knowledge=KnowledgeBindingPlan.from_dict(
                item.get("knowledge") or {"status": "not_requested"}
            ),
            diagnostics=tuple(
                require_string(value, f"diagnostics[{index}]")
                for index, value in enumerate(
                    require_list(item.get("diagnostics") or [], "diagnostics")
                )
            ),
            requirements=tuple(
                CapabilityRequirement.from_dict(value)
                for value in require_list(
                    item.get("requirements") or [], "requirements"
                )
            ),
            rejected_references=tuple(
                require_string(value, f"rejected_references[{index}]")
                for index, value in enumerate(
                    require_list(
                        item.get("rejected_references") or [], "rejected_references"
                    )
                )
            ),
        )


def _planned_tuple(value: Any, field: str) -> tuple[PlannedResource, ...]:
    return tuple(PlannedResource.from_dict(item) for item in require_list(value, field))


def _missing_tuple(value: Any, field: str) -> tuple[MissingCapability, ...]:
    return tuple(
        MissingCapability.from_dict(item) for item in require_list(value, field)
    )
