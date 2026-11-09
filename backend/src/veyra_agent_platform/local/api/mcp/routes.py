"""HTTP surface for host-side MCP server configuration and discovery."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, TypeVar, cast

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from veyra_agent_platform.contracts.common import SCHEMA_VERSION
from veyra_agent_platform.local.api.projects import TypedApiError
from veyra_agent_platform.local.mcp import McpError, McpService
from veyra_agent_platform.local.resources.readiness import ResourceReadiness

_Result = TypeVar("_Result")


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateMcpServerRequest(_ClosedModel):
    name: str = Field(min_length=1, max_length=64)
    command: str | None = Field(default=None, max_length=512)
    args: list[str] = Field(default_factory=list)
    env_names: dict[str, str] = Field(default_factory=dict)
    transport: Literal["stdio", "streamable_http"] = "stdio"
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class ImportMcpServersRequest(_ClosedModel):
    servers: list[CreateMcpServerRequest] = Field(min_length=1, max_length=32)


class UpdateMcpServerRequest(_ClosedModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    command: str | None = Field(default=None, max_length=512)
    args: list[str] | None = None
    env_names: dict[str, str] | None = None
    transport: Literal["stdio", "streamable_http"] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    enabled: bool | None = None

    @model_validator(mode="after")
    def require_update(self) -> UpdateMcpServerRequest:
        if not self.model_fields_set:
            raise ValueError("at least one MCP server field is required")
        return self


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])

    @router.get("/servers")
    def list_servers(request: Request) -> dict[str, Any]:
        return _translate(lambda: _mcp(request).list_servers())

    @router.post("/servers", status_code=status.HTTP_201_CREATED)
    def create_server(
        payload: CreateMcpServerRequest, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _mcp(request).create_server(
                name=payload.name,
                command=payload.command,
                args=payload.args,
                env_names=payload.env_names,
                transport=payload.transport,
                url=payload.url,
                headers=payload.headers,
                enabled=payload.enabled,
            )
        )

    @router.post("/servers/import")
    def import_servers(
        payload: ImportMcpServersRequest, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _mcp(request).import_servers(
                [item.model_dump() for item in payload.servers]
            )
        )

    @router.post("/servers/{server_id}/discover")
    def discover(server_id: str, request: Request) -> dict[str, Any]:
        return _translate(
            lambda: cast(
                ResourceReadiness, request.app.state.resource_readiness
            ).response(_mcp(request).discover(server_id))
        )

    @router.get("/servers/{server_id}/readiness")
    def readiness(server_id: str, request: Request) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "server_id": server_id,
            **_translate(lambda: _mcp(request).readiness(server_id)),
        }

    @router.patch("/servers/{server_id}")
    def update_server(
        server_id: str, payload: UpdateMcpServerRequest, request: Request
    ) -> dict[str, Any]:
        if set(payload.model_fields_set) == {"enabled"}:
            return _translate(
                lambda: _mcp(request).update_server(
                    server_id, enabled=bool(payload.enabled)
                )
            )
        return _translate(
            lambda: _mcp(request).edit_server(
                server_id,
                name=payload.name,
                command=payload.command,
                args=payload.args,
                env_names=payload.env_names,
                transport=payload.transport,
                url=payload.url,
                headers=payload.headers,
                enabled=payload.enabled,
            )
        )

    @router.post("/servers/{server_id}/tools/{resource_id}/versions/{version}/approve")
    def approve_tool(
        server_id: str, resource_id: str, version: str, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: cast(
                ResourceReadiness, request.app.state.resource_readiness
            ).response(_mcp(request).approve_tool(server_id, resource_id, version))
        )

    @router.delete("/servers/{server_id}")
    def delete_server(server_id: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _mcp(request).delete_server(server_id))

    return router


def _mcp(request: Request) -> McpService:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return cast(McpService, request.app.state.mcp)


def _translate(operation: Callable[[], _Result]) -> _Result:
    try:
        return operation()
    except McpError as exc:
        status_code = 404 if exc.code == "mcp_server_not_found" else 422
        raise TypedApiError(status_code, exc.code, str(exc)) from exc
