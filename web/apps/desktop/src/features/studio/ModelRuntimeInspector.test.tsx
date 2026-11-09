import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ProviderCredential } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { ModelRuntimeInspector } from "./ModelRuntimeInspector";

const credential: ProviderCredential = {
  credential_id: "cred-1",
  owner_id: "local",
  provider_type: "moonshot",
  label: "kimi-k3",
  base_url: "https://api.moonshot.cn/v1",
  status: "active",
  credential_scope: "device",
  masked_hint: "••••51BV",
  capabilities: { models: ["kimi-k3", "kimi-k2"] },
  default_model_id: "kimi-k3",
  is_default: true,
  created_at: "2026-09-27T00:00:00Z",
  updated_at: "2026-09-27T00:00:00Z",
  validated_at: "2026-09-27T00:00:00Z",
  last_used_at: null,
  secret_state: "available",
  readiness: "ready",
};

describe("ModelRuntimeInspector", () => {
  it("asks the user to add a Provider when none exist", async () => {
    const api = {
      listRuntimeCredentials: vi.fn().mockResolvedValue({ schema_version: "1.0", credentials: [] }),
      getRuntimeBinding: vi.fn().mockResolvedValue({
        schema_version: "1.0",
        project_id: "project-1",
        agent_id: "agent-1",
        slot: "primary_model",
        binding: null,
        credential: null,
        explicit: null,
      }),
    } as unknown as LocalProjectApi;
    render(
      <ThemeProvider>
        <ModelRuntimeInspector api={api} projectId="project-1" agentId="agent-1" locale="en" />
      </ThemeProvider>,
    );
    expect(await screen.findByLabelText("Call slot")).toHaveValue("model.primary");
    expect(screen.getByText(/This is a call mapping/)).toBeInTheDocument();
    expect(screen.getByText(/No User Runtime Provider is available/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add Provider" })).toBeInTheDocument();
  });

  it("binds the selected User Runtime Provider and model to the Agent", async () => {
    const setRuntimeBinding = vi.fn().mockResolvedValue({
      schema_version: "1.0",
      project_id: "project-1",
      agent_id: "agent-1",
      slot: "primary_model",
      binding: {
        project_id: "project-1",
        agent_id: "agent-1",
        slot: "primary_model",
        credential_id: "cred-1",
        model_id: "kimi-k2",
        source: "explicit",
        updated_at: "2026-09-27T00:00:00Z",
      },
      credential,
      explicit: {
        project_id: "project-1",
        agent_id: "agent-1",
        slot: "primary_model",
        credential_id: "cred-1",
        model_id: "kimi-k2",
        source: "explicit",
        updated_at: "2026-09-27T00:00:00Z",
      },
    });
    const api = {
      listRuntimeCredentials: vi.fn().mockResolvedValue({ schema_version: "1.0", credentials: [credential] }),
      getRuntimeBinding: vi.fn().mockResolvedValue({
        schema_version: "1.0",
        project_id: "project-1",
        agent_id: "agent-1",
        slot: "primary_model",
        binding: null,
        credential,
        explicit: null,
      }),
      setRuntimeBinding,
    } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <ModelRuntimeInspector api={api} projectId="project-1" agentId="agent-1" locale="en" />
      </ThemeProvider>,
    );
    expect(await screen.findByRole("combobox", { name: "Runtime Provider" })).toHaveValue("cred-1");
    expect(screen.getByRole("combobox", { name: "Model" })).toHaveValue("kimi-k3");
    await user.selectOptions(screen.getByRole("combobox", { name: "Model" }), "kimi-k2");
    await waitFor(() => expect(setRuntimeBinding).toHaveBeenCalledWith(
      "project-1",
      { credential_id: "cred-1", model_id: "kimi-k2" },
      "agent-1",
    ));
  });
});
