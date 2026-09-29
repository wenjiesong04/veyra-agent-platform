import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ShowcaseApp } from "./showcase";
import { CommunitySite } from "./site";

beforeEach(() => {
  window.localStorage.clear();
  window.history.replaceState(null, "", "#home");
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "#home");
});

describe("Veyra public showcase", () => {
  it("renders product information without exposing Community workspace controls", () => {
    render(<ShowcaseApp />);

    expect(screen.getByRole("heading", { level: 1, name: "Build, inspect, run and share AI agents from a local-first workspace." })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "A reviewable path, not a black box." })).toBeInTheDocument();
    expect(screen.getByText("Local-first does not mean network-free.")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "A workflow you can inspect" })).toBeInTheDocument();
    expect(screen.getByText("Structure illustration only. No live Project or Run data.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Published" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Starred" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Following" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /sign in|register|publish|import/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
  });

  it("does not contact Community APIs during initial render", () => {
    render(<ShowcaseApp />);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("provides working section links and real repository/document targets", () => {
    render(<ShowcaseApp />);
    const navigation = screen.getByRole("navigation", { name: "Primary navigation" });
    expect(within(navigation).getByRole("link", { name: "Product" })).toHaveAttribute("href", "#product");
    expect(within(navigation).getByRole("link", { name: "How it works" })).toHaveAttribute("href", "#how-it-works");
    expect(within(navigation).getByRole("link", { name: "Safety" })).toHaveAttribute("href", "#safety");
    expect(within(navigation).getByRole("link", { name: "Docs" })).toHaveAttribute("href", "#docs");
    expect(within(navigation).getByRole("link", { name: "Download" })).toHaveAttribute("href", "#download");
    expect(screen.getByRole("link", { name: "Build from source" })).toHaveAttribute("href", "https://github.com/wenjiesong04/veyra-agent-platform/blob/codex/agent-platform/docs/desktop_packaging.md");
    expect(screen.getByRole("link", { name: "README and setup" })).toHaveAttribute("href", "https://github.com/wenjiesong04/veyra-agent-platform/blob/codex/agent-platform/README.md");
  });

  it("renders complete Chinese content and can switch back to English", async () => {
    const user = userEvent.setup();
    render(<ShowcaseApp />);
    await user.click(screen.getByRole("button", { name: "Switch to Chinese" }));

    expect(await screen.findByRole("heading", { level: 1, name: "在本机优先的工作空间中构建、检查、运行和分享 Agent。" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "主导航" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "本机优先，不代表完全离线。" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "目前尚无公开安装包。" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "切换到英文" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Build, inspect, run and share AI agents from a local-first workspace." })).toBeInTheDocument();
  });

  it("supports theme switching and an accessible mobile navigation toggle", async () => {
    const user = userEvent.setup();
    render(<ShowcaseApp />);
    const menu = screen.getByRole("button", { name: "Open navigation" });
    expect(menu).toHaveAttribute("aria-expanded", "false");
    await user.click(menu);
    expect(screen.getByRole("button", { name: "Close navigation" })).toHaveAttribute("aria-expanded", "true");
    await user.click(screen.getByRole("button", { name: "Switch to dark theme" }));
    await waitFor(() => expect(document.documentElement).toHaveAttribute("data-theme", "dark"));
  });

  it.each(["#/community/published", "#/community/starred", "#/community/following", "#/login", "#/register"]) (
    "redirects legacy workspace URL %s to the public home without rendering management UI",
    async (legacyHash) => {
      window.history.replaceState(null, "", legacyHash);
      render(<ShowcaseApp />);
      expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
      expect(screen.queryByRole("heading", { name: /published|starred|following|sign in|register/i })).not.toBeInTheDocument();
      await waitFor(() => expect(window.location.hash).toBe("#home"));
      expect(globalThis.fetch).not.toHaveBeenCalled();
    },
  );

  it("normalizes an in-page legacy Registry hash without loading a workspace", async () => {
    render(<ShowcaseApp />);
    window.location.hash = "#/community/published";
    await waitFor(() => expect(window.location.hash).toBe("#home"));
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Published" })).not.toBeInTheDocument();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

describe("5174 community and showcase", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "not_found" }), { status: 404, headers: { "Content-Type": "application/json" } })));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    window.history.replaceState(null, "", "#home");
  });

  it("opens the public showcase without the cloud workspace", async () => {
    window.history.replaceState(null, "", "#/projects");
    render(<CommunitySite />);
    expect(await screen.findByRole("heading", { level: 1, name: "Build, inspect, run and share AI agents from a local-first workspace." })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Your Veyra workspace" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Chat" })).not.toBeInTheDocument();
    await waitFor(() => expect(window.location.hash).toBe("#home"));
  });

  it("opens the community catalog instead of a cloud project workspace", async () => {
    window.history.replaceState(null, "", "#/community");
    render(<CommunitySite />);
    expect(await screen.findByRole("heading", { name: "Discover" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Your Veyra workspace" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: /local-first workspace/ })).not.toBeInTheDocument();
  });
});
