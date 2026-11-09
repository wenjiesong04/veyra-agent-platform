import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CommunitySite } from "./site";
import { preparePublicationFile } from "./pages/publication-file";

const account = { id: "alice-id", handle: "alice", display_name: "Alice", email: "alice@example.com", avatar_url: null };
const entry = { schema_version: "community.registry.v1", owner_handle: "alice", owner_display_name: "Alice", slug: "gift-designer", name: "Gift Designer", description: "Packaging", version: "1.0.0", source_hash: "a".repeat(64), behavior_hash: "b".repeat(64), lock_hash: "c".repeat(64), status: "published", created_at: "2026-11-06T00:00:00Z", published_at: "2026-11-06T00:00:00Z", fork_of: null, capabilities: null, scan: null, star_count: 0, average_rating: 0, review_count: 0 };
const source = "component_type: Flow\nname: Gift Designer\nslug: gift-designer\nversion: 1.0.0\n";
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
function installApi(onPublish?: (path: string, form: FormData) => Response, onGet?: (path: string) => Response | Promise<Response> | undefined) {
  const posts: { path: string; body: FormData; csrf: string | null }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://localhost").pathname;
    if (init?.method === "POST") {
      posts.push({ path, body: init.body as FormData, csrf: new Headers(init.headers).get("X-CSRF-Token") });
      return onPublish?.(path, init.body as FormData) ?? json(entry, 201);
    }
    const override = onGet?.(path);
    if (override) return override;
    if (path.endsWith("/account/me")) return json({ account });
    if (path.endsWith("/registry/mine/agents") || path.endsWith("/registry/plugins") || path.endsWith("/registry/mine/plugins") || path.endsWith("/registry/starred")) return json({ entries: [] });
    return json({ detail: "not_found" }, 404);
  }));
  return posts;
}
function readText(file: File): Promise<string> {
  return new Promise((resolve) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.readAsText(file); });
}

beforeEach(() => {
  localStorage.clear();
  document.cookie = "veyra-csrf=publish-test; path=/";
  history.replaceState(null, "", "/?lang=en#/community/mine");
});
afterEach(() => {
  cleanup(); vi.unstubAllGlobals();
  document.cookie = "veyra-csrf=; Max-Age=0; path=/";
  history.replaceState(null, "", "/#home");
});

