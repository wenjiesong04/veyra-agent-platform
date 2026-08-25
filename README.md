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

