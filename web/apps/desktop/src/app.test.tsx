import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FolderKanban } from "lucide-react";
import { parseDesktopRoute, projectRoutePaths, type CommunityAccount, type ProjectSummaryResponse, type SaveDraftRequest, type SaveDraftResponse } from "@veyra/api-contracts";
import { createCommunityApi, normalizeCommunityAvatarUrl } from "@veyra/connected-account";
import { ApplicationShell, ThemeProvider } from "@veyra/ui";
import { LocalApiClientError, type LocalProjectApi } from "./api/local-client";
import { DesktopApp } from "./app";

function project(overrides: Partial<ProjectSummaryResponse> = {}): ProjectSummaryResponse {
  return {
    schema_version: "1.0",
    project_id: "project-1",
    root_path: "/Users/test/Projects/project-one",
    name: "Project One",
    description: "",
    pinned: false,
    pinned_at: null,
    indexed_at: "2026-08-28T00:00:00Z",
    manifest_hash: "0123456789abcdef0123456789abcdef",
    default_agent_id: null,
    agent_count: 0,
    agents: [],
    ...overrides,
  };
}

function apiFor(projects: ProjectSummaryResponse[] = []): LocalProjectApi & {
  listProjects: ReturnType<typeof vi.fn>;
  createProject: ReturnType<typeof vi.fn>;
  openProject: ReturnType<typeof vi.fn>;
  selectDirectory: ReturnType<typeof vi.fn>;
  getProject: ReturnType<typeof vi.fn>;
  updateProject: ReturnType<typeof vi.fn>;
  deleteProject: ReturnType<typeof vi.fn>;
  updateAgent: ReturnType<typeof vi.fn>;
  deleteAgent: ReturnType<typeof vi.fn>;
  getDraft: ReturnType<typeof vi.fn>;
  saveDraft: ReturnType<typeof vi.fn>;
  listAgentTemplates: ReturnType<typeof vi.fn>;
  createAgent: ReturnType<typeof vi.fn>;
  importAgent: ReturnType<typeof vi.fn>;
  listAgentRuns: ReturnType<typeof vi.fn>;
} {
  const getProject = vi.fn().mockImplementation(async (projectId: string) => project({ project_id: projectId, name: projectId }));
  return {
    listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects }),
    createProject: vi.fn().mockResolvedValue(project({ project_id: "created-project", name: "Created Project", root_path: "/tmp/created-project" })),
    openProject: vi.fn().mockResolvedValue(project({ project_id: "opened-project", name: "Opened Project", root_path: "/tmp/opened-project" })),
    selectDirectory: vi.fn().mockResolvedValue({ schema_version: "1.0", status: "selected", root_path: "/tmp/selected-folder" }),
    getProject,
    updateProject: vi.fn().mockImplementation(async (projectId: string, input: { pinned?: boolean; name?: string; description?: string }) => project({ project_id: projectId, name: input.name ?? projectId, description: input.description ?? "", pinned: input.pinned ?? false, pinned_at: input.pinned ? "2026-08-28T00:00:00Z" : null })),
    deleteProject: vi.fn().mockResolvedValue({ schema_version: "1.0", project_id: "project-1", disposition: "trashed", removed_at: "2026-08-28T00:00:00Z" }),
    updateAgent: vi.fn().mockImplementation(async (projectId: string, agentId: string) => project({ project_id: projectId, agents: [{ agent_id: agentId, slug: "agent", name: "Agent", description: "", pinned: true, source_path: "agents/agent/agent.vagent.yaml", source_file_hash: "agent-hash" }], default_agent_id: agentId, agent_count: 1 })),
    deleteAgent: vi.fn().mockResolvedValue({ schema_version: "1.0", project_id: "project-1", agent_id: "agent-1", disposition: "trashed", removed_at: "2026-08-28T00:00:00Z", project: project() }),
    listAgentTemplates: vi.fn().mockResolvedValue({ schema_version: "1.0", templates: [{ template_id: "review", name: "Review Agent", description: "Reviews a bounded scope.", default_slug: "review-agent" }] }),
    createAgent: vi.fn().mockResolvedValue({ schema_version: "1.0", project_id: "project-1", agent_id: "created-agent", slug: "created-agent", name: "Created Agent", description: "", source_path: "agents/created-agent/agent.vagent.yaml", source_file_hash: "created-hash" }),
    importAgent: vi.fn().mockResolvedValue({ schema_version: "1.0", project_id: "project-1", agent_id: "imported-agent", slug: "imported-agent", name: "Imported Agent", description: "", source_path: "agents/imported-agent/agent.vagent.yaml", source_file_hash: "imported-hash" }),
    listAgentRuns: vi.fn().mockResolvedValue({ schema_version: "1.0", runs: [] }),
    getDraft: vi.fn().mockResolvedValue({ schema_version: "1.0", draft_id: "draft-1", revision: 1, etag: "etag-1", source_file_hash: "source-hash", source: { schema_version: "1.0", agentspec_version: "26.1", component_type: "Flow", agent_id: "agent-1", slug: "reviewer", name: "Reviewer", description: "", inputs: {}, outputs: {}, nodes: [], transitions: [], extensions: { veyra: { runtime_profile: "guarded-local", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: true, checks: [] } } }, ui: { positions: {} }, lock: {} } }),
    saveDraft: vi.fn().mockImplementation(async (_projectId: string, _agentId: string, input: SaveDraftRequest): Promise<SaveDraftResponse> => ({ schema_version: "1.0", revision: input.expected_revision + 1, etag: "etag-2", source: input.source })),
  };
}

