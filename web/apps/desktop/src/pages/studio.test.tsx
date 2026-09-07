import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentSource, DraftResponse, ProjectSummaryResponse, ResourceDescriptor, WorkflowSource } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { LocalApiClientError, type LocalProjectApi } from "../api/local-client";
import { ProjectWorkspaceProvider } from "../api/project-workspace";
import { STUDIO_RAILS_STORAGE_KEY } from "../features/studio/StudioWorkbench";
import { StudioPage } from "./studio";

class TestResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver = TestResizeObserver;
afterEach(() => {
  cleanup();
  window.localStorage.removeItem(STUDIO_RAILS_STORAGE_KEY);
});

const source: AgentSource = {
  schema_version: "1.0", agentspec_version: "26.1", component_type: "Flow", agent_id: "agent-1", slug: "review", name: "Review", description: "",
  inputs: {}, outputs: { result: "string" }, nodes: [{ id: "start", component_type: "Start" }, { id: "out", component_type: "Output", output_name: "result" }], transitions: [{ from: "start", port: "next", to: "out" }],
  extensions: { veyra: { runtime_profile: "guarded", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } },
  ui: { positions: { start: { x: 0, y: 0 }, out: { x: 100, y: 0 } } }, lock: {},
};

const project: ProjectSummaryResponse = { schema_version: "1.0", project_id: "project-1", root_path: "/tmp/project", name: "Project", description: "", pinned: false, pinned_at: null, indexed_at: "2026-08-28T00:00:00Z", manifest_hash: "hash", default_agent_id: null, agent_count: 0, agents: [] };
const draft = (overrides: Partial<DraftResponse> = {}): DraftResponse => ({ schema_version: "1.0", draft_id: "draft-1", revision: 1, etag: '"etag-1"', source_file_hash: "file", source, ...overrides });

function renderPage(api: LocalProjectApi, locale: "en" | "zh" = "en") {
  window.localStorage.setItem("veyra.language", locale);
  return render(<ThemeProvider storageKey="studio-test-theme"><ProjectWorkspaceProvider api={api}><StudioPage projectId="project-1" agentId="agent-1" /></ProjectWorkspaceProvider></ThemeProvider>);
}

