# Veyra Agent Platform

Veyra is a local-first platform for creating, inspecting, running, controlling,
versioning, and sharing user-owned Agents.

The repository is a greenfield implementation. The legacy Veyra repository is
read-only migration evidence and is never a runtime dependency.

## V1 products

- Desktop: Project Library, Factory, Studio, local Runtime, Run Canvas,
  Orchestrator, and Monitor.
- Community: account registration, creator profiles, Agent publication,
  discovery, download, Fork, Star, version-bound Review, and moderation.

## Development baseline

- Python 3.11.15 in the dedicated Conda environment `veyra-agent-platform`
- FastAPI, Pydantic, SQLAlchemy, Alembic, and SQLite/PostgreSQL
- React 19, TypeScript 5.9, Vite 7, and npm workspaces
- Tauri 2 and a PyInstaller sidecar for the desktop release

The canonical product and engineering requirements are in
`docs/PROJECT_DESIGN.md`.

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

The common locks intentionally exclude `keyring`; the local macOS desktop
sidecar uses the system `security` Keychain command for host credentials, with
process environment variables retained as a development fallback.
`make linux-lock-check` validates the dev lock with Linux wheel resolution.

To configure the model Runtime/Factory and GitHub adapters, open Desktop
Settings and save the API key or token in the Credentials panels. Project and
Agent sources store only opaque references; values are never written to Project
files or local SQLite. `MOONSHOT_API_KEY` and `GITHUB_TOKEN` remain supported
for headless development and CI.
