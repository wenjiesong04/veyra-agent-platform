"""Create quarantined Catalog resources for missing capabilities.

Resource Factory drafts overlay node.yaml through ResourceWorkshop. Generated
Tools are declarative specializations of existing Runtime adapters. Nothing here
executes model-written code.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.capability import CapabilityRequirement
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.contracts.resource_factory import ResourceFactoryPlan
from veyra_agent_platform.contracts.resource_plan import ResourcePlan
from veyra_agent_platform.local.resources.catalog import ResourceCatalog
from veyra_agent_platform.local.resources.factory_strategy import (
    SAFE_FS_ADAPTERS,
    SAFE_HTTP_ADAPTER,
    classify_factory_strategy,
    wrapper_adapter,
)
from veyra_agent_platform.local.resources.factory_validation import (
    ResourceFactoryValidationError,
    snapshot_identity,
    validate_skill_draft,
    validate_tool_wrapper,
)
from veyra_agent_platform.local.resources.workshop import (
    ResourceWorkshop,
    ResourceWorkshopError,
)

_EMPTY_PERMISSIONS = {
    "network_hosts": [],
    "tools": [],
    "filesystem_read_roots": [],
    "filesystem_write_roots": [],
    "shell_workspace_only": False,
}


class ResourceFactoryError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ResourceFactory:
    def __init__(self, workshop: ResourceWorkshop, catalog: ResourceCatalog) -> None:
        self.workshop = workshop
        self.catalog = catalog

    def plan_missing(
        self,
        plan: ResourcePlan,
        *,
        wrappers: Mapping[str, Mapping[str, Any]] | None = None,
        existing: Sequence[Mapping[str, Any]] | None = None,
        proposal_id: str | None = None,
    ) -> list[ResourceFactoryPlan]:
        """Classify Resolver missing_required. Does not call Workshop until drafts."""

        prior = {
            str(item.get("capability")): ResourceFactoryPlan.from_dict(item)
            for item in existing or []
            if isinstance(item, Mapping) and item.get("capability")
        }
        wrappers = wrappers or {}
        results: list[ResourceFactoryPlan] = []
        for gap in plan.missing_required:
            requirement = _requirement_for(plan, gap.capability)
            wrapper = wrappers.get(gap.capability)
            strategy = classify_factory_strategy(requirement, wrapper=wrapper)
            previous = prior.get(gap.capability)
            operation_id = previous.operation_id if previous else new_uuid7()
            results.append(
                ResourceFactoryPlan(
                    capability=gap.capability,
                    status=strategy.status,
                    strategy=strategy.generation_strategy,
                    can_generate=strategy.can_generate,
                    reason=strategy.reason,
                    risk_level=strategy.risk_level,
                    resource_kind=strategy.resource_kind,
                    requirements=strategy.requirements,
                    draft=previous.draft if previous else None,
                    validation=previous.validation if previous else None,
                    published=previous.published if previous else None,
                    snapshot_hash=previous.snapshot_hash if previous else None,
                    proposal_id=proposal_id
                    or (previous.proposal_id if previous else None),
                    operation_id=operation_id,
                )
            )
        return results

    def ensure_skill_draft(
        self, planned: ResourceFactoryPlan, requirement: CapabilityRequirement
    ) -> ResourceFactoryPlan:
        if planned.strategy != "skill_instruction" or not planned.can_generate:
            raise ResourceFactoryError(
                "factory_unsupported",
                planned.reason or "Skill generation is unsupported",
            )
        if planned.draft and planned.snapshot_hash:
            return planned
        instruction = skill_instruction_for(requirement.capability)
        name = _display_name(requirement.capability)
        description = (
            f"Factory Skill for the `{requirement.capability}` capability. "
            "Instruction resource only; it does not grant tools or permissions."
        )
        try:
            validation = validate_skill_draft(
                instruction=instruction,
                capabilities=[requirement.capability],
                name=name,
                description=description,
            )
        except ResourceFactoryValidationError as exc:
            raise ResourceFactoryError(exc.code, str(exc)) from exc
        resource_id, package_id = _new_resource_id("skill", requirement.capability)
        payload = _skill_payload(
            resource_id=resource_id,
            name=name,
            description=description,
            instruction=instruction,
            capabilities=[requirement.capability],
            availability="quarantined",
            selectable=False,
            runtime_status="runtime_not_supported",
            version="0.0.1",
        )
        resource = self.workshop.write_overlay(payload, package_id=package_id)
        digest = snapshot_identity(resource)
        return ResourceFactoryPlan(
            capability=planned.capability,
            status=planned.status,
            strategy=planned.strategy,
            can_generate=True,
            reason=planned.reason,
            risk_level=planned.risk_level,
            resource_kind="skill",
            requirements=planned.requirements,
            draft=resource,
            validation=validation,
            published=None,
            snapshot_hash=digest,
            proposal_id=planned.proposal_id,
            operation_id=planned.operation_id or new_uuid7(),
        )

    def ensure_wrapper_draft(
        self,
        planned: ResourceFactoryPlan,
        requirement: CapabilityRequirement,
        wrapper: Mapping[str, Any],
    ) -> ResourceFactoryPlan:
        if planned.strategy not in {"http_tool_wrapper", "filesystem_tool_wrapper"}:
            raise ResourceFactoryError(
                "factory_unsupported",
                planned.reason or "Wrapper generation is unsupported",
            )
        if not planned.can_generate:
            raise ResourceFactoryError(
                "factory_requires_configuration"
                if planned.status == "requires_user_configuration"
                else "factory_unsupported",
                planned.reason,
            )
        if planned.draft and planned.snapshot_hash:
            return planned
        spec = _wrapper_spec(requirement.capability, wrapper)
        try:
            validation = validate_tool_wrapper(spec)
        except ResourceFactoryValidationError as exc:
            raise ResourceFactoryError(exc.code, str(exc)) from exc
        resource_id, package_id = _new_resource_id("tool", requirement.capability)
        payload = _wrapper_payload(
            resource_id=resource_id,
            capability=requirement.capability,
            spec=spec,
            availability="quarantined",
            selectable=False,
            runtime_status="runtime_not_supported",
            version="0.0.1",
        )
        resource = self.workshop.write_overlay(payload, package_id=package_id)
        return ResourceFactoryPlan(
            capability=planned.capability,
            status="generatable",
            strategy=planned.strategy,
            can_generate=True,
            reason=planned.reason,
            risk_level=planned.risk_level,
            resource_kind="tool",
            requirements=planned.requirements,
            draft=resource,
            validation=validation,
            published=None,
            snapshot_hash=snapshot_identity(resource),
            proposal_id=planned.proposal_id,
            operation_id=planned.operation_id or new_uuid7(),
        )

    def publish(
        self,
        planned: ResourceFactoryPlan,
        *,
        confirm: bool,
        snapshot_hash: str | None = None,
    ) -> ResourceFactoryPlan:
        if not confirm:
            raise ResourceFactoryError(
                "factory_confirmation_required",
                "Explicit confirmation is required to publish a Factory Resource",
            )
        if planned.draft is None or not planned.snapshot_hash:
            raise ResourceFactoryError(
                "factory_draft_missing", "A reviewed Factory draft is required"
            )
        expected = snapshot_hash or planned.snapshot_hash
        resource_id = str(planned.draft.get("resource_id") or "")
        version = str(planned.draft.get("version") or "")
        current = self.catalog.detail(resource_id, version)
        already = (
            current.get("availability") == "ready"
            and current.get("factory_selectable") is True
        )
        if already:
            published_hash = str((planned.published or {}).get("content_hash") or "")
            if expected in {
                planned.snapshot_hash,
                current.get("content_hash"),
                published_hash,
            }:
                return ResourceFactoryPlan(
                    capability=planned.capability,
                    status=planned.status,
                    strategy=planned.strategy,
                    can_generate=planned.can_generate,
                    reason=planned.reason,
                    risk_level=planned.risk_level,
                    resource_kind=planned.resource_kind,
                    requirements=planned.requirements,
                    draft=planned.draft,
                    validation=planned.validation,
                    published=current,
                    snapshot_hash=planned.snapshot_hash,
                    proposal_id=planned.proposal_id,
                    operation_id=planned.operation_id,
                )
        if snapshot_identity(current) != expected:
            raise ResourceFactoryError(
                "factory_snapshot_mismatch",
                "Factory draft snapshot does not match the stored Proposal",
            )
        payload = self.workshop.overlay_payload(resource_id, version)
        try:
            if payload.get("kind") == "skill":
                instruction = str((payload.get("spec") or {}).get("instruction") or "")
                validate_skill_draft(
                    instruction=instruction,
                    capabilities=list(payload.get("capabilities") or []),
                    name=str(payload.get("name") or ""),
                    description=str(payload.get("description") or ""),
                )
                payload["availability"] = "ready"
                payload["factory_selectable"] = True
                payload["runtime_status"] = "runtime_not_configured"
                payload["tags"] = ["workshop", "factory", "approved", "instruction"]
                spec = payload.setdefault("spec", {})
                spec["review_required"] = False
                spec["validation_passed"] = True
            else:
                validate_tool_wrapper(payload.get("spec") or {})
                payload["availability"] = "ready"
                payload["factory_selectable"] = True
                payload["runtime_status"] = "supported"
                payload["tags"] = ["workshop", "factory", "approved", "tool_wrapper"]
                spec = payload.setdefault("spec", {})
                spec["executable"] = True
                spec["review_required"] = False
                spec["validation_passed"] = True
        except ResourceFactoryValidationError as exc:
            raise ResourceFactoryError(exc.code, str(exc)) from exc
        published = self.workshop.replace_overlay(resource_id, version, payload)
        return ResourceFactoryPlan(
            capability=planned.capability,
            status=planned.status,
            strategy=planned.strategy,
            can_generate=planned.can_generate,
            reason=planned.reason,
            risk_level=planned.risk_level,
            resource_kind=planned.resource_kind,
            requirements=planned.requirements,
            draft=planned.draft,
            validation=planned.validation,
            published=published,
            snapshot_hash=planned.snapshot_hash,
            proposal_id=planned.proposal_id,
            operation_id=planned.operation_id,
        )

    def revise_skill(
        self,
        published_id: str,
        published_version: str,
        instruction: str,
        *,
        confirm: bool,
    ) -> dict[str, Any]:
        if not confirm:
            raise ResourceFactoryError(
                "factory_confirmation_required",
                "Explicit confirmation is required to create a new Skill version",
            )
        current = self.catalog.detail(published_id, published_version)
        if current.get("kind") != "skill" or current.get("origin") != "workshop":
            raise ResourceFactoryError(
                "factory_unsupported", "Only published workshop Skills can be revised"
            )
        capabilities = [str(item) for item in (current.get("capabilities") or [])]
        validate_skill_draft(
            instruction=instruction,
            capabilities=capabilities,
            name=str(current.get("name") or ""),
            description=str(current.get("description") or ""),
        )
        next_version = _next_version(self.catalog, published_id, published_version)
        payload = self.workshop.overlay_payload(published_id, published_version)
        payload["version"] = next_version
        payload["availability"] = "quarantined"
        payload["factory_selectable"] = False
        payload["runtime_status"] = "runtime_not_supported"
        payload["tags"] = ["workshop", "factory", "quarantined"]
        spec = payload.setdefault("spec", {})
        spec["instruction"] = instruction
        spec["review_required"] = True
        spec["validation_passed"] = True
        spec["executable"] = False
        package_id = new_uuid7().replace("-", "")
        resource = self.workshop.write_overlay(payload, package_id=package_id)
        return {
            "schema_version": "1.0",
            "previous": current,
            "draft": resource,
            "snapshot_hash": snapshot_identity(resource),
        }


def skill_instruction_for(capability: str) -> str:
    title = _display_name(capability)
    return (
        "Purpose\n"
        f"Provide a reusable {title} procedure the Agent can follow in context.\n\n"
        "When to use\n"
        f"Use this skill when the Agent must satisfy the `{capability}` capability "
        "and no additional Tool is required.\n\n"
        "Procedure\n"
        "1. Restate the criteria implied by the capability name.\n"
        "2. Use only facts already in context or returned by permitted tools.\n"
        "3. Produce the expected output structure.\n"
        "4. Stop if required inputs are missing instead of inventing tools.\n\n"
        "Expected output\n"
        f"A structured result that satisfies `{capability}` without claiming "
        "unavailable tools or permissions.\n\n"
        "Constraints\n"
        "Do not request extra privileges.\n"
        "Do not skip required user confirmation.\n"
        "Do not call tools that are not bound to this Agent.\n"
        "Do not change platform safety rules.\n\n"
        "Failure handling\n"
        "If the capability cannot be completed with available context, state the "
        "gap clearly and stop."
    )


def _skill_payload(
    *,
    resource_id: str,
    name: str,
    description: str,
    instruction: str,
    capabilities: list[str],
    availability: str,
    selectable: bool,
    runtime_status: str,
    version: str,
) -> dict[str, Any]:
    return {
        "resource_id": resource_id,
        "kind": "skill",
        "name": name[:120],
        "description": description[:4_000],
        "availability": availability,
        "factory_selectable": selectable,
        "runtime_status": runtime_status,
        "required_permissions": dict(_EMPTY_PERMISSIONS),
        "tags": ["workshop", "factory", "quarantined"],
        "capabilities": capabilities,
        "loop_compatible": True,
        "spec": {
            "executable": False,
            "origin": "factory",
            "validation_passed": True,
            "review_required": True,
            "instruction": instruction,
            "ui": {
                "category": "workshop",
                "icon": "sparkles",
                "title": name[:80],
            },
        },
        "version": version,
    }


def _wrapper_payload(
    *,
    resource_id: str,
    capability: str,
    spec: dict[str, Any],
    availability: str,
    selectable: bool,
    runtime_status: str,
    version: str,
) -> dict[str, Any]:
    adapter = str(spec.get("adapter") or "")
    hosts = list(spec.get("allowed_hosts") or [])
    permissions = {
        **_EMPTY_PERMISSIONS,
        "tools": [resource_id],
        "network_hosts": hosts if adapter == SAFE_HTTP_ADAPTER else [],
        "filesystem_read_roots": ["project"] if adapter in SAFE_FS_ADAPTERS else [],
    }
    name = _display_name(capability)
    tool_spec = {
        **spec,
        "executable": False,
        "origin": "factory",
        "wrapper_kind": "tool_wrapper",
        "validation_passed": True,
        "review_required": True,
        "tool_name": capability.replace("_", "."),
        "ui": {
            "category": "workshop",
            "icon": "globe" if adapter == SAFE_HTTP_ADAPTER else "file-text",
            "title": name[:80],
        },
    }
    return {
        "resource_id": resource_id,
        "kind": "tool",
        "name": name[:120],
        "description": (
            f"Declarative wrapper for `{capability}` on {adapter}. "
            "Not an arbitrary executor."
        )[:4_000],
        "availability": availability,
        "factory_selectable": selectable,
        "runtime_status": runtime_status,
        "required_permissions": permissions,
        "tags": ["workshop", "factory", "quarantined", "tool_wrapper"],
        "capabilities": [capability],
        "loop_compatible": True,
        "spec": tool_spec,
        "version": version,
    }


def _wrapper_spec(capability: str, wrapper: Mapping[str, Any]) -> dict[str, Any]:
    adapter = wrapper_adapter(wrapper)
    spec: dict[str, Any] = {
        "adapter": adapter,
        "base_adapter": adapter,
        "base_tool": str(wrapper.get("base_tool") or _base_tool(adapter)),
        "approval_required": adapter == SAFE_HTTP_ADAPTER,
        "input_schema": dict(wrapper.get("input_schema") or {}),
        "output_schema": dict(
            wrapper.get("output_schema") or {"body": "string", "status": "integer"}
        ),
        "timeout_ms": int(wrapper.get("timeout_ms") or 5_000),
        "max_response_bytes": int(wrapper.get("max_response_bytes") or 65_536),
    }
    if adapter == SAFE_HTTP_ADAPTER:
        spec["allowed_hosts"] = [
            str(item).strip().lower()
            for item in (wrapper.get("allowed_hosts") or [])
            if str(item).strip()
        ]
        spec["methods"] = [
            str(item).upper()
            for item in (wrapper.get("methods") or ["GET"])
            if str(item).strip()
        ]
        spec["path_prefix"] = str(wrapper.get("path_prefix") or "").strip()
        spec["scheme"] = str(wrapper.get("scheme") or "http").strip().lower()
        if wrapper.get("port") is not None:
            spec["port"] = int(wrapper["port"])
        if not spec["output_schema"]:
            spec["output_schema"] = {"body": "string", "status": "integer"}
    else:
        spec["path_prefix"] = str(wrapper.get("path_prefix") or "").strip()
        spec["approval_required"] = False
        if not spec["input_schema"]:
            spec["input_schema"] = {"path": "string"}
            if adapter.endswith("search"):
                spec["input_schema"]["query"] = "string"
        if not spec.get("output_schema"):
            spec["output_schema"] = (
                {"matches": "array"}
                if adapter.endswith("search")
                else {"content": "string"}
            )
    del capability
    return spec


def _base_tool(adapter: str) -> str:
    mapping = {
        SAFE_HTTP_ADAPTER: "veyra.tool.http.request@1.0.0",
        "veyra.runtime.filesystem.read": "veyra.tool.filesystem.read@1.0.0",
        "veyra.runtime.filesystem.search": "veyra.tool.filesystem.search@1.0.0",
        "veyra.runtime.filesystem.list": "veyra.tool.filesystem.list@1.0.0",
    }
    return mapping.get(adapter, adapter)


def _new_resource_id(kind: str, capability: str) -> tuple[str, str]:
    draft_id = new_uuid7()
    package_id = draft_id.replace("-", "")
    slug = capability.replace("_", "-")
    suffix = package_id[-12:]
    kind_slug = "skill" if kind == "skill" else "tool"
    return f"veyra.workshop.{kind_slug}.{slug}-{suffix}", package_id


def _display_name(capability: str) -> str:
    return capability.replace("_", " ").title()


def _next_version(catalog: ResourceCatalog, resource_id: str, current: str) -> str:
    major, minor, patch = current.split(".")
    candidate = f"{major}.{minor}.{int(patch) + 1}"
    known = {
        item["version"]
        for item in catalog.resources()["resources"]
        if item.get("resource_id") == resource_id
    }
    while candidate in known:
        major, minor, patch = candidate.split(".")
        candidate = f"{major}.{minor}.{int(patch) + 1}"
    return candidate


def _requirement_for(plan: ResourcePlan, capability: str) -> CapabilityRequirement:
    for item in plan.requirements:
        if item.capability == capability:
            return item
    return CapabilityRequirement(capability=capability, required=True)


def translate_factory_error(exc: Exception) -> ResourceFactoryError:
    if isinstance(exc, ResourceFactoryError):
        return exc
    if isinstance(exc, ResourceFactoryValidationError):
        return ResourceFactoryError(exc.code, str(exc))
    if isinstance(exc, ResourceWorkshopError):
        return ResourceFactoryError(exc.code, str(exc))
    return ResourceFactoryError("factory_generation_invalid", str(exc))


def factory_plan_digest(plans: Sequence[ResourceFactoryPlan]) -> str:
    return sha256_digest([item.to_dict() for item in plans])
