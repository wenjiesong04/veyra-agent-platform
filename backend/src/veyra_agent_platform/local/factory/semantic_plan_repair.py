"""Bounded SemanticPlan V2 sanitization before strict contract validation.

The model describes duties. This module may drop unused provider fields, fill
missing keys from adjacent fields, and remap a closed alias list. It does not
invent graph topology, map Chinese keywords onto nodes, or bypass validation.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from veyra_agent_platform.contracts.common import ContractValidationError

_SLUG = re.compile(r"[^a-z0-9]+")
_OPERATION_KINDS = {
    "model",
    "capability",
    "transform",
    "condition",
    "approval",
    "verification",
}
_COMPLEX_KINDS = frozenset(
    {"transform", "condition", "approval", "verification", "capability"}
)
_KIND_ALIASES = {
    "human_approval": "approval",
    "humanapproval": "approval",
    "verify": "verification",
    "verifier": "verification",
    "tool": "capability",
}
_STEP_FIELDS = {
    "semantic_key",
    "name",
    "purpose",
    "operation_kind",
    "depends_on",
    "capability_requirement",
    "dependency_requirement",
    "reusable_capability",
    "inputs",
    "outputs",
    "branches",
    "condition_expression",
    "branch_condition",
    "branch_key",
    "output_mapping",
}
_SHAPE_KEYS = (
    "schema_version",
    "goal",
    "suggested_name",
    "description",
    "inputs",
    "outputs",
    "steps",
    "capability_intents",
    "knowledge_intents",
    "approval_points",
    "success_criteria",
    "user_constraints",
    "step_intents",
    "branches",
    "nodes",
)


def bounded_repair_semantic_plan(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Return a shallow-repaired plan and safe repair notes."""

    repaired = dict(payload)
    notes: list[str] = []
    raw_steps = repaired.get("step_intents")
    if raw_steps is None:
        return repaired, ()
    if not isinstance(raw_steps, list):
        return repaired, ()
    known_keys = _known_semantic_keys(raw_steps)
    steps: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_steps):
        if not isinstance(item, Mapping):
            notes.append(f"dropped_malformed_step:{index}")
            continue
        step = {key: value for key, value in item.items() if key in _STEP_FIELDS}
        kind = _normalized_kind(step.get("operation_kind"))
        if kind is not None and kind != step.get("operation_kind"):
            notes.append(f"aliased_operation_kind:{index}")
            step["operation_kind"] = kind
        if "branches" in step and kind != "condition":
            step.pop("branches", None)
            notes.append(f"dropped_invalid_branches:{index}")
        if (
            step.get("capability_requirement")
            and step.get("operation_kind") != "capability"
            and step.get("reusable_capability") is not True
        ):
            step.pop("capability_requirement", None)
            notes.append(f"dropped_capability_requirement:{index}")
        key = step.get("semantic_key")
        if not _non_empty_string(key):
            generated = _key_from_name(step.get("name"), index, seen)
            if generated:
                step["semantic_key"] = generated
                notes.append(f"filled_semantic_key:{index}")
                key = generated
        if _non_empty_string(key):
            seen.add(str(key).casefold())
        if "branches" in step and not isinstance(step["branches"], list):
            step.pop("branches", None)
            notes.append(f"dropped_malformed_branches:{index}")
        if "output_mapping" in step and not isinstance(step["output_mapping"], Mapping):
            step.pop("output_mapping", None)
            notes.append(f"dropped_malformed_output_mapping:{index}")
        depends = step.get("depends_on")
        if isinstance(depends, list):
            remapped, dropped = _remap_depends_on(depends, known_keys)
            if remapped != [str(item) for item in depends if isinstance(item, str)]:
                notes.append(f"repaired_depends_on:{index}")
            if dropped:
                notes.append(f"dropped_unknown_dependency:{index}")
            if remapped:
                step["depends_on"] = remapped
            else:
                step.pop("depends_on", None)
        steps.append(step)
    repaired["step_intents"] = steps
    _sanitize_declared_names(repaired, notes)
    _align_condition_fields(repaired, notes)
    _keep_single_branch(repaired["step_intents"], notes)
    return repaired, tuple(notes)


def graph_obligations(payload: Mapping[str, Any]) -> frozenset[str]:
    """Complex duties observed in a provider payload, without user text."""

    kinds: set[str] = set()
    raw_steps = payload.get("step_intents")
    input_names = _declared_field_names(payload.get("inputs"))
    output_names = _declared_field_names(payload.get("outputs"))
    model_count = 0
    if isinstance(raw_steps, list):
        for item in raw_steps:
            if not isinstance(item, Mapping):
                continue
            kind = _normalized_kind(item.get("operation_kind"))
            if kind in _COMPLEX_KINDS - {"transform"}:
                kinds.add(kind)
            if kind == "transform" and _transform_is_representable(
                item, input_names=input_names, output_names=output_names
            ):
                kinds.add("transform")
            if item.get("reusable_capability") is True:
                kinds.add("reusable_capability")
            if kind == "condition" and item.get("branches"):
                kinds.add("branch")
            if kind == "model":
                model_count += 1
        if model_count >= 2:
            kinds.add("multi_model")
    points = payload.get("approval_points")
    if isinstance(points, list) and any(_non_empty_string(item) for item in points):
        kinds.add("approval")
    return frozenset(kinds)


