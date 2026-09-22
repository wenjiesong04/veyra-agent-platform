import { describe, expect, it } from "vitest";
import type { AgentSource, ProjectResourceDescriptor, ResourceDescriptor } from "@veyra/api-contracts";
import { attachCatalogBinding, attachCatalogResource, attachKnowledgeBinding, catalogToolRequiresApproval, fallbackPalette, grantCatalogResource, knowledgePalette, nodeDisplayTitle, notePalette, paletteForMode, paletteFromCatalog, paletteItemBlocked, workflowAgentPalette } from "./palette";

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
    const resource: ProjectResourceDescriptor = { ...tool("Read File", "filesystem.read", "ready"), scope: "project", binding_source: "manual", bound_content_hash: "a".repeat(64), used_by: [] };
    const next = attachCatalogResource(source, resource, { id: "read-1", component_type: "Tool", uses: resource.reference }, { x: 40.4, y: 80.8 });
    expect(next.nodes).toContainEqual({ id: "read-1", component_type: "Tool", uses: "veyra.tool.filesystem.read@1.0.0" });
    expect(next.lock[resource.reference]).toBe(resource.bound_content_hash);
    expect(next.extensions.veyra.permissions.tools).toEqual(["veyra.tool.filesystem.read"]);
    expect(next.extensions.veyra.permissions.filesystem_read_roots).toEqual(["project"]);
    expect(next.ui.positions["read-1"]).toEqual({ x: 40, y: 81 });
    const granted = grantCatalogResource(source, resource);
    expect(granted.nodes).toEqual(source.nodes);
    expect(granted.lock[resource.reference]).toBe(resource.bound_content_hash);
    expect(() => grantCatalogResource(source, tool("Global", "global", "ready"))).toThrow(/bound to this Project/);
    expect(paletteFromCatalog([{ ...resource, binding_status: "stale" } as ProjectResourceDescriptor])[0]?.draggable).toBe(false);
  });

  it("attaches Skills as catalog bindings without adding a Flow node", () => {
    const skill: ResourceDescriptor = {
      schema_version: "1.0",
      resource_id: "veyra.skill.research-brief",
      kind: "skill",
      version: "1.0.0",
      reference: "veyra.skill.research-brief@1.0.0",
      name: "Research Brief",
      description: "Brief",
      origin: "builtin",
      content_hash: "c".repeat(64),
      availability: "requires_configuration",
      factory_selectable: true,
      runtime_status: "runtime_not_configured",
      required_permissions: { network_hosts: [], tools: [], filesystem_read_roots: [], filesystem_write_roots: [], shell_workspace_only: false },
      tags: ["research"],
      spec: { ui: { category: "skill", icon: "book-open", title: "Research Brief" } },
    };
    const items = paletteFromCatalog([skill]);
    expect(items[0]?.group).toBe("skill");
    expect(items[0]?.draggable).toBe(true);
    const next = attachCatalogBinding(source, skill, "bind_skill1", { x: 12.2, y: 18.8 });
    expect(next.nodes).toEqual(source.nodes);
    expect(next.extensions.veyra.skill_refs).toEqual([skill.reference]);
    expect(next.lock[skill.reference]).toBe(skill.content_hash);
    expect(next.ui.bindings?.bind_skill1).toEqual({ kind: "skill", reference: skill.reference, x: 12, y: 19 });
  });

  it("keeps the legacy Agent alias out of the new-node palette", () => {
    const items = fallbackPalette();
    expect(items.some((item) => item.componentType === "Agent")).toBe(false);
    expect(paletteForMode(items, "agent").some((item) => item.componentType === "Agent")).toBe(false);
    expect(paletteForMode(items, "agent").some((item) => item.componentType === "Model")).toBe(true);
    expect(paletteForMode(items, "agent").some((item) => item.componentType === "AgentCall")).toBe(false);
    expect(paletteForMode(items, "agent").some((item) => item.componentType === "Condition")).toBe(true);
    expect(paletteForMode(items, "agent").some((item) => item.componentType === "Transform")).toBe(true);
    expect(paletteForMode(items, "workflow").some((item) => item.componentType === "AgentCall")).toBe(true);
    expect(paletteForMode(items, "workflow").some((item) => item.componentType === "Condition")).toBe(true);
    expect(paletteForMode(items, "workflow").some((item) => item.componentType === "Model")).toBe(false);
    expect(paletteForMode(items, "workflow").some((item) => item.componentType === "Tool")).toBe(false);
    expect(paletteForMode(items, "workflow").some((item) => item.componentType === "Agent")).toBe(false);
  });

  it("keeps Workflow AgentCall draggable even when Factory cannot select it", () => {
    const agentCall: ResourceDescriptor = {
      schema_version: "1.0",
      resource_id: "veyra.component.agent-call",
      kind: "component",
      version: "1.0.0",
      reference: "veyra.component.agent-call@1.0.0",
      name: "AgentCall",
      description: "Call a Project Agent",
      origin: "builtin",
      content_hash: "e".repeat(64),
      availability: "ready",
      factory_selectable: false,
      runtime_status: "supported",
      required_permissions: { network_hosts: [], tools: [], filesystem_read_roots: [], filesystem_write_roots: [], shell_workspace_only: false },
      tags: ["graph"],
      spec: { fields: ["agent_ref"], output_ports: ["next"], ui: { category: "orchestration", icon: "bot", title: "Agent call" } },
    };
    const items = paletteFromCatalog([agentCall]);
    expect(items[0]?.draggable).toBe(true);
    expect(paletteForMode(items, "workflow")[0]?.componentType).toBe("AgentCall");
  });

  it("projects Project Agents as Workflow AgentCall shortcuts", () => {
    const agent = { agent_id: "01900000-0000-7000-8000-000000000001", slug: "translation", name: "translation", description: "", pinned: false, source_path: "agents/translation/agent.vagent.yaml", source_file_hash: "f".repeat(64) };
    const items = workflowAgentPalette([agent]);
    expect(items).toHaveLength(1);
    expect(items[0]?.group).toBe("agent");
    expect(items[0]?.componentType).toBe("AgentCall");
    expect(items[0]?.draggable).toBe(true);
    expect(items[0]?.title).toBe("translation");
  });

  it("attaches Knowledge as a catalog binding locked by id@version", () => {
    const document = { knowledge_id: "01900000-0000-7000-8000-000000000010", slug: "brief", name: "Brief", description: "", version: "1.0.0", source_path: "knowledge/brief/document.md", source_file_hash: "d".repeat(64) };
    expect(knowledgePalette([document])[0]?.group).toBe("knowledge");
    const next = attachKnowledgeBinding(source, document, "bind_knowledge1", { x: 8.2, y: 9.8 });
    expect(next.nodes).toEqual(source.nodes);
    expect(next.lock[`${document.knowledge_id}@1.0.0`]).toBe(document.source_file_hash);
    expect(next.ui.bindings?.bind_knowledge1).toEqual({ kind: "knowledge", reference: `${document.knowledge_id}@1.0.0`, x: 8, y: 10 });
  });

  it("prefers semantic labels over component type titles", () => {
    expect(nodeDisplayTitle({ id: "summary", component_type: "Model" }, [], "zh", [], { summary: "总结资料" })).toBe("总结资料");
    expect(nodeDisplayTitle({ id: "summary", component_type: "Model" }, [], "zh")).toBe("模型");
  });

  it("exposes canvas notes as a non-executable palette card", () => {
    expect(notePalette()[0]).toMatchObject({ group: "note", titleZh: "文字卡片", draggable: true, runtimeStatus: "runtime_not_supported" });
  });

  it("blocks a second Start on an Agent graph", () => {
    const start = fallbackPalette().find((item) => item.componentType === "Start");
    const model = fallbackPalette().find((item) => item.componentType === "Model");
    expect(start).toMatchObject({ title: "Start", titleZh: "输入" });
    expect(model).toBeDefined();
    expect(paletteItemBlocked(start!, [{ component_type: "Start" }])).toBe(true);
    expect(paletteItemBlocked(model!, [{ component_type: "Start" }])).toBe(false);
  });
});
