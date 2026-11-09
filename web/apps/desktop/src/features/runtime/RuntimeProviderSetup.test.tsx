import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@veyra/ui";
import { RuntimeProviderSetup } from "./RuntimeProviderSetup";
import { LocalApiClientError } from "../../api/local-client";

afterEach(cleanup);

describe("RuntimeProviderSetup", () => {
  it("continues with a manual ID after discovery fails without creating another credential", async () => {
    const result = { valid: false, code: "runtime_model_discovery_unavailable", message: "No model list", credential: { credential_id: "fake-credential" }, models: [] };
    const api = { createRuntimeCredential: vi.fn().mockResolvedValue(result), addRuntimeModel: vi.fn().mockResolvedValue({ model_profile_id: "manual-profile" }) };
    const saved = vi.fn();
    render(<ThemeProvider><RuntimeProviderSetup locale="en" api={api} onBack={vi.fn()} onSaved={saved} /></ThemeProvider>);
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Provider"), "openai");
    await user.type(screen.getByLabelText("Connection name"), "Test Provider");
    await user.type(screen.getByLabelText(/^API Key/), "fake-test-only-key");
    await user.click(screen.getByRole("button", { name: "Save & check connection" }));
    expect(await screen.findByText(/This platform did not provide a model list/)).toBeInTheDocument();
    expect(screen.queryByLabelText("API Key")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Model ID"), "manual-model");
    await user.click(screen.getByRole("button", { name: "Add this model" }));
    await waitFor(() => expect(saved).toHaveBeenCalledTimes(1));
    expect(api.createRuntimeCredential).toHaveBeenCalledTimes(1);
    expect(api.addRuntimeModel).toHaveBeenCalledWith("fake-credential", { provider_model_id: "manual-model" });
  });

  it("reuses the saved connection when manual model registration fails and is retried", async () => {
    const api = {
      createRuntimeCredential: vi.fn().mockResolvedValue({ valid: true, code: "default_model_unavailable", message: "not listed", credential: { credential_id: "saved-credential" }, models: [] }),
      addRuntimeModel: vi.fn().mockRejectedValueOnce(new Error("Registration failed")).mockResolvedValueOnce({ model_profile_id: "manual-profile" }),
    };
    const saved = vi.fn();
    render(<ThemeProvider><RuntimeProviderSetup locale="en" api={api} onBack={vi.fn()} onSaved={saved} /></ThemeProvider>);
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Provider"), "openai");
    await user.type(screen.getByLabelText("Connection name"), "Provider");
    await user.type(screen.getByLabelText(/^API Key/), "fake-test-only-key");
    await user.click(screen.getByText("Connection options"));
    await user.type(screen.getByLabelText("Model ID"), "manual-model");
    await user.click(screen.getByRole("button", { name: "Save & check connection" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This test did not finish");
    expect(screen.queryByText("Registration failed")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add this model" }));
    await waitFor(() => expect(saved).toHaveBeenCalledTimes(1));
    expect(api.createRuntimeCredential).toHaveBeenCalledTimes(1);
    expect(api.addRuntimeModel).toHaveBeenCalledTimes(2);
  });

  it("fills the official service address and optional name from a preset while requiring a key", async () => {
    const api = {
      createRuntimeCredential: vi.fn().mockResolvedValue({ valid: true, code: "validated", credential: { credential_id: "qwen-api" }, models: [] }),
      addRuntimeModel: vi.fn(),
    };
    const saved = vi.fn();
    render(<ThemeProvider><RuntimeProviderSetup locale="en" api={api} onBack={vi.fn()} onSaved={saved} /></ThemeProvider>);
    const user = userEvent.setup();
    const save = screen.getByRole("button", { name: "Save & check connection" });
    expect(save).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Provider"), "dashscope");
    const address = screen.getByLabelText(/^Service address/);
    expect(address).toHaveValue("https://dashscope.aliyuncs.com/compatible-mode/v1");
    expect(address.closest("details")).toBeNull();
    expect(screen.getByLabelText("Connection name")).toHaveValue("");
    expect(save).toBeDisabled();
    await user.type(screen.getByLabelText(/^API Key/), "fake-qwen-key");
    await user.click(save);
    await waitFor(() => expect(saved).toHaveBeenCalledTimes(1));
    expect(api.createRuntimeCredential).toHaveBeenCalledWith({
      provider_type: "openai_compatible",
      label: "Qwen · Alibaba Model Studio (China)",
      api_key: "fake-qwen-key",
      base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    });
    expect(api.addRuntimeModel).not.toHaveBeenCalled();
  });

  it("accepts an unknown compatible API address without needing a brand preset", async () => {
    const api = {
      createRuntimeCredential: vi.fn().mockResolvedValue({ valid: true, code: "validated", credential: { credential_id: "custom-api" }, models: [] }),
      addRuntimeModel: vi.fn(),
    };
    render(<ThemeProvider><RuntimeProviderSetup locale="en" api={api} onBack={vi.fn()} onSaved={vi.fn()} /></ThemeProvider>);
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Provider"), "openai_compatible");
    const address = screen.getByLabelText(/^Service address/);
    expect(address.closest("details")).toBeNull();
    await user.type(address, "https://independent.example/api/v4/chat/completions/");
    await user.type(screen.getByLabelText(/^API Key/), "fake-custom-key");
    await user.click(screen.getByRole("button", { name: "Save & check connection" }));
    await waitFor(() => expect(api.createRuntimeCredential).toHaveBeenCalledTimes(1));
    expect(api.createRuntimeCredential).toHaveBeenCalledWith(expect.objectContaining({
      provider_type: "openai_compatible", base_url: "https://independent.example/api/v4",
    }));
  });

  it("blocks a console webpage address before creating or validating a connection", async () => {
    const api = { createRuntimeCredential: vi.fn(), addRuntimeModel: vi.fn() };
    render(<ThemeProvider><RuntimeProviderSetup locale="en" api={api} onBack={vi.fn()} onSaved={vi.fn()} /></ThemeProvider>);
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Provider"), "openai_compatible");
    await user.type(screen.getByLabelText(/^Service address/), "https://bailian.console.aliyun.com/cn-beijing/settings/api-key");
    await user.type(screen.getByLabelText(/^API Key/), "fake-key-must-stay-local");
    const submit = screen.getByRole("button", { name: "Save & check connection" });
    expect(submit).toBeDisabled();
    await user.click(submit);
    fireEvent.submit(submit.closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent(/account or API-key webpage/);
    expect(api.createRuntimeCredential).not.toHaveBeenCalled();
    expect(api.addRuntimeModel).not.toHaveBeenCalled();
  });

  it("renders localized error guidance without returning raw provider messages", async () => {
    const api = {
      createRuntimeCredential: vi.fn().mockRejectedValue(new LocalApiClientError("PRIVATE-KEY-AND-PROVIDER-BODY", { status: 422, code: "runtime_insufficient_balance" })),
      addRuntimeModel: vi.fn(),
    };
    render(<ThemeProvider><RuntimeProviderSetup locale="zh" api={api} onBack={vi.fn()} onSaved={vi.fn()} /></ThemeProvider>);
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("你的 API 来自哪个平台？"), "openai");
    await user.type(screen.getByLabelText(/^API 密钥/), "fake-private-key");
    await user.click(screen.getByRole("button", { name: "保存并检查 API" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("服务商余额或可用额度不足");
    expect(screen.queryByText(/PRIVATE-KEY-AND-PROVIDER-BODY/)).not.toBeInTheDocument();
    expect(api.addRuntimeModel).not.toHaveBeenCalled();
  });
});
