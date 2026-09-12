"""Public and authenticated Community Plugin Pack registry routes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, TypeVar, cast

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from ...registry import (
    CommunityPluginRegistryError,
    CommunityPluginRegistryService,
)
from ..auth.security import (
    authenticate_request,
    get_settings,
    require_csrf,
    require_moderator,
)

_Result = TypeVar("_Result")


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModeratePluginRequest(_ClosedModel):
    action: str = Field(pattern="^(publish|reject)$")
    reason: str = Field(min_length=1, max_length=4_000)


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/registry", tags=["plugin-registry"])

    @router.get("/plugins")
    def list_plugins(
        request: Request,
        query: str | None = Query(default=None, max_length=120),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        return _translate(
            lambda: _registry(request).list_entries(query=query, limit=limit)
        )

    @router.get("/plugins/moderation/queue")
    def moderation_queue(
        request: Request,
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        authenticated = authenticate_request(request)
        require_moderator(request, authenticated)
        return _translate(lambda: _registry(request).moderation_queue(limit=limit))

    @router.get("/plugins/{owner_handle}/{slug}")
    def plugin_detail(owner_handle: str, slug: str, request: Request) -> dict[str, Any]:
        return _translate(
            lambda: _registry(request).entry(owner_handle=owner_handle, slug=slug)
        )

    @router.get("/plugins/{owner_handle}/{slug}/versions")
    def plugin_versions(
        owner_handle: str, slug: str, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _registry(request).versions(owner_handle=owner_handle, slug=slug)
        )

    @router.get("/plugins/{owner_handle}/{slug}/versions/{version}")
    def plugin_version(
        owner_handle: str, slug: str, version: str, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _registry(request).entry(
                owner_handle=owner_handle, slug=slug, version=version
            )
        )

    @router.get("/plugins/{owner_handle}/{slug}/versions/{version}/download")
    def download_plugin(
        owner_handle: str, slug: str, version: str, request: Request
    ) -> Response:
        metadata, content = _translate(
            lambda: _registry(request).download(
                owner_handle=owner_handle, slug=slug, version=version
            )
        )
        return Response(
            content=content,
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{slug}-{version}.vplugin.zip"'
                ),
                "ETag": f'"{metadata["package_hash"]}"',
            },
        )

    @router.post("/plugins", status_code=status.HTTP_201_CREATED)
    async def publish_plugin(
        request: Request,
        package: Annotated[UploadFile, File()],
    ) -> dict[str, Any]:
        authenticated = authenticate_request(request)
        require_csrf(request, authenticated, get_settings(request))
        content = await package.read(5_000_001)
        await package.close()
        return _translate(
            lambda: _registry(request).publish(
                user_id=authenticated.user_id,
                filename=package.filename,
                content=content,
            )
        )

    @router.post("/plugins/{owner_handle}/{slug}/versions/{version}/moderate")
    def moderate_plugin(
        owner_handle: str,
        slug: str,
        version: str,
        payload: ModeratePluginRequest,
        request: Request,
    ) -> dict[str, Any]:
        authenticated = authenticate_request(request)
        require_csrf(request, authenticated, get_settings(request))
        require_moderator(request, authenticated)
        return _translate(
            lambda: _registry(request).moderate(
                owner_handle=owner_handle,
                slug=slug,
                version=version,
                moderator_id=authenticated.user_id,
                action=payload.action,
                reason=payload.reason,
            )
        )

    return router


def _registry(request: Request) -> CommunityPluginRegistryService:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="community_database_unavailable",
        )
    return cast(
        CommunityPluginRegistryService, request.app.state.community_plugin_registry
    )


def _translate(operation: Callable[[], _Result]) -> _Result:
    try:
        return operation()
    except CommunityPluginRegistryError as exc:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if exc.code
            in {
                "plugin_entry_not_found",
                "plugin_package_missing",
                "plugin_version_not_found",
            }
            else status.HTTP_409_CONFLICT
            if exc.code == "plugin_version_exists"
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=status_code, detail=exc.code) from exc
