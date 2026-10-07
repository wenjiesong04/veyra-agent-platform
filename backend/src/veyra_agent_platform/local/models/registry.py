"""SQLite-backed Model Profile registry, defaults, and readiness resolution."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.storage.repositories import LocalRepository

from .contracts import (
    CAPABILITY_NAME_SET,
    CAPABILITY_NAMES,
    CapabilityEvidence,
    CapabilityEvidenceSource,
    CapabilityStatus,
    ModelCapability,
    ModelMetadata,
    ModelProfile,
    ModelRoleDefault,
    ModelVerification,
    ModelVerificationState,
    ProviderModelDescriptor,
    capability_map_to_dict,
    default_capabilities,
)
from .discovery import normalize_provider_models

_EVIDENCE_PRIORITY = {
    CapabilityEvidenceSource.USER_DECLARED: 1,
    CapabilityEvidenceSource.INFERRED: 2,
    CapabilityEvidenceSource.PROVIDER_ADAPTER: 3,
    CapabilityEvidenceSource.PROVIDER_METADATA: 4,
    CapabilityEvidenceSource.ACTIVE_PROBE: 5,
}
_MODEL_ROLE_RE = r"^[a-z][a-z0-9_.-]{0,63}$"


class ModelRegistryError(ValueError):
    """Typed, safe Model Registry failures; messages never contain secrets."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ModelRegistry:
    """Model Profiles associated with existing local Provider credentials."""

    def __init__(self, repository: LocalRepository, credential_store: Any) -> None:
        self.repository = repository
        self.credential_store = credential_store

    def list_profiles(
        self, credential_id: str | None = None
    ) -> tuple[ModelProfile, ...]:
        credentials = (
            {credential_id: self._credential(credential_id)}
            if credential_id is not None
            else {item.credential_id: item for item in self.credential_store.list()}
        )
        if not credentials:
            return ()
        placeholders = ",".join("?" for _ in credentials)
        with self.repository._connect() as connection:
            rows = connection.execute(
                "SELECT p.*, c.provider_type, c.label, c.base_url, "
                "c.model_discovery_state FROM model_profiles p "
                "JOIN provider_credentials c "
                "ON c.credential_id = p.provider_connection_id "
                f"WHERE p.provider_connection_id IN ({placeholders}) "
                "ORDER BY c.provider_type, c.label, p.provider_model_id, "
                "p.model_profile_id",
                tuple(credentials),
            ).fetchall()
        return tuple(
            self._profile(row, credentials[row["provider_connection_id"]])
            for row in rows
            if row["provider_connection_id"] in credentials
        )

    def list_profiles_for_connection(
        self, credential_id: str
    ) -> tuple[ModelProfile, ...]:
        return self.list_profiles(credential_id)

    def get_profile(self, model_profile_id: str) -> ModelProfile:
        with self.repository._connect() as connection:
            row = connection.execute(
                "SELECT p.*, c.provider_type, c.label, c.base_url, "
                "c.model_discovery_state FROM model_profiles p "
                "JOIN provider_credentials c "
                "ON c.credential_id = p.provider_connection_id "
                "WHERE p.model_profile_id = ? AND c.owner_id = 'local'",
                (model_profile_id,),
            ).fetchone()
        if row is None:
            raise ModelRegistryError(
                "model_profile_not_found", "Model Profile was not found."
            )
        return self._profile(row, self._credential(row["provider_connection_id"]))

    def resolve_binding(
        self,
        credential_id: str,
        provider_model_id: str,
        capability: str | None = None,
    ) -> ModelProfile:
        """Resolve an existing Runtime binding to one ready registered Model."""
        with self.repository._connect() as connection:
            row = connection.execute(
                "SELECT p.*, c.provider_type, c.label, c.base_url, "
                "c.model_discovery_state, c.status AS credential_status "
                "FROM model_profiles p JOIN provider_credentials c "
                "ON c.credential_id = p.provider_connection_id "
                "WHERE p.provider_connection_id = ? AND p.provider_model_id = ? "
                "AND c.owner_id = 'local'",
                (credential_id, provider_model_id),
            ).fetchone()
        if row is None:
            raise ModelRegistryError(
                "model_profile_not_found",
                "The bound Provider Model is not present in the Model Registry.",
            )
        credential = self._credential(credential_id)
        if credential.status == "disabled":
            raise ModelRegistryError(
                "model_connection_disabled", "The bound Provider is disabled."
            )
        if credential.readiness != "ready":
            raise ModelRegistryError(
                "model_connection_not_ready",
                "The bound Provider credential needs validation or re-entry.",
            )
        profile = self._profile(row, credential)
        if profile.verification.stale_reason == "provider_endpoint_changed":
            raise ModelRegistryError(
                "model_connection_endpoint_changed",
                "The Provider endpoint changed; discover models again before use.",
            )
        if not profile.enabled:
            raise ModelRegistryError(
                "model_profile_disabled", "The bound Model Profile is disabled."
            )
        if not profile.registry_ready:
            raise ModelRegistryError(
                "model_profile_stale",
                "The bound Model Profile is stale or no longer available.",
            )
        if capability is not None:
            if capability not in CAPABILITY_NAME_SET:
                raise ModelRegistryError(
                    "model_capability_invalid", "Unknown Model capability."
                )
            assessment = profile.capabilities[capability]
            if assessment.status is CapabilityStatus.UNKNOWN:
                raise ModelRegistryError(
                    "model_capability_unknown",
                    f"The bound Model capability {capability} is unknown.",
                )
            if assessment.status is CapabilityStatus.UNSUPPORTED:
                raise ModelRegistryError(
                    "model_capability_unsupported",
                    f"The bound Model does not support {capability}.",
                )
        return profile

    def sync_discovery(
        self,
        credential_id: str,
        provider_models: Any,
        *,
        discovered_at: str | None = None,
    ) -> tuple[ModelProfile, ...]:
        """Upsert a successful model list and retain only explicit safe metadata."""
        credential = self._credential(credential_id)
        descriptors = normalize_provider_models(provider_models)
        observed_at = discovered_at or _now()
        endpoint_fingerprint = _base_url_fingerprint(credential.base_url)
        with self.repository.transaction() as connection:
            connection.execute(
                "UPDATE model_profiles SET listed = 0, updated_at = ? "
                "WHERE provider_connection_id = ?",
                (observed_at, credential_id),
            )
            for descriptor in descriptors:
                if not descriptor.provider_model_id.strip():
                    continue
                existing = connection.execute(
                    "SELECT * FROM model_profiles WHERE provider_connection_id = ? "
                    "AND provider_model_id = ?",
                    (credential_id, descriptor.provider_model_id),
                ).fetchone()
                capabilities, metadata, verification = self._merge_discovered(
                    existing,
                    descriptor,
                    observed_at=observed_at,
                    endpoint_fingerprint=endpoint_fingerprint,
                )
                capability_json = json.dumps(
                    capability_map_to_dict(capabilities),
                    sort_keys=True,
                    separators=(",", ":"),
                )
                capability_digest = sha256_digest(capability_map_to_dict(capabilities))
                if existing is None:
                    connection.execute(
                        "INSERT INTO model_profiles("
                        "model_profile_id, provider_connection_id, provider_model_id, "
                        "display_name, profile_source, enabled, listed, metadata_json, "
                        "capabilities_json, "
                        "verification_json, capability_revision, capability_digest, "
                        "base_url_fingerprint, discovered_at, created_at, updated_at"
                        ") VALUES (?, ?, ?, ?, 'discovered', 1, 1, ?, ?, ?, 1, "
                        "?, ?, ?, ?, ?)",
                        (
                            new_uuid7(),
                            credential_id,
                            descriptor.provider_model_id,
                            descriptor.display_name,
                            json.dumps(
                                metadata.to_dict(),
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                            capability_json,
                            json.dumps(
                                verification.to_dict(),
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                            capability_digest,
                            endpoint_fingerprint,
                            observed_at,
                            observed_at,
                            observed_at,
                        ),
                    )
                else:
                    prior_capabilities = _capabilities_from_json(
                        existing["capabilities_json"]
                    )
                    revision = int(existing["capability_revision"])
                    if capability_map_to_dict(
                        prior_capabilities
                    ) != capability_map_to_dict(capabilities):
                        revision += 1
                    connection.execute(
                        "UPDATE model_profiles SET display_name = ?, listed = 1, "
                        "metadata_json = ?, capabilities_json = ?, "
                        "verification_json = ?, "
                        "capability_revision = ?, capability_digest = ?, "
                        "base_url_fingerprint = ?, discovered_at = ?, updated_at = ? "
                        "WHERE model_profile_id = ?",
                        (
                            descriptor.display_name,
                            json.dumps(
                                metadata.to_dict(),
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                            capability_json,
                            json.dumps(
                                verification.to_dict(),
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                            revision,
                            capability_digest,
                            endpoint_fingerprint,
                            observed_at,
                            observed_at,
                            existing["model_profile_id"],
                        ),
                    )
            connection.execute(
                "UPDATE provider_credentials SET model_discovery_state = 'ready', "
                "model_discovery_checked_at = ?, model_discovered_at = ?, "
                "model_discovery_error_code = NULL WHERE credential_id = ? "
                "AND owner_id = 'local'",
                (observed_at, observed_at, credential_id),
            )
        return self.list_profiles_for_connection(credential_id)

    def mark_discovery_failure(
        self,
        credential_id: str,
        *,
        error_code: str,
        state: str = "failed",
        checked_at: str | None = None,
    ) -> tuple[ModelProfile, ...]:
        if state not in {"failed", "stale"}:
            state = "failed"
        observed_at = checked_at or _now()
        safe_code = _safe_error_code(error_code)
        with self.repository.transaction() as connection:
            cursor = connection.execute(
                "UPDATE provider_credentials SET model_discovery_state = ?, "
                "model_discovery_checked_at = ?, model_discovery_error_code = ? "
                "WHERE credential_id = ? AND owner_id = 'local'",
                (state, observed_at, safe_code, credential_id),
            )
            if cursor.rowcount != 1:
                raise ModelRegistryError(
                    "provider_connection_not_found",
                    "Provider connection was not found.",
                )
        return self.list_profiles_for_connection(credential_id)

    def invalidate_connection(
        self, credential_id: str, *, reason: str = "credential_replaced"
    ) -> None:
        """Discard account-scoped probe evidence after a credential replacement."""
        observed_at = _now()
        with self.repository.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM model_profiles WHERE provider_connection_id = ?",
                (credential_id,),
            ).fetchall()
            for row in rows:
                capabilities = dict(default_capabilities())
                prior_verification = _verification_from_json(row["verification_json"])
                changed = any(
                    assessment.status is not CapabilityStatus.UNKNOWN
                    or assessment.evidence is not None
                    for assessment in _capabilities_from_json(
                        row["capabilities_json"]
                    ).values()
                )
                if not changed:
                    continue
                capability_payload = capability_map_to_dict(capabilities)
                digest = sha256_digest(capability_payload)
                revision = int(row["capability_revision"]) + 1
                verification = ModelVerification(
                    state=ModelVerificationState.UNKNOWN,
                    source=(
                        CapabilityEvidenceSource.USER_DECLARED
                        if not bool(row["listed"])
                        and prior_verification.source
                        is CapabilityEvidenceSource.USER_DECLARED
                        else None
                    ),
                    last_checked_at=observed_at,
                    stale_reason=_safe_stale_reason(reason),
                )
                connection.execute(
                    "UPDATE model_profiles SET capabilities_json = ?, "
                    "verification_json = ?, capability_revision = ?, "
                    "capability_digest = ?, updated_at = ? WHERE model_profile_id = ?",
                    (
                        json.dumps(
                            capability_payload, sort_keys=True, separators=(",", ":")
                        ),
                        json.dumps(
                            verification.to_dict(),
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        revision,
                        digest,
                        observed_at,
                        row["model_profile_id"],
                    ),
                )

    def add_manual_model(
        self,
        credential_id: str,
        provider_model_id: str,
        *,
        display_name: str | None = None,
    ) -> ModelProfile:
        credential = self._credential(credential_id)
        model_id = provider_model_id.strip()
        if not model_id or len(model_id) > 512:
            raise ModelRegistryError(
                "provider_model_id_invalid", "Provider Model ID is invalid."
            )
        clean_name = (display_name or model_id).strip()[:200]
        if not clean_name:
            clean_name = model_id
        existing = next(
            (
                item
                for item in self.list_profiles_for_connection(credential_id)
                if item.provider_model_id == model_id
            ),
            None,
        )
        if existing is not None:
            return existing
        observed_at = _now()
        capabilities = default_capabilities()
        capability_payload = capability_map_to_dict(capabilities)
        digest = sha256_digest(capability_payload)
        verification = ModelVerification(
            state=ModelVerificationState.UNKNOWN,
            source=CapabilityEvidenceSource.USER_DECLARED,
        )
        with self.repository.transaction() as connection:
            connection.execute(
                "INSERT INTO model_profiles("
                "model_profile_id, provider_connection_id, provider_model_id, "
                "display_name, profile_source, enabled, listed, metadata_json, "
                "capabilities_json, "
                "verification_json, capability_revision, capability_digest, "
                "base_url_fingerprint, discovered_at, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, 'manual', 1, 0, '{}', ?, ?, 1, "
                "?, ?, NULL, ?, ?)",
                (
                    new_uuid7(),
                    credential_id,
                    model_id,
                    clean_name,
                    json.dumps(
                        capability_payload, sort_keys=True, separators=(",", ":")
                    ),
                    json.dumps(
                        verification.to_dict(), sort_keys=True, separators=(",", ":")
                    ),
                    digest,
                    _base_url_fingerprint(credential.base_url),
                    observed_at,
                    observed_at,
                ),
            )
        return next(
            item
            for item in self.list_profiles_for_connection(credential_id)
            if item.provider_model_id == model_id
        )

    def set_default(self, role: str, model_profile_id: str) -> ModelRoleDefault:
        clean_role = role.strip().lower()
        if not _valid_role(clean_role):
            raise ModelRegistryError("model_role_invalid", "Model role is invalid.")
        profile = self.get_profile(model_profile_id)
        if not profile.registry_ready:
            raise ModelRegistryError(
                "model_profile_not_ready",
                "Model Profile is not ready for a default binding.",
            )
        updated_at = _now()
        with self.repository.transaction() as connection:
            connection.execute(
                "INSERT INTO model_role_defaults(role, model_profile_id, updated_at) "
                "VALUES (?, ?, ?) ON CONFLICT(role) DO UPDATE SET "
                "model_profile_id = excluded.model_profile_id, "
                "updated_at = excluded.updated_at",
                (clean_role, model_profile_id, updated_at),
            )
        result = next(item for item in self.list_defaults() if item.role == clean_role)
        return result

    def clear_default(self, role: str) -> None:
        clean_role = role.strip().lower()
        if not _valid_role(clean_role):
            raise ModelRegistryError("model_role_invalid", "Model role is invalid.")
        with self.repository.transaction() as connection:
            connection.execute(
                "DELETE FROM model_role_defaults WHERE role = ?", (clean_role,)
            )

    def list_defaults(self) -> tuple[ModelRoleDefault, ...]:
        with self.repository._connect() as connection:
            rows = connection.execute(
                "SELECT d.role, d.model_profile_id, d.updated_at "
                "FROM model_role_defaults d JOIN model_profiles p "
                "ON p.model_profile_id = d.model_profile_id "
                "JOIN provider_credentials c "
                "ON c.credential_id = p.provider_connection_id "
                "WHERE c.owner_id = 'local' ORDER BY d.role"
            ).fetchall()
        result: list[ModelRoleDefault] = []
        for row in rows:
            try:
                profile = self.get_profile(row["model_profile_id"])
            except ModelRegistryError:
                continue
            result.append(
                ModelRoleDefault(
                    role=row["role"],
                    model_profile_id=profile.model_profile_id,
                    provider_connection_id=profile.provider_connection_id,
                    provider_model_id=profile.provider_model_id,
                    capability_digest=profile.capability_digest,
                    capability_revision=profile.capability_revision,
                    updated_at=row["updated_at"],
                )
            )
        return tuple(result)

    def record_capability_probe(
        self,
        model_profile_id: str,
        capability: str,
        status: CapabilityStatus,
        *,
        source: CapabilityEvidenceSource = CapabilityEvidenceSource.ACTIVE_PROBE,
        detail: str | None = None,
        observed_at: str | None = None,
    ) -> ModelProfile:
        if capability not in CAPABILITY_NAME_SET:
            raise ModelRegistryError(
                "model_capability_invalid", "Unknown Model capability."
            )
        if status is CapabilityStatus.UNKNOWN:
            raise ModelRegistryError(
                "model_probe_result_invalid",
                "An active probe must report supported or unsupported.",
            )
        profile = self.get_profile(model_profile_id)
        credential = self._credential(profile.provider_connection_id)
        endpoint_fingerprint = _base_url_fingerprint(credential.base_url)
        when = observed_at or _now()
        # An explicit probe may continue after a user corrects the address. Its
        # new result must not carry capability evidence from the old service.
        with self.repository._connect() as connection:
            previous_endpoint = connection.execute(
                "SELECT base_url_fingerprint FROM model_profiles "
                "WHERE model_profile_id = ?",
                (model_profile_id,),
            ).fetchone()[0]
        endpoint_changed = previous_endpoint != endpoint_fingerprint
        capabilities = dict(
            default_capabilities() if endpoint_changed else profile.capabilities
        )
        capabilities[capability] = ModelCapability(
            status=status,
            evidence=CapabilityEvidence(source=source, observed_at=when, detail=detail),
        )
        payload = capability_map_to_dict(capabilities)
        digest = sha256_digest(payload)
        with self.repository.transaction() as connection:
            connection.execute(
                "UPDATE model_profiles SET capabilities_json = ?, "
                "verification_json = ?, capability_revision = capability_revision + 1, "
                "capability_digest = ?, updated_at = ?, "
                "listed = CASE WHEN base_url_fingerprint = ? THEN listed ELSE 0 END, "
                "profile_source = CASE WHEN base_url_fingerprint = ? "
                "THEN profile_source ELSE 'manual' END, "
                "base_url_fingerprint = ? WHERE model_profile_id = ?",
                (
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    json.dumps(
                        ModelVerification(
                            state=ModelVerificationState.VERIFIED,
                            source=source,
                            verified_at=when,
                            last_checked_at=when,
                        ).to_dict(),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    digest,
                    when,
                    endpoint_fingerprint,
                    endpoint_fingerprint,
                    endpoint_fingerprint,
                    model_profile_id,
                ),
            )
        return self.get_profile(model_profile_id)

    def record_probe_failure(
        self,
        model_profile_id: str,
        error_code: str,
        *,
        checked_at: str | None = None,
    ) -> ModelProfile:
        profile = self.get_profile(model_profile_id)
        when = checked_at or _now()
        verification = replace(
            profile.verification,
            last_checked_at=when,
            error_code=_safe_error_code(error_code),
        )
        with self.repository.transaction() as connection:
            connection.execute(
                "UPDATE model_profiles SET verification_json = ?, updated_at = ? "
                "WHERE model_profile_id = ?",
                (
                    json.dumps(
                        verification.to_dict(), sort_keys=True, separators=(",", ":")
                    ),
                    when,
                    model_profile_id,
                ),
            )
        return self.get_profile(model_profile_id)

    def runtime_binding_profiles(
        self, project_id: str, agent_id: str | None = None
    ) -> dict[str, dict[str, str]]:
        """Map bindings to Profile IDs, preserving stale slots with a safe sentinel."""
        bindings = self.credential_store.bindings(project_id, agent_id=agent_id)
        result: dict[str, dict[str, str]] = {}
        for binding in bindings:
            scope = (
                "project" if binding.agent_id is None else f"agent:{binding.agent_id}"
            )
            try:
                profile = self.resolve_binding(
                    binding.credential_id,
                    binding.model_id,
                )
            except ModelRegistryError:
                # Keep precedence explicit: an unusable pinned binding must not
                # disappear and allow ModelResolver to silently choose a fallback.
                result.setdefault(scope, {})[binding.slot] = "__unresolved_binding__"
            else:
                result.setdefault(scope, {})[binding.slot] = profile.model_profile_id
        return result

    def _credential(self, credential_id: str) -> Any:
        try:
            return self.credential_store.get(credential_id)
        except ValueError as exc:
            raise ModelRegistryError(
                "provider_connection_not_found", "Provider connection was not found."
            ) from exc

    def _profile(self, row: Any, credential: Any) -> ModelProfile:
        capabilities = _capabilities_from_json(row["capabilities_json"])
        verification = _verification_from_json(row["verification_json"])
        endpoint_matches = row["base_url_fingerprint"] == _base_url_fingerprint(
            credential.base_url
        )
        is_manual = row["profile_source"] == "manual"
        manual_probe_verified = bool(
            is_manual
            and verification.state is ModelVerificationState.VERIFIED
            and verification.source is CapabilityEvidenceSource.ACTIVE_PROBE
            and (
                credential.discovery_state not in {"failed", "stale"}
                or (
                    verification.verified_at
                    and credential.discovery_checked_at
                    and verification.verified_at >= credential.discovery_checked_at
                )
            )
        )
        digest = sha256_digest(capability_map_to_dict(capabilities))
        stale_reason: str | None = None
        if not endpoint_matches:
            stale_reason = "provider_endpoint_changed"
        elif credential.readiness != "ready":
            stale_reason = _safe_stale_reason(credential.readiness)
        elif (
            credential.discovery_state in {"failed", "stale"}
            and credential.discovery_error_code != "runtime_model_discovery_unavailable"
            and not manual_probe_verified
        ):
            stale_reason = "model_discovery_failed"
        elif digest != row["capability_digest"]:
            stale_reason = "capability_digest_mismatch"
        if stale_reason and verification.state is not ModelVerificationState.UNKNOWN:
            verification = replace(
                verification,
                state=ModelVerificationState.STALE,
                stale_reason=stale_reason,
            )
        manual_probe_ready = bool(manual_probe_verified and endpoint_matches)
        discovery_ready = credential.discovery_state == "ready" or manual_probe_ready
        registry_ready = bool(
            credential.readiness == "ready"
            and endpoint_matches
            and digest == row["capability_digest"]
            and bool(row["enabled"])
            and verification.state is not ModelVerificationState.STALE
            and discovery_ready
            and (bool(row["listed"]) or is_manual)
        )
        return ModelProfile(
            model_profile_id=row["model_profile_id"],
            provider_connection_id=row["provider_connection_id"],
            provider_type=row["provider_type"],
            provider_label=row["label"],
            provider_model_id=row["provider_model_id"],
            display_name=row["display_name"],
            enabled=bool(row["enabled"]),
            listed=bool(row["listed"]),
            metadata=ModelMetadata.from_mapping(_json_object(row["metadata_json"])),
            capabilities=capabilities,
            verification=verification,
            capability_revision=int(row["capability_revision"]),
            capability_digest=row["capability_digest"],
            discovered_at=row["discovered_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            connection_readiness=credential.readiness,
            registry_ready=registry_ready,
        )

    def _merge_discovered(
        self,
        existing: Any,
        descriptor: ProviderModelDescriptor,
        *,
        observed_at: str,
        endpoint_fingerprint: str,
    ) -> tuple[dict[str, ModelCapability], ModelMetadata, ModelVerification]:
        incoming = dict(default_capabilities())
        for name, assessment in descriptor.capabilities.items():
            if name not in CAPABILITY_NAME_SET:
                continue
            evidence = assessment.evidence
            if evidence is None or assessment.status is CapabilityStatus.UNKNOWN:
                continue
            incoming[name] = ModelCapability(
                status=assessment.status,
                evidence=CapabilityEvidence(
                    source=evidence.source,
                    observed_at=observed_at,
                    detail=evidence.detail,
                ),
            )

        if existing is None:
            return (
                incoming,
                descriptor.metadata,
                _verification_from_capabilities(incoming, last_checked_at=observed_at),
            )

        prior = _capabilities_from_json(existing["capabilities_json"])
        same_endpoint = existing["base_url_fingerprint"] == endpoint_fingerprint
        if not same_endpoint:
            prior = dict(default_capabilities())
        caps: dict[str, ModelCapability] = {}
        for name in CAPABILITY_NAMES:
            current = prior[name]
            next_value = incoming[name]
            if (
                not same_endpoint
                and current.evidence is not None
                and (current.evidence.source is CapabilityEvidenceSource.ACTIVE_PROBE)
            ):
                current = ModelCapability()
            if current.evidence is None:
                caps[name] = next_value
            elif next_value.evidence is None:
                caps[name] = current
            elif (
                _EVIDENCE_PRIORITY[next_value.evidence.source]
                >= _EVIDENCE_PRIORITY[current.evidence.source]
            ):
                caps[name] = next_value
            else:
                caps[name] = current
        old_metadata = _json_object(existing["metadata_json"]) if same_endpoint else {}
        new_metadata = descriptor.metadata.to_dict()
        metadata = ModelMetadata.from_mapping({**old_metadata, **new_metadata})
        verification = _verification_from_capabilities(
            caps,
            last_checked_at=observed_at,
        )
        if (
            verification.state is ModelVerificationState.UNKNOWN
            and existing["profile_source"] == "manual"
        ):
            verification = replace(
                verification,
                source=CapabilityEvidenceSource.USER_DECLARED,
            )
        return caps, metadata, verification


def _capabilities_from_json(value: str) -> dict[str, ModelCapability]:
    raw = _json_object(value)
    result: dict[str, ModelCapability] = {}
    for name in CAPABILITY_NAMES:
        item = raw.get(name)
        if not isinstance(item, Mapping):
            result[name] = ModelCapability()
            continue
        try:
            status = CapabilityStatus(item.get("status", "unknown"))
        except ValueError:
            status = CapabilityStatus.UNKNOWN
        evidence_raw = item.get("evidence")
        evidence = None
        if isinstance(evidence_raw, Mapping):
            source_raw = evidence_raw.get("source")
            source: CapabilityEvidenceSource | None = None
            if isinstance(source_raw, str):
                try:
                    source = CapabilityEvidenceSource(source_raw)
                except ValueError:
                    source = None
            observed_at = evidence_raw.get("observed_at")
            detail = evidence_raw.get("detail")
            if source is not None and isinstance(observed_at, str):
                evidence = CapabilityEvidence(
                    source=source,
                    observed_at=observed_at,
                    detail=detail[:240] if isinstance(detail, str) else None,
                )
        if status is not CapabilityStatus.UNKNOWN and evidence is None:
            status = CapabilityStatus.UNKNOWN
        result[name] = ModelCapability(status, evidence)
    return result


def _verification_from_json(value: str) -> ModelVerification:
    raw = _json_object(value)
    try:
        state = ModelVerificationState(raw.get("state", "unknown"))
    except ValueError:
        state = ModelVerificationState.UNKNOWN
    source_raw = raw.get("source")
    try:
        source = CapabilityEvidenceSource(source_raw) if source_raw else None
    except ValueError:
        source = None
    return ModelVerification(
        state=state,
        source=source,
        verified_at=_optional_string(raw.get("verified_at")),
        last_checked_at=_optional_string(raw.get("last_checked_at")),
        stale_reason=_optional_string(raw.get("stale_reason")),
        error_code=_safe_error_code(raw.get("error_code"))
        if raw.get("error_code")
        else None,
    )


def _verification_from_capabilities(
    capabilities: Mapping[str, ModelCapability],
    *,
    last_checked_at: str | None,
    stale_reason: str | None = None,
) -> ModelVerification:
    observed: list[tuple[CapabilityEvidenceSource, str]] = []
    for capability in capabilities.values():
        evidence = capability.evidence
        if evidence is not None and capability.status is not CapabilityStatus.UNKNOWN:
            observed.append((evidence.source, evidence.observed_at))
    if any(source is CapabilityEvidenceSource.ACTIVE_PROBE for source, _ in observed):
        active = [
            observed_at
            for source, observed_at in observed
            if source is CapabilityEvidenceSource.ACTIVE_PROBE
        ]
        return ModelVerification(
            state=ModelVerificationState.VERIFIED,
            source=CapabilityEvidenceSource.ACTIVE_PROBE,
            verified_at=max(active),
            last_checked_at=last_checked_at,
            stale_reason=stale_reason,
        )
    for source in (
        CapabilityEvidenceSource.PROVIDER_METADATA,
        CapabilityEvidenceSource.PROVIDER_ADAPTER,
        CapabilityEvidenceSource.INFERRED,
    ):
        matches = [when for candidate, when in observed if candidate is source]
        if matches:
            return ModelVerification(
                state=ModelVerificationState.DECLARED,
                source=source,
                verified_at=None,
                last_checked_at=last_checked_at,
                stale_reason=stale_reason,
            )
    return ModelVerification(
        state=ModelVerificationState.UNKNOWN,
        source=CapabilityEvidenceSource.USER_DECLARED
        if stale_reason == "credential_replaced"
        else None,
        last_checked_at=last_checked_at,
        stale_reason=stale_reason,
    )


def _json_object(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _base_url_fingerprint(value: str) -> str:
    return hashlib.sha256(value.strip().rstrip("/").encode("utf-8")).hexdigest()


def _valid_role(value: str) -> bool:
    import re

    return bool(re.fullmatch(_MODEL_ROLE_RE, value))


def _safe_error_code(value: Any) -> str:
    import re

    if not isinstance(value, str):
        return "runtime_provider_error"
    normalized = value.strip().lower()
    return (
        normalized
        if re.fullmatch(r"[a-z][a-z0-9_]{0,79}", normalized)
        else "runtime_provider_error"
    )


def _safe_stale_reason(value: str) -> str:
    allowed = {
        "provider_endpoint_changed",
        "credential_replaced",
        "model_discovery_failed",
        "disabled",
        "invalid",
        "needs_reentry",
        "unavailable",
        "unverified",
        "capability_digest_mismatch",
    }
    normalized = value.strip().lower()
    return normalized if normalized in allowed else "provider_connection_not_ready"


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
