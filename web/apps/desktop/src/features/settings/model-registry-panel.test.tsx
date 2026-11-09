import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MODEL_CAPABILITY_NAMES, type ModelProfile, type ProviderCredential } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { ProjectWorkspaceProvider } from "../../api/project-workspace";
import { LocalApiClientError, type LocalProjectApi } from "../../api/local-client";
import { ModelRegistryPanel } from "./model-registry-panel";

function unknownCapabilities(): ModelProfile["capabilities"] {
  return Object.fromEntries(MODEL_CAPABILITY_NAMES.map((name) => [name, { status: "unknown", evidence: null }])) as ModelProfile["capabilities"];
}

function profile(overrides: Partial<ModelProfile> = {}): ModelProfile {
  const capabilities = unknownCapabilities();
  capabilities.image_generation = { status: "supported", evidence: { source: "provider_metadata", observed_at: "2026-10-03T00:00:00Z" } };
  return {
    model_profile_id: "profile-1", provider_connection_id: "credential-1", provider_type: "openai_compatible", provider_label: "Image Provider",
    provider_model_id: "image-test", display_name: "Image model", enabled: true, listed: true,
    metadata: {}, capabilities,
    verification: { state: "verified", source: "provider_metadata", verified_at: "2026-10-03T00:00:00Z", last_checked_at: "2026-10-03T00:00:00Z", stale_reason: null, error_code: null },
    capability_revision: 1, capability_digest: "a".repeat(64), discovered_at: "2026-10-03T00:00:00Z", created_at: "2026-10-03T00:00:00Z", updated_at: "2026-10-03T00:00:00Z", connection_readiness: "ready", registry_ready: true,
    ...overrides,
  };
}

function unknownProfile(overrides: Partial<ModelProfile> = {}): ModelProfile {
  return profile({
    capabilities: unknownCapabilities(),
    verification: { state: "unknown", source: null, verified_at: null, last_checked_at: null, stale_reason: null, error_code: null },
    ...overrides,
  });
}

function credential(overrides: Partial<ProviderCredential> = {}): ProviderCredential {
  return {
    credential_id: "credential-1", owner_id: "local", provider_type: "openai_compatible", label: "Image Provider",
    base_url: "http://127.0.0.1:8790/v1", status: "active", masked_hint: "••••1234", capabilities: { models: ["image-test"] },
    default_model_id: "image-test", is_default: false, created_at: "2026-10-03T00:00:00Z", updated_at: "2026-10-03T00:00:00Z",
    validated_at: "2026-10-03T00:00:00Z", last_used_at: null, credential_scope: "device", secret_state: "available", readiness: "ready",
    discovery_state: "ready", ...overrides,
  };
}

function apiWith(overrides: Record<string, unknown> = {}): LocalProjectApi {
  return {
    listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
    listRuntimeModels: vi.fn().mockResolvedValue({ schema_version: "1.0", models: [profile()] }),
    listRuntimeModelDefaults: vi.fn().mockResolvedValue({ schema_version: "1.0", defaults: [] }),
    listRuntimeCredentials: vi.fn().mockResolvedValue({ schema_version: "1.0", credentials: [credential()] }),
    ...overrides,
  } as unknown as LocalProjectApi;
}

function renderRegistry(api: LocalProjectApi, credentialId?: string | null, embedded = false, onEditConnection?: () => void) {
  return render(<ThemeProvider><ProjectWorkspaceProvider api={api}><ModelRegistryPanel locale="en" credentialId={credentialId} embedded={embedded} onEditConnection={onEditConnection} /></ProjectWorkspaceProvider></ThemeProvider>);
}

async function modelRow(name = "Image model") {
  const [title] = await screen.findAllByText(name);
  const row = title.closest("article");
  if (!row) throw new Error(`No model row for ${name}`);
  return row;
}

afterEach(() => { cleanup(); window.location.hash = ""; });

