"""Non-mutating checks for the dependencies an Agent will use at Runtime.

The Project Resource Library answers which resources are selected.  This module
answers the more useful Studio question: does the current Agent source still
point at an available, hash-matched resource that the local Runtime knows how
to consume?  It deliberately performs no provider calls and never changes a
Project or the Resource Catalog.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.resource import ResourceRef
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService
from veyra_agent_platform.local.resources import ResourceCatalog, ResourceCatalogError

from .knowledge_context import MAX_CONTEXT_BYTES, MAX_DOCUMENTS

DependencyStatus = Literal[
    "ready",
    "missing",
    "lock_missing",
    "lock_mismatch",
    "kind_mismatch",
    "configuration_required",
    "runtime_unavailable",
    "review_required",
    "permission_denied",
    "secret_declaration_missing",
    "context_not_declared",
    "context_too_large",
]

_CATALOG_KINDS = {"component", "tool", "mcp_tool", "skill", "policy", "template"}


def inspect_agent_dependencies(
    projects: ProjectService,
    catalog: ResourceCatalog,
    project_id: str,
    source: AgentSource,
) -> dict[str, Any]:
    """Return stable, bounded dependency evidence for one Agent source.

    ``runtime_ready`` is intentionally scoped to dependency resolution.  The
    model API credential and any host secret are checked by the Runtime at the
    moment of execution, so a true value here must not be presented as a
    provider health check.
    """

    usages: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    def add(
        reference: str,
        expected_kind: str,
        *,
        node_id: str | None = None,
        binding_id: str | None = None,
    ) -> None:
        if not reference:
            return
        if reference not in usages:
            usages[reference] = {
                "expected_kinds": set(),
                "node_ids": [],
                "binding_ids": [],
            }
            order.append(reference)
        usage = usages[reference]
        usage["expected_kinds"].add(expected_kind)
        if node_id is not None and node_id not in usage["node_ids"]:
            usage["node_ids"].append(node_id)
        if binding_id is not None and binding_id not in usage["binding_ids"]:
            usage["binding_ids"].append(binding_id)

    for node in source.nodes:
        if node.uses:
            add(node.uses, "tool", node_id=node.id)
    for reference in source.skill_refs:
        add(reference, "skill")
    for reference in source.policy_refs:
        add(reference, "policy")
    for reference in source.knowledge_refs:
        add(reference, "knowledge")

    bindings = source.ui.get("bindings") or {}
    if isinstance(bindings, Mapping):
        for binding_id, binding in bindings.items():
            if not isinstance(binding_id, str) or not isinstance(binding, Mapping):
                continue
            binding_reference = binding.get("reference")
            binding_kind = binding.get("kind")
            if isinstance(binding_reference, str) and isinstance(binding_kind, str):
                add(binding_reference, binding_kind, binding_id=binding_id)

    checks = []
    for reference in order:
        usage = usages[reference]
        expected_kinds = set(usage["expected_kinds"])
        if "knowledge" in expected_kinds:
            checks.append(
                _knowledge_check(
                    projects,
                    project_id,
                    source,
                    reference,
                    usage["node_ids"],
                    usage["binding_ids"],
                )
            )
        else:
            checks.append(
                _catalog_check(
                    catalog,
                    source,
                    reference,
                    expected_kinds,
                    usage["node_ids"],
                    usage["binding_ids"],
                )
            )

    ready = sum(item["status"] == "ready" for item in checks)
    attention = len(checks) - ready
    return {
        "dependencies": checks,
        "dependency_summary": {
            "total": len(checks),
            "ready": ready,
            "attention": attention,
        },
        "runtime_ready": attention == 0,
        "runtime_ready_scope": "agent_dependencies",
    }


def _catalog_check(
    catalog: ResourceCatalog,
    source: AgentSource,
    reference: str,
    expected_kinds: set[str],
    node_ids: list[str],
    binding_ids: list[str],
) -> dict[str, Any]:
    expected_kind = _display_kind(expected_kinds)
    result: dict[str, Any] = {
        "reference": reference,
        "kind": expected_kind,
        "name": reference,
        "status": "missing",
        "detail": "Resource version is not registered in the local catalog.",
        "used_by": node_ids,
        "bound_by": binding_ids,
    }
    locked_hash = source.lock.get(reference)
    if locked_hash is not None:
        result["locked_hash"] = locked_hash
    else:
        result["status"] = "lock_missing"
        result["detail"] = "Agent source does not lock this dependency."

    try:
        resource = catalog.by_reference(reference)
    except ResourceCatalogError:
        return result

    actual_kind = str(resource["kind"])
    result.update(
        {
            "kind": actual_kind,
            "name": str(resource["name"]),
            "version": str(resource["version"]),
            "content_hash": str(resource["content_hash"]),
            "availability": str(resource["availability"]),
            "runtime_status": str(resource["runtime_status"]),
            "required_permissions": resource["required_permissions"],
        }
    )

    allowed_kinds = _allowed_kinds(expected_kinds)
    if actual_kind not in allowed_kinds:
        result["status"] = "kind_mismatch"
        result["detail"] = "Catalog resource kind does not match this Agent usage."
        return result
    if locked_hash is None:
        return result
    if locked_hash != resource["content_hash"]:
        result["status"] = "lock_mismatch"
        result["detail"] = "Agent lock does not match the current catalog content hash."
        return result

    availability = resource["availability"]
    if availability != "ready":
        result["status"] = (
            "configuration_required"
            if availability == "requires_configuration"
            else "runtime_unavailable"
        )
        result["detail"] = (
            "Resource requires host configuration before it can run."
            if availability == "requires_configuration"
            else "Resource is not available for local execution."
        )
        return result

    spec = resource.get("spec")
    if not isinstance(spec, Mapping):
        spec = {}
    if resource.get("origin") == "discovered" and (
        resource.get("factory_selectable") is not True
        or spec.get("review_required") is True
    ):
        result["status"] = "review_required"
        result["detail"] = "Discovered MCP tools must be reviewed before execution."
        return result

    permission_detail = _permission_detail(source, resource["required_permissions"])
    if permission_detail is not None:
        result["status"] = "permission_denied"
        result["detail"] = permission_detail
        return result

    secret_ref = spec.get("secret_ref")
    if isinstance(secret_ref, str) and secret_ref not in source.secret_refs:
        result["status"] = "secret_declaration_missing"
        result["detail"] = "Agent source does not declare the Tool secret reference."
        return result

    runtime_status = resource["runtime_status"]
    if runtime_status != "supported":
        mode, detail = _non_executable_mode(actual_kind)
        if mode is None:
            result["status"] = "runtime_unavailable"
            result["detail"] = "Resource has no supported local Runtime adapter."
            return result
        result["runtime_mode"] = mode
        result["status"] = "ready"
        result["detail"] = detail
        return result

    result["runtime_mode"] = (
        "tool_adapter" if actual_kind in {"tool", "mcp_tool"} else "catalog"
    )
    result["status"] = "ready"
    result["detail"] = "Locked catalog resource is available to the local Runtime."
    return result


def _knowledge_check(
    projects: ProjectService,
    project_id: str,
    source: AgentSource,
    reference: str,
    node_ids: list[str],
    binding_ids: list[str],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "reference": reference,
        "kind": "knowledge",
        "name": reference,
        "status": "missing",
        "detail": "Knowledge document is not available in this Project.",
        "availability": "ready",
        "runtime_status": "supported",
        "runtime_mode": "knowledge_context",
        "used_by": node_ids,
        "bound_by": binding_ids,
    }
    locked_hash = source.lock.get(reference)
    if locked_hash is not None:
        result["locked_hash"] = locked_hash

    if reference not in source.knowledge_refs:
        result["status"] = "context_not_declared"
        result["detail"] = (
            "Knowledge is shown in the Studio binding but is not declared in "
            "extensions.veyra.knowledge_refs."
        )
        return result
    if len(source.knowledge_refs) > MAX_DOCUMENTS:
        result["status"] = "context_too_large"
        result["detail"] = "Agent context supports at most eight Knowledge documents."
        return result

    try:
        ref = ResourceRef.from_string(reference)
        document = projects.knowledge_summary(project_id, ref.resource_id)
    except (ProjectError, ValueError) as exc:
        result["detail"] = str(exc)
        return result

    actual_hash = document.get("source_file_hash")
    result.update(
        {
            "name": str(document["name"]),
            "version": str(document["version"]),
            "content_hash": str(actual_hash),
            "byte_length": len(str(document["text"]).encode("utf-8")),
        }
    )
    if document["version"] != ref.version or locked_hash != actual_hash:
        result["status"] = "lock_mismatch"
        result["detail"] = (
            "Knowledge version or content hash changed after the Agent was bound."
        )
        return result

    result["status"] = "ready"
    result["detail"] = "Project Knowledge is version- and content-hash verified."
    return result


def _display_kind(expected_kinds: set[str]) -> str:
    if "tool" in expected_kinds or "mcp_tool" in expected_kinds:
        return "tool"
    return sorted(expected_kinds)[0] if expected_kinds else "resource"


def _allowed_kinds(expected_kinds: set[str]) -> set[str]:
    if expected_kinds & {"tool", "mcp_tool"}:
        return {"tool", "mcp_tool"}
    return expected_kinds & _CATALOG_KINDS


def _permission_detail(source: AgentSource, required: Any) -> str | None:
    if not isinstance(required, Mapping):
        return "Catalog resource permissions are invalid."
    checks = (
        ("tools", source.permissions.tools, "Tool"),
        ("network_hosts", source.permissions.network_hosts, "network"),
        (
            "filesystem_read_roots",
            source.permissions.filesystem_read_roots,
            "file read",
        ),
        (
            "filesystem_write_roots",
            source.permissions.filesystem_write_roots,
            "file write",
        ),
    )
    for field, granted, label in checks:
        missing = sorted(set(required.get(field, [])) - set(granted))
        if missing:
            return (
                f"Agent permissions do not include required {label}: "
                f"{', '.join(missing)}."
            )
    if (
        required.get("shell_workspace_only", False)
        and not source.permissions.shell_workspace_only
    ):
        return "Agent permissions do not include the required workspace shell scope."
    return None


def _non_executable_mode(kind: str) -> tuple[str, str] | tuple[None, None]:
    if kind == "skill":
        return (
            "model_context",
            "Skill instruction will be added to the model prompt during an Agent run.",
        )
    if kind == "policy":
        return (
            "source_policy",
            "Policy is retained as source-level runtime guidance; "
            "it has no standalone adapter.",
        )
    if kind == "template":
        return (
            "design_only",
            "Template is design metadata and is not executed by the Runtime.",
        )
    return None, None


def dependency_context_limits() -> dict[str, int]:
    """Expose the same bounded Knowledge context limits used by Runtime."""

    return {
        "max_documents": MAX_DOCUMENTS,
        "max_bytes": MAX_CONTEXT_BYTES,
    }
