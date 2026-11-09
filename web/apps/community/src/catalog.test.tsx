import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CommunityPluginEntry, CommunityRegistryEntry } from "@veyra/api-contracts";
import { CommunitySite } from "./site";

type ObservedRequest = { path: string; method: string; csrf: string | null };
const account = { id: "account-alice", email: "alice@example.com", handle: "alice", display_name: "Alice Chen", avatar_url: null };
function agent(overrides: Partial<CommunityRegistryEntry> = {}): CommunityRegistryEntry {
  return { schema_version: "community.registry.v1", owner_handle: "ada", owner_display_name: "Ada Lin", owner_avatar_url: null, slug: "gift-designer", name: "Gift Designer", description: "Gift packaging directions and visuals.", version: "1.0.0", source_hash: "a".repeat(64), behavior_hash: "b".repeat(64), lock_hash: "c".repeat(64), status: "published", created_at: "2026-11-01T08:00:00Z", published_at: "2026-11-01T08:00:00Z", fork_of: null, capabilities: null, scan: null, star_count: 3, review_count: 0, average_rating: 0, ...overrides };
}
const plugin: CommunityPluginEntry = { schema_version: "community.plugin.registry.v1", owner_handle: "ada", owner_display_name: "Ada Lin", owner_avatar_url: null, plugin_id: "brand-notes", slug: "brand-notes", name: "Brand Notes Pack", description: "Reusable brand notes and tools.", version: "1.0.0", package_hash: "d".repeat(64), status: "published", skill_count: 2, mcp_count: 0, skills: [], mcp_servers: [], license: "MIT", created_at: "2026-11-02T08:00:00Z", published_at: "2026-11-02T08:00:00Z" };
function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
function agentList(entries: CommunityRegistryEntry[]) {
  return json({ schema_version: "community.registry.v1", entries });
}
function installApi(options: { signedIn?: boolean; publicAgents?: CommunityRegistryEntry[]; plugins?: CommunityPluginEntry[]; mine?: CommunityRegistryEntry[]; starred?: CommunityRegistryEntry[]; respond?: (path: string, method: string) => Response | Promise<Response> | undefined } = {}) {
  const requests: ObservedRequest[] = [];
  if (options.signedIn) document.cookie = "veyra-csrf=test-csrf; path=/";
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://localhost");
    const path = url.pathname;
    const method = (init?.method ?? "GET").toUpperCase();
    requests.push({ path: path + url.search, method, csrf: new Headers(init?.headers).get("X-CSRF-Token") });
    const override = options.respond?.(path, method);
    if (override) return override;
    if (path === "/api/v1/account/me") return options.signedIn ? json({ schema_version: "community.account.v1", account }) : json({ detail: "authentication_required" }, 401);
    if (path === "/api/v1/registry/agents") return agentList(options.publicAgents ?? []);
    if (path === "/api/v1/registry/mine/plugins") return json({ schema_version: "community.plugin.registry.v1", entries: (options.plugins ?? []).filter((entry) => entry.owner_handle === account.handle) });
    if (path === "/api/v1/registry/plugins") return json({ schema_version: "community.plugin.registry.v1", entries: options.plugins ?? [] });
    if (path === "/api/v1/registry/mine/agents") return agentList(options.mine ?? []);
    if (path === "/api/v1/registry/starred") return agentList(options.starred ?? []);
    return json({ detail: "not_found" }, 404);
  }));
  return requests;
}
function route(hash: string) {
  const oldURL = window.location.href;
  const url = new URL(oldURL);
  url.hash = hash;
  window.history.replaceState(window.history.state, "", url);
  fireEvent(window, new HashChangeEvent("hashchange", { oldURL, newURL: url.href }));
}
function sidebar() { return screen.getByRole("navigation", { name: "Community pages" }); }

beforeEach(() => {
  localStorage.clear();
  document.cookie = "veyra-csrf=; Max-Age=0; path=/";
  document.cookie = "__Host-veyra-csrf=; Max-Age=0; path=/";
  window.history.replaceState(null, "", "/?lang=en#/community");
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.cookie = "veyra-csrf=; Max-Age=0; path=/";
  window.history.replaceState(null, "", "/#home");
});

