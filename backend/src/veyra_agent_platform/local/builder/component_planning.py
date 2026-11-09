"""Resolve reusable semantic duties and derive safe Custom Component plans."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from veyra_agent_platform.contracts.semantic_plan import (
    AgentSemanticPlanV1,
    OperationKind,
    SemanticField,
    SemanticStepIntent,
)

_ARTIFACT_TYPES = {"image", "pdf", "document", "file", "audio", "video", "table"}
_WORD = re.compile(r"[^a-z0-9]+")
_TEMPLATE = re.compile(r"^\s*([a-z][a-z0-9_-]{0,62})\s*:\s*(.+?)\s*$")
_PLACEHOLDER = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")


@dataclass(frozen=True)
class ReusableCapabilityResolution:
    plan: AgentSemanticPlanV1
    missing: tuple[dict[str, Any], ...]
    clarification: str | None = None


def resolve_reusable_capabilities(
    plan: AgentSemanticPlanV1,
    project_resources: list[dict[str, Any]],
) -> ReusableCapabilityResolution:
    """Reuse a unique ready Project capability or return one safe proposal plan."""

    updated: list[SemanticStepIntent] = []
    missing: list[dict[str, Any]] = []
    for step in plan.step_intents:
        if not step.reusable_capability:
            updated.append(step)
            continue

        requirement = step.capability_requirement
        matches = _matching_project_capabilities(project_resources, requirement)
        if len(matches) > 1:
            names = ", ".join(str(item.get("name") or "Component") for item in matches)
            return ReusableCapabilityResolution(
                plan=replace(
                    plan,
                    step_intents=tuple(
                        updated + list(plan.step_intents[len(updated) :])
                    ),
                ),
                missing=tuple(missing),
                clarification=(
                    f"当前 Project 中有多个匹配能力：{names}。"
                    "请指定要复用的 Component。"
                ),
            )
        if matches:
            resource = matches[0]
            readiness = _readiness(resource)
            if readiness == "ready":
                updated.append(
                    replace(
                        step,
                        operation_kind="capability",
                        capability_requirement=str(resource["reference"]),
                        dependency_requirement="",
                        reusable_capability=False,
                        inputs=(),
                        outputs=(),
                    )
                )
            else:
                missing.append(
                    _blocked(
                        requirement,
                        readiness,
                        "Existing matching capability is not ready; configure it "
                        "instead of creating a duplicate.",
                        name=str(resource.get("name") or requirement),
                    )
                )
                updated.append(step)
            continue

        draft_plan, reason = reusable_draft_plan(step, project_resources)
        if draft_plan is not None:
            missing.append(
                {
                    "kind": "custom_component",
                    "reference": requirement,
                    "reason": (
                        "A reusable capability can be created after explicit "
                        "confirmation."
                    ),
                    "resolution_status": "proposal_available",
                    "readiness": draft_plan["readiness_expectation"],
                    "component_plan": draft_plan,
                }
            )
        else:
            missing.append(
                _blocked(
                    requirement,
                    "unavailable",
                    reason or "No safe Custom Component implementation is available.",
                )
            )
        updated.append(step)
    return ReusableCapabilityResolution(
        plan=replace(plan, step_intents=tuple(updated)), missing=tuple(missing)
    )


def reusable_draft_plan(
    step: SemanticStepIntent,
    project_resources: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    """Build a server-owned draft plan; never accepts implementation/permission IDs."""

    inputs = list(step.inputs)
    outputs = list(step.outputs)
    if not inputs or not outputs:
        return None, "Reusable capability needs explicit typed inputs and outputs."
    if any(item.type in _ARTIFACT_TYPES for item in (*inputs, *outputs)):
        artifact = next(
            item.type for item in (*inputs, *outputs) if item.type in _ARTIFACT_TYPES
        )
        return None, _unsupported_modality_reason(artifact)

    dependencies: list[dict[str, str]] = []
    permissions = _empty_permissions()
    implementation: dict[str, Any]
    if step.operation_kind == "model":
        if any(item.type not in {"string", "object"} for item in (*inputs, *outputs)):
            return None, "model_recipe is limited to text and object semantic I/O."
        implementation = {
            "kind": "model_recipe",
            "instruction": _model_recipe_instruction(step.purpose, outputs),
            "model_ref": "model.primary",
        }
        readiness = "runtime_dependent"
    elif step.operation_kind == "transform":
        if any(item.type != "string" for item in (*inputs, *outputs)):
            return (
                None,
                "The current Transform runtime only supports bounded string "
                "templates for reusable components.",
            )
        mapping = _transform_mapping(step.purpose, inputs, outputs)
        if mapping is None:
            return (
                None,
                "This Transform cannot be expressed by the current bounded "
                "field-mapping grammar.",
            )
        implementation = {"kind": "transform", "mapping": mapping}
        readiness = "ready"
    elif step.operation_kind == "capability":
        if not step.dependency_requirement:
            return (
                None,
                "A missing external capability cannot be created here; a "
                "tool_wrapper requires a named Project-bound Tool.",
            )
        tools = _matching_project_tools(project_resources, step.dependency_requirement)
        if len(tools) != 1:
            if len(tools) > 1:
                return (
                    None,
                    "Multiple Project-bound Tools match the wrapper dependency; "
                    "choose one exact Tool.",
                )
            return (
                None,
                "tool_wrapper requires an exact Tool already bound to this Project.",
            )
        tool = tools[0]
        if _readiness(tool) != "ready":
            return None, "The selected Project-bound Tool is not ready for a wrapper."
        reference = str(tool["reference"])
        digest = str(tool.get("bound_content_hash") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            return None, "The selected Tool does not have a current exact Project pin."
        dependencies = [{"reference": reference, "content_hash": digest}]
        required = tool.get("required_permissions")
        if isinstance(required, dict):
            permissions = required
        implementation = {
            "kind": "tool_wrapper",
            "tool_reference": reference,
        }
        readiness = "ready"
    else:
        return (
            None,
            "Core primitives already handle this operation; no Custom "
            "Component is needed.",
        )

    requirement = step.capability_requirement.strip()
    display_name = requirement or step.name.strip()
    if not display_name:
        return None, "A reusable capability needs a clear semantic name."
    return (
        {
            "display_name": display_name[:80],
            "description": step.purpose.strip()[:2000],
            "capability_requirement": requirement[:240],
            "agent_step": step.name[:80],
            "agent_step_key": step.semantic_key[:64],
            "inputs": _typed_fields(inputs),
            "outputs": _typed_fields(outputs),
            "implementation": implementation,
            "dependencies": dependencies,
            "required_permissions": permissions,
            "readiness_expectation": readiness,
            "why": step.purpose.strip()[:500],
        },
        None,
    )


def direct_component_draft_plan(
    *,
    capability_requirement: str,
    purpose: str,
    operation_kind: OperationKind,
    inputs: list[SemanticField],
    outputs: list[SemanticField],
    dependency_requirement: str,
    project_resources: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    step = SemanticStepIntent(
        semantic_key="reusable_component",
        name=capability_requirement,
        purpose=purpose,
        operation_kind=operation_kind,
        depends_on=(),
        capability_requirement=capability_requirement,
        dependency_requirement=dependency_requirement,
        reusable_capability=True,
        inputs=tuple(inputs),
        outputs=tuple(outputs),
    )
    return reusable_draft_plan(step, project_resources)


def matching_existing_component(
    project_resources: list[dict[str, Any]], requirement: str
) -> tuple[dict[str, Any], ...]:
    return tuple(_matching_project_components(project_resources, requirement))


def matching_project_capabilities(
    project_resources: list[dict[str, Any]], requirement: str
) -> tuple[dict[str, Any], ...]:
    return tuple(_matching_project_capabilities(project_resources, requirement))


def capability_readiness(resource: dict[str, Any]) -> str:
    return _readiness(resource)


def _matching_project_capabilities(
    resources: list[dict[str, Any]], requirement: str
) -> list[dict[str, Any]]:
    matches = [
        item
        for item in resources
        if item.get("scope") == "project"
        and (
            item.get("kind") in {"tool", "mcp_tool"}
            or (
                item.get("kind") == "component"
                and item.get("component_class") == "composite"
            )
        )
        and item.get("factory_selectable") is not False
        and _matches(item, _normalize(requirement))
    ]
    custom = [item for item in matches if item.get("component_class") == "composite"]
    tools = [item for item in matches if item not in custom]
    selected = _latest_per_component(custom) + _unique_references(tools)
    return selected


def _matching_project_components(
    resources: list[dict[str, Any]], requirement: str
) -> list[dict[str, Any]]:
    query = _normalize(requirement)
    if not query:
        return []
    components = [
        item
        for item in resources
        if item.get("scope") == "project"
        and item.get("kind") == "component"
        and item.get("component_class") == "composite"
        and item.get("factory_selectable") is not False
    ]
    matching = [item for item in components if _matches(item, query)]
    return _latest_per_component(matching)


def _latest_per_component(
    matching: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    # Multiple published versions of the same Component are one capability.
    by_id: dict[str, list[dict[str, Any]]] = {}
    for item in matching:
        by_id.setdefault(
            str(item.get("resource_id") or item.get("reference")), []
        ).append(item)
    selected: list[dict[str, Any]] = []
    for versions in by_id.values():
        selected.append(
            max(versions, key=lambda item: _version_key(item.get("version")))
        )
    return selected


def _matching_project_tools(
    resources: list[dict[str, Any]], requirement: str
) -> list[dict[str, Any]]:
    query = _normalize(requirement)
    matches = [
        item
        for item in resources
        if item.get("scope") == "project"
        and item.get("kind") in {"tool", "mcp_tool"}
        and item.get("binding_status") != "stale"
        and _matches(item, query)
    ]
    return _unique_references(matches)


def _matches(item: dict[str, Any], query: str) -> bool:
    keys = [
        _normalize(item.get(key))
        for key in ("name", "slug", "resource_id", "reference")
    ]
    keys.extend(
        _normalize(value)
        for key in ("reference",)
        for value in [str(item.get(key) or "").split("@", 1)[0]]
    )
    if query in keys:
        return True
    if any(len(query) >= 4 and (query in key or key in query) for key in keys if key):
        return True
    query_words = set(query.split())
    if len(query_words) >= 2:
        return any(
            len(query_words & set(key.split())) / len(query_words) >= 0.75
            for key in keys
            if key
        )
    return False


def _readiness(resource: dict[str, Any]) -> str:
    if resource.get("binding_status") == "stale":
        return "unavailable"
    availability = str(resource.get("availability") or "unavailable")
    runtime = str(resource.get("runtime_status") or "runtime_not_supported")
    if availability == "requires_configuration" or runtime == "runtime_not_configured":
        return "requires_configuration"
    if availability == "design_only":
        return "design_only"
    if availability == "ready" and runtime == "supported":
        return "ready"
    return "unavailable"


def _typed_fields(fields: list[SemanticField]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in fields:
        descriptor: dict[str, Any] = {
            "type": field.type,
            "required": True,
        }
        if field.description:
            descriptor["description"] = field.description
        if field.multiple:
            descriptor["multiple"] = True
        result[field.name] = descriptor
    return result


def _model_recipe_instruction(purpose: str, outputs: list[SemanticField]) -> str:
    fields = ", ".join(item.name for item in outputs)
    return (
        purpose.strip()
        + "\n\nUse only the provided inputs. Return a JSON object containing "
        + f"the declared output fields: {fields}. Do not claim external tools, "
        "file access, image understanding, or unsupported capabilities."
    )


def _transform_mapping(
    purpose: str, inputs: list[SemanticField], outputs: list[SemanticField]
) -> dict[str, str] | None:
    match = _TEMPLATE.fullmatch(purpose)
    if match:
        output, template = match.groups()
        allowed = {item.name for item in inputs}
        variables = _PLACEHOLDER.findall(template)
        if output not in {item.name for item in outputs} or not variables:
            return None
        if any(variable not in allowed for variable in variables):
            return None
        return {output: template}
    if len(inputs) == 1 and len(outputs) == 1:
        return {outputs[0].name: f"{{{{{inputs[0].name}}}}}"}
    if all(output.name in {item.name for item in inputs} for output in outputs):
        return {output.name: f"{{{{{output.name}}}}}" for output in outputs}
    return None


def _empty_permissions() -> dict[str, Any]:
    return {
        "network_hosts": [],
        "tools": [],
        "filesystem_read_roots": [],
        "filesystem_write_roots": [],
        "shell_workspace_only": False,
    }


def _blocked(
    requirement: str,
    readiness: str,
    reason: str,
    *,
    name: str | None = None,
) -> dict[str, Any]:
    return {
        "kind": "custom_component",
        "reference": requirement,
        "reason": reason,
        "resolution_status": readiness,
        "readiness": readiness,
        **({"name": name} if name else {}),
    }


def _unsupported_modality_reason(kind: str) -> str:
    messages = {
        "image": (
            "The current Runtime model does not support image input; no "
            "text-only Vision Component will be proposed."
        ),
        "pdf": (
            "No PDF parser or renderer is available; a model_recipe cannot "
            "substitute for PDF processing."
        ),
        "audio": (
            "Audio Runtime adapters are not enabled; no Custom Component can "
            "provide this modality."
        ),
        "video": (
            "Video Runtime adapters are not enabled; no Custom Component can "
            "provide this modality."
        ),
        "file": (
            "File processing requires a real Project-bound capability; a "
            "text model_recipe cannot substitute for it."
        ),
        "document": (
            "Document parsing requires a real Project-bound capability; a "
            "text model_recipe cannot substitute for it."
        ),
        "table": (
            "The current component proposal path does not safely implement table I/O."
        ),
    }
    return messages.get(
        kind,
        f"The current Runtime does not support {kind} I/O for a reusable component.",
    )


def _normalize(value: object) -> str:
    raw = str(value or "").casefold()
    normalized = _WORD.sub(" ", raw)
    cjk = "".join(char for char in raw if "\u3400" <= char <= "\u9fff")
    words = normalized.strip()
    return words if words else cjk


def _version_key(value: object) -> tuple[int, int, int]:
    try:
        parts = [int(item) for item in str(value).split(".")]
        parts.extend([0] * (3 - len(parts)))
        return parts[0], parts[1], parts[2]
    except ValueError:
        return (0, 0, 0)


def _unique_references(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in resources:
        reference = str(item.get("reference") or "")
        if reference and reference not in seen:
            seen.add(reference)
            result.append(item)
    return result
