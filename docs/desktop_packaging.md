# Desktop packaging

Electron packages the Desktop web build with a PyInstaller executable for the
Local API. Build on the target platform. Use Apple Silicon macOS for the arm64
DMG, Windows x64 for the NSIS installer, and Linux x64 for the AppImage.

## Build

Activate the Python 3.11 environment from the [quick start](../README.md#quick-start)
and install the locked backend dependencies. On Windows, install
`requirements/desktop-windows-py311.txt` together with the runtime lock. Install
PyInstaller 6.22.0 in that environment.

From the repository root, install the two JavaScript dependency sets.

```sh
npm --prefix web ci
npm --prefix apps/desktop ci
```

Run the packager for the current host.

```sh
python scripts/build/package/package.py
```

The packager uses the current commit SHA by default. It builds the web assets and
native Local executable, checks the sidecar, then asks Electron Builder to make
the installer. Build output goes to `build/desktop-package/dist/`.

To launch the same native shell before building an installer, run
`npm --prefix apps/desktop run dev` with the packaging dependencies installed.
This builds and opens an unpacked Veyra Agent Platform app with its native name
and icon.

## Native workspace

Electron serves the packaged renderer from `veyra://desktop/`. It starts the
bundled Local service on loopback, waits for the expected build and database
readiness, then opens the workspace. A Community session is needed for
community actions in the system browser. To configure that link, set
`VITE_COMMUNITY_SITE_URL` during the build.

The bundle identifier and platform data root preserve the existing Desktop
workspace layout. Project folders, SQLite, run objects, and user credentials
live outside the installer. The Local process gets an allowlisted environment
and exits with the desktop application.

## Verification and distribution

Run the static package contract check with
`python scripts/build/package/package_smoke.py --static-only`. The package
workflow also starts Electron with an isolated workspace to exercise the
renderer and Local API. On macOS it verifies the DMG and the application
signature. On Windows and Linux it checks the packaged app before keeping the
installer.

Push the source revision before running the three platform builds in GitHub
Actions. Download the resulting installers from the workflow artifacts for
testing. After a clean install and upgrade check on each target, sign the
installers as appropriate and attach them to a GitHub Release for the same
source tag.