describe("Community catalog access and interactions", () => {
  it.each(["published", "starred", "mine"])("keeps anonymous %s pages behind sign-in without querying private lists", async (section) => {
    window.history.replaceState(null, "", `/?lang=en#/community/${section}`);
    const requests = installApi();
    render(<CommunitySite />);
    expect(await screen.findByText("Sign in to see your Community content")).toBeInTheDocument();
    expect(within(sidebar()).getByRole("link", { current: "page" })).toHaveAttribute("href", `#/community/${section}`);
    expect(screen.getAllByRole("banner")).toHaveLength(1);
    expect(requests).toEqual([]);
  });

  it("loads signed-in published and starred collections from their own endpoints", async () => {
    window.history.replaceState(null, "", "/?lang=en#/community/published");
    const own = agent({ name: "My Release", owner_handle: "alice", owner_display_name: "Alice Chen", slug: "my-release" });
    const saved = agent({ name: "Saved Release", slug: "saved-release" });
    const requests = installApi({ signedIn: true, publicAgents: [agent({ name: "Public Only" })], mine: [own], starred: [saved] });
    const user = userEvent.setup();
    render(<CommunitySite />);
    expect(await screen.findByRole("heading", { name: "My Release" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Public Only" })).not.toBeInTheDocument();
    expect(requests.some(({ path }) => path.startsWith("/api/v1/registry/mine/agents?"))).toBe(true);
    expect(requests.some(({ path }) => path === "/api/v1/registry/agents")).toBe(false);
    await user.click(within(sidebar()).getByRole("link", { name: "Starred" }));
    expect(await screen.findByRole("heading", { name: "Saved Release" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "My Release" })).not.toBeInTheDocument();
    expect(requests.some(({ path }) => path.startsWith("/api/v1/registry/starred?"))).toBe(true);
    await user.click(within(sidebar()).getByRole("link", { name: "Mine" }));
    expect(await screen.findByRole("heading", { name: "Alice Chen" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "My Release" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Profile and security" })).toHaveAttribute("href", "#/community/mine/settings");
  });

  it("keeps owned Plugin versions in Published and Mine, including moderation states after refresh", async () => {
    window.history.replaceState(null, "", "/?lang=en#/community/published");
    const ownedPack: CommunityPluginEntry = { ...plugin, owner_handle: "alice", status: "quarantined", published_at: null };
    const requests = installApi({ signedIn: true, plugins: [ownedPack] });
    const user = userEvent.setup();
    let view = render(<CommunitySite />);
    expect(await screen.findByRole("heading", { name: "Brand Notes Pack" })).toBeInTheDocument();
    expect(screen.getByText("In review")).toBeInTheDocument();
    expect(requests.some(({ path }) => path.startsWith("/api/v1/registry/mine/plugins?"))).toBe(true);
    await user.click(within(sidebar()).getByRole("link", { name: "Mine" }));
    expect(await screen.findByText("Brand Notes Pack")).toBeInTheDocument();
    const stats = screen.getByRole("region", { name: "Release statistics" });
    expect(within(stats).getByText("In review").closest("div")).toHaveTextContent("1In review");
    view.unmount();
    view = render(<CommunitySite />);
    expect(await screen.findByText("Brand Notes Pack")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Release statistics" })).getByText("In review").closest("div")).toHaveTextContent("1In review");
  });

  it("searches author names, filters real resource categories, and remembers the chosen view", async () => {
    const review = agent({ name: "Review Helper", slug: "review-helper", owner_handle: "beatrice", owner_display_name: "Beatrice Wu" });
    installApi({ publicAgents: [agent(), review], plugins: [plugin] });
    const user = userEvent.setup();
    const view = render(<CommunitySite />);
    expect(await screen.findByRole("heading", { name: "Brand Notes Pack" })).toBeInTheDocument();
    await user.type(screen.getByRole("searchbox", { name: "Search names or authors" }), "bEaTrIcE");
    expect(screen.getByRole("heading", { name: "Review Helper" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Gift Designer" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Brand Notes Pack" })).not.toBeInTheDocument();
    await user.clear(screen.getByRole("searchbox", { name: "Search names or authors" }));
    await user.click(screen.getByRole("button", { name: /^Plugin Pack / }));
    expect(screen.getByRole("heading", { name: "Brand Notes Pack" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Review Helper" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Workflow / }));
    expect(screen.getByText("No matching resources")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^All / }));
    await user.click(screen.getByRole("button", { name: "List view" }));
    expect(screen.getByRole("button", { name: "List view" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Grid view" })).toHaveAttribute("aria-pressed", "false");
    view.unmount();
    render(<CommunitySite />);
    expect(await screen.findByRole("heading", { name: "Gift Designer" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "List view" })).toHaveAttribute("aria-pressed", "true");
  });

  it("retains a saved release on Unstar failure, then removes it after confirmed server feedback", async () => {
    window.history.replaceState(null, "", "/?lang=en#/community/starred");
    let attempts = 0;
    const requests = installApi({ signedIn: true, starred: [agent()], respond: (path, method) => {
      if (!path.endsWith("/star") || method !== "DELETE") return undefined;
      attempts += 1;
      return attempts === 1 ? json({ detail: "unstar_temporarily_unavailable" }, 503) : json({ schema_version: "community.feedback.v1", starred: false, star_count: 2, review_count: 0, average_rating: 0 });
    } });
    const user = userEvent.setup();
    render(<CommunitySite />);
    await user.click(await screen.findByRole("button", { name: "Unstar Gift Designer" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("unstar_temporarily_unavailable");
    expect(screen.getByRole("heading", { name: "Gift Designer" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Unstar Gift Designer" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Unstar Gift Designer" }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Gift Designer" })).not.toBeInTheDocument());
    expect(screen.getByText("No matching resources")).toBeInTheDocument();
    const changes = requests.filter(({ method }) => method === "DELETE");
    expect(changes).toHaveLength(2);
    expect(changes.every(({ path, csrf }) => path === "/api/v1/registry/agents/ada/gift-designer/versions/1.0.0/star" && csrf === "test-csrf")).toBe(true);
  });

  it("does not replace a newer collection when the previous route finishes loading late", async () => {
    let resolveDiscover!: (response: Response) => void;
    const discover = new Promise<Response>((resolve) => { resolveDiscover = resolve; });
    const requests = installApi({ signedIn: true, mine: [agent({ name: "Own Current Release" })], respond: (path) => path === "/api/v1/registry/agents" ? discover : undefined });
    const user = userEvent.setup();
    render(<CommunitySite />);
    await waitFor(() => expect(requests.some(({ path }) => path === "/api/v1/registry/agents")).toBe(true));
    await user.click(within(sidebar()).getByRole("link", { name: "Published" }));
    expect(await screen.findByRole("heading", { name: "Own Current Release" })).toBeInTheDocument();
    await act(async () => { resolveDiscover(agentList([agent({ name: "Late Public Release" })])); });
    expect(screen.getByRole("heading", { name: "Own Current Release" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Late Public Release" })).not.toBeInTheDocument();
    expect(window.location.hash).toBe("#/community/published");
  });

  it("isolates late detail responses when navigating between two resource routes", async () => {
    window.history.replaceState(null, "", "/?lang=en#/community/ada/old-design");
    const old = agent({ name: "Old Design", slug: "old-design" });
    const current = agent({ name: "Current Design", slug: "current-design" });
    let resolveOld!: (response: Response) => void;
    const pendingOld = new Promise<Response>((resolve) => { resolveOld = resolve; });
    const requests = installApi({ respond: (path) => {
      if (path === "/api/v1/registry/agents/ada/old-design") return pendingOld;
      if (path === "/api/v1/registry/agents/ada/current-design") return json(current);
      if (path.endsWith("/old-design/versions")) return json({ schema_version: "community.registry.v1", versions: [old] });
      if (path.endsWith("/current-design/versions")) return json({ schema_version: "community.registry.v1", versions: [current] });
      return undefined;
    } });
    render(<CommunitySite />);
    await waitFor(() => expect(requests.some(({ path }) => path === "/api/v1/registry/agents/ada/old-design")).toBe(true));
    route("#/community/ada/current-design");
    expect(await screen.findByRole("heading", { name: "Current Design" })).toBeInTheDocument();
    await act(async () => { resolveOld(json(old)); });
    expect(screen.getByRole("heading", { name: "Current Design" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Old Design" })).not.toBeInTheDocument();
    expect(window.location.hash).toBe("#/community/ada/current-design");
  });
});
