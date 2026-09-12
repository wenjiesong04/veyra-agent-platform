import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ListResourcesResponse } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { ProjectWorkspaceProvider } from "../../api/project-workspace";
import type { LocalProjectApi } from "../../api/local-client";
import { ResourceLibraryPage } from "./resource-library";

function descriptor(kind: "component" | "tool" | "mcp_tool" | "skill" | "policy" | "template", name: string, id: string, availability: "ready" | "design_only" | "unavailable" | "requires_configuration" = "ready") {
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
