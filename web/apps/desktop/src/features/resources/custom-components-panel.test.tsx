import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CustomComponentDefinition, CustomComponentSummary, ListCustomComponentsResponse } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { ProjectWorkspaceProvider } from "../../api/project-workspace";
import { LocalApiClientError } from "../../api/local-client";
import type { LocalProjectApi } from "../../api/local-client";
import { CustomComponentsPanel } from "./custom-components-panel";

const baseDefinition: CustomComponentDefinition = {
  schema_version: "1.0",
  component_id: "custom-1",
  project_id: "project-1",
  slug: "invoice-extractor",
  display_name: "Invoice Extractor",
  description: "Extract invoice fields.",
  version: "0.0.0",
  reference: "custom-1@0.0.0",
  content_hash: "a".repeat(64),
  inputs: { text: "string" },
  outputs: { invoice: "object" },
  implementation: { kind: "model_recipe", instruction: "Extract invoice fields.", model_ref: "model.primary" },
  metadata: { owner: "finance" },
  dependencies: [],
  required_permissions: { network_hosts: [], tools: [], filesystem_read_roots: [], filesystem_write_roots: [], shell_workspace_only: false },
  readiness: "ready",
  provenance: "manual",
  lifecycle: "draft",
  deprecated: false,
  created_at: "2026-09-22T00:00:00Z",
  updated_at: "2026-09-22T00:00:00Z",
};

function summary(draft: CustomComponentDefinition | null, versions: CustomComponentSummary["versions"] = []): CustomComponentSummary {
  return {
    schema_version: "1.0",
    component_id: baseDefinition.component_id,
    project_id: baseDefinition.project_id,
    slug: baseDefinition.slug,
    display_name: baseDefinition.display_name,
    description: baseDefinition.description,
    draft,
    latest_version: versions.at(-1)?.version ?? null,
    versions,
  };
}

function listResponse(components: CustomComponentSummary[]): ListCustomComponentsResponse {
  return { schema_version: "1.0", project_id: "project-1", components };
}

function renderPanel(api: LocalProjectApi, onChanged?: () => void | Promise<void>) {
  return render(
    <ThemeProvider storageKey="custom-component-test-theme">
      <ProjectWorkspaceProvider api={api}>
        <CustomComponentsPanel api={api} projectId="project-1" onChanged={onChanged} />
      </ProjectWorkspaceProvider>
    </ThemeProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Project Custom Components panel", () => {
  it("locks the editor when the component API returns 404 and unlocks after a successful retry", async () => {
    const user = userEvent.setup();
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
      listCustomComponents: vi.fn()
        .mockRejectedValueOnce(new LocalApiClientError("Not Found", { status: 404, code: "not_found" }))
        .mockResolvedValue(listResponse([])),
      createCustomComponent: vi.fn(),
      updateCustomComponent: vi.fn(),
    } as unknown as LocalProjectApi;

    renderPanel(api);

    expect(await screen.findByText(/Custom Component list API returned 404/i)).toBeInTheDocument();
    expect(screen.getByText("Component list unavailable")).toBeInTheDocument();
    expect(screen.queryByText("No Custom Components yet")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Display name")).toBeDisabled();
    expect(screen.getByRole("button", { name: "New component" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save draft" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Retry" }));

    await screen.findByText("No Custom Components yet");
    expect(screen.getByLabelText("Display name")).toBeEnabled();
    expect(screen.getByRole("button", { name: "New component" })).toBeEnabled();
    expect(api.createCustomComponent).not.toHaveBeenCalled();
  });

  it("saves a draft, validates it, and publishes an immutable version", async () => {
    const user = userEvent.setup();
    let current = listResponse([]);
    const published: CustomComponentDefinition = {
      ...baseDefinition,
      version: "1.0.0",
      reference: "custom-1@1.0.0",
      lifecycle: "active",
      content_hash: "b".repeat(64),
    };
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
      listCustomComponents: vi.fn().mockImplementation(async () => current),
      createCustomComponent: vi.fn().mockImplementation(async (_projectId, input) => {
        const draft = { ...baseDefinition, display_name: input.display_name, description: input.description, inputs: input.inputs, outputs: input.outputs, implementation: input.implementation, metadata: input.metadata ?? {} };
        current = listResponse([summary(draft)]);
        return draft;
      }),
      updateCustomComponent: vi.fn().mockResolvedValue(baseDefinition),
      validateCustomComponent: vi.fn().mockResolvedValue(baseDefinition),
      publishCustomComponent: vi.fn().mockImplementation(async () => {
        current = listResponse([summary(null, [{ version: "1.0.0", reference: published.reference, lifecycle: "active", implementation_kind: "model_recipe", readiness: "ready", content_hash: published.content_hash }])]);
        return published;
      }),
    } as unknown as LocalProjectApi;
    const onChanged = vi.fn();

    renderPanel(api, onChanged);
    await screen.findByText("No Custom Components yet");
    await user.click(screen.getByRole("button", { name: "New component" }));
    expect(screen.getByRole("button", { name: "Publish version" })).toBeDisabled();
    await user.type(screen.getByLabelText("Display name"), "Invoice Extractor");
    await user.type(screen.getByLabelText("Description"), "Extract invoice fields.");
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(api.createCustomComponent).toHaveBeenCalledWith("project-1", expect.objectContaining({ display_name: "Invoice Extractor", implementation: expect.objectContaining({ kind: "model_recipe" }) })));
    await screen.findByText("Draft changes are unpublished");
    expect(screen.getByRole("button", { name: "Publish version" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Validate" }));
    await waitFor(() => expect(api.validateCustomComponent).toHaveBeenCalledWith("project-1", "custom-1"));
    expect(screen.getByRole("button", { name: "Publish version" })).toBeEnabled();
    await user.type(screen.getByLabelText("Description"), " Changed after validation");
    expect(screen.getByRole("button", { name: "Publish version" })).toBeDisabled();
    expect(api.publishCustomComponent).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Validate" }));
    await waitFor(() => expect(api.validateCustomComponent).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("button", { name: "Publish version" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Publish version" }));
    await waitFor(() => expect(api.publishCustomComponent).toHaveBeenCalledWith("project-1", "custom-1"));
    await screen.findByText("custom-1@1.0.0");
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("confirms deprecation and presents lifecycle after the mutation", async () => {
    const user = userEvent.setup();
    const activeVersion = { version: "1.2.0", reference: "custom-1@1.2.0", lifecycle: "active" as const, implementation_kind: "transform" as const, readiness: "ready" as const, content_hash: "c".repeat(64) };
    let current = listResponse([summary(null, [activeVersion])]);
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
      listCustomComponents: vi.fn().mockImplementation(async () => current),
      createCustomComponent: vi.fn(),
      updateCustomComponent: vi.fn(),
      deprecateCustomComponent: vi.fn().mockImplementation(async () => {
        current = listResponse([summary(null, [{ ...activeVersion, lifecycle: "deprecated" }])]);
        return { ...baseDefinition, version: activeVersion.version, reference: activeVersion.reference, lifecycle: "deprecated", deprecated: true };
      }),
    } as unknown as LocalProjectApi;
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderPanel(api);
    await screen.findByText("Latest version: 1.2.0");
    await user.click(screen.getByRole("button", { name: "Deprecate" }));
    expect(confirm).toHaveBeenCalled();
    await waitFor(() => expect(api.deprecateCustomComponent).toHaveBeenCalledWith("project-1", "custom-1", "1.2.0"));
    await screen.findByText("Deprecated");
  });
});
