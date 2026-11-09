import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentSource, AgentVersionSnapshot, ProjectSummaryResponse, WorkItem } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { LocalApiClientError, type LocalProjectApi } from "../api/local-client";
import { ProjectWorkspaceProvider } from "../api/project-workspace";
import { runDetailHref } from "../features/runs/run-location";
import { MonitorPage } from "./monitor";

const createdAt = "2026-10-15T01:00:00Z";
const source: AgentSource = { schema_version: "1.0", agentspec_version: "26.1", component_type: "Flow", agent_id: "agent-1", slug: "worker", name: "Worker", description: "", inputs: {}, outputs: { answer: "string" }, nodes: [], transitions: [], extensions: { veyra: { runtime_profile: "guarded-local", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: true, checks: [] } } }, ui: { positions: {} }, lock: {} };
const version: AgentVersionSnapshot = { version_id: "version-1", agent_id: "agent-1", source_hash: "a".repeat(64), behavior_hash: "b".repeat(64), created_at: createdAt, committed: true, source };
const project = { schema_version: "1.0", project_id: "project-1", name: "Project", agents: [{ agent_id: "agent-1", name: "Worker", slug: "worker" }, { agent_id: "agent-2", name: "Second worker", slug: "second" }] } as ProjectSummaryResponse;
const initialItem: WorkItem = { schema_version: "1.0", work_item_id: "work-1", project_id: "project-1", agent_id: "agent-1", agent_version_id: version.version_id, agent_source_hash: version.source_hash, binding_required: false, title: "Research work", description: "", inputs: {}, status: "ready", run_id: null, attempt_number: 0, depends_on: [], attempts: [], created_at: createdAt, updated_at: createdAt };

function attempted(item: WorkItem, runId: string, operation: "start" | "retry"): WorkItem {
  const number = item.attempt_number! + 1;
  return { ...item, attempt_number: number, run_id: runId, status: "running", attempts: [...(item.attempts ?? []), { attempt_id: `attempt-${number}`, attempt_number: number, operation, previous_run_id: operation === "retry" ? item.run_id : null, run_id: runId, status: "running", failure_class: null, claimed_at: createdAt, started_at: createdAt, finished_at: null, created_at: createdAt }] };
}

function setup(item: WorkItem | null = initialItem) {
  let current = item;
  const api = {
    listProjects: vi.fn().mockResolvedValue({ projects: [project] }),
    listAgentVersions: vi.fn().mockImplementation(async (_projectId: string, agentId: string) => ({ schema_version: "1.0", versions: agentId === "agent-1" ? [version] : [{ ...version, agent_id: "agent-2", version_id: "second-version", source: { ...source, agent_id: "agent-2" } }] })),
    orchestratorStatus: vi.fn().mockResolvedValue({ schema_version: "1.0", execution_plane: "local", cloud_execution: false, active: [], counts: { backlog: 0, ready: 1, running: 0, waiting: 0, cancelling: 0, done: 0, failed: 0, cancelled: 0 }, limits: { global_concurrency: 4, per_project_concurrency: 2 }, stale_count: 0 }),
    listWorkItems: vi.fn().mockImplementation(async () => ({ schema_version: "1.0", project_id: "project-1", execution_plane: "local", work_items: current ? [current] : [] })),
    createWorkItem: vi.fn().mockImplementation(async (_projectId: string, input: { agent_id: string; agent_version_id: string; title: string }) => ({ ...initialItem, ...input })),
    updateWorkItem: vi.fn().mockImplementation(async (_id: string, input: { agent_version_id: string }) => { current = { ...current!, ...input, agent_source_hash: version.source_hash, binding_required: false }; return current; }),
    dispatchWorkItem: vi.fn().mockImplementation(async () => { current = attempted(current!, "run-1", "start"); return current; }),
    retryWorkItem: vi.fn().mockImplementation(async () => { current = attempted(current!, "retry-run", "retry"); return current; }),
    cancelWorkItem: vi.fn(), recoverWorkItem: vi.fn(), runAgent: vi.fn(), getDraft: vi.fn(), commitAgent: vi.fn(),
  } as unknown as LocalProjectApi;
  render(<ThemeProvider storageKey="monitor-test"><ProjectWorkspaceProvider api={api}><MonitorPage /></ProjectWorkspaceProvider></ThemeProvider>);
  return { api, setItem: (next: WorkItem) => { current = next; } };
}

