import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProjectResourceDescriptor, ProjectResourcesResponse, ResourceDescriptor } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { ProjectWorkspaceProvider } from "../api/project-workspace";
import type { LocalProjectApi } from "../api/local-client";
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
    await waitFor(() => expect(api.addProjectResource).toHaveBeenCalledWith("project-1", { reference: "veyra.filesystem.read@1.0.0" }));
  });
});
