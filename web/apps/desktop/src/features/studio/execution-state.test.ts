import { describe, expect, it } from "vitest";
import type { AgentSource, RuntimeEvent } from "@veyra/api-contracts";
import { canvasEdgeId, projectRunToExecutionState } from "./execution-state";

const graph: AgentSource = {
  schema_version: "1.0",
  agentspec_version: "26.1",
  component_type: "Flow",
  agent_id: "agent-1",
  slug: "runner",
  name: "Runner",
  description: "",
  inputs: {},
  outputs: { result: "string" },
  nodes: [
    { id: "start", component_type: "Start" },
    { id: "condition", component_type: "Condition", expression: "ok" },
    { id: "branch_a", component_type: "Model", model_ref: "runtime:model" },
    { id: "branch_b", component_type: "Model", model_ref: "runtime:model" },
    { id: "approval", component_type: "HumanApproval", prompt: "Approve?" },
    { id: "out", component_type: "Output", output_name: "result" },
  ],
  transitions: [
    { from: "start", port: "next", to: "condition" },
    { from: "condition", port: "true", to: "branch_a" },
    { from: "condition", port: "false", to: "branch_b" },
    { from: "branch_a", port: "next", to: "approval" },
    { from: "approval", port: "approved", to: "out" },
  ],
  extensions: {
    veyra: {
      runtime_profile: "guarded",
      secret_refs: [],
      permissions: { network_hosts: [], tools: [] },
      verification: { required: false, checks: [] },
    },
  },
  ui: {
    positions: {},
    notes: { note_intro: { x: 10, y: 20, text: "This note is annotation only." } },
  },
  lock: {},
};

function event(
  kind: RuntimeEvent["kind"],
  sequence: number,
  nodeId: string | null = null,
  payload: RuntimeEvent["payload"] = {},
  runId = "run-1",
): RuntimeEvent {
  return {
    schema_version: "1.0",
    event_id: `event-${sequence}`,
    run_id: runId,
    sequence,
    kind,
    node_id: nodeId,
    payload,
    timestamp: `2026-09-22T10:00:${String(sequence).padStart(2, "0")}Z`,
  };
}

describe("canonical run execution projection", () => {
  it("keeps a fresh graph idle and excludes annotation notes", () => {
    const projection = projectRunToExecutionState(graph, null);
    expect([...projection.nodeStates.values()]).toEqual(["idle", "idle", "idle", "idle", "idle", "idle"]);
    expect(projection.edgeStates.get("condition:true:branch_a")).toBe("idle");
    expect(projection.nodeStates.has("note_intro")).toBe(false);
  });

  it("orders persisted events by sequence and is idempotent for replayed events", () => {
    const started = event("node.started", 2, "branch_a");
    const completed = event("node.completed", 3, "branch_a", { port: "next" });
    const projection = projectRunToExecutionState(graph, {
      run_id: "run-1",
      status: "verified",
      events: [completed, started, started],
    });

    expect(projection.orderedEvents.map((item) => item.sequence)).toEqual([2, 3]);
    expect(projection.nodeStates.get("branch_a")).toBe("completed");
    expect(projection.edgeStates.get("branch_a:next:approval")).toBe("traversed");
  });

  it("marks only the canonical Condition output as active or traversed", () => {
    const projection = projectRunToExecutionState(graph, {
      run_id: "run-1",
      status: "running",
      events: [
        event("node.completed", 1, "condition", { port: "true" }),
        event("node.started", 2, "branch_a"),
      ],
    });

    expect(projection.edgeStates.get("condition:true:branch_a")).toBe("active");
    expect(projection.edgeStates.get("condition:false:branch_b")).toBe("idle");
    expect(projection.nodeStates.get("branch_a")).toBe("running");
    expect(projection.nodeStates.get("branch_b")).toBe("idle");
  });

  it("projects explicit queued, skipped, and failed node events", () => {
    const projection = projectRunToExecutionState(graph, {
      run_id: "run-1",
      status: "failed",
      events: [
        event("node.queued", 1, "branch_a"),
        event("node.skipped", 2, "branch_b"),
        event("node.failed", 3, "approval", { error_code: "approval_timeout" }),
      ],
    });

    expect(projection.nodeStates.get("branch_a")).toBe("queued");
    expect(projection.nodeStates.get("branch_b")).toBe("skipped");
    expect(projection.nodeStates.get("approval")).toBe("failed");
  });

  it("marks the actual approval node waiting and clears it when resolved", () => {
    const waiting = projectRunToExecutionState(graph, {
      run_id: "run-1",
      status: "waiting",
      events: [
        event("node.waiting", 1, "approval", { reason: "approval" }),
        event("approval.requested", 2, "approval", { prompt: "Approve?" }),
      ],
    });
    expect(waiting.nodeStates.get("approval")).toBe("waiting_approval");
    expect(waiting.waitingNodeId).toBe("approval");

    const approved = projectRunToExecutionState(graph, {
      run_id: "run-1",
      status: "running",
      events: [
        event("node.waiting", 1, "approval", { reason: "approval" }),
        event("approval.resolved", 2, "approval", { decision: "approve" }),
        event("node.completed", 3, "approval", { port: "approved" }),
        event("node.started", 4, "out"),
      ],
    });
    expect(approved.nodeStates.get("approval")).toBe("completed");
    expect(approved.edgeStates.get("approval:approved:out")).toBe("active");
  });

  it("stops only nodes that were actually in progress when the run was cancelled", () => {
    const projection = projectRunToExecutionState(graph, {
      run_id: "run-1",
      status: "cancelled",
      events: [
        event("node.started", 1, "branch_a"),
        event("node.waiting", 2, "approval", { reason: "approval" }),
      ],
    });

    expect(projection.nodeStates.get("branch_a")).toBe("stopped");
    expect(projection.nodeStates.get("approval")).toBe("stopped");
    expect(projection.nodeStates.get("branch_b")).toBe("idle");
    expect(projection.activeNodeId).toBeNull();
    expect(projection.waitingNodeId).toBeNull();
  });

  it("ignores events from other runs and uses the stable graph edge identity", () => {
    const edge = graph.transitions[1];
    expect(edge).toBeDefined();
    expect(canvasEdgeId(edge!)).toBe("condition:true:branch_a");
    const projection = projectRunToExecutionState(graph, {
      run_id: "run-1",
      status: "running",
      events: [event("node.started", 1, "branch_a", {}, "run-2")],
    });
    expect(projection.orderedEvents).toEqual([]);
    expect(projection.nodeStates.get("branch_a")).toBe("idle");
  });
});
