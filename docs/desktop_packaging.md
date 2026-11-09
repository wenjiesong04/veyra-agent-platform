# Desktop release candidate packaging

This repository now has a narrow macOS arm64 release lane. It packages the
Desktop React application with a Tauri shell and one PyInstaller Local API
sidecar. Community is still a separate service and is not bundled into the
Desktop application.

## Build

The release target is `aarch64-apple-darwin` and the build identity is the
source commit SHA:

```sh
cd /Users/spectre/PycharmProjects/veyra-agent-platform
VEYRA_BUILD_SHA="$(git rev-parse HEAD)" \
  /opt/anaconda3/envs/veyra-agent-platform/bin/python \
  scripts/build/package/package.py
```

The command requires Python 3.11, the locked project dependencies, PyInstaller
6.x, Node/npm, the Tauri CLI 2.11.4, and a Rust toolchain. Rust installed under
`~/.cargo/bin` is accepted even when that directory is not on `PATH`.

The generated paths are:

```text
apps/desktop/src-tauri/binaries/veyra-local-aarch64-apple-darwin
apps/desktop/src-tauri/target/aarch64-apple-darwin/release/bundle/dmg/*.dmg
```

Generated binaries and Rust output are ignored by Git. They must not be
committed as source artifacts.

## Runtime contract

The Tauri shell owns Local sidecar startup and shutdown. The sidecar is started
with no command-line arguments and with an explicitly cleared environment. It
receives only:

```text
VEYRA_LOCAL_MODE=release
VEYRA_LOCAL_HOST=127.0.0.1
VEYRA_LOCAL_PORT=8771
VEYRA_LOCAL_DATABASE_URL=sqlite+aiosqlite:///<app-data>/v1/local/app.sqlite3
VEYRA_LOCAL_PROJECT_STORAGE_ROOT=<app-data>/v1/projects
VEYRA_BUILD_SHA=<source commit SHA>
VEYRA_APP_VERSION=0.1.0
```

The shell reserves `127.0.0.1:8771` before spawning. It then polls
`GET /api/v1/health` and requires `service=local`, `status=ok`,
`database_ready=true`, and an exact `build_sha` match. A missing sidecar,
occupied port, early exit, health timeout, or SHA mismatch fails the release
startup. A normal window close and the Tauri exit event kill the owned child.

The packaged frontend is built with
`http://127.0.0.1:8771/api/v1` as its Local API base. The browser-only relative
`/api/v1` base remains the development fallback for the Vite app.

## Data boundary

The application data directory is resolved by Tauri at runtime using the bundle
identifier. Only these mutable paths are passed to the Local sidecar:

```text
<app-data>/v1/local/       SQLite database and migration backups
<app-data>/v1/projects/   managed Project directories
<app-data>/v1/objects/    content-addressed run/project objects
```

The Tauri bundle and PyInstaller input set contain no `.env`, Keychain values,
SQLite files, objects, run state, user Projects, user plugins, or Community
storage. Host credentials remain in the host Keychain; the release child does
not inherit `MOONSHOT_API_KEY` or `GITHUB_TOKEN`. Existing Project data is
outside the application bundle and is not reset or replaced during an app
upgrade. Local migrations retain the existing pre-migration backup behavior.

The sidecar spec includes only the Local source package, local migrations,
platform-owned node descriptors, and shared schemas required by the Local
service. It does not include the Community package or execute external plugin
code.

## Evidence commands

The static check is runnable without a Rust or PyInstaller installation:

```sh
python3 scripts/build/package/package_smoke.py \
  --static-only --target aarch64-apple-darwin
```

After a real sidecar build, the health probe exercises startup, exact SHA,
SQLite initialization, preservation of a pre-existing Project sentinel,
graceful stop, port release, and port-conflict failure:

```sh
VEYRA_BUILD_SHA="$(git rev-parse HEAD)" \
  /opt/anaconda3/envs/veyra-agent-platform/bin/python \
  scripts/build/package/package_smoke.py \
  --sidecar apps/desktop/src-tauri/binaries/veyra-local-aarch64-apple-darwin \
  --build-sha "$(git rev-parse HEAD)"
```

The GitHub Actions `desktop-package` job repeats the same checks on a clean
`macos-15` arm64 runner, then runs the Tauri build and asserts that exactly one
DMG exists under the target-specific release bundle directory. A local static
pass or a Rust compile pass is not a packaged-artifact proof; the real sidecar
and DMG steps are the release evidence.