_NAME_NOISE = (
    "source.lock",
    "knowledge_refs",
    "resource hash",
    "canvas",
    "etag",
    "revision",
)


def _sanitize_declared_names(plan: dict[str, Any], notes: list[str]) -> None:
    """Rename fields that contain internal tokens, then retarget conditions."""

    rename: dict[str, str] = {}
    for field in ("inputs", "outputs"):
        items = plan.get(field)
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            name = item["name"]
            lowered = name.casefold()
            if not any(token in lowered for token in _NAME_NOISE):
                continue
            safe = f"field-{index + 1}"
            item["name"] = safe
            rename[name.casefold()] = safe
            notes.append(f"renamed_internal_field:{field}")
    if not rename:
        return
    steps = plan.get("step_intents")
    if not isinstance(steps, list):
        return
    for step in steps:
        if not isinstance(step, dict):
            continue
        expression = step.get("condition_expression")
        if isinstance(expression, str) and expression.strip():
            parts = expression.split()
            mapped = rename.get(parts[0].casefold())
            if mapped:
                parts[0] = mapped
                step["condition_expression"] = " ".join(parts)


def _align_condition_fields(plan: dict[str, Any], notes: list[str]) -> None:
    names = [
        str(item["name"])
        for item in plan.get("inputs") or []
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    ]
    steps = plan.get("step_intents")
    if not isinstance(steps, list) or not names:
        return
    for step in steps:
        if not isinstance(step, dict):
            continue
        expression = step.get("condition_expression")
        if not isinstance(expression, str) or not expression.strip():
            continue
        parts = expression.split()
        matched = _matching_input(parts[0], names)
        if matched and matched != parts[0]:
            parts[0] = matched
            step["condition_expression"] = " ".join(parts)
            notes.append("aligned_condition_field")


def _matching_input(token: str, names: list[str]) -> str | None:
    folded = token.casefold().replace("_", "-").replace(" ", "-")
    for name in names:
        if name.casefold().replace("_", "-").replace(" ", "-") == folded:
            return name
    return None


def _keep_single_branch(steps: list[dict[str, Any]], notes: list[str]) -> None:
    """The graph compiler accepts one branched Condition. Later forks stay linear."""

    branched = [
        step
        for step in steps
        if isinstance(step.get("branches"), list) and step.get("branches")
    ]
    if len(branched) <= 1:
        return
    kept = str(branched[0].get("semantic_key") or "").casefold()
    for step in branched[1:]:
        step.pop("branches", None)
        step.pop("condition_expression", None)
        if step.get("operation_kind") == "condition":
            step["operation_kind"] = "verification"
        notes.append("linearized_extra_branch")
    for step in steps:
        owner = step.get("branch_condition")
        if isinstance(owner, str) and owner.casefold() != kept:
            step.pop("branch_condition", None)
            step.pop("branch_key", None)
            notes.append("detached_extra_branch_step")


def _declared_field_names(value: Any) -> frozenset[str]:
    if not isinstance(value, list):
        return frozenset()
    return frozenset(
        str(item["name"]).casefold()
        for item in value
        if isinstance(item, Mapping) and isinstance(item.get("name"), str)
    )


def _transform_is_representable(
    step: Mapping[str, Any],
    *,
    input_names: frozenset[str],
    output_names: frozenset[str],
) -> bool:
    """Do not turn an invalid inter-step copy into a required repair obligation."""

    if "inputs" in step or "outputs" in step:
        return False
    mapping = step.get("output_mapping")
    if not isinstance(mapping, Mapping):
        # A missing mapping can be repaired while preserving a genuine Transform.
        return True
    if not mapping:
        return False
    for target, template in mapping.items():
        if not isinstance(target, str) or target.casefold() not in output_names:
            return False
        if not isinstance(template, str):
            return False
        for token in re.findall(r"\{\{([^{}]+)\}\}", template):
            if token.casefold() not in input_names:
                return False
    return True


def reject_silent_v1_degradation(
    *,
    obligations: frozenset[str],
    operation_kinds: tuple[str, ...],
    approval_points: tuple[str, ...],
    reusable_capability: bool = False,
    branch_intent: bool = False,
) -> None:
    present = set(operation_kinds)
    if approval_points:
        present.add("approval")
    if sum(1 for kind in operation_kinds if kind == "model") >= 2:
        present.add("multi_model")
    if reusable_capability:
        present.add("reusable_capability")
    if branch_intent:
        present.add("branch")
    missing = sorted(kind for kind in obligations if kind not in present)
    if missing:
        raise ContractValidationError(
            "step_intents omitted complex duties: " + ", ".join(missing)
        )


