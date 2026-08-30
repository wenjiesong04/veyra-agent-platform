# ADR 0004: First local Runtime provider and Tool adapter

## Decision

The first Runtime slice supports these real execution paths:

- an `Agent` node calls one configured OpenAI-compatible model through the
  host-side Runtime profile;
- `veyra.tool.filesystem.read@1.0.0` reads a UTF-8 file below the selected
  Project root; and
- `veyra.tool.filesystem.write@1.0.0` writes a UTF-8 file below the Project
  root after an approved `HumanApproval` node on the current path.

Tool execution records an authorization decision before any adapter effect.
Write, Shell, and similar high-authority tools remain approval-gated. A run
that reaches `HumanApproval` becomes `waiting`, persists a checkpoint and
approval request, and continues only through a durable `run_command`
(`approve`, `reject`, `stop`, `retry`).

Both model and Tool paths remain synchronous for the opening POST, while
node events are persisted as they happen and replayed over SSE. A run without
a model credential fails with `runtime_not_configured`; it is never simulated.

## Boundaries

- Tool references must resolve to a ready Resource Catalog descriptor, match the
  immutable content hash in the Agent lock, and have the required permission
  subset in the source.
- The file adapter rejects absolute paths, traversal, symlinks, secret-like
  names and files larger than 1 MiB. Read returns text as the declared
  `content` value. Write returns `{ written: true }` after an approved
  `HumanApproval`. Receipts record only digests and a relative path, never
  file contents.
- Model responses are mapped only to declared Agent outputs. String outputs use
  the final response text; object, array, number and boolean outputs require
  matching JSON values.
- Shell, network, MCP, and token streaming remain explicit unsupported states.
  They are not represented as fake successful adapters. `resume` is not used
  for approval waits; those waits continue through `approve` or `reject`.
  `GET .../runs/{run_id}/events` is a replayable SSE follow of persisted
  events. POST `/run` is still synchronous.

## Consequences

The Resource Library can now honestly mark filesystem read and write as
runnable, and Factory can select them. Write still requires a HumanApproval
node before compilation. The next Runtime wave can make POST `/run`
asynchronous and paint node state onto the Studio graph without changing the
portable Agent source format.