describe("StudioPage source and conflict safety", () => {
  it("keeps structurally incomplete JSON in the Source text buffer without crashing the graph", async () => {
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }), getDraft: vi.fn().mockResolvedValue(draft()) } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    renderPage(api);
    await user.click(await screen.findByRole("tab", { name: "Source" }));
    const editor = screen.getByRole("textbox", { name: "Agent source" });
    await user.clear(editor);
    fireEvent.change(editor, { target: { value: '{"schema_version":"1.0"}' } });
    expect(await screen.findByText(/Source cannot be applied/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save draft" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Canvas" }));
    expect(screen.getByRole("button", { name: "Save draft" })).toBeDisabled();
    expect(editor).toHaveValue('{"schema_version":"1.0"}');
  });

  it("uses reloadDraft, not getDraft, to explicitly load a disk version after a draft conflict", async () => {
    const conflict = new LocalApiClientError("External edit", { status: 409, code: "draft_conflict" });
    const getDraft = vi.fn().mockRejectedValue(conflict);
    const reloadDraft = vi.fn().mockResolvedValue(draft({ revision: 2, etag: '"etag-2"', source: { ...source, name: "Disk review" } }));
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }), getDraft, reloadDraft } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    renderPage(api);
    await user.click(await screen.findByRole("button", { name: "Load disk version" }));
    await waitFor(() => expect(reloadDraft).toHaveBeenCalledWith("project-1", "agent-1"));
    expect(getDraft).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("tab", { name: "Form" }));
    expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue("Disk review");
  });

  it("offers disk reload after a save conflict and keeps ordinary initial loading separate", async () => {
    const conflict = new LocalApiClientError("External edit", { status: 409, code: "draft_conflict" });
    const saveDraft = vi.fn().mockRejectedValue(conflict);
    const reloadDraft = vi.fn().mockResolvedValue(draft({ revision: 2, etag: '"etag-2"' }));
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }), getDraft: vi.fn().mockResolvedValue(draft()), saveDraft, reloadDraft } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    renderPage(api);
    await screen.findByRole("tab", { name: "Canvas" });
    expect(screen.queryByText("Agent definition")).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Form" }));
    await user.clear(screen.getByRole("textbox", { name: "Name" }));
    await user.type(screen.getByRole("textbox", { name: "Name" }), "Changed");
    await user.click(screen.getByRole("tab", { name: "Canvas" }));
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    await user.click(await screen.findByRole("button", { name: "Load disk version" }));
    await waitFor(() => expect(reloadDraft).toHaveBeenCalledWith("project-1", "agent-1"));
  });

  it("autosaves a dirty draft after idle debounce without a manual save click", async () => {
    const saveDraft = vi.fn().mockResolvedValue(draft({ revision: 2, etag: '"etag-2"', source: { ...source, name: "Changed" } }));
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }), getDraft: vi.fn().mockResolvedValue(draft()), saveDraft } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    renderPage(api);
    await user.click(await screen.findByRole("tab", { name: "Form" }));
    await user.clear(screen.getByRole("textbox", { name: "Name" }));
    await user.type(screen.getByRole("textbox", { name: "Name" }), "Changed");
    expect(saveDraft).not.toHaveBeenCalled();
    await waitFor(() => expect(saveDraft).toHaveBeenCalledWith(
      "project-1",
      "agent-1",
      { source: expect.objectContaining({ name: "Changed" }), expected_revision: 1 },
      { etag: '"etag-1"' },
    ), { timeout: 3500 });
    await user.click(screen.getByRole("tab", { name: "Canvas" }));
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(screen.queryByText("Draft saved with the current revision.")).not.toBeInTheDocument();
  }, 8000);

  it("renders stable graph diagnostic codes as localized Studio copy", async () => {
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }), getDraft: vi.fn().mockResolvedValue(draft({ source: { ...source, nodes: [{ id: "out", component_type: "Output", output_name: "result" }], transitions: [] } })) } as unknown as LocalProjectApi;
    renderPage(api, "zh");
    expect(await screen.findByText("必须且只能有一个 Start 节点。")).toBeInTheDocument();
  });

  it("loads Catalog tools into the palette and attaches Read File uses, lock, and permissions", async () => {
    const read: ResourceDescriptor = {
      schema_version: "1.0",
      resource_id: "veyra.tool.filesystem.read",
      kind: "tool",
      version: "1.0.0",
      reference: "veyra.tool.filesystem.read@1.0.0",
      name: "Filesystem Read",
      description: "Read a bounded Project path.",
      origin: "builtin",
      content_hash: "d".repeat(64),
      availability: "ready",
      factory_selectable: true,
      runtime_status: "supported",
      required_permissions: { network_hosts: [], tools: ["veyra.tool.filesystem.read"], filesystem_read_roots: ["project"], filesystem_write_roots: [], shell_workspace_only: false },
      tags: ["filesystem"],
      spec: { ui: { category: "filesystem", icon: "file-text", title: "Read File" }, approval_required: false },
    };
    const github: ResourceDescriptor = {
      ...read,
      resource_id: "veyra.tool.github.read",
      reference: "veyra.tool.github.read@1.0.0",
      name: "GitHub Read",
      availability: "unavailable",
      factory_selectable: false,
      runtime_status: "runtime_not_supported",
      required_permissions: { network_hosts: ["api.github.com"], tools: ["veyra.tool.github.read"], filesystem_read_roots: [], filesystem_write_roots: [], shell_workspace_only: false },
      spec: { ui: { category: "git", icon: "github", title: "GitHub Read" } },
    };
    const start: ResourceDescriptor = {
      ...read,
      resource_id: "veyra.component.start",
      kind: "component",
      reference: "veyra.component.start@1.0.0",
      name: "Start",
      required_permissions: { network_hosts: [], tools: [], filesystem_read_roots: [], filesystem_write_roots: [], shell_workspace_only: false },
      spec: { fields: [], output_ports: ["next"], ui: { category: "core", icon: "circle-play", title: "Start" } },
    };
    const listResources = vi.fn(async ({ kind }: { kind?: string } = {}) => ({
      schema_version: "1.0",
      resources: kind === "tool" ? [read, github] : kind === "component" ? [start] : [start, read, github],
      kinds: [],
    }));
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }), getDraft: vi.fn().mockResolvedValue(draft()), listResources } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    renderPage(api);
    expect(await screen.findByRole("button", { name: /Read File/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /GitHub Read/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /Read File/ }));
    expect((await screen.findAllByDisplayValue("veyra.tool.filesystem.read@1.0.0")).length).toBeGreaterThan(1);
    expect(screen.getByDisplayValue("veyra.tool.filesystem.read")).toBeInTheDocument();
  });

  it("collapses catalog and inspector rails and restores them from the edge strips", async () => {
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }), getDraft: vi.fn().mockResolvedValue(draft()) } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    renderPage(api);
    expect(await screen.findByRole("button", { name: /Start Entry point/ })).toBeInTheDocument();
    expect(screen.getByText("Select a canvas node or connection to edit.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Collapse catalog" }));
    expect(screen.queryByRole("button", { name: /Start Entry point/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand catalog" })).toHaveAttribute("aria-expanded", "false");
    await user.click(screen.getByRole("button", { name: "Collapse inspector" }));
    expect(screen.queryByText("Select a canvas node or connection to edit.")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Expand catalog" }));
    expect(screen.getByRole("button", { name: /Start Entry point/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Expand inspector" }));
    expect(screen.getByText("Select a canvas node or connection to edit.")).toBeInTheDocument();
  });

  it("overlays a collapsible test run panel without removing the run controls until collapsed", async () => {
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }), getDraft: vi.fn().mockResolvedValue(draft()) } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    renderPage(api);
    expect(await screen.findByRole("button", { name: "Test run" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Collapse test panel" }));
    expect(screen.queryByRole("button", { name: "Test run" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand test panel" })).toHaveAttribute("aria-expanded", "false");
    await user.click(screen.getByRole("button", { name: "Expand test panel" }));
    expect(screen.getByRole("button", { name: "Test run" })).toBeInTheDocument();
  });

  it("remembers collapsed studio rails after remount", async () => {
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }), getDraft: vi.fn().mockResolvedValue(draft()) } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    const { unmount } = renderPage(api);
    await user.click(await screen.findByRole("button", { name: "Collapse catalog" }));
    await waitFor(() => {
      expect(window.localStorage.getItem(STUDIO_RAILS_STORAGE_KEY)).toContain('"paletteCollapsed":true');
    });
    unmount();
    renderPage(api);
    expect(await screen.findByRole("button", { name: "Expand catalog" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Start Entry point/ })).not.toBeInTheDocument();
  });

  it("keeps Agent internals off the Workflow palette and orchestration nodes off the Agent palette", async () => {
    const workflow: WorkflowSource = {
      schema_version: "1.0",
      component_type: "Workflow",
      workflow_id: "wf-1",
      slug: "review-path",
      name: "Review path",
      description: "",
      version: "1.0.0",
      inputs: { prompt: "string" },
      outputs: { result: "string" },
      nodes: [{ id: "start", component_type: "Start" }, { id: "out", component_type: "Output", output_name: "result" }],
      transitions: [{ from: "start", port: "next", to: "out" }],
      extensions: { veyra: { permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } },
      ui: { positions: { start: { x: 0, y: 0 }, out: { x: 100, y: 0 } } },
      lock: {},
    };
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }),
      getDraft: vi.fn().mockResolvedValue(draft()),
      getWorkflowDraft: vi.fn().mockResolvedValue({ schema_version: "1.0", draft_id: "wf-draft", revision: 1, etag: '"etag-w"', source_file_hash: "wf-hash", source: workflow }),
    } as unknown as LocalProjectApi;
    renderPage(api);
    expect(await screen.findByRole("button", { name: /Model Model instruction/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /AgentCall/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Condition Branch expression/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Transform Map values/ })).not.toBeInTheDocument();
    cleanup();
    const workflowProject = {
      ...project,
      agents: [{ agent_id: "agent-1", slug: "translation", name: "translation", description: "", pinned: false, source_path: "agents/translation/agent.vagent.yaml", source_file_hash: "file" }],
    };
    const workflowApi = {
      ...api,
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [workflowProject] }),
    } as unknown as LocalProjectApi;
    render(<ThemeProvider storageKey="studio-test-theme"><ProjectWorkspaceProvider api={workflowApi}><StudioPage projectId="project-1" workflowId="wf-1" /></ProjectWorkspaceProvider></ThemeProvider>);
    const agentCall = await screen.findByRole("button", { name: /AgentCall Call a Project Agent/ });
    expect(agentCall).toBeEnabled();
    expect(screen.getByRole("button", { name: /translation Call a committed version/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Condition Branch expression/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Transform Map values/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Model Model instruction/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Tool Governed tool/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Test run" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run Workflow" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /Workflow run inputs/i })).not.toBeInTheDocument();
    expect(screen.getByText("Run the current workflow with real inputs")).toBeInTheDocument();
  });

  it("inserts a Project Agent between Start and Output and explains missing committed versions", async () => {
    const workflow: WorkflowSource = {
      schema_version: "1.0",
      component_type: "Workflow",
      workflow_id: "wf-1",
      slug: "review-path",
      name: "Review path",
      description: "",
      version: "1.0.0",
      inputs: { prompt: "string" },
      outputs: { result: "string" },
      nodes: [{ id: "start", component_type: "Start" }, { id: "out", component_type: "Output", output_name: "result" }],
      transitions: [{ from: "start", port: "next", to: "out" }],
      extensions: { veyra: { permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } },
      ui: { positions: { start: { x: 0, y: 0 }, out: { x: 100, y: 0 } } },
      lock: {},
    };
    const workflowProject = {
      ...project,
      agents: [{ agent_id: "01900000-0000-7000-8000-000000000001", slug: "translation", name: "translation", description: "", pinned: false, source_path: "agents/translation/agent.vagent.yaml", source_file_hash: "file" }],
    };
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [workflowProject] }),
      getWorkflowDraft: vi.fn().mockResolvedValue({ schema_version: "1.0", draft_id: "wf-draft", revision: 1, etag: '"etag-w"', source_file_hash: "wf-hash", source: workflow }),
      listAgentVersions: vi.fn().mockResolvedValue({ schema_version: "1.0", versions: [] }),
    } as unknown as LocalProjectApi;
    window.localStorage.setItem("veyra.language", "zh");
    const user = userEvent.setup();
    render(<ThemeProvider storageKey="studio-test-theme"><ProjectWorkspaceProvider api={api}><StudioPage projectId="project-1" workflowId="wf-1" /></ProjectWorkspaceProvider></ThemeProvider>);
    await user.click(await screen.findByRole("button", { name: /translation 调用已提交版本/ }));
    expect(screen.queryByText(/还没有接到流程上/)).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "去提交版本" })).toBeInTheDocument();
    expect(screen.getByText(/还没有绑定已提交的 Agent 版本/)).toBeInTheDocument();
  });
});
