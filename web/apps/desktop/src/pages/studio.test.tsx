import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentSource, DraftResponse, ProjectResourceDescriptor, ProjectSummaryResponse, ResourceDescriptor, WorkflowSource } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { LocalApiClientError, type LocalProjectApi } from "../api/local-client";
import { ProjectWorkspaceProvider } from "../api/project-workspace";
import { STUDIO_RAILS_STORAGE_KEY } from "../features/studio/StudioWorkbench";
import { DependencyReport } from "../features/studio/DependencyReport";
import { fluidRunHeight } from "../features/studio/studio-chrome";
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
  Reflect.deleteProperty(window, "matchMedia");
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

function stubCompactViewport(compact: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: (query: string) => ({
      matches: compact && query.includes("max-width: 960px"),
      media: query,
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
      dispatchEvent() { return false; },
    }),
  });
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
    expect(await screen.findByText("必须且只能有一个输入节点。")).toBeInTheDocument();
  });

  it("binds only Project Tools and preserves pins through Canvas/Form/Source, save and refresh", async () => {
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
      availability: "requires_configuration",
      blocking_reasons: [{ code: "secret_not_configured", message: "Configure host credential github.token." }],
      factory_selectable: true,
      runtime_status: "runtime_not_configured",
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
    const owned = (resource: ResourceDescriptor): ProjectResourceDescriptor => ({ ...resource, scope: "project", binding_status: "current", binding_source: "manual", bound_content_hash: resource.content_hash, used_by: [] });
    const listProjectResources = vi.fn().mockResolvedValue({ schema_version: "1.0", project_id: project.project_id, resources: [owned(read), owned(github), { ...owned(read), reference: "unbound@1.0.0", name: "Unbound tool", scope: "used_unbound", spec: {} }, { ...owned(read), reference: "stale@1.0.0", name: "Stale tool", bound_content_hash: "a".repeat(64), binding_status: "stale", spec: {} }, { ...owned(read), reference: "missing-adapter@1.0.0", name: "Unavailable tool", availability: "unavailable", spec: {} }, { ...owned(start), scope: "builtin" }], missing_references: ["missing@1.0.0"] });
    let disk = draft();
    const getDraft = vi.fn(async () => disk);
    const saveDraft = vi.fn(async (_projectId, _agentId, request) => { disk = draft({ source: request.source, revision: disk.revision + 1, etag: `"etag-${disk.revision + 1}"` }); return disk; });
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }), getDraft, listProjectResources, listResources, saveDraft } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    const page = renderPage(api);
    expect(await screen.findByRole("button", { name: /Read File/ })).toBeInTheDocument();
    expect(listProjectResources).toHaveBeenCalledWith("project-1");
    expect(listResources).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /Unbound tool/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Stale tool/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Unavailable tool/ })).toBeDisabled();
    expect(screen.queryByText(/Missing Project resources:/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /GitHub Read/ })).toHaveTextContent("Configure");
    expect(screen.getByRole("button", { name: /GitHub Read/ })).toHaveTextContent("Configure host credential github.token.");
    expect(screen.getByRole("button", { name: /GitHub Read/ })).not.toHaveTextContent("Runnable");
    await user.dblClick(screen.getByRole("button", { name: /Read File/ }));
    expect((await screen.findAllByDisplayValue("veyra.tool.filesystem.read@1.0.0")).length).toBeGreaterThan(1);
    expect(screen.getByDisplayValue("veyra.tool.filesystem.read")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Form" }));
    expect(screen.getByRole("textbox", { name: "Resource reference" })).toHaveValue(read.reference);
    expect(screen.getByRole("textbox", { name: "Pinned hash" })).toHaveValue(read.content_hash);
    fireEvent.change(screen.getByRole("textbox", { name: /input_mapping/ }), { target: { value: '{"path":"request"}' } });
    await user.click(screen.getByRole("tab", { name: "Source" }));
    const boundSource = JSON.parse((screen.getByRole("textbox", { name: "Agent source" }) as HTMLTextAreaElement).value) as AgentSource;
    expect(boundSource.nodes.filter((node) => node.component_type === "Tool")).toHaveLength(1);
    expect(boundSource.nodes.find((node) => node.component_type === "Tool")?.input_mapping).toEqual({ path: "request" });
    expect(boundSource.lock[read.reference]).toBe(read.content_hash);
    expect(boundSource.ui.bindings).toBeUndefined();
    await user.click(screen.getByRole("tab", { name: "Canvas" }));
    await user.dblClick(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(saveDraft).toHaveBeenCalledTimes(1));
    expect(saveDraft).toHaveBeenCalledWith("project-1", "agent-1", { source: boundSource, expected_revision: 1 }, { etag: '"etag-1"' });
    page.unmount();
    listProjectResources.mockResolvedValue({ schema_version: "1.0", project_id: project.project_id, resources: [{ ...owned(read), content_hash: "b".repeat(64), binding_status: "stale" }], missing_references: [] });
    renderPage(api);
    await user.click(await screen.findByRole("tab", { name: "Source" }));
    expect(JSON.parse((screen.getByRole("textbox", { name: "Agent source" }) as HTMLTextAreaElement).value)).toEqual(boundSource);
    await user.click(screen.getByRole("tab", { name: "Form" }));
    expect(screen.getByRole("textbox", { name: "Pinned hash" })).toHaveValue(read.content_hash);
    fireEvent.change(screen.getByRole("textbox", { name: "Name" }), { target: { value: "Stale draft edit" } });
    await user.click(screen.getByRole("tab", { name: "Canvas" }));
    expect(screen.getByRole("button", { name: /Read File/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Read File/ })).toHaveTextContent("Project pin stale");
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(saveDraft).toHaveBeenCalledTimes(2));
    expect(disk.source).toEqual({ ...boundSource, name: "Stale draft edit" });
  });

  it.each([
    ["resource_unbound", "Not bound to Project"],
    ["project_binding_stale", "Project binding stale"],
    ["configuration_required", "Needs configuration"],
    ["ready", "Ready"],
  ] as const)("renders the %s dependency status without claiming Runnable", (status, label) => {
    render(<DependencyReport locale="en" validation={{ schema_version: "1.0", valid: true, source_hash: "source", behavior_hash: "behavior", lock_hash: "lock", runtime_ready: status === "ready", dependency_summary: { total: 1, ready: status === "ready" ? 1 : 0, attention: status === "ready" ? 0 : 1 }, dependencies: [{ reference: "veyra.tool.filesystem.read@1.0.0", name: "Read File", kind: "tool", status, detail: "Dependency evidence", used_by: ["read"], bound_by: [] }] }} />);
    expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.queryByText(/Runnable/)).not.toBeInTheDocument();
  });

  it("never falls back to global Tools when Project resource loading fails", async () => {
    const listResources = vi.fn();
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }), getDraft: vi.fn().mockResolvedValue(draft()), listProjectResources: vi.fn().mockRejectedValue(new Error("offline")), listResources } as unknown as LocalProjectApi;
    renderPage(api);
    expect(await screen.findByText("Project resources unavailable. Refresh to retry.")).toBeInTheDocument();
    expect(listResources).not.toHaveBeenCalled();
    expect(screen.getByText("Add a Tool in Project Resources first.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Read File|GitHub/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Tool / })).toBeInTheDocument();
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

  it("inserts an Agent palette component between Start and Output", async () => {
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }), getDraft: vi.fn().mockResolvedValue(draft()) } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    renderPage(api);
    expect(await screen.findByRole("button", { name: /Start Entry point/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /Model Model instruction/ }));
    expect(screen.queryByText(/is not wired into the flow/)).not.toBeInTheDocument();
    expect(await screen.findByDisplayValue("model.primary")).toBeInTheDocument();
  });

  it("keeps compact viewports to one studio overlay so the canvas stays usable", async () => {
    stubCompactViewport(true);
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }), getDraft: vi.fn().mockResolvedValue(draft()) } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    renderPage(api);
    expect(await screen.findByRole("button", { name: "Expand catalog" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand inspector" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand test panel" })).toBeInTheDocument();
    expect(document.querySelector(".studio-stage.is-compact")).not.toBeNull();
    await user.click(screen.getByRole("button", { name: "Expand inspector" }));
    expect(screen.getByText("Select a canvas node or connection to edit.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand catalog" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand test panel" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Expand catalog" }));
    expect(screen.getByRole("button", { name: /Start Entry point/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand inspector" })).toBeInTheDocument();
  });

  it("expands the collapsed inspector with the clicked canvas node", async () => {
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }), getDraft: vi.fn().mockResolvedValue(draft()) } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    renderPage(api);
    await user.click(await screen.findByRole("button", { name: "Collapse inspector" }));
    expect(screen.queryByText("Select a canvas node or connection to edit.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand inspector" })).toBeInTheDocument();
    fireEvent.click(screen.getByText("start"));
    expect(await screen.findByRole("button", { name: "Collapse inspector" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("start")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete node" })).toBeInTheDocument();
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

  it("lets the user resize catalog, inspector, and test panels without keeping the sizes after remount", async () => {
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }), getDraft: vi.fn().mockResolvedValue(draft()) } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    const { unmount } = renderPage(api);
    const catalog = await screen.findByRole("separator", { name: "Resize catalog" });
    expect(catalog).toHaveAttribute("aria-valuenow", "228");
    fireEvent.keyDown(catalog, { key: "ArrowRight" });
    expect(screen.getByRole("separator", { name: "Resize catalog" })).toHaveAttribute("aria-valuenow", "236");
    fireEvent.keyDown(screen.getByRole("separator", { name: "Resize inspector" }), { key: "ArrowLeft" });
    expect(screen.getByRole("separator", { name: "Resize inspector" })).toHaveAttribute("aria-valuenow", "308");
    fireEvent.keyDown(screen.getByRole("separator", { name: "Resize test panel" }), { key: "ArrowUp" });
    expect(screen.getByRole("separator", { name: "Resize test panel" })).toHaveAttribute("aria-valuenow", String(fluidRunHeight() + 8));
    expect(screen.getByRole("toolbar", { name: "Canvas editing" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Duplicate" })).not.toBeInTheDocument();
    await waitFor(() => {
      const stored = window.localStorage.getItem(STUDIO_RAILS_STORAGE_KEY) ?? "";
      expect(stored).not.toContain("paletteWidth");
    });
    await user.click(screen.getByRole("button", { name: "Collapse catalog" }));
    expect(screen.queryByRole("separator", { name: "Resize catalog" })).not.toBeInTheDocument();
    unmount();
    renderPage(api);
    expect(await screen.findByRole("separator", { name: "Resize inspector" })).toHaveAttribute("aria-valuenow", "300");
    expect(screen.getByRole("separator", { name: "Resize test panel" })).toHaveAttribute("aria-valuenow", String(fluidRunHeight()));
    expect(screen.getByRole("button", { name: "Expand catalog" })).toBeInTheDocument();
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
    expect(screen.getByRole("button", { name: /Condition Branch expression/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Transform Map values/ })).toBeInTheDocument();
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

  it("undoes an inserted Workflow AgentCall from the canvas toolbar", async () => {
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
    expect(await screen.findByRole("button", { name: "去提交版本" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "撤销" }));
    await waitFor(() => expect(screen.queryByText(/还没有绑定已提交的 Agent 版本/)).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "重做" }));
    expect(await screen.findByText(/还没有绑定已提交的 Agent 版本/)).toBeInTheDocument();
  });

  it("copies a Model node with select-all and pastes a new copy", async () => {
    const withModel: AgentSource = {
      ...source,
      nodes: [
        { id: "start", component_type: "Start" },
        { id: "model", component_type: "Model", model_ref: "model.primary", system_prompt: "Hi" },
        { id: "out", component_type: "Output", output_name: "result" },
      ],
      transitions: [
        { from: "start", port: "next", to: "model" },
        { from: "model", port: "next", to: "out" },
      ],
      ui: { positions: { start: { x: 0, y: 0 }, model: { x: 120, y: 0 }, out: { x: 240, y: 0 } } },
    };
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }),
      getDraft: vi.fn().mockResolvedValue(draft({ source: withModel })),
    } as unknown as LocalProjectApi;
    renderPage(api);
    await screen.findByRole("button", { name: "Undo" });
    fireEvent.keyDown(window, { key: "a", code: "KeyA", metaKey: true });
    fireEvent.keyDown(window, { key: "c", code: "KeyC", metaKey: true });
    await waitFor(() => expect(screen.getByRole("button", { name: "Paste" })).toBeEnabled());
    fireEvent.keyDown(window, { key: "v", code: "KeyV", metaKey: true });
    await waitFor(() => expect(screen.getByRole("button", { name: "Undo" })).toBeEnabled());
  });
});