def classify_plan_error(exc: BaseException) -> str:
    if isinstance(exc, json.JSONDecodeError):
        return "json_parse"
    message = str(exc).casefold()
    if "code=unsupported_step_io" in message or (
        "inputs/outputs are only supported for reusable capability steps" in message
    ):
        return "unsupported_step_io"
    if "code=invalid_reusable_capability" in message or (
        "reusable_capability is only valid for operation_kind=capability" in message
    ):
        return "invalid_reusable_capability"
    if "omitted complex duties" in message:
        return "silent_v1_degradation"
    if "missing field" in message:
        return "missing_field"
    if "unknown field" in message:
        return "unknown_field"
    if "operation_kind is not supported" in message:
        return "invalid_enum"
    if "unknown key" in message:
        return "unknown_dependency"
    if "must be unique" in message:
        return "duplicate_key"
    if "cycle" in message:
        return "cycle"
    if "veyra internals" in message:
        return "forbidden_token"
    return "schema_mismatch"


def semantic_plan_shape(payload: Any) -> dict[str, Any]:
    """Bounded shape for diagnostics. Never includes field values."""

    if not isinstance(payload, Mapping):
        return {"type": type(payload).__name__}
    keys = [key for key in _SHAPE_KEYS if key in payload]
    extras = sorted(
        str(key) for key in payload if key not in _SHAPE_KEYS and isinstance(key, str)
    )
    shape: dict[str, Any] = {
        "keys": keys,
        "extra_key_count": len(extras),
    }
    raw_steps = payload.get("step_intents")
    if isinstance(raw_steps, list):
        kinds: list[str] = []
        branch_count = 0
        missing_key_count = 0
        step_io_fields: list[dict[str, Any]] = []
        for index, item in enumerate(raw_steps):
            if not isinstance(item, Mapping):
                kinds.append("malformed")
                continue
            kind = item.get("operation_kind")
            kinds.append(str(kind) if isinstance(kind, str) else "missing")
            if item.get("branches"):
                branch_count += 1
                kinds.append("branch")
            if item.get("branch_condition") or item.get("branch_key"):
                kinds.append("branch_local")
            if not _non_empty_string(item.get("semantic_key")):
                missing_key_count += 1
            declared_io = [name for name in ("inputs", "outputs") if name in item]
            if declared_io:
                step_io_fields.append({"index": index, "fields": declared_io})
        shape["step_intent_count"] = len(raw_steps)
        shape["operation_kinds"] = kinds
        shape["branch_object_count"] = branch_count
        shape["missing_semantic_key_count"] = missing_key_count
        if step_io_fields:
            shape["step_io_fields"] = step_io_fields
    for field, label in (
        ("capability_intents", "capability_intent_count"),
        ("approval_points", "approval_point_count"),
        ("steps", "step_count"),
    ):
        value = payload.get(field)
        if isinstance(value, list):
            shape[label] = len(value)
    return shape


def validation_error_path(exc: BaseException) -> str:
    message = str(exc)
    explicit_path = re.search(r"(?:^|\s)path=([^\s]+)", message)
    if explicit_path is not None:
        return explicit_path.group(1)
    if "step_intents[" in message:
        return message.split(" ", 1)[0].rstrip(":")
    if "missing field(s):" in message:
        return message.rsplit(":", 1)[-1].strip()
    return type(exc).__name__


def _known_semantic_keys(raw_steps: list[Any]) -> dict[str, str]:
    known: dict[str, str] = {}
    for index, item in enumerate(raw_steps):
        if not isinstance(item, Mapping):
            continue
        key = item.get("semantic_key")
        if _non_empty_string(key):
            known[str(key).casefold()] = str(key)
            continue
        generated = _key_from_name(item.get("name"), index, set(known))
        if generated:
            known[generated.casefold()] = generated
    return known


def _remap_depends_on(
    depends: list[Any], known: Mapping[str, str]
) -> tuple[list[str], int]:
    remapped: list[str] = []
    dropped = 0
    seen: set[str] = set()
    for item in depends:
        if not isinstance(item, str) or not item.strip():
            dropped += 1
            continue
        canonical = known.get(item.casefold())
        if canonical is None:
            dropped += 1
            continue
        folded = canonical.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        remapped.append(canonical)
    return remapped, dropped


def _normalized_kind(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    folded = value.strip().casefold().replace("-", "_")
    if folded in _OPERATION_KINDS:
        return folded
    return _KIND_ALIASES.get(folded)


def _key_from_name(name: Any, index: int, seen: set[str]) -> str:
    if not isinstance(name, str) or not name.strip():
        candidate = f"step_{index + 1}"
    else:
        folded = _SLUG.sub("_", name.casefold()).strip("_")
        if not folded or not folded[0].isalpha():
            candidate = f"step_{index + 1}"
        else:
            candidate = folded[:64]
    base = candidate
    suffix = 2
    while candidate.casefold() in seen:
        extra = f"_{suffix}"
        candidate = f"{base[: 64 - len(extra)]}{extra}"
        suffix += 1
    return candidate


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
