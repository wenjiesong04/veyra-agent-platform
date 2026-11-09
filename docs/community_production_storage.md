# Community production storage

Community keeps its database and object storage separate from the Local
desktop service. Development and tests continue to use SQLite and local
directories. Production requires PostgreSQL and a private S3-compatible
bucket.

## Required production settings

```text
VEYRA_COMMUNITY_MODE=production
VEYRA_COMMUNITY_DATABASE_URL=postgresql+psycopg://...
VEYRA_COMMUNITY_OBJECT_STORAGE_BACKEND=s3
VEYRA_COMMUNITY_S3_ENDPOINT_URL=https://s3.example.com
VEYRA_COMMUNITY_S3_BUCKET=veyra-community
VEYRA_COMMUNITY_S3_REGION=us-east-1
VEYRA_COMMUNITY_S3_ACCESS_KEY_ID=...
VEYRA_COMMUNITY_S3_SECRET_ACCESS_KEY=...
```

The Community settings validator also requires a concrete build SHA, a
non-development auth secret, a public origin, package moderation, and at least
one moderator handle. S3 credentials are read as secret settings and are never
included in API responses, Project files, logs, or package manifests.

The storage adapter uses private path-style AWS Signature V4 requests. Agent
and Plugin Pack bytes use `packages/<sha256>` keys; avatars use random
non-content-addressed keys under `avatars/`. Package reads verify the returned
bytes against the content hash and fail closed if an object was corrupted.

## Local development

Leave `VEYRA_COMMUNITY_OBJECT_STORAGE_BACKEND` unset to keep the existing local
directory storage. No S3 service or credentials are needed for the normal
SQLite test harness.

The CI backend job runs Community migrations against both SQLite and a clean
PostgreSQL service. This proves database-dialect migration compatibility, but
it is not a deployment or backup/restore proof.

## Deployment baseline

`deploy/community/compose.yaml` starts PostgreSQL, MinIO, the Community
container, and Caddy in that order. `start.sh` upgrades the Community schema
before opening port 8000; Caddy is the only public-facing service. The
`/api/v1/ready` endpoint returns 503 until both the required migration head and
the private object-storage bucket are available, and the container health
checks use that endpoint. The `backup.sh` and guarded `restore.sh` helpers
cover the PostgreSQL metadata database. MinIO object backup, TLS issuance on
the target host, and a restore drill remain required before calling a public
deployment ready.

The external images in `compose.yaml` are pinned to immutable manifest digests.
Refresh a pin only after a registry manifest request returns 2xx and a real
`Docker-Content-Digest`; never hash a failed or empty response.
