import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@veyra/ui";
import { parseDesktopRoute } from "@veyra/api-contracts";
import { CommunityWebsiteBoundary, CommunityWebsitePage } from "./community-website-entry";
import { COMMUNITY_SITE_SETUP, communityWebsiteHref, openCommunityWebsite, resolveCommunityWebsite } from "./community-website";

const originalClipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");

beforeEach(() => {
  window.localStorage.setItem("veyra.language", "en");
  window.history.replaceState(null, "", "/#/projects/project-1/chat");
  vi.stubEnv("VITE_COMMUNITY_SITE_URL", "https://community.example/veyra/");
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  if (originalClipboard) Object.defineProperty(navigator, "clipboard", originalClipboard);
  else Reflect.deleteProperty(navigator, "clipboard");
});

function renderBoundary() {
  return render(<ThemeProvider><CommunityWebsiteBoundary><a href="#/community">Community</a><p>Current workspace</p></CommunityWebsiteBoundary></ThemeProvider>);
}

describe("Desktop Community website boundary", () => {
  it("uses loopback only as a development default and requires a production configuration", () => {
    expect(resolveCommunityWebsite(undefined, true)).toEqual({ status: "ready", baseUrl: "http://127.0.0.1:5174/" });
    expect(resolveCommunityWebsite(undefined, false)).toEqual({ status: "missing" });
    expect(resolveCommunityWebsite(" ", false)).toEqual({ status: "missing" });
  });

  it.each(["javascript:alert(1)", "file:///tmp/community", "tauri://localhost", "mailto:user@example.com", "/community", "https://user:password@community.example", "https://community.example/?token=private", "https://community.example/#/community"])("rejects unsafe or non-base website configuration %s", (url) => {
    expect(resolveCommunityWebsite(url, true)).toEqual({ status: "invalid" });
  });

  it.each([
    ["#/community", "/community"], ["#/community/published", "/community/published"], ["#/community/starred", "/community/starred"], ["#/community/mine", "/community/mine"],
    ["#/community/ada/gift-box", "/community/ada/gift-box"], ["#/community/ada/gift-box/versions/1.2.0", "/community/ada/gift-box/versions/1.2.0"],
  ])("preserves the web destination for legacy route %s", (hash, expected) => {
    expect(communityWebsiteHref({ status: "ready", baseUrl: "https://community.example/veyra/" }, hash, "zh")).toBe(`https://community.example/veyra/?lang=zh#${expected}`);
  });

  it("opens an isolated browser tab after a click without changing the current desktop route", () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    renderBoundary();
    expect(open).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("link", { name: "Community" }));
    expect(open).toHaveBeenCalledWith("https://community.example/veyra/?lang=en#/community", "_blank", "noopener,noreferrer");
    expect(window.location.hash).toBe("#/projects/project-1/chat");
    expect(screen.getByText("Current workspace")).toBeInTheDocument();
  });

  it("shows a copyable setup example when a production build has no website URL", async () => {
    vi.stubEnv("DEV", false);
    vi.stubEnv("VITE_COMMUNITY_SITE_URL", "");
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    renderBoundary();
    fireEvent.click(screen.getByRole("link", { name: "Community" }));
    expect(screen.getByRole("heading", { name: "Community website not configured" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Copy configuration example" })).toHaveValue(COMMUNITY_SITE_SETUP);
    expect(screen.getByRole("button", { name: "Copy configuration example" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Copy configuration example" }));
    expect(writeText).toHaveBeenCalledWith(COMMUNITY_SITE_SETUP);
    expect(await screen.findByRole("status")).toHaveTextContent("Copied.");
    expect(window.location.hash).toBe("#/projects/project-1/chat");
    expect(open).not.toHaveBeenCalled();
  });

  it("does not echo credentials from an invalid configuration into its error notice", () => {
    vi.stubEnv("VITE_COMMUNITY_SITE_URL", "https://user:private-password@community.example");
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    renderBoundary();
    fireEvent.click(screen.getByRole("link", { name: "Community" }));
    expect(screen.getByRole("heading", { name: "Invalid Community website configuration" })).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("private-password");
    expect(screen.getByRole("textbox", { name: "Copy configuration example" })).toHaveValue(COMMUNITY_SITE_SETUP);
    expect(open).not.toHaveBeenCalled();
  });

  it("offers an explicit external destination for an old resource-version route without opening it on load", () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const route = parseDesktopRoute("#/community/ada/gift-box/versions/1.2.0");
    render(<ThemeProvider><CommunityWebsiteBoundary><CommunityWebsitePage route={route} /></CommunityWebsiteBoundary></ThemeProvider>);
    expect(screen.getByRole("heading", { name: "Community is on the web" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Copy link" })).toHaveValue("https://community.example/veyra/?lang=en#/community/ada/gift-box/versions/1.2.0");
    expect(open).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Open Community website" }));
    expect(open).toHaveBeenCalledWith("https://community.example/veyra/?lang=en#/community/ada/gift-box/versions/1.2.0", "_blank", "noopener,noreferrer");
  });

  it("uses the existing Tauri shell open command instead of browser window.open", async () => {
    const invoke = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("__TAURI__", { core: { invoke } });
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    await openCommunityWebsite("https://community.example/?lang=en#/community");
    expect(invoke).toHaveBeenCalledWith("plugin:shell|open", { path: "https://community.example/?lang=en#/community" });
    expect(open).not.toHaveBeenCalled();
  });

  it("does not fall back to an embedded webview when the native bridge is unavailable", async () => {
    vi.stubGlobal("__TAURI_INTERNALS__", {});
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    await expect(openCommunityWebsite("https://community.example/#/community")).rejects.toThrow("community_browser_bridge_unavailable");
    expect(open).not.toHaveBeenCalled();
  });

  it("provides a copyable link after a native failure and clears the notice on an explicit retry", async () => {
    const invoke = vi.fn().mockRejectedValueOnce(new Error("permission denied")).mockResolvedValue(undefined);
    vi.stubGlobal("__TAURI__", { core: { invoke } });
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    renderBoundary();
    fireEvent.click(screen.getByRole("link", { name: "Community" }));
    expect(await screen.findByRole("heading", { name: "Could not open the Community website" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Copy link" })).toHaveValue("https://community.example/veyra/?lang=en#/community");
    fireEvent.click(screen.getByRole("link", { name: "Community" }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Could not open the Community website" })).not.toBeInTheDocument());
    expect(invoke).toHaveBeenCalledTimes(2);
    expect(open).not.toHaveBeenCalled();
    expect(window.location.hash).toBe("#/projects/project-1/chat");
  });

  it("rejects an unsafe destination before invoking native code", async () => {
    const invoke = vi.fn();
    vi.stubGlobal("__TAURI__", { core: { invoke } });
    await expect(openCommunityWebsite("file:///tmp/community")).rejects.toThrow("unsafe_community_website");
    await expect(openCommunityWebsite("https://user:password@community.example")).rejects.toThrow("unsafe_community_website");
    expect(invoke).not.toHaveBeenCalled();
  });

  it("keeps the packaged shell open scope restricted to HTTP(S), with no execution permission", () => {
    const nativeRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../../../../../apps/desktop/src-tauri");
    const config = JSON.parse(readFileSync(resolve(nativeRoot, "tauri.conf.json"), "utf8")) as { app: { withGlobalTauri: boolean }; plugins: { shell: { open: string } } };
    const capability = JSON.parse(readFileSync(resolve(nativeRoot, "capabilities/default.json"), "utf8")) as { permissions: unknown[] };
    const allowed = new RegExp(`^(?:${config.plugins.shell.open})$`);
    expect(config.app.withGlobalTauri).toBe(true);
    expect(capability.permissions).toContain("shell:allow-open");
    expect(capability.permissions).not.toContain("shell:allow-execute");
    for (const value of ["http://127.0.0.1:5174/?lang=en#/community", "https://community.example/#/community", "http://[::1]:5174/"]) expect(allowed.test(value)).toBe(true);
    for (const value of ["file:///tmp/file", "javascript:alert(1)", "mailto:user@example.com", "tel:1234", "--execute", "https://user:pass@community.example"]) expect(allowed.test(value)).toBe(false);
  });
});
