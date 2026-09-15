"""Live API projection; never write host readiness into package identity."""

from __future__ import annotations

import os
import shutil
from collections.abc import Collection
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from veyra_agent_platform.local.mcp.schema import McpSchemaError, require_contract
from veyra_agent_platform.local.mcp.service import McpService
from veyra_agent_platform.local.secrets import resolve_secret

if TYPE_CHECKING:
    from veyra_agent_platform.local.runtime.client import RuntimeModelClient

from .catalog import RESOURCE_KINDS, ResourceCatalog, ResourceCatalogError


class ResourceReadiness:
    def __init__(
        self,
        catalog: ResourceCatalog,
        model: RuntimeModelClient,
        adapters: Collection[str],
        mcp: McpService | None,
    ) -> None:
        self.catalog = catalog
        self.model = model
        self.adapters = adapters
        self.mcp = mcp

    def project(self, descriptor: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(descriptor)
        spec = result["spec"]
        kind = result["kind"]
        requirements: list[dict[str, Any]] = []
        reasons: list[dict[str, str]] = []
        availability = "ready"
        runtime = "supported"

        def block(state: str, code: str, message: str) -> None:
            nonlocal availability, runtime
            availability = state
            runtime = (
                "runtime_not_configured"
                if state == "requires_configuration"
                else "runtime_not_supported"
            )
            reasons.append({"code": code, "message": message})

        def require(code: str, message: str, satisfied: bool) -> None:
            requirements.append(
                {"code": code, "message": message, "satisfied": satisfied}
            )
            if not satisfied:
                block("requires_configuration", code, message)

        if result["availability"] in {"disabled", "quarantined", "unavailable"}:
            block(
                result["availability"],
                "resource_" + result["availability"],
                "Resource is "
                + result["availability"]
                + "; review or enable it before use.",
            )
        elif kind == "template" or result["availability"] == "design_only":
            block(
                "design_only",
                "design_resource",
                "Design/creation resource; not directly executable by Runtime.",
            )
        elif kind == "mcp_tool" and not spec.get("adapter"):
            require(
                "mcp_discovery_required",
                "Configure an MCP server, discover and review a concrete Tool.",
                False,
            )
        elif kind in {"tool", "mcp_tool"}:
            adapter = spec.get("adapter")
            if adapter not in self.adapters:
                block(
                    "unavailable",
                    "adapter_unavailable",
                    "The required Tool adapter is not installed on this host.",
                )
            elif result["origin"] == "discovered" and (
                spec.get("review_required") or not result["factory_selectable"]
            ):
                block(
                    "unavailable",
                    "mcp_review_required",
                    "Review the discovered Tool schema before enabling it.",
                )
            elif result["runtime_status"] == "runtime_not_supported":
                block(
                    "unavailable",
                    "runtime_unsupported",
                    "This resource is not supported by the current Runtime.",
                )
            else:
                if spec.get("secret_ref"):
                    require(
                        "secret_not_configured",
                        f"Configure host credential {spec['secret_ref']} "
                        f"({spec.get('secret_env', '')}).",
                        bool(
                            resolve_secret(
                                self.model.secret_store,
                                spec["secret_ref"],
                                spec.get("secret_env", ""),
                            )
                        ),
                    )
                if adapter == "veyra.runtime.shell.exec":
                    shell = "cmd.exe" if os.name == "nt" else "/bin/sh"
                    require(
                        "host_shell_missing",
                        f"Install {shell} on this host.",
                        shutil.which(shell) is not None,
                    )
                if adapter == "veyra.runtime.mcp.call":
                    server_id = spec.get("mcp_server_id")
                    check = (
                        self.mcp.readiness(server_id or "")
                        if self.mcp is not None
                        else {
                            "ready": False,
                            "code": "mcp_configuration",
                            "detail": "MCP is not configured",
                        }
                    )
                    require(
                        "mcp_configuration",
                        "Configure an enabled MCP server and its credential bindings.",
                        bool(check["ready"]),
                    )
                    if not check["ready"]:
                        if check["code"] == "mcp_server_disabled":
                            block("disabled", check["code"], check["detail"])
                        else:
                            reasons.append(
                                {"code": check["code"], "message": check["detail"]}
                            )
                    else:
                        assert self.mcp is not None
                        server = next(
                            item
                            for item in self.mcp.list_servers()["servers"]
                            if item["server_id"] == server_id
                        )
                        if server["transport"] == "stdio":
                            require(
                                "mcp_command_missing",
                                "Install the configured MCP server command.",
                                shutil.which(server["command"]) is not None,
                            )
                    try:
                        require_contract(spec)
                    except McpSchemaError:
                        block(
                            "unavailable",
                            "mcp_schema_unsupported",
                            "Discover and review a supported MCP input/output schema.",
                        )
                if availability == "ready" and (
                    result["availability"] == "requires_configuration"
                    or result["runtime_status"] == "runtime_not_configured"
                ):
                    require(
                        "resource_configuration",
                        "Complete the configuration declared in the resource spec.",
                        False,
                    )
        elif result["runtime_status"] == "runtime_not_supported":
            block(
                "unavailable",
                "runtime_unsupported",
                "This resource is not supported by the current Runtime.",
            )
        elif kind == "skill" or (
            kind == "component" and result["name"] in {"Agent", "Model"}
        ):
            require(
                "model_configuration",
                "Configure the Runtime provider, model and host model credential.",
                self.model.configured,
            )
        elif (
            result["runtime_status"] == "runtime_not_configured"
            or result["availability"] == "requires_configuration"
        ):
            require(
                "resource_configuration",
                "Complete this resource's Runtime configuration before use.",
                False,
            )

        result.update(
            availability=availability,
            runtime_status=runtime,
            configuration_requirements=requirements,
            blocking_reasons=reasons,
            dependencies=deepcopy(spec.get("dependencies", [])),
            compatibility={
                "scope": "host",
                "execution": (
                    "Requires Project/Agent permissions and inputs; "
                    "readiness is not execution verification. "
                    "Remote credentials, endpoints and models are not probed."
                ),
                "network_verified": False,
            },
        )
        return result

    def response(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = dict(payload)
        for field in ("resources", "tools"):
            if field in result:
                result[field] = [self.project(item) for item in result[field]]
        if "resource" in result:
            result["resource"] = self.project(result["resource"])
        return result

    def resources(
        self, *, kind: str | None, availability: str | None
    ) -> dict[str, Any]:
        if availability is not None and availability not in {
            "ready",
            "requires_configuration",
            "design_only",
            "unavailable",
            "disabled",
            "quarantined",
        }:
            raise ResourceCatalogError(
                "invalid_resource_availability", "availability is not a catalog state"
            )
        result = self.response(self.catalog.resources(kind=kind))
        result["resources"] = [
            item
            for item in result["resources"]
            if availability is None or item["availability"] == availability
        ]
        result["kinds"] = [
            {
                "kind": value,
                "count": sum(item["kind"] == value for item in result["resources"]),
            }
            for value in RESOURCE_KINDS
        ]
        return result
