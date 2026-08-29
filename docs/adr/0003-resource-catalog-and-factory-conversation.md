# ADR 0003: Resource Catalog and conversational Factory boundary

## Status

Accepted for the next V1 implementation wave.

## Context

The strict `AgentBlueprint` contract and eight graph Components already exist,
but the current Resource Library page is static. There is no versioned Tool,
MCP, Skill, or Policy catalog, and Factory has no Kimi client or multi-turn
session. Connecting Kimi directly would let the model invent capabilities that
the platform cannot resolve or run.

## Decision

- A server-owned Resource Catalog is the only capability source for Factory and
  Studio.
- Components define graph structure; Tools/MCP define executable capabilities;
  Skills are non-executable instruction assets; Policies constrain generation
  and Runtime; Templates are complete Forkable definitions.
- Every resource has an exact version, content hash, origin, availability,
  Factory selectability, Runtime support, compatibility, and permission
  requirements.
- MCP discovery never grants execution. Discovered tools are normalized and
  reviewed before becoming selectable Tool descriptors.
- Factory is a Project-scoped multi-turn conversation. It persists user-visible
  messages and summaries outside Project source, but never persists provider
  reasoning content.
- The configurable Kimi client discovers the requested model through
  `/v1/models` and currently defaults to `kimi-k3`.
- Kimi receives a bounded immutable catalog snapshot and a strict JSON Schema.
  The server resolves versions, compiles Skills, applies Policies, derives
  permissions and locks, and validates the graph.
- The repair loop is limited to three attempts and cannot broaden the catalog or
  permissions.
- Provider `reasoning_content` is request-chain-only and never persisted.
- Kimi K3 Structured Output uses `response_format.type=json_schema` with
  `strict: true`; only final `message.content` is parsed. Reasoning effort and
  maximum completion tokens are bounded configuration, and fixed sampling
  parameters are omitted.
- Missing capabilities produce a typed, quarantined Resource Draft. Generated
  executable code is never automatically registered, authorized, installed, or
  executed.
- Factory generation and Runtime model execution use separate provider profiles.
  Without a user-configured Runtime provider, an Agent remains designable,
  versionable, and exportable but cannot run model nodes.

## Initial slice

1. Replace the static Resource Library with a real catalog API and tabs for
   Components, Tools/MCP, Skills, Policies, and Templates.
2. Register the existing eight Components, a small set of built-in Skills and
   default Policies, plus only honestly supported Tool/MCP descriptors.
3. Add Factory session/message/generate endpoints with an injected Kimi
   transport and deterministic fake transport for tests.
4. Show the conversation, selected Resource Plan, missing capabilities, repair
   diagnostics, and explicit “Create Agent Draft” confirmation in Desktop.
5. Hand the resulting Draft to the existing Studio without running it.

## Consequences

The first Factory cannot fabricate a capability merely because a model emitted
its name. Resource authoring remains possible, including Kimi-assisted
specification and scaffolding, but it crosses a separate quarantine and review
boundary before any Agent can depend on it.
