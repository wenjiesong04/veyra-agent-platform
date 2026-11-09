import type { ProjectAgentRecord } from "@veyra/api-contracts";

export type AgentHierarchyRecord = Pick<
  ProjectAgentRecord,
  "agent_id" | "slug" | "name" | "parent_agent_id" | "source_path"
> & {
  pinned?: boolean;
};

export type AgentTreeNode<T extends AgentHierarchyRecord = AgentHierarchyRecord> = T & {
  children: AgentTreeNode<T>[];
};

export const AGENT_GRAPH_NODE_WIDTH = 168;
export const AGENT_GRAPH_NODE_HEIGHT = 44;
export const AGENT_GRAPH_H_GAP = 28;
export const AGENT_GRAPH_V_GAP = 56;

export function agentTree<T extends AgentHierarchyRecord>(agents: readonly T[]): AgentTreeNode<T>[] {
  const nodes = new Map<string, AgentTreeNode<T>>();
  for (const agent of agents) {
    nodes.set(agent.agent_id, { ...agent, children: [] });
  }
  const roots: AgentTreeNode<T>[] = [];
  for (const node of nodes.values()) {
    const parentId = node.parent_agent_id ?? undefined;
    const parent = parentId ? nodes.get(parentId) : undefined;
    if (parent && parent.agent_id !== node.agent_id) parent.children.push(node);
    else roots.push(node);
  }
  const seen = new Set<string>();
  const mark = (node: AgentTreeNode<T>, visiting: Set<string>) => {
    if (visiting.has(node.agent_id) || seen.has(node.agent_id)) return;
    visiting.add(node.agent_id);
    seen.add(node.agent_id);
    for (const child of node.children) mark(child, visiting);
    visiting.delete(node.agent_id);
  };
  for (const root of roots) mark(root, new Set());
  for (const node of nodes.values()) {
    if (!seen.has(node.agent_id)) roots.push(node);
  }
  const compare = (left: AgentTreeNode<T>, right: AgentTreeNode<T>) => {
    const pin = Number(Boolean(right.pinned)) - Number(Boolean(left.pinned));
    if (pin) return pin;
    return left.slug.localeCompare(right.slug) || left.agent_id.localeCompare(right.agent_id);
  };
  const sortTree = (items: AgentTreeNode<T>[]) => {
    items.sort(compare);
    for (const item of items) sortTree(item.children);
  };
  sortTree(roots);
  return roots;
}

export function agentAncestryPath<T extends AgentHierarchyRecord>(
  agents: readonly T[],
  agentId: string,
): T[] {
  const byId = new Map(agents.map((agent) => [agent.agent_id, agent]));
  const chain: T[] = [];
  const visiting = new Set<string>();
  let current = byId.get(agentId);
  while (current) {
    if (visiting.has(current.agent_id)) break;
    visiting.add(current.agent_id);
    chain.unshift(current);
    const parentId = current.parent_agent_id ?? undefined;
    current = parentId ? byId.get(parentId) : undefined;
  }
  return chain;
}

export function agentRelationEdges<T extends AgentHierarchyRecord>(
  agents: readonly T[],
): Array<{ parent: T; child: T }> {
  const byId = new Map(agents.map((agent) => [agent.agent_id, agent]));
  const edges: Array<{ parent: T; child: T }> = [];
  for (const agent of agents) {
    const parentId = agent.parent_agent_id;
    if (!parentId) continue;
    const parent = byId.get(parentId);
    if (parent) edges.push({ parent, child: agent });
  }
  return edges;
}

export type LaidOutAgent<T extends AgentHierarchyRecord = AgentHierarchyRecord> = {
  agent: T;
  x: number;
  y: number;
};

export type AgentGraphLayout<T extends AgentHierarchyRecord = AgentHierarchyRecord> = {
  nodes: LaidOutAgent<T>[];
  edges: Array<{ parentId: string; childId: string; x1: number; y1: number; x2: number; y2: number }>;
  width: number;
  height: number;
};

export function layoutAgentGraph<T extends AgentHierarchyRecord>(
  agents: readonly T[],
): AgentGraphLayout<T> {
  const forest = agentTree(agents);
  if (!forest.length) return { nodes: [], edges: [], width: 0, height: 0 };
  const placed: LaidOutAgent<T>[] = [];
  const subtreeWidth = (node: AgentTreeNode<T>, visiting: Set<string>): number => {
    if (visiting.has(node.agent_id) || node.children.length === 0) return AGENT_GRAPH_NODE_WIDTH;
    visiting.add(node.agent_id);
    const width = node.children.reduce(
      (sum, child, index) => sum + subtreeWidth(child, visiting) + (index > 0 ? AGENT_GRAPH_H_GAP : 0),
      0,
    );
    visiting.delete(node.agent_id);
    return Math.max(AGENT_GRAPH_NODE_WIDTH, width);
  };
  const place = (node: AgentTreeNode<T>, left: number, depth: number, visiting: Set<string>) => {
    if (visiting.has(node.agent_id)) return AGENT_GRAPH_NODE_WIDTH;
    visiting.add(node.agent_id);
    const width = subtreeWidth(node, new Set());
    placed.push({
      agent: node,
      x: left + width / 2,
      y: depth * (AGENT_GRAPH_NODE_HEIGHT + AGENT_GRAPH_V_GAP),
    });
    let childLeft = left;
    for (const child of node.children) {
      const childWidth = place(child, childLeft, depth + 1, visiting);
      childLeft += childWidth + AGENT_GRAPH_H_GAP;
    }
    visiting.delete(node.agent_id);
    return width;
  };
  let cursor = 0;
  let maxDepth = 0;
  for (const root of forest) {
    const width = place(root, cursor, 0, new Set());
    cursor += width + AGENT_GRAPH_H_GAP;
  }
  for (const node of placed) {
    maxDepth = Math.max(maxDepth, node.y);
  }
  const byId = new Map(placed.map((item) => [item.agent.agent_id, item]));
  const edges = agentRelationEdges(agents).flatMap(({ parent, child }) => {
    const from = byId.get(parent.agent_id);
    const to = byId.get(child.agent_id);
    if (!from || !to) return [];
    return [{
      parentId: parent.agent_id,
      childId: child.agent_id,
      x1: from.x,
      y1: from.y + AGENT_GRAPH_NODE_HEIGHT,
      x2: to.x,
      y2: to.y,
    }];
  });
  return {
    nodes: placed,
    edges,
    width: Math.max(0, cursor - AGENT_GRAPH_H_GAP),
    height: maxDepth + AGENT_GRAPH_NODE_HEIGHT,
  };
}

export function projectFileId(projectId: string, path: string): string {
  return `${projectId}::${path}`;
}

export function parseProjectFileId(fileId: string): { projectId: string; path: string } | null {
  const separator = fileId.indexOf("::");
  if (separator <= 0) return null;
  const projectId = fileId.slice(0, separator);
  const path = fileId.slice(separator + 2);
  return projectId && path ? { projectId, path } : null;
}
