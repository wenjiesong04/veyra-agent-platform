# ADR 0002: Studio canonical IR and first executable Runtime slice

## Status

Accepted — V1-2 first vertical slice.

## Context

Veyra already owns a strict `AgentSource`, project-local `agent.vagent.yaml`,
mutable Draft revision/ETag, validation, and immutable Agent versions. The next
surface must let a user add, connect, move, inspect, and edit graph nodes without
turning the Canvas into a second source of truth or presenting an animation as a
working Agent.

A visual graph is temporarily incomplete while a user is wiring it. The portable
source contract is deliberately stricter: it requires one Start node, at least
one Output node, an acyclic reachable graph, exact output ports, registered Tool
locks, and consistent verification declarations.

## Decision

- `AgentSource` remains the only persisted behavior definition. Canvas nodes,
  edges, positions, Form fields, and Source text are projections of the same
  in-memory Studio IR.
- Studio may hold an incomplete graph locally, but it does not overwrite the
  project source until the graph passes client diagnostics and the server's
  strict validation. The project file therefore remains the last valid Agent.
- Draft writes use the existing revision, ETag, and idempotency boundaries.
  Conflicts are visible and require an explicit reload; Studio never silently
  overwrites another window or an external file edit.
- Node positions are stored only under `ui.positions`. Moving a node changes the
  file/source hash but not the behavior hash.
- The component palette is backed by a server-owned registry. It exposes all
  eight V1 component types, their editable fields and output ports, plus an
  explicit Runtime-support state. Unknown components, tools, permissions, and
  dependency locks remain rejected.
- The first executable local slice supports Start, safe Transform interpolation,
  an allowlisted Condition DSL, allowlisted Verifier checks, and Output. A
  no-tools Agent node may run only through an explicitly configured provider
  adapter with bounded timeout/output and redacted receipts.
- Tool and HumanApproval remain designable portable nodes. The current Runtime
  executes `HumanApproval` as a durable wait plus `approve`/`reject`/`stop`
  commands, and executes catalogued filesystem read/write adapters. Unsupported
  tools still fail as `runtime_not_supported` or `tool_runtime_unavailable`;
  the executor never skips them or reports a successful run.
- Every test run validates the current source, materializes or reuses an immutable
  Agent version, and records a Run plus ordered events outside the Project
  directory. Runtime state and provider secrets never enter Agent source.
- Agent routes use an Agent-context sidebar: New chat, Orchestration, Data
  analysis, the existing Project tree, and a Recent section. Recent stays an
  honest empty state until backed by durable conversation/run data.
- The main Agent route remains intentionally minimal in this slice. Orchestration
  owns the visual Studio, while Data analysis is a separate route prepared for
  real Run metrics.

## First-slice acceptance

1. Open a real Project Agent and load its current Draft.
2. Add, drag, connect, edit, and remove Canvas nodes and edges.
3. Keep Canvas, Form, and Source projections on one in-memory definition.
4. Block invalid saves with actionable diagnostics.
5. Save with revision/ETag, validate on the server, and commit an immutable
   version without changing behavior hash for a position-only edit.
6. Execute a supported graph, persist ordered events, reload its result, and show
   unsupported/provider-not-configured failures without fixture substitution.
7. Preserve the existing Project sidebar and responsive light/dark shell outside
   Agent context.

## Consequences

The first Studio is useful before high-authority tools are enabled, while the
portable file and Runtime remain fail-closed. Later Tool Proxy, approvals,
checkpoints, MCP, and Run Canvas work can extend the registry and executor without
replacing the editor's canonical mapping.
