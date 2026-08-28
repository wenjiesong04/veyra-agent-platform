import type { AgentSource, FlowNode, FlowTransition } from "@veyra/api-contracts";
import type { Edge, Node } from "@xyflow/react";
import { componentFor } from "./registry";

export type CanvasNodeData = { flow: FlowNode };

export function toCanvas(source: AgentSource): { nodes: Node<CanvasNodeData>[]; edges: Edge[] } {
  return {
    nodes: source.nodes.map((flow, index) => ({ id: flow.id, type: "agentNode", position: source.ui.positions[flow.id] ?? { x: 90 + (index % 3) * 240, y: 80 + Math.floor(index / 3) * 170 }, data: { flow } })),
    edges: source.transitions.map((transition) => ({ id: `${transition.from}:${transition.port}:${transition.to}`, source: transition.from, target: transition.to, sourceHandle: transition.port, label: transition.port })),
  };
}

export function sourceWithGraph(source: AgentSource, nodes: Node<CanvasNodeData>[], edges: Edge[]): AgentSource {
  const positions = Object.fromEntries(nodes.map((node) => [node.id, { x: Math.round(node.position.x), y: Math.round(node.position.y) }]));
  const transitions: FlowTransition[] = edges.flatMap((edge) => {
    const from = source.nodes.find((node) => node.id === edge.source);
    const port = edge.sourceHandle;
    return from && port && componentFor(from.component_type).ports.includes(port) ? [{ from: edge.source, port: port as FlowTransition["port"], to: edge.target }] : [];
  });
  return { ...source, transitions, ui: { ...source.ui, positions } };
}

export function graphDiagnostics(source: AgentSource): string[] {
  const problems: string[] = [];
  const ids = new Set(source.nodes.map((node) => node.id));
  if (source.nodes.filter((node) => node.component_type === "Start").length !== 1) problems.push("Exactly one Start node is required.");
  if (!source.nodes.some((node) => node.component_type === "Output")) problems.push("An Output node is required.");
  const outputNames = source.nodes.filter((node) => node.component_type === "Output").map((node) => node.output_name);
  if (new Set(outputNames).size !== outputNames.length || outputNames.some((name) => !name || !(name in source.outputs))) problems.push("Every Output node must match one declared output.");
  if (source.extensions.veyra.verification.required && !source.nodes.some((node) => node.component_type === "Verifier")) problems.push("Required verification needs a Verifier node.");
  for (const node of source.nodes) {
    const required = node.component_type === "Agent" ? [node.model_ref, node.system_prompt] : node.component_type === "Tool" ? [node.uses] : node.component_type === "Condition" ? [node.expression] : node.component_type === "Transform" ? [node.mapping && Object.keys(node.mapping).length] : node.component_type === "HumanApproval" ? [node.prompt] : node.component_type === "Verifier" ? [node.checks?.length] : node.component_type === "Output" ? [node.output_name] : [];
    if (required.some((value) => !value)) problems.push(`${node.id} is missing required ${node.component_type} fields.`);
    if (node.component_type === "Tool" && node.uses && (!source.extensions.veyra.permissions.tools.includes(node.uses.split("@").slice(0, -1).join("@")) || !(node.uses in source.lock))) problems.push(`${node.id} must be permitted and locked before it can be saved.`);
  }
  for (const edge of source.transitions) {
    if (!ids.has(edge.from) || !ids.has(edge.to)) problems.push(`Transition ${edge.from} → ${edge.to} has an unknown node.`);
    const node = source.nodes.find((item) => item.id === edge.from);
    if (node && !componentFor(node.component_type).ports.includes(edge.port)) problems.push(`Port ${edge.port} is not valid for ${node.id}.`);
  }
  for (const node of source.nodes) {
    const actual = source.transitions.filter((edge) => edge.from === node.id).map((edge) => edge.port).sort();
    const expected = componentFor(node.component_type).ports.slice().sort();
    if (actual.join(",") !== expected.join(",")) problems.push(`${node.id} must connect every required output port exactly once.`);
  }
  return problems;
}
