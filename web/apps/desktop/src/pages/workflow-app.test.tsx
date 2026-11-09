import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProjectSummaryResponse, WorkflowRunResponse, WorkflowRuntimeReadiness, WorkflowSource, WorkflowVersionSnapshot } from "@veyra/api-contracts";
import { projectRoutePaths } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { ProjectWorkspaceProvider } from "../api/project-workspace";
import type { LocalProjectApi } from "../api/local-client";
import { runDetailHref } from "../features/runs/run-location";
import { WorkflowAppPage } from "./workflow-app";

const projectId = "project-1";
const workflowId = "workflow-1";

function source(overrides: Partial<WorkflowSource> = {}): WorkflowSource {
  return {
    schema_version: "1.0",
    component_type: "Workflow",
    workflow_id: workflowId,
    slug: "gift-review",
    name: "Gift review",
    description: "Review a gift package request.",
    version: "1.0.0",
    inputs: { prompt: { type: "string", description: "What should be reviewed?" } },
    outputs: { result: "string" },
    nodes: [
      { id: "start", component_type: "Start" },
      { id: "analyze", component_type: "AgentCall", agent_ref: "agent-1@agent-version-1" },
      { id: "output", component_type: "Output", output_name: "result" },
    ],
    transitions: [
      { from: "start", port: "next", to: "analyze" },
      { from: "analyze", port: "next", to: "output" },
    ],
    extensions: { veyra: { permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } },
    ui: { positions: { start: { x: 0, y: 0 }, analyze: { x: 220, y: 0 }, output: { x: 440, y: 0 } } },
    lock: {},
    ...overrides,
  };
}

const workflowSource = source();
const project = {
  schema_version: "1.0",
  project_id: projectId,
  root_path: "/tmp/veyra-test-project",
  name: "Gift studio",
  description: "",
  pinned: false,
  pinned_at: null,
  indexed_at: "2026-09-01T00:00:00Z",
  manifest_hash: "sha256:manifest",
  default_agent_id: null,
  agent_count: 1,
  agents: [{ agent_id: "agent-1", name: "Analyzer", slug: "analyzer" }],
  workflows: [{ workflow_id: workflowId, slug: "gift-review", name: "Gift review", description: "Review a gift package request.", source_path: "workflows/gift-review/workflow.vworkflow.yaml", source_file_hash: "sha256:draft" }],
} as unknown as ProjectSummaryResponse;

function version(versionId: string, createdAt: string, committed = true, workflowSourceOverride: WorkflowSource = workflowSource): WorkflowVersionSnapshot {
  return {
    version_id: versionId,
    workflow_id: workflowId,
    source_hash: `sha256:${versionId}`,
    behavior_hash: `sha256:behavior-${versionId}`,
    created_at: createdAt,
    source: workflowSourceOverride,
    committed,
  };
}

function readiness(snapshot: WorkflowVersionSnapshot, ready = true): WorkflowRuntimeReadiness {
  return {
    schema_version: "1.0",
    project_id: projectId,
    workflow_id: workflowId,
    source_kind: "committed",
    version_id: snapshot.version_id,
    source_hash: snapshot.source_hash,
    ready,
    calls: [],
    checks: [
      { id: "agent_calls", ready, code: ready ? "ready" : "agent_unready", detail: ready ? "Pinned Agents are ready." : "Analyzer requires configuration." },
      { id: "permissions", ready: true, code: "ready", detail: "Permissions are ready." },
      { id: "limits", ready: true, code: "ready", detail: "Execution limits are ready." },
    ],
  };
}

function event(runId: string, kind: "node.completed" | "approval.requested" = "node.completed") {
  return {
    schema_version: "1.0" as const,
    event_id: `${runId}:1`,
    run_id: runId,
    sequence: 1,
    kind,
    node_id: kind === "approval.requested" ? "review" : "output",
    payload: (kind === "approval.requested" ? { prompt: "Confirm this step." } : { result: "Looks good" }) as Record<string, string>,
    timestamp: "2026-09-01T10:00:01Z",
  };
}

function run(overrides: Partial<WorkflowRunResponse> = {}): WorkflowRunResponse {
  return {
    schema_version: "1.0",
    run_id: "run-previous",
    project_id: projectId,
    workflow_id: workflowId,
    version_id: "workflow-version-1",
    status: "unverified",
    result: { result: "Looks good" },
    error: null,
    created_at: "2026-09-01T10:00:00Z",
    finished_at: "2026-09-01T10:00:01Z",
    waiting: null,
    children: [{ node_id: "analyze", agent_id: "agent-1", version_id: "agent-version-1", child_run_id: "child-agent-run", status: "unverified" }],
    events: [event("run-previous")],
    ...overrides,
  };
}

function makeApi(overrides: Partial<LocalProjectApi> = {}): LocalProjectApi {
  const newest = version("workflow-version-2", "2026-09-02T10:00:00Z");
  const older = version("workflow-version-1", "2026-09-01T10:00:00Z");
  return {
    listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }),
    getProject: vi.fn().mockResolvedValue(project),
    listWorkflowVersions: vi.fn().mockResolvedValue({ schema_version: "1.0", versions: [older, newest] }),
    listWorkflowRuns: vi.fn().mockResolvedValue({ schema_version: "1.0", runs: [] }),
    workflowRuntimeReadiness: vi.fn().mockImplementation((_projectId: string, _workflowId: string, versionId: string) => {
      const snapshot = versionId === older.version_id ? older : newest;
      return Promise.resolve(readiness(snapshot, versionId !== newest.version_id));
    }),
    runWorkflow: vi.fn().mockResolvedValue(run({ run_id: "run-new", version_id: older.version_id })),
    getWorkflowRun: vi.fn().mockResolvedValue(run()),
    commandWorkflowRun: vi.fn().mockResolvedValue(run({ status: "running", finished_at: null })),
    ...overrides,
  } as unknown as LocalProjectApi;
}

