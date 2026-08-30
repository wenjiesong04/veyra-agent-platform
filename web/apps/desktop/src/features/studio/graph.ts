import type { AgentSource, CatalogBinding, FlowNode, FlowTransition, ResourceDescriptor } from "@veyra/api-contracts";
import type { Edge, Node } from "@xyflow/react";
import { catalogToolRequiresApproval } from "./palette";
import { componentFor } from "./registry";
import type { NodeRunState } from "./live-run";

export type CanvasNodeData = {
  flow?: FlowNode;
  binding?: Omit<CatalogBinding, "x" | "y">;
  runState?: NodeRunState;
  title?: string;
};

export type GraphDiagnosticCode =
  | "start_count"
  | "output_missing"
  | "output_declaration"
  | "verifier_required"
  | "node_fields_missing"
  | "tool_not_permitted_or_locked"
  | "write_requires_approval"
  | "transition_unknown_node"
  | "transition_invalid_port"
  | "node_ports_incomplete";

export type GraphDiagnostic = {
  code: GraphDiagnosticCode;
  params?: Record<string, string>;
};

const componentTypes = new Set<FlowNode["component_type"]>([
  "Start", "Agent", "Tool", "Condition", "Transform", "HumanApproval", "Verifier", "Output",
]);
const ports = new Set<FlowTransition["port"]>(["next", "true", "false", "approved", "rejected", "passed", "failed"]);

