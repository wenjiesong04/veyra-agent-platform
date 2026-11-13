"""Run static and optional real-process checks for the desktop package lane."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from build_sidecar import SUPPORTED_TARGETS, default_target, repository_root

LOCAL_HOST = "127.0.0.1"
HEALTH_PATH = "/api/v1/health"


class PackageSmokeError(RuntimeError):
    """The package contract or the local sidecar process is invalid."""


def check_static_contract(root: Path, *, target: str) -> None:
    desktop = root / "apps" / "desktop"
    try:
        config = json.loads(
            (desktop / "electron-builder.json").read_text(encoding="utf-8")
        )
        manifest = json.loads((desktop / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageSmokeError("Electron desktop config cannot be read") from exc

    if target not in SUPPORTED_TARGETS:
        raise PackageSmokeError(f"unsupported desktop package target: {target}")
    if manifest.get("main") != "electron/main.cjs":
        raise PackageSmokeError("Electron main entry must point to the desktop shell")
    names = {"renderer", "sidecar", "build-info.json"}
    resources = config.get("extraResources")
    if (
        not isinstance(resources, list)
        or len(resources) != len(names)
        or any(not isinstance(resource, dict) for resource in resources)
        or {(item.get("from"), item.get("to")) for item in resources}
        != {
            (
                f"../../build/desktop-package/${{env.VEYRA_ELECTRON_STAGE_NAME}}/{name}",
                name,
            )
            for name in names
        }
    ):
        raise PackageSmokeError(
            "Electron must bundle the staged renderer, Local sidecar, and "
            "build identity"
        )

    if "/build/" not in (root / ".gitignore").read_text(encoding="utf-8").splitlines():
        raise PackageSmokeError("generated desktop packages must be ignored by Git")
    print("static_contract=ok")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((LOCAL_HOST, 0))
        return int(listener.getsockname()[1])


def _environment(data_root: Path, port: int, build_sha: str) -> dict[str, str]:
    system_keys = (
        (
            "SYSTEMROOT",
            "WINDIR",
            "SYSTEMDRIVE",
            "COMSPEC",
            "USERPROFILE",
            "APPDATA",
            "LOCALAPPDATA",
            "TEMP",
            "TMP",
        )
        if sys.platform == "win32"
        else ("HOME", "TMPDIR", "LANG", "LC_ALL")
    )
    inherited = {key: os.environ[key] for key in system_keys if os.environ.get(key)}
    system_path = (
        str(Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32")
        if sys.platform == "win32"
        else "/usr/bin:/bin:/usr/sbin:/sbin"
    )
    database_path = (data_root / "v1" / "local" / "app.sqlite3").as_posix()
    inherited.update(
        {
            "PATH": system_path,
            "VEYRA_LOCAL_MODE": "release",
            "VEYRA_LOCAL_HOST": LOCAL_HOST,
            "VEYRA_LOCAL_PORT": str(port),
            "VEYRA_LOCAL_DATABASE_URL": f"sqlite+aiosqlite:///{database_path}",
            "VEYRA_LOCAL_PROJECT_STORAGE_ROOT": str(data_root / "v1" / "projects"),
            "VEYRA_BUILD_SHA": build_sha,
            "VEYRA_APP_VERSION": "0.1.0",
            "PYTHONNOUSERSITE": "1",
        }
    )
    return inherited


def _health(port: int) -> dict[str, Any]:
    connection = http.client.HTTPConnection(LOCAL_HOST, port, timeout=0.5)
    try:
        connection.request("GET", HEALTH_PATH, headers={"Connection": "close"})
        response = connection.getresponse()
        if response.status != 200:
            raise PackageSmokeError(f"health returned HTTP {response.status}")
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()
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
        except (
            OSError,
            http.client.HTTPException,
            ValueError,
            PackageSmokeError,
        ) as exc:
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
        if sys.platform == "win32":
            # PyInstaller's one-file bootloader owns the real service process.
            result = subprocess.run(
                ["taskkill.exe", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
                timeout=10,
            )
            if result.returncode != 0 and process.poll() is None:
                raise PackageSmokeError(
                    "could not stop the Windows sidecar process tree"
                )
        else:
            process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait(timeout=5)
        raise PackageSmokeError("sidecar did not stop after termination") from exc
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
        if sys.platform == "win32":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
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
    parser.add_argument("--target", choices=SUPPORTED_TARGETS, default=default_target())
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
