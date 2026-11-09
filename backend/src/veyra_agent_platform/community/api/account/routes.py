"""Authenticated profile and device-session management HTTP routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)

from ...accounts.identifiers import InvalidPublicHandle
from ...accounts.profiles import ProfileUnavailableError
from ..auth.schemas import AccountResponse
from ..auth.security import (
    authenticate_request,
    clear_auth_cookies,
    get_settings,
    get_workflows,
    require_csrf,
)
from .schemas import (
    DeviceSessionResponse,
    MeResponse,
    ProfileUpdateRequest,
    SessionListResponse,
)


def build_router() -> APIRouter:
    """Build the authenticated Community account router."""

    router = APIRouter(prefix="/api/v1/account", tags=["account"])

    @router.get("/me", response_model=MeResponse)
    def me(request: Request) -> MeResponse:
        authenticated = authenticate_request(request)
        profile = request.app.state.account_profiles.get(authenticated.user_id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="authentication_required",
            )
        return MeResponse(account=AccountResponse.from_profile(profile))

    @router.patch("/profile", response_model=MeResponse)
    @router.patch("/me", response_model=MeResponse)
    def update_profile(payload: ProfileUpdateRequest, request: Request) -> MeResponse:
        authenticated = authenticate_request(request)
        require_csrf(request, authenticated, get_settings(request))
        try:
            profile = request.app.state.account_profiles.update(
                authenticated.user_id,
                handle=payload.handle,
                display_name=payload.display_name,
            )
        except (InvalidPublicHandle, ProfileUnavailableError) as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="profile_update_unavailable",
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="profile_update_invalid",
            ) from error
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="authentication_required",
            )
        return MeResponse(account=AccountResponse.from_profile(profile))

    @router.post("/avatar", response_model=MeResponse)
    async def upload_avatar(
        request: Request, avatar: Annotated[UploadFile, File()]
    ) -> MeResponse:
        authenticated = authenticate_request(request)
        require_csrf(request, authenticated, get_settings(request))
        content = await avatar.read(2 * 1024 * 1024 + 1)
        await avatar.close()
        try:
            request.app.state.account_avatars.replace(
                authenticated.user_id, content, avatar.content_type
            )
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="avatar_invalid",
            ) from error
        profile = request.app.state.account_profiles.get(authenticated.user_id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="authentication_required",
            )
        return MeResponse(account=AccountResponse.from_profile(profile))

    @router.delete("/avatar", status_code=status.HTTP_204_NO_CONTENT)
    def delete_avatar(request: Request) -> Response:
        authenticated = authenticate_request(request)
        require_csrf(request, authenticated, get_settings(request))
        request.app.state.account_avatars.delete(authenticated.user_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/sessions", response_model=SessionListResponse)
    def list_sessions(request: Request) -> SessionListResponse:
        authenticated = authenticate_request(request)
        sessions = get_workflows(request).sessions.list_for_user(
            authenticated.user_id,
            authenticated.session_id,
        )
        return SessionListResponse(
            sessions=tuple(
                DeviceSessionResponse.from_session(item) for item in sessions
            )
        )

    @router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
    def revoke_session(session_id: str, request: Request) -> Response:
        authenticated = authenticate_request(request)
        settings = get_settings(request)
        require_csrf(request, authenticated, settings)
        if not get_workflows(request).sessions.revoke_named_session(
            authenticated, session_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="not_found"
            )
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        if session_id == authenticated.session_id:
            clear_auth_cookies(response, settings)
        return response

    return router


def build_avatar_router() -> APIRouter:
    """Build the anonymous display endpoint for persisted profile avatars."""

    router = APIRouter(prefix="/api/v1/avatars", tags=["avatars"])

    @router.get("/{user_id}")
    def get_avatar(user_id: str, request: Request) -> Response:
        result = request.app.state.account_avatars.get(user_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="not_found"
            )
        avatar, content = result
        etag = f'"{avatar.etag}"'
        if request.headers.get("if-none-match") == etag:
            return Response(
                status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag}
            )
        return Response(
            content=content,
            media_type=avatar.media_type,
            headers={"Cache-Control": "public, max-age=3600", "ETag": etag},
        )

    return router
