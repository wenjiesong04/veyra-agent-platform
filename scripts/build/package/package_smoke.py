"""Run static and optional real-process checks for the desktop package lane."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

TARGET = "aarch64-apple-darwin"
LOCAL_HOST = "127.0.0.1"
HEALTH_PATH = "/api/v1/health"


class PackageSmokeError(RuntimeError):
    """The package contract or the local sidecar process is invalid."""


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def check_static_contract(root: Path, *, target: str) -> None:
    config_path = root / "apps" / "desktop" / "src-tauri" / "tauri.conf.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageSmokeError(f"Tauri config cannot be read: {config_path}") from exc

    bundle = config.get("bundle")
    build = config.get("build")
    app = config.get("app")
    if not isinstance(bundle, dict) or bundle.get("externalBin") != [
        "binaries/veyra-local"
    ]:
        raise PackageSmokeError("Tauri must bundle exactly the Local sidecar")
    if bundle.get("resources"):
        raise PackageSmokeError("Tauri resources must not contain runtime data")
    if (
        not isinstance(build, dict)
        or build.get("frontendDist") != "../../../web/apps/desktop/dist"
    ):
        raise PackageSmokeError(
            "Tauri frontendDist must point at the Desktop web build"
        )
    if not isinstance(app, dict):
        raise PackageSmokeError("Tauri app configuration is missing")
    csp = str(app.get("security", {}).get("csp", ""))
    if "127.0.0.1:*" not in csp:
        raise PackageSmokeError("Tauri CSP must permit the loopback Local API")
    if "community" in " ".join(str(value) for value in bundle.get("externalBin", [])):
        raise PackageSmokeError("Community must not be packaged as a Local sidecar")
    if target != TARGET:
        raise PackageSmokeError(f"unsupported desktop package target: {target}")

    ignore_path = root / ".gitignore"
    ignore_text = ignore_path.read_text(encoding="utf-8")
    if "apps/desktop/src-tauri/binaries/" not in ignore_text:
        raise PackageSmokeError("generated sidecars must be ignored by Git")
    print("static_contract=ok")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((LOCAL_HOST, 0))
        return int(listener.getsockname()[1])


def _environment(data_root: Path, port: int, build_sha: str) -> dict[str, str]:
    inherited = {
        key: os.environ[key]
        for key in ("HOME", "TMPDIR", "LANG", "LC_ALL")
        if os.environ.get(key)
    }
    inherited.update(
        {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "VEYRA_LOCAL_MODE": "release",
            "VEYRA_LOCAL_HOST": LOCAL_HOST,
            "VEYRA_LOCAL_PORT": str(port),
            "VEYRA_LOCAL_DATABASE_URL": (
                f"sqlite+aiosqlite:///{data_root / 'v1' / 'local' / 'app.sqlite3'}"
            ),
            "VEYRA_LOCAL_PROJECT_STORAGE_ROOT": str(data_root / "v1" / "projects"),
            "VEYRA_BUILD_SHA": build_sha,
            "VEYRA_APP_VERSION": "0.1.0",
            "PYTHONNOUSERSITE": "1",
        }
    )
    return inherited


def _health(port: int) -> dict[str, Any]:
    request = Request(
        f"http://{LOCAL_HOST}:{port}{HEALTH_PATH}",
        headers={"Connection": "close"},
    )
    with urlopen(request, timeout=0.5) as response:  # noqa: S310
        if response.status != 200:
            raise PackageSmokeError(f"health returned HTTP {response.status}")
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise PackageSmokeError("health response is not a JSON object")
    return payload


def _wait_for_health(
    port: int, build_sha: str, process: subprocess.Popen[bytes]
) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    last_error = "no health response"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = (
                process.stderr.read().decode("utf-8", errors="replace")
                if process.stderr
                else ""
            )
            raise PackageSmokeError(
                "sidecar exited before health "
                f"({process.returncode}): {stderr[-2_000:]}"
            )
        try:
            payload = _health(port)
        except (OSError, URLError, ValueError, PackageSmokeError) as exc:
            last_error = str(exc)
            time.sleep(0.2)
            continue
        if payload.get("build_sha") != build_sha:
            raise PackageSmokeError(
                "health build SHA mismatch: "
                f"expected {build_sha}, got {payload.get('build_sha')}"
            )
        if payload.get("service") != "local":
            raise PackageSmokeError(
                f"health service mismatch: {payload.get('service')}"
            )
        if payload.get("status") == "ok" and payload.get("database_ready") is True:
            return payload
        last_error = f"health not ready: {payload}"
        time.sleep(0.2)
    raise PackageSmokeError(f"sidecar health timeout: {last_error}")


def _stop(process: subprocess.Popen[bytes], port: int) -> None:
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait(timeout=5)
        raise PackageSmokeError("sidecar did not stop after SIGTERM") from exc
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((LOCAL_HOST, port), timeout=0.1):
                pass
        except OSError:
            return
        time.sleep(0.1)
    raise PackageSmokeError(f"sidecar port {port} remained open after process exit")


def _check_port_conflict(sidecar: Path, build_sha: str) -> None:
    port = _free_port()
    with tempfile.TemporaryDirectory(
        prefix="veyra-package-port-conflict-"
    ) as temporary:
        data_root = Path(temporary) / "app-data"
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((LOCAL_HOST, port))
        listener.listen(1)
        process = subprocess.Popen(
            [str(sidecar)],
            cwd=temporary,
            env=_environment(data_root, port, build_sha),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            # The Local lifespan migrates an empty SQLite database before
            # uvicorn attempts to bind. Give that real startup path the same
            # bounded window as the health probe, then require a non-zero exit.
            deadline = time.monotonic() + 35
            while process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.1)
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
                raise PackageSmokeError(
                    "sidecar did not fail on a loopback port conflict"
                )
            if process.returncode == 0:
                raise PackageSmokeError(
                    "sidecar unexpectedly succeeded on a port conflict"
                )
        finally:
            listener.close()
    print("port_conflict=ok")


def run_runtime_smoke(sidecar: Path, *, build_sha: str) -> None:
    if not sidecar.is_file() or not os.access(sidecar, os.X_OK):
        raise PackageSmokeError(f"executable sidecar is missing: {sidecar}")
    with tempfile.TemporaryDirectory(prefix="veyra-package-health-") as temporary:
        temporary_root = Path(temporary)
        data_root = temporary_root / "app-data"
        sentinel = data_root / "v1" / "projects" / "upgrade-sentinel.txt"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_text("keep across app upgrades\n", encoding="utf-8")
        port = _free_port()
        process = subprocess.Popen(
            [str(sidecar)],
            cwd=temporary,
            env=_environment(data_root, port, build_sha),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            payload = _wait_for_health(port, build_sha, process)
            database_path = data_root / "v1" / "local" / "app.sqlite3"
            if not database_path.is_file():
                raise PackageSmokeError(
                    "sidecar did not create the application database"
                )
            if not sentinel.is_file():
                raise PackageSmokeError(
                    "sidecar overwrote the existing Project data root"
                )
            if any(
                path.name in {".env", "credentials.json"}
                for path in data_root.rglob("*")
            ):
                raise PackageSmokeError("sidecar wrote a forbidden credential file")
            print(f"health_status={payload.get('status')}")
            print(f"health_build_sha={payload.get('build_sha')}")
            print(f"health_port={port}")
        finally:
            _stop(process, port)
    print("sidecar_stop=ok")
    _check_port_conflict(sidecar, build_sha)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sidecar", type=Path)
    parser.add_argument("--build-sha")
    parser.add_argument("--target", default=TARGET)
    parser.add_argument("--static-only", action="store_true")
    arguments = parser.parse_args()
    root = repository_root()
    try:
        check_static_contract(root, target=arguments.target)
        if arguments.sidecar is None or arguments.static_only:
            print("runtime_health_probe=skipped")
            return 0
        if not arguments.build_sha:
            raise PackageSmokeError("--build-sha is required with --sidecar")
        run_runtime_smoke(arguments.sidecar.resolve(), build_sha=arguments.build_sha)
    except (OSError, PackageSmokeError) as exc:
        print(f"package smoke failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
