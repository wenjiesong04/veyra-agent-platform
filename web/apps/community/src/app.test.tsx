import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ShowcaseApp } from "./showcase";
import { CommunitySite, isCommunitySitePath } from "./site";

beforeEach(() => {
  window.localStorage.clear();
  window.history.replaceState(null, "", "/#home");
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/#home");
});

describe("Veyra public showcase", () => {
  it("shows the product without exposing account or workspace controls", () => {
    render(<ShowcaseApp />);
    expect(screen.getByRole("heading", { level: 1, name: /Describe a task\.\s*Build your Agent\./ })).toBeInTheDocument();
    expect(screen.getByText("Veyra / AI studio")).toBeInTheDocument();
    expect(screen.getByText(/Your workspace is local/)).toBeInTheDocument();
    expect(screen.getByText(/existing outputs from one gift-packaging case/)).toBeInTheDocument();
    expect(screen.queryByText(/CSV reconciliation|60\.10/)).not.toBeInTheDocument();
    expect([...document.querySelectorAll('img[src^="/showcase/"]')].every((image) => image.getAttribute("src")?.startsWith("/showcase/gift-"))).toBe(true);
    expect(screen.queryByRole("link", { name: /sign in|register|publish|import/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
    expect(screen.queryByRole("contentinfo")).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("keeps the original section deep links and real documentation targets", () => {
    render(<ShowcaseApp />);
    const navigation = screen.getByRole("navigation", { name: "Primary navigation" });
    expect(within(navigation).getAllByRole("link").map((link) => link.textContent)).toEqual(["Demo", "Product", "Control", "Docs", "Community"]);
    for (const [name, href] of [["Demo", "#demo"], ["Product", "#product"], ["Control", "#safety"], ["Docs", "#/docs"], ["Community", "#/community"]]) {
      expect(within(navigation).getByRole("link", { name })).toHaveAttribute("href", href);
    }
    for (const anchor of ["product", "how-it-works", "safety", "docs", "download", "experience", "control", "start"]) {
      expect(document.getElementById(anchor)).toBeInTheDocument();
    }
    expect(screen.getByRole("link", { name: /Desktop build guide/ })).toHaveAttribute("href", "https://github.com/wenjiesong04/veyra-agent-platform/blob/codex/agent-platform/docs/desktop_packaging.md");
    const buildLinks = screen.getAllByRole("link", { name: "Build" });
    expect(buildLinks).toHaveLength(2);
    for (const link of buildLinks) expect(link).toHaveAttribute("href", "#/docs/get-started");
    expect(screen.getByRole("link", { name: "Explore the case" })).toHaveAttribute("href", "#product");
  });

  it("switches the complete page language using the existing preference", async () => {
    const user = userEvent.setup();
    render(<ShowcaseApp />);
    await user.click(screen.getByRole("button", { name: "Switch to Chinese" }));
    expect(await screen.findByRole("heading", { level: 1, name: /描述任务，\s*创建你的 Agent。/ })).toBeInTheDocument();
    expect(screen.getByText("Veyra / AI 工作室")).toBeInTheDocument();
    expect(within(screen.getByRole("navigation", { name: "主导航" })).getByRole("link", { name: "社区" })).toHaveAttribute("href", "#/community");
    expect(screen.getByText(/公开安装包尚未通过发布验收/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "切换到英文" }));
    expect(await screen.findByText("Veyra / AI studio")).toBeInTheDocument();
  });
});

describe("5174 community and showcase routing", () => {
  it("normalizes an unknown legacy workspace route to the normal homepage", async () => {
    window.history.replaceState(null, "", "/?lang=zh#/projects");
    render(<CommunitySite />);
    expect(await screen.findByRole("heading", { level: 1, name: /描述任务，\s*创建你的 Agent。/ })).toBeInTheDocument();
    await waitFor(() => expect(window.location.hash).toBe("#home"));
    expect(window.location.search).toBe("?lang=zh");
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each(["community", "/community/published", "/account", "/login", "/register", "/forgot-password"])(
    "preserves the Community route %s",
    (path) => expect(isCommunitySitePath(path)).toBe(true),
  );

  it("opens the Community catalog from the homepage without rewriting its URL", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "not_found" }), { status: 404, headers: { "Content-Type": "application/json" } })));
    render(<CommunitySite />);
    await user.click(within(screen.getByRole("navigation", { name: "Primary navigation" })).getByRole("link", { name: "Community" }));
    expect(await screen.findByRole("heading", { name: "Discover" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/community");
    expect(screen.queryByText("Veyra / AI studio")).not.toBeInTheDocument();
    expect(screen.getAllByRole("banner")).toHaveLength(1);
    expect(screen.getAllByRole("navigation", { name: "Primary navigation" })).toHaveLength(1);
    expect(within(screen.getByRole("banner")).getByRole("link", { name: "Community" })).toHaveAttribute("aria-current", "location");
    const sidebar = screen.getByRole("navigation", { name: "Community pages" });
    expect(within(sidebar).getAllByRole("link").map((link) => link.textContent)).toEqual(["Discover", "Published", "Starred", "Mine"]);
    for (const [name, href] of [["Discover", "#/community"], ["Published", "#/community/published"], ["Starred", "#/community/starred"], ["Mine", "#/community/mine"]]) {
      expect(within(sidebar).getByRole("link", { name })).toHaveAttribute("href", href);
    }
    await user.click(within(sidebar).getByRole("link", { name: "Published" }));
    expect(await screen.findByRole("heading", { name: "Published" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/community/published");
    expect(screen.getAllByRole("banner")).toHaveLength(1);
  });
});
