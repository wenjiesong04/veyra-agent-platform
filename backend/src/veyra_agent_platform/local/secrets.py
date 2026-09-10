"""Host-side secret storage for local Tool adapters.

Project sources contain opaque secret references only. Values are kept in the
macOS Keychain when available, with process environment variables as the
development fallback.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from typing import Protocol

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


class MacOSKeychainSecretStore:
    """Use the macOS `security` CLI without persisting secrets in SQLite."""

    def __init__(
        self,
        *,
        service: str = SERVICE_NAME,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.service = service
        self.environment = dict(environment or os.environ)

    def get(self, secret_ref: str) -> str | None:
        try:
            result = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-s",
                    self.service,
                    "-a",
                    secret_ref,
                    "-w",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                env=self.environment,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SecretStoreError("macOS Keychain could not be queried") from exc
        if result.returncode == 0:
            value = result.stdout.strip()
            return value or None
        return None

    def set(self, secret_ref: str, value: str) -> None:
        if not value.strip():
            raise SecretStoreError("secret value must not be empty")
        try:
            result = subprocess.run(
                [
                    "security",
                    "add-generic-password",
                    "-U",
                    "-s",
                    self.service,
                    "-a",
                    secret_ref,
                    "-w",
                    value,
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                env=self.environment,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SecretStoreError("macOS Keychain could not store the secret") from exc
        if result.returncode != 0:
            raise SecretStoreError("macOS Keychain rejected the secret")

    def delete(self, secret_ref: str) -> None:
        try:
            result = subprocess.run(
                [
                    "security",
                    "delete-generic-password",
                    "-s",
                    self.service,
                    "-a",
                    secret_ref,
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                env=self.environment,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SecretStoreError(
                "macOS Keychain could not remove the secret"
            ) from exc
        if result.returncode not in {0, 44}:
            raise SecretStoreError("macOS Keychain rejected the removal")


def secret_environment_name(secret_ref: str) -> str:
    return _SECRET_ENV_NAMES.get(
        secret_ref, secret_ref.upper().replace(".", "_").replace("-", "_")
    )


def known_secret_refs() -> tuple[str, ...]:
    return tuple(_SECRET_ENV_NAMES)