function record(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function stringMap(value: unknown): value is Record<string, string> {
  return record(value) && Object.values(value).every((item) => typeof item === "string");
}

function flowNode(value: unknown): value is FlowNode {
  if (!record(value) || typeof value.id !== "string" || !componentTypes.has(value.component_type as FlowNode["component_type"])) return false;
  const optionalStrings = ["model_ref", "system_prompt", "uses", "expression", "prompt", "output_name"];
  if (optionalStrings.some((key) => key in value && typeof value[key] !== "string")) return false;
  if ("mapping" in value && !stringMap(value.mapping)) return false;
  return !("checks" in value) || (Array.isArray(value.checks) && value.checks.every((check) => typeof check === "string"));
}

/** A UI safety guard, not a replacement for the server's semantic validation. */
export function isAgentSourceCandidate(value: unknown): value is AgentSource {
  if (!record(value)
    || value.schema_version !== "1.0"
    || value.agentspec_version !== "26.1"
    || value.component_type !== "Flow"
    || !["agent_id", "slug", "name", "description"].every((key) => typeof value[key] === "string")
    || !stringMap(value.inputs) || !stringMap(value.outputs) || !stringMap(value.lock)
    || !Array.isArray(value.nodes) || !value.nodes.every(flowNode)
    || !Array.isArray(value.transitions)) return false;
  if (!value.transitions.every((transition) => record(transition)
    && typeof transition.from === "string" && typeof transition.to === "string"
    && ports.has(transition.port as FlowTransition["port"]))) return false;
  if (!record(value.extensions) || !record(value.extensions.veyra) || !record(value.ui)) return false;
  const veyra = value.extensions.veyra;
  const permissions = veyra.permissions;
  const verification = veyra.verification;
  if (typeof veyra.runtime_profile !== "string" || !Array.isArray(veyra.secret_refs) || !veyra.secret_refs.every((item) => typeof item === "string")
    || !record(permissions) || !Array.isArray(permissions.network_hosts) || !permissions.network_hosts.every((item) => typeof item === "string")
    || !Array.isArray(permissions.tools) || !permissions.tools.every((item) => typeof item === "string")
    || ("filesystem_read_roots" in permissions && (!Array.isArray(permissions.filesystem_read_roots) || !permissions.filesystem_read_roots.every((item) => typeof item === "string")))
    || ("filesystem_write_roots" in permissions && (!Array.isArray(permissions.filesystem_write_roots) || !permissions.filesystem_write_roots.every((item) => typeof item === "string")))
    || ("shell_workspace_only" in permissions && typeof permissions.shell_workspace_only !== "boolean")
    || !record(verification) || typeof verification.required !== "boolean" || !Array.isArray(verification.checks) || !verification.checks.every((item) => typeof item === "string")
    || ("skill_refs" in veyra && (!Array.isArray(veyra.skill_refs) || !veyra.skill_refs.every((item) => typeof item === "string")))
    || ("policy_refs" in veyra && (!Array.isArray(veyra.policy_refs) || !veyra.policy_refs.every((item) => typeof item === "string")))
    || !record(value.ui.positions)) return false;
  if ("bindings" in value.ui) {
    if (!record(value.ui.bindings)) return false;
    for (const binding of Object.values(value.ui.bindings)) {
      if (!record(binding) || typeof binding.kind !== "string" || typeof binding.reference !== "string"
        || typeof binding.x !== "number" || !Number.isFinite(binding.x)
        || typeof binding.y !== "number" || !Number.isFinite(binding.y)) return false;
    }
  }
  return Object.values(value.ui.positions).every((position) => record(position)
    && typeof position.x === "number" && Number.isFinite(position.x)
    && typeof position.y === "number" && Number.isFinite(position.y));
}

export function toCanvas(source: AgentSource): { nodes: Node<CanvasNodeData>[]; edges: Edge[] } {
  const flowNodes = source.nodes.map((flow, index) => ({
    id: flow.id,
    type: "agentNode",
    position: source.ui.positions[flow.id] ?? { x: 90 + (index % 3) * 240, y: 80 + Math.floor(index / 3) * 170 },
    data: { flow, runState: "pending" as const },
  }));
  const bindingNodes = Object.entries(source.ui.bindings ?? {}).map(([id, binding]) => ({
    id,
    type: "bindingNode",
    position: { x: binding.x, y: binding.y },
    data: { binding: { kind: binding.kind, reference: binding.reference } },
  }));
  return {
    nodes: [...flowNodes, ...bindingNodes],
    edges: source.transitions.map((transition) => ({ id: `${transition.from}:${transition.port}:${transition.to}`, source: transition.from, target: transition.to, sourceHandle: transition.port, label: transition.port })),
  };
}

export function sourceWithGraph(source: AgentSource, nodes: Node<CanvasNodeData>[], edges: Edge[]): AgentSource {
  const flowCanvas = nodes.filter((node) => node.data.flow);
  const bindingCanvas = nodes.filter((node) => node.data.binding && !node.data.flow);
  const positions = Object.fromEntries(flowCanvas.map((node) => [node.id, { x: Math.round(node.position.x), y: Math.round(node.position.y) }]));
  const flowNodes = flowCanvas.map((node) => node.data.flow as FlowNode);
  const bindings = Object.fromEntries(bindingCanvas.map((node) => {
    const binding = node.data.binding as NonNullable<CanvasNodeData["binding"]>;
    return [node.id, { ...binding, x: Math.round(node.position.x), y: Math.round(node.position.y) }];
  }));
  const transitions: FlowTransition[] = edges.flatMap((edge) => {
    const from = flowNodes.find((node) => node.id === edge.source);
    const port = edge.sourceHandle;
    return from && port && componentFor(from.component_type).ports.includes(port) ? [{ from: edge.source, port: port as FlowTransition["port"], to: edge.target }] : [];
  });
  const boundSkills = Object.values(bindings).filter((binding) => binding.kind === "skill").map((binding) => binding.reference);
  const boundPolicies = Object.values(bindings).filter((binding) => binding.kind === "policy").map((binding) => binding.reference);
  const originalBindings = Object.values(source.ui.bindings ?? {});
  const keepRef = (reference: string, kind: "skill" | "policy", current: string[]) => {
    const hadBinding = originalBindings.some((binding) => binding.kind === kind && binding.reference === reference);
    return current.includes(reference) || !hadBinding;
  };
  const skillRefs = [...new Set([
    ...(source.extensions.veyra.skill_refs ?? []).filter((reference) => keepRef(reference, "skill", boundSkills)),
    ...boundSkills,
  ])];
  const policyRefs = [...new Set([
    ...(source.extensions.veyra.policy_refs ?? []).filter((reference) => keepRef(reference, "policy", boundPolicies)),
    ...boundPolicies,
  ])];
  return {
    ...source,
    nodes: flowNodes,
    transitions,
    extensions: {
      ...source.extensions,
      veyra: {
        ...source.extensions.veyra,
        skill_refs: skillRefs,
        policy_refs: policyRefs,
      },
    },
    ui: { ...source.ui, positions, ...(Object.keys(bindings).length ? { bindings } : { bindings: undefined }) },
  };
}

export function graphDiagnostics(source: AgentSource, catalog: ResourceDescriptor[] = []): GraphDiagnostic[] {
  const problems: GraphDiagnostic[] = [];
  const ids = new Set(source.nodes.map((node) => node.id));
  const approvalRequired = new Set(
    catalog.filter(catalogToolRequiresApproval).map((resource) => resource.reference),
  );
  const hasApproval = source.nodes.some((node) => node.component_type === "HumanApproval");
  if (source.nodes.filter((node) => node.component_type === "Start").length !== 1) problems.push({ code: "start_count" });
  if (!source.nodes.some((node) => node.component_type === "Output")) problems.push({ code: "output_missing" });
  const outputNames = source.nodes.filter((node) => node.component_type === "Output").map((node) => node.output_name);
  if (new Set(outputNames).size !== outputNames.length || outputNames.some((name) => !name || !(name in source.outputs))) problems.push({ code: "output_declaration" });
  if (source.extensions.veyra.verification.required && !source.nodes.some((node) => node.component_type === "Verifier")) problems.push({ code: "verifier_required" });
  for (const node of source.nodes) {
    const required = node.component_type === "Agent" ? [node.model_ref, node.system_prompt] : node.component_type === "Tool" ? [node.uses] : node.component_type === "Condition" ? [node.expression] : node.component_type === "Transform" ? [node.mapping && Object.keys(node.mapping).length] : node.component_type === "HumanApproval" ? [node.prompt] : node.component_type === "Verifier" ? [node.checks?.length] : node.component_type === "Output" ? [node.output_name] : [];
    if (required.some((value) => !value)) problems.push({ code: "node_fields_missing", params: { nodeId: node.id, componentType: node.component_type } });
    if (node.component_type === "Tool" && node.uses && (!source.extensions.veyra.permissions.tools.includes(node.uses.split("@").slice(0, -1).join("@")) || !(node.uses in source.lock))) problems.push({ code: "tool_not_permitted_or_locked", params: { nodeId: node.id } });
    if (node.component_type === "Tool" && node.uses && approvalRequired.has(node.uses) && !hasApproval) {
      problems.push({ code: "write_requires_approval", params: { nodeId: node.id } });
    }
  }
  for (const edge of source.transitions) {
    if (!ids.has(edge.from) || !ids.has(edge.to)) problems.push({ code: "transition_unknown_node", params: { from: edge.from, to: edge.to } });
    const node = source.nodes.find((item) => item.id === edge.from);
    if (node && !componentFor(node.component_type).ports.includes(edge.port)) problems.push({ code: "transition_invalid_port", params: { port: edge.port, nodeId: node.id } });
  }
  for (const node of source.nodes) {
    const actual = source.transitions.filter((edge) => edge.from === node.id).map((edge) => edge.port).sort();
    const expected = componentFor(node.component_type).ports.slice().sort();
    if (actual.join(",") !== expected.join(",")) problems.push({ code: "node_ports_incomplete", params: { nodeId: node.id } });
  }
  return problems;
}
