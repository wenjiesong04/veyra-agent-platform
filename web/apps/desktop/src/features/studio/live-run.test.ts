import { describe, expect, it } from "vitest";
import type { AgentRunResponse, AgentSource, RuntimeEvent } from "@veyra/api-contracts";
import { applyRuntimeEvent, inferRunStatus, nodeRunStates } from "./live-run";

const source: AgentSource = {
  schema_version: "1.0", agentspec_version: "26.1", component_type: "Flow", agent_id: "agent-1", slug: "runner", name: "Runner", description: "",
  inputs: {}, outputs: { result: "string" },
  nodes: [{ id: "start", component_type: "Start" }, { id: "write", component_type: "Tool", uses: "veyra.tool.filesystem.write@1.0.0" }, { id: "out", component_type: "Output", output_name: "result" }],
  transitions: [],
  extensions: { veyra: { runtime_profile: "guarded", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } },
  ui: { positions: {} }, lock: {},
};

const run: AgentRunResponse = {
  schema_version: "1.0", run_id: "run-1", project_id: "project-1", agent_id: "agent-1", version_id: "version-1",
  status: "running", result: null, error: null, created_at: "2026-08-28T10:00:00Z", finished_at: null, events: [],
};

function event(kind: RuntimeEvent["kind"], sequence: number, nodeId: string | null = null, payload: RuntimeEvent["payload"] = {}): RuntimeEvent {
  return { schema_version: "1.0", event_id: `event-${sequence}`, run_id: "run-1", sequence, kind, node_id: nodeId, payload, timestamp: "2026-08-28T10:00:00Z" };
}

describe("live run projections", () => {
  it("infers waiting from approval events without treating it as success", () => {
    const events = [event("run.started", 1), event("node.started", 2, "start"), event("node.waiting", 3, "write"), event("approval.requested", 4, "write", { prompt: "Write notes.txt?" })];
    expect(inferRunStatus("running", events)).toBe("waiting");
    expect(nodeRunStates(source, events)).toEqual([
      { id: "start", state: "running" },
      { id: "write", state: "waiting" },
      { id: "out", state: "pending" },
    ]);
  });

  it("appends live events and keeps failed nodes failed", () => {
    const withStart = applyRuntimeEvent(run, event("node.started", 1, "write"));
    const failed = applyRuntimeEvent(withStart, event("node.failed", 2, "write"));
    expect(failed?.status).toBe("running");
    expect(nodeRunStates(source, failed?.events ?? []).find((node) => node.id === "write")?.state).toBe("failed");
    expect(applyRuntimeEvent(failed, event("node.failed", 2, "write"))).toBe(failed);
  });
});
