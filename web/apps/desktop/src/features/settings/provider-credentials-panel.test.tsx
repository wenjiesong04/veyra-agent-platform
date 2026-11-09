import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProviderCredential } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { ProjectWorkspaceProvider } from "../../api/project-workspace";
import type { LocalProjectApi } from "../../api/local-client";
import { ProviderCredentialsPanel } from "./provider-credentials-panel";

function credential(overrides: Partial<ProviderCredential> = {}): ProviderCredential {
  return {
    credential_id: "credential-1", owner_id: "local", provider_type: "openai_compatible", label: "Local Runtime",
    base_url: "http://127.0.0.1:8790/v1", status: "active", masked_hint: "••••1234", capabilities: { models: ["mock-model"] },
    default_model_id: "mock-model", is_default: true, created_at: "2026-10-03T00:00:00Z", updated_at: "2026-10-03T00:00:00Z",
    validated_at: "2026-10-03T00:00:00Z", last_used_at: null, credential_scope: "device", secret_state: "available", readiness: "ready",
    discovery_state: "ready", ...overrides,
  };
}

function renderPanel(api: LocalProjectApi, onSelectCredential = vi.fn(), selectedCredentialId?: string | null, renderModels?: (id: string) => ReactNode) {
  function Harness() {
    const [selected, setSelected] = useState(selectedCredentialId);
    return <ProviderCredentialsPanel locale="en" selectedCredentialId={selected} onSelectCredential={(id) => { setSelected(id); onSelectCredential(id); }} renderModels={renderModels} />;
  }
  render(<ThemeProvider><ProjectWorkspaceProvider api={api}><Harness /></ProjectWorkspaceProvider></ThemeProvider>);
  return onSelectCredential;
}

function apiWith(overrides: Record<string, unknown>): LocalProjectApi {
  return {
    listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
    listRuntimeCredentials: vi.fn().mockResolvedValue({ schema_version: "1.0", credentials: [] }),
    ...overrides,
  } as unknown as LocalProjectApi;
}

async function fillConnection(user: ReturnType<typeof userEvent.setup>, modelId?: string) {
  await user.click(screen.getByRole("button", { name: "Add Provider" }));
  await user.selectOptions(screen.getByLabelText("Provider"), "openai");
  await user.type(screen.getByLabelText("Connection name"), "Provider");
  await user.type(screen.getByLabelText(/^API Key/), "fake-test-only-key");
  if (modelId) {
    await user.click(screen.getByText("Connection options"));
    await user.type(screen.getByLabelText("Model ID"), modelId);
  }
}

afterEach(() => { cleanup(); window.location.hash = ""; });

