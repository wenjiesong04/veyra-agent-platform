#!/bin/sh
set -eu

deployment_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
backup_dir="${VEYRA_BACKUP_DIR:-$deployment_dir/backups}"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$backup_dir"
output="$backup_dir/community-$stamp.dump"

docker compose --env-file "$deployment_dir/.env" \
  --file "$deployment_dir/compose.yaml" \
  exec -T postgres pg_dump \
  --format=custom \
  --no-owner \
  --username "${POSTGRES_USER:-veyra}" \
  --dbname "${POSTGRES_DB:-veyra_community}" > "$output"
chmod 0600 "$output"
printf 'postgres_backup=%s\n' "$output"

blob_output="$backup_dir/blob-store-$stamp.tar.gz"
docker compose --env-file "$deployment_dir/.env" \
  --file "$deployment_dir/compose.yaml" \
  exec -T minio tar -C /data -czf - . > "$blob_output"
chmod 0600 "$blob_output"
printf 'blob_store_backup=%s\n' "$blob_output"
