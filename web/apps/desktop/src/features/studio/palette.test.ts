import { describe, expect, it } from "vitest";
import type { AgentSource, ProjectResourceDescriptor, ResourceDescriptor } from "@veyra/api-contracts";
import { attachCatalogBinding, attachCatalogResource, attachKnowledgeBinding, catalogToolRequiresApproval, fallbackPalette, grantCatalogResource, isProjectCustomComponentResource, knowledgePalette, newCatalogNode, nodeDisplayTitle, notePalette, paletteForMode, paletteFromCatalog, paletteItemBlocked, workflowAgentPalette } from "./palette";

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

  it("projects a Project composite as a dynamic Agent node with an exact version lock", () => {
    const component: ProjectResourceDescriptor = {
      ...tool("Invoice Extractor", "custom.invoice-extractor", "design_only"),
      resource_id: "custom-component-1",
      kind: "component",
      component_class: "composite",
      version: "1.0.0",
      reference: "custom-component-1@1.0.0",
      name: "Invoice Extractor",
      origin: "project",
      content_hash: "c".repeat(64),
      required_permissions: { network_hosts: ["files.example.test"], tools: ["veyra.tool.filesystem.read"], filesystem_read_roots: ["project"], filesystem_write_roots: [], shell_workspace_only: false },
      tags: ["custom-component", "transform"],
      spec: { implementation_kind: "transform", ui: { category: "custom", icon: "box", title: "Invoice Extractor" } },
      scope: "project",
      binding_status: "current",
      binding_source: "manual",
      bound_content_hash: "d".repeat(64),
      used_by: [],
    };
    const staleComponent: ProjectResourceDescriptor = { ...component, binding_status: "stale" };
    const item = paletteFromCatalog([component])[0];
    expect(item).toMatchObject({ key: component.reference, group: "component", componentType: "CustomComponent", title: "Invoice Extractor", draggable: true });
    expect(paletteForMode([item!], "agent")).toHaveLength(1);
    expect(paletteForMode([item!], "workflow")).toHaveLength(0);
    expect(isProjectCustomComponentResource(staleComponent)).toBe(true);
    expect(paletteFromCatalog([staleComponent])[0]?.draggable).toBe(false);
    expect(paletteFromCatalog([{ ...component, scope: "used_unbound", bound_content_hash: null } as ProjectResourceDescriptor])).toHaveLength(0);

    const node = newCatalogNode(item!, "custom_1");
    expect(node).toEqual({ id: "custom_1", component_type: "CustomComponent", uses: component.reference, input_mapping: {}, output_mapping: {} });
    const next = attachCatalogResource(source, component, node, { x: 10, y: 20 });
    expect(next.lock[component.reference]).toBe(component.bound_content_hash);
    expect(next.extensions.veyra.permissions.tools).toContain("veyra.tool.filesystem.read");
    expect(next.extensions.veyra.permissions.network_hosts).toContain("files.example.test");
    expect(nodeDisplayTitle(node, [component], "zh")).toBe("Invoice Extractor");
    expect(() => grantCatalogResource(source, staleComponent)).toThrow(/bound to this Project/);
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
    expect(items.some((item) => item.componentType === "CustomComponent")).toBe(false);
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
    expect(paletteForMode(items, "loop").some((item) => item.componentType === "Condition")).toBe(false);
    expect(paletteForMode(items, "loop").some((item) => item.componentType === "HumanApproval")).toBe(false);
    expect(paletteForMode(items, "loop").some((item) => item.componentType === "Model")).toBe(false);
    expect(paletteForMode(items, "workflow").some((item) => item.componentType === "Start")).toBe(true);
    expect(paletteForMode(items, "workflow").some((item) => item.componentType === "Output")).toBe(true);
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

  it("offers terminal Stop nodes only in Workflow palettes without effect permissions", () => {
    const stop: ResourceDescriptor = {
      ...tool("Stop", "stop", "ready"),
      resource_id: "veyra.component.stop",
      reference: "veyra.component.stop@1.0.0",
      kind: "component",
      component_class: "primitive",
      factory_selectable: false,
      required_permissions: { network_hosts: [], tools: [], filesystem_read_roots: [], filesystem_write_roots: [], shell_workspace_only: false },
      spec: { fields: [], output_ports: [], ui: { category: "core", icon: "square", title: "Stop" } },
    };
    for (const items of [fallbackPalette(), paletteFromCatalog([stop])]) {
      const item = paletteForMode(items, "workflow").find((entry) => entry.componentType === "Stop");
      expect(item).toMatchObject({ componentType: "Stop", titleZh: "停止", ports: [], draggable: true, runtimeStatus: "supported" });
      expect(newCatalogNode(item!, "stop")).toEqual({ id: "stop", component_type: "Stop" });
      expect(paletteForMode(items, "agent").some((entry) => entry.componentType === "Stop")).toBe(false);
      expect(paletteForMode(items, "loop").some((entry) => entry.componentType === "Stop")).toBe(false);
    }
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
