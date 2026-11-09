"""Deterministic structural validation for Resource Factory drafts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from veyra_agent_platform.contracts.canonical import sha256_digest

from .factory_strategy import SAFE_FS_ADAPTERS, SAFE_HTTP_ADAPTER, SAFE_HTTP_BASE_TOOLS

_CAPABILITY_NAME = re.compile(r"^[a-z][a-z0-9_]{2,62}$")
_SECRET_KEY = re.compile(
    r"(api[_-]?key|authorization|secret|password|token|private[_-]?key|credential)",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(
    r"(?:\bsk-[A-Za-z0-9_-]{20,}|\bgh[pousr]_[A-Za-z0-9]{20,}|"
    r"\bgithub_pat_[A-Za-z0-9_]{20,}|\bxox[baprs]-[A-Za-z0-9-]{20,}|"
    r"\bAKIA[0-9A-Z]{16}\b|\bBearer\s+\S+)",
    re.IGNORECASE,
)
_OVERRIDE = re.compile(
    r"(ignore previous|jailbreak|you are now|bypass approval|"
    r"override system|权限提升|绕过.?审批|修改 system)",
    re.IGNORECASE,
)
_CODE_CLAIM = re.compile(
    r"(execute python|run (?:arbitrary )?shell|eval\s*\(|subprocess|"
    r"javascript executor|dynamic import|任意代码)",
    re.IGNORECASE,
)
_UNSUPPORTED_TOOL = re.compile(
    r"veyra\.tool\.shell|veyra\.runtime\.shell|shell\.exec|"
    r"veyra\.runtime\.filesystem\.write|python://|javascript:",
    re.IGNORECASE,
)
_SKILL_SECTIONS = (
    "Purpose",
    "When to use",
    "Procedure",
    "Expected output",
    "Constraints",
    "Failure handling",
)
_WILDCARD_HOSTS = frozenset({"*", "*.*", "0.0.0.0", "::", "any"})
_MAX_INSTRUCTION = 20_000
_MIN_SECTION = 8
_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"})
_SCHEMA_TYPES = frozenset({"string", "number", "integer", "boolean", "object", "array"})


class ResourceFactoryValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_skill_draft(
    *,
    instruction: str,
    capabilities: list[str],
    name: str,
    description: str,
) -> dict[str, Any]:
    text = (instruction or "").strip()
    if not text:
        raise ResourceFactoryValidationError(
            "factory_validation_failed", "Skill instruction is required"
        )
    if len(text) > _MAX_INSTRUCTION:
        raise ResourceFactoryValidationError(
            "factory_validation_failed", "Skill instruction is too large"
        )
    sections = _required_sections(text)
    purpose = sections["Purpose"]
    if len(purpose.strip()) < _MIN_SECTION:
        raise ResourceFactoryValidationError(
            "factory_validation_failed", "Skill purpose is empty"
        )
    if not (name or "").strip() or not (description or "").strip():
        raise ResourceFactoryValidationError(
            "factory_validation_failed", "Skill name and description are required"
        )
    tags = list(dict.fromkeys(item.strip() for item in capabilities if item.strip()))
    if not tags:
        raise ResourceFactoryValidationError(
            "factory_validation_failed", "Skill capabilities are required"
        )
    for tag in tags:
        if _CAPABILITY_NAME.fullmatch(tag) is None:
            raise ResourceFactoryValidationError(
                "factory_validation_failed", "Skill capability tags must be snake_case"
            )
    _reject_secrets({"instruction": text, "name": name, "description": description})
    if _OVERRIDE.search(text):
        raise ResourceFactoryValidationError(
            "factory_validation_failed", "Skill instruction cannot override the system"
        )
    if _CODE_CLAIM.search(text):
        raise ResourceFactoryValidationError(
            "factory_validation_failed",
            "Skill instruction cannot claim code execution",
        )
    if _UNSUPPORTED_TOOL.search(text):
        raise ResourceFactoryValidationError(
            "factory_validation_failed",
            "Skill instruction cannot reference unsupported tools",
        )
    return {
        "passed": True,
        "kind": "skill",
        "capabilities": tags,
        "instruction_digest": sha256_digest({"instruction": text}),
    }


def validate_tool_wrapper(spec: Mapping[str, Any]) -> dict[str, Any]:
    adapter = str(spec.get("base_adapter") or spec.get("adapter") or "").strip()
    if adapter in SAFE_HTTP_BASE_TOOLS or adapter.endswith("http.request"):
        adapter = SAFE_HTTP_ADAPTER
    identity = adapter.split("@", 1)[0]
    mapping = {
        "veyra.tool.filesystem.read": "veyra.runtime.filesystem.read",
        "veyra.tool.filesystem.search": "veyra.runtime.filesystem.search",
        "veyra.tool.filesystem.list": "veyra.runtime.filesystem.list",
        "veyra.tool.http.request": SAFE_HTTP_ADAPTER,
    }
    adapter = mapping.get(identity, adapter)
    if adapter == SAFE_HTTP_ADAPTER:
        return _validate_http_wrapper(spec, adapter)
    if adapter in SAFE_FS_ADAPTERS:
        return _validate_fs_wrapper(spec, adapter)
    raise ResourceFactoryValidationError(
        "factory_unsupported", "Unknown or unsafe wrapper base adapter"
    )


def snapshot_identity(resource: Mapping[str, Any]) -> str:
    spec = resource.get("spec")
    spec_map = dict(spec) if isinstance(spec, Mapping) else {}
    spec_map.pop("ui", None)
    spec_map.pop("review_required", None)
    material = {
        "resource_id": resource.get("resource_id"),
        "kind": resource.get("kind"),
        "version": resource.get("version"),
        "capabilities": list(resource.get("capabilities") or []),
        "spec": spec_map,
        "required_permissions": resource.get("required_permissions"),
    }
    return sha256_digest(material)


def _validate_http_wrapper(spec: Mapping[str, Any], adapter: str) -> dict[str, Any]:
    _reject_secrets(spec)
    hosts = _string_list(spec.get("allowed_hosts"), "allowed_hosts")
    if not hosts:
        raise ResourceFactoryValidationError(
            "factory_validation_failed", "HTTP wrappers require allowed_hosts"
        )
    for host in hosts:
        if host.lower() in _WILDCARD_HOSTS or "*" in host:
            raise ResourceFactoryValidationError(
                "factory_validation_failed", "Wildcard HTTP hosts are not allowed"
            )
        if "/" in host or host.startswith("[") or "@" in host:
            raise ResourceFactoryValidationError(
                "factory_validation_failed", "HTTP host is invalid"
            )
        parsed = urlsplit(f"http://{host}")
        if parsed.hostname is None or parsed.username or parsed.password:
            raise ResourceFactoryValidationError(
                "factory_validation_failed", "HTTP host is invalid"
            )
    methods = [item.upper() for item in _string_list(spec.get("methods"), "methods")]
    if not methods or any(item not in _HTTP_METHODS for item in methods):
        raise ResourceFactoryValidationError(
            "factory_validation_failed", "HTTP wrappers require an explicit method list"
        )
    path_prefix = str(spec.get("path_prefix") or "").strip()
    if not path_prefix.startswith("/") or path_prefix == "/" or "*" in path_prefix:
        raise ResourceFactoryValidationError(
            "factory_validation_failed",
            "HTTP wrappers require a frozen path prefix, not an open route",
        )
    scheme = str(spec.get("scheme") or "http").strip().lower()
    if scheme not in {"http", "https"}:
        raise ResourceFactoryValidationError(
            "factory_validation_failed", "HTTP wrapper scheme must be http or https"
        )
    inputs = _schema_map(spec.get("input_schema"), "input_schema")
    if "url" in inputs or "method" in inputs or "headers" in inputs:
        raise ResourceFactoryValidationError(
            "factory_validation_failed",
            "HTTP wrappers cannot expose unconstrained URL, method, or headers",
        )
    outputs = _schema_map(spec.get("output_schema"), "output_schema")
    timeout_ms = spec.get("timeout_ms", 5_000)
    max_bytes = spec.get("max_response_bytes", 65_536)
    if not isinstance(timeout_ms, int) or timeout_ms < 100 or timeout_ms > 30_000:
        raise ResourceFactoryValidationError(
            "factory_validation_failed", "HTTP wrapper timeout is out of bounds"
        )
    if not isinstance(max_bytes, int) or max_bytes < 1 or max_bytes > 1_000_000:
        raise ResourceFactoryValidationError(
            "factory_validation_failed", "HTTP wrapper response size is out of bounds"
        )
    port = spec.get("port")
    if port is not None and (not isinstance(port, int) or port < 1 or port > 65_535):
        raise ResourceFactoryValidationError(
            "factory_validation_failed", "HTTP wrapper port is invalid"
        )
    return {
        "passed": True,
        "kind": "tool_wrapper",
        "base_adapter": adapter,
        "allowed_hosts": hosts,
        "methods": methods,
        "path_prefix": path_prefix,
        "input_schema": inputs,
        "output_schema": outputs,
    }


def _validate_fs_wrapper(spec: Mapping[str, Any], adapter: str) -> dict[str, Any]:
    _reject_secrets(spec)
    prefix = str(spec.get("path_prefix") or "").strip().replace("\\", "/")
    if (
        not prefix
        or prefix.startswith("/")
        or ".." in prefix.split("/")
        or "*" in prefix
    ):
        raise ResourceFactoryValidationError(
            "factory_validation_failed",
            "Filesystem wrappers require a relative path prefix inside the Project",
        )
    if adapter == "veyra.runtime.filesystem.write":
        raise ResourceFactoryValidationError(
            "factory_unsupported", "Filesystem write wrappers are not allowed"
        )
    inputs = _schema_map(spec.get("input_schema"), "input_schema")
    outputs = _schema_map(spec.get("output_schema"), "output_schema")
    return {
        "passed": True,
        "kind": "tool_wrapper",
        "base_adapter": adapter,
        "path_prefix": prefix,
        "input_schema": inputs,
        "output_schema": outputs,
    }


def _required_sections(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    current = ""
    body: list[str] = []
    for line in text.splitlines():
        heading = line.strip()
        if heading in _SKILL_SECTIONS:
            if current:
                found[current] = "\n".join(body).strip()
            current = heading
            body = []
            continue
        if current:
            body.append(line)
    if current:
        found[current] = "\n".join(body).strip()
    missing = [name for name in _SKILL_SECTIONS if not found.get(name)]
    if missing:
        raise ResourceFactoryValidationError(
            "factory_validation_failed",
            "Skill instruction is missing required sections: " + ", ".join(missing),
        )
    return found


def _schema_map(value: Any, field: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ResourceFactoryValidationError(
            "factory_validation_failed", f"{field} must be a mapping"
        )
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key or not isinstance(item, str):
            raise ResourceFactoryValidationError(
                "factory_validation_failed", f"{field} keys and types must be strings"
            )
        if item not in _SCHEMA_TYPES:
            raise ResourceFactoryValidationError(
                "factory_validation_failed", f"{field} type {item} is not allowed"
            )
        result[key] = item
    return result


def _string_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ResourceFactoryValidationError(
            "factory_validation_failed", f"{field} must be a list of strings"
        )
    return [item.strip() for item in value]


def _reject_secrets(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and _SECRET_KEY.search(key):
                raise ResourceFactoryValidationError(
                    "factory_validation_failed",
                    "Factory drafts must not store secrets or credentials",
                )
            _reject_secrets(item)
        return
    if isinstance(value, list):
        for item in value:
            _reject_secrets(item)
        return
    if isinstance(value, str) and _SECRET_VALUE.search(value):
        raise ResourceFactoryValidationError(
            "factory_validation_failed",
            "Factory drafts must not store secret values",
        )
