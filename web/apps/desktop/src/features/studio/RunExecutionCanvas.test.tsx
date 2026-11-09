import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentRunResponse, AgentSource, RuntimeEvent } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { RunExecutionCanvas } from "./RunExecutionCanvas";

class TestResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver = TestResizeObserver;
afterEach(() => cleanup());

const source: AgentSource = {
  schema_version: "1.0",
  agentspec_version: "26.1",
  component_type: "Flow",
  agent_id: "agent-1",
  slug: "approval-flow",
  name: "Approval flow",
  description: "",
  inputs: {},
  outputs: { result: "string" },
  nodes: [
    { id: "start", component_type: "Start" },
    { id: "condition", component_type: "Condition", expression: "approved" },
    { id: "branch_a", component_type: "Model", model_ref: "runtime:model" },
    { id: "branch_b", component_type: "Model", model_ref: "runtime:model" },
    { id: "approval", component_type: "HumanApproval", prompt: "Continue?" },
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
    positions: {
      start: { x: 0, y: 0 },
      condition: { x: 200, y: 0 },
      branch_a: { x: 400, y: -80 },
      branch_b: { x: 400, y: 80 },
      approval: { x: 600, y: -80 },
      out: { x: 800, y: -80 },
    },
    notes: { note_intro: { x: 100, y: -220, text: "Annotation only." } },
  },
  lock: {},
};

function event(kind: RuntimeEvent["kind"], sequence: number, nodeId: string | null, payload: RuntimeEvent["payload"] = {}): RuntimeEvent {
  return {
    schema_version: "1.0",
    event_id: `event-${sequence}`,
    run_id: "run-1",
    sequence,
    kind,
    node_id: nodeId,
    payload,
    timestamp: `2026-09-22T10:00:${String(sequence).padStart(2, "0")}Z`,
  };
}

const waitingRun: AgentRunResponse = {
  schema_version: "1.0",
  run_id: "run-1",
  project_id: "project-1",
  agent_id: "agent-1",
  version_id: "version-1",
  status: "waiting",
  result: null,
  error: null,
  created_at: "2026-09-22T10:00:00Z",
  finished_at: null,
  events: [
    event("node.completed", 1, "condition", { port: "true" }),
    event("node.started", 2, "branch_a"),
    event("node.completed", 3, "branch_a", { port: "next" }),
    event("node.waiting", 4, "approval", { reason: "approval" }),
    event("approval.requested", 5, "approval", { prompt: "Continue?" }),
  ],
};

const approvedRun: AgentRunResponse = {
  ...waitingRun,
  status: "running",
  events: [
    ...(waitingRun.events ?? []),
    event("approval.resolved", 6, "approval", { decision: "approve" }),
    event("node.completed", 7, "approval", { port: "approved" }),
    event("node.started", 8, "out"),
  ],
};

function apiFor(overrides: Partial<LocalProjectApi> = {}): LocalProjectApi {
  return {
    getAgentRun: vi.fn().mockResolvedValue(waitingRun),
    listAgentVersions: vi.fn().mockResolvedValue({
      schema_version: "1.0",
      versions: [{ version_id: "version-1", agent_id: "agent-1", source_hash: "source-hash", behavior_hash: "behavior-hash", created_at: waitingRun.created_at, source }],
    }),
    watchAgentRunEvents: vi.fn().mockReturnValue(() => undefined),
    ...overrides,
  } as unknown as LocalProjectApi;
}

function renderCanvas(api: LocalProjectApi) {
  return render(
    <ThemeProvider>
      <RunExecutionCanvas api={api} projectId="project-1" agentId="agent-1" runId="run-1" locale="en" />
    </ThemeProvider>,
  );
}

