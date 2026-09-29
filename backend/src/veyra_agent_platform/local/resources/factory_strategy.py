"""Classify missing capabilities into safe factory strategies. Fail closed."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from veyra_agent_platform.contracts.capability import CapabilityRequirement
from veyra_agent_platform.contracts.resource_factory import ResourceFactoryStrategy

SAFE_HTTP_ADAPTER = "veyra.runtime.http.request"
SAFE_FS_ADAPTERS = {
    "veyra.runtime.filesystem.read": "filesystem.read",
    "veyra.runtime.filesystem.search": "filesystem.search",
    "veyra.runtime.filesystem.list": "filesystem.list",
}
SAFE_HTTP_BASE_TOOLS = {"veyra.tool.http.request@1.0.0", "veyra.tool.http.request"}
_UNSAFE_TOKEN = re.compile(
    r"(?:^|[.\s/_-])"
    r"(?:shell|python|eval|exec|javascript|subprocess|browser|wasm|"
    r"filesystem\.write)"
    r"(?:$|[.\s/_-])"
)
KNOWN_EXECUTABLE = frozenset(
    {
        "web_search",
        "http_request",
        "browser_navigate",
        "workspace_read",
        "workspace_search",
        "workspace_list",
        "workspace_write",
        "shell_exec",
        "github_read",
        "github_write",
        "mcp_call",
    }
)
POLICY_CAPABILITIES = frozenset(
    {"local_only", "verification_required", "external_write_approval"}
)
UNSUPPORTED_RUNTIME = frozenset({"image_generation"})
HTTP_LOOKUP_SUFFIXES = ("_lookup", "_fetch", "_http")
SKILL_SUFFIXES = ("_method", "_synthesis", "_procedure", "_protocol", "_planning")


class ResourceFactoryStrategyError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def classify_factory_strategy(
    requirement: CapabilityRequirement,
    *,
    wrapper: Mapping[str, Any] | None = None,
) -> ResourceFactoryStrategy:
    """Return a fail-closed strategy. Never maps a domain occupation to a Skill."""

    capability = requirement.capability.strip()
    if not capability:
        return _unsupported("capability is empty", "none")
    lowered = capability.casefold()
    adapter = wrapper_adapter(wrapper)
    if _is_unsafe_intent(capability, adapter, wrapper):
        return _unsupported(
            "This capability requires an unsafe or arbitrary executor",
            "none",
            risk="high",
        )
    if lowered in UNSUPPORTED_RUNTIME or lowered.startswith("image_"):
        return _unsupported(
            "No local Runtime exists for this capability; Factory will not invent one",
            "none",
        )
    if lowered.startswith("browser_") or lowered == "browser_navigate":
        return _unsupported(
            "Browser automation is not a generatable Resource in this slice",
            "none",
            risk="high",
        )
    if lowered in POLICY_CAPABILITIES or lowered.endswith("_policy"):
        return _unsupported(
            "Policy generation is not runtime-enforced and is unsupported",
            "none",
        )
    if (
        lowered.startswith("github_")
        or lowered == "mcp_call"
        or lowered.startswith("mcp_")
    ):
        return ResourceFactoryStrategy(
            can_generate=False,
            resource_kind=None,
            generation_strategy="none",
            reason="This capability needs an existing external integration",
            risk_level="medium",
            status="requires_external_integration",
            requirements=("external_integration",),
        )
    if lowered in {"shell_exec", "workspace_write"} or lowered.endswith("_write"):
        return _unsupported(
            "Write and shell capabilities use builtin Tools with approval; "
            "Factory will not wrap them",
            "none",
            risk="high",
        )
    if wrapper:
        return _classify_wrapper(requirement, wrapper, adapter)
    if lowered in {"http_request"} or lowered.endswith(HTTP_LOOKUP_SUFFIXES):
        return ResourceFactoryStrategy(
            can_generate=False,
            resource_kind="tool",
            generation_strategy="http_tool_wrapper",
            reason="A constrained HTTP wrapper needs host, method, and route bounds",
            risk_level="medium",
            status="requires_user_configuration",
            requirements=("host", "endpoint"),
        )
    if lowered in {"workspace_read", "workspace_search", "workspace_list"}:
        return ResourceFactoryStrategy(
            can_generate=False,
            resource_kind="tool",
            generation_strategy="filesystem_tool_wrapper",
            reason="A filesystem wrapper needs a fixed project path prefix",
            risk_level="low",
            status="requires_user_configuration",
            requirements=("path_prefix",),
        )
    if lowered in KNOWN_EXECUTABLE:
        return _unsupported(
            "A platform Tool already represents this capability; Factory "
            "will not invent a substitute",
            "none",
        )
    if lowered.endswith(SKILL_SUFFIXES) or lowered not in KNOWN_EXECUTABLE:
        title = capability.replace("_", " ")
        return ResourceFactoryStrategy(
            can_generate=True,
            resource_kind="skill",
            generation_strategy="skill_instruction",
            reason=f"Veyra can create a quarantined Skill for {title}",
            risk_level="low",
            status="generatable",
        )
    return _unsupported("Factory has no safe strategy for this capability", "none")


def _classify_wrapper(
    requirement: CapabilityRequirement,
    wrapper: Mapping[str, Any],
    adapter: str,
) -> ResourceFactoryStrategy:
    if adapter == SAFE_HTTP_ADAPTER or adapter in SAFE_HTTP_BASE_TOOLS:
        missing = [
            name
            for name, present in (
                ("host", bool(_hosts(wrapper))),
                ("endpoint", bool(str(wrapper.get("path_prefix") or "").strip())),
            )
            if not present
        ]
        if missing:
            return ResourceFactoryStrategy(
                can_generate=False,
                resource_kind="tool",
                generation_strategy="http_tool_wrapper",
                reason="HTTP wrappers need a frozen host and route boundary",
                risk_level="medium",
                status="requires_user_configuration",
                requirements=tuple(missing),
            )
        return ResourceFactoryStrategy(
            can_generate=True,
            resource_kind="tool",
            generation_strategy="http_tool_wrapper",
            reason="Veyra can create a declarative HTTP wrapper on http.request",
            risk_level="medium",
            status="generatable",
        )
    if adapter in SAFE_FS_ADAPTERS:
        prefix = str(wrapper.get("path_prefix") or "").strip()
        if not prefix:
            return ResourceFactoryStrategy(
                can_generate=False,
                resource_kind="tool",
                generation_strategy="filesystem_tool_wrapper",
                reason="Filesystem wrappers need a fixed path prefix",
                risk_level="low",
                status="requires_user_configuration",
                requirements=("path_prefix",),
            )
        return ResourceFactoryStrategy(
            can_generate=True,
            resource_kind="tool",
            generation_strategy="filesystem_tool_wrapper",
            reason="Veyra can specialize a read-only filesystem adapter",
            risk_level="low",
            status="generatable",
        )
    del requirement
    return _unsupported("Unknown or unsafe wrapper base adapter", "none", risk="high")


def _is_unsafe_intent(
    capability: str, adapter: str, wrapper: Mapping[str, Any] | None
) -> bool:
    haystack = " ".join(
        part
        for part in (
            capability,
            adapter,
            str((wrapper or {}).get("base_adapter") or ""),
            str((wrapper or {}).get("base_tool") or ""),
            str((wrapper or {}).get("kind") or ""),
        )
        if part
    ).casefold()
    if _UNSAFE_TOKEN.search(haystack):
        return True
    if "wildcard" in haystack or haystack in {"*", "*/*"}:
        return True
    hosts = _hosts(wrapper or {})
    if any(host in {"*", "*.*", "0.0.0.0"} or "*" in host for host in hosts):
        return True
    methods = [
        str(item).upper()
        for item in ((wrapper or {}).get("methods") or [])
        if isinstance(item, str)
    ]
    return "*" in methods or "ANY" in methods


def wrapper_adapter(wrapper: Mapping[str, Any] | None) -> str:
    if not wrapper:
        return ""
    raw = (
        wrapper.get("base_adapter")
        or wrapper.get("adapter")
        or wrapper.get("base_tool")
        or ""
    )
    text = str(raw).strip()
    if text in SAFE_HTTP_BASE_TOOLS or text.endswith("http.request"):
        return SAFE_HTTP_ADAPTER
    if text in SAFE_FS_ADAPTERS:
        return text
    identity = text.split("@", 1)[0]
    mapping = {
        "veyra.tool.filesystem.read": "veyra.runtime.filesystem.read",
        "veyra.tool.filesystem.search": "veyra.runtime.filesystem.search",
        "veyra.tool.filesystem.list": "veyra.runtime.filesystem.list",
        "veyra.tool.http.request": SAFE_HTTP_ADAPTER,
    }
    return mapping.get(identity, text)


def _hosts(wrapper: Mapping[str, Any]) -> list[str]:
    raw = wrapper.get("allowed_hosts") or wrapper.get("hosts") or []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [str(item).strip().lower() for item in raw if str(item).strip()]


def _unsupported(
    reason: str, strategy: str, *, risk: str = "medium"
) -> ResourceFactoryStrategy:
    del strategy
    return ResourceFactoryStrategy(
        can_generate=False,
        resource_kind=None,
        generation_strategy="none",
        reason=reason,
        risk_level=risk,  # type: ignore[arg-type]
        status="unsupported",
    )
