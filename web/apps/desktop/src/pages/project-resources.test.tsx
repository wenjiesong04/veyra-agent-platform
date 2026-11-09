import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProjectResourceDescriptor, ProjectResourcesResponse, ResourceDescriptor } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { ProjectWorkspaceProvider } from "../api/project-workspace";
import { LocalApiClientError, type LocalProjectApi } from "../api/local-client";
import { ProjectResourcesPage } from "./project-resources";

function resource(overrides: Partial<ResourceDescriptor> = {}): ResourceDescriptor {
  return {
    schema_version: "1.0",
    resource_id: "veyra.filesystem.read",
    kind: "tool",
    version: "1.0.0",
    reference: "veyra.filesystem.read@1.0.0",
    name: "Filesystem Read",
    description: "Read a bounded Project path.",
    origin: "builtin",
    content_hash: "a".repeat(64),
    availability: "ready",
    factory_selectable: true,
    runtime_status: "supported",
    required_permissions: { network_hosts: [], tools: [], filesystem_read_roots: ["$PROJECT"], filesystem_write_roots: [], shell_workspace_only: false },
    tags: ["filesystem"],
    spec: {},
    ...overrides,
  };
}

function projectResource(scope: ProjectResourceDescriptor["scope"]): ProjectResourceDescriptor {
  return { ...resource(), scope, binding_source: scope === "project" ? "manual" : null, bound_content_hash: scope === "project" ? "a".repeat(64) : null, used_by: [] };
}

function response(resources: ProjectResourceDescriptor[]): ProjectResourcesResponse {
  return { schema_version: "1.0", project_id: "project-1", resources, missing_references: [], project_count: resources.filter((item) => item.scope === "project").length, used_count: 0, unbound_count: resources.filter((item) => item.scope === "used_unbound").length, builtin_count: resources.filter((item) => item.scope === "builtin").length };
}

function renderPage(api: LocalProjectApi) {
  return render(<ThemeProvider><ProjectWorkspaceProvider api={api}><ProjectResourcesPage projectId="project-1" /></ProjectWorkspaceProvider></ThemeProvider>);
}

afterEach(() => cleanup());

describe("ProjectResourcesPage", () => {
  it("shows Project bindings separately from built-in primitives", async () => {
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
      listProjectResources: vi.fn().mockResolvedValue(response([projectResource("project"), { ...resource({ resource_id: "veyra.core.start", reference: "veyra.core.start@1.0.0", name: "Start", kind: "component" }), scope: "builtin", binding_source: null, bound_content_hash: null, used_by: [] }])),
      listResources: vi.fn().mockResolvedValue({ schema_version: "1.0", resources: [resource()], kinds: [] }),
    } as unknown as LocalProjectApi;

    renderPage(api);
    expect(await screen.findByRole("heading", { name: "Project resources" })).toBeInTheDocument();
    expect(screen.getByText("Filesystem Read")).toBeInTheDocument();
    expect(screen.queryByText("Start")).not.toBeInTheDocument();
    expect(screen.getByText("Bound resources")).toBeInTheDocument();
  });

  it("adds a resource from the global Catalog", async () => {
    const user = userEvent.setup();
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
      listProjectResources: vi.fn().mockResolvedValue(response([])),
      listResources: vi.fn().mockResolvedValue({ schema_version: "1.0", resources: [resource()], kinds: [] }),
      addProjectResource: vi.fn().mockResolvedValue(response([projectResource("project")])),
    } as unknown as LocalProjectApi;

    renderPage(api);
    await user.click(await screen.findByRole("button", { name: "Add from Catalog" }));
    await user.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(api.addProjectResource).toHaveBeenCalledWith("project-1", { reference: "veyra.filesystem.read@1.0.0", content_hash: "a".repeat(64) }));
  });

  it("renders readiness and drift, removes once, then reads the refreshed server state", async () => {
    const bound = { ...projectResource("project"), binding_status: "stale" as const, content_hash: "b".repeat(64), availability: "requires_configuration" as const, blocking_reasons: [{ code: "secret_not_configured", message: "Configure host credential" }] };
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
      listProjectResources: vi.fn().mockResolvedValue(response([bound])),
      listResources: vi.fn().mockResolvedValue({ schema_version: "1.0", resources: [resource()], kinds: [] }),
      removeProjectResource: vi.fn(),
    } as unknown as LocalProjectApi;
    let complete!: (value: ProjectResourcesResponse) => void;
    api.removeProjectResource = vi.fn().mockImplementation(() => new Promise((resolve) => { complete = resolve; }));
    const view = renderPage(api);
    const remove = await screen.findByRole("button", { name: "Remove Filesystem Read" });
    expect(screen.getByText("Version drift")).toBeInTheDocument();
    expect(screen.getByText("Configure host credential")).toBeInTheDocument();
    expect(screen.getByText(/Pinned version \/ hash/)).toHaveTextContent("a".repeat(64));
    expect(screen.getByText(/Current Catalog version \/ hash/)).toHaveTextContent("b".repeat(64));
    await userEvent.dblClick(remove);
    expect(remove).toBeDisabled();
    expect(api.removeProjectResource).toHaveBeenCalledTimes(1);
    expect(api.removeProjectResource).toHaveBeenCalledWith("project-1", "veyra.filesystem.read", "1.0.0");
    await act(async () => complete(response([])));
    expect(screen.queryByText("Filesystem Read")).not.toBeInTheDocument();
    api.listProjectResources = vi.fn().mockResolvedValue(response([]));
    await userEvent.click(screen.getByRole("button", { name: "Refresh bindings" }));
    await waitFor(() => expect(api.listProjectResources).toHaveBeenCalledWith("project-1"));
    view.unmount();
    renderPage(api);
    expect(await screen.findByText("No optional resources yet")).toBeInTheDocument();
  });

  it("keeps the binding after a typed in-use refusal", async () => {
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
      listProjectResources: vi.fn().mockResolvedValue(response([projectResource("project")])),
      listResources: vi.fn().mockResolvedValue({ schema_version: "1.0", resources: [], kinds: [] }),
      removeProjectResource: vi.fn().mockRejectedValue(new LocalApiClientError("Saved version references this resource", { status: 409, code: "resource_in_use" })),
    } as unknown as LocalProjectApi;
    renderPage(api);
    await userEvent.click(await screen.findByRole("button", { name: "Remove Filesystem Read" }));
    expect(await screen.findByText("resource_in_use: Saved version references this resource")).toBeInTheDocument();
    expect(screen.getByText("Filesystem Read")).toBeInTheDocument();
  });

  it("retains a missing binding identity and removes only that reference", async () => {
    const missing = { reference: "veyra.skill.missing@0.0.1", content_hash: "c".repeat(64), source: "manual", used_by: [] };
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
      listProjectResources: vi.fn().mockResolvedValue({ ...response([]), project_count: 1, missing_references: [missing.reference], missing_bindings: [missing] }),
      listResources: vi.fn().mockResolvedValue({ schema_version: "1.0", resources: [], kinds: [] }),
      removeProjectResource: vi.fn().mockResolvedValue(response([])),
    } as unknown as LocalProjectApi;
    renderPage(api);
    expect(await screen.findByText("Bound; Catalog version missing, unavailable")).toBeInTheDocument();
    expect(screen.getByText(missing.content_hash)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remove missing binding" }));
    expect(api.removeProjectResource).toHaveBeenCalledWith("project-1", "veyra.skill.missing", "0.0.1");
    await waitFor(() => expect(screen.queryByText(missing.content_hash)).not.toBeInTheDocument());
  });
});
