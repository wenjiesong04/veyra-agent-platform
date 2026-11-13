"""Build and verify the Electron installer with its Local API executable."""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from build_sidecar import (
    LINUX_TARGET,
    MAC_TARGET,
    SUPPORTED_TARGETS,
    SidecarBuildError,
    build_sidecar,
    default_target,
    repository_root,
    resolve_build_sha,
    sidecar_name,
)
from package_smoke import PackageSmokeError, check_static_contract, run_runtime_smoke

PRODUCT_NAME = "Veyra Agent Platform"
APP_ID = "com.veyra.agentplatform"
BUILDER_CONFIG = "electron-builder.json"
SMOKE_TIMEOUT_SECONDS = 90


class DesktopPackageError(RuntimeError):
    """The desktop package lane could not run."""


def _build_directory(root: Path) -> Path:
    return root / "build" / "desktop-package"


def _stage_desktop(root: Path, sidecar: Path, stage: Path, *, build_sha: str) -> None:
    npm = shutil.which("npm")
    if not npm:
        raise DesktopPackageError("npm is required to build the Desktop interface")
    environment = os.environ.copy()
    environment["VITE_LOCAL_API_BASE_URL"] = "/api/v1"
    subprocess.run(
        [npm, "--prefix", "web", "run", "build:desktop"],
        cwd=root,
        env=environment,
        check=True,
    )

    renderer = root / "web" / "apps" / "desktop" / "dist"
    if not (renderer / "index.html").is_file():
        raise DesktopPackageError("Desktop build is missing index.html")
    if stage.exists():
        shutil.rmtree(stage)
    (stage / "sidecar").mkdir(parents=True)
    shutil.copytree(renderer, stage / "renderer")
    shutil.copy2(sidecar, stage / "sidecar" / sidecar.name)
    (stage / "build-info.json").write_text(
        json.dumps({"buildSha": build_sha}) + "\n", encoding="utf-8"
    )
    print(f"electron_stage={stage}")


def _mac_signing_arguments(
    config: dict[str, object], environment: dict[str, str]
) -> list[str]:
    mac = config.get("mac")
    configured_identity = mac.get("identity") if isinstance(mac, dict) else None
    identity = environment.get("APPLE_SIGNING_IDENTITY", "").strip()
    if not identity and not configured_identity:
        if environment.get("CSC_LINK") or environment.get("CSC_NAME"):
            return []
        identity = "-"
    if identity == "-" or (not identity and configured_identity == "-"):
        print("desktop_signing=ad-hoc-preview")
        return ["--config.mac.identity=-", "--config.mac.hardenedRuntime=false"]
    return [f"--config.mac.identity={identity}"] if identity else []