describe("ModelRegistryPanel", () => {
  it("shows capability evidence and requires cost acknowledgement before an image probe", async () => {
    window.location.hash = "#/settings?requiredCapability=image_generation";
    const probeRuntimeModelCapability = vi.fn();
    renderRegistry(apiWith({ probeRuntimeModelCapability }));
    expect(await screen.findByText("Needed now: Image generation")).toBeInTheDocument();
    expect(screen.getByText("1 models have current capability evidence.")).toBeInTheDocument();
    expect(screen.getByText("Image model")).toBeInTheDocument();
    const verify = screen.getByRole("button", { name: "Verify" });
    expect(verify).toBeDisabled();
    await userEvent.setup().click(screen.getByRole("checkbox", { name: /may incur a small API charge/i }));
    await waitFor(() => expect(verify).toBeEnabled());
    expect(probeRuntimeModelCapability).not.toHaveBeenCalled();
  });

  it("blocks image probes against a console webpage and opens address correction on request", async () => {
    window.location.hash = "#/settings?requiredCapability=image_generation";
    const probeRuntimeModelCapability = vi.fn();
    const onEditConnection = vi.fn();
    renderRegistry(apiWith({
      listRuntimeModels: vi.fn().mockResolvedValue({ schema_version: "1.0", models: [unknownProfile()] }),
      listRuntimeCredentials: vi.fn().mockResolvedValue({ schema_version: "1.0", credentials: [credential({ base_url: "https://bailian.console.aliyun.com/cn-beijing/settings/api-key" })] }),
      probeRuntimeModelCapability,
    }), "credential-1", true, onEditConnection);
    const row = await modelRow();
    const verify = within(row).getByRole("button", { name: "Verify" });
    expect(verify).toBeDisabled();
    expect(within(row).getByText(/Correct the service address before testing/)).toBeInTheDocument();
    expect(within(row).queryByRole("checkbox")).not.toBeInTheDocument();
    await userEvent.setup().click(verify);
    expect(probeRuntimeModelCapability).not.toHaveBeenCalled();
    expect(onEditConnection).not.toHaveBeenCalled();
    await userEvent.setup().click(within(row).getByRole("button", { name: "Correct service address" }));
    expect(onEditConnection).toHaveBeenCalledTimes(1);
    expect(probeRuntimeModelCapability).not.toHaveBeenCalled();
  });

  it.each([
    ["runtime_endpoint_not_found", /No matching model endpoint/],
    ["runtime_unauthorized", /The key was rejected/],
    ["runtime_permission_denied", /HTTP 403/],
    ["runtime_model_unavailable", /could not find this model/],
    ["runtime_parameters_unsupported", /rejected the test parameters/],
    ["runtime_insufficient_balance", /balance or quota is exhausted/],
  ] as const)("explains %s beside the model without showing raw provider details", async (code, guidance) => {
    const probeRuntimeModelCapability = vi.fn().mockRejectedValue(new LocalApiClientError("PRIVATE-KEY-AND-RAW-PROVIDER-BODY", { status: 422, code }));
    renderRegistry(apiWith({
      listRuntimeModels: vi.fn().mockResolvedValue({ schema_version: "1.0", models: [unknownProfile()] }),
      probeRuntimeModelCapability,
    }));
    const row = await modelRow();
    await userEvent.setup().click(within(row).getByRole("button", { name: "Verify" }));
    expect(await within(row).findByRole("alert")).toHaveTextContent(guidance);
    expect(screen.queryByText(/PRIVATE-KEY-AND-RAW-PROVIDER-BODY/)).not.toBeInTheDocument();
    expect(screen.queryByText(/verified.*You can use/i)).not.toBeInTheDocument();
  });

  it("restores a persisted verification failure with guidance without repeating a model call", async () => {
    const prior = unknownProfile();
    prior.verification.error_code = "runtime_insufficient_balance";
    const probeRuntimeModelCapability = vi.fn();
    const onEditConnection = vi.fn();
    renderRegistry(apiWith({ listRuntimeModels: vi.fn().mockResolvedValue({ schema_version: "1.0", models: [prior] }), probeRuntimeModelCapability }), "credential-1", true, onEditConnection);
    const row = await modelRow();
    expect(within(row).getByRole("alert")).toHaveTextContent(/balance or quota is exhausted/);
    await userEvent.setup().click(within(row).getByRole("button", { name: "Check service address" }));
    expect(onEditConnection).toHaveBeenCalledTimes(1);
    expect(probeRuntimeModelCapability).not.toHaveBeenCalled();
  });

  it("does not offer an active probe for capabilities the backend cannot verify", async () => {
    window.location.hash = "#/settings?requiredCapability=audio_generation";
    renderRegistry(apiWith({ probeRuntimeModelCapability: vi.fn() }));
    expect(await screen.findByText(/Active probing is not available for this capability yet/)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Actively verify" })).not.toHaveValue("audio_generation");
    expect(screen.queryByRole("option", { name: "Audio generation" })).not.toBeInTheDocument();
  });

  it("keeps a discovered model with no capability evidence unverified", async () => {
    renderRegistry(apiWith({ listRuntimeModels: vi.fn().mockResolvedValue({ schema_version: "1.0", models: [unknownProfile()] }) }));
    expect(await screen.findByText("Unverified")).toBeInTheDocument();
    expect(screen.queryByText("Actively verified")).not.toBeInTheDocument();
  });

  it("filters models to the selected Provider and keeps another Provider out of its setup flow", async () => {
    const other = profile({ model_profile_id: "profile-2", provider_connection_id: "credential-2", provider_label: "Other Provider", display_name: "Other model", provider_model_id: "other-model" });
    const api = apiWith({
      listRuntimeModels: vi.fn().mockResolvedValue({ schema_version: "1.0", models: [profile(), other] }),
      listRuntimeCredentials: vi.fn().mockResolvedValue({ schema_version: "1.0", credentials: [credential(), credential({ credential_id: "credential-2", label: "Other Provider", default_model_id: "other-model" })] }),
    });
    const view = renderRegistry(api, "credential-1", true);
    expect(await screen.findByText("Image model")).toBeInTheDocument();
    expect(screen.queryByText("Other model")).not.toBeInTheDocument();
    view.rerender(<ThemeProvider><ProjectWorkspaceProvider api={api}><ModelRegistryPanel locale="en" credentialId="credential-2" embedded /></ProjectWorkspaceProvider></ThemeProvider>);
    expect(await screen.findByText("Other model")).toBeInTheDocument();
    expect(screen.queryByText("Image model")).not.toBeInTheDocument();
  });

  it("opens the new Provider's model when the deep-linked profile belongs to another Provider", async () => {
    window.location.hash = "#/settings?modelProfileId=profile-1";
    const other = profile({ model_profile_id: "profile-2", provider_connection_id: "credential-2", provider_label: "Other Provider", display_name: "Other model", provider_model_id: "other-model" });
    const api = apiWith({
      listRuntimeModels: vi.fn().mockResolvedValue({ schema_version: "1.0", models: [profile(), other] }),
      listRuntimeCredentials: vi.fn().mockResolvedValue({ schema_version: "1.0", credentials: [credential(), credential({ credential_id: "credential-2", label: "Other Provider", default_model_id: "other-model" })] }),
      probeRuntimeModelCapability: vi.fn(),
    });
    const view = renderRegistry(api, "credential-1");
    expect(within(await modelRow()).getByRole("button", { name: "Verify" })).toBeInTheDocument();
    view.rerender(<ThemeProvider><ProjectWorkspaceProvider api={api}><ModelRegistryPanel locale="en" credentialId="credential-2" /></ProjectWorkspaceProvider></ThemeProvider>);

    const row = await modelRow("Other model");
    expect(within(row).getByRole("button", { name: "Other model" })).toHaveAttribute("aria-expanded", "true");
    expect(within(row).getByRole("button", { name: "Verify" })).toBeEnabled();
    expect(screen.queryByText("Image model")).not.toBeInTheDocument();
  });

  it("uses the new Provider's default ID when switching an unfinished manual setup", async () => {
    const addRuntimeModel = vi.fn().mockResolvedValue(unknownProfile({ model_profile_id: "other-manual", provider_connection_id: "credential-2", provider_model_id: "second-manual", display_name: "second-manual" }));
    const api = apiWith({
      listRuntimeModels: vi.fn().mockResolvedValue({ schema_version: "1.0", models: [] }),
      listRuntimeCredentials: vi.fn().mockResolvedValue({ schema_version: "1.0", credentials: [credential({ default_model_id: "first-manual" }), credential({ credential_id: "credential-2", label: "Other Provider", default_model_id: "second-manual" })] }),
      addRuntimeModel,
    });
    const view = renderRegistry(api, "credential-1");
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue("first-manual"));
    view.rerender(<ThemeProvider><ProjectWorkspaceProvider api={api}><ModelRegistryPanel locale="en" credentialId="credential-2" /></ProjectWorkspaceProvider></ThemeProvider>);
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue("second-manual"));
    await userEvent.setup().click(screen.getByRole("button", { name: "Add & verify" }));
    await waitFor(() => expect(addRuntimeModel).toHaveBeenCalledWith("credential-2", { provider_model_id: "second-manual" }));
    expect(addRuntimeModel).toHaveBeenCalledTimes(1);
  });

  it("prefills an unlisted default ID, adds it to the selected Provider, and opens it for verification", async () => {
    const saved = credential({ status: "unverified", readiness: "unverified", capabilities: { models: [] }, default_model_id: "manual-image-model", discovery_state: "failed", discovery_error_code: "runtime_model_discovery_unavailable" });
    const manual = unknownProfile({ model_profile_id: "manual-profile", display_name: "manual-image-model", provider_model_id: "manual-image-model", listed: false, registry_ready: false, connection_readiness: "unverified" });
    let models: ModelProfile[] = [profile()];
    const addRuntimeModel = vi.fn().mockImplementation(async () => { models = [...models, manual]; return manual; });
    const verified = { ...manual, capabilities: { ...manual.capabilities, text_generation: { status: "supported", evidence: { source: "active_probe", observed_at: "2026-10-04T00:00:00Z" } } }, connection_readiness: "ready", registry_ready: true };
    const probeRuntimeModelCapability = vi.fn().mockImplementation(async () => { models = [profile(), verified as ModelProfile]; return verified; });
    renderRegistry(apiWith({
      listRuntimeModels: vi.fn().mockImplementation(async () => ({ schema_version: "1.0", models })),
      listRuntimeCredentials: vi.fn().mockResolvedValue({ schema_version: "1.0", credentials: [saved] }),
      addRuntimeModel, probeRuntimeModelCapability,
    }), "credential-1", true);
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue("manual-image-model"));
    await userEvent.setup().click(screen.getByRole("button", { name: "Add & verify" }));
    const row = await modelRow("manual-image-model");
    const verify = within(row).getByRole("button", { name: "Verify" });
    await waitFor(() => expect(within(row).getByRole("combobox", { name: "Actively verify" })).toHaveFocus());
    expect(verify).toBeEnabled();
    expect(addRuntimeModel).toHaveBeenCalledWith("credential-1", { provider_model_id: "manual-image-model" });
    await userEvent.setup().click(verify);
    await waitFor(() => expect(probeRuntimeModelCapability).toHaveBeenCalledWith("manual-profile", "text_generation", false));
    expect(await within(row).findByText(/Text generation.*verified|verified.*Text generation/i)).toBeInTheDocument();
  });

  it("reports unsupported capability results in the target model row without a success message", async () => {
    const unknown = unknownProfile();
    const unsupported = { ...unknown, capabilities: { ...unknown.capabilities, text_generation: { status: "unsupported", evidence: { source: "provider_adapter", observed_at: "2026-10-04T00:00:00Z" } } } };
    renderRegistry(apiWith({ listRuntimeModels: vi.fn().mockResolvedValue({ schema_version: "1.0", models: [unknown] }), probeRuntimeModelCapability: vi.fn().mockResolvedValue(unsupported) }));
    const row = await modelRow();
    await userEvent.setup().click(within(row).getByRole("button", { name: "Verify" }));
    expect(await within(row).findByText(/does not support|unsupported/i)).toBeInTheDocument();
    expect(screen.queryByText(/Capability verification updated|Text generation.*verified successfully/i)).not.toBeInTheDocument();
  });

  it("does not report a failed verification response as successful", async () => {
    const unknown = unknownProfile();
    const failed = { ...unknown, verification: { ...unknown.verification, error_code: "runtime_invalid_response" } };
    renderRegistry(apiWith({ listRuntimeModels: vi.fn().mockResolvedValue({ schema_version: "1.0", models: [unknown] }), probeRuntimeModelCapability: vi.fn().mockResolvedValue(failed) }));
    const row = await modelRow();
    await userEvent.setup().click(within(row).getByRole("button", { name: "Verify" }));
    expect(await within(row).findByText(/could not|failed|not confirmed/i)).toBeInTheDocument();
    expect(screen.queryByText(/Capability verification updated|Text generation.*verified successfully/i)).not.toBeInTheDocument();
  });

  it("shows a rejected verification request beside the model that failed", async () => {
    renderRegistry(apiWith({ probeRuntimeModelCapability: vi.fn().mockRejectedValue(new Error("Synthetic probe failed")) }));
    const row = await modelRow();
    await userEvent.setup().click(within(row).getByRole("button", { name: "Verify" }));
    expect(await within(row).findByRole("alert")).toHaveTextContent(/This test did not finish/);
    expect(screen.queryByText("Synthetic probe failed")).not.toBeInTheDocument();
    expect(screen.queryByText(/Capability verification updated/)).not.toBeInTheDocument();
  });

  it.each([
    { readiness: "disabled", secret_state: "available", status: "disabled", reason: /disabled|enable/i },
    { readiness: "needs_reentry", secret_state: "missing", status: "active", reason: /key|re-enter|re-entry/i },
    { readiness: "unavailable", secret_state: "unavailable", status: "active", reason: /unavailable|secure store/i },
  ] as const)("blocks verification for a $readiness connection and explains the next step", async ({ readiness, secret_state, status, reason }) => {
    const probeRuntimeModelCapability = vi.fn();
    renderRegistry(apiWith({
      listRuntimeModels: vi.fn().mockResolvedValue({ schema_version: "1.0", models: [unknownProfile({ connection_readiness: readiness, registry_ready: false })] }),
      listRuntimeCredentials: vi.fn().mockResolvedValue({ schema_version: "1.0", credentials: [credential({ readiness, secret_state, status })] }),
      probeRuntimeModelCapability,
    }));
    const row = await modelRow();
    expect(within(row).getByRole("button", { name: "Verify" })).toBeDisabled();
    expect(within(row).getByText(reason)).toBeInTheDocument();
    expect(probeRuntimeModelCapability).not.toHaveBeenCalled();
  });
});
