import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@veyra/ui";
import { ProjectWorkspaceProvider } from "../api/project-workspace";
import type { LocalProjectApi } from "../api/local-client";
import { SettingsPage } from "./settings";

function renderSettings() {
  const api = {
    factoryStatus: vi.fn().mockResolvedValue({ configured: true, capability_profile: null }),
    listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
    listRuntimeCredentials: vi.fn().mockResolvedValue({ schema_version: "1.0", credentials: [] }),
    listRuntimeModels: vi.fn().mockResolvedValue({ schema_version: "1.0", models: [] }),
    listRuntimeModelDefaults: vi.fn().mockResolvedValue({ schema_version: "1.0", defaults: [] }),
    getSecretStatus: vi.fn().mockResolvedValue({ schema_version: "1.0", secret_ref: "github.main", env_name: "GITHUB_TOKEN", configured: false, source: "missing" }),
    setSecret: vi.fn().mockResolvedValue({ schema_version: "1.0", secret_ref: "github.main", env_name: "GITHUB_TOKEN", configured: true, source: "keychain" }),
  } as unknown as LocalProjectApi;
  render(<ThemeProvider><ProjectWorkspaceProvider api={api}><SettingsPage /></ProjectWorkspaceProvider></ThemeProvider>);
  return api;
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("veyra.language", "en");
  window.location.hash = "#/settings";
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  window.location.hash = "";
});

describe("SettingsPage", () => {
  it("keeps an unsaved Token when changing settings categories and saves only on request", async () => {
    const api = renderSettings();
    const user = userEvent.setup();
    const categories = screen.getByRole("navigation", { name: "Settings sections" });
    await user.click(within(categories).getByRole("button", { name: "Tool credentials" }));
    await user.type(await screen.findByLabelText("Token"), "fake-unsaved-token");
    await user.click(within(categories).getByRole("button", { name: "Appearance" }));
    expect(window.location.hash).toContain("settingsSection=appearance");
    await user.click(within(categories).getByRole("button", { name: "Tool credentials" }));
    expect(screen.getByLabelText("Token")).toHaveValue("fake-unsaved-token");
    expect(api.setSecret).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Save Token" }));
    expect(await screen.findByText("Token saved securely on this device.")).toBeInTheDocument();
    expect(api.setSecret).toHaveBeenCalledWith("github.main", "fake-unsaved-token");
    expect(screen.getByLabelText("Token")).toHaveValue("");
  });

  it("applies and retains the selected appearance while moving between settings categories", async () => {
    renderSettings();
    const user = userEvent.setup();
    const categories = screen.getByRole("navigation", { name: "Settings sections" });
    await user.click(within(categories).getByRole("button", { name: "Appearance" }));
    await user.click(screen.getByRole("button", { name: "Dark" }));
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(localStorage.getItem("veyra.theme")).toBe("dark");
    await user.click(within(categories).getByRole("button", { name: "Model APIs" }));
    await user.click(within(categories).getByRole("button", { name: "Appearance" }));
    expect(screen.getByRole("button", { name: "Dark" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Light" })).toHaveAttribute("aria-pressed", "false");
  });

  it("applies and persists reduced motion across settings navigation and remounts", async () => {
    renderSettings();
    const user = userEvent.setup();
    const categories = screen.getByRole("navigation", { name: "Settings sections" });
    await user.click(within(categories).getByRole("button", { name: "Appearance" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Interface motion" }), "reduced");
    expect(document.documentElement).toHaveAttribute("data-motion", "reduced");
    expect(localStorage.getItem("veyra.theme.motion")).toBe("reduced");
    expect(screen.getByText(/Interface animations reduced/)).toBeInTheDocument();
    await user.click(within(categories).getByRole("button", { name: "Model APIs" }));
    await user.click(within(categories).getByRole("button", { name: "Appearance" }));
    expect(screen.getByRole("combobox", { name: "Interface motion" })).toHaveValue("reduced");
    cleanup();
    renderSettings();
    expect(screen.getByRole("combobox", { name: "Interface motion" })).toHaveValue("reduced");
    expect(document.documentElement).toHaveAttribute("data-motion", "reduced");
    await user.selectOptions(screen.getByRole("combobox", { name: "Interface motion" }), "system");
    expect(document.documentElement).toHaveAttribute("data-motion", "system");
    expect(localStorage.getItem("veyra.theme.motion")).toBe("system");
  });

  it("changes the interface language and explains the creation assistant in ordinary language", async () => {
    renderSettings();
    const user = userEvent.setup();
    const categories = screen.getByRole("navigation", { name: "Settings sections" });
    await user.click(within(categories).getByRole("button", { name: "Creation assistant" }));
    expect(screen.getByRole("heading", { name: "Creation assistant" })).toBeInTheDocument();
    expect(screen.getByText("Turn your ideas into Agents and Workflows.")).toBeInTheDocument();
    expect(within(categories).queryByRole("button", { name: "Builder service" })).not.toBeInTheDocument();
    await user.click(within(categories).getByRole("button", { name: "Appearance" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Interface language" }), "zh");
    expect(localStorage.getItem("veyra.language")).toBe("zh");
    expect(document.documentElement.lang).toBe("zh-CN");
    expect(screen.getByRole("combobox", { name: "界面语言" })).toHaveValue("zh");
    expect(screen.getByRole("heading", { name: "界面偏好" })).toBeInTheDocument();
  });
});
