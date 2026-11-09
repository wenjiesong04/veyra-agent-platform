import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentRunResponse, AgentSource, RuntimeEvent } from "@veyra/api-contracts";
import { applyRuntimeEvent, approvalRequestBinding, approvalRequestId, inferRunStatus, nodeRunStates, runCommandKey, useLiveRun } from "./live-run";
import type { LocalProjectApi } from "../../api/local-client";

afterEach(cleanup);

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
  it("binds budget continuation and Stop to the current nonce without legacy fallback", () => {
    const waiting = { ...run, status: "waiting" as const, events: [event("approval.requested", 1, "model", { kind: "budget", request_id: "budget-current" })] };
    expect(approvalRequestBinding(waiting, "extend_budget")).toEqual({ expected_request_id: "budget-current" });
    expect(approvalRequestBinding(waiting, "stop")).toEqual({ expected_request_id: "budget-current" });
    const missing = { ...waiting, events: [event("approval.requested", 2, "model", { kind: "budget" })] };
    expect(() => approvalRequestBinding(missing, "extend_budget")).toThrow("current budget request is unavailable");
    const keys = new Map<string, string>();
    const key = runCommandKey(keys, waiting, "extend_budget", 8);
    expect(runCommandKey(keys, waiting, "extend_budget", 8)).toBe(key);
    expect(runCommandKey(keys, waiting, "extend_budget", 9)).not.toBe(key);
    expect(runCommandKey(keys, { ...waiting, events: [event("approval.requested", 3, "model", { kind: "budget", request_id: "budget-new" })] }, "extend_budget", 8)).not.toBe(key);
  });
  it("binds visible Agent requests to their nonce and falls back to legacy event identity", () => {
    const waiting = { ...run, status: "waiting" as const, events: [event("approval.requested", 1, "model", { request_id: "question-1" })] };
    expect(approvalRequestId(waiting)).toBe("question-1");
    expect(approvalRequestBinding(waiting, "reply")).toEqual({ expected_request_id: "question-1" });
    const legacy = { ...waiting, events: [event("approval.requested", 2)] };
    expect(approvalRequestBinding(legacy, "approve")).toEqual({ expected_request_id: "event-2" });
    for (const command of ["stop", "retry", "resume"]) expect(approvalRequestBinding(waiting, command)).toEqual({});
  });

  it("uses Workflow waiting identity rather than a synthetic or earlier approval event", () => {
    const { agent_id: _agentId, ...base } = run;
    const waiting = { ...base, workflow_id: "workflow-1", status: "waiting" as const, children: [], waiting: { kind: "input", node_id: "call", prompt: "Question", request_id: "child-question-2" }, events: [event("approval.requested", 1, "call", { request_id: "old-request" })] };
    expect(approvalRequestBinding(waiting, "reply")).toEqual({ expected_request_id: "child-question-2" });
    expect(() => approvalRequestBinding({ ...waiting, waiting: { ...waiting.waiting, request_id: undefined } }, "approve")).toThrow("current request is unavailable");
    expect(() => approvalRequestBinding({ ...waiting, status: "running" }, "reply")).toThrow("current request is unavailable");
  });

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