const uuidV7 = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
afterEach(() => { cleanup(); window.history.replaceState(null, "", "#/projects"); vi.restoreAllMocks(); });

describe("Monitor pinned execution", () => {
  it("keeps cancelling work visible without dispatch, retry or repeated cancellation", async () => {
    const item: WorkItem = { ...attempted(initialItem, "stopping-run", "start"), status: "cancelling" };
    item.attempts![0] = { ...item.attempts![0], status: "cancelling", failure_class: "runtime", error_code: "runtime_stop_pending" };
    const { api } = setup(item);
    vi.mocked(api.orchestratorStatus!).mockResolvedValue({ schema_version: "1.0", execution_plane: "local", cloud_execution: false, active: [item], counts: { backlog: 0, ready: 0, running: 0, waiting: 0, cancelling: 1, done: 0, failed: 0, cancelled: 0 }, stale_count: 0, limits: { global_concurrency: 4, per_project_concurrency: 2 } });
    const button = await screen.findByRole("button", { name: "Cancelling" });
    expect(button).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Dispatch" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(screen.getByText(/cancelling 1/)).toBeInTheDocument();
    expect(screen.getByText("agent-1 · Cancelling · attempt 1 · runtime_stop_pending")).toBeInTheDocument();
    expect(screen.queryByText(/· runtime$/)).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "stopping-run" })[0]).toHaveAttribute("href", runDetailHref({ projectId: "project-1", agentId: "agent-1", runId: "stopping-run" }));
    await userEvent.setup().click(button);
    expect(api.cancelWorkItem).not.toHaveBeenCalled();
    expect(api.dispatchWorkItem).not.toHaveBeenCalled();
    expect(api.retryWorkItem).not.toHaveBeenCalled();
  });

  it("requires an explicit committed version choice and never lists Draft or commits it", async () => {
    const { api } = setup(null);
    vi.mocked(api.listAgentVersions!).mockResolvedValue({ schema_version: "1.0", versions: [{ ...version, version_id: "draft-version", committed: false }, version, { ...version, version_id: "version-2", created_at: "2026-10-15T02:00:00Z" }] });
    const user = userEvent.setup();
    const select = await screen.findByRole("combobox", { name: "Pinned version" });
    await screen.findByRole("option", { name: "v2 · version-2" });
    expect(within(select).queryByText(/draft-version/)).not.toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "Title" }), "Pinned task");
    expect(screen.getByRole("button", { name: "Create WorkItem" })).toBeDisabled();
    await user.selectOptions(select, "version-2");
    await user.click(screen.getByRole("button", { name: "Create WorkItem" }));
    expect(api.createWorkItem).toHaveBeenCalledWith("project-1", { title: "Pinned task", agent_id: "agent-1", agent_version_id: "version-2", description: "", depends_on: [] });
    expect(api.getDraft).not.toHaveBeenCalled();
    expect((api as unknown as { commitAgent: ReturnType<typeof vi.fn> }).commitAgent).not.toHaveBeenCalled();
  });

  it("clears version selection across Agent changes and ignores a late previous-Agent response", async () => {
    const { api } = setup(null);
    let finish!: (value: { schema_version: "1.0"; versions: AgentVersionSnapshot[] }) => void;
    vi.mocked(api.listAgentVersions!).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    const user = userEvent.setup();
    await waitFor(() => expect(api.listAgentVersions).toHaveBeenCalledWith("project-1", "agent-1"));
    await user.selectOptions(screen.getByRole("combobox", { name: "Agent" }), "agent-2");
    await screen.findByRole("option", { name: "v1 · second-version" });
    await act(async () => finish({ schema_version: "1.0", versions: [version] }));
    expect(screen.queryByRole("option", { name: "v1 · version-1" })).not.toBeInTheDocument();
    const select = screen.getByRole("combobox", { name: "Pinned version" });
    await user.selectOptions(select, "second-version");
    await user.selectOptions(screen.getByRole("combobox", { name: "Agent" }), "agent-1");
    await screen.findByRole("option", { name: "v1 · version-1" });
    expect(select).toHaveValue("");
  });

  it("does not create when an Agent only has Draft versions", async () => {
    const { api } = setup(null);
    vi.mocked(api.listAgentVersions!).mockResolvedValue({ schema_version: "1.0", versions: [{ ...version, committed: false }] });
    await screen.findByRole("option", { name: "No committed versions" });
    await userEvent.setup().type(screen.getByRole("textbox", { name: "Title" }), "No publication");
    expect(screen.getByRole("button", { name: "Create WorkItem" })).toBeDisabled();
    expect(api.createWorkItem).not.toHaveBeenCalled();
  });

  it("rejects a committed-version response for a different Agent", async () => {
    const { api } = setup(null);
    vi.mocked(api.listAgentVersions!).mockResolvedValue({ schema_version: "1.0", versions: [{ ...version, agent_id: "other-agent" }] });
    expect(await screen.findByRole("alert")).toHaveTextContent("Agent version identity mismatch");
    expect(screen.getByRole("button", { name: "Create WorkItem" })).toBeDisabled();
  });

  it("explicitly binds only an unattempted legacy item without dispatching it", async () => {
    const legacy = { ...initialItem, agent_version_id: null, agent_source_hash: null, binding_required: true };
    const { api } = setup(legacy);
    const user = userEvent.setup();
    await screen.findByText(/Legacy work item has no pinned version/);
    expect(screen.getByRole("button", { name: "Dispatch" })).toBeDisabled();
    const select = screen.getByRole("combobox", { name: "Bind committed version" });
    await waitFor(() => expect(select).toBeEnabled());
    await user.selectOptions(select, "version-1");
    await user.click(screen.getByRole("button", { name: "Bind version" }));
    expect(api.updateWorkItem).toHaveBeenCalledWith("work-1", { agent_version_id: "version-1" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Dispatch" })).toBeEnabled());
    expect(api.dispatchWorkItem).not.toHaveBeenCalled();
    expect(screen.getByText(version.source_hash, { selector: "code" })).toBeInTheDocument();
  });

  it("keeps attempted legacy history read-only and retains original Run links", async () => {
    const item: WorkItem = { ...initialItem, agent_version_id: null, agent_source_hash: null, binding_required: true, status: "failed", attempt_number: 2, run_id: "latest-run", attempts: [{ attempt_id: "attempt-2", attempt_number: 2, operation: "retry", previous_run_id: "original-run", run_id: "latest-run", status: "failed", failure_class: "provider", claimed_at: createdAt, started_at: createdAt, finished_at: createdAt, created_at: createdAt }] };
    const { api } = setup(item);
    expect(await screen.findByRole("button", { name: "Retry" })).toBeDisabled();
    expect(screen.queryByRole("combobox", { name: "Bind committed version" })).not.toBeInTheDocument();
    expect(screen.getByText(/Rebinding, dispatch and retry are disabled/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Previous run: original-run" })).toHaveAttribute("href", runDetailHref({ projectId: "project-1", agentId: "agent-1", runId: "original-run" }));
    expect(api.updateWorkItem).not.toHaveBeenCalled();
  });

  it("dispatches the displayed attempt once under a synchronous double-click lock", async () => {
    const { api } = setup();
    let finish!: (value: WorkItem) => void;
    vi.mocked(api.dispatchWorkItem!).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const button = await screen.findByRole("button", { name: "Dispatch" });
    await userEvent.setup().dblClick(button);
    expect(api.dispatchWorkItem).toHaveBeenCalledTimes(1);
    expect(api.dispatchWorkItem).toHaveBeenCalledWith("work-1", { idempotencyKey: expect.stringMatching(uuidV7), expectedAttemptNumber: 0 });
    expect(button).toBeDisabled();
    await act(async () => finish(attempted(initialItem, "run-1", "start")));
    expect(api.runAgent).not.toHaveBeenCalled();
    expect(api.getDraft).not.toHaveBeenCalled();
  });

  it("does not dispatch without a saved current attempt number and refreshes instead", async () => {
    const { api } = setup({ ...initialItem, attempt_number: undefined });
    await userEvent.setup().click(await screen.findByRole("button", { name: "Dispatch" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Current attempt number is missing");
    expect(api.dispatchWorkItem).not.toHaveBeenCalled();
    expect(vi.mocked(api.listWorkItems!).mock.calls.length).toBeGreaterThan(1);
  });

  it("refreshes an unknown result without resubmitting and reuses the same intent key on manual retry", async () => {
    const { api } = setup();
    vi.mocked(api.dispatchWorkItem!).mockRejectedValue(new Error("Network response lost"));
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Dispatch" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Network response lost");
    await waitFor(() => expect(screen.getByRole("button", { name: "Dispatch" })).toBeEnabled());
    expect(api.dispatchWorkItem).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Dispatch" }));
    await waitFor(() => expect(api.dispatchWorkItem).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.dispatchWorkItem!).mock.calls[0][1]).toEqual(vi.mocked(api.dispatchWorkItem!).mock.calls[1][1]);
    expect(api.runAgent).not.toHaveBeenCalled();
  });

  it("uses a fresh intent key only after a new displayed attempt and explicit action", async () => {
    const failed: WorkItem = { ...initialItem, status: "failed", attempt_number: 1, run_id: "failed-1" };
    const { api, setItem } = setup(failed);
    vi.mocked(api.retryWorkItem!).mockImplementationOnce(async () => {
      const next: WorkItem = { ...attempted(failed, "failed-2", "retry"), status: "failed" };
      setItem(next);
      return next;
    }).mockImplementationOnce(async () => attempted({ ...failed, attempt_number: 2, run_id: "failed-2" }, "run-3", "retry"));
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Retry" }));
    await screen.findByText(/attempt 2/);
    await waitFor(() => expect(screen.getByRole("button", { name: "Retry" })).toBeEnabled());
    expect(api.retryWorkItem).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    const calls = vi.mocked(api.retryWorkItem!).mock.calls;
    expect(calls[0][1].expectedAttemptNumber).toBe(1);
    expect(calls[1][1].expectedAttemptNumber).toBe(2);
    expect(calls[0][1].idempotencyKey).not.toBe(calls[1][1].idempotencyKey);
  });

  it.each(["work_item_id", "project_id", "agent_id", "agent_version_id", "agent_source_hash", "attempt_number", "run_id"] as const)("rejects an incorrect command response %s without starting a fallback Run", async (field) => {
    const { api } = setup();
    vi.mocked(api.dispatchWorkItem!).mockResolvedValue({ ...attempted(initialItem, "run-1", "start"), [field]: field === "attempt_number" ? 5 : field === "run_id" ? null : "wrong-identity" });
    await userEvent.setup().click(await screen.findByRole("button", { name: "Dispatch" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("WorkItem command identity mismatch");
    expect(api.dispatchWorkItem).toHaveBeenCalledTimes(1);
    expect(api.runAgent).not.toHaveBeenCalled();
  });

  it.each(["missing", "wrong-run", "wrong-operation", "wrong-parent"]) ("rejects a %s attempt lineage in a command response", async (kind) => {
    const failed: WorkItem = { ...initialItem, status: "failed", attempt_number: 1, run_id: "failed-run" };
    const { api } = setup(failed);
    const response = attempted(failed, "new-run", "retry");
    if (kind === "missing") response.attempts = [];
    else if (kind === "wrong-run") response.attempts![0].run_id = "another-run";
    else if (kind === "wrong-operation") response.attempts![0].operation = "start";
    else response.attempts![0].previous_run_id = "another-parent";
    vi.mocked(api.retryWorkItem!).mockResolvedValue(response);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("WorkItem command identity mismatch");
    expect(api.runAgent).not.toHaveBeenCalled();
  });

  it("exposes retry_effect_unsafe with original evidence instead of falling back to a fresh run", async () => {
    const { api } = setup({ ...initialItem, status: "failed", attempt_number: 1, run_id: "failed-run" });
    vi.mocked(api.retryWorkItem!).mockRejectedValue(new LocalApiClientError("A write may already have happened", { code: "retry_effect_unsafe", status: 409 }));
    await userEvent.setup().click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("retry_effect_unsafe: A write may already have happened");
    expect(screen.getByRole("link", { name: "failed-run" })).toHaveAttribute("href", runDetailHref({ projectId: "project-1", agentId: "agent-1", runId: "failed-run" }));
    expect(screen.getByText("version-1", { selector: "code" })).toBeInTheDocument();
    expect(api.runAgent).not.toHaveBeenCalled();
  });
});
