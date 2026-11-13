import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FolderKanban } from "lucide-react";
import { communityRoutePaths, desktopLoginHash, parseDesktopRoute, projectRoutePaths, type CommunityAccount, type ProjectSummaryResponse, type SaveDraftRequest, type SaveDraftResponse } from "@veyra/api-contracts";
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
  device_name: null,
  user_agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36",
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
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  window.location.hash = "";
  document.cookie = "veyra-csrf=; Max-Age=0; path=/";
});

describe("desktop Project workspace", () => {
  it("renders the normal New chat surface at #/projects and shows Recent in the sidebar", async () => {
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
    expect(document.querySelector(".nav-group-recent")).toBeInTheDocument();
    expect(screen.getByText("No recent chats yet.")).toBeInTheDocument();
    const fixedNav = document.querySelector(".sidebar-nav-fixed") as HTMLElement;
    const scrollNav = document.querySelector(".sidebar-nav-scroll") as HTMLElement;
    expect(within(fixedNav).getByRole("link", { name: "New chat" })).toBeInTheDocument();
    expect(within(fixedNav).getByRole("link", { name: "Community" })).toBeInTheDocument();
    expect(scrollNav.querySelector(".nav-group-projects")).not.toBeNull();
    expect(scrollNav.querySelector(".nav-group-recent")).not.toBeNull();
    expect(fixedNav.querySelector(".nav-group-projects")).toBeNull();
    expect(fixedNav.querySelector(".nav-group-recent")).toBeNull();
    expect(screen.getAllByRole("link", { name: /Alpha Project/ }).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Signal Review")).not.toBeInTheDocument();
    expect(screen.queryByText("Verified results")).not.toBeInTheDocument();

    expect(screen.queryByRole("heading", { name: "Projects", level: 2 })).not.toBeInTheDocument();
  });

  it("lists Recent chats on the home sidebar across Projects", async () => {
    const scoped = project({ project_id: "dddd", name: "dddd" });
    const api = apiFor([scoped]);
    Object.assign(api, {
      listBuilderActivity: vi.fn().mockResolvedValue({
        schema_version: "1.0",
        project_id: "",
        items: Array.from({ length: 6 }, (_, index) => ({
          kind: "conversation" as const,
          id: `conv-${index}`,
          conversation_id: `conv-${index}`,
          project_id: "dddd",
          title: `聊天 ${index}`,
          status: "succeeded",
          operation_kind: "resolve",
          occurred_at: new Date(Date.now() - index * 60_000).toISOString(),
        })),
      }),
    });
    await renderApp(api);
    const recent = document.querySelector(".nav-group-recent") as HTMLElement;
    expect(await within(recent).findByRole("link", { name: /聊天 0/ })).toHaveAttribute("href", projectRoutePaths.projectChat("dddd", "conv-0"));
    expect(within(recent).getAllByRole("link")).toHaveLength(6);
    expect(within(recent).queryByText("No recent chats yet.")).not.toBeInTheDocument();
  });

  it("lists Recent chats from every Project while inside one Project", async () => {
    const alpha = project({ project_id: "alpha", name: "Alpha Project" });
    const beta = project({ project_id: "beta", name: "Beta Project" });
    const api = apiFor([alpha, beta]);
    const listBuilderActivity = vi.fn().mockResolvedValue({
      schema_version: "1.0",
      project_id: "",
      items: [
        { kind: "conversation" as const, id: "c-alpha", conversation_id: "c-alpha", project_id: "alpha", title: "Alpha chat", status: "succeeded", operation_kind: "resolve", occurred_at: new Date(Date.now() - 60_000).toISOString() },
        { kind: "conversation" as const, id: "c-beta", conversation_id: "c-beta", project_id: "beta", title: "Beta chat", status: "succeeded", operation_kind: "resolve", occurred_at: new Date(Date.now() - 120_000).toISOString() },
      ],
    });
    Object.assign(api, { listBuilderActivity });
    window.location.hash = projectRoutePaths.project("alpha");
    await renderApp(api);
    await waitFor(() => expect(listBuilderActivity).toHaveBeenCalled());
    expect(listBuilderActivity.mock.calls[0]?.[0]).toBeUndefined();
    const recent = document.querySelector(".nav-group-recent") as HTMLElement;
    expect(await within(recent).findByRole("link", { name: /Alpha chat/ })).toHaveAttribute("href", projectRoutePaths.projectChat("alpha", "c-alpha"));
    expect(within(recent).getByRole("link", { name: /Beta chat/ })).toHaveAttribute("href", projectRoutePaths.projectChat("beta", "c-beta"));
  });

  it("folds the Projects heading next to the label and keeps the create action visible", async () => {
    const user = userEvent.setup();
    await renderApp(apiFor([project({ project_id: "p-one", name: "Alpha Project" })]));
    const projectsGroup = await screen.findByText("Projects", { selector: ".nav-group-projects .nav-group-label" }).then((label) => label.closest(".nav-group-projects") as HTMLElement);
    const fold = within(projectsGroup).getByRole("button", { name: "Collapse Projects" });
    const heading = fold.closest(".nav-group-heading");
    expect(fold).toContainElement(within(projectsGroup).getByText("Projects", { selector: ".nav-group-label" }));
    expect(heading?.firstElementChild).toBe(fold);
    expect(heading?.querySelector(".nav-group-action")).not.toBeNull();
    expect(within(projectsGroup).getByRole("link", { name: "Alpha Project" })).toBeInTheDocument();
    await user.click(within(projectsGroup).getByText("Projects", { selector: ".nav-group-label" }));
    expect(within(projectsGroup).getByRole("button", { name: "Expand Projects" })).toHaveAttribute("aria-expanded", "false");
    expect(within(projectsGroup).queryByRole("link", { name: "Alpha Project" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create Project" })).toBeInTheDocument();
    expect(window.localStorage.getItem("veyra.nav-section-collapsed.v1")).toContain('"projects":true');
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
    expect(document.querySelector(".sidebar-nav-scroll")?.contains(document.querySelector(".nav-group-pinned"))).toBe(true);
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
    const tree = project({ project_id: "tree", name: "Tree Project", agents: [{ agent_id: "agent-tree", slug: "tree-agent", name: "Tree Agent", description: "", pinned: false, source_path: "agents/tree/agent.vagent.yaml", source_file_hash: "tree-hash" }], agent_count: 1, workflows: [{ workflow_id: "workflow-tree", slug: "tree-workflow", name: "Tree Workflow", description: "", source_path: "workflows/tree/workflow.vworkflow.yaml", source_file_hash: "workflow-hash" }] });
    const user = userEvent.setup();
    const api = apiFor([tree]);
    api.updateAgent.mockResolvedValue(tree);
    await renderApp(api);

    await user.click(await screen.findByRole("button", { name: "Expand Project: Tree Project" }));
    const agentLink = screen.getByRole("link", { name: "Tree Agent" });
    expect(agentLink).toHaveAttribute("href", projectRoutePaths.agentDesign("tree", "agent-tree"));
    expect(screen.getByRole("link", { name: "Open App: Tree Agent" })).toHaveAttribute("href", projectRoutePaths.agent("tree", "agent-tree"));
    expect(screen.getByRole("link", { name: "Open App: Tree Workflow" })).toHaveAttribute("href", projectRoutePaths.workflowRun("tree", "workflow-tree"));
    expect(agentLink).toHaveClass("tone-instance", "kind-agent");
    expect(screen.getByRole("link", { name: "Agents" })).toHaveAttribute("href", projectRoutePaths.agents("tree"));
    expect(screen.getByRole("link", { name: "Agents" })).toHaveClass("tone-kind", "kind-agent");
    expect(screen.getByRole("link", { name: "Workflows" })).toHaveAttribute("href", projectRoutePaths.workflows("tree"));
    expect(screen.getByRole("link", { name: "Workflows" })).toHaveClass("tone-kind", "kind-workflow");
    expect(screen.getByRole("link", { name: "Knowledge" })).toHaveAttribute("href", projectRoutePaths.knowledge("tree"));
    expect(screen.getByRole("link", { name: "Files" })).toHaveAttribute("href", projectRoutePaths.files("tree"));
    expect(screen.getByRole("link", { name: "Files" })).toHaveClass("tone-kind", "kind-files");
    expect(screen.getByRole("link", { name: "Runs" })).toHaveAttribute("href", projectRoutePaths.runs("tree"));
    expect(screen.getByRole("link", { name: "Runs" })).toHaveClass("tone-kind", "kind-runs");
    expect(screen.getByRole("link", { name: "History" })).toHaveAttribute("href", "#/runs");
    const projectRow = document.querySelector(`.nav-group-projects .sidebar-nav-item-row`);
    const projectLink = projectRow?.querySelector(`a[href="${projectRoutePaths.project("tree")}"]`);
    expect(projectLink).toHaveClass("sidebar-nav-link");
    expect(projectLink).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("button", { name: "Collapse Project: Tree Project" })).toHaveClass("is-open");
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
    expect(within(tree as HTMLElement).getByRole("link", { name: "Files" })).toHaveClass("tone-kind", "kind-files");
    expect(within(tree as HTMLElement).getByRole("link", { name: "Runs" })).toHaveClass("tone-kind", "kind-runs");
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

  it("renders root and nested headers as the same breadcrumb path", async () => {
    setViewport(true);
    const nested = project({ project_id: "crumb", name: "Breadcrumb Project", agents: [{ agent_id: "crumb-agent", slug: "breadcrumb-agent", name: "Breadcrumb Agent", description: "", pinned: false, source_path: "agents/breadcrumb/agent.vagent.yaml", source_file_hash: "crumb-hash" }], agent_count: 1 });
    const api = apiFor([nested]);
    api.getProject.mockResolvedValue(nested);
    window.location.hash = projectRoutePaths.project("crumb");
    await renderApp(api);

    expect(await screen.findByLabelText("Breadcrumb")).toBeInTheDocument();
    const crumbs = screen.getByLabelText("Breadcrumb");
    expect(within(crumbs).getByRole("link", { name: "Home" })).toHaveAttribute("href", "#/projects");
    expect(within(crumbs).queryByRole("link", { name: "Breadcrumb Project" })).not.toBeInTheDocument();
    expect(within(crumbs).getByText("Breadcrumb Project").closest("[aria-current=page]")).toBeInTheDocument();
    expect(within(crumbs).getByText("Breadcrumb Project")).toHaveAttribute("title", "Breadcrumb Project");
    expect(screen.queryByRole("link", { name: "Back" })).not.toBeInTheDocument();
    expect(within(crumbs).getAllByText("Breadcrumb Project")).toHaveLength(1);
    cleanup();
    window.location.hash = "#/projects";
    await renderApp(apiFor());
    const rootCrumbs = await screen.findByLabelText("Breadcrumb");
    expect(within(rootCrumbs).getByText("New chat").closest("[aria-current=page]")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "New chat", level: 1 })).not.toBeInTheDocument();
    const menu = screen.getByRole("button", { name: "Open navigation" });
    await userEvent.click(menu);
    expect(screen.getAllByRole("button", { name: "Close navigation" })).toHaveLength(2);
  });

  it("deduplicates repeated Project records before rendering the sidebar", async () => {
    const duplicate = project({ project_id: "duplicate", name: "Duplicate Project" });
    await renderApp(apiFor([duplicate, duplicate]));

    expect(document.querySelectorAll('.nav-group-projects a[href="#/projects/duplicate"]')).toHaveLength(1);
  });

  it("uses Project-context navigation when a Project is opened from the sidebar", async () => {
    const scoped = project({ project_id: "project-open", name: "Opened Project" });
    const api = apiFor([scoped]);
    api.getProject.mockResolvedValue(scoped);
    api.listProjectFiles.mockResolvedValue({
      schema_version: "1.0",
      project_id: "project-open",
      files: [{ path: "README.md", kind: "readme", byte_length: 12 }],
    });
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
    expect(projectTreeLink).toHaveAttribute("aria-current", "page");
    expect(projectTreeLink).toHaveClass("active");
    expect(projectTreeLink).not.toHaveClass("contextual");
    expect(screen.getByRole("link", { name: "Workflows" })).toHaveAttribute("href", projectRoutePaths.workflows("project-open"));
    expect(screen.getByRole("link", { name: "Agents" })).toHaveClass("tone-kind");
    expect(await screen.findByRole("heading", { name: "Opened Project", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Collaboration" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /README.md/ })).toHaveAttribute("href", expect.stringContaining("#/files/"));
    expect(within(document.querySelector(".nav-group-projects") as HTMLElement).getByRole("link", { name: "Files" })).toHaveAttribute("href", projectRoutePaths.files("project-open"));
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

  it("offers a website entry for old Community routes without rendering the local catalog", async () => {
    window.location.hash = "#/community";
    const fetcher = signedInFetcher();
    await renderApp(apiFor(), accountApi(fetcher));
    expect(await screen.findByRole("heading", { name: "Community is on the web" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open Community website" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Discover" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Community" })).not.toBeInTheDocument();
    expect(screen.queryByText("Veyra Community")).not.toBeInTheDocument();
    expect(screen.queryByText("Discover useful Agents, Workflows, Skills, and Tools from the community.")).not.toBeInTheDocument();
    expect(screen.queryByText("Research Brief")).not.toBeInTheDocument();
    expect(screen.queryByText("4.8")).not.toBeInTheDocument();
    expect(fetcher.mock.calls.some(([input]) => String(input).includes("/registry/"))).toBe(false);
  });

  it("opens Community in the browser without leaving the current Desktop workspace", async () => {
    vi.stubEnv("VITE_COMMUNITY_SITE_URL", "https://community.example/");
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const user = userEvent.setup();
    await renderApp(apiFor());
    const currentRoute = window.location.hash;
    await user.click(screen.getByRole("link", { name: "Community" }));
    expect(open).toHaveBeenCalledWith("https://community.example/?lang=en#/community", "_blank", "noopener,noreferrer");
    expect(window.location.hash).toBe(currentRoute);
    expect(screen.queryByRole("heading", { name: "Community is on the web" })).not.toBeInTheDocument();
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
    expect(within(breadcrumbs).getByText("Child Agent").closest("[aria-current=page]")).toBeInTheDocument();
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

  it("shows the chat icon and conversation name in the header", () => {
    const scoped = project({ project_id: "chat-crumb", name: "Chat Project" });
    const named = desktopHeader(
      { kind: "project-chat", path: projectRoutePaths.projectChat("chat-crumb", "conv-1"), projectId: "chat-crumb", conversationId: "conv-1" },
      [scoped],
      "zh",
      { conversationTitle: "日程提醒整理 Agent" },
    );
    expect(named.title).toBe("日程提醒整理 Agent");
    expect(named.breadcrumbs?.map((item) => [item.label, item.href])).toEqual([
      ["Home", "#/projects"],
      ["Chat Project", projectRoutePaths.project("chat-crumb")],
      ["日程提醒整理 Agent", projectRoutePaths.projectChat("chat-crumb", "conv-1")],
    ]);
    const blank = desktopHeader(
      { kind: "project-chat", path: projectRoutePaths.projectChat("chat-crumb"), projectId: "chat-crumb" },
      [scoped],
      "zh",
    );
    expect(blank.title).toBe("新聊天");
    expect(blank.breadcrumbs?.map((item) => item.label)).toEqual(["Home", "Chat Project", "新聊天"]);
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
    expect(within(tree).getByRole("link", { name: "Runs" })).toHaveAttribute("href", projectRoutePaths.runs("agent-project"));
    expect(screen.getByRole("link", { name: "History" })).toHaveAttribute("href", projectRoutePaths.runs("agent-project"));
    expect(document.querySelector(".nav-group-recent")).toBeInTheDocument();
    expect(screen.getByText("No recent chats yet.")).toBeInTheDocument();
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
    expect(within(tree).getByRole("link", { name: "文件" })).toHaveClass("tone-kind", "kind-files");
    expect(within(tree).getByRole("link", { name: "运行记录" })).toHaveClass("tone-kind", "kind-runs");
    expect(screen.getByRole("link", { name: "历史" })).toHaveAttribute("href", projectRoutePaths.runs("agent-project-zh"));
    const agentTreeLink = tree.querySelector(`a[href="${projectRoutePaths.agentDesign("agent-project-zh", "agent-zh")}"]`);
    const projectTreeLink = tree.querySelector(`a[href="${projectRoutePaths.project("agent-project-zh")}"]`);
    expect(agentTreeLink).toHaveAttribute("aria-current", "page");
    expect(agentTreeLink).not.toHaveClass("contextual");
    expect(projectTreeLink).not.toHaveAttribute("aria-current");
    expect(projectTreeLink).not.toHaveClass("contextual");
    expect(screen.getByText("暂无最近聊天。")).toBeInTheDocument();
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
    expect(screen.getByRole("menuitem", { name: "Trash" })).toHaveAttribute("href", "#/trash");

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
    await waitFor(() => expect(menu).toHaveFocus());
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
    expect(within(screen.getByLabelText("Breadcrumb")).getByText("History").closest("[aria-current=page]")).toBeInTheDocument();

    window.location.hash = projectRoutePaths.project("history-project");
    await waitFor(() => expect(screen.getByRole("link", { name: "History" })).toHaveAttribute("href", projectRoutePaths.runs("history-project")));
    expect(screen.getByRole("link", { name: "History" })).not.toHaveAttribute("aria-current");
    await user.click(screen.getByRole("link", { name: "History" }));
    expect(window.location.hash).toBe(projectRoutePaths.runs("history-project"));
    await waitFor(() => expect(document.querySelector("a.history-control")).toHaveAttribute("aria-current", "page"));
    expect(within(document.querySelector(".nav-group-projects") as HTMLElement).getByRole("link", { name: "Runs" })).toHaveAttribute("href", projectRoutePaths.runs("history-project"));
    expect(within(document.querySelector(".nav-group-projects") as HTMLElement).getByRole("link", { name: "Runs" })).toHaveClass("active");
  });

  it("projects persisted Builder conversations into Recent without changing Runtime History", async () => {
    const scoped = project({ project_id: "dddd", name: "dddd" });
    const snapshot = {
      schema_version: "1.0" as const,
      conversation: {
        conversation_id: "conv-1",
        project_id: "dddd",
        title: "礼物包装 Agent",
        status: "active",
        created_at: "2026-09-18T00:00:00Z",
        updated_at: "2026-09-18T00:00:01Z",
        last_activity_at: "2026-09-18T00:00:01Z",
        last_operation_status: "failed" as const,
      },
      messages: [
        { message_id: "m-user", conversation_id: "conv-1", sequence: 0, role: "user" as const, kind: "user" as const, content: "帮我生成礼物包装 Agent", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:00Z" },
        { message_id: "m-fail", conversation_id: "conv-1", sequence: 1, role: "system" as const, kind: "failure" as const, content: "Agent 结构生成失败", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:01Z" },
      ],
      operations: [
        { operation_id: "op-1", conversation_id: "conv-1", kind: "create_agent", status: "failed" as const, retry_of: null, error_code: "factory_request_invalid", proposal_id: null, run_id: null, factory_session_id: null, created_at: "2026-09-18T00:00:00Z", updated_at: "2026-09-18T00:00:01Z", diagnostic: {}, has_request: true, target_kind: "agent" as const, events: [], receipts: [] },
      ],
      resolution: null,
      factory_session: null,
    };
    const api = apiFor([scoped]);
    const getBuilderConversation = vi.fn().mockResolvedValue(snapshot);
    Object.assign(api, {
      listBuilderActivity: vi.fn().mockResolvedValue({
        schema_version: "1.0",
        project_id: "dddd",
        items: [
          { kind: "conversation", id: "conv-1", conversation_id: "conv-1", title: "礼物包装 Agent", status: "failed", operation_kind: "create_agent", occurred_at: new Date(Date.now() - 120_000).toISOString() },
        ],
      }),
      getBuilderConversation,
      submitBuilderTurn: vi.fn(),
    });
    window.location.hash = projectRoutePaths.projectChat("dddd");
    await renderApp(api);
    const recent = document.querySelector(".nav-group-recent") as HTMLElement;
    const conversation = await within(recent).findByRole("link", { name: /礼物包装 Agent/ });
    expect(conversation).toHaveAttribute("href", projectRoutePaths.projectChat("dddd", "conv-1"));
    expect(within(recent).queryByText(/Create Agent ·/)).not.toBeInTheDocument();
    expect(within(recent).queryByText(/Failed/)).not.toBeInTheDocument();
    expect(within(recent).queryByText(/Run ·/)).not.toBeInTheDocument();
    expect(within(recent).getByRole("button", { name: "Chat actions: 礼物包装 Agent" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "History" })).toHaveAttribute("href", projectRoutePaths.runs("dddd"));
    fireEvent.click(within(recent).getByRole("button", { name: "Chat actions: 礼物包装 Agent" }));
    expect(screen.getByRole("menuitem", { name: "Pin" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Delete" })).toBeInTheDocument();
    fireEvent.click(conversation);
    await waitFor(() => expect(getBuilderConversation).toHaveBeenCalledWith("dddd", "conv-1"));
    expect(await screen.findByText("帮我生成礼物包装 Agent")).toBeInTheDocument();
    expect(screen.getByText("Agent 结构生成失败")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "History" })).toHaveAttribute("href", projectRoutePaths.runs("dddd"));
    const crumbs = screen.getByLabelText("Breadcrumb");
    expect(within(crumbs).getByText("礼物包装 Agent").closest("[aria-current=page]")).toBeInTheDocument();
    expect(within(crumbs).getByText("Home")).toBeInTheDocument();
    expect(within(crumbs).getByText("dddd")).toBeInTheDocument();
    expect(within(crumbs).queryByText("New chat")).not.toBeInTheDocument();
    const projectTreeLink = document.querySelector(`.nav-group-projects a[href="${projectRoutePaths.project("dddd")}"]`);
    expect(projectTreeLink).toHaveClass("contextual");
    expect(projectTreeLink).not.toHaveAttribute("aria-current");
    expect(conversation).toHaveAttribute("aria-current", "page");
    expect(conversation).toHaveClass("active");
  });

  it("makes Recent chat pin, rename, and Trash actions execute", async () => {
    const user = userEvent.setup();
    const scoped = project({ project_id: "recent-actions", name: "Recent Actions" });
    const api = apiFor([scoped]);
    const activity = {
      schema_version: "1.0" as const,
      project_id: "recent-actions",
      items: [{
        kind: "conversation" as const,
        id: "conv-actions",
        conversation_id: "conv-actions",
        title: "日程提醒整理 Agent",
        status: "succeeded",
        operation_kind: "create_agent",
        occurred_at: new Date(Date.now() - 60_000).toISOString(),
      }],
    };
    Object.assign(api, {
      listBuilderActivity: vi.fn().mockResolvedValue(activity),
      renameBuilderConversation: vi.fn().mockResolvedValue({}),
      deleteBuilderConversation: vi.fn().mockResolvedValue({ schema_version: "1.0", conversation_id: "conv-actions", deleted: true }),
    });
    window.location.hash = projectRoutePaths.projectChat("recent-actions");
    await renderApp(api);
    const recent = document.querySelector(".nav-group-recent") as HTMLElement;
    const actions = () => within(recent).getByRole("button", { name: "Chat actions: 日程提醒整理 Agent" });

    await user.click(actions());
    await user.click(screen.getByRole("menuitem", { name: "Pin" }));
    expect(window.localStorage.getItem("veyra.sidebar-resource-pins")).toContain("conv-actions");

    await user.click(actions());
    await user.click(screen.getByRole("menuitem", { name: "Edit" }));
    const name = screen.getByLabelText("Chat name");
    await user.clear(name);
    await user.type(name, "提醒整理");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.renameBuilderConversation).toHaveBeenCalledWith("recent-actions", "conv-actions", { title: "提醒整理" }));

    await user.click(actions());
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    expect(screen.getByRole("dialog", { name: "Move chat to Trash?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Move to Trash" }));
    await waitFor(() => expect(api.deleteBuilderConversation).toHaveBeenCalledWith("recent-actions", "conv-actions"));
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
    const submitBuilderTurn = vi.fn(() => new Promise<never>(() => undefined));
    Object.assign(api, { submitBuilderTurn });
    const user = userEvent.setup();
    await renderApp(api);
    await user.type(await screen.findByRole("textbox", { name: "Message" }), "Write a brief");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(api.createProject).toHaveBeenCalledWith({ description: "" }));
    expect(window.location.hash).toBe("#/projects/created-project/chat");
    await waitFor(() => expect(submitBuilderTurn).toHaveBeenCalledTimes(1));
    expect(submitBuilderTurn).toHaveBeenCalledWith(
      "created-project",
      expect.objectContaining({ content: "Write a brief" }),
      expect.anything(),
    );
    expect(await screen.findByText("Write a brief")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("");
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

  it("opens the selected Agent Builder context from the composer picker", async () => {
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
    expect(window.location.hash).toBe("#/projects/p-one/chat?target=agent:agent-1");
    expect(await screen.findByRole("complementary", { name: "Workbench" })).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Build target" })).not.toBeInTheDocument();
    const sidebar = document.querySelector(".nav-group-fixed") as HTMLElement;
    expect(within(sidebar).getByRole("link", { name: "Back to home" })).toHaveAttribute("href", "#/projects");
    expect(within(sidebar).getByRole("link", { name: "New chat" })).toHaveAttribute("href", projectRoutePaths.projectChat("p-one"));
    expect(within(sidebar).getByRole("link", { name: "Project resources" })).toHaveAttribute("href", projectRoutePaths.projectResources("p-one"));
    const agentTreeLink = document.querySelector(`.nav-group-projects a[href="${projectRoutePaths.agentDesign("p-one", "agent-1")}"]`);
    expect(agentTreeLink).not.toHaveAttribute("aria-current");
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

  it("opens the Electron workspace and Community website independently of the Community API", async () => {
    vi.stubEnv("VITE_COMMUNITY_SITE_URL", "https://community.example/");
    const openExternal = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("veyraDesktop", { openExternal });
    document.cookie = "veyra-csrf=stale-csrf; path=/";
    const fetcher = vi.fn(async () => jsonResponse(503, { detail: "community_unavailable" }));
    const api = apiFor();
    const user = userEvent.setup();
    render(<DesktopApp api={api} communityApi={accountApi(fetcher)} />);

    expect(await screen.findByRole("heading", { name: "What do you want to achieve in a new project?" })).toBeInTheDocument();
    expect(api.listProjects).toHaveBeenCalled();
    expect(window.location.hash).toBe("#/projects");
    expect(fetcher).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Open account menu" }));
    await user.click(screen.getByRole("menuitem", { name: "Sign in or register" }));
    expect(openExternal).toHaveBeenCalledWith("https://community.example/?lang=en#/community/mine");
    expect(window.location.hash).toBe("#/projects");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("offers the Community website from a legacy account route in Electron", async () => {
    vi.stubEnv("VITE_COMMUNITY_SITE_URL", "https://community.example/");
    const openExternal = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("veyraDesktop", { openExternal });
    window.location.hash = "#/account";
    const user = userEvent.setup();
    render(<DesktopApp api={apiFor()} />);

    expect(await screen.findByRole("heading", { name: "Community is on the web" })).toBeInTheDocument();
    expect(openExternal).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Open Community website" }));
    expect(openExternal).toHaveBeenCalledWith("https://community.example/?lang=en#/community/mine");
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
    expect(screen.getByRole("heading", { name: "Alice", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Public profile" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Device records" })).toBeInTheDocument();
    expect(screen.getByText("Mac · Chrome")).toBeInTheDocument();
    expect(screen.getByText("1 active session")).toBeInTheDocument();
    expect(screen.getByText("Account access")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Creator workspace/ })).toHaveAttribute("href", communityRoutePaths.mine);
    expect(screen.getByRole("link", { name: /Published releases/ })).toHaveAttribute("href", communityRoutePaths.published);
    expect(screen.getByRole("link", { name: /Saved resources/ })).toHaveAttribute("href", communityRoutePaths.starred);
    expect(screen.getByText("What stays on this device")).toBeInTheDocument();
    expect(screen.getByText("Project, Agent, and Workflow source files")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open account menu" }));
    expect(screen.getByRole("menuitem", { name: "Account" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Sign out" })).toBeInTheDocument();

    const avatarInput = screen.getByLabelText("Choose avatar");
    expect(avatarInput).toHaveAttribute("accept", "image/png,image/jpeg,image/webp");
    const file = new File(["png bytes"], "avatar.png", { type: "image/png" });
    await user.upload(avatarInput, file);
    await user.click(screen.getAllByRole("button", { name: "Save profile" })[0]!);
    expect(await screen.findByText("Avatar updated.")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Avatar preview" })).toHaveAttribute("src", "/community-api/api/v1/avatars/account-desktop");
    expect(document.querySelector(".shell-account-trigger .shell-account-avatar img")).toHaveAttribute("src", "/community-api/api/v1/avatars/account-desktop");
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

  it("marks Account, Settings, and Trash in the account menu when those pages are current", async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <ApplicationShell
          brand={{ name: "Veyra", subtitle: "Agent Platform" }}
          navigation={[{ label: "Build", items: [{ href: "#/projects", label: "Projects", icon: FolderKanban }] }]}
          activeHref="#/trash"
          eyebrow="Workspace"
          title="Trash"
          account={{ displayName: "Ada", authenticated: true, accountHref: "#/account", settingsHref: "#/settings", trashHref: "#/trash" }}
        >
          <div>Trash content</div>
        </ApplicationShell>
      </ThemeProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Open account menu" }));
    expect(screen.getByRole("menuitem", { name: "Trash" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("menuitem", { name: "Trash" })).toHaveClass("is-current");
    expect(screen.getByRole("menuitem", { name: "Account" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("menuitem", { name: "Settings" })).not.toHaveAttribute("aria-current");
    const { readFileSync } = await import("node:fs");
    const { dirname, join } = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const shellCss = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "../../../packages/ui/src/styles/shell.css"),
      "utf8",
    );
    expect(shellCss).toMatch(/\.shell-account-menu-item\.is-current svg[\s\S]*?color:\s*var\(--nav-active-ink\)/);
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

  it("hides the sidebar completely and keeps the fold control in the header", async () => {
    const user = userEvent.setup();
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
    const collapse = screen.getByRole("button", { name: "Collapse sidebar" });
    expect(collapse.closest(".app-sidebar")).not.toBeNull();
    await user.click(collapse);
    expect(document.querySelector(".app-shell")).toHaveClass("is-collapsed");
    expect(document.getElementById("primary-navigation")).toHaveAttribute("aria-hidden", "true");
    expect(screen.queryByRole("separator", { name: "Resize sidebar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Projects" })).not.toBeInTheDocument();
    const expand = screen.getByRole("button", { name: "Expand sidebar" });
    expect(expand.closest(".app-header")).not.toBeNull();
    expect(window.localStorage.getItem("veyra.sidebar-collapsed.v1")).toBe("true");
    await user.click(expand);
    expect(document.querySelector(".app-shell")).not.toHaveClass("is-collapsed");
    expect(screen.getByRole("button", { name: "Collapse sidebar" }).closest(".app-sidebar")).not.toBeNull();
    expect(screen.getByRole("link", { name: "Projects" })).toBeInTheDocument();
  });

  it("places fold controls beside pinned, projects, and recent labels and persists the closed state", async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <ApplicationShell
          brand={{ name: "Veyra", subtitle: "Agent Platform" }}
          navigation={[
            { label: "Build", section: "fixed", items: [{ href: "#/projects", label: "Workspace Home", icon: FolderKanban }] },
            { label: "Pinned", section: "pinned", items: [{ href: "#/projects/pin", label: "Pinned One", icon: FolderKanban }] },
            { label: "Projects", section: "projects", action: <span className="nav-group-action-slot">+</span>, items: [{ href: "#/projects/listed", label: "Listed Project", icon: FolderKanban }] },
            { label: "Recent", section: "recent", items: [{ href: "#/projects/listed/chat", label: "Recent chat", icon: FolderKanban }] },
          ]}
          activeHref="#/projects"
          eyebrow="Workspace"
          title="Projects"
        >
          <div>Workspace content</div>
        </ApplicationShell>
      </ThemeProvider>,
    );
    expect(screen.queryByRole("button", { name: "Collapse Build" })).not.toBeInTheDocument();
    expect(document.querySelector(".sidebar-nav-fixed")?.querySelector(".nav-group-fixed")).not.toBeNull();
    expect(document.querySelector(".sidebar-nav-scroll")?.contains(document.querySelector(".nav-group-pinned"))).toBe(true);
    expect(document.querySelector(".sidebar-nav-scroll")?.contains(document.querySelector(".nav-group-projects"))).toBe(true);
    expect(document.querySelector(".sidebar-nav-scroll")?.contains(document.querySelector(".nav-group-recent"))).toBe(true);
    const pinnedFold = screen.getByRole("button", { name: "Collapse Pinned" });
    const projectsFold = screen.getByRole("button", { name: "Collapse Projects" });
    const recentFold = screen.getByRole("button", { name: "Collapse Recent" });
    expect(pinnedFold.querySelector(".nav-group-label")).toHaveTextContent("Pinned");
    expect(projectsFold.nextElementSibling).toHaveClass("nav-group-action");
    expect(recentFold.querySelector(".nav-group-label")).toHaveTextContent("Recent");
    await user.click(screen.getByText("Pinned", { selector: ".nav-group-pinned .nav-group-label" }));
    expect(screen.getByRole("button", { name: "Expand Pinned" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: "Pinned One" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Listed Project" })).toBeInTheDocument();
    await user.click(projectsFold);
    await user.click(recentFold);
    expect(screen.queryByRole("link", { name: "Listed Project" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Recent chat" })).not.toBeInTheDocument();
    expect(JSON.parse(window.localStorage.getItem("veyra.nav-section-collapsed.v1") ?? "{}")).toEqual({
      pinned: true,
      projects: true,
      recent: true,
    });
  });

  it("does not reserve a pinned slot when the pinned group is absent", () => {
    render(
      <ThemeProvider>
        <ApplicationShell
          brand={{ name: "Veyra", subtitle: "Agent Platform" }}
          navigation={[
            { label: "Build", section: "fixed", items: [{ href: "#/projects", label: "Workspace Home", icon: FolderKanban }] },
            { label: "Projects", section: "projects", action: <span className="nav-group-action-slot">+</span>, items: [] },
            { label: "Recent", section: "recent", items: [{ href: "#/projects/listed/chat", label: "Recent chat", icon: FolderKanban }] },
          ]}
          activeHref="#/projects"
          eyebrow="Workspace"
          title="Projects"
        >
          <div>Workspace content</div>
        </ApplicationShell>
      </ThemeProvider>,
    );
    const scrollNav = document.querySelector(".sidebar-nav-scroll") as HTMLElement;
    expect(scrollNav.querySelector(".nav-group-pinned")).toBeNull();
    expect(scrollNav.style.getPropertyValue("--nav-sticky-first")).toBe("0px");
    expect(scrollNav.style.getPropertyValue("--nav-sticky-rest")).toBe("39px");
  });

  it("sticks original section headers and auto-folds upper section bodies while scrolling", async () => {
    const { readFileSync } = await import("node:fs");
    const { dirname, join } = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const shellCss = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "../../../packages/ui/src/styles/shell.css"),
      "utf8",
    );
    expect(shellCss).toMatch(/\.nav-group-chrome\s*\{[\s\S]*?position:\s*sticky;/);
    expect(shellCss).toMatch(/\.nav-group-chrome\s*\{[\s\S]*?padding:\s*8px 0;/);
    expect(shellCss).toMatch(/\.nav-group-pinned\s*>\s*\.nav-group-chrome\s*\{[\s\S]*?top:\s*0;/);
    expect(shellCss).toMatch(/\.nav-group-projects\s*>\s*\.nav-group-chrome\s*\{[\s\S]*?top:\s*var\(--nav-sticky-first/);
    expect(shellCss).toMatch(/\.nav-group-recent\s*>\s*\.nav-group-chrome\s*\{[\s\S]*?top:\s*calc\(var\(--nav-sticky-first/);
    expect(shellCss).toMatch(/\.nav-group-body\s*\{[\s\S]*?transition:\s*grid-template-rows\s+180ms/);
    expect(shellCss).not.toMatch(/nav-sticky-stack/);
    expect(shellCss).not.toMatch(/is-auto-sticky/);

    function mockBox(node: Element, top: number, height: number) {
      (node as HTMLElement).getBoundingClientRect = () => ({
        x: 0,
        y: top,
        width: 240,
        height,
        top,
        right: 240,
        bottom: top + height,
        left: 0,
        toJSON() {
          return {};
        },
      });
    }

    render(
      <ThemeProvider>
        <ApplicationShell
          brand={{ name: "Veyra", subtitle: "Agent Platform" }}
          navigation={[
            { label: "Build", section: "fixed", items: [{ href: "#/projects", label: "Workspace Home", icon: FolderKanban }] },
            { label: "Pinned", section: "pinned", items: [{ href: "#/projects/pin", label: "Pinned One", icon: FolderKanban }] },
            { label: "Projects", section: "projects", action: <span className="nav-group-action-slot">+</span>, items: [{ href: "#/projects/listed", label: "Listed Project", icon: FolderKanban }] },
            { label: "Recent", section: "recent", items: [{ href: "#/projects/listed/chat", label: "Recent chat", icon: FolderKanban }] },
          ]}
          activeHref="#/projects"
          eyebrow="Workspace"
          title="Projects"
        >
          <div>Workspace content</div>
        </ApplicationShell>
      </ThemeProvider>,
    );
    const scrollNav = document.querySelector(".sidebar-nav-scroll") as HTMLElement;
    const pinned = document.querySelector(".nav-group-pinned") as HTMLElement;
    const projects = document.querySelector(".nav-group-projects") as HTMLElement;
    const recent = document.querySelector(".nav-group-recent") as HTMLElement;
    expect(document.querySelector(".nav-sticky-stack")).not.toBeInTheDocument();
    expect(pinned.querySelector(".nav-group-heading")).not.toBeNull();
    expect(projects.querySelector(".nav-group-heading")).not.toBeNull();
    expect(recent.querySelector(".nav-group-heading")).not.toBeNull();

    Object.defineProperty(scrollNav, "clientHeight", { configurable: true, value: 400 });
    Object.defineProperty(scrollNav, "scrollTop", { configurable: true, writable: true, value: 0 });
    mockBox(scrollNav, 0, 400);
    mockBox(pinned.querySelector(".nav-group-chrome") as HTMLElement, 0, 38);
    mockBox(pinned.querySelector(".nav-group-body") as HTMLElement, -160, 200);
    Object.defineProperty(pinned.querySelector(".nav-group-body-inner") as HTMLElement, "scrollHeight", { configurable: true, value: 200 });
    mockBox(projects.querySelector(".nav-group-chrome") as HTMLElement, 38, 39);
    mockBox(projects.querySelector(".nav-group-body") as HTMLElement, 77, 200);
    Object.defineProperty(projects.querySelector(".nav-group-body-inner") as HTMLElement, "scrollHeight", { configurable: true, value: 200 });
    mockBox(recent.querySelector(".nav-group-chrome") as HTMLElement, 277, 39);
    mockBox(recent.querySelector(".nav-group-body") as HTMLElement, 316, 400);
    Object.defineProperty(recent.querySelector(".nav-group-body-inner") as HTMLElement, "scrollHeight", { configurable: true, value: 400 });

    scrollNav.scrollTop = 180;
    fireEvent.scroll(scrollNav);
    await waitFor(() => expect(pinned).toHaveClass("is-scroll-folded"));
    expect(within(pinned).getByRole("button", { name: "Expand Pinned" })).toHaveAttribute("aria-expanded", "false");
    expect(within(projects).getByRole("button", { name: "Collapse Projects" })).toHaveAttribute("aria-expanded", "true");
    expect(within(recent).getByRole("button", { name: "Collapse Recent" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.queryByRole("link", { name: "Pinned One" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Listed Project" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Recent chat" })).toBeInTheDocument();
    expect(JSON.parse(window.localStorage.getItem("veyra.nav-section-collapsed.v1") ?? "{}")).toEqual({
      pinned: false,
      projects: false,
      recent: false,
    });

    const user = userEvent.setup();
    await user.click(within(pinned).getByRole("button", { name: "Expand Pinned" }));
    await waitFor(() => expect(pinned).not.toHaveClass("is-scroll-folded"));
    expect(screen.getByRole("link", { name: "Pinned One" })).toBeInTheDocument();
    expect(JSON.parse(window.localStorage.getItem("veyra.nav-section-collapsed.v1") ?? "{}")).toEqual({
      pinned: false,
      projects: false,
      recent: false,
    });
    await user.click(within(pinned).getByRole("button", { name: "Collapse Pinned" }));
    expect(pinned).toHaveClass("is-folded");
    expect(JSON.parse(window.localStorage.getItem("veyra.nav-section-collapsed.v1") ?? "{}")).toEqual({
      pinned: true,
      projects: false,
      recent: false,
    });
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
    expect(parseDesktopRoute(projectRoutePaths.projectChat("p", "conv-1"))).toMatchObject({ kind: "project-chat", conversationId: "conv-1" });
    expect(parseDesktopRoute(projectRoutePaths.projectAnalysis("p")).kind).toBe("project-analysis");
    expect(parseDesktopRoute(projectRoutePaths.agents("p")).kind).toBe("project-agents");
    expect(parseDesktopRoute(projectRoutePaths.agent("p", "a")).kind).toBe("agent-detail");
    expect(parseDesktopRoute(projectRoutePaths.agentVersion("p", "a", "v1")).kind).toBe("agent-version");
    expect(parseDesktopRoute(projectRoutePaths.agentAnalysis("p", "a")).kind).toBe("agent-analysis");
    expect(parseDesktopRoute("#/components").kind).toBe("components");
    expect(parseDesktopRoute("#/files").kind).toBe("files");
    expect(parseDesktopRoute("#/runs").kind).toBe("runs");
    expect(parseDesktopRoute("#/monitor").kind).toBe("monitor");
    expect(parseDesktopRoute("#/trash").kind).toBe("trash");
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
    expect(parseDesktopRoute(projectRoutePaths.workflowRun("p", "w"))).toMatchObject({ kind: "project-workflow-run", projectId: "p", workflowId: "w" });
    expect(parseDesktopRoute(projectRoutePaths.knowledge("p")).kind).toBe("project-knowledge");
    expect(parseDesktopRoute(projectRoutePaths.knowledgeItem("p", "k")).kind).toBe("project-knowledge-item");
    expect(parseDesktopRoute(projectRoutePaths.files("p")).kind).toBe("project-files");
    expect(parseDesktopRoute(projectRoutePaths.runs("p")).kind).toBe("project-runs");
    expect(parseDesktopRoute(projectRoutePaths.agentDesignFromWorkflow("p", "a", "w"))).toMatchObject({ kind: "agent-design", agentId: "a", workflowId: "w" });
  });
});
