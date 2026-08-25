# ADR 0001: Portable Project and Agent contracts

## Status

Accepted — V1.

## Decision

- A Project root contains exactly one `project.vproject.yaml`, with a stable UUIDv7
  `project_id` and an explicit non-empty list of Agent UUIDv7 identities. Each has
  a separate user-facing slug and an exact `agents/<slug>` directory path.
- Portable Agents use strict `*.vagent.yaml` source contracts. They may compose
  only Start, Agent, Tool, Condition, Transform, HumanApproval, Verifier, and
  Output nodes. Unknown components and fields are rejected.
- Agent source contains secret *references* only. Secret values, arbitrary
  executable components, and transient run data are absent by contract.
- Source, behavior, and dependency lock receive independent canonical SHA-256
  projections. A separately normalized raw UTF-8/LF/NFC file digest is used for
  file bytes. UI/documentation changes affect source only; semantic changes to
  prompts, permissions, transitions, models, or verifier data affect behavior.
- Runtime commands and events are versioned strict wire contracts. IDs are UUIDv7
  text. Only enumerated run-level events may carry `node_id: null`.
- Graphs are DAGs in V1. Every component declares exactly one edge per supported
  output port; required verifier checks and Verifier-node checks are identical.
- Execution behavior hashes exclude Agent UUID/slug and presentation data so
  import and Fork remapping is behavior-stable. Outputs are a one-to-one
  declaration-to-Output-node mapping, and graph input is bounded to 128 nodes
  and 256 transitions before semantic traversal.
- Factory Blueprints require closed capability and UI-suggestion objects. Their
  single-file JSON Schema contains only internal references for structured output.
- Project manifests set a listed default Agent UUID and bounded resource policy.
  Parsed contract maps/lists are recursively frozen; Tool node references must
  appear by exact version in the lock; event timestamps are UTC RFC 3339 `Z`.
- Runtime wire contracts freeze the V1 RunState and NodeState vocabularies. An
  explicit per-kind node-ID table keeps only run lifecycle events run-scoped,
  while node/tool/approval/input/artifact/checkpoint/verification events are
  node-scoped;
  controls use the matching explicit command table.

## Consequences

Studio, Runtime, and future generated clients share a fail-closed portable
boundary without importing local persistence or execution code. The YAML files
are JSON-compatible YAML in the initial fixtures so fixture validation does not
silently depend on a developer-installed YAML parser.

The committed JSON Schemas mirror the structural contract. This bootstrap does
not install `jsonschema`; production request handling must use an RFC 2020-12
validator in addition to the pure Python semantic validator.
