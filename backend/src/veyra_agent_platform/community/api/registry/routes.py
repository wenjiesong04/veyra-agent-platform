"""Public browse/download and authenticated Agent package publishing routes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, Literal, TypeVar, cast

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from ...registry import (
    CommunityForkOrigin,
    CommunityRegistryError,
    CommunityRegistryService,
)
from ..auth.security import (
    authenticate_request,
    get_settings,
    require_csrf,
    require_moderator,
)

_Result = TypeVar("_Result")
MAX_PACKAGE_BYTES = 1_000_000


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReviewRequest(_ClosedModel):
    rating: int = Field(ge=1, le=5)
    body: str = Field(min_length=1, max_length=4_000)


class ReportRequest(_ClosedModel):
    reason: str = Field(min_length=1, max_length=64)
    details: str = Field(default="", max_length=4_000)


class ModerateAgentRequest(_ClosedModel):
    action: Literal["publish", "reject"]
    reason: str = Field(min_length=1, max_length=4_000)


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

    @router.get("/mine/agents")
    def my_agents(
        request: Request,
        limit: int = Query(default=100, ge=1, le=100),
    ) -> dict[str, Any]:
        authenticated = authenticate_request(request)
        return _translate(
            lambda: _registry(request).owned_entries(
                user_id=authenticated.user_id, limit=limit
            )
        )

    @router.get("/starred")
    def starred_agents(
        request: Request,
        limit: int = Query(default=100, ge=1, le=100),
    ) -> dict[str, Any]:
        authenticated = authenticate_request(request)
        return _translate(
            lambda: _registry(request).starred_entries(
                user_id=authenticated.user_id, limit=limit
            )
        )

    @router.get("/moderation/queue")
    def moderation_queue(
        request: Request,
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        authenticated = authenticate_request(request)
        require_moderator(request, authenticated)
        return _translate(lambda: _registry(request).moderation_queue(limit=limit))

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

    @router.get("/agents/{owner_handle}/{slug}/versions")
    def agent_versions(
        owner_handle: str, slug: str, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _registry(request).versions(owner_handle=owner_handle, slug=slug)
        )

    @router.post("/agents/{owner_handle}/{slug}/versions/{version}/moderate")
    def moderate_agent(
        owner_handle: str,
        slug: str,
        version: str,
        payload: ModerateAgentRequest,
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

    @router.post("/agents/{owner_handle}/{slug}/versions/{version}/star")
    def star_agent(
        owner_handle: str, slug: str, version: str, request: Request
    ) -> dict[str, Any]:
        authenticated = authenticate_request(request)
        require_csrf(request, authenticated, get_settings(request))
        return _translate(
            lambda: _registry(request).star(
                owner_handle=owner_handle,
                slug=slug,
                version=version,
                user_id=authenticated.user_id,
            )
        )

    @router.get("/agents/{owner_handle}/{slug}/versions/{version}/star")
    def star_status(
        owner_handle: str, slug: str, version: str, request: Request
    ) -> dict[str, Any]:
        authenticated = authenticate_request(request)
        return _translate(
            lambda: _registry(request).star_status(
                owner_handle=owner_handle,
                slug=slug,
                version=version,
                user_id=authenticated.user_id,
            )
        )

    @router.delete("/agents/{owner_handle}/{slug}/versions/{version}/star")
    def unstar_agent(
        owner_handle: str, slug: str, version: str, request: Request
    ) -> dict[str, Any]:
        authenticated = authenticate_request(request)
        require_csrf(request, authenticated, get_settings(request))
        return _translate(
            lambda: _registry(request).unstar(
                owner_handle=owner_handle,
                slug=slug,
                version=version,
                user_id=authenticated.user_id,
            )
        )

    @router.get("/agents/{owner_handle}/{slug}/versions/{version}/reviews")
    def list_reviews(
        owner_handle: str, slug: str, version: str, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _registry(request).reviews(
                owner_handle=owner_handle, slug=slug, version=version
            )
        )

    @router.post("/agents/{owner_handle}/{slug}/versions/{version}/reviews")
    def create_review(
        owner_handle: str,
        slug: str,
        version: str,
        payload: ReviewRequest,
        request: Request,
    ) -> dict[str, Any]:
        authenticated = authenticate_request(request)
        require_csrf(request, authenticated, get_settings(request))
        return _translate(
            lambda: _registry(request).review(
                owner_handle=owner_handle,
                slug=slug,
                version=version,
                user_id=authenticated.user_id,
                rating=payload.rating,
                body=payload.body,
            )
        )

    @router.post("/agents/{owner_handle}/{slug}/versions/{version}/report")
    def report_agent(
        owner_handle: str,
        slug: str,
        version: str,
        payload: ReportRequest,
        request: Request,
    ) -> dict[str, Any]:
        authenticated = authenticate_request(request)
        require_csrf(request, authenticated, get_settings(request))
        return _translate(
            lambda: _registry(request).report(
                owner_handle=owner_handle,
                slug=slug,
                version=version,
                user_id=authenticated.user_id,
                reason=payload.reason,
                details=payload.details,
            )
        )

    @router.post("/agents", status_code=status.HTTP_201_CREATED)
    async def publish_agent(
        request: Request,
        package: Annotated[UploadFile, File()],
        fork_owner_handle: Annotated[str | None, Form()] = None,
        fork_slug: Annotated[str | None, Form()] = None,
        fork_version: Annotated[str | None, Form()] = None,
        fork_source_hash: Annotated[str | None, Form()] = None,
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
                fork_origin=CommunityForkOrigin.from_optional_fields(
                    owner_handle=fork_owner_handle,
                    slug=fork_slug,
                    version=fork_version,
                    source_hash=fork_source_hash,
                ),
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
            if code
            in {
                "registry_entry_not_found",
                "registry_package_missing",
                "registry_version_not_found",
            }
            else status.HTTP_409_CONFLICT
            if code == "registry_version_exists"
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=status_code, detail=code) from exc
