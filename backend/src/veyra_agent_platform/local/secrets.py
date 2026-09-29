"""Host-side secret storage for local adapters.

Project sources contain opaque secret references only. Device credentials are
kept in the operating system's credential service through the cross-platform
``keyring`` adapter. Process environment variables remain an explicit
development fallback for deployment-owned Platform credentials, not for User
Runtime credentials.
"""

from __future__ import annotations

import os
from typing import Any, Protocol

SERVICE_NAME = "Veyra Agent Platform"
MODEL_SECRET_REF = "model.primary"
_SECRET_ENV_NAMES = {
    "github.main": "GITHUB_TOKEN",
    MODEL_SECRET_REF: "MOONSHOT_API_KEY",
}


class SecretStoreError(RuntimeError):
    """A host secret operation failed without exposing its value."""


class SecretStore(Protocol):
    def get(self, secret_ref: str) -> str | None: ...

    def set(self, secret_ref: str, value: str) -> None: ...

    def delete(self, secret_ref: str) -> None: ...


def resolve_secret(
    store: SecretStore | None,
    secret_ref: str,
    env_name: str,
    *,
    allow_environment: bool = True,
) -> str:
    """Resolve a host secret without persisting its value in Project data."""
    if store is not None:
        try:
            value = store.get(secret_ref)
        except SecretStoreError:
            value = None
        if value:
            return value.strip()
    return os.environ.get(env_name, "").strip() if allow_environment else ""


_SYSTEM_KEYRING_MODULES = (
    "keyring.backends.macOS",
    "keyring.backends.OS_X",
    "keyring.backends.Windows",
    "keyring.backends.SecretService",
    "keyring.backends.kwallet",
    "keyring.backends.Gnome",
)
_UNSAFE_KEYRING_MODULES = (
    "keyring.backends.fail",
    "keyring.backends.null",
    "keyring.backends.file",
    "keyrings.alt",
)


class DeviceSecretStore:
    """Persist device credentials in the host operating system's keyring.

    ``keyring`` owns the platform selection: macOS Keychain, Windows
    Credential Manager, or a Linux Secret Service/KWallet backend. We reject
    the null, plaintext-file, and alternate-file backends instead of silently
    weakening the credential boundary when a system service is unavailable.
    """

    def __init__(self, *, service: str = SERVICE_NAME) -> None:
        self.service = service
        self._keyring: Any | None = None

    def get(self, secret_ref: str) -> str | None:
        keyring = self._client()
        try:
            value = keyring.get_password(self.service, secret_ref)
        except Exception as exc:
            raise SecretStoreError(
                "system credential store could not be queried"
            ) from exc
        return value.strip() if isinstance(value, str) and value.strip() else None

    def set(self, secret_ref: str, value: str) -> None:
        if not value.strip():
            raise SecretStoreError("secret value must not be empty")
        keyring = self._client()
        try:
            keyring.set_password(self.service, secret_ref, value)
        except Exception as exc:
            raise SecretStoreError(
                "system credential store rejected the secret"
            ) from exc

    def delete(self, secret_ref: str) -> None:
        keyring = self._client()
        try:
            keyring.delete_password(self.service, secret_ref)
        except Exception as exc:
            # keyring uses PasswordDeleteError for an already absent item.
            # Deletion is intentionally idempotent, while all other failures
            # remain visible to the caller.
            if exc.__class__.__name__ == "PasswordDeleteError":
                return
            raise SecretStoreError(
                "system credential store rejected the removal"
            ) from exc

    def _client(self) -> Any:
        if self._keyring is not None:
            return self._keyring
        try:
            import keyring
        except ImportError as exc:
            raise SecretStoreError("no system credential backend is installed") from exc
        try:
            backend = keyring.get_keyring()
        except Exception as exc:
            raise SecretStoreError(
                "system credential backend could not be initialized"
            ) from exc
        module = type(backend).__module__
        if any(module.startswith(prefix) for prefix in _UNSAFE_KEYRING_MODULES):
            raise SecretStoreError(
                "configured credential backend is not an approved system store"
            )
        if not any(module.startswith(prefix) for prefix in _SYSTEM_KEYRING_MODULES):
            raise SecretStoreError("no approved system credential backend is available")
        self._keyring = keyring
        return keyring


# Compatibility names kept for existing tests and integrations. They now
# resolve to the same cross-platform device store rather than a macOS-only
# implementation.
SystemKeyringSecretStore = DeviceSecretStore
MacOSKeychainSecretStore = DeviceSecretStore


def secret_environment_name(secret_ref: str) -> str:
    return _SECRET_ENV_NAMES.get(
        secret_ref, secret_ref.upper().replace(".", "_").replace("-", "_")
    )


def known_secret_refs() -> tuple[str, ...]:
    return tuple(_SECRET_ENV_NAMES)