describe("RunExecutionCanvas", () => {
  it("restores the exact Run version and shows only the Runtime-selected branch as completed", async () => {
    const api = apiFor();
    renderCanvas(api);

    expect(await screen.findByRole("heading", { name: "Approval flow" })).toBeInTheDocument();
    expect(screen.getByText("Waiting for approval")).toBeInTheDocument();
    expect(document.querySelector('[data-id="branch_a"] .agent-flow-node')).toHaveAttribute("data-state", "completed");
    expect(document.querySelector('[data-id="branch_b"] .agent-flow-node')).toHaveAttribute("data-state", "idle");
    expect(document.querySelector('[data-id="approval"] .agent-flow-node')).toHaveAttribute("data-state", "waiting_approval");
    expect(screen.getByText("Annotation only.")).toBeInTheDocument();
    const approvalNode = document.querySelector('[data-id="approval"]');
    expect(approvalNode).not.toBeNull();
    fireEvent.click(approvalNode!);
    expect(screen.getByRole("button", { name: "View Run Detail" })).toBeInTheDocument();
    expect(api.getAgentRun).toHaveBeenCalledWith("project-1", "agent-1", "run-1");
    expect(api.listAgentVersions).toHaveBeenCalledWith("project-1", "agent-1");
    expect(api.watchAgentRunEvents).toHaveBeenCalledWith(
      "project-1",
      "agent-1",
      "run-1",
      expect.any(Object),
      { after: 5 },
    );
  });

  it("continues approval through the same canonical Run and projects its approved successor", async () => {
    const commandAgentRun = vi.fn().mockResolvedValue(approvedRun);
    const getAgentRun = vi.fn().mockResolvedValueOnce(waitingRun).mockResolvedValue(approvedRun);
    const api = apiFor({ commandAgentRun, getAgentRun });
    renderCanvas(api);

    await screen.findByRole("heading", { name: "Approval flow" });
    await screen.findByRole("button", { name: "Approve" });
    await act(async () => {
      screen.getByRole("button", { name: "Approve" }).click();
    });

    expect(commandAgentRun).toHaveBeenCalledWith("project-1", "agent-1", "run-1", { command: "approve", expected_request_id: "event-5" });
    expect(document.querySelector('[data-id="out"] .agent-flow-node')).toHaveAttribute("data-state", "running");
    expect(screen.getByText("Running")).toBeInTheDocument();
  });

  it("refuses to draw a different or latest version when the pinned one is unavailable", async () => {
    const api = apiFor({
      listAgentVersions: vi.fn().mockResolvedValue({
        schema_version: "1.0",
        versions: [{ version_id: "other-version", agent_id: "agent-1", source_hash: "other", behavior_hash: "other", created_at: waitingRun.created_at, source }],
      }),
    });
    renderCanvas(api);
    expect(await screen.findByRole("heading", { name: "Could not restore the Run canvas" })).toBeInTheDocument();
    expect(screen.getByText(/immutable Agent version for this Run is unavailable/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Approval flow" })).not.toBeInTheDocument();
  });

  it("shows budget continuation instead of approval and preserves pinned Run identity", async () => {
    const budgetRun: AgentRunResponse = { ...waitingRun, events: [...waitingRun.events!, event("approval.requested", 6, "approval", { kind: "budget", request_id: "budget-current", context: { budget: { scope: "run_model_turns", used: 14, limit: 16, remaining: 2 }, required_remaining: 4, max_additional_turns: 32, suggested_additional_turns: 8 } })] };
    const commandAgentRun = vi.fn().mockRejectedValue(new Error("Response unknown"));
    renderCanvas(apiFor({ getAgentRun: vi.fn().mockResolvedValue(budgetRun), commandAgentRun }));
    await screen.findByRole("button", { name: "Continue" });
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(document.querySelector('[data-id="approval"] .agent-flow-node')).toHaveAttribute("data-state", "waiting_budget");
    await act(async () => { screen.getByRole("button", { name: "Continue" }).click(); });
    await screen.findByText("Response unknown");
    expect(commandAgentRun).toHaveBeenCalledTimes(1);
    expect(commandAgentRun.mock.calls[0].slice(0, 4)).toEqual(["project-1", "agent-1", "run-1", { command: "extend_budget", expected_request_id: "budget-current", additional_turns: 8 }]);
  });

  it("refreshes changed approval data after a rejected command without automatically approving it", async () => {
    const newer: AgentRunResponse = { ...waitingRun, events: [...waitingRun.events!, event("approval.requested", 6, "approval", { prompt: "Review a different action", request_id: "request-new" })] };
    let current = waitingRun;
    const commandAgentRun = vi.fn().mockImplementation(async () => {
      if (current === waitingRun) { current = newer; throw new Error("Request changed"); }
      return current;
    });
    renderCanvas(apiFor({ commandAgentRun, getAgentRun: vi.fn().mockImplementation(async () => current) }));
    await screen.findByRole("button", { name: "Approve" });
    await act(async () => { screen.getByRole("button", { name: "Approve" }).click(); });
    expect(await screen.findByText("Review a different action")).toBeInTheDocument();
    expect(commandAgentRun).toHaveBeenCalledTimes(1);
    expect(commandAgentRun).toHaveBeenLastCalledWith("project-1", "agent-1", "run-1", { command: "approve", expected_request_id: "event-5" });
    await act(async () => { screen.getByRole("button", { name: "Reject" }).click(); });
    expect(commandAgentRun).toHaveBeenLastCalledWith("project-1", "agent-1", "run-1", { command: "reject", expected_request_id: "request-new" });
  });
});
