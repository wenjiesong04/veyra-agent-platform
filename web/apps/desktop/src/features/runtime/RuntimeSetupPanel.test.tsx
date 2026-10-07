import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MODEL_CAPABILITY_NAMES, type ModelProfile } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { RuntimeSetupPanel } from "./RuntimeSetupPanel";

afterEach(cleanup);

describe("RuntimeSetupPanel", () => {
  it("keeps setup compact and opens model configuration without leaving the task", async () => {
    const recheck = vi.fn();
    render(<ThemeProvider><RuntimeSetupPanel locale="zh" returnTo="#/projects/project-1/agents/agent-1" onRecheck={recheck} resourceNames={{ "agent-1": "Renderer" }} issues={[{
      code: "model_capability_missing", scope: "agent-1", agent_id: "agent-1", resource_type: "agent", requirement: ["image_generation"], message: "这个 Agent 需要生成效果图。", action: "configure_model",
    }]} /></ThemeProvider>);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "配置模型" }));
    expect(screen.getByRole("dialog", { name: "配置运行模型" })).toBeInTheDocument();
    expect(screen.getByText("Renderer")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "图片生成" })).toBeInTheDocument();
    expect(screen.queryByText("model_capability_missing")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "在新标签中管理全部模型" }).getAttribute("href")).toContain("requiredCapability=image_generation");
    expect(screen.getByRole("link", { name: "在新标签中管理全部模型" }).getAttribute("href")).toContain("returnTo=%23%2Fprojects%2Fproject-1%2Fagents%2Fagent-1");
  });

  it("groups per-agent capability gaps on one model into a single verification step", async () => {
    const unverified = (agent: string, capability: "text_generation" | "image_input" | "image_generation", scope: string) => ({
      code: "model_capability_unverified", scope: `${agent}.${scope}`, agent_id: agent, resource_type: "model_profile", requirement: [capability],
      message: `Required capability '${capability}' has no current verified evidence on this Model Profile.`, action: "verify_model" as const, model_profile_id: "profile-kimi",
    });
    render(<ThemeProvider><RuntimeSetupPanel locale="zh" returnTo="#/workflow" resourceNames={{ identify: "Analyzer", render: "Renderer" }} issues={[
      unverified("identify", "text_generation", "primary_model"),
      unverified("identify", "image_input", "primary_model"),
      unverified("render", "text_generation", "primary_model"),
      unverified("render", "image_input", "primary_model"),
      unverified("render", "image_generation", "image_model"),
    ]} /></ThemeProvider>);
    expect(screen.getByText(/2 项待完成/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "配置模型" }));
    expect(screen.getByRole("heading", { name: "文字生成、图片理解" })).toBeInTheDocument();
    expect(screen.getByText("Analyzer、Renderer")).toBeInTheDocument();
    expect(screen.queryByText(/has no current verified evidence/)).not.toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: "在新标签中管理全部模型" });
    expect(links).toHaveLength(2);
    expect(links[0].getAttribute("href")).toContain("modelProfileId=profile-kimi");
    expect(links[0].getAttribute("href")).not.toContain("add-provider");
  });

  it("replaces a Workflow child's image binding with a compatible model and rechecks", async () => {
    const capabilities = Object.fromEntries(MODEL_CAPABILITY_NAMES.map((name) => [name, { status: "unknown", evidence: null }])) as ModelProfile["capabilities"];
    capabilities.image_generation = { status: "supported", evidence: { source: "active_probe", observed_at: "2026-10-04T00:00:00Z" } };
    const model = { model_profile_id: "image-profile", provider_connection_id: "image-credential", provider_model_id: "fake-image", provider_label: "Image Provider", display_name: "Image model", capabilities, registry_ready: true } as ModelProfile;
    const api = { listRuntimeModels: vi.fn().mockResolvedValue({ schema_version: "1.0", models: [model] }), setRuntimeBinding: vi.fn().mockResolvedValue({}) };
    const recheck = vi.fn();
    render(<ThemeProvider><RuntimeSetupPanel locale="en" projectId="project-1" api={api} returnTo="#/workflow" onRecheck={recheck} issues={[{
      code: "model_binding_unsupported", scope: "render.image_model", node_id: "render", agent_id: "renderer-agent", resource_type: "model_profile", requirement: ["image_generation"], message: "Choose an image model.", action: "rebind_model",
    }]} /></ThemeProvider>);
    await userEvent.setup().click(screen.getByRole("button", { name: "Set up models" }));
    expect(await screen.findByRole("option", { name: "Image Provider · Image model · Ready" })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Use this model" }));
    await waitFor(() => expect(api.setRuntimeBinding).toHaveBeenCalledWith("project-1", { credential_id: "image-credential", model_id: "fake-image", slot: "image_model" }, "renderer-agent"));
    expect(recheck).toHaveBeenCalledTimes(1);
  });

  it("verifies an unknown image capability only after cost consent, binds and rechecks", async () => {
    const capabilities = Object.fromEntries(MODEL_CAPABILITY_NAMES.map((name) => [name, { status: "unknown", evidence: null }])) as ModelProfile["capabilities"];
    const model = { model_profile_id: "image-profile", provider_connection_id: "image-credential", provider_model_id: "fake-image", provider_label: "Provider", display_name: "Image", capabilities, registry_ready: true } as ModelProfile;
    const verified = { ...model, capabilities: { ...capabilities, image_generation: { status: "supported", evidence: { source: "active_probe", observed_at: "2026-10-04T00:00:00Z" } } } } as ModelProfile;
    const api = { listRuntimeModels: vi.fn().mockResolvedValue({ schema_version: "1.0", models: [model] }), probeRuntimeModelCapability: vi.fn().mockResolvedValue(verified), setRuntimeBinding: vi.fn().mockResolvedValue({}) };
    const recheck = vi.fn().mockResolvedValue(undefined);
    render(<ThemeProvider><RuntimeSetupPanel api={api} projectId="project-1" locale="en" returnTo="#/task" onRecheck={recheck} issues={[{ code: "model_capability_unverified", scope: "image_model", agent_id: "agent-1", model_profile_id: "image-profile", resource_type: "model_profile", requirement: ["image_generation"], message: "Unknown", action: "verify_model" }]} /></ThemeProvider>);
    await userEvent.setup().click(screen.getByRole("button", { name: "Set up models" }));
    const verify = await screen.findByRole("button", { name: "Verify & use" });
    expect(verify).toBeDisabled();
    expect(api.probeRuntimeModelCapability).not.toHaveBeenCalled();
    await userEvent.setup().click(screen.getByRole("checkbox", { name: /may incur a small API charge/ }));
    await userEvent.setup().click(verify);
    await waitFor(() => expect(recheck).toHaveBeenCalledTimes(1));
    expect(api.probeRuntimeModelCapability).toHaveBeenCalledWith("image-profile", "image_generation", true);
    expect(api.setRuntimeBinding).toHaveBeenCalledWith("project-1", { credential_id: "image-credential", model_id: "fake-image", slot: "image_model" }, "agent-1");
  });

  it("adds an API and verifies its model in place while preserving task input", async () => {
    const capabilities = Object.fromEntries(MODEL_CAPABILITY_NAMES.map((name) => [name, { status: "unknown", evidence: null }])) as ModelProfile["capabilities"];
    const model = { model_profile_id: "added-profile", provider_connection_id: "added-credential", provider_model_id: "image-test", provider_label: "My API", display_name: "Image", capabilities, registry_ready: true } as ModelProfile;
    const verified = { ...model, capabilities: { ...capabilities, image_generation: { status: "supported", evidence: { source: "active_probe", observed_at: "2026-10-04T00:00:00Z" } } } } as ModelProfile;
    let models: ModelProfile[] = [];
    const api = {
      listRuntimeModels: vi.fn(async () => ({ schema_version: "1.0" as const, models })),
      createRuntimeCredential: vi.fn(async () => { models = [model]; return { valid: true, code: "validated", message: "saved", credential: { credential_id: "added-credential" }, models }; }),
      probeRuntimeModelCapability: vi.fn().mockResolvedValue(verified), setRuntimeBinding: vi.fn().mockResolvedValue({}),
    } as unknown as NonNullable<Parameters<typeof RuntimeSetupPanel>[0]["api"]>;
    const recheck = vi.fn().mockResolvedValue(undefined);
    render(<ThemeProvider><input aria-label="Task" defaultValue="design a gift package" /><RuntimeSetupPanel api={api} projectId="project-1" locale="en" returnTo="#/task" onRecheck={recheck} issues={[{ code: "image_model_not_configured", scope: "image_model", agent_id: "agent-1", resource_type: "model_profile", requirement: ["image_generation"], message: "Missing", action: "configure_model" }]} /></ThemeProvider>);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Set up models" }));
    await user.click(await screen.findByRole("button", { name: "Add a model API" }));
    await user.selectOptions(screen.getByLabelText("Provider"), "openai");
    await user.type(screen.getByLabelText("Connection name"), "My API");
    await user.type(screen.getByLabelText("API Key"), "fake-test-only-key");
    await user.click(screen.getByRole("button", { name: "Save & check connection" }));
    const verify = await screen.findByRole("button", { name: "Verify & use" });
    expect(api.probeRuntimeModelCapability).not.toHaveBeenCalled();
    expect(verify).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: /may incur a small API charge/ }));
    await user.click(verify);
    await waitFor(() => expect(recheck).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText("Task")).toHaveValue("design a gift package");
  });
});
