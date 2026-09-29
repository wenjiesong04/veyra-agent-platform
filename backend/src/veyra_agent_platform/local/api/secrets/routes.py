"""HTTP boundary for host-side secret status and updates."""

from __future__ import annotations

import os
from typing import Any, cast

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from veyra_agent_platform.local.api.projects import TypedApiError
from veyra_agent_platform.local.secrets import (
    SecretStore,
    SecretStoreError,
    known_secret_refs,
    secret_environment_name,
)


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SetSecretRequest(_ClosedModel):
    value: str = Field(min_length=1, max_length=16_384)


_PLATFORM_SECRET_REFS = {"model.primary"}


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/secrets", tags=["secrets"])

    @router.get("")
    def list_secrets(request: Request) -> dict[str, Any]:
        store = _store(request)
        return {
            "schema_version": "1.0",
            "secrets": [
                _status(store, secret_ref)
                for secret_ref in known_secret_refs()
                if secret_ref not in _PLATFORM_SECRET_REFS
            ],
        }

    @router.get("/{secret_ref}")
    def secret_status(secret_ref: str, request: Request) -> dict[str, Any]:
        if secret_ref in _PLATFORM_SECRET_REFS:
            raise TypedApiError(
                403,
                "platform_credential_forbidden",
                "Platform Provider credentials are not exposed through the local user "
                "API.",
            )
        return {"schema_version": "1.0", **_status(_store(request), secret_ref)}

    @router.put("/{secret_ref}")
    def set_secret(
        secret_ref: str, payload: SetSecretRequest, request: Request
    ) -> dict[str, Any]:
        if secret_ref in _PLATFORM_SECRET_REFS:
            raise TypedApiError(
                403,
                "platform_credential_forbidden",
                "Platform Provider credentials are not editable through the local user "
                "API.",
            )
        try:
            _store(request).set(secret_ref, payload.value)
        except SecretStoreError as exc:
            raise TypedApiError(422, "secret_store_failed", str(exc)) from exc
        return {"schema_version": "1.0", **_status(_store(request), secret_ref)}

    @router.delete("/{secret_ref}")
    def delete_secret(secret_ref: str, request: Request) -> dict[str, Any]:
        if secret_ref in _PLATFORM_SECRET_REFS:
            raise TypedApiError(
                403,
                "platform_credential_forbidden",
                "Platform Provider credentials are not editable through the local user "
                "API.",
            )
        try:
            _store(request).delete(secret_ref)
        except SecretStoreError as exc:
            raise TypedApiError(422, "secret_store_failed", str(exc)) from exc
        return {"schema_version": "1.0", **_status(_store(request), secret_ref)}

    return router


def _store(request: Request) -> SecretStore:
    return cast(SecretStore, request.app.state.secrets)


def _status(store: SecretStore, secret_ref: str) -> dict[str, Any]:
    try:
        keychain_value = store.get(secret_ref)
    except SecretStoreError:
        keychain_value = None
    env_name = secret_environment_name(secret_ref)
    if keychain_value:
        source = "keychain"
    else:
        source = "environment" if os.environ.get(env_name, "").strip() else "missing"
    return {
        "secret_ref": secret_ref,
        "env_name": env_name,
        "configured": source != "missing",
        "source": source,
    }
