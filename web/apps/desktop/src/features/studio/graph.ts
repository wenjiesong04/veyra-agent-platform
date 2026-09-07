import type { AgentSource, AgentVersionSnapshot, CatalogBinding, FlowNode, FlowTransition, ResourceDescriptor, StudioNote, StudioSource, WorkflowSource } from "@veyra/api-contracts";
import { MarkerType, type Edge, type Node } from "@xyflow/react";
import { agentCallRef, parseAgentCallRef } from "./agent-call";
import { catalogToolRequiresApproval } from "./palette";
import { componentFor } from "./registry";
import type { NodeRunState } from "./live-run";

export type CanvasNodeData = {
  flow?: FlowNode;
  binding?: Omit<CatalogBinding, "x" | "y">;
  note?: Omit<StudioNote, "x" | "y">;
  runState?: NodeRunState;
  title?: string;
};

export type GraphDiagnosticCode =
  | "node_context_invalid"
  | "agent_ref_invalid"
  | "agent_version_unavailable"
  | "agent_lock_mismatch"
  | "agent_mapping_invalid"
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

export const FLOW_NODE_ID_RE = /^[a-z][a-z0-9_]{0,62}$/;

export function newFlowNodeId(componentType: string): string {
  const prefix = componentType.toLowerCase().replace(/[^a-z0-9]/g, "") || "node";
  return `${prefix}_${crypto.randomUUID().replaceAll("-", "").slice(0, 8)}`;
}

function sanitizeFlowNodeId(id: string, used: Set<string>): string {
  let next = id.toLowerCase().replace(/[^a-z0-9_]/g, "_").replace(/_+/g, "_").replace(/^_+|_+$/g, "");
  if (!next || !/^[a-z]/.test(next)) next = `n_${next}`;
  next = next.slice(0, 63);
  let candidate = next;
  let suffix = 2;
  while (used.has(candidate) || !FLOW_NODE_ID_RE.test(candidate)) {
    const extra = `_${suffix}`;
    candidate = `${next.slice(0, 63 - extra.length)}${extra}`;
    suffix += 1;
  }
  return candidate;
}

function rewriteNodeRef(value: string, rename: Map<string, string>): string {
  const exact = rename.get(value);
  if (exact) return exact;
  for (const [from, to] of rename) {
    if (value.startsWith(`${from}_`)) return `${to}${value.slice(from.length)}`;
  }
  return value;
}

export function repairInvalidNodeIds(source: StudioSource): StudioSource {
  const used = new Set<string>();
  const rename = new Map<string, string>();
  for (const node of source.nodes) {
    if (FLOW_NODE_ID_RE.test(node.id) && !used.has(node.id)) {
      used.add(node.id);
      continue;
    }
    const next = sanitizeFlowNodeId(node.id, used);
    used.add(next);
    if (next !== node.id) rename.set(node.id, next);
  }
  if (!rename.size) return source;
  const rewriteMap = (mapping: Record<string, string> | undefined) => mapping
    ? Object.fromEntries(Object.entries(mapping).map(([key, value]) => [key, rewriteNodeRef(value, rename)]))
    : mapping;
  return {
    ...source,
    nodes: source.nodes.map((node) => ({
      ...node,
      id: rewriteNodeRef(node.id, rename),
      input_mapping: rewriteMap(node.input_mapping),
      output_mapping: rewriteMap(node.output_mapping),
    })),
    transitions: source.transitions.map((item) => ({ ...item, from: rewriteNodeRef(item.from, rename), to: rewriteNodeRef(item.to, rename) })),
    ui: {
      ...source.ui,
      positions: Object.fromEntries(Object.entries(source.ui.positions).map(([id, position]) => [rewriteNodeRef(id, rename), position])),
    },
  };
}

