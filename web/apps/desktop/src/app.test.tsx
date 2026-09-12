import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FolderKanban } from "lucide-react";
import { desktopLoginHash, parseDesktopRoute, projectRoutePaths, type CommunityAccount, type ProjectSummaryResponse, type SaveDraftRequest, type SaveDraftResponse } from "@veyra/api-contracts";
import { createCommunityApi, errorCopy, normalizeCommunityAvatarUrl } from "@veyra/connected-account";
import { ApplicationShell, ThemeProvider } from "@veyra/ui";
import { LocalApiClientError, type LocalProjectApi } from "./api/local-client";
import { DesktopApp } from "./app";
import { desktopHeader } from "./desktop-header";

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
  selectArchive: ReturnType<typeof vi.fn>;
  importProjectFromPath: ReturnType<typeof vi.fn>;
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
  importProject: ReturnType<typeof vi.fn>;
  revealProject: ReturnType<typeof vi.fn>;
  exportProject: ReturnType<typeof vi.fn>;
  listProjectFiles: ReturnType<typeof vi.fn>;
  listAgentRuns: ReturnType<typeof vi.fn>;
  createWorkflow: ReturnType<typeof vi.fn>;
  deleteWorkflow: ReturnType<typeof vi.fn>;
  getWorkflowDraft: ReturnType<typeof vi.fn>;
  saveWorkflowDraft: ReturnType<typeof vi.fn>;
  createKnowledge: ReturnType<typeof vi.fn>;
  updateKnowledge: ReturnType<typeof vi.fn>;
  deleteKnowledge: ReturnType<typeof vi.fn>;
  listResources: ReturnType<typeof vi.fn>;
} {
  const getProject = vi.fn().mockImplementation(async (projectId: string) => project({ project_id: projectId, name: projectId }));
  return {
    listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects }),
    createProject: vi.fn().mockResolvedValue(project({ project_id: "created-project", name: "Created Project", root_path: "/tmp/created-project" })),
    openProject: vi.fn().mockResolvedValue(project({ project_id: "opened-project", name: "Opened Project", root_path: "/tmp/opened-project" })),
    selectDirectory: vi.fn().mockResolvedValue({ schema_version: "1.0", status: "selected", root_path: "/tmp/selected-folder" }),
    selectArchive: vi.fn().mockResolvedValue({ schema_version: "1.0", status: "cancelled", path: null }),
    importProjectFromPath: vi.fn().mockResolvedValue(project({ project_id: "imported-project", name: "Imported Project", root_path: "/tmp/imported-project" })),
    getProject,
    updateProject: vi.fn().mockImplementation(async (projectId: string, input: { pinned?: boolean; name?: string; description?: string }) => project({ project_id: projectId, name: input.name ?? projectId, description: input.description ?? "", pinned: input.pinned ?? false, pinned_at: input.pinned ? "2026-08-28T00:00:00Z" : null })),
    deleteProject: vi.fn().mockResolvedValue({ schema_version: "1.0", project_id: "project-1", disposition: "trashed", removed_at: "2026-08-28T00:00:00Z" }),
    updateAgent: vi.fn().mockImplementation(async (projectId: string, agentId: string) => project({ project_id: projectId, agents: [{ agent_id: agentId, slug: "agent", name: "Agent", description: "", pinned: true, source_path: "agents/agent/agent.vagent.yaml", source_file_hash: "agent-hash" }], default_agent_id: agentId, agent_count: 1 })),
    deleteAgent: vi.fn().mockResolvedValue({ schema_version: "1.0", project_id: "project-1", agent_id: "agent-1", disposition: "trashed", removed_at: "2026-08-28T00:00:00Z", project: project() }),
    listAgentTemplates: vi.fn().mockResolvedValue({ schema_version: "1.0", templates: [{ template_id: "review", name: "Review Agent", description: "Reviews a bounded scope.", default_slug: "review-agent" }] }),
    createAgent: vi.fn().mockResolvedValue({ schema_version: "1.0", project_id: "project-1", agent_id: "created-agent", slug: "created-agent", name: "Created Agent", description: "", source_path: "agents/created-agent/agent.vagent.yaml", source_file_hash: "created-hash" }),
    importAgent: vi.fn().mockResolvedValue({ schema_version: "1.0", project_id: "project-1", agent_id: "imported-agent", slug: "imported-agent", name: "Imported Agent", description: "", source_path: "agents/imported-agent/agent.vagent.yaml", source_file_hash: "imported-hash" }),
    importProject: vi.fn().mockResolvedValue(project({ project_id: "imported-project", name: "Imported Project", root_path: "/tmp/imported-project" })),
    revealProject: vi.fn().mockResolvedValue({ schema_version: "1.0", status: "revealed", root_path: "/tmp/project-1" }),
    exportProject: vi.fn().mockResolvedValue(new Blob(["zip"], { type: "application/zip" })),
    listProjectFiles: vi.fn().mockResolvedValue({ schema_version: "1.0", project_id: "project-1", files: [] }),
    listAgentRuns: vi.fn().mockResolvedValue({ schema_version: "1.0", runs: [] }),
    createWorkflow: vi.fn().mockResolvedValue({ schema_version: "1.0", project_id: "project-1", workflow_id: "created-workflow", slug: "created-workflow", name: "Created Workflow", description: "", source_path: "workflows/created-workflow/workflow.vworkflow.yaml", source_file_hash: "wf-created" }),
    deleteWorkflow: vi.fn().mockResolvedValue({ schema_version: "1.0", project_id: "project-1", workflow_id: "created-workflow", disposition: "trashed", removed_at: "2026-08-28T00:00:00Z", project: project() }),
    getWorkflowDraft: vi.fn().mockResolvedValue({ schema_version: "1.0", draft_id: "wf-draft-1", revision: 1, etag: "wf-etag-1", source_file_hash: "wf-hash", source: { schema_version: "1.0", component_type: "Workflow", workflow_id: "wf-1", slug: "flow", name: "Flow", description: "", inputs: {}, outputs: {}, nodes: [], transitions: [], extensions: { veyra: { permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } }, ui: { positions: {} }, lock: {} } }),
    saveWorkflowDraft: vi.fn().mockImplementation(async (_projectId: string, _workflowId: string, input: { expected_revision: number; source: { name: string; description: string } }) => ({ schema_version: "1.0", revision: input.expected_revision + 1, etag: "wf-etag-2", source: input.source })),
    createKnowledge: vi.fn().mockResolvedValue({ schema_version: "1.0", project_id: "project-1", knowledge_id: "created-knowledge", slug: "created-knowledge", name: "Created Knowledge", description: "", source_path: "knowledge/created-knowledge/resource.yaml", source_file_hash: "kn-created", text: "" }),
    updateKnowledge: vi.fn().mockImplementation(async (projectId: string, knowledgeId: string, input: { name?: string; description?: string }) => ({ schema_version: "1.0", project_id: projectId, knowledge_id: knowledgeId, slug: "knowledge", name: input.name ?? "Knowledge", description: input.description ?? "", source_path: "knowledge/knowledge/resource.yaml", source_file_hash: "kn-hash", text: "" })),
    deleteKnowledge: vi.fn().mockResolvedValue({ schema_version: "1.0", project_id: "project-1", knowledge_id: "created-knowledge", disposition: "trashed", removed_at: "2026-08-28T00:00:00Z", project: project() }),
    listResources: vi.fn().mockResolvedValue({ schema_version: "1.0", resources: [], kinds: [] }),
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

function signedInFetcher(handler?: (url: string, method: string, init?: RequestInit) => Response | undefined) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = (init?.method ?? "GET").toUpperCase();
    const handled = handler?.(url, method, init);
    if (handled) return handled;
    if (url.endsWith("/account/me")) return jsonResponse(200, { schema_version: "community.account.v1", account: connectedAccount });
    if (url.endsWith("/auth/logout") && method === "POST") return new Response(null, { status: 204 });
    return jsonResponse(404, { detail: "not_found" });
  });
}

