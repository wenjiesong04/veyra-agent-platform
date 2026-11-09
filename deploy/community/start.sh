#!/bin/sh
set -eu

python -m alembic -c backend/migrations/community/alembic.ini upgrade head
exec python -m uvicorn veyra_agent_platform.community.app:app \
  --host "${VEYRA_COMMUNITY_HOST:-0.0.0.0}" \
  --port "${VEYRA_COMMUNITY_PORT:-8000}" \
  --log-level "${VEYRA_COMMUNITY_LOG_LEVEL:-info}"
