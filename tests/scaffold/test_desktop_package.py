from __future__ import annotations

import importlib.util
import plistlib
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
    ("configured_identity", "environment", "expected"),
    [
        (None, {}, ["--config.mac.identity=-", "--config.mac.hardenedRuntime=false"]),
        (None, {"CSC_LINK": "certificate.p12"}, []),
        (None, {"CSC_NAME": "Developer ID Application: Example"}, []),
        ("Developer ID Application: Example", {}, []),
        (
            None,
            {"APPLE_SIGNING_IDENTITY": "Developer ID Application: Example"},
            ["--config.mac.identity=Developer ID Application: Example"],
        ),
    ],
)
def test_signing_preserves_provided_identity(
    package: ModuleType,
    configured_identity: str | None,
    environment: dict[str, str],
    expected: list[str],
) -> None:
    config = {"mac": {"identity": configured_identity}}
    assert package._mac_signing_arguments(config, environment) == expected


def test_native_smoke_rejects_a_missing_bundled_sidecar(
    package: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "Veyra.exe"
    executable.touch()
    calls: list[object] = []
    monkeypatch.setattr(package.subprocess, "run", lambda *a, **kw: calls.append(a))
    with pytest.raises(package.DesktopPackageError, match="missing"):
        package._verify_native_window(
            executable,
            tmp_path / "resources",
            target="x86_64-pc-windows-msvc",
        )
    assert not calls


@pytest.mark.parametrize("valid", [True, False])
def test_disk_image_checks_signature_before_launch_and_always_detaches(
    package: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    valid: bool,
) -> None:
    installer = tmp_path / "Veyra.dmg"
    commands: list[list[str]] = []
    launches: list[tuple[Path, Path, str]] = []

    def run(command: list[str], *, check: bool) -> None:
        assert check
        commands.append(command)
        if command[:2] == ["hdiutil", "attach"]:
            mount = Path(command[command.index("-mountpoint") + 1])
            contents = mount / "Veyra Agent Platform.app" / "Contents"
            resources = contents / "Resources"
            resources.mkdir(parents=True)
            with (contents / "Info.plist").open("wb") as bundle_metadata:
                plistlib.dump(
                    {
                        "CFBundleName": "Veyra Agent Platform",
                        "CFBundleDisplayName": "Veyra Agent Platform",
                        "CFBundleIdentifier": "com.veyra.agentplatform",
                        "CFBundleIconFile": "icon.icns",
                    },
                    bundle_metadata,
                )
            (resources / "icon.icns").touch()
        if command[0] == "codesign" and not valid:
            raise subprocess.CalledProcessError(1, command)

    def launch(executable: Path, resources: Path, *, target: str) -> None:
        launches.append((executable, resources, target))

    monkeypatch.setattr(package.subprocess, "run", run)
    monkeypatch.setattr(package, "_verify_native_window", launch)

    if valid:
        package._verify_disk_image(installer)
        [(executable, resources, target)] = launches
        assert executable == resources.parent / "MacOS" / "Veyra Agent Platform"
        assert target == "aarch64-apple-darwin"
    else:
        with pytest.raises(package.DesktopPackageError, match="signature is invalid"):
            package._verify_disk_image(installer)
        assert not launches

    assert [command[:2] for command in commands] == [
        ["hdiutil", "verify"],
        ["hdiutil", "attach"],
        ["codesign", "--verify"],
        ["hdiutil", "detach"],
    ]
