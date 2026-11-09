import type { FlowTransition, RuntimeEvent, RuntimeRunStatus, StudioSource } from "@veyra/api-contracts";

export type NodeExecutionState =
  | "idle"
  | "queued"
  | "running"
  | "waiting_approval"
  | "waiting_budget"
  | "waiting_input"
  | "completed"
  | "failed"
  | "stopped"
  | "skipped";

export type EdgeExecutionState = "idle" | "active" | "traversed" | "failed";

export type ExecutionRunInput = {
  run_id?: string;
  status?: RuntimeRunStatus;
  events?: readonly RuntimeEvent[];
};

export type ExecutionProjection = {
  runId: string | null;
  runStatus: RuntimeRunStatus | null;
  nodeStates: Map<string, NodeExecutionState>;
  edgeStates: Map<string, EdgeExecutionState>;
  nodeEvents: Map<string, RuntimeEvent[]>;
  orderedEvents: RuntimeEvent[];
  activeNodeId: string | null;
  waitingNodeId: string | null;
};

function stateFromEvent(event: RuntimeEvent): NodeExecutionState | null {
  switch (event.kind) {
    case "node.queued":
      return "queued";
    case "node.started":
      return "running";
    case "node.waiting":
    case "approval.requested":
      if (event.payload.kind === "budget" || event.payload.reason === "budget") return "waiting_budget";
      if (event.payload.kind === "input" || event.payload.reason === "input") return "waiting_input";
      return event.kind === "approval.requested" || event.payload.reason === "approval"
        ? "waiting_approval"
        : null;
    case "node.completed":
      return "completed";
    case "node.failed":
      return "failed";
    case "node.cancelled":
      return "stopped";
    case "node.skipped":
      return "skipped";
    case "node.state_changed":
      switch (event.payload.state) {
        case "queued": return "queued";
        case "running": return "running";
        case "waiting_approval": return "waiting_approval";
        case "waiting_budget": return "waiting_budget";
        case "waiting_input": return "waiting_input";
        case "completed":
        case "verified": return "completed";
        case "failed": return "failed";
        case "cancelled": return "stopped";
        case "skipped": return "skipped";
        default: return null;
      }
    default:
      return null;
  }
}

function orderEvents(run: ExecutionRunInput): RuntimeEvent[] {
  const runEvents = (run.events ?? []).filter((event) => !run.run_id || event.run_id === run.run_id);
  const sorted = [...runEvents].sort((left, right) => left.sequence - right.sequence || left.event_id.localeCompare(right.event_id));
  const seenSequences = new Set<number>();
  const seenIds = new Set<string>();
  return sorted.filter((event) => {
    if (seenSequences.has(event.sequence) || seenIds.has(event.event_id)) return false;
    seenSequences.add(event.sequence);
    seenIds.add(event.event_id);
    return true;
  });
}

export function canvasEdgeId(transition: Pick<FlowTransition, "from" | "port" | "to">): string {
  return `${transition.from}:${transition.port}:${transition.to}`;
}

type ExecutionGraph = Pick<StudioSource, "nodes" | "transitions"> & {
  ui?: {
    positions?: Record<string, { x: number; y: number }>;
    bindings?: Record<string, { kind: string; reference: string }>;
  };
};

function catalogBindings(graph: ExecutionGraph): Record<string, { kind: string; reference: string }> {
  return graph.ui?.bindings ?? {};
}

function toolBindingId(graph: ExecutionGraph, reference: unknown): string | null {
  if (typeof reference !== "string" || !reference.trim()) return null;
  const requested = reference.split("@")[0];
  for (const [id, binding] of Object.entries(catalogBindings(graph))) {
    if (binding.kind !== "tool" && binding.kind !== "mcp_tool") continue;
    const bound = binding.reference.split("@")[0];
    if (binding.reference === reference || bound === requested) return id;
  }
  return null;
}

function capabilityStateFromEvent(event: RuntimeEvent): NodeExecutionState | null {
  if (event.kind === "tool.requested" || event.kind === "tool.started") return "running";
  if (event.kind === "tool.completed") return "completed";
  if (event.kind === "tool.failed") return "failed";
  return stateFromEvent(event);
}

export function projectRunToExecutionState(
  graph: ExecutionGraph,
  run: ExecutionRunInput | null | undefined,
): ExecutionProjection {
  const nodeStates = new Map<string, NodeExecutionState>(graph.nodes.map((node) => [node.id, "idle"]));
  const edgeStates = new Map<string, EdgeExecutionState>(graph.transitions.map((edge) => [canvasEdgeId(edge), "idle"]));
  const nodeEvents = new Map<string, RuntimeEvent[]>(graph.nodes.map((node) => [node.id, []]));
  for (const id of Object.keys(catalogBindings(graph))) {
    if (!nodeStates.has(id)) {
      nodeStates.set(id, "idle");
      nodeEvents.set(id, []);
    }
  }
  const orderedEvents = run ? orderEvents(run) : [];

  for (const event of orderedEvents) {
    const bindingId = toolBindingId(graph, event.payload.tool_reference);
    const targetId = (event.node_id && nodeStates.has(event.node_id) ? event.node_id : null) ?? bindingId;
    if (!targetId) continue;
    nodeEvents.get(targetId)?.push(event);
    const next = capabilityStateFromEvent(event);
    if (next) nodeStates.set(targetId, next);
  }

  const selectedEdges = new Set<string>();
  for (const event of orderedEvents) {
    if (event.kind !== "node.completed" || !event.node_id) continue;
    const port = event.payload.port;
    if (typeof port !== "string") continue;
    const edge = graph.transitions.find((item) => item.from === event.node_id && item.port === port);
    if (!edge) continue;
    const id = canvasEdgeId(edge);
    selectedEdges.add(id);
    edgeStates.set(id, "traversed");
  }

  let activeNodeId: string | null = null;
  let waitingNodeId: string | null = null;
  for (const [nodeId, state] of nodeStates) {
    if (state === "running") activeNodeId = nodeId;
    if (state.startsWith("waiting_")) waitingNodeId = nodeId;
  }

  if (run?.status === "cancelled" || run?.status === "interrupted") {
    for (const [nodeId, state] of nodeStates) {
      if (state === "running" || state.startsWith("waiting_")) nodeStates.set(nodeId, "stopped");
    }
    activeNodeId = null;
    waitingNodeId = null;
  }

  if (run?.status === "running" || run?.status === "waiting") {
    for (const transition of graph.transitions) {
      const edgeId = canvasEdgeId(transition);
      if (selectedEdges.has(edgeId) && nodeStates.get(transition.to) === "running") {
        edgeStates.set(edgeId, "active");
      }
    }
  }

  return {
    runId: run?.run_id ?? null,
    runStatus: run?.status ?? null,
    nodeStates,
    edgeStates,
    nodeEvents,
    orderedEvents,
    activeNodeId,
    waitingNodeId,
  };
}
