# ADR 0001: Portable Project and Agent contracts

## Status

Accepted — V1.

## Decision

- A Project root contains exactly one `project.vproject.yaml`, with a stable UUIDv7
  `project_id` and an explicit non-empty list of relative `agents/` directories.
- Portable Agents use strict `*.vagent.yaml` source contracts. They may compose
  only Start, Agent, Tool, Condition, Transform, HumanApproval, Verifier, and
  Output nodes. Unknown components and fields are rejected.
- Agent source contains secret *references* only. Secret values, arbitrary
  executable components, and transient run data are absent by contract.
- Source, behavior, and dependency lock receive independent canonical SHA-256
  projections. UI/documentation changes affect source only; semantic changes to
  prompts, permissions, transitions, models, or verifier data affect behavior.
- Runtime commands and events are versioned strict wire contracts. IDs are UUIDv7
  text. Only enumerated run-level events may carry `node_id: null`.

## Consequences

Studio, Runtime, and future generated clients share a fail-closed portable
boundary without importing local persistence or execution code. The YAML files
are JSON-compatible YAML in the initial fixtures so fixture validation does not
silently depend on a developer-installed YAML parser.
