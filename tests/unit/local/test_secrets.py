from __future__ import annotations

import keyring
import pytest

from veyra_agent_platform.local.secrets import DeviceSecretStore, SecretStoreError


class _SystemBackend:
    __module__ = "keyring.backends.macOS"


class _UnsafeBackend:
    __module__ = "keyring.backends.file"


def test_device_secret_store_delegates_to_system_keyring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(keyring, "get_keyring", lambda: _SystemBackend())
    monkeypatch.setattr(
        keyring,
        "set_password",
        lambda service, username, password: values.__setitem__(
            (service, username), password
        ),
    )
    monkeypatch.setattr(
        keyring,
        "get_password",
        lambda service, username: values.get((service, username)),
    )
    monkeypatch.setattr(
        keyring,
        "delete_password",
        lambda service, username: values.pop((service, username), None),
    )

    store = DeviceSecretStore(service="test-service")
    store.set("runtime.credential.test", "synthetic-secret")
    assert store.get("runtime.credential.test") == "synthetic-secret"
    store.delete("runtime.credential.test")
    assert store.get("runtime.credential.test") is None


def test_device_secret_store_rejects_file_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(keyring, "get_keyring", lambda: _UnsafeBackend())
    with pytest.raises(SecretStoreError, match="approved system store"):
        DeviceSecretStore().get("runtime.credential.test")
