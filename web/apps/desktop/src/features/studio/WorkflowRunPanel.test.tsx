import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { WorkflowRunResponse, WorkflowSource } from "@veyra/api-contracts";
import type { LocalProjectApi } from "../../api/local-client";
import { WorkflowRunPanel } from "./WorkflowRunPanel";

const source: WorkflowSource = {
  schema_version: "1.0",
  component_type: "Workflow",
  workflow_id: "wf-1",
  slug: "review-path",
  name: "Review path",
  description: "",
  version: "1.0.0",
  inputs: { prompt: "string" },
  outputs: { result: "string" },
  nodes: [
    { id: "start", component_type: "Start" },
    { id: "call", component_type: "AgentCall", agent_ref: "agent-1@version-1" },
    { id: "output", component_type: "Output", output_name: "result" },
  ],
  transitions: [
    { from: "start", port: "next", to: "call" },
    { from: "call", port: "next", to: "output" },
  ],
  extensions: { veyra: { permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } },
  ui: { positions: { start: { x: 0, y: 0 }, call: { x: 200, y: 0 }, output: { x: 400, y: 0 } } },
  lock: {},
};

const run: WorkflowRunResponse = {
  schema_version: "1.0",
  run_id: "run-w1",
  project_id: "project-1",
  workflow_id: "wf-1",
  version_id: "wf-version-1",
  status: "unverified",
  result: { result: "Hello Ada" },
  error: null,
  created_at: "2026-08-28T10:00:00Z",
  finished_at: "2026-08-28T10:00:01Z",
  waiting: null,
  children: [{ node_id: "call", agent_id: "agent-1", version_id: "version-1", child_run_id: "child-1", status: "unverified" }],
};

afterEach(() => cleanup());

describe("WorkflowRunPanel", () => {
  it("uses named fields and the test-run chrome instead of a JSON editor", async () => {
    const runWorkflow = vi.fn().mockResolvedValue(run);
    const getWorkflowRun = vi.fn().mockResolvedValue({
      ...run,
      events: [{
        schema_version: "1.0",
        event_id: "event-1",
        run_id: "run-w1",
        sequence: 1,
        kind: "run.created",
        node_id: null,
        payload: {},
        timestamp: "2026-08-28T10:00:00Z",
      }],
    });
    const api = { runWorkflow, getWorkflowRun } as unknown as LocalProjectApi;
    const user = userEvent.setup();

    render(<WorkflowRunPanel api={api} projectId="project-1" workflowId="wf-1" source={source} disabled={false} locale="en" />);
    expect(screen.getByRole("button", { name: "Test run" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /Workflow run inputs/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run Workflow" })).not.toBeInTheDocument();
    await user.type(screen.getByRole("textbox"), "Ada");
    await user.click(screen.getByRole("button", { name: "Test run" }));

    await waitFor(() => expect(runWorkflow).toHaveBeenCalledWith(
      "project-1",
      "wf-1",
      { inputs: { prompt: "Ada" } },
    ));
    expect(await screen.findByText("Run created")).toBeInTheDocument();
    expect(screen.getByText(/Hello Ada/)).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Child Agent runs" })).toHaveTextContent("call");
  });

  it("sends approve when a workflow run is waiting", async () => {
    const waiting: WorkflowRunResponse = {
      ...run,
      status: "waiting",
      result: null,
      finished_at: null,
      waiting: { kind: "approval", node_id: "call", prompt: "Write notes.txt?", agent_id: "agent-1", child_run_id: "child-1" },
      children: [{ node_id: "call", agent_id: "agent-1", version_id: "version-1", child_run_id: "child-1", status: "waiting" }],
    };
    const commandWorkflowRun = vi.fn().mockResolvedValue({ ...run, status: "unverified", waiting: null });
    const getWorkflowRun = vi.fn().mockResolvedValue(waiting);
    const api = { runWorkflow: vi.fn().mockResolvedValue(waiting), getWorkflowRun, commandWorkflowRun } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    render(<WorkflowRunPanel api={api} projectId="project-1" workflowId="wf-1" source={source} disabled={false} locale="en" />);
    await user.click(screen.getByRole("button", { name: "Test run" }));
    expect(await screen.findByText("Write notes.txt?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(commandWorkflowRun).toHaveBeenCalledWith("project-1", "wf-1", "run-w1", { command: "approve" }));
  });

  it("collapses the overlay chrome without leaving the JSON editor behind", async () => {
    const api = { runWorkflow: vi.fn() } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    render(<WorkflowRunPanel api={api} projectId="project-1" workflowId="wf-1" source={source} disabled={false} locale="en" />);
    expect(screen.getByRole("button", { name: "Test run" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Collapse test panel" }));
    expect(screen.queryByRole("button", { name: "Test run" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand test panel" })).toHaveAttribute("aria-expanded", "false");
  });
});
