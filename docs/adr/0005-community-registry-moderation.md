# ADR 0005: Community package scanning and moderation boundary

## Decision

Community package publication keeps two explicit modes:

- development and test keep the runnable local registry slice with direct
  publication after AgentSource, UTF-8, size, and obvious credential-marker
  checks;
- production requires `VEYRA_COMMUNITY_REQUIRE_MODERATION=true` and a
  non-empty `VEYRA_COMMUNITY_MODERATOR_HANDLES` list. A validated upload is
  stored content-addressably with status `quarantined` until a configured
  moderator publishes or rejects it.

Every accepted package stores a `community.scan.v1` report containing the
completed checks and derived risk level. The report contains no secret values.
Every moderation decision appends an immutable receipt with moderator identity,
action, reason, and timestamp.

## API

- `GET /api/v1/registry/moderation/queue` lists quarantined versions for a
  configured moderator.
- `POST /api/v1/registry/agents/{owner}/{slug}/versions/{version}/moderate`
  accepts `publish` or `reject` plus a required reason.
- Public registry queries and downloads continue to select only `published`
  versions. Community never executes a submitted Agent.

## Boundaries

The first scan is intentionally bounded to the single YAML Agent package:
schema/UTF-8/marker checks are hard gates, while tool, network, filesystem,
Shell, Secret, Skill, verification, and risk metadata are shown before import.
Archive path/symlink scanning, dependency provenance, license checks, and a
long-lived moderation operations console remain subsequent work.
