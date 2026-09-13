"""Build the macOS arm64 Tauri package after proving the Local sidecar."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from build_sidecar import TARGET, SidecarBuildError, build_sidecar, resolve_build_sha
from package_smoke import PackageSmokeError, check_static_contract, run_runtime_smoke

TAURI_CLI_VERSION = "2.11.4"


class DesktopPackageError(RuntimeError):
    """The complete desktop package lane could not run."""


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _cargo_path() -> Path:
    cargo = shutil.which("cargo")
    if cargo:
        return Path(cargo)
    candidate = Path.home() / ".cargo" / "bin" / "cargo"
    if candidate.is_file():
        return candidate
    raise DesktopPackageError(
        "cargo is required for the Tauri package; install Rust stable or "
        "add ~/.cargo/bin to PATH"
    )


def _run_tauri(root: Path, *, build_sha: str, target: str) -> Path:
    npm = shutil.which("npm")
    npx = shutil.which("npx")
    if not npm or not npx:
        raise DesktopPackageError("npm and npx are required for the Tauri package lane")
    cargo = _cargo_path()
    environment = os.environ.copy()
    # The release lane is also run locally on headless macOS hosts. Tauri's
    # DMG helper otherwise invokes Finder/AppleScript to arrange the volume,
    # which is not deterministic (and cannot run without a Finder session).
    # CI mode keeps the artifact creation path reproducible while preserving
    # the normal app bundle and DMG contents.
    environment.setdefault("CI", "true")
    environment["VEYRA_BUILD_SHA"] = build_sha
    environment["VEYRA_APP_VERSION"] = "0.1.0"
    environment["VITE_LOCAL_API_BASE_URL"] = "http://127.0.0.1:8771/api/v1"
    cargo_bin = str(cargo.parent)
    environment["PATH"] = cargo_bin + os.pathsep + environment.get("PATH", "")

    # Build the Desktop web assets explicitly so the release API base is not the
    # browser-only relative `/api/v1` fallback. Tauri repeats this through its
    # beforeBuildCommand for direct CLI invocations.
    try:
        subprocess.run(
            [npm, "--prefix", "web", "run", "build:desktop"],
            cwd=root,
            env=environment,
            check=True,
        )
        subprocess.run(
            [
                npx,
                "--yes",
                f"@tauri-apps/cli@{TAURI_CLI_VERSION}",
                "build",
                "--config",
                "apps/desktop/src-tauri/tauri.conf.json",
                "--target",
                target,
            ],
            cwd=root,
            env=environment,
            check=True,
        )
    except OSError as exc:
        raise DesktopPackageError(f"could not start the Tauri build: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        raise DesktopPackageError(
            f"Tauri package failed with exit code {exc.returncode}"
        ) from exc

    bundle_root = (
        root
        / "apps"
        / "desktop"
        / "src-tauri"
        / "target"
        / target
        / "release"
        / "bundle"
    )
    dmgs = sorted(bundle_root.glob("dmg/*.dmg"))
    if not dmgs:
        raise DesktopPackageError(
            f"Tauri completed without a macOS DMG under {bundle_root}"
        )
    if len(dmgs) != 1:
        raise DesktopPackageError(
            f"expected one release DMG under {bundle_root}, found {len(dmgs)}"
        )
    return dmgs[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=TARGET)
    parser.add_argument("--build-sha")
    arguments = parser.parse_args()
    root = repository_root()
    try:
        sha = resolve_build_sha(arguments.build_sha, root=root)
        check_static_contract(root, target=arguments.target)
        sidecar = build_sidecar(root=root, target=arguments.target, build_sha=sha)
        run_runtime_smoke(sidecar, build_sha=sha)
        package = _run_tauri(root, build_sha=sha, target=arguments.target)
    except (DesktopPackageError, SidecarBuildError, PackageSmokeError) as exc:
        print(f"desktop package failed: {exc}", file=sys.stderr)
        return 2
    print(f"desktop_package={package}")
    print(f"desktop_build_sha={sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
