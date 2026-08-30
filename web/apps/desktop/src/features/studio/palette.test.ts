import { describe, expect, it } from "vitest";
import type { AgentSource, ResourceDescriptor } from "@veyra/api-contracts";
import { attachCatalogResource, catalogToolRequiresApproval, paletteFromCatalog } from "./palette";

const source: AgentSource = {
  schema_version: "1.0", agentspec_version: "26.1", component_type: "Flow", agent_id: "agent-1", slug: "review", name: "Review", description: "",
  inputs: {}, outputs: { result: "string" }, nodes: [{ id: "start", component_type: "Start" }], transitions: [],
  extensions: { veyra: { runtime_profile: "guarded", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } },
  ui: { positions: { start: { x: 0, y: 0 } } }, lock: {},
};

function tool(name: string, id: string, availability: ResourceDescriptor["availability"], extra: Partial<ResourceDescriptor> = {}): ResourceDescriptor {
  return {
    schema_version: "1.0",
    resource_id: `veyra.tool.${id}`,
    kind: "tool",
    version: "1.0.0",
    reference: `veyra.tool.${id}@1.0.0`,
    name,
    description: `${name} description`,
    origin: "builtin",
    content_hash: "b".repeat(64),
    availability,
    factory_selectable: availability !== "unavailable",
    runtime_status: availability === "ready" ? "supported" : "runtime_not_supported",
    required_permissions: { network_hosts: [], tools: [`veyra.tool.${id}`], filesystem_read_roots: id.includes("read") ? ["project"] : [], filesystem_write_roots: id.includes("write") ? ["project"] : [], shell_workspace_only: false },
    tags: ["tool"],
    spec: { ui: { category: "filesystem", icon: "file-text", title: name }, approval_required: id.includes("write") },
    ...extra,
  };
}

describe("Studio catalog palette", () => {
  it("projects Catalog tools as distinct palette cards and marks unavailable tools as not draggable", () => {
    const items = paletteFromCatalog([
      tool("Read File", "filesystem.read", "ready"),
      tool("Write File", "filesystem.write", "ready"),
      tool("GitHub Read", "github.read", "unavailable", { factory_selectable: false }),
    ]);
    expect(items.map((item) => item.title)).toEqual(["Read File", "Write File", "GitHub Read"]);
    expect(items.find((item) => item.title === "Read File")?.draggable).toBe(true);
    expect(items.find((item) => item.title === "GitHub Read")?.draggable).toBe(false);
    expect(catalogToolRequiresApproval(tool("Write File", "filesystem.write", "ready"))).toBe(true);
  });

  it("writes uses, lock, and permission roots when a Catalog tool is attached", () => {
    const resource = tool("Read File", "filesystem.read", "ready");
    const next = attachCatalogResource(source, resource, { id: "read-1", component_type: "Tool", uses: resource.reference }, { x: 40.4, y: 80.8 });
    expect(next.nodes).toContainEqual({ id: "read-1", component_type: "Tool", uses: "veyra.tool.filesystem.read@1.0.0" });
    expect(next.lock[resource.reference]).toBe(resource.content_hash);
    expect(next.extensions.veyra.permissions.tools).toEqual(["veyra.tool.filesystem.read"]);
    expect(next.extensions.veyra.permissions.filesystem_read_roots).toEqual(["project"]);
    expect(next.ui.positions["read-1"]).toEqual({ x: 40, y: 81 });
  });
});
