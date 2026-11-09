"""Local-only User Runtime Provider credential and binding endpoints."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, TypeVar, cast

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from veyra_agent_platform.local.api.projects import TypedApiError
from veyra_agent_platform.local.models.contracts import CAPABILITY_NAME_SET
from veyra_agent_platform.local.models.registry import ModelRegistry, ModelRegistryError
from veyra_agent_platform.local.runtime.credentials import (
    RUNTIME_BINDING_SLOT,
    ProviderCredentialError,
    ProviderCredentialMetadata,
    ProviderCredentialService,
    ProviderCredentialStore,
)

_Result = TypeVar("_Result")


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateCredentialRequest(_ClosedModel):
    provider_type: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    api_key: str = Field(min_length=1, max_length=16_384)
    base_url: str | None = Field(default=None, max_length=500)
    default_model_id: str | None = Field(default=None, max_length=128)
    make_default: bool = False
    credential_scope: Literal["device", "cloud"] = "device"


class UpdateCredentialRequest(_ClosedModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: str | None = Field(default=None, max_length=500)
    default_model_id: str | None = Field(default=None, max_length=128)
    make_default: bool | None = None


class ReplaceCredentialSecretRequest(_ClosedModel):
    api_key: str = Field(min_length=1, max_length=16_384)


class ManualModelRequest(_ClosedModel):
    provider_model_id: str = Field(min_length=1, max_length=512)
    display_name: str | None = Field(default=None, max_length=200)


class ModelRoleDefaultRequest(_ClosedModel):
    model_profile_id: str = Field(min_length=1, max_length=64)


class ProbeModelCapabilityRequest(_ClosedModel):
    capability: str = Field(min_length=1, max_length=64)
    acknowledge_cost: bool = False

    @field_validator("capability")
    @classmethod
    def validate_capability(cls, value: str) -> str:
        if value not in CAPABILITY_NAME_SET:
            raise ValueError("Unknown Model capability.")
        return value


class RuntimeBindingRequest(_ClosedModel):
    credential_id: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=128)
    slot: str = Field(default=RUNTIME_BINDING_SLOT, min_length=1, max_length=64)


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["runtime-credentials"])

    @router.get("/runtime-credentials")
    def list_credentials(request: Request) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "credentials": [_metadata(item) for item in _store(request).list()],
        }

    @router.get("/runtime-models")
    def list_runtime_models(request: Request) -> dict[str, Any]:
        registry = _registry(request)
        return {
            "schema_version": "1.0",
            "models": [item.to_dict() for item in registry.list_profiles()],
        }

    @router.get("/runtime-models/defaults")
    def list_model_defaults(request: Request) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "defaults": [item.to_dict() for item in _registry(request).list_defaults()],
        }

    @router.put("/runtime-models/defaults/{role}")
    def set_model_default(
        role: str, payload: ModelRoleDefaultRequest, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: {
                "schema_version": "1.0",
                "default": _registry(request)
                .set_default(role, payload.model_profile_id)
                .to_dict(),
            }
        )

    @router.delete("/runtime-models/defaults/{role}")
    def clear_model_default(role: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _clear_model_default(_registry(request), role))

    @router.get("/runtime-models/{model_profile_id}")
    def get_runtime_model(model_profile_id: str, request: Request) -> dict[str, Any]:
        return _translate(
            lambda: {
                "schema_version": "1.0",
                "model": _registry(request).get_profile(model_profile_id).to_dict(),
            }
        )

    @router.post("/runtime-models/{model_profile_id}/capabilities/probe")
    def probe_runtime_model_capability(
        model_profile_id: str,
        payload: ProbeModelCapabilityRequest,
        request: Request,
    ) -> dict[str, Any]:
        return _translate(
            lambda: {
                "schema_version": "1.0",
                "model": _credential_service(request)
                .probe_capability(
                    model_profile_id,
                    payload.capability,
                    acknowledge_cost=payload.acknowledge_cost,
                )
                .to_dict(),
            }
        )

    @router.post("/runtime-credentials", status_code=201)
    def create_credential(
        payload: CreateCredentialRequest, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _credential_service(request).create_and_validate(
                provider_type_value=payload.provider_type,
                label=payload.label,
                api_key=payload.api_key,
                base_url=payload.base_url,
                default_model_id=payload.default_model_id,
                make_default=payload.make_default,
                credential_scope=payload.credential_scope,
            )
        )

    @router.patch("/runtime-credentials/{credential_id}")
    def update_credential(
        credential_id: str, payload: UpdateCredentialRequest, request: Request
    ) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            credential = _store(request).update_metadata(
                credential_id,
                label=payload.label,
                base_url=payload.base_url,
                default_model_id=payload.default_model_id,
                make_default=payload.make_default,
            )
            if payload.make_default is True or (
                payload.default_model_id is not None and credential.is_default
            ):
                _credential_service(request).sync_primary_default(credential_id)
            return {"schema_version": "1.0", "credential": _metadata(credential)}

        return _translate(operation)

    @router.post("/runtime-credentials/{credential_id}/validate")
    def validate_credential(credential_id: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _credential_service(request).validate(credential_id))

    @router.post("/runtime-credentials/{credential_id}/models/discover")
    def discover_runtime_models(credential_id: str, request: Request) -> dict[str, Any]:
        return _translate(
            lambda: _credential_service(request).discover_models(credential_id)
        )

    @router.post("/runtime-credentials/{credential_id}/models")
    def add_manual_runtime_model(
        credential_id: str, payload: ManualModelRequest, request: Request
    ) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            profile = _registry(request).add_manual_model(
                credential_id,
                payload.provider_model_id,
                display_name=payload.display_name,
            )
            credential = _store(request).get(credential_id)
            if (
                credential.is_default
                and credential.default_model_id == payload.provider_model_id
            ):
                _credential_service(request).sync_primary_default(credential_id)
                profile = _registry(request).get_profile(profile.model_profile_id)
            return {"schema_version": "1.0", "model": profile.to_dict()}

        return _translate(operation)

    @router.post("/runtime-credentials/{credential_id}/replace-secret")
    def replace_secret(
        credential_id: str,
        payload: ReplaceCredentialSecretRequest,
        request: Request,
    ) -> dict[str, Any]:
        return _translate(
            lambda: _credential_service(request).replace_and_validate(
                credential_id, payload.api_key
            )
        )

    @router.post("/runtime-credentials/{credential_id}/enable")
    def enable_credential(credential_id: str, request: Request) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            store = _store(request)
            if store.get(credential_id).status == "disabled":
                # Explicitly enabling resumes setup even when /models is absent.
                # The connection stays unverified until discovery or a requested
                # capability probe succeeds; enabling alone never makes it ready.
                store.set_validation(credential_id, status="unverified")
            return _credential_service(request).validate(credential_id)

        return _translate(operation)

    @router.post("/runtime-credentials/{credential_id}/disable")
    def disable_credential(credential_id: str, request: Request) -> dict[str, Any]:
        return _translate(
            lambda: {
                "schema_version": "1.0",
                "credential": _metadata(
                    _store(request).set_status(credential_id, "disabled")
                ),
            }
        )

    @router.delete("/runtime-credentials/{credential_id}")
    def delete_credential(credential_id: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _delete_response(_store(request), credential_id))

    @router.get("/projects/{project_id}/runtime-binding")
    def get_project_binding(project_id: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _binding_response(_store(request), project_id, None))

    @router.patch("/projects/{project_id}/runtime-binding")
    def set_project_binding(
        project_id: str, payload: RuntimeBindingRequest, request: Request
    ) -> dict[str, Any]:
        return _translate(lambda: _set_binding(request, project_id, None, payload))

    @router.delete("/projects/{project_id}/runtime-binding")
    def clear_project_binding(project_id: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _clear_binding(_store(request), project_id, None))

    @router.get("/projects/{project_id}/agents/{agent_id}/runtime-binding")
    def get_agent_binding(
        project_id: str,
        agent_id: str,
        request: Request,
        slot: str = Query(default=RUNTIME_BINDING_SLOT, min_length=1, max_length=64),
    ) -> dict[str, Any]:
        return _translate(
            lambda: _binding_response(_store(request), project_id, agent_id, slot)
        )

    @router.patch("/projects/{project_id}/agents/{agent_id}/runtime-binding")
    def set_agent_binding(
        project_id: str,
        agent_id: str,
        payload: RuntimeBindingRequest,
        request: Request,
    ) -> dict[str, Any]:
        return _translate(lambda: _set_binding(request, project_id, agent_id, payload))

    @router.delete("/projects/{project_id}/agents/{agent_id}/runtime-binding")
    def clear_agent_binding(
        project_id: str, agent_id: str, request: Request
    ) -> dict[str, Any]:
        return _translate(lambda: _clear_binding(_store(request), project_id, agent_id))

    return router


def _store(request: Request) -> ProviderCredentialStore:
    return cast(ProviderCredentialStore, request.app.state.provider_credentials)


def _registry(request: Request) -> ModelRegistry:
    return cast(ModelRegistry, request.app.state.model_registry)


def _credential_service(request: Request) -> ProviderCredentialService:
    return cast(
        ProviderCredentialService, request.app.state.provider_credential_service
    )


def _translate(operation: Callable[[], _Result]) -> _Result:
    try:
        return operation()
    except ProviderCredentialError as exc:
        status = 404 if exc.code == "credential_not_found" else 422
        raise TypedApiError(status, exc.code, str(exc)) from exc
    except ModelRegistryError as exc:
        status = (
            404
            if exc.code in {"model_profile_not_found", "provider_connection_not_found"}
            else 409
            if exc.code in {"model_profile_stale", "model_connection_endpoint_changed"}
            else 422
        )
        raise TypedApiError(status, exc.code, str(exc)) from exc


def _metadata(value: ProviderCredentialMetadata) -> dict[str, Any]:
    return {"schema_version": "1.0", **value.to_dict()}


def _binding_response(
    store: ProviderCredentialStore,
    project_id: str,
    agent_id: str | None,
    slot: str = RUNTIME_BINDING_SLOT,
) -> dict[str, Any]:
    explicit = store.binding(project_id, agent_id, slot)
    effective = (
        store.effective_credential(project_id, agent_id or "", slot)
        if agent_id is not None
        else None
    )
    if agent_id is None:
        project = store.binding(project_id, None, slot)
        effective_binding = project
        effective_credential = store.get(project.credential_id) if project else None
    else:
        effective_binding = store.effective_binding(project_id, agent_id, slot)
        effective_credential = effective[0] if effective else None
    return {
        "schema_version": "1.0",
        "project_id": project_id,
        "agent_id": agent_id,
        "slot": slot,
        "binding": effective_binding.to_dict() if effective_binding else None,
        "credential": _metadata(effective_credential) if effective_credential else None,
        "explicit": explicit.to_dict() if explicit else None,
    }


def _set_binding(
    request: Request,
    project_id: str,
    agent_id: str | None,
    payload: RuntimeBindingRequest,
) -> dict[str, Any]:
    store = _store(request)
    binding = store.set_binding(
        project_id,
        agent_id,
        payload.credential_id,
        payload.model_id,
        payload.slot,
    )
    return _binding_response(store, project_id, agent_id, payload.slot) | {
        "binding": binding.to_dict()
    }


def _clear_binding(
    store: ProviderCredentialStore, project_id: str, agent_id: str | None
) -> dict[str, Any]:
    store.clear_binding(project_id, agent_id)
    return _binding_response(store, project_id, agent_id)


def _delete_response(
    store: ProviderCredentialStore, credential_id: str
) -> dict[str, Any]:
    store.delete(credential_id)
    return {"schema_version": "1.0", "credential_id": credential_id, "deleted": True}


def _clear_model_default(registry: ModelRegistry, role: str) -> dict[str, Any]:
    registry.clear_default(role)
    return {
        "schema_version": "1.0",
        "role": role,
        "deleted": True,
        "defaults": [item.to_dict() for item in registry.list_defaults()],
    }
