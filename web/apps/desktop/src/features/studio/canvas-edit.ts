import type { CatalogBinding, FlowNode, FlowTransition, StudioNote, StudioSource } from "@veyra/api-contracts";
import { newFlowNodeId } from "./graph";

export const CANVAS_CLIPBOARD_KIND = "veyra.studio.clipboard";

const WORKFLOW_TYPES = new Set(["AgentCall", "Condition", "Transform", "HumanApproval", "Verifier"]);
const AGENT_TYPES = new Set(["Agent", "Model", "Tool", "Condition", "Transform", "HumanApproval", "Verifier"]);

export type CanvasClipboard = {
  kind: typeof CANVAS_CLIPBOARD_KIND;
  nodes: FlowNode[];
  transitions: FlowTransition[];
  positions: Record<string, { x: number; y: number }>;
  notes?: Record<string, StudioNote>;
  bindings?: Record<string, CatalogBinding>;
};

let memoryClipboard: CanvasClipboard | null = null;

export function storeCanvasClipboard(clip: CanvasClipboard): void {
  memoryClipboard = clip;
}

export function loadCanvasClipboard(): CanvasClipboard | null {
  return memoryClipboard;
}

export function isProtectedFlowNode(node: FlowNode, nodes: FlowNode[] = [node]): boolean {
  if (node.component_type !== "Start" && node.component_type !== "Output") return false;
  const same = nodes.filter((item) => item.component_type === node.component_type);
  if (same.length <= 1) return true;
  const preferred = same.find((item) => item.id === "start" || item.id === "output" || item.id === "out") ?? same[0];
  return node.id === preferred.id;
}

function occupiedIds(source: StudioSource): Set<string> {
  return new Set([
    ...source.nodes.map((node) => node.id),
    ...Object.keys(source.ui.notes ?? {}),
    ...Object.keys(source.component_type === "Flow" ? source.ui.bindings ?? {} : {}),
  ]);
}

function allowedComponent(source: StudioSource, type: FlowNode["component_type"]): boolean {
  return source.component_type === "Workflow" ? WORKFLOW_TYPES.has(type) : AGENT_TYPES.has(type);
}

function rewriteMap(mapping: Record<string, string> | undefined, rename: Map<string, string>): Record<string, string> | undefined {
  if (!mapping) return mapping;
  return Object.fromEntries(Object.entries(mapping).map(([key, value]) => [key, rename.get(value) ?? value]));
}

function takeId(prefix: string, used: Set<string>): string {
  let next = newFlowNodeId(prefix);
  while (used.has(next)) next = newFlowNodeId(prefix);
  used.add(next);
  return next;
}

function originId(rename: Map<string, string>, nextId: string): string {
  for (const [from, to] of rename) {
    if (to === nextId) return from;
  }
  return nextId;
}

export function parseCanvasClipboard(raw: string): CanvasClipboard | null {
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    const item = parsed as Partial<CanvasClipboard>;
    if (item.kind !== CANVAS_CLIPBOARD_KIND || !Array.isArray(item.nodes) || !Array.isArray(item.transitions) || !item.positions) return null;
    return item as CanvasClipboard;
  } catch {
    return null;
  }
}

export async function writeCanvasClipboard(clip: CanvasClipboard): Promise<void> {
  storeCanvasClipboard(clip);
  try {
    await navigator.clipboard.writeText(JSON.stringify(clip));
  } catch {
    /* macOS / browser permission: in-memory clipboard still works inside Studio. */
  }
}

export async function readCanvasClipboard(): Promise<CanvasClipboard | null> {
  try {
    const parsed = parseCanvasClipboard(await navigator.clipboard.readText());
    if (parsed) {
      storeCanvasClipboard(parsed);
      return parsed;
    }
  } catch {
    /* fall through to the in-memory clipboard */
  }
  return loadCanvasClipboard();
}

export function copySelection(source: StudioSource, selectedIds: string[]): CanvasClipboard | null {
  const ids = new Set(selectedIds);
  const nodes = source.nodes.filter((node) => ids.has(node.id) && !isProtectedFlowNode(node) && allowedComponent(source, node.component_type));
  const notes = Object.fromEntries(Object.entries(source.ui.notes ?? {}).filter(([id]) => ids.has(id)));
  const bindings = source.component_type === "Flow"
    ? Object.fromEntries(Object.entries(source.ui.bindings ?? {}).filter(([id]) => ids.has(id)))
    : {};
  if (!nodes.length && !Object.keys(notes).length && !Object.keys(bindings).length) return null;
  const nodeIds = new Set(nodes.map((node) => node.id));
  return {
    kind: CANVAS_CLIPBOARD_KIND,
    nodes: structuredClone(nodes),
    transitions: structuredClone(source.transitions.filter((edge) => nodeIds.has(edge.from) && nodeIds.has(edge.to))),
    positions: Object.fromEntries(nodes.map((node) => [node.id, source.ui.positions[node.id] ?? { x: 0, y: 0 }])),
    ...(Object.keys(notes).length ? { notes: structuredClone(notes) } : {}),
    ...(Object.keys(bindings).length ? { bindings: structuredClone(bindings) } : {}),
  };
}

