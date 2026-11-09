export type LayoutNode = { id: string; component_type: string; width?: number; height?: number };
export type LayoutEdge = { from: string; to: string; port?: string };
export type CanvasPoint = { x: number; y: number };
export type CanvasSize = { width: number; height: number };

/** Canvas-only notes should not shrink the executable graph during initial fit. */
export function fitViewCandidates<T extends { id: string; data?: object }>(nodes: T[], includeIntroNote = false): T[] {
  const hasNote = (node: T) => Boolean((node.data as { note?: unknown } | undefined)?.note);
  const graphNodes = nodes.filter((node) => !hasNote(node));
  const introNote = includeIntroNote ? nodes.find((node) => node.id === "note_intro" && hasNote(node)) : undefined;
  const candidates = introNote ? [...graphNodes, introNote] : graphNodes;
  return candidates.length ? candidates : nodes;
}

const NODE_SIZES: Record<string, CanvasSize> = {
  Start: { width: 164, height: 82 },
  Agent: { width: 212, height: 96 },
  Model: { width: 212, height: 96 },
  AgentCall: { width: 224, height: 96 },
  Tool: { width: 204, height: 92 },
  CustomComponent: { width: 236, height: 100 },
  Condition: { width: 190, height: 92 },
  Transform: { width: 204, height: 96 },
  HumanApproval: { width: 228, height: 104 },
  Verifier: { width: 216, height: 100 },
  Output: { width: 184, height: 84 },
};

const HORIZONTAL_GAP = 108;
const VERTICAL_GAP = 48;
const COLLISION_GAP = 18;
const NODE_MIN_WIDTH = 132;
const NODE_MAX_WIDTH = 200;
const NODE_PAD_X = 30;
const NODE_PAD_Y = 22;
const TITLE_LINE = 17;
const ID_LINE = 13;
const TEXT_GAP = 4;
const PORT_GAP = 18;

function glyphWidth(char: string, cjk: number, latin: number): number {
  return /[\u3400-\u9fff]/.test(char) ? cjk : latin;
}

function textWidth(text: string, cjk: number, latin: number): number {
  return [...text].reduce((sum, char) => sum + glyphWidth(char, cjk, latin), 0);
}

export function estimatedNodeSize(componentType: string): CanvasSize {
  return NODE_SIZES[componentType] ?? { width: 208, height: 96 };
}

export function labeledNodeSize(title: string, nodeId: string, portCount = 1): CanvasSize {
  const heading = title.trim() || nodeId;
  const titleWidth = textWidth(heading, 13, 7.2);
  const idWidth = textWidth(nodeId, 8, 6.2);
  const width = Math.round(Math.min(NODE_MAX_WIDTH, Math.max(NODE_MIN_WIDTH, Math.max(titleWidth, idWidth) + NODE_PAD_X)));
  const inner = Math.max(12, width - NODE_PAD_X);
  const titleLines = Math.max(1, Math.ceil(titleWidth / inner));
  const idLines = Math.max(1, Math.ceil(idWidth / inner));
  const ports = Math.max(portCount, 1);
  const height = Math.round(Math.max(
    NODE_PAD_Y + titleLines * TITLE_LINE + TEXT_GAP + idLines * ID_LINE,
    52 + Math.max(0, ports - 1) * PORT_GAP,
  ));
  return { width, height };
}

export function nodeSize(node: LayoutNode): CanvasSize {
  const base = estimatedNodeSize(node.component_type);
  return {
    width: node.width ?? base.width,
    height: node.height ?? base.height,
  };
}

function compareId(left: LayoutNode, right: LayoutNode): number {
  return left.id.localeCompare(right.id);
}

function branchOrder(port: string | undefined): number {
  if (port === "true" || port === "approved" || port === "passed") return -0.35;
  if (port === "false" || port === "rejected" || port === "failed") return 0.35;
  return 0;
}

function boxesOverlap(
  first: LayoutNode,
  firstPosition: CanvasPoint,
  second: LayoutNode,
  secondPosition: CanvasPoint,
): boolean {
  const firstSize = nodeSize(first);
  const secondSize = nodeSize(second);
  return firstPosition.x < secondPosition.x + secondSize.width + COLLISION_GAP
    && firstPosition.x + firstSize.width + COLLISION_GAP > secondPosition.x
    && firstPosition.y < secondPosition.y + secondSize.height + COLLISION_GAP
    && firstPosition.y + firstSize.height + COLLISION_GAP > secondPosition.y;
}

