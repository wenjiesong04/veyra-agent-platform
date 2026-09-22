import type { FlowTransition, RuntimeEvent, RuntimeRunStatus, StudioSource } from "@veyra/api-contracts";

export type NodeExecutionState =
  | "idle"
  | "queued"
  | "running"
  | "waiting_approval"
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

export function projectRunToExecutionState(
  graph: Pick<StudioSource, "nodes" | "transitions">,
  run: ExecutionRunInput | null | undefined,
): ExecutionProjection {
  const nodeStates = new Map<string, NodeExecutionState>(graph.nodes.map((node) => [node.id, "idle"]));
  const edgeStates = new Map<string, EdgeExecutionState>(graph.transitions.map((edge) => [canvasEdgeId(edge), "idle"]));
  const nodeEvents = new Map<string, RuntimeEvent[]>(graph.nodes.map((node) => [node.id, []]));
  const orderedEvents = run ? orderEvents(run) : [];

  for (const event of orderedEvents) {
    if (!event.node_id || !nodeStates.has(event.node_id)) continue;
    nodeEvents.get(event.node_id)?.push(event);
    const next = stateFromEvent(event);
    if (next) nodeStates.set(event.node_id, next);
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
  for (const node of graph.nodes) {
    const state = nodeStates.get(node.id);
    if (state === "running") activeNodeId = node.id;
    if (state === "waiting_approval") waitingNodeId = node.id;
  }

  if (run?.status === "cancelled" || run?.status === "interrupted") {
    for (const [nodeId, state] of nodeStates) {
      if (state === "running" || state === "waiting_approval") nodeStates.set(nodeId, "stopped");
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
