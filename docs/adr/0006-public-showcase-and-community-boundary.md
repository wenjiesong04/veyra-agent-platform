# ADR 0006: Public Showcase and Community boundary

## Status

Accepted — 2026-09-23.

## Decision

- `5173` is the Veyra Desktop product workspace and the interaction surface for
  Community discovery, publishing, release inspection, starring, and import.
- `8771` is the loopback Local API for Project-owned source, Builder, Studio,
  Runtime, Knowledge, Resources, Import, approvals, receipts, and Orchestrator.
- `8772` is the separate Community API for accounts and the existing immutable
  release registry, metadata, moderation, feedback, and artifact downloads.
  Community never runs downloaded Agents.
- `5174` is the anonymous Veyra Public Showcase: product introduction, current
  capabilities, local-first/security boundaries, Getting Started, repository
  documentation, and truthful desktop distribution status.
- The `5174` Showcase is independent of `8772` for its core routes. It does not
  expose Registry account, Published, Starred, Following, publish, or import
  management workflows. A read-only Community section may be considered later,
  but it is optional and must fail independently of the core Showcase.
- `web/apps/community` retains its workspace/package name in this slice. The
  product boundary is defined by the app entrypoint and behavior, not the
  historical directory name.

## Rationale

The Desktop serves people doing Agent work; the Public Showcase serves visitors
learning what Veyra is. Treating a version registry as the website duplicated
Community product UI and made the public site depend on account and Registry
availability. The Registry remains useful for immutable, inspectable sharing,
but is a service capability rather than a website identity.

## Non-goals

- Do not delete the `8772` service, Registry schema, release data, or Desktop
  Community pages.
- Do not redesign the Agent sharing protocol or add Community resource types.
- Do not implement production Community deployment in this slice.
- Do not invent public download artifacts, testimonials, usage metrics, or
  customer claims.