/** Deterministic longest-path DAG layout. Existing coordinates are fixed when supplied. */
export function layoutExecutionGraph(
  nodes: LayoutNode[],
  edges: LayoutEdge[],
  fixedPositions: Record<string, CanvasPoint> = {},
): Record<string, CanvasPoint> {
  if (!nodes.length) return {};
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const incoming = new Map<string, LayoutEdge[]>();
  const outgoing = new Map<string, LayoutEdge[]>();
  for (const node of nodes) {
    incoming.set(node.id, []);
    outgoing.set(node.id, []);
  }
  for (const edge of edges) {
    if (!byId.has(edge.from) || !byId.has(edge.to)) continue;
    incoming.get(edge.to)!.push(edge);
    outgoing.get(edge.from)!.push(edge);
  }

  const indegree = new Map(nodes.map((node) => [node.id, incoming.get(node.id)!.length]));
  const ready = nodes.filter((node) => indegree.get(node.id) === 0).sort(compareId);
  const topological: LayoutNode[] = [];
  const ranks = new Map(nodes.map((node) => [node.id, 0]));
  while (ready.length) {
    const node = ready.shift()!;
    topological.push(node);
    for (const edge of outgoing.get(node.id)!) {
      ranks.set(edge.to, Math.max(ranks.get(edge.to) ?? 0, (ranks.get(node.id) ?? 0) + 1));
      const nextIndegree = (indegree.get(edge.to) ?? 0) - 1;
      indegree.set(edge.to, nextIndegree);
      if (nextIndegree === 0) {
        ready.push(byId.get(edge.to)!);
        ready.sort(compareId);
      }
    }
  }

  // Invalid cyclic drafts still get a finite, stable preview; valid contracts take the DAG path above.
  const cyclic = nodes.filter((node) => !topological.some((item) => item.id === node.id)).sort(compareId);
  const lastRank = Math.max(-1, ...ranks.values());
  cyclic.forEach((node, index) => {
    ranks.set(node.id, lastRank + index + 1);
    topological.push(node);
  });

  const outputRank = Math.max(-1, ...nodes.filter((node) => node.component_type !== "Output").map((node) => ranks.get(node.id) ?? 0)) + 1;
  for (const node of nodes) {
    if (node.component_type === "Output") ranks.set(node.id, Math.max(ranks.get(node.id) ?? 0, outputRank));
  }

  const layers = new Map<number, LayoutNode[]>();
  for (const node of nodes) {
    const rank = ranks.get(node.id) ?? 0;
    const layer = layers.get(rank) ?? [];
    layer.push(node);
    layers.set(rank, layer);
  }
  const orderedLayers = [...layers.keys()].sort((left, right) => left - right);
  const row = new Map<string, number>();
  for (const rank of orderedLayers) {
    const layer = layers.get(rank)!;
    layer.sort((left, right) => {
      const score = (node: LayoutNode) => {
        const parents = incoming.get(node.id) ?? [];
        if (!parents.length) return Number.POSITIVE_INFINITY;
        const values = parents.map((edge) => (row.get(edge.from) ?? 0) + branchOrder(edge.port));
        return values.reduce((sum, value) => sum + value, 0) / values.length;
      };
      const difference = score(left) - score(right);
      return Number.isFinite(difference) && difference !== 0 ? difference : compareId(left, right);
    });
    layer.forEach((node, index) => row.set(node.id, index));
  }

  const columnWidths = new Map<number, number>();
  for (const node of nodes) {
    const rank = ranks.get(node.id) ?? 0;
    columnWidths.set(rank, Math.max(columnWidths.get(rank) ?? 0, nodeSize(node).width));
  }
  const columnX = new Map<number, number>();
  let nextX = 0;
  for (const rank of orderedLayers) {
    columnX.set(rank, nextX);
    nextX += (columnWidths.get(rank) ?? 0) + HORIZONTAL_GAP;
  }

  const layerHeights = new Map<number, number>();
  let maxLayerHeight = 0;
  for (const rank of orderedLayers) {
    const height = layers.get(rank)!.reduce((sum, node) => sum + nodeSize(node).height, 0)
      + Math.max(0, layers.get(rank)!.length - 1) * VERTICAL_GAP;
    layerHeights.set(rank, height);
    maxLayerHeight = Math.max(maxLayerHeight, height);
  }
  const positions: Record<string, CanvasPoint> = {};
  const preferredOrder = orderedLayers.flatMap((rank) => layers.get(rank)!);
  for (const rank of orderedLayers) {
    const layer = layers.get(rank)!;
    const height = layerHeights.get(rank) ?? 0;
    let y = Math.round((maxLayerHeight - height) / 2);
    for (const node of layer) {
      positions[node.id] = { x: columnX.get(rank) ?? 0, y };
      y += nodeSize(node).height + VERTICAL_GAP;
    }
  }

  const placed: LayoutNode[] = [];
  const result: Record<string, CanvasPoint> = {};
  for (const node of nodes) {
    const fixed = fixedPositions[node.id];
    if (!fixed) continue;
    result[node.id] = { x: fixed.x, y: fixed.y };
    placed.push(node);
  }
  for (const node of preferredOrder) {
    if (result[node.id]) continue;
    const preferred = positions[node.id];
    const step = nodeSize(node).height + VERTICAL_GAP;
    const candidates = [preferred, ...Array.from({ length: 60 }, (_, index) => {
      const distance = Math.ceil((index + 1) / 2) * step;
      return { x: preferred.x, y: preferred.y + (index % 2 === 0 ? distance : -distance) };
    })];
    const selected = candidates.find((candidate) => !placed.some((other) => boxesOverlap(node, candidate, other, result[other.id]))) ?? preferred;
    result[node.id] = selected;
    placed.push(node);
  }
  return result;
}

export function centerNoteAboveGraph(
  nodes: LayoutNode[],
  positions: Record<string, CanvasPoint>,
  noteWidth = 420,
  noteHeight = 150,
  gap = 52,
): CanvasPoint {
  const bounds = nodes.flatMap((node) => {
    const position = positions[node.id];
    if (!position) return [];
    const size = nodeSize(node);
    return [{ left: position.x, right: position.x + size.width, top: position.y }];
  });
  if (!bounds.length) return { x: 0, y: -noteHeight - gap };
  const left = Math.min(...bounds.map((item) => item.left));
  const right = Math.max(...bounds.map((item) => item.right));
  const top = Math.min(...bounds.map((item) => item.top));
  return {
    x: Math.round((left + right - noteWidth) / 2),
    y: Math.round(top - noteHeight - gap),
  };
}
