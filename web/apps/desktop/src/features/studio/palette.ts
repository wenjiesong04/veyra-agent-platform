import type { AgentSource, FlowNode, ResourceDescriptor, ResourceRuntimeStatus } from "@veyra/api-contracts";
import { newNode, studioComponents } from "./registry";

export const PALETTE_MIME = "application/x-veyra-palette";

export type PaletteItem = {
  key: string;
  group: "component" | "tool" | "skill" | "policy" | "template" | "mcp";
  componentType: FlowNode["component_type"];
  title: string;
  titleZh: string;
  detail: string;
  detailZh: string;
  category: string;
  icon: string;
  ports: string[];
  draggable: boolean;
  runtimeStatus: ResourceRuntimeStatus;
  availability: ResourceDescriptor["availability"];
  resource?: ResourceDescriptor;
};

const COMPONENT_TYPES = new Set<FlowNode["component_type"]>([
  "Start", "Agent", "Tool", "Condition", "Transform", "HumanApproval", "Verifier", "Output",
]);

const ZH_TITLE: Record<string, string> = {
  Start: "开始",
  Agent: "Agent",
  Tool: "工具",
  Condition: "条件",
  Transform: "转换",
  HumanApproval: "人工审批",
  Approval: "审批",
  Verifier: "验证器",
  Output: "输出",
  "Read File": "读取文件",
  "Write File": "写入文件",
  "Workspace Shell": "工作区 Shell",
  "HTTP Request": "HTTP 请求",
  "GitHub Read": "GitHub 读取",
  "GitHub Write": "GitHub 写入",
  "LLM Agent": "LLM Agent",
  "MCP Call": "MCP 调用",
  "Research Brief": "研究简报",
};

function unique(values: string[]): string[] {
  return [...new Set(values)];
}

export function resourceUi(resource: ResourceDescriptor): { category: string; icon: string; title: string } | null {
  const ui = resource.spec.ui;
  if (!ui || typeof ui !== "object" || Array.isArray(ui)) return null;
  const record = ui as Record<string, unknown>;
  if (typeof record.category !== "string" || typeof record.icon !== "string" || typeof record.title !== "string") return null;
  if (!record.category.trim() || !record.icon.trim() || !record.title.trim()) return null;
  return { category: record.category, icon: record.icon, title: record.title };
}

export function catalogToolRequiresApproval(resource: ResourceDescriptor): boolean {
  return resource.kind === "tool" && resource.spec.approval_required === true;
}

function canDrag(resource: ResourceDescriptor): boolean {
  if (resource.availability === "unavailable" || resource.availability === "quarantined" || resource.availability === "disabled") {
    return false;
  }
  if (resource.kind === "mcp_tool") return true;
  return resource.factory_selectable;
}

export function paletteFromCatalog(resources: ResourceDescriptor[]): PaletteItem[] {
  const components: PaletteItem[] = [];
  const rest: PaletteItem[] = [];
  for (const resource of resources) {
    const ui = resourceUi(resource);
    const title = ui?.title ?? resource.name;
    if (resource.kind === "component" && COMPONENT_TYPES.has(resource.name as FlowNode["component_type"])) {
      const type = resource.name as FlowNode["component_type"];
      const fallback = studioComponents.find((item) => item.type === type);
      components.push({
        key: resource.reference,
        group: "component",
        componentType: type,
        title,
        titleZh: ZH_TITLE[title] ?? ZH_TITLE[type] ?? title,
        detail: resource.description,
        detailZh: fallback?.detailZh ?? resource.description,
        category: ui?.category ?? "core",
        icon: ui?.icon ?? "box",
        ports: fallback?.ports ?? [],
        draggable: canDrag(resource),
        runtimeStatus: resource.runtime_status,
        availability: resource.availability,
        resource,
      });
    } else if (resource.kind === "tool" || resource.kind === "mcp_tool" || resource.kind === "skill" || resource.kind === "policy" || resource.kind === "template") {
      rest.push({
        key: resource.reference,
        group: resource.kind === "mcp_tool" ? "mcp" : resource.kind,
        componentType: resource.kind === "tool" || resource.kind === "mcp_tool" ? "Tool" : "Agent",
        title,
        titleZh: ZH_TITLE[title] ?? title,
        detail: resource.description,
        detailZh: resource.description,
        category: ui?.category ?? resource.kind,
        icon: ui?.icon ?? "box",
        ports: resource.kind === "tool" || resource.kind === "mcp_tool" ? ["next"] : [],
        draggable: canDrag(resource),
        runtimeStatus: resource.runtime_status,
        availability: resource.availability,
        resource,
      });
    }
  }
  const order = studioComponents.map((item) => item.type);
  components.sort((left, right) => order.indexOf(left.componentType) - order.indexOf(right.componentType));
  return [...components, ...rest];
}

