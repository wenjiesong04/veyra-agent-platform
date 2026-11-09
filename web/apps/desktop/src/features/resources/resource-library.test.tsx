import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ListResourcesResponse, ProjectResourcesResponse, ResourceDescriptor } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { ProjectWorkspaceProvider } from "../../api/project-workspace";
import { LocalApiClientError, type LocalProjectApi } from "../../api/local-client";
import { ResourceLibraryPage } from "./resource-library";

function descriptor(kind: "component" | "tool" | "mcp_tool" | "skill" | "policy" | "template", name: string, id: string, availability: "ready" | "design_only" | "unavailable" | "requires_configuration" = "ready"): ResourceDescriptor {
  return {
    schema_version: "1.0",
    resource_id: `veyra.${kind}.${id}`,
    kind,
    version: "1.0.0",
    reference: `veyra.${kind}.${id}@1.0.0`,
    name,
    description: `${name} description`,
    origin: "builtin",
    content_hash: "a".repeat(64),
    availability,
    factory_selectable: availability !== "unavailable" && availability !== "requires_configuration",
    runtime_status: availability === "ready" ? "supported" : availability === "requires_configuration" ? "runtime_not_configured" : "runtime_not_supported",
    required_permissions: { network_hosts: [], tools: [], filesystem_read_roots: [], filesystem_write_roots: [], shell_workspace_only: false },
    tags: [kind, "builtin"],
    spec: { label: name },
  } as const;
}

const components = [descriptor("component", "Start", "start"), descriptor("component", "Agent", "agent", "requires_configuration")];
const skills = [descriptor("skill", "Research Brief", "research-brief", "requires_configuration"), descriptor("skill", "Document Analyzer", "document-analyzer", "requires_configuration")];
const policies = [descriptor("policy", "Local Only", "local-only"), descriptor("policy", "Verification Required", "verification-required")];
const tools = [
  descriptor("tool", "Filesystem Read", "filesystem.read", "design_only"),
  descriptor("tool", "GitHub Read", "github.read", "unavailable"),
];
const mcp = [descriptor("mcp_tool", "MCP Call", "call", "requires_configuration")];
const catalog = [...components, ...skills, ...policies, ...tools, ...mcp];

function apiFor(extra: unknown[] = []): LocalProjectApi & { listResources: ReturnType<typeof vi.fn>; getResource: ReturnType<typeof vi.fn> } {
  const listResources = vi.fn(async ({ kind }: { kind?: string } = {}): Promise<ListResourcesResponse> => {
    const allResources = [...catalog, ...extra] as typeof catalog;
    const resources = kind ? allResources.filter((item) => item.kind === kind) : allResources;
    return { schema_version: "1.0", resources: resources as never, kinds: ["component", "tool", "mcp_tool", "skill", "policy", "template"].map((item) => ({ kind: item, count: resources.filter((resource) => resource.kind === item).length })) as never };
  });
  const getResource = vi.fn(async (resourceId: string) => skills.find((resource) => resource.resource_id === resourceId));
  return {
    listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
    createProject: vi.fn(), openProject: vi.fn(), getProject: vi.fn(), updateProject: vi.fn(), deleteProject: vi.fn(),
    updateAgent: vi.fn(), deleteAgent: vi.fn(), listAgentTemplates: vi.fn(), createAgent: vi.fn(), importAgent: vi.fn(), getDraft: vi.fn(), selectDirectory: vi.fn(),
    listResources, getResource,
  } as unknown as LocalProjectApi & { listResources: ReturnType<typeof vi.fn>; getResource: ReturnType<typeof vi.fn> };
}

function renderPage(api: LocalProjectApi) {
  return render(<ThemeProvider><ProjectWorkspaceProvider api={api}><ResourceLibraryPage /></ProjectWorkspaceProvider></ThemeProvider>);
}

afterEach(() => {
  cleanup();
  window.location.hash = "";
});

