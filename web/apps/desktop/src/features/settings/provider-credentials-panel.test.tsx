import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@veyra/ui";
import { ProjectWorkspaceProvider } from "../../api/project-workspace";
import type { LocalProjectApi } from "../../api/local-client";
import { ProviderCredentialsPanel } from "./provider-credentials-panel";

afterEach(() => cleanup());

describe("ProviderCredentialsPanel", () => {
  it("reads Runtime credentials from the local device store", async () => {
    const localList = vi.fn().mockResolvedValue({
      schema_version: "1.0",
      credentials: [{
        credential_id: "credential-1",
        provider_type: "openai_compatible",
        label: "Local Runtime",
        base_url: "http://127.0.0.1:8790/v1",
        status: "active",
        masked_hint: "••••1234",
        capabilities: { models: ["mock-model"] },
        default_model_id: "mock-model",
        is_default: true,
        created_at: "2026-09-25T00:00:00Z",
        updated_at: "2026-09-25T00:00:00Z",
        validated_at: "2026-09-25T00:00:00Z",
        last_used_at: null,
        credential_scope: "device" as const,
        secret_state: "available" as const,
        readiness: "ready" as const,
      }],
    });
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
      listRuntimeCredentials: localList,
    } as unknown as LocalProjectApi;

    render(
      <ThemeProvider>
        <ProjectWorkspaceProvider api={api}>
          <ProviderCredentialsPanel locale="en" />
        </ProjectWorkspaceProvider>
      </ThemeProvider>,
    );

    expect(await screen.findByText("Local Runtime")).toBeInTheDocument();
    expect(screen.getByText("••••1234").parentElement?.textContent).toContain("This device");
    expect(localList).toHaveBeenCalledTimes(1);
  });
});
