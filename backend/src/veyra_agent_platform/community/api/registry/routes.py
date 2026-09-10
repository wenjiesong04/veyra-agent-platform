"""Public browse/download and authenticated Agent package publishing routes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, TypeVar, cast

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response

from ...registry import CommunityRegistryError, CommunityRegistryService
from ..auth.security import authenticate_request, get_settings, require_csrf

_Result = TypeVar("_Result")
MAX_PACKAGE_BYTES = 1_000_000


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/registry", tags=["registry"])

    @router.get("/agents")
    def list_agents(
        request: Request,
        query: str | None = Query(default=None, max_length=120),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        return _translate(
            lambda: _registry(request).list_entries(query=query, limit=limit)
        )

    @router.get("/agents/{owner_handle}/{slug}")
    def agent_detail(owner_handle: str, slug: str, request: Request) -> dict[str, Any]:
        return _translate(
            lambda: _registry(request).entry(owner_handle=owner_handle, slug=slug)
        )

    @router.get("/agents/{owner_handle}/{slug}/versions/{version}")
    def agent_version(
        owner_handle: str, slug: str, version: str, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _registry(request).entry(
                owner_handle=owner_handle, slug=slug, version=version
            )
        )

    @router.get("/agents/{owner_handle}/{slug}/versions/{version}/download")
    def download_agent(
        owner_handle: str, slug: str, version: str, request: Request
    ) -> Response:
        metadata, content = _translate(
            lambda: _registry(request).download(
                owner_handle=owner_handle, slug=slug, version=version
            )
        )
        return Response(
            content=content,
            media_type="application/yaml",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{slug}-{version}.vagent.yaml"'
                ),
                "ETag": f'"{metadata["source_hash"]}"',
            },
        )

    @router.post("/agents", status_code=status.HTTP_201_CREATED)
    async def publish_agent(
        request: Request, package: Annotated[UploadFile, File()]
    ) -> dict[str, Any]:
        authenticated = authenticate_request(request)
        require_csrf(request, authenticated, get_settings(request))
        content = await package.read(MAX_PACKAGE_BYTES + 1)
        await package.close()
        return _translate(
            lambda: _registry(request).publish(
                user_id=authenticated.user_id,
                filename=package.filename,
                content=content,
            )
        )

    return router


def _registry(request: Request) -> CommunityRegistryService:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="community_database_unavailable",
        )
    return cast(CommunityRegistryService, request.app.state.community_registry)


def _translate(operation: Callable[[], _Result]) -> _Result:
    try:
        return operation()
    except CommunityRegistryError as exc:
        code = exc.code
        status_code = (
            status.HTTP_404_NOT_FOUND
            if code in {"registry_entry_not_found", "registry_package_missing"}
            else status.HTTP_409_CONFLICT
            if code == "registry_version_exists"
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=status_code, detail=code) from exc