const componentTypes = new Set<FlowNode["component_type"]>([
  "Start", "Agent", "Model", "AgentCall", "Tool", "Condition", "Transform", "HumanApproval", "Verifier", "Output",
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
  const optionalStrings = ["model_ref", "system_prompt", "agent_ref", "uses", "expression", "prompt", "output_name"];
  if (optionalStrings.some((key) => key in value && typeof value[key] !== "string")) return false;
  for (const key of ["mapping", "input_mapping", "output_mapping"]) {
    if (key in value && !stringMap(value[key])) return false;
  }
  return !("checks" in value) || (Array.isArray(value.checks) && value.checks.every((check) => typeof check === "string"));
}

function canvasNotesValid(ui: Record<string, unknown>): boolean {
  if (!("notes" in ui)) return true;
  if (!record(ui.notes)) return false;
  const colors = new Set(["teal", "amber", "violet", "slate"]);
  for (const note of Object.values(ui.notes)) {
    if (!record(note) || typeof note.text !== "string" || note.text.length > 4000
      || typeof note.x !== "number" || !Number.isFinite(note.x)
      || typeof note.y !== "number" || !Number.isFinite(note.y)) return false;
    if ("color" in note && (typeof note.color !== "string" || !colors.has(note.color))) return false;
    if ("width" in note && (typeof note.width !== "number" || !Number.isFinite(note.width) || note.width < 160 || note.width > 640)) return false;
  }
  return true;
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
  if (!canvasNotesValid(value.ui)) return false;
  return Object.values(value.ui.positions).every((position) => record(position)
    && typeof position.x === "number" && Number.isFinite(position.x)
    && typeof position.y === "number" && Number.isFinite(position.y));
}

export function isWorkflowSourceCandidate(value: unknown): value is WorkflowSource {
  if (!record(value)
    || value.schema_version !== "1.0"
    || value.component_type !== "Workflow"
    || !["workflow_id", "slug", "name", "description"].every((key) => typeof value[key] === "string")
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
  if (!record(permissions) || !Array.isArray(permissions.network_hosts) || !permissions.network_hosts.every((item) => typeof item === "string")
    || !Array.isArray(permissions.tools) || !permissions.tools.every((item) => typeof item === "string")
    || !record(verification) || typeof verification.required !== "boolean" || !Array.isArray(verification.checks) || !verification.checks.every((item) => typeof item === "string")
    || !record(value.ui.positions)) return false;
  if (!canvasNotesValid(value.ui)) return false;
  return Object.values(value.ui.positions).every((position) => record(position)
    && typeof position.x === "number" && Number.isFinite(position.x)
    && typeof position.y === "number" && Number.isFinite(position.y));
}

function flowEdge(transition: FlowTransition): Edge {
  return {
    id: `${transition.from}:${transition.port}:${transition.to}`,
    source: transition.from,
    target: transition.to,
    sourceHandle: transition.port,
    type: "flowEdge",
    data: { port: transition.port },
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
  };
}

export function toCanvas(source: StudioSource): { nodes: Node<CanvasNodeData>[]; edges: Edge[] } {
  const flowNodes = source.nodes.map((flow, index) => ({
    id: flow.id,
    type: "agentNode",
    position: source.ui.positions[flow.id] ?? { x: 90 + (index % 3) * 240, y: 80 + Math.floor(index / 3) * 170 },
    data: { flow, runState: "pending" as const },
  }));
  const bindingNodes = Object.entries("bindings" in source.ui ? source.ui.bindings ?? {} : {}).map(([id, binding]) => ({
    id,
    type: "bindingNode",
    position: { x: binding.x, y: binding.y },
    data: { binding: { kind: binding.kind, reference: binding.reference } },
  }));
  const noteNodes = Object.entries(source.ui.notes ?? {}).map(([id, note]) => ({
    id,
    type: "noteNode",
    position: { x: note.x, y: note.y },
    data: { note: { text: note.text, color: note.color ?? "amber", width: note.width ?? 220 } },
    draggable: true,
    connectable: false,
  }));
  return {
    nodes: [...flowNodes, ...bindingNodes, ...noteNodes],
    edges: source.transitions.map(flowEdge),
  };
}

function persistNotes(nodes: Node<CanvasNodeData>[]): Record<string, StudioNote> | undefined {
  const notes = Object.fromEntries(nodes.filter((node) => node.data.note && !node.data.flow).map((node) => {
    const note = node.data.note as NonNullable<CanvasNodeData["note"]>;
    return [node.id, { x: Math.round(node.position.x), y: Math.round(node.position.y), text: note.text, color: note.color, width: note.width }];
  }));
  return Object.keys(notes).length ? notes : undefined;
}

export function flowNodeOutgoingPort(componentType: FlowNode["component_type"]): string | null {
  const outgoing = componentFor(componentType).ports;
  return outgoing.length === 1 ? outgoing[0] : null;
}

export function defaultSpliceEdgeId(nodes: Node<CanvasNodeData>[], edges: Edge[]): string | null {
  const output = nodes.find((node) => node.data.flow?.component_type === "Output");
  if (!output) return null;
  const incoming = edges.filter((edge) => edge.target === output.id);
  return incoming.length === 1 ? incoming[0].id : null;
}

export function insertFlowNodeOnEdge(
  nodes: Node<CanvasNodeData>[],
  edges: Edge[],
  edgeId: string,
  node: Node<CanvasNodeData>,
  outgoingPort: string,
): { nodes: Node<CanvasNodeData>[]; edges: Edge[] } | null {
  const edge = edges.find((item) => item.id === edgeId);
  if (!edge || !node.data.flow) return null;
  const sourceNode = nodes.find((item) => item.id === edge.source);
  const targetNode = nodes.find((item) => item.id === edge.target);
  const placed = {
    ...node,
    position: {
      x: Math.round(((sourceNode?.position.x ?? 0) + (targetNode?.position.x ?? 0)) / 2),
      y: Math.round(((sourceNode?.position.y ?? 0) + (targetNode?.position.y ?? 0)) / 2) + 28,
    },
  };
  const port = typeof edge.sourceHandle === "string" ? edge.sourceHandle : "next";
  return {
    nodes: [...nodes, placed],
    edges: [
      ...edges.filter((item) => item.id !== edgeId),
      flowEdge({ from: edge.source, port: port as FlowTransition["port"], to: placed.id }),
      flowEdge({ from: placed.id, port: outgoingPort as FlowTransition["port"], to: edge.target }),
    ],
  };
}

export function attachFlowNodeOnEdge(
  nodes: Node<CanvasNodeData>[],
  edges: Edge[],
  edgeId: string,
  nodeId: string,
  outgoingPort: string,
): { nodes: Node<CanvasNodeData>[]; edges: Edge[] } | null {
  const edge = edges.find((item) => item.id === edgeId);
  const node = nodes.find((item) => item.id === nodeId);
  if (!edge || !node?.data.flow || edge.source === nodeId || edge.target === nodeId) return null;
  if (edges.some((item) => item.source === nodeId || item.target === nodeId)) return null;
  const port = typeof edge.sourceHandle === "string" ? edge.sourceHandle : "next";
  return {
    nodes,
    edges: [
      ...edges.filter((item) => item.id !== edgeId),
      flowEdge({ from: edge.source, port: port as FlowTransition["port"], to: nodeId }),
      flowEdge({ from: nodeId, port: outgoingPort as FlowTransition["port"], to: edge.target }),
    ],
  };
}

export function sourceWithGraph(source: AgentSource, nodes: Node<CanvasNodeData>[], edges: Edge[]): AgentSource;
export function sourceWithGraph(source: WorkflowSource, nodes: Node<CanvasNodeData>[], edges: Edge[]): WorkflowSource;
export function sourceWithGraph(source: StudioSource, nodes: Node<CanvasNodeData>[], edges: Edge[]): StudioSource;
export function sourceWithGraph(source: StudioSource, nodes: Node<CanvasNodeData>[], edges: Edge[]): StudioSource {
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
  if (source.component_type === "Workflow") {
    const used = new Set(flowNodes.flatMap((node) => (node.agent_ref ? [node.agent_ref] : [])));
    return {
      ...source,
      nodes: flowNodes,
      transitions,
      lock: Object.fromEntries(Object.entries(source.lock).filter(([key]) => used.has(key))),
      ui: { ...source.ui, positions, notes: persistNotes(nodes) },
    };
  }
  const boundSkills = Object.values(bindings).filter((binding) => binding.kind === "skill").map((binding) => binding.reference);
  const boundKnowledge = Object.values(bindings).filter((binding) => binding.kind === "knowledge").map((binding) => binding.reference);
  const boundPolicies = Object.values(bindings).filter((binding) => binding.kind === "policy").map((binding) => binding.reference);
  const originalBindings = Object.values(source.ui.bindings ?? {});
  const keepRef = (reference: string, kind: "skill" | "policy" | "knowledge", current: string[]) => {
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
        ...((source.extensions.veyra.knowledge_refs?.length || boundKnowledge.length) ? { knowledge_refs: [...new Set([...(source.extensions.veyra.knowledge_refs ?? []).filter((ref) => keepRef(ref, "knowledge", boundKnowledge)), ...boundKnowledge])] } : {}),
      },
    },
    ui: { ...source.ui, positions, ...(Object.keys(bindings).length ? { bindings } : { bindings: undefined }), notes: persistNotes(nodes) },
  };
}