describe("ProviderCredentialsPanel", () => {
  it("reads Runtime credentials from the local device store", async () => {
    const localList = vi.fn().mockResolvedValue({ schema_version: "1.0", credentials: [credential()] });
    renderPanel(apiWith({ listRuntimeCredentials: localList }));

    const connection = await screen.findByRole("combobox", { name: "API connection" });
    expect(connection).toHaveValue("credential-1");
    expect(within(screen.getByRole("article")).getByText("••••1234").closest("article")?.textContent).toContain("This device");
    expect(localList).toHaveBeenCalledTimes(1);
  });

  it("continues a preserved but undiscovered default model in the same setup flow", async () => {
    const saved = credential({ credential_id: "credential-2", label: "Provider", capabilities: { models: [] }, default_model_id: "manual-model", is_default: false });
    const createRuntimeCredential = vi.fn().mockResolvedValue({
      valid: true, code: "default_model_unavailable", message: "saved default not listed", credential: saved,
      model_selection: { provider_model_id: "manual-model", state: "needs_setup" },
      discovery: { state: "ready", models_found: 0, discovered_at: "2026-10-03T00:00:00Z" }, models: [],
    });
    const addRuntimeModel = vi.fn().mockResolvedValue({ model_profile_id: "manual-profile", provider_model_id: "manual-model" });
    const listRuntimeCredentials = vi.fn().mockResolvedValueOnce({ schema_version: "1.0", credentials: [] }).mockResolvedValue({ schema_version: "1.0", credentials: [saved] });
    const renderModels = vi.fn((id: string) => <section aria-label="Selected model workspace">Models for {id}</section>);
    const selected = renderPanel(apiWith({ createRuntimeCredential, addRuntimeModel, listRuntimeCredentials }), vi.fn(), undefined, renderModels);
    const user = userEvent.setup();
    await fillConnection(user, "manual-model");
    await user.click(screen.getByRole("button", { name: "Save & check connection" }));

    await waitFor(() => expect(selected).toHaveBeenCalledWith("credential-2"));
    expect(addRuntimeModel).toHaveBeenCalledWith("credential-2", { provider_model_id: "manual-model" });
    expect(createRuntimeCredential).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(/Connection and model saved/)).toBeInTheDocument();
    expect(await screen.findByText("manual-model")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "API connection" })).toHaveValue("credential-2");
    expect(screen.getByRole("region", { name: "Selected model workspace" })).toHaveTextContent("Models for credential-2");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("retries manual registration using the saved connection and closes after it succeeds", async () => {
    const saved = credential({ credential_id: "saved-credential", label: "Provider", capabilities: { models: [] }, default_model_id: "manual-model", is_default: false });
    const createRuntimeCredential = vi.fn().mockResolvedValue({ valid: true, code: "default_model_unavailable", message: "not listed", credential: saved, models: [] });
    const addRuntimeModel = vi.fn().mockRejectedValueOnce(new Error("Registration failed")).mockResolvedValueOnce({ model_profile_id: "manual-profile", provider_model_id: "manual-model" });
    const selected = renderPanel(apiWith({ createRuntimeCredential, addRuntimeModel }));
    const user = userEvent.setup();
    await fillConnection(user, "manual-model");
    await user.click(screen.getByRole("button", { name: "Save & check connection" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This test did not finish");
    expect(screen.queryByText("Registration failed")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^API Key/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add this model" }));

    await waitFor(() => expect(selected).toHaveBeenCalledWith("saved-credential"));
    expect(createRuntimeCredential).toHaveBeenCalledTimes(1);
    expect(addRuntimeModel).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("rechecks a rejected saved credential without creating another Provider", async () => {
    const saved = credential({ credential_id: "saved-credential", label: "Provider", status: "invalid", readiness: "invalid", is_default: false });
    const createRuntimeCredential = vi.fn().mockResolvedValue({ valid: false, code: "runtime_unauthorized", message: "Provider credentials were rejected", credential: saved, models: [] });
    const replaceRuntimeCredential = vi.fn().mockResolvedValue({ valid: true, code: "validated", message: "Connection checked", credential: { ...saved, status: "active", readiness: "ready" }, models: [] });
    const selected = renderPanel(apiWith({ createRuntimeCredential, replaceRuntimeCredential }));
    const user = userEvent.setup();
    await fillConnection(user);
    await user.click(screen.getByRole("button", { name: "Save & check connection" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The key was rejected");
    await user.type(screen.getByLabelText(/^API Key/), "replacement-test-only-key");
    await user.click(screen.getByRole("button", { name: "Recheck connection" }));

    await waitFor(() => expect(selected).toHaveBeenCalledWith("saved-credential"));
    expect(createRuntimeCredential).toHaveBeenCalledTimes(1);
    expect(replaceRuntimeCredential).toHaveBeenCalledWith("saved-credential", "replacement-test-only-key");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("selects an existing Provider to continue model setup", async () => {
    const selected = renderPanel(apiWith({ listRuntimeCredentials: vi.fn().mockResolvedValue({ schema_version: "1.0", credentials: [credential(), credential({ credential_id: "credential-2", label: "Other Provider" })] }) }), vi.fn(), "credential-2");
    const connection = await screen.findByRole("combobox", { name: "API connection" });
    expect(connection).toHaveValue("credential-2");
    expect(screen.getByRole("article", { name: "Other Provider" })).toBeInTheDocument();
    expect(screen.queryByRole("article", { name: "Local Runtime" })).not.toBeInTheDocument();
    await userEvent.setup().selectOptions(connection, "credential-1");
    expect(selected).toHaveBeenCalledWith("credential-1");
    expect(screen.getByRole("article", { name: "Local Runtime" })).toBeInTheDocument();
    expect(screen.queryByRole("article", { name: "Other Provider" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Manage models & verification" })).not.toBeInTheDocument();
  });

  it("opens the default connection when the saved selection no longer exists", async () => {
    renderPanel(apiWith({ listRuntimeCredentials: vi.fn().mockResolvedValue({ schema_version: "1.0", credentials: [credential({ is_default: false }), credential({ credential_id: "credential-2", label: "Default Provider", is_default: true })] }) }), vi.fn(), "deleted-credential");
    expect(await screen.findByRole("combobox", { name: "API connection" })).toHaveValue("credential-2");
    expect(screen.getByRole("article", { name: "Default Provider" })).toBeInTheDocument();
  });

  it("keeps key replacement and deletion scoped to the selected connection", async () => {
    let credentials = [credential(), credential({ credential_id: "credential-2", label: "Other Provider", is_default: false })];
    const replaceRuntimeCredential = vi.fn().mockImplementation(async (id: string) => ({ valid: true, code: "validated", credential: credentials.find((item) => item.credential_id === id), models: [] }));
    const deleteRuntimeCredential = vi.fn().mockImplementation(async (id: string) => { credentials = credentials.filter((item) => item.credential_id !== id); });
    renderPanel(apiWith({
      listRuntimeCredentials: vi.fn().mockImplementation(async () => ({ schema_version: "1.0", credentials })),
      replaceRuntimeCredential, deleteRuntimeCredential,
    }));
    const connection = await screen.findByRole("combobox", { name: "API connection" });
    const user = userEvent.setup();
    await user.selectOptions(connection, "credential-2");
    const row = screen.getByRole("article", { name: "Other Provider" });
    await user.click(within(row).getByText("Connection settings"));
    await user.click(within(row).getByRole("button", { name: "Replace Key" }));
    await user.type(within(row).getByLabelText("New API Key"), "replacement-test-key");
    await user.click(within(row).getByRole("button", { name: "Save & check" }));
    await waitFor(() => expect(replaceRuntimeCredential).toHaveBeenCalledWith("credential-2", "replacement-test-key"));
    expect(screen.queryByLabelText("New API Key")).not.toBeInTheDocument();

    await user.click(within(row).getByRole("button", { name: /^Delete$/ }));
    expect(deleteRuntimeCredential).not.toHaveBeenCalled();
    await user.click(within(row).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("button", { name: "Delete connection" })).not.toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: /^Delete$/ }));
    await user.click(within(row).getByRole("button", { name: "Delete connection" }));
    await waitFor(() => expect(deleteRuntimeCredential).toHaveBeenCalledWith("credential-2"));
    await waitFor(() => expect(connection).toHaveValue("credential-1"));
    expect(screen.queryByRole("article", { name: "Other Provider" })).not.toBeInTheDocument();
  });

  it("reports a rejected enable check as an error instead of claiming the connection was enabled", async () => {
    let saved = credential({ status: "disabled", readiness: "disabled" });
    const setRuntimeCredentialStatus = vi.fn().mockImplementation(async () => {
      saved = { ...saved, status: "invalid", readiness: "invalid" };
      return { valid: false, code: "runtime_unauthorized", message: "Provider credentials were rejected", credential: saved };
    });
    renderPanel(apiWith({
      listRuntimeCredentials: vi.fn().mockImplementation(async () => ({ schema_version: "1.0", credentials: [saved] })),
      setRuntimeCredentialStatus,
    }));
    await screen.findByRole("combobox", { name: "API connection" });
    const row = screen.getByRole("article");
    const user = userEvent.setup();
    await user.click(within(row).getByText("Connection settings"));
    await user.click(within(row).getByRole("button", { name: "Enable" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/connection.*failed|invalid|rejected/i);
    expect(setRuntimeCredentialStatus).toHaveBeenCalledWith("credential-1", true);
    expect(screen.queryByText(/Connection enabled/)).not.toBeInTheDocument();
  });

  it("corrects a stored console address only after explicit save and reuses the stored key", async () => {
    let saved = credential({ base_url: "https://bailian.console.aliyun.com/cn-beijing/settings/api-key", status: "unverified", readiness: "unverified", discovery_state: "failed" });
    const updateRuntimeCredential = vi.fn().mockImplementation(async (_id: string, update: { label: string; base_url: string }) => {
      saved = { ...saved, ...update };
      return saved;
    });
    const validateRuntimeCredential = vi.fn().mockImplementation(async () => {
      saved = { ...saved, status: "active", readiness: "ready" };
      return { valid: true, code: "validated", credential: saved, models: [] };
    });
    const replaceRuntimeCredential = vi.fn();
    const createRuntimeCredential = vi.fn();
    renderPanel(apiWith({
      listRuntimeCredentials: vi.fn().mockImplementation(async () => ({ schema_version: "1.0", credentials: [saved] })),
      updateRuntimeCredential, validateRuntimeCredential, replaceRuntimeCredential, createRuntimeCredential,
    }));
    const user = userEvent.setup();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/account or API-key webpage/);
    await user.click(screen.getByRole("button", { name: "Correct service address" }));
    let dialog = screen.getByRole("dialog", { name: "Edit service address" });
    expect(within(dialog).getByLabelText(/^Service address/)).toHaveValue("https://dashscope.aliyuncs.com/compatible-mode/v1");
    expect(within(dialog).queryByLabelText(/^API Key/)).not.toBeInTheDocument();
    expect(updateRuntimeCredential).not.toHaveBeenCalled();
    expect(validateRuntimeCredential).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(updateRuntimeCredential).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Correct service address" }));
    dialog = screen.getByRole("dialog", { name: "Edit service address" });
    await user.click(within(dialog).getByRole("button", { name: "Save address & check" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(updateRuntimeCredential).toHaveBeenCalledTimes(1);
    expect(updateRuntimeCredential).toHaveBeenCalledWith("credential-1", {
      label: "Local Runtime", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    });
    expect(validateRuntimeCredential).toHaveBeenCalledWith("credential-1");
    expect(replaceRuntimeCredential).not.toHaveBeenCalled();
    expect(createRuntimeCredential).not.toHaveBeenCalled();
  });
});
