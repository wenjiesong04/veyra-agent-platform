# Veyra node packages

Each platform capability is a directory:

```text
resources/nodes/<family>/<id>/node.yaml
```

`node.yaml` is the only authored source for Components, Tools, MCP
descriptors, Skills, Policies, and Templates. The local Resource Catalog
scans these packages at process start, validates them, and computes each
descriptor's content hash. `spec.ui` is Studio palette metadata; it is not
sent to Factory and does not change the lock hash.

A model may reference only entries marked `factory_selectable`.
`runtime_status` and `availability` are authoritative. Adding an executable
node requires a platform-owned adapter and review. A model-generated special
node remains a quarantined declarative proposal until a separate
human-reviewed promotion flow exists.
