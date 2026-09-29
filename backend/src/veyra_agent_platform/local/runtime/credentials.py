"""Local User Runtime Provider credentials and Project/Agent bindings.

SQLite stores metadata and opaque references only. Device credential values are
resolved through ``SecretStore``; a future cloud credential store can satisfy
the same contract without changing Agent or Runtime semantics.
"""

from __future__ import annotations

import json
import re
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.secrets import SecretStore, SecretStoreError
from veyra_agent_platform.local.storage.repositories import LocalRepository

SUPPORTED_PROVIDER_TYPES = frozenset(
    {"moonshot", "openai", "anthropic", "openrouter", "openai_compatible"}
)
DEFAULT_BASE_URLS = {
    "moonshot": "https://api.moonshot.cn/v1",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "openrouter": "https://openrouter.ai/api/v1",
}
RUNTIME_BINDING_SLOT = "primary_model"
IMAGE_BINDING_SLOT = "image_model"
RUNTIME_BINDING_SLOTS = frozenset({RUNTIME_BINDING_SLOT, IMAGE_BINDING_SLOT})
_NODE_SLOT = re.compile(r"^node\.[a-z][a-z0-9_]{0,62}$")
LOCAL_PROFILE_ID = "local"
CREDENTIAL_SCOPES = frozenset({"device", "cloud"})
CredentialScope = Literal["device", "cloud"]
SecretState = Literal["available", "missing", "unavailable"]
CredentialReadiness = Literal[
    "ready", "needs_reentry", "unavailable", "disabled", "invalid", "unverified"
]


def node_binding_slot(node_id: str) -> str:
    return f"node.{node_id}"


def is_runtime_slot(slot: str) -> bool:
    return slot in RUNTIME_BINDING_SLOTS or bool(_NODE_SLOT.fullmatch(slot))


class ProviderCredentialError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProviderCredentialMetadata:
    credential_id: str
    owner_id: str
    provider_type: str
    label: str
    base_url: str
    status: str
    credential_scope: str
    masked_hint: str
    capabilities: dict[str, Any]
    default_model_id: str | None
    is_default: bool
    created_at: str
    updated_at: str
    validated_at: str | None
    last_used_at: str | None
    secret_state: SecretState
    readiness: CredentialReadiness

    def to_dict(self) -> dict[str, Any]:
        return {
            "credential_id": self.credential_id,
            "owner_id": self.owner_id,
            "provider_type": self.provider_type,
            "label": self.label,
            "base_url": self.base_url,
            "status": self.status,
            "credential_scope": self.credential_scope,
            "masked_hint": self.masked_hint,
            "capabilities": self.capabilities,
            "default_model_id": self.default_model_id,
            "is_default": self.is_default,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "validated_at": self.validated_at,
            "last_used_at": self.last_used_at,
            "secret_state": self.secret_state,
            "readiness": self.readiness,
        }


@dataclass(frozen=True)
class RuntimeBinding:
    project_id: str
    agent_id: str | None
    slot: str
    credential_id: str
    model_id: str
    source: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "agent_id": self.agent_id,
            "slot": self.slot,
            "credential_id": self.credential_id,
            "model_id": self.model_id,
            "source": self.source,
            "updated_at": self.updated_at,
        }


def provider_base_url(provider_type: str, base_url: str | None) -> str:
    normalized_provider = provider_type.strip().lower()
    value = (
        (base_url or DEFAULT_BASE_URLS.get(normalized_provider) or "")
        .strip()
        .rstrip("/")
    )
    parsed = urlsplit(value)
    if not value or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ProviderCredentialError(
            "provider_base_url_invalid",
            "Provider base URL must be an HTTP(S) API endpoint.",
        )
    if parsed.query or parsed.fragment or parsed.path.endswith("/chat/completions"):
        raise ProviderCredentialError(
            "provider_base_url_invalid",
            "Provider base URL must stop at the API version.",
        )
    return value


def provider_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in SUPPORTED_PROVIDER_TYPES:
        raise ProviderCredentialError(
            "provider_type_unsupported",
            "This Runtime Provider type is not supported by the local client.",
        )
    return normalized


def _credential_scope(value: str) -> CredentialScope:
    normalized = value.strip().lower()
    if normalized not in CREDENTIAL_SCOPES:
        raise ProviderCredentialError(
            "credential_scope_invalid", "Credential scope is invalid."
        )
    return normalized  # type: ignore[return-value]


def _readiness(status: str, secret_state: SecretState) -> CredentialReadiness:
    if status == "disabled":
        return "disabled"
    if status == "invalid":
        return "invalid"
    if secret_state == "unavailable":
        return "unavailable"
    if secret_state == "missing":
        return "needs_reentry"
    if status == "active":
        return "ready"
    return "unverified"