export function pasteClipboard(
  source: StudioSource,
  clipboard: CanvasClipboard,
  offset = { x: 48, y: 48 },
): { source: StudioSource; selectedIds: string[] } | null {
  const used = occupiedIds(source);
  const rename = new Map<string, string>();
  const nodes = clipboard.nodes
    .filter((node) => !isProtectedFlowNode(node) && allowedComponent(source, node.component_type))
    .map((node) => {
      const id = takeId(node.component_type, used);
      rename.set(node.id, id);
      return { ...structuredClone(node), id };
    });
  const notes = Object.fromEntries(Object.entries(clipboard.notes ?? {}).map(([id, note]) => {
    const nextId = takeId("note", used);
    rename.set(id, nextId);
    return [nextId, { ...note, x: Math.round(note.x + offset.x), y: Math.round(note.y + offset.y) }];
  }));
  const bindings = source.component_type === "Flow"
    ? Object.fromEntries(Object.entries(clipboard.bindings ?? {}).map(([id, binding]) => {
      const nextId = takeId("bind", used);
      rename.set(id, nextId);
      return [nextId, { ...binding, x: Math.round(binding.x + offset.x), y: Math.round(binding.y + offset.y) }];
    }))
    : {};
  if (!nodes.length && !Object.keys(notes).length && !Object.keys(bindings).length) return null;
  const selectedIds = [...nodes.map((node) => node.id), ...Object.keys(notes), ...Object.keys(bindings)];
  const positions = {
    ...source.ui.positions,
    ...Object.fromEntries(nodes.map((node) => {
      const origin = clipboard.positions[originId(rename, node.id)] ?? { x: 0, y: 0 };
      return [node.id, { x: Math.round(origin.x + offset.x), y: Math.round(origin.y + offset.y) }];
    })),
  };
  const nextNodes = nodes.map((node) => ({
    ...node,
    input_mapping: rewriteMap(node.input_mapping, rename),
    output_mapping: rewriteMap(node.output_mapping, rename),
  }));
  const next: StudioSource = {
    ...source,
    nodes: [...source.nodes, ...nextNodes],
    transitions: [
      ...source.transitions,
      ...clipboard.transitions.flatMap((edge) => {
        const from = rename.get(edge.from);
        const to = rename.get(edge.to);
        return from && to ? [{ ...edge, from, to }] : [];
      }),
    ],
    ui: {
      ...source.ui,
      positions,
      notes: { ...source.ui.notes, ...notes },
      ...(source.component_type === "Flow" ? { bindings: { ...source.ui.bindings, ...bindings } } : {}),
    },
  };
  return { source: next, selectedIds };
}

export function deleteSelection(source: StudioSource, selectedIds: string[], selectedEdgeIds: string[] = []): StudioSource {
  const dropNodes = new Set(
    selectedIds.filter((id) => {
      const node = source.nodes.find((item) => item.id === id);
      return !node || !isProtectedFlowNode(node, source.nodes);
    }),
  );
  const dropEdges = new Set(selectedEdgeIds);
  const nodes = source.nodes.filter((node) => !dropNodes.has(node.id));
  const keptIds = new Set(nodes.map((node) => node.id));
  const notes = Object.fromEntries(Object.entries(source.ui.notes ?? {}).filter(([id]) => !dropNodes.has(id)));
  const bindings = source.component_type === "Flow"
    ? Object.fromEntries(Object.entries(source.ui.bindings ?? {}).filter(([id]) => !dropNodes.has(id)))
    : undefined;
  return {
    ...source,
    nodes,
    transitions: source.transitions.filter((edge) => (
      keptIds.has(edge.from)
      && keptIds.has(edge.to)
      && !dropEdges.has(`${edge.from}:${edge.port}:${edge.to}`)
    )),
    ui: {
      ...source.ui,
      positions: Object.fromEntries(Object.entries(source.ui.positions).filter(([id]) => keptIds.has(id))),
      notes: Object.keys(notes).length ? notes : undefined,
      ...(source.component_type === "Flow" ? { bindings: bindings && Object.keys(bindings).length ? bindings : undefined } : {}),
    },
  };
}

export function selectableCanvasIds(source: StudioSource): string[] {
  return [
    ...source.nodes.map((node) => node.id),
    ...Object.keys(source.ui.notes ?? {}),
    ...Object.keys(source.component_type === "Flow" ? source.ui.bindings ?? {} : {}),
  ];
}
