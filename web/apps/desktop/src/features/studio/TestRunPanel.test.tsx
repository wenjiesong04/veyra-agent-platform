import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
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
});
