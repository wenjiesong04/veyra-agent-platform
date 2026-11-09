"""HTTP routes for email registration, login, refresh, logout, and recovery."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from ...auth.errors import (
    AuthenticationFailure,
    CsrfFailure,
    RegistrationUnavailable,
    VerificationCodeFailure,
)
from ...auth.passwords import PasswordPolicyError
from ...config import CommunitySettings
from .schemas import (
    AcceptedResponse,
    AccountResponse,
    AuthenticatedResponse,
    EmailRequest,
    LoginRequest,
    PasswordResetConfirmRequest,
    RegisterRequest,
    ResetCompleteResponse,
    VerificationCodeRequest,
)
from .security import (
    auth_cookie_names,
    clear_auth_cookies,
    get_settings,
    get_workflows,
    request_context,
    require_refresh_csrf,
    require_trusted_origin,
    set_auth_cookies,
)


def build_router() -> APIRouter:
    """Build only the versioned public Community authentication router."""

    router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

    @router.post(
        "/verification-codes",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=AcceptedResponse,
    )
    def request_verification_code(
        payload: VerificationCodeRequest, request: Request
    ) -> AcceptedResponse:
        require_trusted_origin(request, get_settings(request))
        context = request_context(request, payload.device_name)
        if payload.purpose == "registration":
            get_workflows(request).request_registration_code(payload.email, context)
        else:
            get_workflows(request).request_password_reset_code(payload.email, context)
        return AcceptedResponse()

    @router.post(
        "/registration-code",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=AcceptedResponse,
    )
    def request_registration_code(
        payload: EmailRequest, request: Request
    ) -> AcceptedResponse:
        require_trusted_origin(request, get_settings(request))
        get_workflows(request).request_registration_code(
            payload.email,
            request_context(request, payload.device_name),
        )
        return AcceptedResponse()

    @router.post(
        "/register",
        status_code=status.HTTP_201_CREATED,
        response_model=AuthenticatedResponse,
    )
    def register(payload: RegisterRequest, request: Request) -> JSONResponse:
        require_trusted_origin(request, get_settings(request))
        try:
            account = get_workflows(request).register(
                email=payload.email,
                handle=payload.handle,
                password=payload.password,
                verification_code=payload.verification_code,
                display_name=payload.display_name,
                context=request_context(request, payload.device_name),
            )
        except PasswordPolicyError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="password_policy_failed",
            ) from error
        except RegistrationUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="registration_unavailable",
            ) from error
        response = JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=AuthenticatedResponse(
                account=AccountResponse.from_profile(account.profile)
            ).model_dump(mode="json"),
        )
        set_auth_cookies(response, account.session, get_settings(request))
        return response

    @router.post("/login", response_model=AuthenticatedResponse)
    def login(payload: LoginRequest, request: Request) -> JSONResponse:
        require_trusted_origin(request, get_settings(request))
        try:
            account = get_workflows(request).login(
                email=payload.email,
                password=payload.password,
                context=request_context(request, payload.device_name),
            )
        except AuthenticationFailure as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid_credentials",
            ) from error
        response = JSONResponse(
            content=AuthenticatedResponse(
                account=AccountResponse.from_profile(account.profile)
            ).model_dump(mode="json"),
        )
        set_auth_cookies(response, account.session, get_settings(request))
        return response

    @router.post("/refresh", response_model=AuthenticatedResponse)
    def refresh(request: Request) -> JSONResponse:
        settings = get_settings(request)
        csrf_token = require_refresh_csrf(request, settings)
        refresh_token = request.cookies.get(auth_cookie_names(settings).refresh)
        if refresh_token is None:
            return _invalid_refresh_response(settings)
        try:
            issue = get_workflows(request).sessions.rotate(
                refresh_token=refresh_token,
                csrf_token=csrf_token,
                context=request_context(request, None),
            )
            profile = request.app.state.account_profiles.get(issue.user_id)
        except CsrfFailure as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="csrf_failed"
            ) from error
        except AuthenticationFailure:
            return _invalid_refresh_response(settings)
        if profile is None:
            return _invalid_refresh_response(settings)
        response = JSONResponse(
            content=AuthenticatedResponse(
                account=AccountResponse.from_profile(profile)
            ).model_dump(mode="json"),
        )
        set_auth_cookies(response, issue, settings)
        return response

    @router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
    def logout(request: Request) -> Response:
        settings = get_settings(request)
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        require_trusted_origin(request, settings)
        refresh_token = request.cookies.get(auth_cookie_names(settings).refresh)
        if refresh_token is None:
            clear_auth_cookies(response, settings)
            return response
        csrf_token = require_refresh_csrf(request, settings)
        try:
            get_workflows(request).sessions.revoke_refresh_family(
                refresh_token=refresh_token,
                csrf_token=csrf_token,
                reason="logout",
            )
        except CsrfFailure as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="csrf_failed"
            ) from error
        clear_auth_cookies(response, settings)
        return response

    @router.post(
        "/password-reset/request",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=AcceptedResponse,
    )
    def request_password_reset(
        payload: EmailRequest, request: Request
    ) -> AcceptedResponse:
        require_trusted_origin(request, get_settings(request))
        get_workflows(request).request_password_reset_code(
            payload.email,
            request_context(request, payload.device_name),
        )
        return AcceptedResponse()

    @router.post("/password-reset/confirm", response_model=ResetCompleteResponse)
    def confirm_password_reset(
        payload: PasswordResetConfirmRequest, request: Request
    ) -> ResetCompleteResponse:
        require_trusted_origin(request, get_settings(request))
        try:
            get_workflows(request).confirm_password_reset(
                email=payload.email,
                verification_code=payload.verification_code,
                new_password=payload.new_password,
                context=request_context(request, payload.device_name),
            )
        except PasswordPolicyError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="password_policy_failed",
            ) from error
        except VerificationCodeFailure as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid_verification_code",
            ) from error
        return ResetCompleteResponse()

    return router


def _invalid_refresh_response(settings: CommunitySettings) -> JSONResponse:
    response = JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": "authentication_required"},
    )
    clear_auth_cookies(response, settings)
    return response