export function fallbackPalette(): PaletteItem[] {
  return studioComponents.map((component) => ({
    key: component.type,
    group: "component" as const,
    componentType: component.type,
    title: component.label,
    titleZh: component.labelZh,
    detail: component.detail,
    detailZh: component.detailZh,
    category: "core",
    icon: component.type.toLowerCase(),
    ports: component.ports,
    draggable: true,
    runtimeStatus: "supported" as const,
    availability: "ready" as const,
  }));
}

export function attachCatalogResource(
  source: AgentSource,
  resource: ResourceDescriptor,
  node: FlowNode,
  position: { x: number; y: number },
): AgentSource {
  const permissions = source.extensions.veyra.permissions;
  const required = resource.required_permissions;
  const lock = resource.kind === "tool" || resource.kind === "mcp_tool"
    ? { ...source.lock, [resource.reference]: resource.content_hash }
    : source.lock;
  return {
    ...source,
    nodes: [...source.nodes, node],
    extensions: {
      ...source.extensions,
      veyra: {
        ...source.extensions.veyra,
        permissions: {
          ...permissions,
          tools: unique([...permissions.tools, ...required.tools]),
          network_hosts: unique([...permissions.network_hosts, ...required.network_hosts]),
          filesystem_read_roots: unique([...(permissions.filesystem_read_roots ?? []), ...required.filesystem_read_roots]),
          filesystem_write_roots: unique([...(permissions.filesystem_write_roots ?? []), ...required.filesystem_write_roots]),
          shell_workspace_only: Boolean(permissions.shell_workspace_only) || required.shell_workspace_only,
        },
      },
    },
    lock,
    ui: {
      ...source.ui,
      positions: { ...source.ui.positions, [node.id]: { x: Math.round(position.x), y: Math.round(position.y) } },
    },
  };
}

export function attachCatalogBinding(
  source: AgentSource,
  resource: ResourceDescriptor,
  bindingId: string,
  position: { x: number; y: number },
): AgentSource {
  const veyra = source.extensions.veyra;
  const point = { x: Math.round(position.x), y: Math.round(position.y) };
  const skillRefs = unique([
    ...(veyra.skill_refs ?? []),
    ...(resource.kind === "skill" ? [resource.reference] : []),
  ]);
  const policyRefs = unique([
    ...(veyra.policy_refs ?? []),
    ...(resource.kind === "policy" ? [resource.reference] : []),
  ]);
  return {
    ...source,
    extensions: {
      ...source.extensions,
      veyra: {
        ...veyra,
        skill_refs: skillRefs,
        policy_refs: policyRefs,
      },
    },
    lock: { ...source.lock, [resource.reference]: resource.content_hash },
    ui: {
      ...source.ui,
      bindings: {
        ...(source.ui.bindings ?? {}),
        [bindingId]: {
          kind: resource.kind === "mcp_tool" ? "mcp_tool" : resource.kind as "skill" | "policy" | "template",
          reference: resource.reference,
          ...point,
        },
      },
    },
  };
}

export function newCatalogNode(item: PaletteItem, id: string): FlowNode {
  if ((item.group === "tool" || item.group === "mcp") && item.resource) {
    return { id, component_type: "Tool", uses: item.resource.reference };
  }
  return newNode(item.componentType, id);
}

export function nodeDisplayTitle(flow: FlowNode, resources: ResourceDescriptor[], locale: "zh" | "en"): string {
  if (flow.component_type === "Tool" && flow.uses) {
    const resource = resources.find((item) => item.reference === flow.uses);
    if (resource) {
      const title = resourceUi(resource)?.title ?? resource.name;
      return locale === "zh" ? (ZH_TITLE[title] ?? title) : title;
    }
  }
  const component = studioComponents.find((item) => item.type === flow.component_type);
  if (!component) return flow.component_type;
  return locale === "zh" ? component.labelZh : component.label;
}
