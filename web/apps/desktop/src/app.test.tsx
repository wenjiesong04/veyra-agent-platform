import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FolderKanban } from "lucide-react";
import { parseDesktopRoute, projectRoutePaths, type CommunityAccount, type ProjectSummaryResponse } from "@veyra/api-contracts";
import { createCommunityApi, normalizeCommunityAvatarUrl } from "@veyra/connected-account";
import { ApplicationShell, ThemeProvider } from "@veyra/ui";
import type { LocalProjectApi } from "./api/local-client";
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
} {
  const getProject = vi.fn().mockImplementation(async (projectId: string) => project({ project_id: projectId, name: projectId }));
  return {
    listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects }),
    createProject: vi.fn().mockResolvedValue(project({ project_id: "created-project", name: "Created Project", root_path: "/tmp/created-project" })),
    openProject: vi.fn().mockResolvedValue(project({ project_id: "opened-project", name: "Opened Project", root_path: "/tmp/opened-project" })),
    selectDirectory: vi.fn().mockResolvedValue({ schema_version: "1.0", status: "selected", root_path: "/tmp/selected-folder" }),
    getProject,
    updateProject: vi.fn().mockImplementation(async (projectId: string, input: { pinned: boolean }) => project({ project_id: projectId, name: projectId, pinned: input.pinned, pinned_at: input.pinned ? "2026-08-28T00:00:00Z" : null })),
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
    const second = project({ project_id: "p-two", name: "Beta Project", root_path: "/Users/test/Projects/project-two", agents: [{ agent_id: "agent-1", slug: "reviewer", source_path: "agents/reviewer/agent.vagent.yaml", source_file_hash: "fedcba9876543210" }] });
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

  it("creates a Project from the global picker dialog without navigating away from the current surface", async () => {
    const api = apiFor();
    const created = project({ project_id: "created-project", name: "Created Project", root_path: "/tmp/created-project" });
    api.createProject.mockResolvedValue(created);
    api.listProjects.mockResolvedValueOnce({ schema_version: "1.0", projects: [] }).mockRejectedValueOnce(new Error("refresh unavailable"));
    api.selectDirectory.mockResolvedValue({ schema_version: "1.0", status: "selected", root_path: "/tmp/created-project" });
    const user = userEvent.setup();
    render(<DesktopApp api={api} />);

    await user.click(await screen.findByRole("button", { name: "Create Project" }));
    expect(screen.getByRole("dialog", { name: "Create project" })).toBeInTheDocument();
    await user.type(await screen.findByRole("textbox", { name: "Project name" }), "Created Project");
    expect(screen.queryByRole("textbox", { name: /path/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/Connect project/i)).not.toBeInTheDocument();
    expect(screen.getByText("Choose a folder for this project.")).toBeInTheDocument();
    expect(screen.queryByText(/path/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Select folder" }));
    expect(await screen.findByText("Selected: created-project")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(api.createProject).toHaveBeenCalledWith({ root_path: "/tmp/created-project", name: "Created Project", description: "" }));
    expect(window.location.hash).toBe("#/projects");
    expect(await screen.findByRole("heading", { name: "New chat", level: 2 })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByText("refresh unavailable")).not.toBeInTheDocument();
  });

  it("opens an existing Project from the sidebar ellipsis menu through the same picker", async () => {
    const api = apiFor();
    const opened = project({ project_id: "opened-project", name: "Opened Project", root_path: "/tmp/opened-project" });
    api.openProject.mockResolvedValue(opened);
    api.selectDirectory.mockResolvedValue({ schema_version: "1.0", status: "selected", root_path: "/tmp/opened-project" });
    const user = userEvent.setup();
    render(<DesktopApp api={api} />);

    await user.click(await screen.findByRole("button", { name: "Project actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Open existing project" }));
    await user.click(screen.getByRole("button", { name: "Select folder" }));
    await user.click(screen.getByRole("button", { name: "Open project" }));

    await waitFor(() => expect(api.openProject).toHaveBeenCalledWith({ root_path: "/tmp/opened-project" }));
    expect(window.location.hash).toBe("#/projects");
  });

  it("keeps picker cancellation and errors recoverable", async () => {
    const api = apiFor();
    api.selectDirectory.mockResolvedValueOnce({ schema_version: "1.0", status: "cancelled", root_path: null }).mockRejectedValueOnce(new Error("picker unavailable"));
    const user = userEvent.setup();
    render(<DesktopApp api={api} />);
    await user.click(await screen.findByRole("button", { name: "Create Project" }));
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
        { agent_id: "agent-a", slug: "reviewer", source_path: "agents/reviewer/agent.vagent.yaml", source_file_hash: "aaaaaaaaaaaaaaaa" },
        { agent_id: "agent-b", slug: "verifier", source_path: "agents/verifier/agent.vagent.yaml", source_file_hash: "bbbbbbbbbbbbbbbb" },
      ],
    });
    const api = apiFor([detailed]);
    api.getProject.mockResolvedValue(detailed);
    window.location.hash = projectRoutePaths.project("p-detail");
    render(<DesktopApp api={api} />);

    expect(await screen.findByRole("heading", { name: "Evidence Project", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "2 Agents" })).toBeInTheDocument();
    expect(screen.getByText("reviewer")).toBeInTheDocument();
    expect(screen.getByText("agents/reviewer/agent.vagent.yaml", { exact: false })).toBeInTheDocument();
    expect(screen.queryByText("Agents will be added later.")).not.toBeInTheDocument();
    expect(api.getProject).toHaveBeenCalledWith("p-detail");
  });

  it("keeps pinned Projects first and updates the pin through the local API", async () => {
    const pinned = project({ project_id: "pinned", name: "Pinned Project", pinned: true, pinned_at: "2026-08-28T08:00:00Z" });
    const others = Array.from({ length: 10 }, (_, index) => project({ project_id: `project-${index}`, name: `Project ${index}`, indexed_at: `2026-08-28T0${index}:00:00Z` }));
    const api = apiFor([others[0]!, pinned, ...others.slice(1)]);
    api.getProject.mockResolvedValue(project({ project_id: "project-0", name: "Project 0" }));
    render(<DesktopApp api={api} />);

    await screen.findByRole("link", { name: "Pinned Project" });
    const sidebarLinks = [...document.querySelectorAll(".nav-group-projects a")].map((link) => link.getAttribute("aria-label"));
    expect(sidebarLinks[0]).toBe("Pinned Project");
    expect(sidebarLinks).toHaveLength(9);
    expect(sidebarLinks).not.toContain("Project 0");

    await userEvent.click(screen.getByRole("button", { name: "Unpin Project" }));
    await waitFor(() => expect(api.updateProject).toHaveBeenCalledWith("pinned", { pinned: false }));
    expect(window.location.hash).toBe("#/projects");
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
    expect(await screen.findByText("Chat and Agent generation will be enabled in the Factory phase.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Switch to Chinese" }));
    expect(await screen.findByText("聊天与 Agent 生成会在 Factory 阶段启用。")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "新聊天" })).toHaveAttribute("href", "#/chat");
    expect(screen.getByRole("link", { name: "运行工作台" })).toHaveAttribute("href", "#/monitor");
    expect(screen.getByRole("link", { name: "资源库" })).toHaveAttribute("href", "#/components");
    expect(screen.getByRole("link", { name: "知识库" })).toHaveAttribute("href", "#/files");
  });

  it("renders the Factory-phase new chat placeholder instead of a generic route error", async () => {
    window.location.hash = "#/chat";
    render(<DesktopApp api={apiFor()} />);
    expect(await screen.findByRole("heading", { name: "New chat", level: 2 })).toBeInTheDocument();
    expect(screen.getByText("Chat and Agent generation will be enabled in the Factory phase.")).toBeInTheDocument();
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
