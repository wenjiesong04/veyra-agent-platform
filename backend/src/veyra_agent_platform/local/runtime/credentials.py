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
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.secrets import SecretStore, SecretStoreError
from veyra_agent_platform.local.storage.repositories import LocalRepository

if TYPE_CHECKING:
    from veyra_agent_platform.local.models.contracts import (
        ModelProfile,
    )
    from veyra_agent_platform.local.models.registry import ModelRegistry

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
    discovery_state: str
    discovery_checked_at: str | None
    discovered_at: str | None
    discovery_error_code: str | None
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
            "discovery_state": self.discovery_state,
            "discovery_checked_at": self.discovery_checked_at,
            "discovered_at": self.discovered_at,
            "discovery_error_code": self.discovery_error_code,
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
    host = (parsed.hostname or "").lower()
    if (
        host.endswith((".console.aliyun.com", ".console.alibabacloud.com"))
        or host
        in {
            "platform.openai.com",
            "platform.deepseek.com",
            "platform.moonshot.cn",
            "platform.moonshot.ai",
            "aistudio.google.com",
            "console.anthropic.com",
            "console.deepseek.com",
            "console.volcengine.com",
            "cloud.siliconflow.cn",
            "chat.openai.com",
            "chatgpt.com",
            "claude.ai",
        }
        or (
            host == "openrouter.ai"
            and parsed.path.startswith(("/settings", "/keys", "/auth", "/login"))
        )
    ):
        raise ProviderCredentialError(
            "provider_console_url",
            "This is a service website, not an API address. Choose the service "
            "preset or copy its API address from the provider documentation.",
        )
    if (
        parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or parsed.path.endswith("/chat/completions")
    ):
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
        endpoint_changed = next_url != current.base_url
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
                   status = CASE WHEN ? THEN 'unverified' ELSE status END,
                   validated_at = CASE WHEN ? THEN NULL ELSE validated_at END,
                   model_discovery_state = CASE WHEN ? THEN 'stale'
                     ELSE model_discovery_state END,
                   model_discovery_checked_at = CASE WHEN ? THEN ?
                     ELSE model_discovery_checked_at END,
                   model_discovery_error_code = CASE WHEN ?
                     THEN 'provider_endpoint_changed'
                     ELSE model_discovery_error_code END,
                   updated_at = ? WHERE credential_id = ? AND owner_id = ?""",
                (
                    next_label,
                    next_url,
                    next_default,
                    int(make_default) if make_default is not None else None,
                    int(endpoint_changed),
                    int(endpoint_changed),
                    int(endpoint_changed),
                    int(endpoint_changed),
                    now,
                    int(endpoint_changed),
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
                "validated_at = NULL, model_discovery_state = 'stale', "
                "model_discovery_checked_at = ?, "
                "model_discovery_error_code = 'credential_replaced', updated_at = ? "
                "WHERE credential_id = ?",
                (_mask(secret), "unverified", now, now, current.credential_id),
            )
        return self.get(credential_id)

    def set_validation(
        self,
        credential_id: str,
        *,
        status: str,
        capabilities: dict[str, Any] | None = None,
        default_model_id: str | None = None,
    ) -> ProviderCredentialMetadata:
        if status not in {"unverified", "active", "invalid", "disabled"}:
            raise ProviderCredentialError(
                "credential_status_invalid", "Credential status is invalid."
            )
        now = _now()
        with self.repository.transaction() as connection:
            connection.execute(
                """UPDATE provider_credentials SET status = ?,
                   capabilities_json = COALESCE(?, capabilities_json),
                   default_model_id = COALESCE(?, default_model_id),
                   validated_at = ?, updated_at = ?
                   WHERE credential_id = ? AND owner_id = ?""",
                (
                    status,
                    json.dumps(capabilities, ensure_ascii=False, sort_keys=True)
                    if capabilities is not None
                    else None,
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
        updated_at = _now()
        with self.repository.transaction() as connection:
            connection.execute(
                "UPDATE provider_credentials SET status = ?, "
                "model_discovery_state = CASE WHEN ? = 'disabled' THEN 'stale' "
                "ELSE model_discovery_state END, "
                "model_discovery_checked_at = CASE WHEN ? = 'disabled' THEN ? "
                "ELSE model_discovery_checked_at END, updated_at = ? "
                "WHERE credential_id = ? AND owner_id = ?",
                (
                    status,
                    status,
                    status,
                    updated_at,
                    updated_at,
                    credential_id,
                    LOCAL_PROFILE_ID,
                ),
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

    def bindings(
        self, project_id: str, *, agent_id: str | None = None
    ) -> tuple[RuntimeBinding, ...]:
        """Return safe binding metadata for Registry-backed Builder resolution."""
        self._require_scope(project_id, agent_id)
        with self.repository._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM runtime_bindings WHERE project_id = ? "
                "AND (? IS NULL OR agent_id = ?) ORDER BY agent_id, binding_slot",
                (project_id, agent_id, agent_id),
            ).fetchall()
        return tuple(self._binding_row(row, source="explicit") for row in rows)

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
        with self.repository._connect() as connection:
            registered = connection.execute(
                "SELECT 1 FROM model_profiles WHERE provider_connection_id = ? "
                "AND provider_model_id = ? AND enabled = 1 LIMIT 1",
                (credential_id, model),
            ).fetchone()
        if registered is None:
            raise ProviderCredentialError(
                "runtime_model_unavailable",
                "Add or discover this Provider Model before binding it.",
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
            discovery_state=row["model_discovery_state"],
            discovery_checked_at=row["model_discovery_checked_at"],
            discovered_at=row["model_discovered_at"],
            discovery_error_code=row["model_discovery_error_code"],
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
        model_registry: ModelRegistry | None = None,
    ) -> None:
        self.store = store
        self.runtime_settings = runtime_settings
        self.transport = transport
        self.model_registry = model_registry

    def validate(self, credential_id: str) -> dict[str, Any]:
        credential = self.store.get(credential_id)
        try:
            client = self._client(credential)
            models = client.discover_models()
        except Exception as exc:
            code = getattr(exc, "code", "runtime_provider_error")
            code = _safe_error_code(code)
            if code == "runtime_request_invalid":
                # This path only asks the Provider for its model list. A rejected
                # listing endpoint can be handled with an explicit manual ID and
                # capability probe; it does not by itself invalidate the key.
                code = "runtime_model_discovery_unavailable"
            permanent_failure = code == "runtime_unauthorized"
            updated = self.store.set_validation(
                credential_id,
                status="invalid" if permanent_failure else credential.status,
                capabilities=None,
            )
            failure_profiles: tuple[ModelProfile, ...] = ()
            discovery_state = "stale" if permanent_failure else "failed"
            if self.model_registry is not None:
                failure_profiles = self.model_registry.mark_discovery_failure(
                    credential_id,
                    error_code=code,
                    state=discovery_state,
                )
                updated = self.store.get(credential_id)
            return {
                "schema_version": "1.0",
                "valid": False,
                "code": code,
                "message": _safe_provider_message(code),
                "credential": updated.to_dict(),
                "discovery": {
                    "state": discovery_state,
                    "discovered_at": updated.discovered_at,
                    "models_found": len(failure_profiles),
                    "error_code": code,
                },
                "models": [item.to_dict() for item in failure_profiles],
            }
        descriptors = tuple(models)
        model_ids = [item.provider_model_id for item in descriptors]
        default_model = credential.default_model_id
        default_missing = bool(default_model and default_model not in model_ids)
        if default_model is None and model_ids:
            default_model = model_ids[0]
        updated = self.store.set_validation(
            credential_id,
            status="active",
            capabilities={"models": model_ids, "validated_without_generation": True},
            default_model_id=default_model,
        )
        profiles: tuple[ModelProfile, ...] = ()
        if self.model_registry is not None:
            profiles = self.model_registry.sync_discovery(
                credential_id,
                descriptors,
            )
            updated = self.store.get(credential_id)
        return {
            "schema_version": "1.0",
            "valid": True,
            "code": "default_model_unavailable" if default_missing else "validated",
            "message": (
                "Provider credentials were verified, but the saved default model ID "
                "was not listed. It was preserved; add it manually or choose "
                "another model."
                if default_missing
                else "Runtime Provider credentials were verified without generation."
            ),
            "model_selection": {
                "provider_model_id": default_model,
                "state": (
                    "needs_setup"
                    if default_missing
                    else "ready"
                    if default_model
                    else "unconfigured"
                ),
            },
            "credential": updated.to_dict(),
            "discovery": {
                "state": "ready",
                "discovered_at": updated.discovered_at,
                "models_found": len(model_ids),
            },
            "models": [item.to_dict() for item in profiles],
        }

    def discover_models(self, credential_id: str) -> dict[str, Any]:
        """Explicitly revalidate the connection and refresh its passive model list."""
        return self.validate(credential_id)

    def create_and_validate(self, **kwargs: Any) -> dict[str, Any]:
        credential = self.store.create(**kwargs)
        result = self.validate(credential.credential_id)
        if kwargs.get("make_default") and result.get("valid") is True:
            self.sync_primary_default(credential.credential_id)
        return result

    def sync_primary_default(self, credential_id: str) -> None:
        """Project the legacy account-default selection into the role registry."""
        if self.model_registry is None:
            return
        credential = self.store.get(credential_id)
        if not credential.is_default or not credential.default_model_id:
            return
        profile = next(
            (
                item
                for item in self.model_registry.list_profiles_for_connection(
                    credential_id
                )
                if item.provider_model_id == credential.default_model_id
                and item.registry_ready
            ),
            None,
        )
        if profile is not None:
            self.model_registry.set_default("primary", profile.model_profile_id)

    def replace_and_validate(self, credential_id: str, api_key: str) -> dict[str, Any]:
        self.store.replace_secret(credential_id, api_key)
        if self.model_registry is not None:
            self.model_registry.invalidate_connection(
                credential_id, reason="credential_replaced"
            )
        return self.validate(credential_id)

    def probe_capability(
        self,
        model_profile_id: str,
        capability: str,
        *,
        acknowledge_cost: bool = False,
    ) -> ModelProfile:
        """Run only an explicitly requested bounded probe; never persist output."""
        from veyra_agent_platform.local.models.contracts import (
            CapabilityEvidenceSource,
            CapabilityStatus,
        )
        from veyra_agent_platform.local.runtime.client import RuntimeProviderError

        if self.model_registry is None:
            raise ProviderCredentialError(
                "capability_probe_unavailable",
                "Model capability verification is not configured on this host.",
            )
        if capability in {"image_input", "image_generation"} and not acknowledge_cost:
            raise ProviderCredentialError(
                "capability_probe_cost_confirmation_required",
                "Image capability verification makes a real model request and may "
                "incur Provider charges.",
            )
        if capability not in {
            "text_generation",
            "image_input",
            "image_generation",
            "structured_output",
        }:
            raise ProviderCredentialError(
                "capability_probe_unavailable",
                "No active probe is available for this capability yet.",
            )
        profile = self.model_registry.get_profile(model_profile_id)
        credential = self.store.get(profile.provider_connection_id)
        if credential.status == "disabled":
            raise ProviderCredentialError(
                "model_connection_disabled", "The Provider connection is disabled."
            )
        if credential.secret_state != "available":
            raise ProviderCredentialError(
                "model_connection_not_ready",
                "Re-enter the Provider credential before verifying this Model.",
            )
        # A new explicit probe verifies this model against the current address.
        # Runtime resolution still refuses stale evidence until that succeeds.
        if not profile.enabled:
            raise ProviderCredentialError(
                "model_profile_disabled", "The Model Profile is disabled."
            )

        try:
            client = self._client(
                credential, model_id=profile.provider_model_id, probe=True
            )
            if capability == "text_generation":
                client.probe_text_generation()
            elif capability == "structured_output":
                client.probe_structured_output()
            elif capability == "image_input":
                client.probe_image_input()
            else:
                # The one generated image is inspected in memory and discarded.
                # It is never written to a Project, Run, event, or API response.
                generated = client.generate_images(
                    "Create a simple monochrome square with a centered dot.",
                    count=1,
                )
                if not generated:
                    raise RuntimeProviderError(
                        "runtime_invalid_response",
                        "Image generation returned no image.",
                    )
                del generated
            if (
                self.store.get(profile.provider_connection_id).base_url
                != credential.base_url
            ):
                raise ProviderCredentialError(
                    "model_connection_endpoint_changed",
                    "The service address changed during verification. Try again.",
                )
        except RuntimeProviderError as exc:
            code = _safe_error_code(exc.code)
            if code == "runtime_unauthorized":
                self.store.set_validation(
                    profile.provider_connection_id,
                    status="invalid",
                    capabilities=None,
                )
                if self.model_registry is not None:
                    self.model_registry.mark_discovery_failure(
                        profile.provider_connection_id,
                        error_code=code,
                        state="stale",
                    )
            if (
                capability == "image_generation"
                and code == "image_generation_unsupported"
            ):
                self.store.set_validation(
                    profile.provider_connection_id,
                    status="active"
                    if credential.status == "active"
                    else credential.status,
                    capabilities=None,
                )
                return self.model_registry.record_capability_probe(
                    model_profile_id,
                    capability,
                    CapabilityStatus.UNSUPPORTED,
                    source=CapabilityEvidenceSource.PROVIDER_ADAPTER,
                    detail=(
                        "The configured Provider adapter does not expose image "
                        "generation."
                    ),
                )
            self.model_registry.record_probe_failure(model_profile_id, code)
            raise ProviderCredentialError(code, _safe_provider_message(code)) from exc
        except Exception as exc:
            code = _safe_error_code(getattr(exc, "code", "runtime_provider_error"))
            self.model_registry.record_probe_failure(model_profile_id, code)
            raise ProviderCredentialError(code, _safe_provider_message(code)) from exc

        self.store.set_validation(
            profile.provider_connection_id,
            status="active",
            capabilities=None,
        )
        verified = self.model_registry.record_capability_probe(
            model_profile_id,
            capability,
            CapabilityStatus.SUPPORTED,
            source=CapabilityEvidenceSource.ACTIVE_PROBE,
            detail="An explicit local capability probe completed successfully.",
        )
        self.sync_primary_default(profile.provider_connection_id)
        return verified

    def _client(
        self,
        credential: ProviderCredentialMetadata,
        *,
        model_id: str | None = None,
        probe: bool = False,
    ) -> Any:
        from .client import RuntimeModelClient

        update: dict[str, Any] = {
            "provider_type": credential.provider_type,
            "model_base_url": provider_base_url(
                credential.provider_type, credential.base_url
            ),
            "model_id": model_id
            or credential.default_model_id
            or self.runtime_settings.model_id,
            "allow_process_environment_key": False,
        }
        if probe:
            update.update(
                {
                    "max_completion_tokens": 256,
                    "reasoning_effort": "low",
                    "timeout_seconds": min(self.runtime_settings.timeout_seconds, 30.0),
                }
            )
        settings = self.runtime_settings.model_copy(update=update)
        return RuntimeModelClient(
            settings,
            self.transport,
            secret_store=self.store.secret_store,
            secret_ref=self.store.secret_ref(credential.credential_id),
        )


def _mask(secret: str) -> str:
    return f"••••{secret[-4:]}" if len(secret) >= 4 else "••••"


def _safe_error_code(value: Any) -> str:
    if not isinstance(value, str):
        return "runtime_provider_error"
    normalized = value.strip().lower()
    return (
        normalized
        if re.fullmatch(r"[a-z][a-z0-9_]{0,79}", normalized)
        else "runtime_provider_error"
    )


def _safe_provider_message(code: str) -> str:
    return {
        "runtime_unauthorized": "Runtime Provider credentials were rejected.",
        "runtime_rate_limited": "Runtime Provider rate limited this check.",
        "runtime_timeout": "Runtime Provider check timed out.",
        "runtime_unavailable": "Runtime Provider is temporarily unavailable.",
        "runtime_provider_error": "Runtime Provider returned an error.",
        "runtime_invalid_response": "Runtime Provider returned an invalid response.",
        "runtime_model_discovery_unavailable": (
            "Provider model discovery is unavailable; add a model ID manually "
            "if needed."
        ),
        "runtime_request_invalid": "Runtime Provider rejected the request or endpoint.",
        "provider_console_url": (
            "The service address points to a website, not a model API."
        ),
        "runtime_endpoint_invalid": (
            "The service address returned a website, not a model API response."
        ),
        "runtime_endpoint_not_found": (
            "This service address does not expose the requested model API."
        ),
        "runtime_permission_denied": (
            "This API key does not have permission to use the selected model."
        ),
        "runtime_model_unavailable": (
            "The model ID is unavailable; check its name, region and account access."
        ),
        "runtime_parameters_unsupported": (
            "The model service does not accept the selected request parameters."
        ),
        "runtime_insufficient_balance": (
            "The model service account has insufficient balance or quota."
        ),
        "model_connection_endpoint_changed": (
            "The service address changed during verification. Try again."
        ),
        "runtime_not_configured": "Runtime Provider credential is not configured.",
        "image_generation_unsupported": (
            "The configured Provider adapter does not expose image generation."
        ),
    }.get(code, "Runtime Provider check did not complete.")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