async function renderApp(api: LocalProjectApi, communityApi?: ReturnType<typeof accountApi>) {
  document.cookie = "veyra-csrf=test-csrf; path=/";
  const view = render(<DesktopApp api={api} communityApi={communityApi ?? accountApi(signedInFetcher())} />);
  await waitFor(() => expect(document.querySelector(".app-shell")).not.toBeNull());
  return view;
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
  document.cookie = "veyra-csrf=; Max-Age=0; path=/";
});

describe("desktop Project workspace", () => {
  it("renders the normal New chat surface at #/projects and keeps a compact Project section without Recent", async () => {
    const first = project({ project_id: "p-one", name: "Alpha Project" });
    const second = project({ project_id: "p-two", name: "Beta Project", root_path: "/Users/test/Projects/project-two", agents: [{ agent_id: "agent-1", slug: "reviewer", name: "Reviewer", description: "", pinned: false, source_path: "agents/reviewer/agent.vagent.yaml", source_file_hash: "fedcba9876543210" }], agent_count: 1 });
    const api = apiFor([first, second]);
    api.getProject.mockImplementation(async (projectId: string) => [first, second].find((item) => item.project_id === projectId) ?? first);
    await renderApp(api);

    expect(screen.getByRole("link", { name: "New chat" })).toHaveAttribute("href", "#/chat");
    expect(await screen.findByRole("heading", { name: "What do you want to achieve in a new project?", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Run workspace" })).toHaveAttribute("href", "#/monitor");
    expect(screen.getByRole("link", { name: "Resource catalog" })).toHaveAttribute("href", "#/resources");
    expect(screen.getByRole("link", { name: "Knowledge base" })).toHaveAttribute("href", "#/files");
    expect(screen.getByRole("link", { name: "Community" })).toHaveAttribute("href", "#/community");
    expect(screen.getByRole("link", { name: "History" })).toHaveAttribute("href", "#/runs");
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
    await renderApp(api);

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
    expect(await screen.findByRole("heading", { name: "What do you want to achieve in a new project?", level: 2 })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByText("refresh unavailable")).not.toBeInTheDocument();
  });

  it("opens an existing Project from its distinct FolderOpen action", async () => {
    const api = apiFor();
    const opened = project({ project_id: "opened-project", name: "Opened Project", root_path: "/tmp/opened-project" });
    api.openProject.mockResolvedValue(opened);
    api.selectDirectory.mockResolvedValue({ schema_version: "1.0", status: "selected", root_path: "/tmp/opened-project" });
    const user = userEvent.setup();
    await renderApp(api);

    await user.click(await screen.findByRole("button", { name: "Open existing project" }));
    expect(screen.getByText("Choose an existing Veyra Project folder on this computer.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Select folder" }));
    await user.click(screen.getByRole("button", { name: "Open project" }));

    await waitFor(() => expect(api.openProject).toHaveBeenCalledWith({ root_path: "/tmp/opened-project" }));
    expect(window.location.hash).toBe("#/projects");
  });

  it("imports a Project archive from the same open-existing dialog", async () => {
    const api = apiFor();
    const imported = project({ project_id: "imported-project", name: "Imported Project", root_path: "/tmp/imported-project" });
    api.selectArchive.mockResolvedValue({ schema_version: "1.0", status: "selected", path: "/tmp/team.vproject.zip" });
    api.importProjectFromPath.mockResolvedValue(imported);
    const user = userEvent.setup();
    await renderApp(api);

    await user.click(await screen.findByRole("button", { name: "Open existing project" }));
    expect(screen.getByText("Choose a .vproject.zip archive on this computer.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Import archive" }));
    await user.click(await screen.findByRole("button", { name: "Import project" }));

    await waitFor(() => expect(api.importProjectFromPath).toHaveBeenCalledWith({ path: "/tmp/team.vproject.zip" }));
    expect(api.selectArchive).toHaveBeenCalled();
    expect(api.importProject).not.toHaveBeenCalled();
  });

  it("localizes a create failure without rendering a folder path on a Chinese Desktop", async () => {
    window.localStorage.setItem("veyra.language", "zh");
    const api = apiFor();
    api.createProject.mockRejectedValue(new LocalApiClientError("/Users/test/Downloads/test unavailable", { status: 503, code: "project_unavailable" }));
    const user = userEvent.setup();
    await renderApp(api);

    await user.click(await screen.findByRole("button", { name: "新建项目" }));
    await user.type(screen.getByRole("textbox", { name: "项目名称" }), "test");
    await user.click(screen.getByRole("button", { name: "创建" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("创建项目失败，请稍后重试。");
    expect(screen.queryByText("/Users/test/Downloads/test unavailable")).not.toBeInTheDocument();
  });

  it("localizes opening a non-Project folder without leaking the sidecar message", async () => {
    window.localStorage.setItem("veyra.language", "zh");
    const api = apiFor();
    api.selectDirectory.mockResolvedValue({ schema_version: "1.0", status: "selected", root_path: "/tmp/assets" });
    api.openProject.mockRejectedValue(new LocalApiClientError("required Project path is absent", { status: 422, code: "not_a_project" }));
    const user = userEvent.setup();
    await renderApp(api);

    await user.click(await screen.findByRole("button", { name: "打开已有项目" }));
    await user.click(screen.getByRole("button", { name: "选择文件夹" }));
    await user.click(screen.getByRole("button", { name: "打开项目" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("所选文件夹不是 Veyra 项目。请选择项目根目录，不要选其中的子文件夹。");
    expect(screen.queryByText("required Project path is absent")).not.toBeInTheDocument();
  });

  it("keeps open-existing picker cancellation and errors recoverable", async () => {
    const api = apiFor();
    api.selectDirectory.mockResolvedValueOnce({ schema_version: "1.0", status: "cancelled", root_path: null }).mockRejectedValueOnce(new LocalApiClientError("native directory picker failed", { status: 500, code: "directory_picker_failed" }));
    const user = userEvent.setup();
    await renderApp(api);
    await user.click(await screen.findByRole("button", { name: "Open existing project" }));
    await user.click(screen.getByRole("button", { name: "Select folder" }));
    expect(screen.queryByText(/^Selected:/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Select folder" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The folder picker could not be opened. Allow disk access and try again.");
    expect(screen.queryByText("native directory picker failed")).not.toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("explains an archive picker failure without leaking the sidecar exception", async () => {
    const api = apiFor();
    api.selectArchive.mockRejectedValue(new LocalApiClientError("native directory picker failed", { status: 500, code: "directory_picker_failed" }));
    const user = userEvent.setup();
    await renderApp(api);
    await user.click(await screen.findByRole("button", { name: "Open existing project" }));
    await user.click(screen.getByRole("button", { name: "Import archive" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The archive picker could not be opened. Choose a .zip or .vproject.zip file, and allow disk access.");
    expect(screen.queryByText("native directory picker failed")).not.toBeInTheDocument();
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
    window.location.hash = projectRoutePaths.agents("p-detail");
    await renderApp(api);

    expect(await screen.findByRole("heading", { name: "Evidence Project", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "2 Agents" })).toBeInTheDocument();
    expect(screen.getAllByText("Reviewer").length).toBeGreaterThanOrEqual(1);
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
    await renderApp(api);

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

  it("expands a Project tree into selected Agent links and keeps the per-Project menu to four actions", async () => {
    const tree = project({ project_id: "tree", name: "Tree Project", agents: [{ agent_id: "agent-tree", slug: "tree-agent", name: "Tree Agent", description: "", pinned: false, source_path: "agents/tree/agent.vagent.yaml", source_file_hash: "tree-hash" }], agent_count: 1 });
    const user = userEvent.setup();
    const api = apiFor([tree]);
    api.updateAgent.mockResolvedValue(tree);
    await renderApp(api);

    await user.click(await screen.findByRole("button", { name: "Expand Project: Tree Project" }));
    const agentLink = screen.getByRole("link", { name: "Tree Agent" });
    expect(agentLink).toHaveAttribute("href", projectRoutePaths.agentDesign("tree", "agent-tree"));
    expect(agentLink).toHaveClass("tone-instance", "kind-agent");
    expect(screen.getByRole("link", { name: "Agents" })).toHaveAttribute("href", projectRoutePaths.agents("tree"));
    expect(screen.getByRole("link", { name: "Agents" })).toHaveClass("tone-kind", "kind-agent");
    expect(screen.getByRole("link", { name: "Workflows" })).toHaveAttribute("href", projectRoutePaths.workflows("tree"));
    expect(screen.getByRole("link", { name: "Workflows" })).toHaveClass("tone-kind", "kind-workflow");
    expect(screen.getByRole("link", { name: "Knowledge" })).toHaveAttribute("href", projectRoutePaths.knowledge("tree"));
    expect(screen.getByRole("link", { name: "Files" })).toHaveClass("tone-collection", "kind-files");
    expect(within(document.querySelector(".nav-group-projects") as HTMLElement).queryByRole("link", { name: "Runs" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "History" })).toHaveAttribute("href", "#/runs");
    const projectRow = document.querySelector(`.nav-group-projects .sidebar-nav-item-row`);
    const projectLink = projectRow?.querySelector(`a[href="${projectRoutePaths.project("tree")}"]`);
    expect(projectLink).toHaveClass("sidebar-nav-link");
    expect(projectLink).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("button", { name: "Add Agent: Tree Project" })).toBeInTheDocument();
    expect(projectRow?.querySelector(`button[aria-label="Add Agent: Tree Project"]`)).toBeNull();
    expect(projectRow?.querySelector(".sidebar-nav-item-action")).not.toBeNull();
    expect(projectRow?.querySelector(".sidebar-nav-item-leading-action")).not.toBeNull();
    expect(projectRow?.parentElement?.querySelector(":scope > .sidebar-nav-children")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Agent actions: Tree Agent" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add child Agent: Tree Agent" })).toHaveAttribute("title", "Add child Agent");
    expect(screen.getByRole("link", { name: "Tree Agent" })).not.toHaveAttribute("title");
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
    expect(screen.getAllByRole("menuitem")).toHaveLength(4);
    expect(screen.getByRole("menuitem", { name: "Pin Project" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Show Project Location" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Delete" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("opens Add Agent, creates a blank Agent, and opens its canvas", async () => {
    const editable = project({ project_id: "editable", name: "Before edit" });
    const api = apiFor([editable]);
    api.updateProject.mockResolvedValue(project({ project_id: "editable", name: "Allocated edit", description: "Updated" }));
    api.deleteProject.mockResolvedValue({ schema_version: "1.0", project_id: "editable", disposition: "trashed", removed_at: "2026-08-28T00:00:00Z" });
    api.getProject.mockResolvedValue(editable);
    const user = userEvent.setup();
    window.location.hash = projectRoutePaths.project("editable");
    await renderApp(api);

    await user.click(await screen.findByRole("button", { name: "Add Agent: Before edit" }));
    expect(window.location.hash).toBe(projectRoutePaths.project("editable"));
    expect(screen.getAllByRole("menuitem")).toHaveLength(4);
    expect(screen.getByRole("menuitem", { name: /Create blank Agent/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Import Agent from template/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Import Agent file/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Import external Agent/ })).toBeInTheDocument();
    await user.click(screen.getByRole("menuitem", { name: /Create blank Agent/ }));
    await user.type(screen.getByRole("textbox", { name: "Agent name (optional)" }), "Requested Agent");
    await user.type(screen.getByRole("textbox", { name: "Description (optional)" }), "Created here");
    await user.click(screen.getByRole("button", { name: "Create Agent" }));
    await waitFor(() => expect(api.createAgent).toHaveBeenCalledWith("editable", { mode: "blank", name: "Requested Agent", description: "Created here" }));
    expect(window.location.hash).toBe(projectRoutePaths.agentDesign("editable", "created-agent"));
    expect(screen.queryByRole("dialog", { name: "Create blank Agent" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Collapse Project: Before edit" })).toHaveAttribute("aria-expanded", "true");
    await user.click(screen.getByRole("button", { name: "Project actions: Before edit" }));
    await user.click(screen.getByRole("menuitem", { name: "Edit" }));
    await user.clear(screen.getByRole("textbox", { name: "Project name" }));
    await user.type(screen.getByRole("textbox", { name: "Project name" }), "Requested name");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.updateProject).toHaveBeenCalledWith("editable", { name: "Requested name", description: "" }));
    const editDialog = await screen.findByRole("dialog", { name: "Edit project" });
    expect(within(editDialog).getByRole("status")).toHaveTextContent("Server-assigned name: Allocated edit");
    expect((await screen.findAllByRole("link", { name: "Allocated edit" })).length).toBeGreaterThanOrEqual(1);
    await user.click(screen.getByRole("button", { name: "Done" }));
    await user.click(screen.getByRole("button", { name: "Project actions: Allocated edit" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    expect(api.deleteProject).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Delete Project" }));
    await waitFor(() => expect(api.deleteProject).toHaveBeenCalledWith("editable"));
    await waitFor(() => expect(window.location.hash).toBe("#/projects"));
    expect(screen.queryAllByRole("link", { name: "Allocated edit" })).toHaveLength(0);
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
    await renderApp(api);

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

  it("edits and deletes a Workflow from the sidebar menu", async () => {
    const workflow = { workflow_id: "wf-edit", slug: "draft-flow", name: "Draft Flow", description: "Before", source_path: "workflows/draft-flow/workflow.vworkflow.yaml", source_file_hash: "wf-hash" };
    const editable = project({ project_id: "wf-edit-project", name: "Workflow Project", workflows: [workflow], workflow_count: 1 });
    const renamed = { ...workflow, name: "Renamed Flow", description: "After" };
    const afterDelete = project({ project_id: editable.project_id, name: editable.name, workflows: [], workflow_count: 0 });
    const api = apiFor([editable]);
    api.getWorkflowDraft.mockResolvedValue({ schema_version: "1.0", draft_id: "wf-draft-edit", revision: 2, etag: "wf-etag-edit", source_file_hash: "wf-hash", source: { schema_version: "1.0", component_type: "Workflow", workflow_id: workflow.workflow_id, slug: workflow.slug, name: workflow.name, description: workflow.description, inputs: {}, outputs: {}, nodes: [], transitions: [], extensions: { veyra: { permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } }, ui: { positions: {} }, lock: {} } });
    api.getProject.mockResolvedValue(project({ ...editable, workflows: [renamed], workflow_count: 1 }));
    api.deleteWorkflow.mockResolvedValue({ schema_version: "1.0", project_id: editable.project_id, workflow_id: workflow.workflow_id, disposition: "trashed", removed_at: "2026-08-28T00:00:00Z", project: afterDelete });
    const user = userEvent.setup();
    window.location.hash = projectRoutePaths.project(editable.project_id);
    await renderApp(api);

    await user.click(await screen.findByRole("button", { name: "Workflow actions: Draft Flow" }));
    await user.click(screen.getByRole("menuitem", { name: "Edit" }));
    await user.clear(await screen.findByRole("textbox", { name: "Workflow name" }));
    await user.type(screen.getByRole("textbox", { name: "Workflow name" }), "Renamed Flow");
    await user.clear(screen.getByRole("textbox", { name: "Description" }));
    await user.type(screen.getByRole("textbox", { name: "Description" }), "After");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.saveWorkflowDraft).toHaveBeenCalledWith(editable.project_id, workflow.workflow_id, expect.objectContaining({ expected_revision: 2, source: expect.objectContaining({ name: "Renamed Flow", description: "After" }) }), { etag: "wf-etag-edit" }));
    expect(screen.queryByRole("dialog", { name: "Edit Workflow" })).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Workflow actions: Renamed Flow" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Workflow actions: Renamed Flow" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    expect(screen.getByRole("dialog", { name: "Delete Workflow?" })).toBeInTheDocument();
    expect(api.deleteWorkflow).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Delete Workflow" }));
    await waitFor(() => expect(api.deleteWorkflow).toHaveBeenCalledWith(editable.project_id, workflow.workflow_id));
    expect(screen.queryByRole("button", { name: "Workflow actions: Renamed Flow" })).not.toBeInTheDocument();
  });

  it("edits, pins, and deletes Knowledge from the sidebar menu", async () => {
    const first = { knowledge_id: "kn-a", slug: "alpha-note", name: "Alpha Note", description: "Before", source_path: "knowledge/alpha-note/document.md", source_file_hash: "kn-a" };
    const second = { knowledge_id: "kn-z", slug: "zeta-note", name: "Zeta Note", description: "", source_path: "knowledge/zeta-note/document.md", source_file_hash: "kn-z" };
    const source = project({ project_id: "kn-edit-project", name: "Knowledge Project", knowledge: [first, second], knowledge_count: 2 });
    const renamed = { ...first, name: "Renamed Note", description: "After" };
    const afterDelete = project({ project_id: source.project_id, name: source.name, knowledge: [second], knowledge_count: 1 });
    const api = apiFor([source]);
    api.getProject.mockResolvedValue(project({ ...source, knowledge: [renamed, second], knowledge_count: 2 }));
    api.deleteKnowledge.mockResolvedValue({ schema_version: "1.0", project_id: source.project_id, knowledge_id: first.knowledge_id, disposition: "trashed", removed_at: "2026-08-28T00:00:00Z", project: afterDelete });
    const user = userEvent.setup();
    window.location.hash = projectRoutePaths.project(source.project_id);
    await renderApp(api);

    const zetaActions = await screen.findByRole("button", { name: "Knowledge actions: Zeta Note" });
    const alphaActions = screen.getByRole("button", { name: "Knowledge actions: Alpha Note" });
    expect(alphaActions.compareDocumentPosition(zetaActions) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(Node.DOCUMENT_POSITION_FOLLOWING);

    await user.click(zetaActions);
    await user.click(screen.getByRole("menuitem", { name: "Pin" }));
    const pinnedZeta = await screen.findByRole("button", { name: "Knowledge actions: Zeta Note" });
    const unpinnedAlpha = screen.getByRole("button", { name: "Knowledge actions: Alpha Note" });
    expect(pinnedZeta.compareDocumentPosition(unpinnedAlpha) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(Node.DOCUMENT_POSITION_FOLLOWING);

    await user.click(unpinnedAlpha);
    await user.click(screen.getByRole("menuitem", { name: "Edit" }));
    await user.clear(await screen.findByRole("textbox", { name: "Knowledge name" }));
    await user.type(screen.getByRole("textbox", { name: "Knowledge name" }), "Renamed Note");
    await user.clear(screen.getByRole("textbox", { name: "Description" }));
    await user.type(screen.getByRole("textbox", { name: "Description" }), "After");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.updateKnowledge).toHaveBeenCalledWith(source.project_id, first.knowledge_id, { name: "Renamed Note", description: "After" }));
    expect(await screen.findByRole("button", { name: "Knowledge actions: Renamed Note" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Knowledge actions: Renamed Note" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    await user.click(screen.getByRole("button", { name: "Delete Knowledge" }));
    await waitFor(() => expect(api.deleteKnowledge).toHaveBeenCalledWith(source.project_id, first.knowledge_id));
    expect(screen.queryByRole("button", { name: "Knowledge actions: Renamed Note" })).not.toBeInTheDocument();
  });

  it("pins an Agent to the top of its Project list", async () => {
    const alpha = { agent_id: "agent-a", slug: "alpha", name: "Alpha Agent", description: "", pinned: false, source_path: "agents/alpha/agent.vagent.yaml", source_file_hash: "h-a" };
    const zeta = { agent_id: "agent-z", slug: "zeta", name: "Zeta Agent", description: "", pinned: false, source_path: "agents/zeta/agent.vagent.yaml", source_file_hash: "h-z" };
    const source = project({ project_id: "pin-agents", name: "Pin Agents", agents: [alpha, zeta], agent_count: 2 });
    const api = apiFor([source]);
    api.updateAgent.mockResolvedValue(project({ ...source, agents: [{ ...zeta, pinned: true }, alpha], default_agent_id: zeta.agent_id, agent_count: 2 }));
    const user = userEvent.setup();
    window.location.hash = projectRoutePaths.project(source.project_id);
    await renderApp(api);

    await user.click(await screen.findByRole("button", { name: "Agent actions: Zeta Agent" }));
    await user.click(screen.getByRole("menuitem", { name: "Pin" }));
    await waitFor(() => expect(api.updateAgent).toHaveBeenCalledWith("pin-agents", "agent-z", { pinned: true }));
    const zetaBtn = screen.getByRole("button", { name: "Agent actions: Zeta Agent" });
    const alphaBtn = screen.getByRole("button", { name: "Agent actions: Alpha Agent" });
    expect(zetaBtn.compareDocumentPosition(alphaBtn) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("submits template and file Agent imports with their real request shapes", async () => {
    const source = project({ project_id: "imports", name: "Import Project" });
    const api = apiFor([source]);
    api.getProject.mockResolvedValue(source);
    const user = userEvent.setup();
    await renderApp(api);

    await user.click(await screen.findByRole("button", { name: "Expand Project: Import Project" }));
    await user.click(screen.getByRole("button", { name: "Add Agent: Import Project" }));
    await user.click(screen.getByRole("menuitem", { name: /Import Agent from template/ }));
    await screen.findByRole("option", { name: "Review Agent" });
    await user.type(screen.getByRole("textbox", { name: "Agent name (optional)" }), "Template override");
    await user.click(screen.getByRole("button", { name: "Import Agent" }));
    await waitFor(() => expect(api.createAgent).toHaveBeenCalledWith("imports", { mode: "template", template_id: "review", name: "Template override" }));
    expect(window.location.hash).toBe(projectRoutePaths.agentDesign("imports", "created-agent"));

    await user.click(screen.getByRole("button", { name: "Add Agent: Import Project" }));
    await user.click(screen.getByRole("menuitem", { name: /Import Agent file/ }));
    const file = new File(["schema_version: '1.0'"], "review.vagent.yaml", { type: "application/x-yaml" });
    await user.upload(screen.getByLabelText("Choose Agent file"), file);
    await user.type(screen.getByRole("textbox", { name: "Description (optional)" }), "Imported file");
    await user.click(screen.getByRole("button", { name: "Import Agent" }));
    await waitFor(() => expect(api.importAgent).toHaveBeenCalledWith("imports", { file, description: "Imported file" }));
    expect(window.location.hash).toBe(projectRoutePaths.agentDesign("imports", "imported-agent"));
  });

  it("does not omit resource-kind folders when an empty Project is expanded", async () => {
    const user = userEvent.setup();
    await renderApp(apiFor([project({ project_id: "empty", name: "Empty Project" })]));
    await user.click(await screen.findByRole("button", { name: "Expand Project: Empty Project" }));
    const tree = document.querySelector(".nav-group-projects .sidebar-nav-children");
    expect(tree).not.toBeNull();
    expect(within(tree as HTMLElement).getByRole("link", { name: "Agents" })).toHaveClass("tone-kind");
    expect(within(tree as HTMLElement).getByRole("link", { name: "Workflows" })).toHaveClass("tone-kind");
    expect(within(tree as HTMLElement).getByRole("link", { name: "Knowledge" })).toHaveClass("tone-kind");
    expect(within(tree as HTMLElement).getByRole("link", { name: "Files" })).toHaveClass("tone-collection");
    expect(within(tree as HTMLElement).queryByRole("link", { name: "Runs" })).not.toBeInTheDocument();
  });

  it("renders grandchild Agent links in the sidebar and reveals a Project folder", async () => {
    const nested = project({
      project_id: "nested",
      name: "Nested Project",
      agents: [
        { agent_id: "parent", slug: "parent", name: "Parent Agent", description: "", pinned: false, source_path: "agents/parent/agent.vagent.yaml", source_file_hash: "p" },
        { agent_id: "child", slug: "child", name: "Child Agent", description: "", pinned: false, source_path: "agents/child/agent.vagent.yaml", source_file_hash: "c", parent_agent_id: "parent" },
        { agent_id: "grand", slug: "grand", name: "Grand Agent", description: "", pinned: false, source_path: "agents/grand/agent.vagent.yaml", source_file_hash: "g", parent_agent_id: "child" },
      ],
      agent_count: 3,
    });
    const user = userEvent.setup();
    const api = apiFor([nested]);
    await renderApp(api);
    await user.click(await screen.findByRole("button", { name: "Expand Project: Nested Project" }));
    expect(screen.getByRole("link", { name: "Grand Agent" })).toHaveAttribute("href", projectRoutePaths.agentDesign("nested", "grand"));
    await user.click(screen.getByRole("button", { name: "Project actions: Nested Project" }));
    await user.click(screen.getByRole("menuitem", { name: "Show Project Location" }));
    await waitFor(() => expect(api.revealProject).toHaveBeenCalledWith("nested"));
  });

  it("renders title-only root headers and linked nested breadcrumbs at 320px", async () => {
    setViewport(true);
    const nested = project({ project_id: "crumb", name: "Breadcrumb Project", agents: [{ agent_id: "crumb-agent", slug: "breadcrumb-agent", name: "Breadcrumb Agent", description: "", pinned: false, source_path: "agents/breadcrumb/agent.vagent.yaml", source_file_hash: "crumb-hash" }], agent_count: 1 });
    const api = apiFor([nested]);
    api.getProject.mockResolvedValue(nested);
    window.location.hash = projectRoutePaths.project("crumb");
    await renderApp(api);

    expect(await screen.findByLabelText("Breadcrumb")).toBeInTheDocument();
    const crumbs = screen.getByLabelText("Breadcrumb");
    expect(within(crumbs).getByRole("link", { name: "Home" })).toHaveAttribute("href", "#/projects");
    expect(within(crumbs).getByRole("link", { name: "Breadcrumb Project" })).toHaveAttribute("href", projectRoutePaths.project("crumb"));
    expect(within(crumbs).getByText("Breadcrumb Project", { selector: "[aria-current=page]" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Back" })).not.toBeInTheDocument();
    cleanup();
    window.location.hash = "#/projects";
    await renderApp(apiFor());
    expect(await screen.findByRole("heading", { name: "New chat", level: 1 })).toBeInTheDocument();
    expect(screen.queryByLabelText("Breadcrumb")).not.toBeInTheDocument();
    const menu = screen.getByRole("button", { name: "Open navigation" });
    await userEvent.click(menu);
    expect(screen.getAllByRole("button", { name: "Close navigation" })).toHaveLength(2);
  });

  it("uses Project-context navigation when a Project is opened from the sidebar", async () => {
    const scoped = project({ project_id: "project-open", name: "Opened Project" });
    const api = apiFor([scoped]);
    api.getProject.mockResolvedValue(scoped);
    window.location.hash = projectRoutePaths.project(scoped.project_id);
    await renderApp(api);

    const sidebar = document.querySelector(".nav-group-fixed") as HTMLElement;
    expect(await within(sidebar).findByRole("link", { name: "Back to home" })).toHaveAttribute("href", "#/projects");
    expect(within(sidebar).getByRole("link", { name: "New chat" })).toHaveAttribute("href", projectRoutePaths.projectChat("project-open"));
    expect(within(sidebar).getByRole("link", { name: "Project resources" })).toHaveAttribute("href", projectRoutePaths.projectResources("project-open"));
    expect(within(sidebar).getByRole("link", { name: "Project resources" })).not.toHaveAttribute("aria-current");
    expect(within(sidebar).getByRole("link", { name: "Data analysis" })).toHaveAttribute("href", projectRoutePaths.projectAnalysis("project-open"));
    expect(within(sidebar).queryByRole("link", { name: "Workflows" })).toBeNull();
    expect(within(sidebar).queryByRole("link", { name: "Knowledge" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Run workspace" })).not.toBeInTheDocument();
    expect(document.querySelector(".nav-group-recent")).toBeInTheDocument();
    const projectTreeLink = document.querySelector(".nav-group-projects a[href=\"" + projectRoutePaths.project("project-open") + "\"]");
    expect(projectTreeLink).not.toHaveAttribute("aria-current");
    expect(projectTreeLink).toHaveClass("contextual");
    expect(screen.getByRole("link", { name: "Workflows" })).toHaveAttribute("href", projectRoutePaths.workflows("project-open"));
    expect(screen.getByRole("link", { name: "Agents" })).toHaveClass("tone-kind");
    expect(await screen.findByRole("heading", { name: "Opened Project", level: 2 })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "All" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Components" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Tools / MCP" })).not.toBeInTheDocument();
  });

  it("opens the global Resource Catalog from home", async () => {
    const scoped = project({ project_id: "library-home", name: "Library Home" });
    const user = userEvent.setup();
    await renderApp(apiFor([scoped]));
    await user.click(await screen.findByRole("link", { name: "Resource catalog" }));
    expect(window.location.hash).toBe("#/resources");
    expect(screen.getByRole("heading", { name: "Resource Catalog", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "All" })).toHaveAttribute("aria-selected", "true");
  });

  it("lists Workflows beside Agents in the Project tree and keeps Resource Library catalog kinds off the Project", async () => {
    const scoped = project({
      project_id: "kinds",
      name: "Kind Project",
      agents: [{ agent_id: "agent-one", slug: "review-agent", name: "Review Agent", description: "", pinned: false, source_path: "agents/review-agent/agent.vagent.yaml", source_file_hash: "agent-hash" }],
      agent_count: 1,
      workflows: [{ workflow_id: "wf-one", slug: "review-path", name: "Review path", description: "", source_path: "workflows/review-path/workflow.vworkflow.yaml", source_file_hash: "wf-hash" }],
    });
    window.location.hash = projectRoutePaths.workflows("kinds");
    await renderApp(apiFor([scoped]));

    const sidebar = document.querySelector(".nav-group-fixed") as HTMLElement;
    expect(await within(sidebar).findByRole("link", { name: "Project resources" })).toHaveAttribute("href", projectRoutePaths.projectResources("kinds"));
    expect(within(sidebar).queryByRole("link", { name: "Workflows" })).toBeNull();
    const tree = document.querySelector(".nav-group-projects") as HTMLElement;
    const workflowsLink = within(tree).getByRole("link", { name: "Workflows" });
    expect(workflowsLink).toHaveAttribute("aria-current", "page");
    expect(workflowsLink).toHaveClass("tone-kind", "kind-workflow");
    const projectTreeLink = tree.querySelector(`a[href="${projectRoutePaths.project("kinds")}"]`);
    expect(projectTreeLink).not.toHaveClass("contextual");
    expect(projectTreeLink).not.toHaveAttribute("aria-current");
    expect(within(tree).getByRole("link", { name: "Review path" })).toHaveAttribute("href", projectRoutePaths.workflow("kinds", "wf-one"));
    expect(within(tree).getByRole("link", { name: "Review path" })).toHaveClass("tone-instance", "kind-workflow");
    expect(within(tree).getByRole("link", { name: "Review Agent" })).toHaveClass("tone-instance", "kind-agent");
    expect(screen.queryByRole("link", { name: "Components" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Tools / MCP" })).not.toBeInTheDocument();
  });

  it("creates a Workflow from the Project tree and keeps Resource Library catalog kinds on the page, not the sidebar", async () => {
    const source = project({ project_id: "wf-add", name: "Flow Add" });
    const api = apiFor([source]);
    api.createWorkflow.mockResolvedValue({ schema_version: "1.0", project_id: "wf-add", workflow_id: "wf-new", slug: "wf-new", name: "New Workflow", description: "", source_path: "workflows/wf-new/workflow.vworkflow.yaml", source_file_hash: "wf-created" });
    api.getWorkflowDraft = vi.fn().mockRejectedValue(new Error("draft unavailable"));
    api.getProject.mockResolvedValue(project({
      ...source,
      workflows: [{ workflow_id: "wf-new", slug: "wf-new", name: "New Workflow", description: "", source_path: "workflows/wf-new/workflow.vworkflow.yaml", source_file_hash: "h" }],
    }));
    window.location.hash = projectRoutePaths.project("wf-add");
    const user = userEvent.setup();
    await renderApp(api);
    await user.click(await screen.findByRole("button", { name: "Add Workflow: Flow Add" }));
    await waitFor(() => expect(api.createWorkflow).toHaveBeenCalledWith("wf-add", { name: "New Workflow" }));
    expect(window.location.hash).toBe(projectRoutePaths.workflow("wf-add", "wf-new"));
    cleanup();
    window.location.hash = "#/components";
    await renderApp(apiFor());
    expect(screen.getByRole("link", { name: "Resource catalog" })).toHaveAttribute("href", "#/resources");
    expect(screen.getByRole("tab", { name: "All" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Components" })).toBeInTheDocument();
  });

  it("does not invent a Community catalog or featured packages", async () => {
    window.location.hash = "#/community";
    await renderApp(apiFor());
    expect(await screen.findByRole("heading", { name: "The Community catalog is not connected." })).toBeInTheDocument();
    expect(screen.queryByText("Research Brief")).not.toBeInTheDocument();
    expect(screen.queryByText("4.8")).not.toBeInTheDocument();
  });

  it("renders nested Agent breadcrumbs as Home / Project / Agents / ancestry", async () => {
    const nested = project({
      project_id: "nested-crumb",
      name: "Nested Project",
      agents: [
        { agent_id: "parent", slug: "parent-agent", name: "Parent Agent", description: "", pinned: false, source_path: "agents/parent/agent.vagent.yaml", source_file_hash: "p" },
        { agent_id: "child", slug: "child-agent", name: "Child Agent", description: "", pinned: false, source_path: "agents/child/agent.vagent.yaml", source_file_hash: "c", parent_agent_id: "parent" },
      ],
      agent_count: 2,
    });
    window.location.hash = projectRoutePaths.agent("nested-crumb", "child");
    await renderApp(apiFor([nested]));

    const breadcrumbs = await screen.findByLabelText("Breadcrumb");
    expect(within(breadcrumbs).getByRole("link", { name: "Home" })).toHaveAttribute("href", "#/projects");
    expect(within(breadcrumbs).getByRole("link", { name: "Nested Project" })).toHaveAttribute("href", projectRoutePaths.project("nested-crumb"));
    expect(within(breadcrumbs).getByRole("link", { name: "Agents" })).toHaveAttribute("href", projectRoutePaths.agents("nested-crumb"));
    expect(within(breadcrumbs).getByRole("link", { name: "Parent Agent" })).toHaveAttribute("href", projectRoutePaths.agentDesign("nested-crumb", "parent"));
    expect(within(breadcrumbs).getByText("Child Agent", { selector: "[aria-current=page]" })).toBeInTheDocument();
  });

  it("keeps Workflow in the Agent breadcrumb when opening an AgentCall target", () => {
    const scoped = project({
      project_id: "wf-crumb",
      name: "Flow Project",
      agents: [{ agent_id: "agent-one", slug: "review-agent", name: "Review Agent", description: "", pinned: false, source_path: "agents/review-agent/agent.vagent.yaml", source_file_hash: "agent-hash" }],
      workflows: [{ workflow_id: "wf-one", slug: "review-path", name: "Review path", description: "", source_path: "workflows/review-path/workflow.vworkflow.yaml", source_file_hash: "wf-hash" }],
    });
    const header = desktopHeader(
      { kind: "agent-design", path: projectRoutePaths.agentDesignFromWorkflow("wf-crumb", "agent-one", "wf-one"), projectId: "wf-crumb", agentId: "agent-one", workflowId: "wf-one" },
      [scoped],
      "en",
    );
    expect(header.breadcrumbs?.map((item) => [item.label, item.href])).toEqual([
      ["Home", "#/projects"],
      ["Flow Project", projectRoutePaths.project("wf-crumb")],
      ["Workflows", projectRoutePaths.workflows("wf-crumb")],
      ["Review path", projectRoutePaths.workflow("wf-crumb", "wf-one")],
      ["Review Agent", projectRoutePaths.agentDesign("wf-crumb", "agent-one")],
    ]);
  });

  it("uses Project-context navigation when an Agent is selected, and highlights the Agent in the tree", async () => {
    const scoped = project({
      project_id: "agent-project",
      name: "Agent Project",
      agents: [{ agent_id: "agent-one", slug: "review-agent", name: "Review Agent", description: "", pinned: false, source_path: "agents/review-agent/agent.vagent.yaml", source_file_hash: "agent-hash" }],
    });
    window.location.hash = projectRoutePaths.agentDesign(scoped.project_id, "agent-one");
    await renderApp(apiFor([scoped]));

    const sidebar = document.querySelector(".nav-group-fixed") as HTMLElement;
    const contextLinks = await within(sidebar).findAllByRole("link", { name: /^(New chat|Project resources|Data analysis)$/ });
    expect(contextLinks.map((link) => link.textContent)).toEqual(["New chat", "Project resources", "Data analysis"]);
    expect(within(sidebar).getByRole("link", { name: "Back to home" })).toHaveAttribute("href", "#/projects");
    expect(within(sidebar).getByRole("link", { name: "New chat" })).toHaveAttribute("href", projectRoutePaths.projectChat("agent-project"));
    expect(within(sidebar).getByRole("link", { name: "Project resources" })).toHaveAttribute("href", projectRoutePaths.projectResources("agent-project"));
    expect(within(sidebar).getByRole("link", { name: "Data analysis" })).toHaveAttribute("href", projectRoutePaths.projectAnalysis("agent-project"));
    expect(within(sidebar).queryByRole("link", { name: "Orchestration" })).toBeNull();
    const tree = document.querySelector(".nav-group-projects") as HTMLElement;
    const agentTreeLink = tree.querySelector(`a[href="${projectRoutePaths.agentDesign("agent-project", "agent-one")}"]`);
    const projectTreeLink = tree.querySelector(`a[href="${projectRoutePaths.project("agent-project")}"]`);
    expect(agentTreeLink).toHaveAttribute("aria-current", "page");
    expect(agentTreeLink).not.toHaveClass("contextual");
    expect(projectTreeLink).not.toHaveAttribute("aria-current");
    expect(projectTreeLink).not.toHaveClass("contextual");
    expect(within(tree).getByRole("link", { name: "Agents" })).not.toHaveClass("active");
    expect(within(tree).getByRole("link", { name: "Agents" })).not.toHaveClass("contextual");
    expect(within(tree).queryByRole("link", { name: "Runs" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "History" })).toHaveAttribute("href", projectRoutePaths.runs("agent-project"));
    expect(document.querySelector(".nav-group-recent")).toBeInTheDocument();
    expect(screen.getByText("No recent conversations or runs yet.")).toBeInTheDocument();
  });

  it("localizes Project-context navigation on Agent canvas in Chinese", async () => {
    window.localStorage.setItem("veyra.language", "zh");
    const scoped = project({
      project_id: "agent-project-zh",
      name: "中文项目",
      agents: [{ agent_id: "agent-zh", slug: "审阅 Agent", name: "审阅 Agent", description: "", pinned: false, source_path: "agents/reviewer/agent.vagent.yaml", source_file_hash: "agent-hash" }],
    });
    window.location.hash = projectRoutePaths.agentDesign(scoped.project_id, "agent-zh");
    await renderApp(apiFor([scoped]));

    const sidebar = document.querySelector(".nav-group-fixed") as HTMLElement;
    const contextLinks = await within(sidebar).findAllByRole("link", { name: /^(新聊天|项目资源|数据分析)$/ });
    expect(contextLinks.map((link) => link.textContent)).toEqual(["新聊天", "项目资源", "数据分析"]);
    expect(within(sidebar).getByRole("link", { name: "返回主页" })).toHaveAttribute("href", "#/projects");
    expect(within(sidebar).queryByRole("link", { name: "编排" })).toBeNull();
    const tree = document.querySelector(".nav-group-projects") as HTMLElement;
    expect(within(tree).getByRole("link", { name: "Agent" })).toHaveClass("tone-kind", "kind-agent");
    expect(within(tree).getByRole("link", { name: "工作流" })).toHaveClass("tone-kind", "kind-workflow");
    expect(within(tree).getByRole("link", { name: "知识" })).toHaveClass("tone-kind", "kind-knowledge");
    expect(within(tree).getByRole("link", { name: "文件" })).toHaveClass("tone-collection", "kind-files");
    expect(within(tree).queryByRole("link", { name: "运行记录" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "历史" })).toHaveAttribute("href", projectRoutePaths.runs("agent-project-zh"));
    const agentTreeLink = tree.querySelector(`a[href="${projectRoutePaths.agentDesign("agent-project-zh", "agent-zh")}"]`);
    const projectTreeLink = tree.querySelector(`a[href="${projectRoutePaths.project("agent-project-zh")}"]`);
    expect(agentTreeLink).toHaveAttribute("aria-current", "page");
    expect(agentTreeLink).not.toHaveClass("contextual");
    expect(projectTreeLink).not.toHaveAttribute("aria-current");
    expect(projectTreeLink).not.toHaveClass("contextual");
    expect(screen.getByText("暂无最近聊天或运行记录。")).toBeInTheDocument();
    expect(within(await screen.findByLabelText("面包屑")).getByRole("link", { name: "主页" })).toHaveAttribute("href", "#/projects");
    expect(within(screen.getByLabelText("面包屑")).getByRole("link", { name: "中文项目" })).toHaveAttribute("href", projectRoutePaths.project("agent-project-zh"));
    expect(within(screen.getByLabelText("面包屑")).getByRole("link", { name: "Agent" })).toHaveAttribute("href", projectRoutePaths.agents("agent-project-zh"));
  });

  it("preserves account controls, theme choices, and responsive sidebar focus behavior", async () => {
    const user = userEvent.setup();
    const api = apiFor();
    await renderApp(api);
    expect(await screen.findByRole("heading", { name: "What do you want to achieve in a new project?", level: 2 })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open account menu" }));
    expect(screen.getByRole("menuitem", { name: "Account" })).toHaveAttribute("href", "#/account");
    expect(screen.getByRole("menuitem", { name: "Settings" })).toHaveAttribute("href", "#/settings");

    window.localStorage.setItem("veyra.theme", "dark");
    cleanup();
    await renderApp(api);
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));
    await user.click(screen.getByRole("button", { name: "Switch to light mode" }));
    await waitFor(() => expect(window.localStorage.getItem("veyra.theme")).toBe("light"));

    cleanup();
    setViewport(true);
    await renderApp(api);
    const menu = screen.getByRole("button", { name: "Open navigation" });
    await user.click(menu);
    await user.keyboard("{Escape}");
    expect(menu).toHaveFocus();
  });

  it("keeps the New chat surface and shell controls bilingual", async () => {
    const user = userEvent.setup();
    await renderApp(apiFor());
    expect(await screen.findByRole("heading", { name: "What do you want to achieve in a new project?", level: 2 })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Switch to Chinese" }));
    expect(await screen.findByRole("heading", { name: "你想在 新项目 实现什么？", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "新聊天" })).toHaveAttribute("href", "#/chat");
    expect(screen.getByRole("link", { name: "运行工作台" })).toHaveAttribute("href", "#/monitor");
    expect(screen.getByRole("link", { name: "资源目录" })).toHaveAttribute("href", "#/resources");
    expect(screen.getByRole("link", { name: "知识库" })).toHaveAttribute("href", "#/files");
    expect(screen.getByRole("link", { name: "历史" })).toHaveAttribute("href", "#/runs");
  });

  it("opens run history from the header History control", async () => {
    const user = userEvent.setup();
    const scoped = project({ project_id: "history-project", name: "History Project" });
    await renderApp(apiFor([scoped]));
    const history = await screen.findByRole("link", { name: "History" });
    expect(history).toHaveAttribute("href", "#/runs");
    expect(history).not.toHaveAttribute("aria-current");
    await user.click(history);
    expect(window.location.hash).toBe("#/runs");
    await waitFor(() => expect(screen.getByRole("link", { name: "History" })).toHaveAttribute("aria-current", "page"));
    expect(screen.getByRole("link", { name: "History" })).toHaveClass("is-current");
    expect(screen.getByRole("heading", { name: "History" })).toBeInTheDocument();

    window.location.hash = projectRoutePaths.project("history-project");
    await waitFor(() => expect(screen.getByRole("link", { name: "History" })).toHaveAttribute("href", projectRoutePaths.runs("history-project")));
    expect(screen.getByRole("link", { name: "History" })).not.toHaveAttribute("aria-current");
    await user.click(screen.getByRole("link", { name: "History" }));
    expect(window.location.hash).toBe(projectRoutePaths.runs("history-project"));
    await waitFor(() => expect(document.querySelector("a.history-control")).toHaveAttribute("aria-current", "page"));
    expect(within(document.querySelector(".nav-group-projects") as HTMLElement).queryByRole("link", { name: "Runs" })).not.toBeInTheDocument();
  });

  it("renders the New chat placeholder instead of a generic route error", async () => {
    window.location.hash = "#/chat";
    await renderApp(apiFor());
    expect(await screen.findByRole("heading", { name: "What do you want to achieve in a new project?", level: 2 })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Type freely")).toBeInTheDocument();
    expect(screen.queryByText("Route not found")).not.toBeInTheDocument();
  });

  it("starts a new Project conversation from the composer by default", async () => {
    const created = project({ project_id: "created-project", name: "Created Project", root_path: "/tmp/created-project" });
    const api = apiFor();
    api.createProject.mockResolvedValue(created);
    api.getProject.mockImplementation(async (projectId: string) => (
      projectId === created.project_id ? created : project({ project_id: projectId, name: projectId })
    ));
    const user = userEvent.setup();
    await renderApp(api);
    await user.type(await screen.findByRole("textbox", { name: "Message" }), "Write a brief");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(api.createProject).toHaveBeenCalledWith({ description: "" }));
    expect(window.location.hash).toBe("#/projects/created-project/chat");
    expect(await screen.findByRole("heading", { name: "What do you want to achieve in Created Project?", level: 2 })).toBeInTheDocument();
  });

  it("opens the selected Project chat immediately and switches the sidebar", async () => {
    const first = project({
      project_id: "p-one",
      name: "Alpha Project",
      default_agent_id: "agent-1",
      agent_count: 1,
      agents: [{ agent_id: "agent-1", slug: "reviewer", name: "Reviewer", description: "", pinned: false, source_path: "agents/reviewer/agent.vagent.yaml", source_file_hash: "hash" }],
    });
    const api = apiFor([first]);
    api.getProject.mockResolvedValue(first);
    const user = userEvent.setup();
    await renderApp(api);
    await user.click(await screen.findByRole("button", { name: "Choose project" }));
    await user.click(await screen.findByRole("option", { name: /^Alpha Project/ }));
    expect(window.location.hash).toBe("#/projects/p-one/chat");
    expect(await screen.findByRole("heading", { name: "What do you want to achieve in Alpha Project?", level: 2 })).toBeInTheDocument();
    const sidebar = document.querySelector(".nav-group-fixed") as HTMLElement;
    expect(within(sidebar).getByRole("link", { name: "Back to home" })).toHaveAttribute("href", "#/projects");
    expect(within(sidebar).getByRole("link", { name: "New chat" })).toHaveAttribute("href", projectRoutePaths.projectChat("p-one"));
    expect(within(sidebar).getByRole("link", { name: "New chat" })).toHaveAttribute("aria-current", "page");
    expect(within(sidebar).getByRole("link", { name: "Project resources" })).toHaveAttribute("href", projectRoutePaths.projectResources("p-one"));
  });

  it("opens the selected Agent conversation from the composer picker", async () => {
    const first = project({
      project_id: "p-one",
      name: "Alpha Project",
      default_agent_id: "agent-1",
      agent_count: 1,
      agents: [{ agent_id: "agent-1", slug: "reviewer", name: "Reviewer", description: "", pinned: false, source_path: "agents/reviewer/agent.vagent.yaml", source_file_hash: "hash" }],
    });
    const api = apiFor([first]);
    api.getProject.mockResolvedValue(first);
    const user = userEvent.setup();
    await renderApp(api);
    await user.click(await screen.findByRole("button", { name: "Choose project" }));
    await user.click(await screen.findByRole("option", { name: /Reviewer/ }));
    expect(window.location.hash).toBe("#/projects/p-one/agents/agent-1");
    expect(await screen.findByRole("heading", { name: "What can I help with?", level: 2 })).toBeInTheDocument();
    const sidebar = document.querySelector(".nav-group-fixed") as HTMLElement;
    expect(within(sidebar).getByRole("link", { name: "Back to home" })).toHaveAttribute("href", "#/projects");
    expect(within(sidebar).getByRole("link", { name: "New chat" })).toHaveAttribute("href", projectRoutePaths.projectChat("p-one"));
    expect(within(sidebar).getByRole("link", { name: "Project resources" })).toHaveAttribute("href", projectRoutePaths.projectResources("p-one"));
    const agentTreeLink = document.querySelector(`.nav-group-projects a[href="${projectRoutePaths.agentDesign("p-one", "agent-1")}"]`);
    expect(agentTreeLink).toHaveAttribute("aria-current", "page");
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
    expect(screen.getByText("Agent Platform", { selector: "small" })).toBeInTheDocument();
    expect(screen.queryByText("Veyra Community")).not.toBeInTheDocument();
    if (hash === "#/login") expect(screen.getByText("Sign in to Veyra with your email and password.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: /^(Sign in|Send verification code|Send reset code)$/ })).toBeEnabled());
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("shows a specific login failure when Community is down or credentials are wrong", async () => {
    window.location.hash = "#/login";
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.endsWith("/account/me")) return jsonResponse(401, { detail: "authentication_required" });
      if (url.endsWith("/auth/login") && method === "POST") return jsonResponse(503, { detail: "community_unavailable" });
      return jsonResponse(404, { detail: "not_found" });
    });
    const user = userEvent.setup();
    render(<DesktopApp api={apiFor()} communityApi={accountApi(fetcher)} />);

    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Email"), "alice@example.com");
    await user.type(screen.getByLabelText("Password"), "maplexyz");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(errorCopy.en.network);

    fetcher.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.endsWith("/account/me")) return jsonResponse(401, { detail: "authentication_required" });
      if (url.endsWith("/auth/login") && method === "POST") return jsonResponse(401, { detail: "invalid_credentials" });
      return jsonResponse(404, { detail: "not_found" });
    });
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(errorCopy.en.invalidCredentials);
    expect(screen.getByLabelText("Password")).toHaveAttribute("aria-invalid", "true");
    expect(screen.queryByText(errorCopy.en.generic)).not.toBeInTheDocument();
  });

  it("sends unsigned users to login, including pasted Studio links", async () => {
    window.location.hash = projectRoutePaths.agentDesign("dddd", "agent-1");
    render(<DesktopApp api={apiFor()} communityApi={accountApi(vi.fn(async () => jsonResponse(401, { detail: "authentication_required" })))} />);

    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.queryByText("Projects", { selector: ".nav-group-projects .nav-group-label" })).not.toBeInTheDocument();
    await waitFor(() => expect(window.location.hash).toBe(desktopLoginHash(projectRoutePaths.agentDesign("dddd", "agent-1"))));

    window.location.hash = "#/projects";
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    await waitFor(() => expect(window.location.hash.startsWith("#/login")).toBe(true));
    expect(screen.queryByRole("heading", { name: "What do you want to achieve in a new project?", level: 2 })).not.toBeInTheDocument();
  });

  it("treats an unreachable Community restore as signed out and returns to login", async () => {
    window.location.hash = "#/account";
    document.cookie = "veyra-csrf=stale-csrf; path=/";
    const fetcher = vi.fn(async () => jsonResponse(503, { detail: "community_unavailable" }));
    render(<DesktopApp api={apiFor()} communityApi={accountApi(fetcher)} />);

    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    await waitFor(() => expect(fetcher).toHaveBeenCalled());
    expect(screen.queryByRole("heading", { name: "Manage your Veyra account" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open account menu" })).not.toBeInTheDocument();
  });

  it("restores a Community session, drives the account menu, and completes avatar lifecycle", async () => {
    window.location.hash = "#/account";
    let currentAccount: CommunityAccount = connectedAccount;
    const requests: Array<{ url: string; method: string; body?: BodyInit | null }> = [];
    let signedIn = true;
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = (init?.method ?? "GET").toUpperCase();
      requests.push({ url, method, body: init?.body });
      if (url.endsWith("/account/me")) {
        return signedIn
          ? jsonResponse(200, { schema_version: "community.account.v1", account: currentAccount })
          : jsonResponse(401, { detail: "authentication_required" });
      }
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
      if (url.endsWith("/auth/logout") && method === "POST") {
        signedIn = false;
        return new Response(null, { status: 204 });
      }
      return jsonResponse(404, { detail: "not_found" });
    });
    document.cookie = "veyra-csrf=test-csrf; path=/";
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
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open account menu" })).not.toBeInTheDocument();
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

  it("lets the user resize the app sidebar for this session only", async () => {
    const { unmount } = render(
      <ThemeProvider>
        <ApplicationShell
          brand={{ name: "Veyra", subtitle: "Agent Platform" }}
          navigation={[{ label: "Build", items: [{ href: "#/projects", label: "Projects", icon: FolderKanban }] }]}
          activeHref="#/projects"
          eyebrow="Workspace"
          title="Projects"
        >
          <div>Workspace content</div>
        </ApplicationShell>
      </ThemeProvider>,
    );
    const handle = screen.getByRole("separator", { name: "Resize sidebar" });
    expect(handle).toHaveAttribute("aria-valuenow", "248");
    fireEvent.keyDown(handle, { key: "ArrowRight" });
    expect(screen.getByRole("separator", { name: "Resize sidebar" })).toHaveAttribute("aria-valuenow", "256");
    unmount();
    render(
      <ThemeProvider>
        <ApplicationShell
          brand={{ name: "Veyra", subtitle: "Agent Platform" }}
          navigation={[{ label: "Build", items: [{ href: "#/projects", label: "Projects", icon: FolderKanban }] }]}
          activeHref="#/projects"
          eyebrow="Workspace"
          title="Projects"
        >
          <div>Workspace content</div>
        </ApplicationShell>
      </ThemeProvider>,
    );
    expect(screen.getByRole("separator", { name: "Resize sidebar" })).toHaveAttribute("aria-valuenow", "248");
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
    expect(parseDesktopRoute("#/resources").kind).toBe("resources");
    expect(parseDesktopRoute(projectRoutePaths.project("p")).kind).toBe("project");
    expect(parseDesktopRoute(projectRoutePaths.projectResources("p")).kind).toBe("project-resources");
    expect(parseDesktopRoute(projectRoutePaths.projectChat("p")).kind).toBe("project-chat");
    expect(parseDesktopRoute(projectRoutePaths.projectAnalysis("p")).kind).toBe("project-analysis");
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
    expect(desktopLoginHash("#/projects")).toBe("#/login?next=%23%2Fprojects");
    expect(desktopLoginHash(projectRoutePaths.agentDesign("p", "a")).startsWith("#/login?next=")).toBe(true);
    expect(desktopLoginHash("#/login")).toBe("#/login");
    expect(desktopLoginHash("#/register")).toBe("#/register");
    expect(parseDesktopRoute("#/nowhere").kind).toBe("not-found");
    expect(parseDesktopRoute(projectRoutePaths.workflows("p")).kind).toBe("project-workflows");
    expect(parseDesktopRoute(projectRoutePaths.workflow("p", "w")).kind).toBe("project-workflow");
    expect(parseDesktopRoute(projectRoutePaths.knowledge("p")).kind).toBe("project-knowledge");
    expect(parseDesktopRoute(projectRoutePaths.knowledgeItem("p", "k")).kind).toBe("project-knowledge-item");
    expect(parseDesktopRoute(projectRoutePaths.files("p")).kind).toBe("project-files");
    expect(parseDesktopRoute(projectRoutePaths.runs("p")).kind).toBe("project-runs");
    expect(parseDesktopRoute(projectRoutePaths.agentDesignFromWorkflow("p", "a", "w"))).toMatchObject({ kind: "agent-design", agentId: "a", workflowId: "w" });
  });
});
