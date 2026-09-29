"""Deterministic Resource Resolver: capability → catalog/project snapshot.

The model may help name capabilities. Only this service may choose resource IDs,
versions, and content hashes from a real Catalog/Project snapshot.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

from veyra_agent_platform.contracts.agent_spec import AgentSpecification
from veyra_agent_platform.contracts.capability import CapabilityRequirement
from veyra_agent_platform.contracts.resource_plan import (
    KnowledgeBindingPlan,
    MissingCapability,
    PlannedResource,
    ResourcePlan,
)
from veyra_agent_platform.local.builder.capability_requirements import (
    claimed_resource_references,
)
from veyra_agent_platform.local.builder.knowledge_binding import knowledge_reference
from veyra_agent_platform.local.library.knowledge_context import MAX_DOCUMENTS
from veyra_agent_platform.local.library.resource_truth import (
    needs_host_configuration,
    pin_hash,
    project_pin,
    project_pin_by_reference,
)
from veyra_agent_platform.local.resources import ResourceCatalog, ResourceCatalogError
from veyra_agent_platform.local.resources.capabilities import (
    BLOCKED_AVAILABILITY,
    CAPABILITY_LABELS,
    CATALOG_RESOURCE_KINDS,
    EXECUTABLE_KINDS,
    MODEL_ONLY_CAPABILITIES,
)

BindStatus = Literal["already_bound", "will_bind", "needs_configuration", "unavailable"]
_BIND_RANK = {
    "already_bound": 0,
    "will_bind": 1,
    "needs_configuration": 2,
    "unavailable": 3,
}


class ResourceResolver:
    """Fail-closed ranking of real catalog and Project resources."""

    def __init__(
        self,
        catalog: ResourceCatalog,
        *,
        secret_configured: Callable[[str], bool] | None = None,
    ) -> None:
        self.catalog = catalog
        self._secret_configured = secret_configured

    def resolve(
        self,
        specification: AgentSpecification,
        requirements: Sequence[CapabilityRequirement],
        *,
        project_resources: Sequence[Mapping[str, Any]] | None = None,
        knowledge_inventory: Sequence[Mapping[str, Any]] | None = None,
        catalog_resources: Sequence[Mapping[str, Any]] | None = None,
        claimed_references: Sequence[str] | None = None,
        requirement_text: str = "",
    ) -> ResourcePlan:
        owned = list(project_resources or [])
        snapshot = [dict(item) for item in (catalog_resources or [])]
        if not snapshot:
            snapshot = list(self.catalog.resources()["resources"])
        claimed = tuple(claimed_references or ())
        if not claimed:
            claimed = claimed_resource_references(
                requirement_text,
                specification.goal,
                specification.description,
                " ".join(specification.responsibilities),
            )
        diagnostics: list[str] = []
        rejected = self._reject_claimed(claimed, snapshot, diagnostics)
        selected: dict[str, PlannedResource] = {}
        needs_configuration: list[PlannedResource] = []
        missing_required: list[MissingCapability] = []
        optional_unresolved: list[MissingCapability] = []
        catalog_by_ref = {
            str(item.get("reference")): item
            for item in snapshot
            if item.get("reference")
        }

        for requirement in requirements:
            if requirement.capability in MODEL_ONLY_CAPABILITIES:
                continue
            if requirement.capability == "project_knowledge":
                continue
            chosen = self._choose(
                requirement,
                snapshot,
                owned,
                catalog_by_ref,
                diagnostics,
            )
            if chosen is None:
                gap = MissingCapability(
                    capability=requirement.capability,
                    status="missing",
                    reason=(
                        "No catalog resource provides this capability "
                        "in a selectable, supported state"
                    ),
                    required=requirement.required,
                )
                if requirement.required:
                    missing_required.append(gap)
                    diagnostics.append(f"missing_capability:{requirement.capability}")
                else:
                    optional_unresolved.append(gap)
                continue
            resource, status, reason = chosen
            planned = self._planned(resource, status, requirement, reason)
            if status == "needs_configuration":
                needs_configuration.append(planned)
                diagnostics.append(
                    f"needs_configuration:{planned.reference}:{requirement.capability}"
                )
                continue
            if status == "unavailable":
                if requirement.required:
                    missing_required.append(
                        MissingCapability(
                            capability=requirement.capability,
                            status="unavailable",
                            reason=reason,
                            required=True,
                        )
                    )
                    diagnostics.append(
                        f"unavailable_capability:{requirement.capability}"
                    )
                else:
                    optional_unresolved.append(
                        MissingCapability(
                            capability=requirement.capability,
                            status="unavailable",
                            reason=reason,
                            required=False,
                        )
                    )
                continue
            existing = selected.get(planned.resource_id)
            if (
                existing is None
                or _BIND_RANK[planned.bind_status] < _BIND_RANK[existing.bind_status]
            ):
                selected[planned.resource_id] = planned

        knowledge = self._knowledge_plan(
            requirements, list(knowledge_inventory or []), diagnostics
        )
        selected_items = tuple(
            sorted(selected.values(), key=lambda item: item.resource_id)
        )
        already = tuple(
            item for item in selected_items if item.bind_status == "already_bound"
        )
        will_bind = tuple(
            item for item in selected_items if item.bind_status == "will_bind"
        )
        return ResourcePlan(
            selected=selected_items,
            already_bound=already,
            will_bind=will_bind,
            needs_configuration=tuple(needs_configuration),
            missing_required=tuple(missing_required),
            optional_unresolved=tuple(optional_unresolved),
            knowledge=knowledge,
            diagnostics=tuple(diagnostics),
            requirements=tuple(requirements),
            rejected_references=rejected,
        )

    def _reject_claimed(
        self,
        claimed: Sequence[str],
        snapshot: Sequence[Mapping[str, Any]],
        diagnostics: list[str],
    ) -> tuple[str, ...]:
        known = {
            str(item.get("resource_id")) for item in snapshot if item.get("resource_id")
        }
        known_refs = {
            str(item.get("reference")) for item in snapshot if item.get("reference")
        }
        rejected: list[str] = []
        for token in claimed:
            resource_id = token.split("@", 1)[0]
            if token in known_refs or resource_id in known:
                continue
            rejected.append(token)
            diagnostics.append(f"rejected_unknown_resource:{token}")
        return tuple(rejected)

    def _choose(
        self,
        requirement: CapabilityRequirement,
        snapshot: Sequence[Mapping[str, Any]],
        owned: Sequence[Mapping[str, Any]],
        catalog_by_ref: Mapping[str, Mapping[str, Any]],
        diagnostics: list[str],
    ) -> tuple[dict[str, Any], BindStatus, str] | None:
        ranked: list[tuple[tuple[object, ...], dict[str, Any], BindStatus, str]] = []
        for raw in snapshot:
            resource = dict(raw)
            if not _capability_match(resource, requirement.capability):
                continue
            eligible, ineligible_reason = _eligibility(resource, requirement)
            if not eligible:
                diagnostics.append(
                    f"rejected:{resource.get('reference')}:{ineligible_reason}"
                )
                continue
            status = self._bind_status(resource, owned, catalog_by_ref)
            reason = _reason(resource, status, requirement)
            ranked.append(
                (_rank_key(resource, status, requirement), resource, status, reason)
            )
        if not ranked:
            return None
        ranked.sort(key=lambda item: item[0])
        _key, resource, status, reason = ranked[0]
        if status == "already_bound":
            pinned = project_pin_by_reference(
                owned, str(resource.get("reference") or "")
            ) or project_pin(owned, str(resource.get("resource_id") or ""))
            if pinned is not None:
                resource = dict(resource)
                digest = pin_hash(pinned) or str(resource.get("content_hash") or "")
                resource["lock_hash"] = digest
                if pinned.get("reference"):
                    resource["reference"] = str(pinned["reference"])
        return resource, status, reason

    def _bind_status(
        self,
        resource: Mapping[str, Any],
        owned: Sequence[Mapping[str, Any]],
        catalog_by_ref: Mapping[str, Mapping[str, Any]],
    ) -> BindStatus:
        availability = str(resource.get("availability") or "")
        if availability in BLOCKED_AVAILABILITY:
            return "unavailable"
        if self._needs_configuration(resource):
            pinned = project_pin_by_reference(
                owned, str(resource.get("reference") or "")
            )
            if pinned is not None:
                return "needs_configuration"
            return "needs_configuration"
        reference = str(resource.get("reference") or "")
        pinned = project_pin_by_reference(owned, reference)
        if pinned is None:
            pinned = project_pin(owned, str(resource.get("resource_id") or ""))
        if pinned is not None:
            catalog_item = catalog_by_ref.get(str(pinned.get("reference") or reference))
            digest = pin_hash(pinned)
            catalog_hash = None
            if catalog_item is not None:
                catalog_hash = str(catalog_item.get("content_hash") or "")
            if digest and catalog_hash and digest != catalog_hash:
                return "unavailable"
            return "already_bound"
        if availability != "ready":
            return "unavailable"
        return "will_bind"

    def _needs_configuration(self, resource: Mapping[str, Any]) -> bool:
        if needs_host_configuration(resource):
            return True
        if str(resource.get("availability") or "") == "requires_configuration":
            return True
        spec = resource.get("spec")
        if not isinstance(spec, Mapping):
            return False
        secret_ref = spec.get("secret_ref")
        if not isinstance(secret_ref, str) or not secret_ref:
            return False
        if self._secret_configured is None:
            return True
        return not bool(self._secret_configured(secret_ref))

    def _planned(
        self,
        resource: Mapping[str, Any],
        status: BindStatus,
        requirement: CapabilityRequirement,
        reason: str,
    ) -> PlannedResource:
        kind = str(resource.get("kind") or "")
        support: Literal["full", "partial", "none"] = "full"
        if kind == "policy":
            support = "partial"
        elif kind == "skill":
            support = "full"
        elif kind in EXECUTABLE_KINDS and not (resource.get("spec") or {}).get(
            "adapter"
        ):
            support = "none"
        version = str(resource.get("version") or "")
        resource_id = str(resource.get("resource_id") or "")
        reference = str(resource.get("reference") or f"{resource_id}@{version}")
        digest = str(resource.get("lock_hash") or resource.get("content_hash") or "")
        capabilities = tuple(
            str(item) for item in (resource.get("capabilities") or ()) if item
        )
        spec = resource.get("spec") if isinstance(resource.get("spec"), Mapping) else {}
        secret_ref = spec.get("secret_ref") if isinstance(spec, Mapping) else None
        permissions = resource.get("required_permissions")
        return PlannedResource(
            resource_id=resource_id,
            version=version,
            content_hash=digest,
            kind=kind,
            capabilities=capabilities,
            reason=reason,
            bind_status=status,
            reference=reference,
            name=str(resource.get("name") or resource_id),
            availability=str(resource.get("availability") or "ready"),
            runtime_status=str(resource.get("runtime_status") or "supported"),
            runtime_support=support,
            factory_selectable=bool(resource.get("factory_selectable", True)),
            required_permissions=(
                dict(permissions) if isinstance(permissions, Mapping) else None
            ),
            secret_ref=str(secret_ref)
            if isinstance(secret_ref, str) and secret_ref
            else None,
        )

    def _knowledge_plan(
        self,
        requirements: Sequence[CapabilityRequirement],
        inventory: Sequence[Mapping[str, Any]],
        diagnostics: list[str],
    ) -> KnowledgeBindingPlan:
        needed = any(item.capability == "project_knowledge" for item in requirements)
        if not needed:
            return KnowledgeBindingPlan(status="not_requested")
        documents = [dict(item) for item in inventory if item.get("knowledge_id")]
        if not documents:
            diagnostics.append("missing_capability:project_knowledge")
            return KnowledgeBindingPlan(
                status="missing",
                source_count=0,
                reason="Project has no Knowledge documents to bind",
            )
        indexed = [
            item
            for item in documents
            if str((item.get("processing") or {}).get("index_status") or "")
            == "indexed"
        ]
        chosen = (indexed or documents)[:MAX_DOCUMENTS]
        refs = tuple(knowledge_reference(item) for item in chosen)
        diagnostics.append(f"knowledge_available:{len(chosen)}")
        return KnowledgeBindingPlan(
            status="available",
            selected_refs=refs,
            source_count=len(documents),
            documents=tuple(chosen),
            reason=f"{len(documents)} sources available",
        )


def plan_factory_items(plan: ResourcePlan) -> list[dict[str, Any]]:
    """Factory session resource_plan rows, including knowledge and missing seams."""

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for resource in (
        *plan.selected,
        *plan.needs_configuration,
    ):
        if resource.reference in seen:
            continue
        seen.add(resource.reference)
        items.append(_factory_item(resource))
    if plan.knowledge.status == "available":
        items.append(
            {
                "reference": "project.knowledge",
                "kind": "knowledge",
                "availability": "ready",
                "runtime_status": "supported",
                "name": "Project Knowledge",
                "bind_status": "already_bound",
                "capability": "project_knowledge",
                "reason": plan.knowledge.reason or "Project Knowledge available",
                "source_count": plan.knowledge.source_count,
            }
        )
    elif plan.knowledge.status in {"missing", "requires_user_input"}:
        items.append(
            {
                "reference": "project.knowledge",
                "kind": "knowledge",
                "availability": "requires_configuration",
                "runtime_status": "runtime_not_configured",
                "name": "Project Knowledge",
                "bind_status": "missing",
                "capability": "project_knowledge",
                "reason": plan.knowledge.reason or "No Project Knowledge",
                "source_count": 0,
            }
        )
    for gap in plan.missing_required:
        items.append(
            {
                "reference": f"capability.{gap.capability}",
                "kind": "capability",
                "availability": "unavailable",
                "runtime_status": "runtime_not_supported",
                "name": CAPABILITY_LABELS.get(gap.capability, gap.capability),
                "bind_status": "missing",
                "capability": gap.capability,
                "reason": gap.reason or f"Missing capability: {gap.capability}",
            }
        )
    return items


def _factory_item(resource: PlannedResource) -> dict[str, Any]:
    capability = resource.capabilities[0] if resource.capabilities else ""
    return {
        "reference": resource.reference,
        "kind": resource.kind,
        "availability": (
            "requires_configuration"
            if resource.bind_status == "needs_configuration"
            else resource.availability
        ),
        "runtime_status": resource.runtime_status,
        "name": resource.name,
        "bind_status": resource.bind_status,
        "capability": capability,
        "reason": resource.reason,
        "runtime_support": resource.runtime_support,
        "version": resource.version,
        "capabilities": list(resource.capabilities),
    }


def _capability_match(resource: Mapping[str, Any], capability: str) -> bool:
    tags = resource.get("capabilities") or []
    return capability in tags


def _eligibility(
    resource: Mapping[str, Any], requirement: CapabilityRequirement
) -> tuple[bool, str]:
    kind = str(resource.get("kind") or "")
    if kind not in CATALOG_RESOURCE_KINDS:
        return False, "incompatible_kind"
    if resource.get("loop_compatible") is False or kind == "template":
        return False, "exclude_from_loop_composition"
    if resource.get("factory_selectable") is not True:
        return False, "factory_selectable_false"
    availability = str(resource.get("availability") or "")
    if availability in BLOCKED_AVAILABILITY:
        return False, f"availability_{availability}"
    spec = _spec_map(resource)
    if kind in EXECUTABLE_KINDS and not spec.get("adapter"):
        return False, "runtime_adapter_missing"
    if str(resource.get("runtime_status") or "") == "runtime_not_supported":
        return False, "runtime_not_supported"
    if not _io_compatible(spec, requirement):
        return False, "typed_io_incompatible"
    if not _constraint_compatible(resource, requirement):
        return False, "constraint_incompatible"
    return True, ""


def _io_compatible(spec: Mapping[str, Any], requirement: CapabilityRequirement) -> bool:
    if not requirement.input_types:
        return True
    schema = spec.get("input_schema")
    if not isinstance(schema, Mapping) or not schema:
        return True
    resource_types = {str(value).casefold() for value in schema.values()}
    needed = {item.casefold() for item in requirement.input_types}
    return bool(needed & resource_types)


def _constraint_compatible(
    resource: Mapping[str, Any], requirement: CapabilityRequirement
) -> bool:
    perms = resource.get("required_permissions") or {}
    write_roots = (
        perms.get("filesystem_write_roots") if isinstance(perms, Mapping) else []
    )
    if requirement.filesystem == "read" and write_roots:
        return False
    hosts = perms.get("network_hosts") if isinstance(perms, Mapping) else []
    return not (requirement.network == "none" and hosts)


def _rank_key(
    resource: Mapping[str, Any],
    status: BindStatus,
    requirement: CapabilityRequirement,
) -> tuple[object, ...]:
    capabilities = tuple(resource.get("capabilities") or ())
    exact = 0 if requirement.capability in capabilities else 1
    extra = len(capabilities)
    spec = _spec_map(resource)
    approval_cost = 1 if spec.get("approval_required") else 0
    origin = 0 if resource.get("origin") == "builtin" else 1
    return (
        _BIND_RANK[status],
        exact,
        extra,
        origin,
        approval_cost,
        str(resource.get("resource_id") or ""),
    )


def _reason(
    resource: Mapping[str, Any],
    status: BindStatus,
    requirement: CapabilityRequirement,
) -> str:
    name = str(resource.get("name") or resource.get("resource_id") or "")
    if status == "already_bound":
        return f"Already pinned in Project; matches {requirement.capability}"
    if status == "will_bind":
        return f"Ready builtin resource matches {requirement.capability}"
    if status == "needs_configuration":
        return f"{name} matches {requirement.capability} but needs configuration"
    return f"{name} matches {requirement.capability} but is not ready"


def _spec_map(resource: Mapping[str, Any]) -> Mapping[str, Any]:
    spec = resource.get("spec")
    return spec if isinstance(spec, Mapping) else {}


def catalog_snapshot(catalog: ResourceCatalog) -> list[dict[str, Any]]:
    try:
        return list(catalog.resources()["resources"])
    except ResourceCatalogError:
        return []
