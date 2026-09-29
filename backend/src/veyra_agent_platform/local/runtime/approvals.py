"""Bounded, server-built approval summaries. Never ask the model to write these."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_SECRET_KEYS = {
    "authorization",
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "credential",
    "private_key",
}


def tool_approval_summary(
    reference: str,
    arguments: Mapping[str, Any],
    *,
    permissions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    identity = reference.split("@", 1)[0]
    action, target = _action_and_target(identity, arguments)
    return {
        "tool": reference,
        "action": action,
        "target": target,
        "reason": "This tool requires explicit approval before it can run.",
        "permissions": _safe_permissions(permissions or {}),
    }


def _action_and_target(identity: str, arguments: Mapping[str, Any]) -> tuple[str, str]:
    name = identity.rsplit(".", 1)[-1]
    if "filesystem.write" in identity or name == "write":
        return "Write file", _text(
            arguments.get("path") or arguments.get("relative_path")
        )
    if "filesystem.read" in identity or name == "read":
        return "Read file", _text(
            arguments.get("path") or arguments.get("relative_path")
        )
    if "filesystem.search" in identity or name == "search":
        return "Search files", _text(arguments.get("query") or arguments.get("path"))
    if "filesystem.list" in identity or name == "list":
        return "List files", _text(arguments.get("path") or arguments.get("directory"))
    if "shell" in identity or name == "exec":
        return "Run command", _text(arguments.get("command") or arguments.get("cmd"))
    if "http" in identity:
        return "HTTP request", _text(
            arguments.get("path") or arguments.get("url") or arguments.get("host")
        )
    if "github" in identity:
        return "GitHub request", _text(arguments.get("path"))
    if "web.search" in identity or identity.endswith(".search"):
        return "Search the web", _text(arguments.get("query"))
    if "browser" in identity:
        return "Open page", _text(arguments.get("url"))
    return "Use tool", _text(arguments.get("path") or arguments.get("query") or name)


def _safe_permissions(permissions: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in (
        "tools",
        "network_hosts",
        "filesystem_read_roots",
        "filesystem_write_roots",
        "shell_workspace_only",
    ):
        if key in permissions:
            result[key] = permissions[key]
    return result


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    lowered = text.casefold()
    if any(key in lowered for key in _SECRET_KEYS):
        return ""
    return text[:240]