describe("read-only Run restoration", () => {
  it("does not restore a late result after the view was cleared", async () => {
    let resolve!: (value: AgentRunResponse) => void;
    const response = new Promise<AgentRunResponse>((accept) => { resolve = accept; });
    const api = { getAgentRun: vi.fn().mockReturnValue(response), runAgent: vi.fn(), commandAgentRun: vi.fn() } as unknown as LocalProjectApi;
    const { result } = renderHook(() => useLiveRun({ api, projectId: "project-1", agentId: "agent-1" }));
    let restoring!: Promise<void>;
    act(() => { restoring = result.current.restore(run.run_id); });
    act(() => result.current.clear());
    await act(async () => { resolve(run); await restoring; });
    expect(result.current.run).toBeNull();
    expect(result.current.error).toBe("");
    expect(result.current.busy).toBe(false);
    expect(api.runAgent).not.toHaveBeenCalled();
    expect(api.commandAgentRun).not.toHaveBeenCalled();
  });

  it("only adopts the latest requested Run when restorations finish out of order", async () => {
    let resolveFirst!: (value: AgentRunResponse) => void;
    let resolveSecond!: (value: AgentRunResponse) => void;
    const first = new Promise<AgentRunResponse>((accept) => { resolveFirst = accept; });
    const second = new Promise<AgentRunResponse>((accept) => { resolveSecond = accept; });
    const api = { getAgentRun: vi.fn().mockReturnValueOnce(first).mockReturnValueOnce(second) } as unknown as LocalProjectApi;
    const { result } = renderHook(() => useLiveRun({ api, projectId: "project-1", agentId: "agent-1" }));
    let earlier!: Promise<void>;
    let latest!: Promise<void>;
    act(() => { earlier = result.current.restore("run-1"); latest = result.current.restore("run-2"); });
    await act(async () => { resolveSecond({ ...run, run_id: "run-2" }); await latest; });
    expect(result.current.run?.run_id).toBe("run-2");
    await act(async () => { resolveFirst(run); await earlier; });
    expect(result.current.run?.run_id).toBe("run-2");
    expect(result.current.busy).toBe(false);
  });

  it("does not surface a stale restoration error after clear", async () => {
    let reject!: (cause: Error) => void;
    const response = new Promise<AgentRunResponse>((_accept, fail) => { reject = fail; });
    const api = { getAgentRun: vi.fn().mockReturnValue(response) } as unknown as LocalProjectApi;
    const { result } = renderHook(() => useLiveRun({ api, projectId: "project-1", agentId: "agent-1" }));
    let restoring!: Promise<void>;
    act(() => { restoring = result.current.restore("run-1"); });
    act(() => result.current.clear());
    await act(async () => { reject(new Error("Old request failed")); await restoring; });
    expect(result.current.error).toBe("");
    expect(result.current.run).toBeNull();
  });

  it("keeps a new pinned execution when an older read-only restoration finishes", async () => {
    let resolve!: (value: AgentRunResponse) => void;
    const response = new Promise<AgentRunResponse>((accept) => { resolve = accept; });
    const started = { ...run, run_id: "new-run", version_id: "version-2" };
    const api = { getAgentRun: vi.fn().mockReturnValueOnce(response).mockResolvedValueOnce(started), runAgent: vi.fn().mockResolvedValue(started) } as unknown as LocalProjectApi;
    const { result } = renderHook(() => useLiveRun({ api, projectId: "project-1", agentId: "agent-1" }));
    let restoring!: Promise<void>;
    act(() => { restoring = result.current.restore("run-1"); });
    await act(async () => result.current.start({ request: "New input" }, { source: "committed", versionId: "version-2" }));
    expect(result.current.run?.run_id).toBe("new-run");
    await act(async () => { resolve(run); await restoring; });
    expect(result.current.run?.run_id).toBe("new-run");
    expect(result.current.run?.version_id).toBe("version-2");
    expect(result.current.busy).toBe(false);
    expect(api.runAgent).toHaveBeenCalledExactlyOnceWith("project-1", "agent-1", { inputs: { request: "New input" }, source: "committed", version_id: "version-2" });
  });

  it("rejects identity mismatches on the latest restoration", async () => {
    const api = { getAgentRun: vi.fn().mockResolvedValue({ ...run, version_id: "version-1", project_id: "wrong-project" }) } as unknown as LocalProjectApi;
    const { result } = renderHook(() => useLiveRun({ api, projectId: "project-1", agentId: "agent-1" }));
    await act(async () => result.current.restore(run.run_id));
    expect(result.current.run).toBeNull();
    expect(result.current.error).toBe("Runtime run identity mismatch");
  });
});