export function graphDiagnostics(source: StudioSource, catalog: ResourceDescriptor[] = [], versions?: AgentVersionSnapshot[]): GraphDiagnostic[] {
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
  const workflowTypes = new Set(["Start", "AgentCall", "Condition", "Transform", "HumanApproval", "Verifier", "Output"]);
  const workflowValues = new Set([...Object.keys(source.inputs), ...source.nodes.flatMap((node) => [...Object.keys(node.mapping ?? {}), ...Object.values(node.output_mapping ?? {})])]);
  for (const node of source.nodes) {
    if ((source.component_type === "Workflow" && !workflowTypes.has(node.component_type)) || (source.component_type === "Flow" && node.component_type === "AgentCall")) {
      problems.push({ code: "node_context_invalid", params: { nodeId: node.id, componentType: node.component_type, context: source.component_type } });
    }
    if (node.component_type === "AgentCall") {
      const params = { nodeId: node.id };
      const ref = node.agent_ref ?? "";
      if (!parseAgentCallRef(ref)) {
        problems.push({ code: "agent_ref_invalid", params });
      } else {
        if (!/^[0-9a-f]{64}$/.test(source.lock[ref] ?? "")) problems.push({ code: "agent_lock_mismatch", params });
        const version = versions?.find((item) => agentCallRef(item) === ref);
        if (versions && !version) problems.push({ code: "agent_version_unavailable", params });
        if (version && version.source_hash !== source.lock[ref]) problems.push({ code: "agent_lock_mismatch", params });
        const inputs = node.input_mapping;
        const outputs = node.output_mapping;
        const name = /^[a-zA-Z_][a-zA-Z0-9_]*$/;
        const malformed = !inputs || !outputs || Object.entries({ ...inputs, ...outputs }).some(([key, value]) => !name.test(key) || !name.test(value));
        const wrongFields = version && (Object.keys(inputs ?? {}).sort().join(",") !== Object.keys(version.source.inputs).sort().join(",") || Object.keys(outputs ?? {}).sort().join(",") !== Object.keys(version.source.outputs).sort().join(","));
        const unknownInput = Object.values(inputs ?? {}).some((value) => !workflowValues.has(value));
        const duplicateOutput = new Set(Object.values(outputs ?? {})).size !== Object.values(outputs ?? {}).length;
        if (malformed || wrongFields || unknownInput || duplicateOutput) problems.push({ code: "agent_mapping_invalid", params });
      }
    }
    const required = node.component_type === "Agent" || node.component_type === "Model" ? [node.model_ref, node.system_prompt] : node.component_type === "Tool" ? [node.uses] : node.component_type === "Condition" ? [node.expression] : node.component_type === "Transform" ? [node.mapping && Object.keys(node.mapping).length] : node.component_type === "HumanApproval" ? [node.prompt] : node.component_type === "Verifier" ? [node.checks?.length] : node.component_type === "Output" ? [node.output_name] : [];
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
