#!/bin/sh
set -eu

if [ "${1:-}" != "--confirm" ] || [ -z "${2:-}" ]; then
  printf '%s\n' 'Usage: restore.sh --confirm /absolute/path/to/community.dump' >&2
  exit 2
fi
backup_path=$2
if [ ! -f "$backup_path" ]; then
  printf '%s\n' 'Backup file does not exist.' >&2
  exit 2
fi

deployment_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
docker compose --env-file "$deployment_dir/.env" \
  --file "$deployment_dir/compose.yaml" \
  exec -T postgres pg_restore \
  --clean \
  --if-exists \
  --no-owner \
  --username "${POSTGRES_USER:-veyra}" \
  --dbname "${POSTGRES_DB:-veyra_community}" < "$backup_path"
printf 'postgres_restore=ok\n'
printf '%s\n' 'blob_restore=run_the_corresponding_blob-store_tar_restore_before_starting_the_app'