class ProviderCredentialStore:
    """Persist metadata and keep each credential secret in the host vault."""

    def __init__(self, repository: LocalRepository, secret_store: SecretStore) -> None:
        self.repository = repository
        self.secret_store = secret_store

    def list(self) -> list[ProviderCredentialMetadata]:
        with self.repository._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM provider_credentials WHERE owner_id = ? "
                "ORDER BY created_at DESC, credential_id DESC",
                (LOCAL_PROFILE_ID,),
            ).fetchall()
        return [self._metadata(row) for row in rows]

    def get(self, credential_id: str) -> ProviderCredentialMetadata:
        row = self._database_row(credential_id)
        return self._metadata(row)

    def secret_ref(self, credential_id: str) -> str:
        self._database_row(credential_id)
        return f"runtime.credential.{credential_id}"

    def secret(self, credential_id: str) -> str | None:
        try:
            value = self.secret_store.get(self.secret_ref(credential_id))
        except SecretStoreError as exc:
            raise ProviderCredentialError(
                "credential_store_unavailable",
                "Runtime Provider secret store is unavailable.",
            ) from exc
        return value.strip() if value else None

    def create(
        self,
        *,
        provider_type_value: str,
        label: str,
        api_key: str,
        base_url: str | None,
        default_model_id: str | None,
        make_default: bool,
        credential_scope: str = "device",
    ) -> ProviderCredentialMetadata:
        kind = provider_type(provider_type_value)
        scope = _credential_scope(credential_scope)
        if scope != "device":
            raise ProviderCredentialError(
                "credential_scope_unsupported",
                "The local Runtime API currently supports device credentials only.",
            )
        clean_label = label.strip()
        if not clean_label:
            raise ProviderCredentialError(
                "credential_label_invalid", "Credential label is required."
            )
        secret = api_key.strip()
        if not secret:
            raise ProviderCredentialError(
                "credential_secret_empty", "Credential secret is required."
            )
        endpoint = provider_base_url(kind, base_url)
        credential_id = new_uuid7()
        secret_ref = f"runtime.credential.{credential_id}"
        try:
            self.secret_store.set(secret_ref, secret)
        except SecretStoreError as exc:
            raise ProviderCredentialError(
                "credential_store_unavailable",
                "Runtime Provider secret could not be stored.",
            ) from exc
        now = _now()
        try:
            with self.repository.transaction() as connection:
                if make_default:
                    connection.execute(
                        "UPDATE provider_credentials SET is_default = 0 "
                        "WHERE owner_id = ?",
                        (LOCAL_PROFILE_ID,),
                    )
                connection.execute(
                    """INSERT INTO provider_credentials(
                        credential_id, owner_id, provider_type, label, base_url,
                        status, credential_scope, masked_hint, capabilities_json,
                        default_model_id,
                        is_default, secret_ref, created_at, updated_at,
                        validated_at, last_used_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        credential_id,
                        LOCAL_PROFILE_ID,
                        kind,
                        clean_label,
                        endpoint,
                        "unverified",
                        scope,
                        _mask(secret),
                        json.dumps({}, sort_keys=True),
                        default_model_id.strip() if default_model_id else None,
                        int(make_default),
                        secret_ref,
                        now,
                        now,
                        None,
                        None,
                    ),
                )
        except BaseException:
            with suppress(SecretStoreError):
                self.secret_store.delete(secret_ref)
            raise
        return self.get(credential_id)

    def update_metadata(
        self,
        credential_id: str,
        *,
        label: str | None = None,
        base_url: str | None = None,
        default_model_id: str | None = None,
        make_default: bool | None = None,
    ) -> ProviderCredentialMetadata:
        current = self.get(credential_id)
        next_label = current.label if label is None else label.strip()
        if not next_label:
            raise ProviderCredentialError(
                "credential_label_invalid", "Credential label is required."
            )
        next_url = (
            current.base_url
            if base_url is None
            else provider_base_url(current.provider_type, base_url)
        )
        next_default = (
            current.default_model_id
            if default_model_id is None
            else default_model_id.strip() or None
        )
        now = _now()
        with self.repository.transaction() as connection:
            if make_default:
                connection.execute(
                    "UPDATE provider_credentials SET is_default = 0 WHERE owner_id = ?",
                    (LOCAL_PROFILE_ID,),
                )
            connection.execute(
                """UPDATE provider_credentials SET label = ?, base_url = ?,
                   default_model_id = ?, is_default = COALESCE(?, is_default),
                   updated_at = ? WHERE credential_id = ? AND owner_id = ?""",
                (
                    next_label,
                    next_url,
                    next_default,
                    int(make_default) if make_default is not None else None,
                    now,
                    credential_id,
                    LOCAL_PROFILE_ID,
                ),
            )
        return self.get(credential_id)

    def replace_secret(
        self, credential_id: str, api_key: str
    ) -> ProviderCredentialMetadata:
        current = self.get(credential_id)
        secret = api_key.strip()
        if not secret:
            raise ProviderCredentialError(
                "credential_secret_empty", "Credential secret is required."
            )
        try:
            self.secret_store.set(self.secret_ref(credential_id), secret)
        except SecretStoreError as exc:
            raise ProviderCredentialError(
                "credential_store_unavailable",
                "Runtime Provider secret could not be stored.",
            ) from exc
        now = _now()
        with self.repository.transaction() as connection:
            connection.execute(
                "UPDATE provider_credentials SET masked_hint = ?, status = ?, "
                "validated_at = NULL, updated_at = ? WHERE credential_id = ?",
                (_mask(secret), "unverified", now, current.credential_id),
            )
        return self.get(credential_id)

    def set_validation(
        self,
        credential_id: str,
        *,
        status: str,
        capabilities: dict[str, Any],
        default_model_id: str | None = None,
    ) -> ProviderCredentialMetadata:
        if status not in {"unverified", "active", "invalid", "disabled"}:
            raise ProviderCredentialError(
                "credential_status_invalid", "Credential status is invalid."
            )
        now = _now()
        with self.repository.transaction() as connection:
            connection.execute(
                """UPDATE provider_credentials SET status = ?, capabilities_json = ?,
                   default_model_id = COALESCE(?, default_model_id),
                   validated_at = ?, updated_at = ?
                   WHERE credential_id = ? AND owner_id = ?""",
                (
                    status,
                    json.dumps(capabilities, ensure_ascii=False, sort_keys=True),
                    default_model_id,
                    now if status == "active" else None,
                    now,
                    credential_id,
                    LOCAL_PROFILE_ID,
                ),
            )
        return self.get(credential_id)

    def set_status(self, credential_id: str, status: str) -> ProviderCredentialMetadata:
        if status not in {"active", "disabled"}:
            raise ProviderCredentialError(
                "credential_status_invalid", "Credential status is invalid."
            )
        self.get(credential_id)
        with self.repository.transaction() as connection:
            connection.execute(
                "UPDATE provider_credentials SET status = ?, updated_at = ? "
                "WHERE credential_id = ? AND owner_id = ?",
                (status, _now(), credential_id, LOCAL_PROFILE_ID),
            )
        return self.get(credential_id)

    def mark_used(self, credential_id: str) -> None:
        self.get(credential_id)
        with self.repository.transaction() as connection:
            connection.execute(
                "UPDATE provider_credentials SET last_used_at = ?, updated_at = ? "
                "WHERE credential_id = ? AND owner_id = ?",
                (_now(), _now(), credential_id, LOCAL_PROFILE_ID),
            )

    def delete(self, credential_id: str) -> None:
        self.get(credential_id)
        secret_ref = self.secret_ref(credential_id)
        try:
            self.secret_store.delete(secret_ref)
        except SecretStoreError as exc:
            raise ProviderCredentialError(
                "credential_store_unavailable",
                "Runtime Provider secret could not be removed.",
            ) from exc
        with self.repository.transaction() as connection:
            connection.execute(
                "DELETE FROM runtime_bindings WHERE credential_id = ?", (credential_id,)
            )
            connection.execute(
                "DELETE FROM provider_credentials WHERE credential_id = ? "
                "AND owner_id = ?",
                (credential_id, LOCAL_PROFILE_ID),
            )

    def binding(
        self, project_id: str, agent_id: str | None, slot: str = RUNTIME_BINDING_SLOT
    ) -> RuntimeBinding | None:
        self._require_scope(project_id, agent_id)
        with self.repository._connect() as connection:
            row = connection.execute(
                "SELECT * FROM runtime_bindings WHERE project_id = ? AND "
                "agent_id IS ? AND binding_slot = ?",
                (project_id, agent_id, slot),
            ).fetchone()
        return self._binding_row(row, source="explicit") if row else None

    def effective_binding(
        self, project_id: str, agent_id: str, slot: str = RUNTIME_BINDING_SLOT
    ) -> RuntimeBinding | None:
        explicit = self.binding(project_id, agent_id, slot)
        if explicit is not None:
            return explicit
        if is_runtime_slot(slot) and slot not in RUNTIME_BINDING_SLOTS:
            agent = self.binding(project_id, agent_id, RUNTIME_BINDING_SLOT)
            if agent is not None:
                return agent
        agent = self.binding(project_id, agent_id, slot)
        if agent is not None:
            return agent
        project = self.binding(project_id, None, slot)
        if project is None and slot not in RUNTIME_BINDING_SLOTS:
            project = self.binding(project_id, None, RUNTIME_BINDING_SLOT)
        if project is not None:
            return RuntimeBinding(
                project_id=project.project_id,
                agent_id=project.agent_id,
                slot=project.slot,
                credential_id=project.credential_id,
                model_id=project.model_id,
                source="project",
                updated_at=project.updated_at,
            )
        return None

    def set_binding(
        self,
        project_id: str,
        agent_id: str | None,
        credential_id: str,
        model_id: str,
        slot: str = RUNTIME_BINDING_SLOT,
    ) -> RuntimeBinding:
        self._require_scope(project_id, agent_id)
        if not is_runtime_slot(slot):
            raise ProviderCredentialError(
                "runtime_slot_invalid", "Unknown Runtime model role."
            )
        credential = self.get(credential_id)
        if credential.status != "active":
            raise ProviderCredentialError(
                "credential_not_active",
                "Only an active Runtime credential can be bound.",
            )
        model = model_id.strip()
        if not model:
            raise ProviderCredentialError(
                "runtime_model_required", "Runtime model is required."
            )
        models = credential.capabilities.get("models")
        # Providers often omit image models from /models, so only the chat
        # slot is checked against the validated model list.
        if (
            slot == RUNTIME_BINDING_SLOT
            and isinstance(models, list)
            and models
            and model not in models
        ):
            raise ProviderCredentialError(
                "runtime_model_unavailable",
                "The selected model is not available for this credential.",
            )
        now = _now()
        scope_id = f"{project_id}:{agent_id or '*'}:{slot}"
        with self.repository.transaction() as connection:
            connection.execute(
                """INSERT INTO runtime_bindings(
                    scope_id, project_id, agent_id, binding_slot, credential_id,
                    model_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope_id) DO UPDATE SET
                    credential_id = excluded.credential_id,
                    model_id = excluded.model_id, updated_at = excluded.updated_at""",
                (scope_id, project_id, agent_id, slot, credential_id, model, now, now),
            )
        return self.binding(project_id, agent_id, slot)  # type: ignore[return-value]

    def clear_binding(
        self, project_id: str, agent_id: str | None, slot: str = RUNTIME_BINDING_SLOT
    ) -> None:
        self._require_scope(project_id, agent_id)
        scope_id = f"{project_id}:{agent_id or '*'}:{slot}"
        with self.repository.transaction() as connection:
            connection.execute(
                "DELETE FROM runtime_bindings WHERE scope_id = ?", (scope_id,)
            )

    def effective_credential(
        self, project_id: str, agent_id: str, slot: str = RUNTIME_BINDING_SLOT
    ) -> tuple[ProviderCredentialMetadata, RuntimeBinding] | None:
        binding = self.effective_binding(project_id, agent_id, slot)
        if binding is not None:
            credential = self.get(binding.credential_id)
            if credential.status == "active" and credential.readiness == "ready":
                return credential, binding
            return None
        if slot != RUNTIME_BINDING_SLOT and not slot.startswith("node."):
            # The account default names a chat model; other roles such as
            # image generation need their own explicit binding.
            return None
        with self.repository._connect() as connection:
            row = connection.execute(
                "SELECT * FROM provider_credentials WHERE owner_id = ? "
                "AND is_default = 1 AND status = 'active' LIMIT 1",
                (LOCAL_PROFILE_ID,),
            ).fetchone()
        if row is None:
            return None
        credential = self._metadata(row)
        model_id = credential.default_model_id or str(
            (credential.capabilities.get("models") or [""])[0]
        )
        if not model_id:
            return None
        if credential.readiness != "ready":
            return None
        return credential, RuntimeBinding(
            project_id=project_id,
            agent_id=None,
            slot=slot,
            credential_id=credential.credential_id,
            model_id=model_id,
            source="user_default",
            updated_at=credential.updated_at,
        )

    def _database_row(self, credential_id: str) -> Any:
        with self.repository._connect() as connection:
            row = connection.execute(
                "SELECT * FROM provider_credentials WHERE credential_id = ? "
                "AND owner_id = ?",
                (credential_id, LOCAL_PROFILE_ID),
            ).fetchone()
        if row is None:
            raise ProviderCredentialError(
                "credential_not_found", "Runtime Provider credential was not found."
            )
        return row

    def _secret_state(self, credential_id: str) -> SecretState:
        try:
            value = self.secret_store.get(self.secret_ref(credential_id))
        except SecretStoreError:
            return "unavailable"
        return "available" if value and value.strip() else "missing"

    def _metadata(self, row: Any) -> ProviderCredentialMetadata:
        metadata = self._row(row)
        secret_state = self._secret_state(metadata.credential_id)
        return replace(
            metadata,
            secret_state=secret_state,
            readiness=_readiness(metadata.status, secret_state),
        )

    def _require_scope(self, project_id: str, agent_id: str | None) -> None:
        if self.repository.project(project_id) is None:
            raise ProviderCredentialError(
                "runtime_project_not_found", "Project was not found."
            )
        if agent_id is not None:
            row = self.repository.agent(agent_id)
            if row is None or row["project_id"] != project_id:
                raise ProviderCredentialError(
                    "runtime_agent_not_found", "Agent was not found in this Project."
                )

    @staticmethod
    def _row(row: Any) -> ProviderCredentialMetadata:
        try:
            capabilities = json.loads(row["capabilities_json"])
        except (TypeError, json.JSONDecodeError):
            capabilities = {}
        return ProviderCredentialMetadata(
            credential_id=row["credential_id"],
            owner_id=row["owner_id"],
            provider_type=row["provider_type"],
            label=row["label"],
            base_url=row["base_url"],
            status=row["status"],
            credential_scope=row["credential_scope"],
            masked_hint=row["masked_hint"],
            capabilities=capabilities if isinstance(capabilities, dict) else {},
            default_model_id=row["default_model_id"],
            is_default=bool(row["is_default"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            validated_at=row["validated_at"],
            last_used_at=row["last_used_at"],
            secret_state="unavailable",
            readiness="unavailable",
        )

    @staticmethod
    def _binding_row(row: Any, *, source: str) -> RuntimeBinding:
        return RuntimeBinding(
            project_id=row["project_id"],
            agent_id=row["agent_id"],
            slot=row["binding_slot"],
            credential_id=row["credential_id"],
            model_id=row["model_id"],
            source=source,
            updated_at=row["updated_at"],
        )


class ProviderCredentialService:
    """Credential mutations plus explicit, no-generation validation."""

    def __init__(
        self,
        store: ProviderCredentialStore,
        runtime_settings: Any,
        transport: Any = None,
    ) -> None:
        self.store = store
        self.runtime_settings = runtime_settings
        self.transport = transport

    def validate(self, credential_id: str) -> dict[str, Any]:
        credential = self.store.get(credential_id)
        try:
            client = self._client(credential)
            models = client.list_models()
        except Exception as exc:
            code = getattr(exc, "code", "runtime_provider_error")
            updated = self.store.set_validation(
                credential_id,
                status="invalid",
                capabilities={"models": []},
            )
            return {
                "valid": False,
                "code": str(code),
                "message": str(exc),
                "credential": updated.to_dict(),
            }
        model_ids = [item for item in models if isinstance(item, str) and item]
        default_model = credential.default_model_id
        if default_model and model_ids and default_model not in model_ids:
            default_model = model_ids[0]
        if default_model is None and model_ids:
            default_model = model_ids[0]
        updated = self.store.set_validation(
            credential_id,
            status="active",
            capabilities={"models": model_ids, "validated_without_generation": True},
            default_model_id=default_model,
        )
        return {
            "valid": True,
            "code": "validated",
            "message": "Runtime Provider credentials were verified without generation.",
            "credential": updated.to_dict(),
        }

    def create_and_validate(self, **kwargs: Any) -> dict[str, Any]:
        credential = self.store.create(**kwargs)
        return self.validate(credential.credential_id)

    def replace_and_validate(self, credential_id: str, api_key: str) -> dict[str, Any]:
        self.store.replace_secret(credential_id, api_key)
        return self.validate(credential_id)

    def _client(self, credential: ProviderCredentialMetadata) -> Any:
        from .client import RuntimeModelClient

        settings = self.runtime_settings.model_copy(
            update={
                "provider_type": credential.provider_type,
                "model_base_url": credential.base_url,
                "model_id": credential.default_model_id
                or self.runtime_settings.model_id,
                "allow_process_environment_key": False,
            }
        )
        return RuntimeModelClient(
            settings,
            self.transport,
            secret_store=self.store.secret_store,
            secret_ref=self.store.secret_ref(credential.credential_id),
        )


def _mask(secret: str) -> str:
    return f"••••{secret[-4:]}" if len(secret) >= 4 else "••••"


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