def _verify_native_window(executable: Path, resources: Path, *, target: str) -> None:
    if not (resources / "sidecar" / sidecar_name(target)).is_file():
        raise DesktopPackageError(
            "the packaged application is missing its Local sidecar"
        )
    if not executable.is_file():
        raise DesktopPackageError(
            f"packaged Electron executable is missing: {executable}"
        )
    with tempfile.TemporaryDirectory(prefix="veyra-electron-smoke-cwd-") as temporary:
        try:
            result = subprocess.run(
                [str(executable), "--veyra-package-smoke"],
                cwd=temporary,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=SMOKE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise DesktopPackageError("packaged Electron smoke timed out") from exc
    if (
        result.returncode != 0
        or "electron_package_smoke=ok" not in result.stdout.splitlines()
    ):
        diagnostics = "\n".join([result.stdout, result.stderr]).strip()
        raise DesktopPackageError(
            f"packaged Electron smoke failed ({result.returncode}): "
            f"{diagnostics[-2000:]}"
        )
    print("electron_package_smoke=ok")


def _verify_mac_brand(contents: Path) -> None:
    with (contents / "Info.plist").open("rb") as bundle_metadata:
        metadata = plistlib.load(bundle_metadata)
    if (
        metadata.get("CFBundleName") != PRODUCT_NAME
        or metadata.get("CFBundleDisplayName") != PRODUCT_NAME
        or metadata.get("CFBundleIdentifier") != APP_ID
    ):
        raise DesktopPackageError("macOS app bundle has incorrect Veyra identity")
    icon_name = metadata.get("CFBundleIconFile")
    if not isinstance(icon_name, str) or not icon_name:
        raise DesktopPackageError("macOS app bundle has no Veyra icon")
    icon = Path(icon_name)
    if not icon.suffix:
        icon = icon.with_suffix(".icns")
    if icon.parent != Path(".") or not (contents / "Resources" / icon).is_file():
        raise DesktopPackageError("macOS app bundle is missing its Veyra icon")
    print("app_bundle_brand=ok")


def _verify_disk_image(installer: Path) -> None:
    subprocess.run(["hdiutil", "verify", str(installer)], check=True)
    with tempfile.TemporaryDirectory(prefix="veyra-dmg-verify-") as temporary:
        subprocess.run(
            [
                "hdiutil",
                "attach",
                "-readonly",
                "-nobrowse",
                "-mountpoint",
                temporary,
                str(installer),
            ],
            check=True,
        )
        try:
            application = Path(temporary) / f"{PRODUCT_NAME}.app"
            if not application.is_dir():
                raise DesktopPackageError("DMG is missing the Electron app bundle")
            try:
                subprocess.run(
                    ["codesign", "--verify", "--deep", "--strict", str(application)],
                    check=True,
                )
            except subprocess.CalledProcessError as exc:
                raise DesktopPackageError(
                    "macOS app bundle signature is invalid"
                ) from exc
            print("app_bundle_signature=ok")
            contents = application / "Contents"
            _verify_mac_brand(contents)
            _verify_native_window(
                contents / "MacOS" / PRODUCT_NAME,
                contents / "Resources",
                target=MAC_TARGET,
            )
        finally:
            subprocess.run(["hdiutil", "detach", temporary], check=True)


def _build_electron(
    root: Path, stage: Path, output: Path, *, target: str, unpacked: bool
) -> None:
    desktop = root / "apps" / "desktop"
    node = shutil.which("node")
    builder = desktop / "node_modules" / "electron-builder" / "cli.js"
    if not node or not builder.is_file():
        raise DesktopPackageError(
            "install Electron build dependencies with npm ci in apps/desktop"
        )
    environment = os.environ.copy()
    environment.setdefault("CI", "true")
    environment["VEYRA_ELECTRON_STAGE_NAME"] = stage.name
    if target == MAC_TARGET:
        config = json.loads((desktop / BUILDER_CONFIG).read_text(encoding="utf-8"))
        arguments = ["--mac", "--arm64", *_mac_signing_arguments(config, environment)]
    elif target == LINUX_TARGET:
        arguments = ["--linux", "--x64"]
    else:
        arguments = ["--win", "--x64"]

    subprocess.run(
        [
            node,
            str(builder),
            "--config",
            BUILDER_CONFIG,
            f"--config.directories.output={output}",
            "--publish",
            "never",
            *arguments,
            *(["--dir"] if unpacked else []),
        ],
        cwd=desktop,
        env=environment,
        check=True,
    )


def _unpacked_application(output: Path, *, target: str) -> tuple[Path, Path]:
    if target == MAC_TARGET:
        contents = output / "mac-arm64" / f"{PRODUCT_NAME}.app" / "Contents"
        _verify_mac_brand(contents)
        return contents / "MacOS" / PRODUCT_NAME, contents / "Resources"
    if target == LINUX_TARGET:
        app = output / "linux-unpacked"
        return app / "veyra", app / "resources"
    app = output / "win-unpacked"
    return app / f"{PRODUCT_NAME}.exe", app / "resources"


def _run_desktop(root: Path, stage: Path, *, target: str) -> None:
    with tempfile.TemporaryDirectory(
        prefix="electron-dev-", dir=_build_directory(root)
    ) as temporary:
        output = Path(temporary)
        _build_electron(root, stage, output, target=target, unpacked=True)
        executable, resources = _unpacked_application(output, target=target)
        command = [str(executable)]
        with subprocess.Popen(command, cwd=resources) as process:
            try:
                status = process.wait()
            except KeyboardInterrupt:
                # Give Electron time to stop the Local API after terminal SIGINT.
                try:
                    process.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=12)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                return
        if status != 0:
            raise subprocess.CalledProcessError(status, command)


def _build_installer(root: Path, stage: Path, *, target: str) -> Path:
    pattern = {
        MAC_TARGET: "*.dmg",
        LINUX_TARGET: "*.AppImage",
    }.get(target, "*.exe")
    build_directory = _build_directory(root)
    with tempfile.TemporaryDirectory(
        prefix="electron-output-", dir=build_directory
    ) as temporary:
        output = Path(temporary)
        _build_electron(root, stage, output, target=target, unpacked=False)
        installers = sorted(output.glob(pattern))
        if len(installers) != 1:
            raise DesktopPackageError(
                f"expected one Electron installer, found {len(installers)}"
            )
        installer = installers[0]
        if target == MAC_TARGET:
            _verify_disk_image(installer)
        else:
            executable, resources = _unpacked_application(output, target=target)
            _verify_native_window(executable, resources, target=target)
        destination = build_directory / "dist" / installer.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        installer.replace(destination)
        return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=SUPPORTED_TARGETS, default=default_target())
    parser.add_argument("--build-sha")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--stage-only", action="store_true")
    mode.add_argument("--run", action="store_true")
    arguments = parser.parse_args()
    root = repository_root()
    try:
        sha = resolve_build_sha(arguments.build_sha, root=root)
        check_static_contract(root, target=arguments.target)
        sidecar = build_sidecar(root=root, target=arguments.target, build_sha=sha)
        if arguments.stage_only:
            stage = _build_directory(root) / "electron-stage"
            _stage_desktop(root, sidecar, stage, build_sha=sha)
        else:
            if not arguments.run:
                run_runtime_smoke(sidecar, build_sha=sha)
            with tempfile.TemporaryDirectory(
                prefix="electron-stage-", dir=_build_directory(root)
            ) as temporary:
                stage = Path(temporary)
                _stage_desktop(root, sidecar, stage, build_sha=sha)
                if arguments.run:
                    _run_desktop(root, stage, target=arguments.target)
                else:
                    package = _build_installer(root, stage, target=arguments.target)
                    print(f"desktop_package={package}")
    except (
        DesktopPackageError,
        SidecarBuildError,
        PackageSmokeError,
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"desktop package failed: {exc}", file=sys.stderr)
        return 2
    print(f"desktop_build_sha={sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