const connectedAccount = {
  id: "account-desktop",
  email: "alice@example.com",
  handle: "veyra-alice",
  display_name: "Alice",
  avatar_url: null,
};

const connectedSession = {
  id: "session-desktop",
  device_name: "Alice Mac",
  user_agent: "Test browser",
  created_at: "2026-08-25T08:00:00Z",
  last_seen_at: "2026-08-26T08:00:00Z",
  expires_at: "2026-09-25T08:00:00Z",
  current: true,
};

function jsonResponse(status: number, body: object): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function accountApi(fetcher: typeof fetch) {
  return createCommunityApi({ baseUrl: "/community-api/api/v1", fetcher });
}

function setViewport(isMobile: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: (query: string) => ({ matches: isMobile && query.includes("max-width"), media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
  });
}

beforeEach(() => {
  window.localStorage.clear();
  window.location.hash = "#/projects";
  setViewport(false);
});

afterEach(() => {
  cleanup();
  window.location.hash = "";
});

describe("desktop Project workspace", () => {
  it("renders the normal New chat surface at #/projects and keeps a compact Project section without Recent", async () => {
    const first = project({ project_id: "p-one", name: "Alpha Project" });
    const second = project({ project_id: "p-two", name: "Beta Project", root_path: "/Users/test/Projects/project-two", agents: [{ agent_id: "agent-1", slug: "reviewer", name: "Reviewer", description: "", pinned: false, source_path: "agents/reviewer/agent.vagent.yaml", source_file_hash: "fedcba9876543210" }], agent_count: 1 });
    const api = apiFor([first, second]);
    api.getProject.mockImplementation(async (projectId: string) => [first, second].find((item) => item.project_id === projectId) ?? first);
    render(<DesktopApp api={api} />);

    expect(await screen.findByRole("heading", { name: "New chat", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New chat" })).toHaveAttribute("href", "#/chat");
    expect(screen.getByRole("link", { name: "Run workspace" })).toHaveAttribute("href", "#/monitor");
    expect(screen.getByRole("link", { name: "Resource library" })).toHaveAttribute("href", "#/components");
    expect(screen.getByRole("link", { name: "Knowledge base" })).toHaveAttribute("href", "#/files");
    expect(screen.getByRole("link", { name: "Community" })).toHaveAttribute("href", "#/community");
    expect(screen.getByText("Projects", { selector: ".nav-group-projects .nav-group-label" })).toBeInTheDocument();
    expect(document.querySelector(".nav-group-recent")).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Alpha Project/ }).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Signal Review")).not.toBeInTheDocument();
    expect(screen.queryByText("Verified results")).not.toBeInTheDocument();

    expect(screen.queryByRole("heading", { name: "Projects", level: 2 })).not.toBeInTheDocument();
  });

  it("creates a Project with an intentionally blank name body and no folder picker", async () => {
    const api = apiFor();
    const created = project({ project_id: "created-project", name: "Created Project", root_path: "/tmp/created-project" });
    api.createProject.mockResolvedValue(created);
    api.listProjects.mockResolvedValueOnce({ schema_version: "1.0", projects: [] }).mockRejectedValueOnce(new Error("refresh unavailable"));
    const user = userEvent.setup();
    render(<DesktopApp api={api} />);

    await user.click(await screen.findByRole("button", { name: "Create Project" }));
    expect(screen.getByRole("dialog", { name: "Create project" })).toBeInTheDocument();
    expect(await screen.findByRole("textbox", { name: "Project name" })).toHaveValue("");
    expect(screen.queryByRole("textbox", { name: /path/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/Connect project/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/folder|save location|path|downloads/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /folder|save location/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(api.createProject).toHaveBeenCalledWith({ description: "" }));
    expect(api.selectDirectory).not.toHaveBeenCalled();
    expect(window.location.hash).toBe("#/projects");
    expect(await screen.findByRole("heading", { name: "New chat", level: 2 })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByText("refresh unavailable")).not.toBeInTheDocument();
  });

  it("opens an existing Project from its distinct FolderOpen action", async () => {
    const api = apiFor();
    const opened = project({ project_id: "opened-project", name: "Opened Project", root_path: "/tmp/opened-project" });
    api.openProject.mockResolvedValue(opened);
    api.selectDirectory.mockResolvedValue({ schema_version: "1.0", status: "selected", root_path: "/tmp/opened-project" });
    const user = userEvent.setup();
    render(<DesktopApp api={api} />);

    await user.click(await screen.findByRole("button", { name: "Open existing project" }));
    expect(screen.getByText("Choose an existing Veyra project folder.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Select folder" }));
    await user.click(screen.getByRole("button", { name: "Open project" }));

    await waitFor(() => expect(api.openProject).toHaveBeenCalledWith({ root_path: "/tmp/opened-project" }));
    expect(window.location.hash).toBe("#/projects");
  });

  it("localizes a create failure without rendering a folder path on a Chinese Desktop", async () => {
    window.localStorage.setItem("veyra.language", "zh");
    const api = apiFor();
    api.createProject.mockRejectedValue(new LocalApiClientError("/Users/test/Downloads/test unavailable", { status: 503, code: "project_unavailable" }));
    const user = userEvent.setup();
    render(<DesktopApp api={api} />);

    await user.click(await screen.findByRole("button", { name: "新建项目" }));
    await user.type(screen.getByRole("textbox", { name: "项目名称" }), "test");
    await user.click(screen.getByRole("button", { name: "创建" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("创建项目失败，请稍后重试。");
    expect(screen.queryByText("/Users/test/Downloads/test unavailable")).not.toBeInTheDocument();
  });

  it("keeps open-existing picker cancellation and errors recoverable", async () => {
    const api = apiFor();
    api.selectDirectory.mockResolvedValueOnce({ schema_version: "1.0", status: "cancelled", root_path: null }).mockRejectedValueOnce(new Error("picker unavailable"));
    const user = userEvent.setup();
    render(<DesktopApp api={api} />);
    await user.click(await screen.findByRole("button", { name: "Open existing project" }));
    await user.click(screen.getByRole("button", { name: "Select folder" }));
    expect(screen.queryByText(/^Selected:/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Select folder" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("picker unavailable");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders a real Agent array and count on Project detail", async () => {
    const detailed = project({
      project_id: "p-detail",
      name: "Evidence Project",
      agents: [
        { agent_id: "agent-a", slug: "reviewer", name: "Reviewer", description: "", pinned: false, source_path: "agents/reviewer/agent.vagent.yaml", source_file_hash: "aaaaaaaaaaaaaaaa" },
        { agent_id: "agent-b", slug: "verifier", name: "Verifier", description: "", pinned: false, source_path: "agents/verifier/agent.vagent.yaml", source_file_hash: "bbbbbbbbbbbbbbbb" },
      ],
    });
    const api = apiFor([detailed]);
    api.getProject.mockResolvedValue(detailed);
    window.location.hash = projectRoutePaths.project("p-detail");
    render(<DesktopApp api={api} />);

    expect(await screen.findByRole("heading", { name: "Evidence Project", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "2 Agents" })).toBeInTheDocument();
    expect(screen.getByText("Reviewer")).toBeInTheDocument();
    expect(screen.getByText("reviewer")).toBeInTheDocument();
    expect(screen.getByText("agents/reviewer/agent.vagent.yaml", { exact: false })).toBeInTheDocument();
    expect(screen.queryByText("Agents will be added later.")).not.toBeInTheDocument();
    expect(api.getProject).toHaveBeenCalledWith("p-detail");
  });

  it("renders exactly one Pinned section and moves the previous pin out when another Project is pinned", async () => {
    const pinned = project({ project_id: "pinned", name: "Pinned Project", pinned: true, pinned_at: "2026-08-28T08:00:00Z" });
    const others = Array.from({ length: 10 }, (_, index) => project({ project_id: `project-${index}`, name: `Project ${index}`, indexed_at: `2026-08-28T0${index}:00:00Z` }));
    const api = apiFor([others[0]!, pinned, ...others.slice(1)]);
    api.updateProject.mockImplementation(async (projectId: string, input: { pinned?: boolean }) => project({ project_id: projectId, name: projectId === "project-0" ? "Project 0" : "Pinned Project", pinned: input.pinned ?? false, pinned_at: input.pinned ? "2026-08-28T09:00:00Z" : null }));
    render(<DesktopApp api={api} />);

    await screen.findByRole("link", { name: "Pinned Project" });
    expect(document.querySelectorAll(".nav-group-pinned")).toHaveLength(1);
    expect(document.querySelector(".nav-group-pinned a")?.getAttribute("aria-label")).toBe("Pinned Project");
    expect([...document.querySelectorAll(".nav-group-projects a")].map((link) => link.getAttribute("aria-label"))).not.toContain("Pinned Project");

    await userEvent.click(screen.getByRole("button", { name: "Project actions: Project 0" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Pin Project" }));
    await waitFor(() => expect(api.updateProject).toHaveBeenCalledWith("project-0", { pinned: true }));
    await waitFor(() => expect(document.querySelector(".nav-group-pinned a")?.getAttribute("aria-label")).toBe("Project 0"));
    expect([...document.querySelectorAll(".nav-group-projects a")].map((link) => link.getAttribute("aria-label"))).not.toContain("Project 0");
    expect(window.location.hash).toBe("#/projects");
  });

  it("expands a Project tree into selected Agent links and keeps the per-Project menu to three actions", async () => {
    const tree = project({ project_id: "tree", name: "Tree Project", agents: [{ agent_id: "agent-tree", slug: "tree-agent", name: "Tree Agent", description: "", pinned: false, source_path: "agents/tree/agent.vagent.yaml", source_file_hash: "tree-hash" }], agent_count: 1 });
    const user = userEvent.setup();
    const api = apiFor([tree]);
    api.updateAgent.mockResolvedValue(tree);
    render(<DesktopApp api={api} />);

    await user.click(await screen.findByRole("button", { name: "Expand Project: Tree Project" }));
    const agentLink = screen.getByRole("link", { name: "Tree Agent" });
    expect(agentLink).toHaveAttribute("href", projectRoutePaths.agentDesign("tree", "agent-tree"));
    const projectRow = document.querySelector(`.nav-group-projects .sidebar-nav-item-row`);
    const projectLink = projectRow?.querySelector(`a[href="${projectRoutePaths.project("tree")}"]`);
    expect(projectLink).toHaveClass("sidebar-nav-link");
    expect(projectLink).not.toHaveAttribute("aria-current");
    expect(projectRow?.querySelector(`button[aria-label="Add Agent: Tree Project"]`)).not.toBeNull();
    expect(projectRow?.querySelector(".sidebar-nav-item-action")).not.toBeNull();
    expect(projectRow?.querySelector(".sidebar-nav-item-leading-action")).not.toBeNull();
    expect(projectRow?.parentElement?.querySelector(":scope > .sidebar-nav-children")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Agent actions: Tree Agent" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add child Agent: Tree Agent" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Agent actions: Tree Agent" }));
    expect(screen.getByRole("menu", { name: "Agent actions: Tree Agent" })).toBeInTheDocument();
    expect(screen.getAllByRole("menuitem")).toHaveLength(3);
    expect(screen.getByRole("menuitem", { name: "Pin" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Delete" })).toBeInTheDocument();
    await user.click(screen.getByRole("menuitem", { name: "Pin" }));
    await waitFor(() => expect(api.updateAgent).toHaveBeenCalledWith("tree", "agent-tree", { pinned: true }));
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Project actions: Tree Project" }));
    expect(document.querySelector(".sidebar-project-menu")?.parentElement).toBe(document.body);
    expect(document.querySelector(".sidebar-project-menu")).not.toHaveClass("agent-add-chooser");
    expect(screen.getAllByRole("menuitem")).toHaveLength(3);
    expect(screen.getByRole("menuitem", { name: "Pin Project" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Delete" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("opens Add Agent without navigation, submits blank Agent creation, and retains edit/delete confirmation", async () => {
    const editable = project({ project_id: "editable", name: "Before edit" });
    const api = apiFor([editable]);
    api.updateProject.mockResolvedValue(project({ project_id: "editable", name: "Allocated edit", description: "Updated" }));
    api.deleteProject.mockResolvedValue({ schema_version: "1.0", project_id: "editable", disposition: "trashed", removed_at: "2026-08-28T00:00:00Z" });
    api.getProject.mockResolvedValue(editable);
    const user = userEvent.setup();
    window.location.hash = projectRoutePaths.project("editable");
    render(<DesktopApp api={api} />);

    await user.click(await screen.findByRole("button", { name: "Collapse Project: Before edit" }));
    await user.click(screen.getByRole("button", { name: "Add Agent: Before edit" }));
    expect(window.location.hash).toBe(projectRoutePaths.project("editable"));
    expect(screen.getAllByRole("menuitem")).toHaveLength(3);
    expect(screen.getByRole("menuitem", { name: /Create blank Agent/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Import Agent from template/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Import Agent file/ })).toBeInTheDocument();
    await user.click(screen.getByRole("menuitem", { name: /Create blank Agent/ }));
    await user.type(screen.getByRole("textbox", { name: "Agent name (optional)" }), "Requested Agent");
    await user.type(screen.getByRole("textbox", { name: "Description (optional)" }), "Created here");
    await user.click(screen.getByRole("button", { name: "Create Agent" }));
    await waitFor(() => expect(api.createAgent).toHaveBeenCalledWith("editable", { mode: "blank", name: "Requested Agent", description: "Created here" }));
    expect(window.location.hash).toBe(projectRoutePaths.project("editable"));
    expect(screen.queryByRole("dialog", { name: "Create blank Agent" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Collapse Project: Before edit" })).toHaveAttribute("aria-expanded", "true");
    await user.click(screen.getByRole("button", { name: "Project actions: Before edit" }));
    await user.click(screen.getByRole("menuitem", { name: "Edit" }));
    await user.clear(screen.getByRole("textbox", { name: "Project name" }));
    await user.type(screen.getByRole("textbox", { name: "Project name" }), "Requested name");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.updateProject).toHaveBeenCalledWith("editable", { name: "Requested name", description: "" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Server-assigned name: Allocated edit");
    expect(await screen.findByRole("link", { name: "Allocated edit" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Done" }));
    await user.click(screen.getByRole("button", { name: "Project actions: Allocated edit" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    expect(api.deleteProject).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Delete Project" }));
    await waitFor(() => expect(api.deleteProject).toHaveBeenCalledWith("editable"));
    await waitFor(() => expect(window.location.hash).toBe("#/projects"));
    expect(screen.queryByRole("link", { name: "Allocated edit" })).not.toBeInTheDocument();
  });

  it("edits an Agent draft and moves it to recoverable trash from the same menu", async () => {
    const agent = { agent_id: "agent-edit", slug: "draft-agent", name: "Draft Agent", description: "Before", pinned: false, source_path: "agents/draft-agent/agent.vagent.yaml", source_file_hash: "draft-hash" };
    const editable = project({ project_id: "agent-edit-project", name: "Agent Project", agents: [agent], agent_count: 1 });
    const renamed = { ...agent, name: "Renamed Agent", description: "After" };
    const afterDelete = project({ project_id: editable.project_id, name: editable.name, agents: [], agent_count: 0 });
    const api = apiFor([editable]);
    api.getDraft.mockResolvedValue({ schema_version: "1.0", draft_id: "draft-edit", revision: 3, etag: "etag-edit", source_file_hash: "draft-hash", source: { schema_version: "1.0", agentspec_version: "26.1", component_type: "Flow", agent_id: agent.agent_id, slug: agent.slug, name: agent.name, description: agent.description, inputs: {}, outputs: {}, nodes: [], transitions: [], extensions: { veyra: { runtime_profile: "guarded-local", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: true, checks: [] } } }, ui: { positions: {} }, lock: {} } });
    api.getProject.mockResolvedValue(project({ ...editable, agents: [renamed], agent_count: 1 }));
    api.deleteAgent.mockResolvedValue({ schema_version: "1.0", project_id: editable.project_id, agent_id: agent.agent_id, disposition: "trashed", removed_at: "2026-08-28T00:00:00Z", project: afterDelete });
    const user = userEvent.setup();
    window.location.hash = projectRoutePaths.project(editable.project_id);
    render(<DesktopApp api={api} />);

    await user.click(await screen.findByRole("button", { name: "Agent actions: Draft Agent" }));
    await user.click(screen.getByRole("menuitem", { name: "Edit" }));
    await user.clear(await screen.findByRole("textbox", { name: "Agent name" }));
    await user.type(screen.getByRole("textbox", { name: "Agent name" }), "Renamed Agent");
    await user.clear(screen.getByRole("textbox", { name: "Description" }));
    await user.type(screen.getByRole("textbox", { name: "Description" }), "After");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.saveDraft).toHaveBeenCalledWith(editable.project_id, agent.agent_id, expect.objectContaining({ expected_revision: 3, source: expect.objectContaining({ name: "Renamed Agent", description: "After" }) }), { etag: "etag-edit" }));
    expect(screen.queryByRole("dialog", { name: "Edit Agent" })).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Agent actions: Renamed Agent" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Agent actions: Renamed Agent" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    expect(screen.getByRole("dialog", { name: "Delete Agent?" })).toBeInTheDocument();
    expect(api.deleteAgent).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Delete Agent" }));
    await waitFor(() => expect(api.deleteAgent).toHaveBeenCalledWith(editable.project_id, agent.agent_id));
    expect(screen.queryByRole("button", { name: "Agent actions: Renamed Agent" })).not.toBeInTheDocument();
  });

  it("submits template and file Agent imports with their real request shapes", async () => {
    const source = project({ project_id: "imports", name: "Import Project" });
    const api = apiFor([source]);
    api.getProject.mockResolvedValue(source);
    const user = userEvent.setup();
    render(<DesktopApp api={api} />);

    await user.click(await screen.findByRole("button", { name: "Add Agent: Import Project" }));
    await user.click(screen.getByRole("menuitem", { name: /Import Agent from template/ }));
    await screen.findByRole("option", { name: "Review Agent" });
    await user.type(screen.getByRole("textbox", { name: "Agent name (optional)" }), "Template override");
    await user.click(screen.getByRole("button", { name: "Import Agent" }));
    await waitFor(() => expect(api.createAgent).toHaveBeenCalledWith("imports", { mode: "template", template_id: "review", name: "Template override" }));
    expect(window.location.hash).toBe("#/projects");

    await user.click(screen.getByRole("button", { name: "Add Agent: Import Project" }));
    await user.click(screen.getByRole("menuitem", { name: /Import Agent file/ }));
    const file = new File(["schema_version: '1.0'"], "review.vagent.yaml", { type: "application/x-yaml" });
    await user.upload(screen.getByLabelText("Choose Agent file"), file);
    await user.type(screen.getByRole("textbox", { name: "Description (optional)" }), "Imported file");
    await user.click(screen.getByRole("button", { name: "Import Agent" }));
    await waitFor(() => expect(api.importAgent).toHaveBeenCalledWith("imports", { file, description: "Imported file" }));
    expect(window.location.hash).toBe("#/projects");
  });

  it("does not render an empty Agent children container when an empty Project is expanded", async () => {
    const user = userEvent.setup();
    render(<DesktopApp api={apiFor([project({ project_id: "empty", name: "Empty Project" })])} />);
    await user.click(await screen.findByRole("button", { name: "Expand Project: Empty Project" }));
    expect(document.querySelector(".nav-group-projects .sidebar-nav-children")).toBeNull();
  });

  it("renders title-only root headers and linked nested breadcrumbs at 320px", async () => {
    setViewport(true);
    const nested = project({ project_id: "crumb", name: "Breadcrumb Project", agents: [{ agent_id: "crumb-agent", slug: "breadcrumb-agent", name: "Breadcrumb Agent", description: "", pinned: false, source_path: "agents/breadcrumb/agent.vagent.yaml", source_file_hash: "crumb-hash" }], agent_count: 1 });
    const api = apiFor([nested]);
    api.getProject.mockResolvedValue(nested);
    window.location.hash = projectRoutePaths.project("crumb");
    render(<DesktopApp api={api} />);

    expect(await screen.findByLabelText("Breadcrumb")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("href", "#/projects");
    expect(screen.getByText("Breadcrumb Project", { selector: "[aria-current=page]" })).toBeInTheDocument();
    cleanup();
    window.location.hash = "#/projects";
    render(<DesktopApp api={apiFor()} />);
    expect(await screen.findByRole("heading", { name: "New chat", level: 1 })).toBeInTheDocument();
    expect(screen.queryByLabelText("Breadcrumb")).not.toBeInTheDocument();
    const menu = screen.getByRole("button", { name: "Open navigation" });
    await userEvent.click(menu);
    expect(screen.getAllByRole("button", { name: "Close navigation" })).toHaveLength(2);
  });

  it("uses Agent-context navigation in English while preserving the real Project tree", async () => {
    const scoped = project({
      project_id: "agent-project",
      name: "Agent Project",
      agents: [{ agent_id: "agent-one", slug: "review-agent", name: "Review Agent", description: "", pinned: false, source_path: "agents/review-agent/agent.vagent.yaml", source_file_hash: "agent-hash" }],
    });
    window.location.hash = projectRoutePaths.agent(scoped.project_id, "agent-one");
    render(<DesktopApp api={apiFor([scoped])} />);

    const contextLinks = await screen.findAllByRole("link", { name: /^(New chat|Orchestration|Data analysis)$/ });
    expect(contextLinks.map((link) => link.textContent)).toEqual(["New chat", "Orchestration", "Data analysis"]);
    expect(screen.getByRole("link", { name: "New chat" })).toHaveAttribute("href", projectRoutePaths.agent("agent-project", "agent-one"));
    expect(screen.getByRole("link", { name: "Orchestration" })).toHaveAttribute("href", projectRoutePaths.agentDesign("agent-project", "agent-one"));
    expect(screen.getByRole("link", { name: "Data analysis" })).toHaveAttribute("href", projectRoutePaths.agentAnalysis("agent-project", "agent-one"));
    expect(screen.getByRole("link", { name: "New chat" })).toHaveAttribute("aria-current", "page");
    const agentTreeLink = document.querySelector(".nav-group-projects a[href=\"" + projectRoutePaths.agentDesign("agent-project", "agent-one") + "\"]");
    const projectTreeLink = document.querySelector(".nav-group-projects a[href=\"" + projectRoutePaths.project("agent-project") + "\"]");
    expect(agentTreeLink).toHaveAttribute("aria-current", "page");
    expect(projectTreeLink).not.toHaveAttribute("aria-current");
    expect(document.querySelector(".nav-group-recent")).toBeInTheDocument();
    expect(screen.getByText("No recent conversations or runs yet.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("link", { name: "Data analysis" }));
    expect(await screen.findByRole("heading", { name: "Data analysis", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Data analysis" })).toHaveAttribute("aria-current", "page");
  });

  it("localizes Agent-context navigation and analysis empty state in Chinese", async () => {
    window.localStorage.setItem("veyra.language", "zh");
    const scoped = project({
      project_id: "agent-project-zh",
      name: "中文项目",
      agents: [{ agent_id: "agent-zh", slug: "审阅 Agent", name: "审阅 Agent", description: "", pinned: false, source_path: "agents/reviewer/agent.vagent.yaml", source_file_hash: "agent-hash" }],
    });
    window.location.hash = projectRoutePaths.agentAnalysis(scoped.project_id, "agent-zh");
    render(<DesktopApp api={apiFor([scoped])} />);

    const contextLinks = await screen.findAllByRole("link", { name: /^(新聊天|编排|数据分析)$/ });
    expect(contextLinks.map((link) => link.textContent)).toEqual(["新聊天", "编排", "数据分析"]);
    expect(screen.getByRole("link", { name: "数据分析" })).toHaveAttribute("href", projectRoutePaths.agentAnalysis("agent-project-zh", "agent-zh"));
    expect(screen.getByRole("link", { name: "数据分析" })).toHaveAttribute("aria-current", "page");
    const agentTreeLink = document.querySelector(".nav-group-projects a[href=\"" + projectRoutePaths.agentDesign("agent-project-zh", "agent-zh") + "\"]");
    const projectTreeLink = document.querySelector(".nav-group-projects a[href=\"" + projectRoutePaths.project("agent-project-zh") + "\"]");
    expect(agentTreeLink).toHaveAttribute("aria-current", "page");
    expect(projectTreeLink).not.toHaveAttribute("aria-current");
    expect(screen.getByText("暂无最近聊天或运行记录。")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "数据分析", level: 2 })).toBeInTheDocument();
    expect(screen.getByText("暂无可分析的运行记录")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "主页" })).toHaveAttribute("href", "#/projects");
  });

  it("preserves account controls, theme choices, and responsive sidebar focus behavior", async () => {
    const user = userEvent.setup();
    const api = apiFor();
    render(<DesktopApp api={api} />);
    await user.click(screen.getByRole("button", { name: "Open account menu" }));
    expect(screen.getByRole("menuitem", { name: "Sign in or register" })).toHaveAttribute("href", "#/account");
    expect(screen.getByRole("menuitem", { name: "Settings" })).toHaveAttribute("href", "#/settings");

    window.localStorage.setItem("veyra.theme", "dark");
    cleanup();
    render(<DesktopApp api={api} />);
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));
    await user.click(screen.getByRole("button", { name: "Switch to light mode" }));
    await waitFor(() => expect(window.localStorage.getItem("veyra.theme")).toBe("light"));

    cleanup();
    setViewport(true);
    render(<DesktopApp api={api} />);
    const menu = screen.getByRole("button", { name: "Open navigation" });
    await user.click(menu);
    await user.keyboard("{Escape}");
    expect(menu).toHaveFocus();
  });

  it("keeps the New chat surface and shell controls bilingual", async () => {
    const user = userEvent.setup();
    render(<DesktopApp api={apiFor()} />);
    expect(await screen.findByText("Open a Project first, then use Factory to create an Agent.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Switch to Chinese" }));
    expect(await screen.findByText("请先进入项目，再通过 Factory 创建 Agent。")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "新聊天" })).toHaveAttribute("href", "#/chat");
    expect(screen.getByRole("link", { name: "运行工作台" })).toHaveAttribute("href", "#/monitor");
    expect(screen.getByRole("link", { name: "资源库" })).toHaveAttribute("href", "#/components");
    expect(screen.getByRole("link", { name: "知识库" })).toHaveAttribute("href", "#/files");
  });

  it("renders the New chat placeholder instead of a generic route error", async () => {
    window.location.hash = "#/chat";
    render(<DesktopApp api={apiFor()} />);
    expect(await screen.findByRole("heading", { name: "New chat", level: 2 })).toBeInTheDocument();
    expect(screen.getByText("Open a Project first, then use Factory to create an Agent.")).toBeInTheDocument();
    expect(screen.queryByText("Route not found")).not.toBeInTheDocument();
  });

  it.each([
    ["#/login", "Welcome back"],
    ["#/register", "Verify your email first"],
    ["#/forgot-password", "Reset your password"],
  ] as const)("renders the connected auth route %s inside Desktop", async (hash, heading) => {
    window.location.hash = hash;
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      return url.endsWith("/account/me") ? jsonResponse(401, { detail: "authentication_required" }) : jsonResponse(404, { detail: "not_found" });
    });
    render(<DesktopApp api={apiFor()} communityApi={accountApi(fetcher)} />);

    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Veyra" })).toHaveAttribute("href", "#/community");
    expect(screen.getByText("/ Agent Platform", { selector: "small" })).toBeInTheDocument();
    expect(screen.queryByText("Veyra Community")).not.toBeInTheDocument();
    if (hash === "#/login") expect(screen.getByText("Sign in to Veyra with your email and password.")).toBeInTheDocument();
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith("/community-api/api/v1/account/me", expect.objectContaining({ credentials: "include" })));
  });

  it("restores a Community session, drives the account menu, and completes avatar lifecycle", async () => {
    window.location.hash = "#/account";
    let currentAccount: CommunityAccount = connectedAccount;
    const requests: Array<{ url: string; method: string; body?: BodyInit | null }> = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = (init?.method ?? "GET").toUpperCase();
      requests.push({ url, method, body: init?.body });
      if (url.endsWith("/account/me")) return jsonResponse(200, { schema_version: "community.account.v1", account: currentAccount });
      if (url.endsWith("/account/sessions")) return jsonResponse(200, { schema_version: "community.account.v1", sessions: [connectedSession] });
      if (url.endsWith("/account/avatar") && method === "POST") {
        const body = init?.body as FormData;
        expect(body.get("avatar")).toBeInstanceOf(File);
        currentAccount = { ...currentAccount, avatar_url: "/api/v1/avatars/account-desktop" };
        return jsonResponse(200, { schema_version: "community.account.v1", account: currentAccount });
      }
      if (url.endsWith("/account/avatar") && method === "DELETE") {
        currentAccount = { ...currentAccount, avatar_url: null };
        return new Response(null, { status: 204 });
      }
      if (url.endsWith("/auth/logout") && method === "POST") return new Response(null, { status: 204 });
      return jsonResponse(404, { detail: "not_found" });
    });
    const user = userEvent.setup();
    render(<DesktopApp api={apiFor()} communityApi={accountApi(fetcher)} />);

    expect(await screen.findByDisplayValue("alice@example.com")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open account menu" }));
    expect(screen.getByRole("menuitem", { name: "Account" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Sign out" })).toBeInTheDocument();

    const avatarInput = screen.getByLabelText("Choose avatar");
    expect(avatarInput).toHaveAttribute("accept", "image/png,image/jpeg,image/webp");
    const file = new File(["png bytes"], "avatar.png", { type: "image/png" });
    await user.upload(avatarInput, file);
    await user.click(screen.getAllByRole("button", { name: "Save changes" })[0]!);
    expect(await screen.findByText("Avatar updated.")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Avatar preview" })).toHaveAttribute("src", "/community-api/api/v1/avatars/account-desktop");
    expect(requests.some((request) => request.url.endsWith("/account/avatar") && request.method === "POST")).toBe(true);

    await user.click(screen.getByRole("button", { name: "Remove avatar" }));
    expect(await screen.findByText("Avatar removed.")).toBeInTheDocument();
    expect(requests.some((request) => request.url.endsWith("/account/avatar") && request.method === "DELETE")).toBe(true);

    await user.click(screen.getByRole("button", { name: "Open account menu" }));
    await user.click(screen.getByRole("menuitem", { name: "Sign out" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Open account menu" })).toHaveAttribute("title", "Local workspace"));
    await user.click(screen.getByRole("button", { name: "Open account menu" }));
    expect(screen.getByRole("menuitem", { name: "Sign in or register" })).toBeInTheDocument();
  });
});

describe("shared ApplicationShell account behavior", () => {
  it("invokes sign out only for an authenticated account", async () => {
    const user = userEvent.setup();
    const onSignOut = vi.fn();
    render(
      <ThemeProvider>
        <ApplicationShell
          brand={{ name: "Veyra", subtitle: "Agent Platform" }}
          navigation={[{ label: "Build", items: [{ href: "#/projects", label: "Projects", icon: FolderKanban }] }]}
          activeHref="#/projects"
          eyebrow="Workspace"
          title="Projects"
          account={{ displayName: "Ada", authenticated: true, accountHref: "#/account", settingsHref: "#/settings", onSignOut }}
        >
          <div>Workspace content</div>
        </ApplicationShell>
      </ThemeProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Open account menu" }));
    expect(screen.getByRole("menuitem", { name: "Account" })).toHaveAttribute("href", "#/account");
    await user.click(screen.getByRole("menuitem", { name: "Sign out" }));
    expect(onSignOut).toHaveBeenCalledOnce();
  });
});

describe("desktop route parser", () => {
  it("maps Community avatar paths through the configured API proxy", () => {
    expect(normalizeCommunityAvatarUrl("/api/v1/avatars/account-desktop?v=2", "/community-api/api/v1")).toBe("/community-api/api/v1/avatars/account-desktop?v=2");
    expect(normalizeCommunityAvatarUrl("/api/v1/avatars/account-desktop", "/api/v1")).toBe("/api/v1/avatars/account-desktop");
  });

  it("covers the typed Project and fixed-feature route matrix", () => {
    expect(parseDesktopRoute("#/chat").kind).toBe("chat");
    expect(parseDesktopRoute("#/projects").kind).toBe("projects");
    expect(parseDesktopRoute(projectRoutePaths.project("p")).kind).toBe("project");
    expect(parseDesktopRoute(projectRoutePaths.agents("p")).kind).toBe("project-agents");
    expect(parseDesktopRoute(projectRoutePaths.agent("p", "a")).kind).toBe("agent-detail");
    expect(parseDesktopRoute(projectRoutePaths.agentVersion("p", "a", "v1")).kind).toBe("agent-version");
    expect(parseDesktopRoute(projectRoutePaths.agentAnalysis("p", "a")).kind).toBe("agent-analysis");
    expect(parseDesktopRoute("#/components").kind).toBe("components");
    expect(parseDesktopRoute("#/files").kind).toBe("files");
    expect(parseDesktopRoute("#/runs").kind).toBe("runs");
    expect(parseDesktopRoute("#/monitor").kind).toBe("monitor");
    expect(parseDesktopRoute("#/community").kind).toBe("community");
    expect(parseDesktopRoute("#/login").kind).toBe("login");
    expect(parseDesktopRoute("#/register").kind).toBe("register");
    expect(parseDesktopRoute("#/forgot-password").kind).toBe("forgot-password");
    expect(parseDesktopRoute("#/nowhere").kind).toBe("not-found");
  });
});
