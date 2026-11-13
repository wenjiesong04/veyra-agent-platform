"""Build the Local FastAPI executable bundled with Electron."""

from __future__ import annotations

import argparse
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

MAC_TARGET = "aarch64-apple-darwin"
WINDOWS_TARGET = "x86_64-pc-windows-msvc"
LINUX_TARGET = "x86_64-unknown-linux-gnu"
SUPPORTED_TARGETS = (MAC_TARGET, WINDOWS_TARGET, LINUX_TARGET)
_SHA = re.compile(r"^[0-9a-fA-F]{7,64}$")


class SidecarBuildError(RuntimeError):
    """The sidecar could not be built from the isolated build environment."""


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_target() -> str:
    return {"win32": WINDOWS_TARGET, "linux": LINUX_TARGET}.get(
        sys.platform, MAC_TARGET
    )


def sidecar_name(target: str) -> str:
    return "veyra-local.exe" if target == WINDOWS_TARGET else "veyra-local"


def _require_native_target(target: str) -> None:
    host = (sys.platform, platform.machine().lower())
    targets = {
        ("darwin", "arm64"): MAC_TARGET,
        ("win32", "amd64"): WINDOWS_TARGET,
        ("win32", "x86_64"): WINDOWS_TARGET,
        ("linux", "x86_64"): LINUX_TARGET,
    }
    if target not in SUPPORTED_TARGETS or targets.get(host) != target:
        raise SidecarBuildError(
            f"cannot build {target} on {host[0]}/{host[1]}; "
            "build on a native macOS arm64, Windows x64, or Linux x64 host"
        )


def resolve_build_sha(value: str | None = None, *, root: Path | None = None) -> str:
    candidate = (
        value.strip()
        if value is not None
        else os.environ.get("VEYRA_BUILD_SHA", "").strip()
    )
    if not candidate:
        try:
            candidate = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=root or repository_root(),
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise SidecarBuildError(
                "VEYRA_BUILD_SHA is required when git cannot resolve HEAD"
            ) from exc
    if _SHA.fullmatch(candidate) is None:
        raise SidecarBuildError(
            "VEYRA_BUILD_SHA must be a 7-64 character hexadecimal commit SHA"
        )
    return candidate.lower()


def _require_python() -> None:
    if sys.version_info[:2] != (3, 11):
        raise SidecarBuildError(
            "Python 3.11 is required for the locked sidecar build, "
            f"got {sys.version.split()[0]}"
        )
    try:
        import PyInstaller  # type: ignore[import-untyped]  # noqa: F401
    except ModuleNotFoundError as exc:
        raise SidecarBuildError(
            "PyInstaller is not installed in this Python environment; "
            "install the locked desktop build tool before packaging"
        ) from exc


def build_sidecar(
    *,
    root: Path | None = None,
    target: str | None = None,
    build_sha: str | None = None,
) -> Path:
    root = root or repository_root()
    target = target or default_target()
    _require_native_target(target)
    _require_python()
    sha = resolve_build_sha(build_sha, root=root)

    staging = root / "build" / "desktop-package" / "pyinstaller" / target
    dist_path = staging / "dist"
    work_path = staging / "work"
    dist_path.mkdir(parents=True, exist_ok=True)
    work_path.mkdir(parents=True, exist_ok=True)
    spec_path = root / "scripts" / "build" / "package" / "veyra-local.spec"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(spec_path),
        "--noconfirm",
        "--clean",
        "--distpath",
        str(dist_path),
        "--workpath",
        str(work_path),
    ]
    environment = os.environ.copy()
    environment["VEYRA_BUILD_SHA"] = sha
    try:
        subprocess.run(command, cwd=root, env=environment, check=True)
    except OSError as exc:
        raise SidecarBuildError(f"could not start PyInstaller: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        raise SidecarBuildError(
            f"PyInstaller failed with exit code {exc.returncode}"
        ) from exc

    built = dist_path / sidecar_name(target)
    if not built.is_file():
        raise SidecarBuildError(f"PyInstaller did not produce {built}")

    print(f"sidecar={built}")
    print(f"sidecar_build_sha={sha}")
    return built


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=SUPPORTED_TARGETS, default=default_target())
    parser.add_argument("--build-sha")
    arguments = parser.parse_args()
    try:
        build_sidecar(target=arguments.target, build_sha=arguments.build_sha)
    except SidecarBuildError as exc:
        print(f"sidecar build failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
