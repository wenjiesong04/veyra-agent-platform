# ADR 0004: First local Runtime provider and Tool adapter

## Decision

The first Runtime slice supports two real execution paths:

- an `Agent` node calls one configured OpenAI-compatible model through the
  process environment; and
- `veyra.tool.filesystem.read@1.0.0` reads a UTF-8 file below the selected
  Project root.

Both paths remain synchronous inside the existing local Run service until the
durable command and event-stream wave is implemented. A run without a model
credential fails with `runtime_provider_not_configured`; it is never simulated.

## Boundaries

- Tool references must resolve to a ready Resource Catalog descriptor, match the
  immutable content hash in the Agent lock, and have the required permission
  subset in the source.
- The file adapter rejects absolute paths, traversal, symlinks, secret-like
  names and files larger than 1 MiB. It returns the text as the declared
  `result` value and records only digests and a relative path in the Run receipt.
- Model responses are mapped only to declared Agent outputs. String outputs use
  the final response text; object, array, number and boolean outputs require
  matching JSON values.
- Shell, write, network, MCP, HumanApproval, checkpoints, cancellation and
  streaming remain explicit unsupported states. They are not represented as
  fake successful adapters.

## Consequences

The Resource Library can now honestly mark one Tool as runnable and Factory can
select it. The next Runtime wave can add a permission broker, durable commands,
approval/checkpoint persistence and additional adapters without changing the
portable Agent source format.
