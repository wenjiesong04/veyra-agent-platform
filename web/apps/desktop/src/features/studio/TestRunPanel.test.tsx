import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentRunResponse, AgentSource } from "@veyra/api-contracts";
import type { LocalProjectApi } from "../../api/local-client";
import { TestRunPanel } from "./TestRunPanel";

const source: AgentSource = {
  schema_version: "1.0",
  agentspec_version: "26.1",
  component_type: "Flow",
  agent_id: "agent-1",
  slug: "runner",
  name: "Runner",
  description: "A deterministic local runner.",
  inputs: { name: "string" },
  outputs: { result: "string" },
  nodes: [
    { id: "start", component_type: "Start" },
    { id: "transform", component_type: "Transform", mapping: { result: "Hello {{name}}" } },
    { id: "output", component_type: "Output", output_name: "result" },
  ],
  transitions: [
    { from: "start", port: "next", to: "transform" },
    { from: "transform", port: "next", to: "output" },
  ],
  extensions: {
    veyra: {
      runtime_profile: "veyra-runtime-profile/1",
      secret_refs: [],
      permissions: { network_hosts: [], tools: [] },
      verification: { required: false, checks: [] },
    },
  },
  ui: { positions: { start: { x: 0, y: 0 }, transform: { x: 200, y: 0 }, output: { x: 400, y: 0 } } },
  lock: { "veyra.runtime.profile@1.0.0": "0".repeat(64) },
};

const run: AgentRunResponse = {
  schema_version: "1.0",
  run_id: "run-1",
  project_id: "project-1",
  agent_id: "agent-1",
  version_id: "version-1",
  status: "unverified",
  result: { result: "Hello Ada" },
  error: null,
  created_at: "2026-08-28T10:00:00Z",
  finished_at: "2026-08-28T10:00:01Z",
};

afterEach(() => cleanup());

describe("TestRunPanel", () => {
  it("submits typed inputs and renders durable run evidence", async () => {
    const runAgent = vi.fn().mockResolvedValue(run);
    const getAgentRun = vi.fn().mockResolvedValue({
      ...run,
      events: [{
        schema_version: "1.0",
        event_id: "event-1",
        run_id: "run-1",
        sequence: 1,
        kind: "run.created",
        node_id: null,
        payload: {},
        timestamp: "2026-08-28T10:00:00Z",
      }],
    });
    const api = { runAgent, getAgentRun } as unknown as LocalProjectApi;
    const user = userEvent.setup();

    render(<TestRunPanel api={api} projectId="project-1" agentId="agent-1" source={source} disabled={false} locale="en" />);
    await user.type(screen.getByRole("textbox"), "Ada");
    await user.click(screen.getByRole("button", { name: "Test run" }));

    await waitFor(() => expect(runAgent).toHaveBeenCalledWith(
      "project-1",
      "agent-1",
      { inputs: { name: "Ada" } },
    ));
    expect(await screen.findByText("Run created")).toBeInTheDocument();
    expect(screen.getByText("run.created")).toBeInTheDocument();
    expect(screen.getByText(/Hello Ada/)).toBeInTheDocument();
  });

  it("sends approve when a run is waiting", async () => {
    const waiting: AgentRunResponse = {
      ...run,
      status: "waiting",
      result: null,
      finished_at: null,
      events: [{
        schema_version: "1.0",
        event_id: "event-2",
        run_id: "run-1",
        sequence: 4,
        kind: "approval.requested",
        node_id: "approve",
        payload: { prompt: "Write notes.txt?" },
        timestamp: "2026-08-28T10:00:02Z",
      }],
    };
    const commandAgentRun = vi.fn().mockResolvedValue({ ...run, status: "unverified", result: { written: true } });
    const getAgentRun = vi.fn().mockResolvedValue(waiting);
    const api = { runAgent: vi.fn().mockResolvedValue(waiting), getAgentRun, commandAgentRun } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    render(<TestRunPanel api={api} projectId="project-1" agentId="agent-1" source={source} disabled={false} locale="en" />);
    await user.click(screen.getByRole("button", { name: "Test run" }));
    expect(await screen.findByText("Write notes.txt?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(commandAgentRun).toHaveBeenCalledWith("project-1", "agent-1", "run-1", { command: "approve" }));
  });

  it("paints node run states from the live event stream", async () => {
    const running: AgentRunResponse = { ...run, status: "running", result: null, finished_at: null, events: [] };
    let emit: ((event: NonNullable<AgentRunResponse["events"]>[number]) => void) | undefined;
    const watchAgentRunEvents = vi.fn((_project: string, _agent: string, _run: string, handlers: { onEvent: (event: NonNullable<AgentRunResponse["events"]>[number]) => void }) => {
      emit = handlers.onEvent;
      return () => undefined;
    });
    const api = { runAgent: vi.fn().mockResolvedValue(running), getAgentRun: vi.fn().mockResolvedValue(running), watchAgentRunEvents } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    render(<TestRunPanel api={api} projectId="project-1" agentId="agent-1" source={source} disabled={false} locale="en" />);
    await user.click(screen.getByRole("button", { name: "Test run" }));
    await waitFor(() => expect(watchAgentRunEvents).toHaveBeenCalled());
    emit?.({
      schema_version: "1.0",
      event_id: "event-3",
      run_id: "run-1",
      sequence: 3,
      kind: "node.started",
      node_id: "transform",
      payload: {},
      timestamp: "2026-08-28T10:00:00Z",
    });
    expect(await screen.findByRole("list", { name: "Node run states" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Node run states" }).querySelector('[data-state="running"]')).toHaveTextContent("transform");
  });
});
