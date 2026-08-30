# Veyra node catalog

`catalog.v1.json` is the checked-in, versioned definition of the platform
nodes that Factory and Studio may resolve. It contains graph Components, Tools,
MCP descriptors, Skills, Policies, and Forkable Templates.

The local Resource Catalog validates this file and computes each descriptor's
content hash at load time. A model may reference only entries marked
`factory_selectable`; `runtime_status` and `availability` are authoritative.
Adding a new executable node requires a platform-owned adapter and review. A
model-generated special node remains a quarantined declarative proposal until a
separate human-reviewed promotion flow exists.
