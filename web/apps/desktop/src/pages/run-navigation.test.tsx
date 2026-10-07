import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentRunResponse, AgentSource, ProjectSummaryResponse, WorkItem } from "@veyra/api-contracts";
import { projectRoutePaths } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { LocalApiClient, type LocalProjectApi } from "../api/local-client";
import { ProjectWorkspaceProvider } from "../api/project-workspace";
import { AgentRunPage } from "./agent-run";
import { MonitorPage } from "./monitor";
import { StudioPage } from "./studio";
import { runDetailHref, runMonitorHref, runStudioHref } from "../features/runs/run-location";
import { RunDetail } from "../features/runs/RunDetail";
import userEvent from "@testing-library/user-event";

const identity = { projectId: "project-1", agentId: "agent-1", runId: "historical-1" };
const executionSource: AgentSource = {
  schema_version: "1.0", agentspec_version: "26.1", component_type: "Flow", agent_id: "agent-1", slug: "runner", name: "Runner", description: "",
  inputs: {}, outputs: { result: "string" },
  nodes: [{ id: "start", component_type: "Start" }, { id: "tool", component_type: "Tool", uses: "veyra.tool.example@1.0.0" }, { id: "out", component_type: "Output", output_name: "result" }],
  transitions: [{ from: "start", port: "next", to: "tool" }, { from: "tool", port: "next", to: "out" }],
  extensions: { veyra: { runtime_profile: "guarded", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } },
  ui: { positions: { start: { x: 0, y: 0 }, tool: { x: 200, y: 0 }, out: { x: 400, y: 0 } } },
  lock: { "veyra.tool.example@1.0.0": "sha256:locked" },
};
const run: AgentRunResponse = {
  schema_version: "1.0", project_id: identity.projectId, agent_id: identity.agentId, run_id: identity.runId,
  version_id: "version-original", status: "failed", result: null, error: { code: "tool_failed", message: "Original failure" },
  created_at: "2026-09-01T10:00:00Z", finished_at: "2026-09-01T10:00:01Z",
  events: [{ schema_version: "1.0", event_id: "receipt-1", run_id: identity.runId, sequence: 1, kind: "tool.failed", node_id: "tool", timestamp: "2026-09-01T10:00:01Z", payload: { receipt: "original-evidence" } }],
};
const project = {
  schema_version: "1.0", project_id: "project-1", name: "Project", agents: [{ agent_id: "agent-1", name: "Agent", slug: "agent" }],
} as ProjectSummaryResponse;

function setup() {
  const fetcher = vi.fn().mockImplementation(async () => new Response(JSON.stringify(run), { status: 200, headers: { "Content-Type": "application/json" } }));
  const client = new LocalApiClient({ fetcher });
  const item: WorkItem = {
    schema_version: "1.0", work_item_id: "work-1", project_id: "project-1", agent_id: "agent-1", title: "Work", description: "", inputs: {},
    status: "failed", run_id: "newer-run", depends_on: [], created_at: run.created_at, updated_at: run.finished_at!,
    attempts: [{ attempt_id: "attempt-1", attempt_number: 1, run_id: identity.runId, status: "failed", failure_class: null, claimed_at: run.created_at, started_at: run.created_at, finished_at: run.finished_at, created_at: run.created_at }],
  };
  const api = {
    listProjects: vi.fn().mockResolvedValue({ projects: [project] }),
    listAgentRuns: vi.fn().mockResolvedValue({ runs: [{ ...run, events: undefined }] }),
    listAgentVersions: vi.fn().mockResolvedValue({ schema_version: "1.0", versions: [{ version_id: "version-original", agent_id: "agent-1", source_hash: "source-hash", behavior_hash: "behavior-hash", created_at: run.created_at, source: executionSource, committed: true }] }),
    getAgentRun: vi.fn(client.getAgentRun.bind(client)),
    runAgent: vi.fn(), getDraft: vi.fn(),
    orchestratorStatus: vi.fn().mockResolvedValue({ active: [], counts: {}, limits: {}, stale_count: 0 }),
    listWorkItems: vi.fn().mockResolvedValue({ work_items: [item] }),
  } as unknown as LocalProjectApi;
  return { api, fetcher };
}

function mount(api: LocalProjectApi, page: React.ReactNode) {
  return render(<ThemeProvider><ProjectWorkspaceProvider api={api}>{page}</ProjectWorkspaceProvider></ThemeProvider>);
}

