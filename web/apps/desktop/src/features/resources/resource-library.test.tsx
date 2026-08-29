import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ListResourcesResponse } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { ProjectWorkspaceProvider } from "../../api/project-workspace";
import type { LocalProjectApi } from "../../api/local-client";
import { ResourceLibraryPage } from "./resource-library";

function descriptor(kind: "component" | "skill" | "policy" | "template", name: string, id: string, availability: "ready" | "runtime_not_configured" = "ready") {
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
    availability: "ready",
    factory_selectable: true,
    runtime_status: availability === "ready" ? "supported" : "runtime_not_configured",
    required_permissions: { network_hosts: [], tools: [], filesystem_read_roots: [], filesystem_write_roots: [], shell_workspace_only: false },
    tags: [kind, "builtin"],
    spec: { label: name },
  } as const;
}

const components = [descriptor("component", "Start", "start"), descriptor("component", "Agent", "agent", "runtime_not_configured")];
const skills = [descriptor("skill", "Research Brief", "research-brief", "runtime_not_configured"), descriptor("skill", "Document Analyzer", "document-analyzer", "runtime_not_configured")];
const policies = [descriptor("policy", "Local Only", "local-only"), descriptor("policy", "Verification Required", "verification-required")];

function apiFor(): LocalProjectApi & { listResources: ReturnType<typeof vi.fn>; getResource: ReturnType<typeof vi.fn> } {
  const listResources = vi.fn(async ({ kind }: { kind?: string } = {}): Promise<ListResourcesResponse> => {
    const resources = kind === "component" ? components : kind === "skill" ? skills : kind === "policy" ? policies : [];
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

afterEach(() => cleanup());

describe("ResourceLibraryPage", () => {
  it("loads real Component resources and switches to Skills and Policies", async () => {
    const api = apiFor();
    const user = userEvent.setup();
    renderPage(api);

    expect(await screen.findByText("Start")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Skills" }));
    expect(await screen.findByText("Research Brief")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Policies" }));
    expect(await screen.findByText("Local Only")).toBeInTheDocument();
    expect(api.listResources).toHaveBeenCalledWith({ kind: "policy" });
  });

  it("shows an honest empty Tools and MCP category", async () => {
    const api = apiFor();
    const user = userEvent.setup();
    renderPage(api);

    await user.click(await screen.findByRole("tab", { name: "Tools / MCP" }));
    expect(await screen.findByText("No resources in this category yet")).toBeInTheDocument();
    expect(screen.queryByText("Downloads")).not.toBeInTheDocument();
  });

  it("loads a resource detail by its immutable reference", async () => {
    const api = apiFor();
    render(<ThemeProvider><ProjectWorkspaceProvider api={api}><ResourceLibraryPage resourceId="veyra.skill.research-brief@1.0.0" /></ProjectWorkspaceProvider></ThemeProvider>);

    expect(await screen.findByText("Research Brief description")).toBeInTheDocument();
    expect(await screen.findByText("a".repeat(64))).toBeInTheDocument();
    expect(api.getResource).toHaveBeenCalledWith("veyra.skill.research-brief", "1.0.0");
  });
});