describe("ResourceLibraryPage", () => {
  it("adds an exact identity once and reloads server-owned bindings with a Project link", async () => {
    const api = apiFor();
    const empty: ProjectResourcesResponse = { schema_version: "1.0", project_id: "project-1", resources: [], missing_references: [], project_count: 0, used_count: 0, unbound_count: 0, builtin_count: 0 };
    const bound: ProjectResourcesResponse = { ...empty, project_count: 1, resources: [{ ...skills[0]!, scope: "project", binding_status: "current", binding_source: "manual", bound_content_hash: "a".repeat(64), used_by: [] }] };
    api.listProjects = vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [{ project_id: "project-1", name: "Target" }] });
    api.listProjectResources = vi.fn().mockResolvedValue(empty);
    let complete!: (value: ProjectResourcesResponse) => void;
    api.addProjectResource = vi.fn().mockImplementation(() => new Promise((resolve) => { complete = resolve; }));
    const user = userEvent.setup();
    const view = render(<ThemeProvider><ProjectWorkspaceProvider api={api}><ResourceLibraryPage resourceId={skills[0]!.reference} /></ProjectWorkspaceProvider></ThemeProvider>);
    const add = await screen.findByRole("button", { name: "Add to Project" });
    await waitFor(() => expect(add).toBeEnabled());
    await user.dblClick(add);
    expect(api.addProjectResource).toHaveBeenCalledTimes(1);
    expect(api.addProjectResource).toHaveBeenCalledWith("project-1", { reference: skills[0]!.reference, content_hash: "a".repeat(64) });
    expect(add).toBeDisabled();
    await act(async () => complete(bound));
    expect(await screen.findByRole("button", { name: "Added to Project" })).toBeDisabled();
    expect(screen.getByRole("link", { name: "Open Project Resources" })).toHaveAttribute("href", "#/projects/project-1/resources");
    expect(screen.getAllByText("Needs configuration").length).toBeGreaterThan(0);
    view.unmount();
    api.listProjectResources = vi.fn().mockResolvedValue(bound);
    render(<ThemeProvider><ProjectWorkspaceProvider api={api}><ResourceLibraryPage resourceId={skills[0]!.reference} /></ProjectWorkspaceProvider></ThemeProvider>);
    expect(await screen.findByRole("button", { name: "Added to Project" })).toBeDisabled();
    expect(api.addProjectResource).toHaveBeenCalledTimes(1);
  });

  it("does not count used-unbound resources as ownership and shows typed add errors", async () => {
    const api = apiFor();
    api.listProjects = vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [{ project_id: "project-1", name: "Target" }] });
    api.listProjectResources = vi.fn().mockResolvedValue({ schema_version: "1.0", project_id: "project-1", resources: [{ ...skills[0], scope: "used_unbound", used_by: [] }], missing_references: [], project_count: 0, used_count: 1, unbound_count: 1, builtin_count: 0 });
    api.addProjectResource = vi.fn().mockRejectedValue(new LocalApiClientError("Reload Catalog identity", { status: 409, code: "resource_identity_conflict" }));
    render(<ThemeProvider><ProjectWorkspaceProvider api={api}><ResourceLibraryPage resourceId={skills[0]!.reference} /></ProjectWorkspaceProvider></ThemeProvider>);
    const add = await screen.findByRole("button", { name: "Add to Project" });
    await waitFor(() => expect(add).toBeEnabled());
    await userEvent.click(add);
    expect(await screen.findByText("resource_identity_conflict: Reload Catalog identity")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Added to Project" })).not.toBeInTheDocument();
  });

  it("opens on the full catalog and filters to Skills and Policies", async () => {
    const api = apiFor();
    const user = userEvent.setup();
    renderPage(api);

    expect(await screen.findByRole("tab", { name: "All" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Start")).toBeInTheDocument();
    expect(screen.getByText("Research Brief")).toBeInTheDocument();
    expect(screen.getByText("Local Only")).toBeInTheDocument();
    expect(api.listResources).toHaveBeenCalledWith();
    await user.click(screen.getByRole("tab", { name: "Skills" }));
    expect(await screen.findByText("Research Brief")).toBeInTheDocument();
    expect(screen.queryByText("Start")).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Policies" }));
    expect(await screen.findByText("Local Only")).toBeInTheDocument();
    expect(window.location.hash).toBe("#/components?tab=policy");
  });

  it("keeps catalog tabs on the Project workspace route", async () => {
    const api = apiFor();
    const user = userEvent.setup();
    window.location.hash = "#/projects/library-project";
    render(<ThemeProvider><ProjectWorkspaceProvider api={api}><ResourceLibraryPage catalogHref="#/projects/library-project" /></ProjectWorkspaceProvider></ThemeProvider>);

    expect(await screen.findByRole("tab", { name: "All" })).toHaveAttribute("aria-selected", "true");
    await user.click(screen.getByRole("tab", { name: "Skills" }));
    expect(await screen.findByText("Research Brief")).toBeInTheDocument();
    expect(window.location.hash).toBe("#/projects/library-project?tab=skill");
  });

  it("shows registered Tools including unavailable GitHub entries", async () => {
    const api = apiFor();
    const user = userEvent.setup();
    renderPage(api);

    await user.click(await screen.findByRole("tab", { name: "Tools / MCP" }));
    expect(await screen.findByText("Filesystem Read")).toBeInTheDocument();
    expect(screen.getByText("GitHub Read")).toBeInTheDocument();
    expect(screen.getByText("MCP Call")).toBeInTheDocument();
    expect(screen.queryByText("Downloads")).not.toBeInTheDocument();
  });

  it("loads a resource detail by its immutable reference", async () => {
    const api = apiFor();
    render(<ThemeProvider><ProjectWorkspaceProvider api={api}><ResourceLibraryPage resourceId="veyra.skill.research-brief@1.0.0" /></ProjectWorkspaceProvider></ThemeProvider>);

    expect(await screen.findByText("Research Brief description")).toBeInTheDocument();
    expect(await screen.findByText("a".repeat(64))).toBeInTheDocument();
    expect(api.getResource).toHaveBeenCalledWith("veyra.skill.research-brief", "1.0.0");
  });

  it("fetches Project inline detail and displays server readiness instead of the list snapshot", async () => {
    const api = apiFor();
    api.getResource.mockResolvedValue({ ...skills[0], availability: "unavailable", runtime_status: "runtime_not_supported", blocking_reasons: [{ code: "host_missing", message: "Host capability is unavailable." }] });
    render(<ThemeProvider><ProjectWorkspaceProvider api={api}><ResourceLibraryPage catalogHref="#/projects/library-project" /></ProjectWorkspaceProvider></ThemeProvider>);
    await userEvent.click(await screen.findByText("Research Brief"));
    expect(await screen.findByText("Host capability is unavailable.")).toBeInTheDocument();
    expect(api.getResource).toHaveBeenCalledWith("veyra.skill.research-brief", "1.0.0");
    expect(screen.getAllByText("Unavailable")).toHaveLength(2);
    expect(screen.queryByText("Ready")).not.toBeInTheDocument();
  });

  it("reloads discovered MCP tools after the Resource Library is reopened", async () => {
    const discovered = { ...descriptor("tool", "Discovered Echo", "mcp.echo"), origin: "discovered", factory_selectable: false, spec: { mcp_server_id: "server-1", review_required: true } };
    const api = apiFor([discovered]);
    api.listMcpServers = vi.fn().mockResolvedValue({ schema_version: "1.0", servers: [{ server_id: "server-1", name: "demo", command: "node", args: [], env_names: {}, enabled: true, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" }] });
    api.mcpServerReadiness = vi.fn().mockResolvedValue({ schema_version: "1.0", server_id: "server-1", ready: true, code: "ready", detail: "ready" });
    const user = userEvent.setup();
    renderPage(api);

    await user.click(await screen.findByRole("tab", { name: "Tools / MCP" }));

    expect((await screen.findAllByText("Discovered Echo")).length).toBeGreaterThanOrEqual(2);
    expect(await screen.findByText(/Review required/)).toBeInTheDocument();
  });
});