function mount(api: LocalProjectApi, language?: "zh" | "en") {
  if (language) window.localStorage.setItem("veyra.language", language);
  return render(<ThemeProvider><ProjectWorkspaceProvider api={api}><WorkflowAppPage projectId={projectId} workflowId={workflowId} /></ProjectWorkspaceProvider></ThemeProvider>);
}

afterEach(() => {
  cleanup();
  window.localStorage.removeItem("veyra.language");
  window.history.replaceState(null, "", projectRoutePaths.workflowRun(projectId, workflowId));
});

describe("WorkflowAppPage", () => {
  it("shows a Studio commit path when there is no committed Workflow version", async () => {
    const draftOnly = version("draft-run-version", "2026-09-02T10:00:00Z", false);
    const api = makeApi({ listWorkflowVersions: vi.fn().mockResolvedValue({ schema_version: "1.0", versions: [draftOnly] }) });
    mount(api);

    expect(await screen.findByText("Commit a Workflow version first")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Studio to commit" })).toHaveAttribute("href", projectRoutePaths.workflow(projectId, workflowId));
    expect(screen.queryByRole("button", { name: "Run workflow" })).not.toBeInTheDocument();
    expect(api.runWorkflow).not.toHaveBeenCalled();
    expect(api.workflowRuntimeReadiness).not.toHaveBeenCalled();
  });

  it("keeps the task and primary action separate from a folded workflow preview", async () => {
    const newest = version("workflow-version-2", "2026-09-02T10:00:00Z");
    const api = makeApi({
      workflowRuntimeReadiness: vi.fn().mockResolvedValue(readiness(newest, true)),
    });
    const user = userEvent.setup();
    mount(api);

    const runButton = await screen.findByRole("button", { name: "Run workflow" });
    expect(runButton).toBeDisabled();
    expect(screen.getByText("Fill in the required fields to run this Workflow.")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "Task description" }), "Review the label");
    await waitFor(() => expect(runButton).toBeEnabled());
    const previewSummary = screen.getByText("Workflow preview");
    const preview = previewSummary.closest("details");
    expect(preview).not.toHaveAttribute("open");
    expect(screen.getByRole("heading", { name: "Describe the task and run" })).toBeInTheDocument();
    expect(document.querySelector(".workflow-app-task-panel")?.contains(preview)).toBe(false);

    await user.click(previewSummary);
    expect(preview).toHaveAttribute("open");
    const userFlow = screen.getByRole("list", { name: "Workflow preview" });
    expect(userFlow).toHaveTextContent("Analyzer");
    expect(userFlow).not.toHaveTextContent("AgentCall");
    expect(userFlow).not.toHaveTextContent("analyze");
    await user.click(screen.getByText("Technical node details"));
    expect(screen.getByText("analyze", { selector: "code" })).toBeInTheDocument();
    expect(screen.getByText("AgentCall")).toBeInTheDocument();
    await user.click(previewSummary);
    expect(preview).not.toHaveAttribute("open");
  });

  it("localizes common input labels and preserves source keys for custom fields", async () => {
    const newest = version(
      "workflow-version-2",
      "2026-09-02T10:00:00Z",
      true,
      source({
        inputs: {
          image: { type: "image", required: false, description: "Reference image content." },
          message: { type: "string", description: "Optional user message" },
          review_depth: { type: "integer", description: "Number of review passes." },
        },
      }),
    );
    const finished = run({ run_id: "run-localized", version_id: newest.version_id });
    const api = makeApi({
      listWorkflowVersions: vi.fn().mockResolvedValue({ schema_version: "1.0", versions: [newest] }),
      workflowRuntimeReadiness: vi.fn().mockResolvedValue(readiness(newest, true)),
      runWorkflow: vi.fn().mockResolvedValue(finished),
      getWorkflowRun: vi.fn().mockResolvedValue(finished),
    });
    const user = userEvent.setup();
    mount(api, "zh");

    const note = await screen.findByRole("textbox", { name: "补充说明" });
    expect(note).toHaveAttribute("placeholder", "补充说明…");
    expect(screen.getByLabelText("上传图片")).toBeInTheDocument();
    const depth = screen.getByRole("spinbutton", { name: "Review Depth" });
    await user.type(note, "请关注品牌色");
    await user.clear(depth);
    await user.type(depth, "4");
    const runButton = screen.getByRole("button", { name: "运行工作流" });
    await waitFor(() => expect(runButton).toBeEnabled());
    await user.click(runButton);

    await waitFor(() => expect(api.runWorkflow).toHaveBeenCalledWith(projectId, workflowId, {
      inputs: { message: "请关注品牌色", review_depth: 4 },
      source: "committed",
      version_id: newest.version_id,
    }));
  });

  it("keeps long committed instructions in a usage dialog instead of the workspace", async () => {
    const longDescription = `${"Review the package details and return a practical recommendation. ".repeat(5)}`;
    const snapshot = version(
      "workflow-version-2",
      "2026-09-02T10:00:00Z",
      true,
      source({ description: longDescription }),
    );
    const api = makeApi({
      listWorkflowVersions: vi.fn().mockResolvedValue({ schema_version: "1.0", versions: [snapshot] }),
      workflowRuntimeReadiness: vi.fn().mockResolvedValue(readiness(snapshot, true)),
    });
    const user = userEvent.setup();
    mount(api);

    const details = await screen.findByRole("button", { name: "Usage details" });
    expect(screen.queryByText(longDescription.trim())).not.toBeInTheDocument();
    expect(document.querySelector(".agent-app-description")).toBeNull();
    await user.click(details);
    const dialog = screen.getByRole("dialog", { name: "Usage details" });
    expect(dialog).toHaveTextContent(longDescription.trim());
    expect(screen.getByRole("button", { name: "Run workflow" })).toBeInTheDocument();
    fireEvent(dialog, new Event("cancel", { cancelable: true, bubbles: true }));
    expect(screen.queryByRole("dialog", { name: "Usage details" })).not.toBeInTheDocument();
    expect(details).toHaveFocus();
  });

  it("runs only the selected committed version after exact-version preflight", async () => {
    const older = version("workflow-version-1", "2026-09-01T10:00:00Z");
    const newest = version("workflow-version-2", "2026-09-02T10:00:00Z");
    const created = run({ run_id: "run-new", version_id: older.version_id });
    const api = makeApi({
      listWorkflowVersions: vi.fn().mockResolvedValue({ schema_version: "1.0", versions: [older, newest] }),
      workflowRuntimeReadiness: vi.fn().mockImplementation((_projectId: string, _workflowId: string, versionId: string) => Promise.resolve(readiness(versionId === older.version_id ? older : newest, versionId === older.version_id))),
      runWorkflow: vi.fn().mockResolvedValue(created),
      getWorkflowRun: vi.fn().mockResolvedValue(created),
    });
    const user = userEvent.setup();
    mount(api);

    const runButton = await screen.findByRole("button", { name: "Run workflow" });
    expect(screen.getByRole("combobox", { name: "Committed version" })).toHaveValue(newest.version_id);
    expect(runButton).toBeDisabled();
    await user.selectOptions(screen.getByRole("combobox", { name: "Committed version" }), older.version_id);
    await waitFor(() => expect(api.workflowRuntimeReadiness).toHaveBeenCalledWith(projectId, workflowId, older.version_id));
    await user.type(screen.getByRole("textbox", { name: "Task description" }), "Review this package");
    await waitFor(() => expect(runButton).toBeEnabled());
    await user.click(runButton);

    await waitFor(() => expect(api.runWorkflow).toHaveBeenCalledWith(projectId, workflowId, {
      inputs: { prompt: "Review this package" },
      source: "committed",
      version_id: older.version_id,
    }));
    await waitFor(() => expect(window.location.hash).toContain("run_id=run-new"));
  });

  it("reloads a selected run and shows its node state, child Agent, result, and evidence", async () => {
    const previous = run();
    const api = makeApi({
      listWorkflowRuns: vi.fn().mockResolvedValue({ schema_version: "1.0", runs: [previous] }),
      getWorkflowRun: vi.fn().mockResolvedValue(previous),
    });
    window.history.replaceState(null, "", runDetailHref({ projectId, workflowId, runId: previous.run_id }));
    const user = userEvent.setup();
    mount(api);

    const execution = await screen.findByRole("region", { name: "Current run" });
    const progressSummary = within(execution).getByText("Node progress", { selector: "summary span" });
    const foldedProgress = progressSummary.closest("details");
    expect(foldedProgress).not.toHaveAttribute("open");
    expect(screen.getByRole("list", { name: "Node progress" })).not.toBeVisible();
    expect(screen.getByText("Looks good")).toBeInTheDocument();
    await user.click(progressSummary);
    const progress = await screen.findByRole("list", { name: "Node progress" });
    expect(api.getWorkflowRun).toHaveBeenCalledWith(projectId, workflowId, previous.run_id);
    expect(screen.queryByRole("heading", { name: "Run error" })).not.toBeInTheDocument();
    expect(progress).toHaveTextContent("Analyzer");
    expect(screen.queryByRole("list", { name: "Child Agent runs" })).not.toBeInTheDocument();
    expect(screen.getByText("Looks good")).toBeInTheDocument();
    expect(screen.queryByText("Node completed")).not.toBeInTheDocument();
    expect(within(progress).getByRole("link", { name: "Open Agent run" })).toHaveAttribute("href", runDetailHref({ projectId, agentId: "agent-1", runId: "child-agent-run" }));
    await user.click(screen.getByText("Run details"));
    expect(await screen.findByText("Node completed")).toBeInTheDocument();
    expect(screen.getAllByText("Looks good")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Back to Workflow App" })).toHaveAttribute("href", runDetailHref({ projectId, workflowId, runId: previous.run_id }));
    expect(document.querySelector(".workflow-app-run-list")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Runs" }));
    const history = screen.getByRole("list", { name: "Runs" });
    expect(within(history).getByRole("link")).toHaveAttribute("href", runDetailHref({ projectId, workflowId, runId: previous.run_id }));
    await user.click(screen.getByRole("button", { name: "Hide runs" }));
    expect(document.querySelector(".workflow-app-run-list")).toBeNull();
  });

  it("uses the HumanInput node's typed fields for a reply", async () => {
    const inputSource = source({
      nodes: [
        { id: "start", component_type: "Start" },
        { id: "review", component_type: "HumanApproval", prompt: "Choose a model number", inputs: { model: { type: "string", description: "Model number" } } },
        { id: "output", component_type: "Output", output_name: "result" },
      ],
      transitions: [
        { from: "start", port: "next", to: "review" },
        { from: "review", port: "approved", to: "output" },
      ],
    });
    const snapshot = version("workflow-version-1", "2026-09-01T10:00:00Z", true, inputSource);
    const waiting = run({
      status: "waiting",
      result: null,
      finished_at: null,
      waiting: { kind: "input", node_id: "review", prompt: "Choose a model number", request_id: "input-request-1", expected_fields: ["model"] } as WorkflowRunResponse["waiting"],
      children: [],
      events: [event("run-previous", "approval.requested")],
    });
    const resumed = { ...waiting, status: "running" as const, waiting: null, finished_at: null };
    const api = makeApi({
      listWorkflowVersions: vi.fn().mockResolvedValue({ schema_version: "1.0", versions: [snapshot] }),
      getWorkflowRun: vi.fn().mockResolvedValue(waiting),
      commandWorkflowRun: vi.fn().mockResolvedValue(resumed),
    });
    const user = userEvent.setup();
    window.history.replaceState(null, "", runDetailHref({ projectId, workflowId, runId: waiting.run_id }));
    mount(api);

    expect(await screen.findByRole("region", { name: "Provide run input" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "model" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Task description" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run workflow" })).not.toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "model" }), "ABC-1");
    await user.click(screen.getByRole("button", { name: "Submit and continue" }));
    await waitFor(() => expect(api.commandWorkflowRun).toHaveBeenCalledWith(projectId, workflowId, waiting.run_id, { command: "reply", expected_request_id: "input-request-1", inputs: { model: "ABC-1" } }));
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("shows an approval card in the run thread and sends approve", async () => {
    const waiting = run({
      status: "waiting",
      result: null,
      finished_at: null,
      waiting: { kind: "approval", node_id: "review", prompt: "Confirm this step.", request_id: "approval-request-1" },
      children: [],
      events: [event("run-previous", "approval.requested")],
    });
    const api = makeApi({ getWorkflowRun: vi.fn().mockResolvedValue(waiting) });
    const user = userEvent.setup();
    window.history.replaceState(null, "", runDetailHref({ projectId, workflowId, runId: waiting.run_id }));
    mount(api);

    const card = await screen.findByRole("region", { name: "Run approval" });
    expect(card).toHaveTextContent("Confirm this step.");
    expect(screen.queryByRole("textbox", { name: "Task description" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Committed version" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(api.commandWorkflowRun).toHaveBeenCalledWith(projectId, workflowId, waiting.run_id, { command: "approve", expected_request_id: "approval-request-1" }));
  });

  it("extends child budget only for the displayed request and never automatically replays a changed request", async () => {
    const context = { budget: { scope: "run_model_turns", used: 14, limit: 16, remaining: 2 }, required_remaining: 4, max_additional_turns: 32, suggested_additional_turns: 8 };
    const first = run({ status: "waiting", result: null, finished_at: null, waiting: { kind: "budget", node_id: "review", prompt: "More turns needed", request_id: "budget-old", child_run_id: "child-1", context } });
    const second = { ...first, waiting: { ...first.waiting!, request_id: "budget-new", context: { ...context, suggested_additional_turns: 4 } } };
    let current = first;
    const commandWorkflowRun = vi.fn().mockImplementation(async () => { current = second; throw new Error("Request changed"); });
    const api = makeApi({ getWorkflowRun: vi.fn().mockImplementation(async () => current), commandWorkflowRun });
    window.history.replaceState(null, "", runDetailHref({ projectId, workflowId, runId: first.run_id }));
    mount(api);
    const user = userEvent.setup();
    await screen.findByRole("spinbutton", { name: "Additional model turns" });
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(screen.getByRole("spinbutton")).toHaveValue(4));
    expect(commandWorkflowRun).toHaveBeenCalledTimes(1);
    expect(commandWorkflowRun.mock.calls[0].slice(0, 4)).toEqual([projectId, workflowId, first.run_id, { command: "extend_budget", expected_request_id: "budget-old", additional_turns: 8 }]);
    expect(api.runWorkflow).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(commandWorkflowRun.mock.calls[1][3]).toEqual({ command: "extend_budget", expected_request_id: "budget-new", additional_turns: 4 });
    expect(commandWorkflowRun.mock.calls[1][4].idempotencyKey).not.toBe(commandWorkflowRun.mock.calls[0][4].idempotencyKey);
  });

  it("shows child Agent questions and forwards replies without approving effects", async () => {
    const first = run({ status: "waiting", result: null, finished_at: null,
      waiting: { kind: "input", node_id: "review", prompt: "Which column?", agent_id: "child-agent", child_run_id: "child-run", request_id: "question-1", input_schema: { reply: "string" }, context: { choices: ["amount", "total"] } },
      events: [event("run-previous", "approval.requested")],
    });
    const second = { ...first, waiting: { ...first.waiting!, prompt: "Which unit?", request_id: "question-2", context: { choices: ["USD", "CNY"] } } };
    const toolWait = { ...first, waiting: { kind: "agent", node_id: "review", prompt: "Approve exact write", agent_id: "child-agent", child_run_id: "child-run", approval_summary: { action: "Write file", target: "reports/review.md" } } };
    let current = first;
    const api = makeApi({
      getWorkflowRun: vi.fn().mockImplementation(async () => current),
      commandWorkflowRun: vi.fn().mockImplementation(async () => {
        current = current === first ? second : toolWait;
        return current;
      }),
    });
    const user = userEvent.setup();
    window.history.replaceState(null, "", runDetailHref({ projectId, workflowId, runId: first.run_id }));
    mount(api);
    const region = await screen.findByRole("region", { name: "Provide run input" });
    expect(within(region).getByText("Which column?")).toBeInTheDocument();
    await user.click(within(region).getByText("View this turn's options and context"));
    expect(within(region).getByText(/"amount"/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "reply" }), "amount");
    await user.click(screen.getByRole("button", { name: "Submit and continue" }));
    await waitFor(() => expect(api.commandWorkflowRun).toHaveBeenCalledWith(projectId, workflowId, first.run_id, { command: "reply", expected_request_id: "question-1", inputs: { reply: "amount" } }));
    expect(await screen.findByText("Which unit?")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "reply" })).toHaveValue("");
    await user.type(screen.getByRole("textbox", { name: "reply" }), "CNY");
    await user.click(screen.getByRole("button", { name: "Submit and continue" }));
    expect(api.commandWorkflowRun).toHaveBeenLastCalledWith(projectId, workflowId, first.run_id, { command: "reply", expected_request_id: "question-2", inputs: { reply: "CNY" } });
    expect(await screen.findByText("Approve exact write")).toBeInTheDocument();
    expect(screen.getByText("Write file: reports/review.md")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "reply" })).not.toBeInTheDocument();
    expect(api.commandWorkflowRun).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("button", { name: "Approve" })).toBeEnabled();
  });

  it("sends reject for a waiting Workflow approval", async () => {
    const waiting = run({
      status: "waiting",
      result: null,
      finished_at: null,
      waiting: { kind: "approval", node_id: "review", prompt: "Confirm this step.", request_id: "reject-request-1" },
      children: [],
      events: [event("run-previous", "approval.requested")],
    });
    const api = makeApi({ getWorkflowRun: vi.fn().mockResolvedValue(waiting) });
    const user = userEvent.setup();
    window.history.replaceState(null, "", runDetailHref({ projectId, workflowId, runId: waiting.run_id }));
    mount(api);

    await user.click(await screen.findByRole("button", { name: "Reject" }));
    await waitFor(() => expect(api.commandWorkflowRun).toHaveBeenCalledWith(projectId, workflowId, waiting.run_id, { command: "reject", expected_request_id: "reject-request-1" }));
  });

  it("shows the server-bound report preview before approving its write", async () => {
    const waiting = run({ status: "waiting", result: null, finished_at: null,
      waiting: { kind: "approval", node_id: "write", prompt: "Approve report write", request_id: "report-request-1",
        tool_reference: "veyra.tool.filesystem.write@1.0.0",
        approval_summary: { action: "Write file", target: "reports/reconciliation.csv", content_preview: "order,total\nA,30.00", content_digest: "sealed-digest", preview_truncated: true } },
      children: [], events: [],
    });
    const api = makeApi({ getWorkflowRun: vi.fn().mockResolvedValue(waiting) });
    const user = userEvent.setup();
    window.history.replaceState(null, "", runDetailHref({ projectId, workflowId, runId: waiting.run_id }));
    mount(api);
    expect(await screen.findByText("order,total A,30.00")).toBeInTheDocument();
    expect(screen.getByText("Partial content preview")).toBeInTheDocument();
    expect(screen.getByText("Write file: reports/reconciliation.csv")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(api.commandWorkflowRun).toHaveBeenCalledWith(projectId, workflowId, waiting.run_id, { command: "approve", expected_request_id: "report-request-1" }));
  });

  it("refreshes a changed approval after failure without replaying it with the new token", async () => {
    const first = run({ status: "waiting", result: null, finished_at: null,
      waiting: { kind: "approval", node_id: "review", prompt: "First approval", request_id: "request-old" },
    });
    const second = { ...first, waiting: { ...first.waiting!, prompt: "Second approval", request_id: "request-new" } };
    let current = first;
    const commandWorkflowRun = vi.fn().mockImplementation(async () => {
      if (current === first) { current = second; throw new Error("Request changed"); }
      return current;
    });
    const api = makeApi({ getWorkflowRun: vi.fn().mockImplementation(async () => current), commandWorkflowRun });
    window.history.replaceState(null, "", runDetailHref({ projectId, workflowId, runId: first.run_id }));
    mount(api);
    const user = userEvent.setup();
    await screen.findByText("First approval");
    await user.click(screen.getByRole("button", { name: "Approve" }));
    expect(await screen.findByText("Second approval")).toBeInTheDocument();
    expect(commandWorkflowRun).toHaveBeenCalledTimes(1);
    expect(commandWorkflowRun).toHaveBeenLastCalledWith(projectId, workflowId, first.run_id, { command: "approve", expected_request_id: "request-old" });
    await user.click(screen.getByRole("button", { name: "Reject" }));
    expect(commandWorkflowRun).toHaveBeenLastCalledWith(projectId, workflowId, first.run_id, { command: "reject", expected_request_id: "request-new" });
  });

  it("does not send an approval without a displayed request identity and only refreshes", async () => {
    const missing = run({ status: "waiting", result: null, finished_at: null, waiting: { kind: "approval", node_id: "review", prompt: "Legacy approval" } });
    const refreshed = { ...missing, waiting: { ...missing.waiting!, prompt: "Current approval", request_id: "request-current" } };
    let current = missing;
    const getWorkflowRun = vi.fn().mockImplementation(async () => current);
    const commandWorkflowRun = vi.fn().mockResolvedValue(refreshed);
    const api = makeApi({ getWorkflowRun, commandWorkflowRun });
    window.history.replaceState(null, "", runDetailHref({ projectId, workflowId, runId: missing.run_id }));
    mount(api);
    await screen.findByText("Legacy approval");
    current = refreshed;
    await userEvent.setup().click(screen.getByRole("button", { name: "Approve" }));
    expect(await screen.findByText("Current approval")).toBeInTheDocument();
    expect(commandWorkflowRun).not.toHaveBeenCalled();
    expect(getWorkflowRun.mock.calls.length).toBeGreaterThan(1);
  });

  it("sends stop for a running Workflow", async () => {
    const active = run({ status: "running", result: null, finished_at: null });
    const api = makeApi({ getWorkflowRun: vi.fn().mockResolvedValue(active) });
    const user = userEvent.setup();
    window.history.replaceState(null, "", runDetailHref({ projectId, workflowId, runId: active.run_id }));
    mount(api);

    const stop = await screen.findByRole("button", { name: "Stop workflow" });
    expect(screen.queryByRole("textbox", { name: "Task description" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run workflow" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Committed version" })).toBeDisabled();
    const header = document.querySelector(".workflow-app-header") as HTMLElement;
    expect(within(header).getByText("Running")).toBeInTheDocument();
    expect(within(header).queryByText("Ready")).not.toBeInTheDocument();
    await user.click(stop);
    await waitFor(() => expect(api.commandWorkflowRun).toHaveBeenCalledWith(projectId, workflowId, active.run_id, { command: "stop" }));
  });

  it("retries a failed run with the same inputs and pinned version", async () => {
    const older = version("workflow-version-1", "2026-09-01T10:00:00Z");
    const failed = run({ run_id: "run-failed", version_id: older.version_id, status: "failed", result: null, error: { code: "workflow_agent_failed", message: "Agent failed." } });
    const api = makeApi({
      listWorkflowVersions: vi.fn().mockResolvedValue({ schema_version: "1.0", versions: [older] }),
      workflowRuntimeReadiness: vi.fn().mockResolvedValue(readiness(older, true)),
      runWorkflow: vi.fn().mockResolvedValueOnce(failed).mockResolvedValueOnce(run({ run_id: "run-retry", version_id: older.version_id, status: "running", result: null, finished_at: null })),
      getWorkflowRun: vi.fn().mockResolvedValue(failed),
    });
    const user = userEvent.setup();
    mount(api);

    await user.type(await screen.findByRole("textbox", { name: "Task description" }), "Retry this package");
    const runButton = screen.getByRole("button", { name: "Run workflow" });
    await waitFor(() => expect(runButton).toBeEnabled());
    await user.click(runButton);
    const retryButton = await screen.findByRole("button", { name: "Retry with the same inputs" });
    await user.click(retryButton);
    await waitFor(() => expect(api.runWorkflow).toHaveBeenNthCalledWith(2, projectId, workflowId, {
      inputs: { prompt: "Retry this package" },
      source: "committed",
      version_id: older.version_id,
    }));
  });

  it("starts a clean new run from a finished run", async () => {
    const newest = version("workflow-version-2", "2026-09-02T10:00:00Z");
    const finished = run({ run_id: "run-finished", version_id: newest.version_id });
    const api = makeApi({
      workflowRuntimeReadiness: vi.fn().mockResolvedValue(readiness(newest, true)),
      runWorkflow: vi.fn().mockResolvedValue(finished),
      getWorkflowRun: vi.fn().mockResolvedValue(finished),
    });
    const user = userEvent.setup();
    mount(api);

    await user.type(await screen.findByRole("textbox", { name: "Task description" }), "First task");
    const runButton = screen.getByRole("button", { name: "Run workflow" });
    await waitFor(() => expect(runButton).toBeEnabled());
    await user.click(runButton);
    await waitFor(() => expect(window.location.hash).toContain("run_id=run-finished"));
    expect(screen.queryByRole("textbox", { name: "Task description" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "New run" }));

    await waitFor(() => expect(window.location.hash).not.toContain("run_id="));
    expect(screen.getByRole("textbox", { name: "Task description" })).toHaveValue("");
    expect(screen.queryByRole("region", { name: "Current run" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run workflow" })).toBeInTheDocument();
  });

  it("shows only the execution state while a selected historical run is loading", async () => {
    const snapshot = version("workflow-version-1", "2026-09-01T10:00:00Z");
    const active = run({ status: "running", result: null, finished_at: null });
    let resolveRun!: (value: WorkflowRunResponse) => void;
    const pending = new Promise<WorkflowRunResponse>((resolve) => { resolveRun = resolve; });
    const api = makeApi({
      listWorkflowVersions: vi.fn().mockResolvedValue({ schema_version: "1.0", versions: [snapshot] }),
      workflowRuntimeReadiness: vi.fn().mockResolvedValue(readiness(snapshot, true)),
      getWorkflowRun: vi.fn().mockReturnValue(pending),
    });
    window.history.replaceState(null, "", runDetailHref({ projectId, workflowId, runId: active.run_id }));
    mount(api);

    await screen.findByText("Loading run details…");
    expect(screen.queryByRole("textbox", { name: "Task description" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run workflow" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Committed version" })).toBeDisabled();
    expect(api.runWorkflow).not.toHaveBeenCalled();

    await act(async () => { resolveRun(active); });
    await screen.findByRole("button", { name: "Stop workflow" });
    expect(screen.queryByRole("textbox", { name: "Task description" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Committed version" })).toBeDisabled();
  });

  it("keeps the submitted task and shared ArtifactRef in one execution summary", async () => {
    const snapshot = version("workflow-version-2", "2026-09-02T10:00:00Z", true, source({ inputs: { image: "image", prompt: "string" } }));
    const image = { kind: "artifact" as const, artifact_id: "image-1", media_type: "image/png", filename: "package.png" };
    const active = run({ run_id: "run-image", version_id: snapshot.version_id, status: "running", result: null, finished_at: null, events: [] });
    const api = makeApi({
      listWorkflowVersions: vi.fn().mockResolvedValue({ schema_version: "1.0", versions: [snapshot] }),
      workflowRuntimeReadiness: vi.fn().mockResolvedValue(readiness(snapshot, true)),
      uploadArtifact: vi.fn().mockResolvedValue({ ...image, project_id: projectId, sha256: "a".repeat(64), size_bytes: 3, storage_ref: "sha256/aa", source_kind: "upload", created_at: "2026-09-01T10:00:00Z" }),
      runWorkflow: vi.fn().mockResolvedValue(active),
      getWorkflowRun: vi.fn().mockResolvedValue(active),
    });
    const user = userEvent.setup();
    mount(api);

    const task = await screen.findByRole("textbox", { name: "Task description" });
    const runButton = screen.getByRole("button", { name: "Run workflow" });
    await user.type(task, "Design a Christmas package");
    expect(runButton).toBeDisabled();
    const file = new File([new Uint8Array([1, 2, 3])], "package.png", { type: "image/png" });
    await user.upload(screen.getByLabelText("Upload an image"), file);
    await waitFor(() => expect(runButton).toBeEnabled());
    await user.click(runButton);

    await waitFor(() => expect(api.runWorkflow).toHaveBeenCalledWith(projectId, workflowId, {
      inputs: { image, prompt: "Design a Christmas package" }, source: "committed", version_id: snapshot.version_id,
    }));
    const execution = await screen.findByRole("region", { name: "Current run" });
    expect(within(execution).getByText("Design a Christmas package")).toBeInTheDocument();
    expect(within(execution).getByText("package.png")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Task description" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Upload an image")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Committed version" })).toBeDisabled();
    expect(api.uploadArtifact).toHaveBeenCalledWith(projectId, file);
    expect(api.runWorkflow).toHaveBeenCalledTimes(1);
  });

  it.each([0, false])("shows a %s result once and retains it when evidence is opened", async (result) => {
    const finished = run({ result: { result }, children: [], events: [] });
    const api = makeApi({ getWorkflowRun: vi.fn().mockResolvedValue(finished) });
    const user = userEvent.setup();
    window.history.replaceState(null, "", runDetailHref({ projectId, workflowId, runId: finished.run_id }));
    mount(api);

    await screen.findByRole("region", { name: "Current run" });
    const resultPanel = document.querySelector(".workflow-app-result") as HTMLElement;
    expect(resultPanel).not.toBeNull();
    expect(within(resultPanel).getByText(String(result))).toBeInTheDocument();
    expect(document.querySelectorAll(".runtime-output-scalar")).toHaveLength(1);
    await user.click(screen.getByText("Run details"));
    expect(await screen.findByRole("heading", { name: "Run detail" })).toBeInTheDocument();
    expect(document.querySelectorAll(".runtime-output-scalar")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "New run" })).toBeEnabled();
    expect(screen.queryByRole("textbox", { name: "Task description" })).not.toBeInTheDocument();
  });

  it("keeps running disabled when preflight reports a different committed source hash", async () => {
    const snapshot = version("workflow-version-2", "2026-09-02T10:00:00Z");
    const api = makeApi({ workflowRuntimeReadiness: vi.fn().mockResolvedValue({ ...readiness(snapshot, true), source_hash: "sha256:another-source" }) });
    const user = userEvent.setup();
    mount(api);

    await user.type(await screen.findByRole("textbox", { name: "Task description" }), "Review this package");
    expect(await screen.findByText("Preflight did not match the selected version, so running is disabled.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run workflow" })).toBeDisabled();
    expect(api.runWorkflow).not.toHaveBeenCalled();
  });

  it("opens a fresh task from historical failure without inventing retry inputs", async () => {
    const snapshot = version("workflow-version-1", "2026-09-01T10:00:00Z");
    const failed = run({ status: "failed", result: null, error: { code: "workflow_agent_failed", message: "Agent failed." } });
    const api = makeApi({
      listWorkflowVersions: vi.fn().mockResolvedValue({ schema_version: "1.0", versions: [snapshot] }),
      workflowRuntimeReadiness: vi.fn().mockResolvedValue(readiness(snapshot, true)),
      getWorkflowRun: vi.fn().mockResolvedValue(failed),
    });
    const user = userEvent.setup();
    window.history.replaceState(null, "", runDetailHref({ projectId, workflowId, runId: failed.run_id }));
    mount(api);

    expect(await screen.findByText("Inputs are not retained for this historical run. Fill in the task and run it again.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry with the same inputs" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Task description" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "New run" }));
    await waitFor(() => expect(window.location.hash).not.toContain("run_id="));
    expect(screen.getByRole("textbox", { name: "Task description" })).toHaveValue("");
    expect(screen.getByRole("button", { name: "Run workflow" })).toBeDisabled();
    expect(api.runWorkflow).not.toHaveBeenCalled();
  });

  it("ignores a previous version's late readiness after selecting another committed version", async () => {
    const newest = version("workflow-version-2", "2026-09-02T10:00:00Z");
    const older = version("workflow-version-1", "2026-09-01T10:00:00Z");
    let resolveNewest!: (value: WorkflowRuntimeReadiness) => void;
    const newestPending = new Promise<WorkflowRuntimeReadiness>((resolve) => { resolveNewest = resolve; });
    const api = makeApi({
      workflowRuntimeReadiness: vi.fn().mockImplementation((_project: string, _workflow: string, versionId: string) => versionId === newest.version_id ? newestPending : Promise.resolve(readiness(older, true))),
      runWorkflow: vi.fn().mockResolvedValue(run({ run_id: "run-older", version_id: older.version_id })),
      getWorkflowRun: vi.fn().mockResolvedValue(run({ run_id: "run-older", version_id: older.version_id })),
    });
    const user = userEvent.setup();
    mount(api);

    const versionPicker = await screen.findByRole("combobox", { name: "Committed version" });
    await user.selectOptions(versionPicker, older.version_id);
    await user.type(screen.getByRole("textbox", { name: "Task description" }), "Use the selected version");
    const runButton = screen.getByRole("button", { name: "Run workflow" });
    await waitFor(() => expect(runButton).toBeEnabled());
    await act(async () => { resolveNewest(readiness(newest, false)); });
    expect(versionPicker).toHaveValue(older.version_id);
    expect(runButton).toBeEnabled();
    await user.click(runButton);
    await waitFor(() => expect(api.runWorkflow).toHaveBeenCalledWith(projectId, workflowId, {
      inputs: { prompt: "Use the selected version" }, source: "committed", version_id: older.version_id,
    }));
  });

  it("preserves the prepared task when starting fails before a Run is created", async () => {
    const snapshot = version("workflow-version-2", "2026-09-02T10:00:00Z");
    const api = makeApi({
      workflowRuntimeReadiness: vi.fn().mockResolvedValue(readiness(snapshot, true)),
      runWorkflow: vi.fn().mockRejectedValue(new Error("The local Runtime is unavailable.")),
    });
    const user = userEvent.setup();
    mount(api);

    await user.type(await screen.findByRole("textbox", { name: "Task description" }), "Keep my request");
    const runButton = screen.getByRole("button", { name: "Run workflow" });
    await waitFor(() => expect(runButton).toBeEnabled());
    await user.click(runButton);
    expect(await screen.findByText("The local Runtime is unavailable.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Task description" })).toHaveValue("Keep my request");
    expect(screen.getByRole("button", { name: "Run workflow" })).toBeEnabled();
    expect(screen.queryByRole("region", { name: "Current run" })).not.toBeInTheDocument();
    expect(window.location.hash).not.toContain("run_id=");
  });

  it("restores the preparation form after a historical run cannot be loaded", async () => {
    const snapshot = version("workflow-version-2", "2026-09-02T10:00:00Z");
    const api = makeApi({
      workflowRuntimeReadiness: vi.fn().mockResolvedValue(readiness(snapshot, true)),
      getWorkflowRun: vi.fn().mockRejectedValue(new Error("Historical run could not be loaded.")),
    });
    const user = userEvent.setup();
    window.history.replaceState(null, "", runDetailHref({ projectId, workflowId, runId: "unavailable-run" }));
    mount(api);

    expect(await screen.findByText("Historical run could not be loaded.")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Task description" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "New run" }));
    await waitFor(() => expect(window.location.hash).not.toContain("run_id="));
    expect(await screen.findByRole("textbox", { name: "Task description" })).toHaveValue("");
    expect(screen.getByRole("combobox", { name: "Committed version" })).toBeEnabled();
    expect(screen.queryByText("Historical run could not be loaded.")).not.toBeInTheDocument();
    expect(api.runWorkflow).not.toHaveBeenCalled();
  });

  it("shows an unavailable historical version's own identity without another version's instructions", async () => {
    const latest = version("workflow-version-2", "2026-09-02T10:00:00Z", true, source({ description: "These instructions belong to a newer version." }));
    const historical = run({ version_id: "removed-version-1" });
    const api = makeApi({
      listWorkflowVersions: vi.fn().mockResolvedValue({ schema_version: "1.0", versions: [latest] }),
      workflowRuntimeReadiness: vi.fn().mockResolvedValue(readiness(latest, true)),
      getWorkflowRun: vi.fn().mockResolvedValue(historical),
    });
    window.history.replaceState(null, "", runDetailHref({ projectId, workflowId, runId: historical.run_id }));
    mount(api);

    await screen.findByRole("region", { name: "Current run" });
    const header = document.querySelector(".workflow-app-header") as HTMLElement;
    const versionLabel = within(header).getByLabelText("Committed version");
    expect(versionLabel).toHaveTextContent(historical.version_id.slice(0, 8));
    expect(versionLabel).toHaveTextContent(/definition unavailable/i);
    expect(within(header).queryByRole("combobox", { name: "Committed version" })).not.toBeInTheDocument();
    expect(within(header).queryByRole("button", { name: "Usage details" })).not.toBeInTheDocument();
    expect(screen.queryByText("These instructions belong to a newer version.")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Task description" })).not.toBeInTheDocument();
    expect(api.runWorkflow).not.toHaveBeenCalled();
  });

  it("retains both submitted images when their friendly field names match", async () => {
    const snapshot = version("workflow-version-2", "2026-09-02T10:00:00Z", true, source({ inputs: { image: "image", photo: "image", prompt: "string" } }));
    const front = { kind: "artifact" as const, artifact_id: "front-image", media_type: "image/png", filename: "front.png" };
    const back = { kind: "artifact" as const, artifact_id: "back-image", media_type: "image/png", filename: "back.png" };
    const active = run({ run_id: "run-two-images", version_id: snapshot.version_id, status: "running", result: null, finished_at: null, events: [] });
    const artifactRecord = (image: typeof front) => ({ ...image, project_id: projectId, sha256: "a".repeat(64), size_bytes: 1, storage_ref: "sha256/aa", source_kind: "upload", created_at: "2026-09-01T10:00:00Z" });
    const api = makeApi({
      listWorkflowVersions: vi.fn().mockResolvedValue({ schema_version: "1.0", versions: [snapshot] }),
      workflowRuntimeReadiness: vi.fn().mockResolvedValue(readiness(snapshot, true)),
      uploadArtifact: vi.fn().mockResolvedValueOnce(artifactRecord(front)).mockResolvedValueOnce(artifactRecord(back)),
      runWorkflow: vi.fn().mockResolvedValue(active),
      getWorkflowRun: vi.fn().mockResolvedValue(active),
    });
    const user = userEvent.setup();
    mount(api);

    await user.type(await screen.findByRole("textbox", { name: "Task description" }), "Use both reference images");
    await user.upload(screen.getByLabelText("Upload an image"), new File(["f"], "front.png", { type: "image/png" }));
    await user.upload(screen.getByLabelText("Upload an image (2)"), new File(["b"], "back.png", { type: "image/png" }));
    const startButton = screen.getByRole("button", { name: "Run workflow" });
    await waitFor(() => expect(startButton).toBeEnabled());
    await user.click(startButton);

    await waitFor(() => expect(api.runWorkflow).toHaveBeenCalledWith(projectId, workflowId, {
      inputs: { image: front, photo: back, prompt: "Use both reference images" }, source: "committed", version_id: snapshot.version_id,
    }));
    const execution = await screen.findByRole("region", { name: "Current run" });
    expect(within(execution).getByText("front.png")).toBeInTheDocument();
    expect(within(execution).getByText("back.png")).toBeInTheDocument();
    expect(within(execution).getByText("Upload an image")).toBeInTheDocument();
    expect(within(execution).getByText("Upload an image (2)")).toBeInTheDocument();
  });

  it("announces active run status without announcing every clock update", async () => {
    const active = run({ status: "running", result: null, finished_at: null });
    const api = makeApi({ getWorkflowRun: vi.fn().mockResolvedValue(active) });
    window.history.replaceState(null, "", runDetailHref({ projectId, workflowId, runId: active.run_id }));
    mount(api);

    const heading = await screen.findByRole("heading", { name: "Working on your task" });
    const liveStatus = heading.closest('[aria-live="polite"]');
    expect(liveStatus).not.toBeNull();
    const clock = document.querySelector(".workflow-run-clock");
    expect(clock).not.toBeNull();
    expect(liveStatus!.contains(clock)).toBe(false);
    expect(clock!.closest("[aria-live]")).toBeNull();
    const progress = screen.getByRole("list", { name: "Node progress" });
    expect(progress.closest("details")).toBeNull();
  });
});
