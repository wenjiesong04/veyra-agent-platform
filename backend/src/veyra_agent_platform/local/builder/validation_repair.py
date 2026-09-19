"""Project existing Agent validation into Builder-readable repair facts."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from veyra_agent_platform.contracts.resource import ResourceRef
from veyra_agent_platform.local.builder.resource_binding import (
    grant_required_permissions,
)

_HASH = re.compile(r"^[0-9a-f]{64}$")


class ValidationRepairError(ValueError):
    """The requested validation issue cannot be repaired without guessing."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


_NEXT_ACTION = {
    "resource_unbound": (
        "Add this Tool in Project Resources first. Builder will not add it "
        "from the Catalog."
    ),
    "missing": (
        "This dependency is not available in the current Project. Choose an "
        "owned resource instead of guessing."
    ),
    "configuration_required": (
        "Configure the host credential in Resource Library. Builder will not "
        "store secrets."
    ),
    "runtime_unavailable": "This resource cannot run on the local Runtime.",
    "review_required": "Review the discovered MCP tool before using it.",
    "project_binding_stale": (
        "Rebind the Project Resource pin explicitly. Builder will not silently "
        "upgrade the Agent lock to the Catalog hash."
    ),
    "kind_mismatch": "The Catalog kind does not match this Agent usage.",
    "secret_declaration_missing": (
        "Declare the secret reference in Studio. Builder will not configure "
        "host secrets."
    ),
    "context_not_declared": "Declare the Knowledge reference in the Agent source.",
    "context_too_large": (
        "Remove Knowledge documents until the Agent is within the limit."
    ),
}


def project_issues(validation: dict[str, Any]) -> list[dict[str, Any]]:
    """Project inspect_agent_dependencies rows into bounded Builder issues."""

    issues = [
        _issue(dependency)
        for dependency in validation.get("dependencies") or []
        if dependency.get("status") != "ready"
    ]
    return issues


def select_issue(
    validation: dict[str, Any], reference: str, code: str
) -> dict[str, Any]:
    """Return exactly one matching issue or fail closed."""

    matches = [
        issue
        for issue in project_issues(validation)
        if issue["reference"] == reference and issue["code"] == code
    ]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise ValidationRepairError(
            "validation_repair_ambiguous",
            "Multiple validation issues matched this request.",
        )
    raise ValidationRepairError(
        "validation_repair_not_found",
        "No matching Agent validation issue was found.",
    )


def repair_agent_source(
    source: dict[str, Any], issue: dict[str, Any]
) -> dict[str, Any]:
    """Mutate one Agent source using server-known pins and required permissions."""

    if not issue.get("repairable"):
        raise ValidationRepairError(
            "validation_repair_not_repairable",
            issue.get("next_action")
            or "This validation issue cannot be repaired automatically.",
        )
    candidate = deepcopy(source)
    code = issue["code"]
    reference = str(issue["reference"])
    if code in {"lock_mismatch", "lock_missing"} and issue["kind"] == "knowledge":
        pin = issue.get("content_hash")
        _require_hash(pin)
        if (
            str(issue.get("version") or "")
            != ResourceRef.from_string(reference).version
        ):
            raise ValidationRepairError(
                "validation_repair_not_repairable",
                "The Knowledge version changed; rebind it explicitly "
                "instead of guessing.",
            )
        candidate["lock"] = {**candidate.get("lock", {}), reference: pin}
        return candidate
    if code in {"lock_mismatch", "lock_missing"}:
        pin = issue.get("bound_content_hash")
        _require_hash(pin)
        candidate["lock"] = {**candidate.get("lock", {}), reference: pin}
        return candidate
    if code == "permission_denied":
        required = issue.get("required_permissions")
        if not isinstance(required, dict):
            raise ValidationRepairError(
                "validation_repair_not_repairable",
                "Required permissions are not available for a deterministic repair.",
            )
        current = candidate["extensions"]["veyra"]["permissions"]
        candidate["extensions"] = {
            **candidate["extensions"],
            "veyra": {
                **candidate["extensions"]["veyra"],
                "permissions": grant_required_permissions(current, required),
            },
        }
        return candidate
    raise ValidationRepairError(
        "validation_repair_not_repairable",
        "This validation issue cannot be repaired automatically.",
    )


def repair_plan(issue: dict[str, Any], *, kind: str = "agent") -> dict[str, Any]:
    """Facts shown on the repair Proposal; never a second mutation protocol."""

    payload: dict[str, Any] = {
        "code": issue["code"],
        "kind": issue["kind"],
        "reference": issue["reference"],
        "name": issue["name"],
        "repairable": True,
        "automatic_upgrade": False,
        "project_resource_changed": False,
        "target_kind": kind,
        "impact": (
            "Explicitly rebind the Agent lock to the current Project "
            "Knowledge hash. This is not a silent upgrade."
            if issue["kind"] == "knowledge"
            else "Align the Agent lock to the current Project pin."
            if issue["code"] in {"lock_mismatch", "lock_missing"}
            else "Grant only the missing required permissions."
        ),
    }
    for field in ("locked_hash", "bound_content_hash", "content_hash"):
        value = issue.get(field)
        if isinstance(value, str):
            payload[field] = value
    required = issue.get("required_permissions")
    if isinstance(required, dict):
        payload["required_permissions"] = required
    return payload


def _issue(dependency: dict[str, Any]) -> dict[str, Any]:
    code = str(dependency["status"])
    repairable = _repairable(dependency)
    return {
        "code": code,
        "kind": str(dependency["kind"]),
        "reference": str(dependency["reference"]),
        "name": str(dependency.get("name") or dependency["reference"]),
        "message": str(dependency.get("detail") or ""),
        "blocking": True,
        "repairable": repairable,
        "locked_hash": dependency.get("locked_hash"),
        "bound_content_hash": dependency.get("bound_content_hash"),
        "content_hash": dependency.get("content_hash"),
        "version": dependency.get("version"),
        "required_permissions": dependency.get("required_permissions"),
        "next_action": None if repairable else _NEXT_ACTION.get(code),
    }


def _repairable(dependency: dict[str, Any]) -> bool:
    status = dependency.get("status")
    if status == "permission_denied":
        return isinstance(dependency.get("required_permissions"), dict)
    if status not in {"lock_mismatch", "lock_missing"}:
        return False
    if dependency.get("kind") == "knowledge":
        hash_value = dependency.get("content_hash")
        version = dependency.get("version")
        try:
            ref = ResourceRef.from_string(str(dependency.get("reference") or ""))
        except (TypeError, ValueError):
            return False
        return (
            isinstance(hash_value, str)
            and _HASH.fullmatch(hash_value) is not None
            and version == ref.version
        )
    pin = dependency.get("bound_content_hash")
    return isinstance(pin, str) and _HASH.fullmatch(pin) is not None


def _require_hash(value: Any) -> None:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ValidationRepairError(
            "validation_repair_not_repairable",
            "A server-known content hash is required for this repair.",
        )