afterEach(() => { cleanup(); window.history.replaceState(null, "", "#/projects"); });

describe("historical run navigation", () => {
  it("opens Workflow run details in the App and keeps Studio as the design surface", () => {
    const workflowIdentity = { projectId: "project-1", workflowId: "workflow-1", runId: "workflow-run-1" };
    expect(runDetailHref(workflowIdentity)).toBe(`${projectRoutePaths.workflowRun("project-1", "workflow-1")}?run_id=workflow-run-1`);
    expect(runStudioHref(workflowIdentity)).toBe(`${projectRoutePaths.workflow("project-1", "workflow-1")}?run_id=workflow-run-1`);
  });
  it("resumes an explicit execution checkpoint once and opens its descendant", async () => {
    const { api } = setup();
    const events = [{ ...run.events![0], kind: "checkpoint.created" as const, payload: { checkpoint_id: "checkpoint-1", waiting_kind: "execution" } }];
    vi.mocked(api.getAgentRun!).mockResolvedValue({ ...run, status: "interrupted", events });
    let finish!: (value: AgentRunResponse) => void;
    api.commandAgentRun = vi.fn().mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    mount(api, <RunDetail api={api} {...identity} locale="en" />);
    const button = await screen.findByRole("button", { name: "Resume from checkpoint" });
    await userEvent.setup().dblClick(button);
    expect(api.commandAgentRun).toHaveBeenCalledTimes(1);
    expect(api.commandAgentRun).toHaveBeenCalledWith("project-1", "agent-1", run.run_id, { command: "resume", checkpoint_id: "checkpoint-1" }, { idempotencyKey: expect.stringMatching(/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/) });
    expect(screen.getByRole("button", { name: "Retry safely" })).toBeDisabled();
    await act(async () => finish({ ...run, run_id: "resume-child" }));
    expect(window.location.hash).toBe(runDetailHref({ ...identity, runId: "resume-child" }));
    expect(api.runAgent).not.toHaveBeenCalled();
  });

  it.each(["missing", "approval", "dispatched", "cancelled"])("does not offer Resume for %s state", async (kind) => {
    const { api } = setup();
    const events = kind === "missing" ? [] : [{ ...run.events![0], kind: "checkpoint.created" as const, payload: { checkpoint_id: "checkpoint-1", waiting_kind: kind === "approval" ? "approval" : "execution" } }];
    const detail: AgentRunResponse = { ...run, status: kind === "cancelled" ? "cancelled" : kind === "approval" ? "waiting" : "interrupted", events };
    if (kind === "dispatched") detail.events!.push({ ...run.events![0], event_id: "dispatch-2", sequence: 2, kind: "tool.started" });
    vi.mocked(api.getAgentRun!).mockResolvedValue(detail);
    api.commandAgentRun = vi.fn();
    mount(api, <RunDetail api={api} {...identity} locale="en" />);
    await screen.findByRole("heading", { name: run.run_id });
    expect(screen.queryByRole("button", { name: "Resume from checkpoint" })).not.toBeInTheDocument();
    if (kind === "approval") expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
  });

  it("retries once while pending and navigates to the new pinned Run", async () => {
    const { api } = setup();
    let finish!: (value: AgentRunResponse) => void;
    api.commandAgentRun = vi.fn().mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    mount(api, <RunDetail api={api} {...identity} locale="en" />);
    const button = await screen.findByRole("button", { name: "Retry safely" });
    await userEvent.setup().dblClick(button);
    expect(api.commandAgentRun).toHaveBeenCalledTimes(1);
    expect(button).toBeDisabled();
    expect(api.commandAgentRun).toHaveBeenCalledWith("project-1", "agent-1", run.run_id, { command: "retry" }, { idempotencyKey: expect.stringMatching(/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/) });
    await act(async () => finish({ ...run, run_id: "retry-child" }));
    expect(window.location.hash).toBe(runDetailHref({ ...identity, runId: "retry-child" }));
    expect(api.runAgent).not.toHaveBeenCalled();
    expect(api.getDraft).not.toHaveBeenCalled();
  });

  it("keeps unsafe rejection and original evidence visible and reuses the retry key", async () => {
    const { api } = setup();
    api.commandAgentRun = vi.fn().mockRejectedValue(new Error("retry_effect_unsafe"));
    mount(api, <RunDetail api={api} {...identity} locale="en" />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Retry safely" }));
    expect(await screen.findByText("retry_effect_unsafe")).toBeInTheDocument();
    expect(screen.getByText(/original-evidence/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry safely" }));
    const calls = vi.mocked(api.commandAgentRun).mock.calls;
    expect(calls[0][4]).toEqual(calls[1][4]);
  });

  it("links retry lineage back to the original immutable Run", async () => {
    const { api } = setup();
    vi.mocked(api.getAgentRun!).mockResolvedValue({ ...run, events: [{ ...run.events![0], kind: "run.created", node_id: null, payload: { retry_of_run_id: "parent-run", retry_command_id: "command-1", inputs: { prompt: "original" } } }] });
    mount(api, <RunDetail api={api} {...identity} locale="en" />);
    expect(await screen.findByRole("link", { name: "Original run" })).toHaveAttribute("href", runDetailHref({ ...identity, runId: "parent-run" }));
    expect(screen.getByText("version-original")).toBeInTheDocument();
    expect(screen.getByText(/command-1/)).toBeInTheDocument();
  });

  it("links Agent history and every Monitor attempt to the explicit original run", async () => {
    const { api } = setup();
    const view = mount(api, <AgentRunPage projectId="project-1" agentId="agent-1" />);
    await waitFor(() => expect(document.querySelector(`a[href="${runDetailHref(identity)}"]`)).not.toBeNull());
    expect(screen.queryByText(identity.runId)).not.toBeInTheDocument();
    expect(api.getAgentRun).not.toHaveBeenCalled();
    view.unmount();
    mount(api, <MonitorPage />);
    expect(await screen.findByRole("link", { name: identity.runId })).toHaveAttribute("href", runDetailHref(identity));
    expect(screen.getByRole("link", { name: "newer-run" })).toHaveAttribute("href", runDetailHref({ ...identity, runId: "newer-run" }));
  });

  it.each(["history", "monitor"])("restores the same detail on %s and remount without creating a Run or reading latest/draft", async (entry) => {
    const { api, fetcher } = setup();
    const href = entry === "history" ? runDetailHref(identity) : runMonitorHref(identity);
    window.history.replaceState(null, "", href);
    const page = entry === "history" ? <AgentRunPage projectId="project-1" agentId="agent-1" /> : <MonitorPage />;
    let view = mount(api, page);
    for (let attempt = 0; attempt < 2; attempt++) {
      expect(await screen.findByRole("heading", { name: identity.runId })).toBeInTheDocument();
      expect(screen.getByText("Original failure")).toBeInTheDocument();
      expect(screen.getByText(run.created_at)).toBeInTheDocument();
      expect(screen.getByText(/original-evidence/)).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Studio" })).toHaveAttribute("href", runStudioHref(identity));
      expect(screen.getByRole("link", { name: "Monitor" })).toHaveAttribute("href", runMonitorHref(identity));
      if (attempt === 0) { view.unmount(); view = mount(api, page); }
    }
    expect(api.runAgent).not.toHaveBeenCalled();
    expect(api.getDraft).not.toHaveBeenCalled();
    expect(api.listAgentRuns).not.toHaveBeenCalled();
    expect(fetcher.mock.calls.every(([url]) => url === "/api/v1/projects/project-1/agents/agent-1/runs/historical-1")).toBe(true);
  });

  it("restores the exact immutable Run version on Studio and keeps Run Detail as a separate route", async () => {
    const { api } = setup();
    window.history.replaceState(null, "", runStudioHref(identity));
    mount(api, <StudioPage projectId="project-1" agentId="agent-1" />);
    expect(await screen.findByRole("heading", { name: "Runner" })).toBeInTheDocument();
    expect(screen.getByText(new RegExp(identity.runId))).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("tool")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View Run Detail" })).toHaveAttribute("href", runDetailHref(identity));
    expect(api.getAgentRun).toHaveBeenCalledWith("project-1", "agent-1", identity.runId);
    expect(api.listAgentVersions).toHaveBeenCalledWith("project-1", "agent-1");
    expect(api.getDraft).not.toHaveBeenCalled();

    cleanup();
    window.history.replaceState(null, "", runDetailHref(identity));
    mount(api, <StudioPage projectId="project-1" agentId="agent-1" />);
    expect(await screen.findByRole("heading", { name: identity.runId })).toBeInTheDocument();
    expect(screen.getByText("Original failure")).toBeInTheDocument();
  });

  it("shows missing run errors instead of substituting another Run", async () => {
    const { api } = setup();
    vi.mocked(api.getAgentRun!).mockRejectedValue(new Error("Run not found"));
    window.history.replaceState(null, "", runStudioHref(identity));
    mount(api, <StudioPage projectId="project-1" agentId="agent-1" />);
    expect(await screen.findByText("Run not found")).toBeInTheDocument();
    expect(api.listAgentRuns).not.toHaveBeenCalled();
    expect(api.runAgent).not.toHaveBeenCalled();
  });

  it("ignores a late response when the run query changes on the same Studio", async () => {
    const { api } = setup();
    let finish!: (value: AgentRunResponse) => void;
    vi.mocked(api.getAgentRun!).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    vi.mocked(api.getAgentRun!).mockResolvedValueOnce({ ...run, run_id: "historical-2" });
    window.history.replaceState(null, "", runStudioHref(identity));
    mount(api, <StudioPage projectId="project-1" agentId="agent-1" />);
    await waitFor(() => expect(api.getAgentRun).toHaveBeenCalled());
    await act(async () => { window.location.hash = runStudioHref({ ...identity, runId: "historical-2" }); window.dispatchEvent(new HashChangeEvent("hashchange")); });
    expect(await screen.findByText(/historical-2/)).toBeInTheDocument();
    await act(async () => finish(run));
    expect(screen.getByText(/historical-2/)).toBeInTheDocument();
    expect(screen.queryByText(/historical-1/)).not.toBeInTheDocument();
  });

  it("loads Workflow history by workflow and run identity", async () => {
    const { api } = setup();
    const { agent_id: _, ...summary } = run;
    api.getWorkflowRun = vi.fn().mockResolvedValue({ ...summary, workflow_id: "workflow-1", children: [], waiting: null });
    mount(api, <RunDetail api={api} projectId="project-1" workflowId="workflow-1" runId={run.run_id} locale="en" />);
    expect(await screen.findByRole("heading", { name: run.run_id })).toBeInTheDocument();
    expect(api.getWorkflowRun).toHaveBeenCalledWith("project-1", "workflow-1", run.run_id);
    expect(api.getAgentRun).not.toHaveBeenCalled();
  });

  it("routes a Workflow human-input wait to its typed App instead of offering approval", async () => {
    const { api } = setup();
    const { agent_id: _, ...summary } = run;
    api.getWorkflowRun = vi.fn().mockResolvedValue({ ...summary, workflow_id: "workflow-1", status: "waiting", finished_at: null, result: null, children: [], waiting: { kind: "input", node_id: "collect", prompt: "Which model?", expected_fields: ["model"] } });
    mount(api, <RunDetail api={api} projectId="project-1" workflowId="workflow-1" runId={run.run_id} locale="en" />);
    expect(await screen.findByText("Workflow is waiting for input")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Workflow App" })).toHaveAttribute("href", runDetailHref({ projectId: "project-1", workflowId: "workflow-1", runId: run.run_id }));
  });

  it("rejects a detail response for another identity", async () => {
    const { api } = setup();
    vi.mocked(api.getAgentRun!).mockResolvedValue({ ...run, run_id: "latest-run" });
    mount(api, <RunDetail api={api} {...identity} locale="en" />);
    expect(await screen.findByText("Runtime run identity mismatch")).toBeInTheDocument();
    expect(screen.queryByText("Original failure")).not.toBeInTheDocument();
  });

  it("approves a restored waiting Run and reloads its authoritative detail", async () => {
    const { api } = setup();
    vi.mocked(api.getAgentRun!).mockResolvedValueOnce({ ...run, status: "waiting", error: null, finished_at: null });
    api.commandAgentRun = vi.fn().mockResolvedValue({ ...run, events: undefined });
    mount(api, <RunDetail api={api} {...identity} locale="en" />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Approve" }));
    expect(api.commandAgentRun).toHaveBeenCalledWith("project-1", "agent-1", "historical-1", { command: "approve" });
    expect(await screen.findByText("Original failure")).toBeInTheDocument();
    expect(screen.getByText(/original-evidence/)).toBeInTheDocument();
    expect(api.getAgentRun).toHaveBeenCalledTimes(2);
    expect(api.runAgent).not.toHaveBeenCalled();
  });
});
