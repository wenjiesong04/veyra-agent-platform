"""HTTP surface for host-side MCP server configuration and discovery."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict, Field

from veyra_agent_platform.local.api.projects import TypedApiError
from veyra_agent_platform.local.mcp import McpError, McpService

_Result = TypeVar("_Result")


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateMcpServerRequest(_ClosedModel):
    name: str = Field(min_length=1, max_length=64)
    command: str = Field(min_length=1, max_length=512)
    args: list[str] = Field(default_factory=list)
    env_names: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class UpdateMcpServerRequest(_ClosedModel):
    enabled: bool


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
                enabled=payload.enabled,
            )
        )

    @router.post("/servers/{server_id}/discover")
    def discover(server_id: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _mcp(request).discover(server_id))

    @router.patch("/servers/{server_id}")
    def update_server(
        server_id: str, payload: UpdateMcpServerRequest, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _mcp(request).update_server(server_id, enabled=payload.enabled)
        )

    @router.post("/servers/{server_id}/tools/{resource_id}/versions/{version}/approve")
    def approve_tool(
        server_id: str, resource_id: str, version: str, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _mcp(request).approve_tool(server_id, resource_id, version)
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