describe("Web creator workspace", () => {
  it("unifies the legacy account URL with Mine and puts the account entry in the shared header", async () => {
    history.replaceState(null, "", "/?lang=en#/account");
    installApi();
    render(<CommunitySite />);
    expect(await screen.findByRole("heading", { name: "Choose what to publish" })).toBeInTheDocument();
    const header = screen.getByRole("banner");
    expect(within(header).getByRole("link", { name: "Mine · Alice, signed in" })).toHaveAttribute("href", "#/community/mine");
    expect(within(screen.getByRole("navigation", { name: "Community pages" })).getAllByRole("link")).toHaveLength(4);
    expect(screen.queryByRole("link", { name: "Manage Community account" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Profile and security" })).toHaveAttribute("href", "#/community/mine/settings");
  });

  it("keeps file selection local and uploads the reviewed bytes only after confirmation", async () => {
    const posts = installApi(); const user = userEvent.setup();
    render(<CommunitySite />);
    await screen.findByRole("heading", { name: "Choose what to publish" });
    const file = new File([source], "gift.vagent.yaml", { type: "application/yaml" });
    await user.upload(screen.getByLabelText("Choose an export"), file);
    expect(await screen.findByText("gift.vagent.yaml")).toBeInTheDocument();
    expect(posts).toHaveLength(0);
    const publish = screen.getByRole("button", { name: "Upload and publish" });
    expect(publish).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: /I have reviewed/ }));
    await user.click(publish);
    await screen.findByText(/Gift Designer · v1.0.0 — Published/);
    expect(posts).toHaveLength(1);
    expect(posts[0]?.path).toBe("/api/v1/registry/agents");
    expect(posts[0]?.csrf).toBe("publish-test");
    expect(posts[0]?.body.get("expected_publisher_id")).toBe(account.id);
    const uploaded = posts[0]!.body.get("package") as File;
    expect(uploaded.name).toBe(file.name);
    expect(await readText(uploaded)).toBe(source);
    expect(await screen.findByRole("link", { name: "Gift Designer" })).toBeInTheDocument();
  });

  it("clears consent when the chosen file changes and retains the preview after a server rejection", async () => {
    const posts = installApi(() => json({ detail: "registry_version_exists" }, 409)); const user = userEvent.setup();
    render(<CommunitySite />);
    await screen.findByRole("heading", { name: "Choose what to publish" });
    await user.upload(screen.getByLabelText("Choose an export"), new File([source], "first.vagent.yaml"));
    await screen.findByText("first.vagent.yaml");
    await user.click(screen.getByRole("checkbox", { name: /I have reviewed/ }));
    fireEvent.change(screen.getByLabelText("Choose an export"), { target: { files: [new File([source + "description: Revised\n"], "second.vagent.yaml")] } });
    await screen.findByText("second.vagent.yaml");
    expect(screen.getByRole("button", { name: "Upload and publish" })).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: /I have reviewed/ }));
    await user.click(screen.getByRole("button", { name: "Upload and publish" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("registry_version_exists");
    expect(posts).toHaveLength(1);
    expect((posts[0]!.body.get("package") as File).name).toBe("second.vagent.yaml");
    expect(screen.getByText("second.vagent.yaml")).toBeInTheDocument();
  });

  it("keeps the confirmed publication when an older release-list response arrives late", async () => {
    let resolveList!: (response: Response) => void;
    const pending = new Promise<Response>((resolve) => { resolveList = resolve; });
    installApi(undefined, (path) => path.endsWith("/registry/mine/agents") ? pending : undefined);
    const user = userEvent.setup(); render(<CommunitySite />);
    await screen.findByRole("heading", { name: "Choose what to publish" });
    await user.upload(screen.getByLabelText("Choose an export"), new File([source], "gift.vagent.yaml"));
    await screen.findByText("gift.vagent.yaml");
    await user.click(screen.getByRole("checkbox", { name: /I have reviewed/ }));
    await user.click(screen.getByRole("button", { name: "Upload and publish" }));
    await screen.findByText(/Gift Designer · v1.0.0 — Published/);
    await act(async () => { resolveList(json({ entries: [] })); });
    expect(screen.getByRole("link", { name: "Gift Designer" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Release statistics" })).toHaveTextContent("1Published versions");
  });

  it("discards the old confirmation when the server detects a changed publisher account", async () => {
    let changed = false;
    const posts = installApi(() => { changed = true; return json({ detail: "publication_account_changed" }, 409); }, (path) => changed && path.endsWith("/account/me") ? json({ account: { ...account, id: "bob-id", handle: "bob", display_name: "Bob" } }) : undefined);
    const user = userEvent.setup(); render(<CommunitySite />);
    await screen.findByRole("heading", { name: "Choose what to publish" });
    await user.upload(screen.getByLabelText("Choose an export"), new File([source], "gift.vagent.yaml"));
    await screen.findByText("gift.vagent.yaml");
    await user.click(screen.getByRole("checkbox", { name: /I have reviewed/ }));
    await user.click(screen.getByRole("button", { name: "Upload and publish" }));
    expect(await screen.findByRole("heading", { name: "Bob" })).toBeInTheDocument();
    expect(screen.queryByText("gift.vagent.yaml")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /I have reviewed/ })).not.toBeInTheDocument();
    expect(posts).toHaveLength(1);
    expect(posts[0]?.body.get("expected_publisher_id")).toBe(account.id);
  });

  it("uses the Plugin API and respects the moderation receipt", async () => {
    const posts = installApi(() => json({ schema_version: "community.plugin.registry.v1", owner_handle: "alice", slug: "notes", version: "1.0.0", description: "Notes", package_hash: "d".repeat(64), plugin_id: "notes", name: "Notes Pack", status: "quarantined", created_at: entry.created_at, published_at: null, skill_count: 1, mcp_count: 0, skills: [], mcp_servers: [] }, 201));
    const user = userEvent.setup(); render(<CommunitySite />);
    await screen.findByRole("heading", { name: "Choose what to publish" });
    await user.click(screen.getByRole("button", { name: /^Plugin Pack/ }));
    await user.upload(screen.getByLabelText("Choose an export"), new File(["PK fixture"], "notes.vplugin.zip", { type: "application/zip" }));
    await screen.findByText("notes.vplugin.zip");
    await user.click(screen.getByRole("checkbox", { name: /I have reviewed/ }));
    await user.click(screen.getByRole("button", { name: "Upload and publish" }));
    expect(await screen.findByText(/Notes Pack · v1.0.0 — Submitted for review/)).toBeInTheDocument();
    expect(posts[0]?.path).toBe("/api/v1/registry/plugins");
    expect(screen.getByRole("button", { name: /^Workflow/ })).toBeDisabled();
  });
});

describe("Publication file checks", () => {
  it("rejects unsupported formats, oversized exports, Workflow sources, and credential markers locally", async () => {
    await expect(preparePublicationFile(new File(["a"], "secret.env"), "agent")).rejects.toThrow("file_type_invalid");
    await expect(preparePublicationFile(new File([new Uint8Array(1_000_001)], "large.vagent.yaml"), "agent")).rejects.toThrow("file_too_large");
    await expect(preparePublicationFile(new File([source], "flow.vworkflow.yaml"), "agent")).rejects.toThrow("workflow_not_supported");
    await expect(preparePublicationFile(new File(["-----BEGIN PRIVATE KEY-----"], "secret.vagent.yaml"), "agent")).rejects.toThrow("credential_marker");
    await expect(preparePublicationFile(new File(["x"], "notes.zip"), "plugin")).rejects.toThrow("file_type_invalid");
  });
});
