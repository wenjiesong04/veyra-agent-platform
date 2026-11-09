from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture
def package(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    directory = Path(__file__).resolve().parents[2] / "scripts/build/package"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location(
        "veyra_desktop_package", directory / "package.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("configured", "provided", "expected", "mode"),
    [
        (None, None, "-", "ad-hoc-preview"),
        (None, "", "-", "ad-hoc-preview"),
        (None, "-", "-", "ad-hoc-preview"),
        (
            None,
            "Developer ID Application: Example",
            "Developer ID Application: Example",
            "configured",
        ),
        ("Developer ID Application: Example", None, None, "configured"),
    ],
)
def test_signing_preserves_configured_identity_and_labels_local_preview(
    package: ModuleType,
    tmp_path: Path,
    configured: str | None,
    provided: str | None,
    expected: str | None,
    mode: str,
) -> None:
    config = tmp_path / "apps/desktop/src-tauri/tauri.conf.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps({"bundle": {"macOS": {"signingIdentity": configured}}}),
        encoding="utf-8",
    )
    environment = {} if provided is None else {"APPLE_SIGNING_IDENTITY": provided}
    assert package._configure_signing(tmp_path, environment) == mode
    assert environment.get("APPLE_SIGNING_IDENTITY") == expected


def test_package_rejects_a_missing_bundled_sidecar(
    package: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundled = tmp_path / "macos/Veyra.app/Contents/MacOS/veyra-local"
    bundled.parent.mkdir(parents=True)
    calls: list[object] = []
    monkeypatch.setattr(package.subprocess, "run", lambda *a, **kw: calls.append(a))
    with pytest.raises(package.DesktopPackageError, match="missing"):
        package._verify_app_bundle(tmp_path, build_sha="a" * 40)
    assert not calls


@pytest.mark.parametrize("valid", [True, False])
def test_bundle_signature_verification_is_mandatory(
    package: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    valid: bool,
) -> None:
    application = tmp_path / "macos/Veyra.app"
    bundled = application / "Contents/MacOS/veyra-local"
    bundled.parent.mkdir(parents=True)
    bundled.write_bytes(b"signed build")
    calls: list[list[str]] = []
    probes: list[tuple[Path, str]] = []

    def verify(command: list[str], *, check: bool) -> None:
        assert check
        calls.append(command)
        if not valid:
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(package.subprocess, "run", verify)
    monkeypatch.setattr(
        package,
        "run_runtime_smoke",
        lambda path, *, build_sha: probes.append((path, build_sha)),
    )
    if valid:
        assert package._verify_app_bundle(tmp_path, build_sha="a" * 40) == application
        assert probes == [(bundled, "a" * 40)]
    else:
        with pytest.raises(package.DesktopPackageError, match="signature is invalid"):
            package._verify_app_bundle(tmp_path, build_sha="a" * 40)
        assert not probes
    assert calls == [["codesign", "--verify", "--deep", "--strict", str(application)]]
