# Veyra Agent Platform

Veyra is a local-first AI Agent workspace. Desktop and the Local API create,
inspect, run, control, and version user-owned Agents. Community is the
separate account and release registry. There is no Cloud data plane.

The repository is a greenfield implementation. The legacy Veyra repository is
read-only migration evidence and is never a runtime dependency.

## V1 products

- Desktop (`5173`): the local workspace for Projects, Chat/Builder, Studio,
  Resources, Knowledge, Runs/Monitor, and Community publish/discovery/import.
- Public site (`5174`): the anonymous product showcase, plus the Community
  catalog and account pages. It does not host Cloud Projects, Chat, Files, or
  Runs.
- Local API (`8771`): the local Project, Builder, Runtime, Knowledge, Resource,
  Import, and Orchestrator service. Builder and Chat call the configured model
  provider directly from this process.
- Community API (`8772`): accounts and the immutable Agent/Plugin release
  registry. It does not execute Agents and does not own a Cloud data plane.

## Development baseline

- Python 3.11.15 in the dedicated Conda environment `veyra-agent-platform`
- FastAPI, Pydantic, SQLAlchemy, Alembic, and SQLite/PostgreSQL
- React 19, TypeScript 5.9, Vite 7, and npm workspaces
- Tauri 2 and a PyInstaller sidecar for the desktop release

The canonical product and engineering requirements are in
`docs/PROJECT_DESIGN.md`.

Current implementation status, module priorities, and acceptance evidence are
maintained in [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

Desktop and the Local API own Projects, Builder conversations, files, and
Runs. The public site does not read or write that local state. Community
account and release metadata stay on `8772`.

## Backend development

Activate the dedicated Conda environment before local work:

```sh
conda activate veyra-agent-platform
make install
make check
```

`make install` installs the hashed dev lock with `--require-hashes`, then
installs the local package with `--no-deps --no-build-isolation`. Runtime-only
environments use `make install-runtime`. The runtime and dev lock files are the
only committed dependency locks. Refresh both generated locks deterministically
with `make lock-refresh`; the lock files pin versions and artifact hashes.

The local Runtime uses the cross-platform `keyring` abstraction for device
credentials: macOS Keychain, Windows Credential Manager, or a Linux Secret
Service/KWallet backend. A missing system credential service is reported as an
unavailable credential store; it is never silently replaced with a plaintext
file or process-memory store. Process environment variables remain an explicit
development fallback for deployment-owned Platform credentials only.
`make linux-lock-check` validates the dev lock with Linux wheel resolution.

To configure the model Runtime/Factory and GitHub adapters, open Desktop
Settings and save the API key or token in the Credentials panels. Project and
Agent sources store only opaque references; values are never written to Project
files or local SQLite. `MOONSHOT_API_KEY` and `GITHUB_TOKEN` remain supported
for headless development and CI.

To bring in an external Agent, open a Project's Add Agent menu and choose
Import external Agent. Veyra accepts a generic YAML file, a folder, or a ZIP
archive. It first shows a compatibility report, then creates an editable
Veyra Agent draft only after confirmation; ZIP is treated as a transport and
external code or dependency files are never executed automatically.

## Desktop release candidate

The Desktop shell and macOS arm64 packaging contract are documented in
[`docs/desktop_packaging.md`](docs/desktop_packaging.md). The static contract
check does not require Rust or PyInstaller:

```sh
python3 scripts/build/package/package_smoke.py --static-only \
  --target aarch64-apple-darwin
```
