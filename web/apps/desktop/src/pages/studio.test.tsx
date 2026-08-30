import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentSource, DraftResponse, ProjectSummaryResponse, ResourceDescriptor } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { LocalApiClientError, type LocalProjectApi } from "../api/local-client";
import { ProjectWorkspaceProvider } from "../api/project-workspace";
import { StudioPage } from "./studio";

class TestResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver = TestResizeObserver;
afterEach(cleanup);

const source: AgentSource = {
  schema_version: "1.0", agentspec_version: "26.1", component_type: "Flow", agent_id: "agent-1", slug: "review", name: "Review", description: "",
  inputs: {}, outputs: { result: "string" }, nodes: [{ id: "start", component_type: "Start" }, { id: "out", component_type: "Output", output_name: "result" }], transitions: [{ from: "start", port: "next", to: "out" }],
  extensions: { veyra: { runtime_profile: "guarded", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } },
  ui: { positions: { start: { x: 0, y: 0 }, out: { x: 100, y: 0 } } }, lock: {},
};

const project: ProjectSummaryResponse = { schema_version: "1.0", project_id: "project-1", root_path: "/tmp/project", name: "Project", description: "", pinned: false, pinned_at: null, indexed_at: "2026-08-28T00:00:00Z", manifest_hash: "hash", default_agent_id: null, agent_count: 0, agents: [] };
const draft = (overrides: Partial<DraftResponse> = {}): DraftResponse => ({ schema_version: "1.0", draft_id: "draft-1", revision: 1, etag: '"etag-1"', source_file_hash: "file", source, ...overrides });

function renderPage(api: LocalProjectApi, locale: "en" | "zh" = "en") {
  window.localStorage.setItem("veyra.language", locale);
  return render(<ThemeProvider storageKey="studio-test-theme"><ProjectWorkspaceProvider api={api}><StudioPage projectId="project-1" agentId="agent-1" /></ProjectWorkspaceProvider></ThemeProvider>);
}

describe("StudioPage source and conflict safety", () => {
  it("keeps structurally incomplete JSON in the Source text buffer without crashing the graph", async () => {
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }), getDraft: vi.fn().mockResolvedValue(draft()) } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    renderPage(api);
    await user.click(await screen.findByRole("tab", { name: "Source" }));
    const editor = screen.getByRole("textbox", { name: "Agent source" });
    await user.clear(editor);
    fireEvent.change(editor, { target: { value: '{"schema_version":"1.0"}' } });
    expect(await screen.findByText(/Source cannot be applied/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save draft" })).toBeDisabled();
    expect(editor).toHaveValue('{"schema_version":"1.0"}');
  });

  it("uses reloadDraft, not getDraft, to explicitly load a disk version after a draft conflict", async () => {
    const conflict = new LocalApiClientError("External edit", { status: 409, code: "draft_conflict" });
    const getDraft = vi.fn().mockRejectedValue(conflict);
    const reloadDraft = vi.fn().mockResolvedValue(draft({ revision: 2, etag: '"etag-2"', source: { ...source, name: "Disk review" } }));
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }), getDraft, reloadDraft } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    renderPage(api);
    await user.click(await screen.findByRole("button", { name: "Load disk version" }));
    await waitFor(() => expect(reloadDraft).toHaveBeenCalledWith("project-1", "agent-1"));
    expect(getDraft).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("tab", { name: "Form" }));
    expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue("Disk review");
  });

  it("offers disk reload after a save conflict and keeps ordinary initial loading separate", async () => {
    const conflict = new LocalApiClientError("External edit", { status: 409, code: "draft_conflict" });
    const saveDraft = vi.fn().mockRejectedValue(conflict);
    const reloadDraft = vi.fn().mockResolvedValue(draft({ revision: 2, etag: '"etag-2"' }));
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }), getDraft: vi.fn().mockResolvedValue(draft()), saveDraft, reloadDraft } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    renderPage(api);
    await screen.findByRole("tab", { name: "Canvas" });
    expect(screen.queryByText("Agent definition")).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Form" }));
    await user.clear(screen.getByRole("textbox", { name: "Name" }));
    await user.type(screen.getByRole("textbox", { name: "Name" }), "Changed");
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    await user.click(await screen.findByRole("button", { name: "Load disk version" }));
    await waitFor(() => expect(reloadDraft).toHaveBeenCalledWith("project-1", "agent-1"));
  });

  it("renders stable graph diagnostic codes as localized Studio copy", async () => {
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }), getDraft: vi.fn().mockResolvedValue(draft({ source: { ...source, nodes: [{ id: "out", component_type: "Output", output_name: "result" }], transitions: [] } })) } as unknown as LocalProjectApi;
    renderPage(api, "zh");
    expect(await screen.findByText("必须且只能有一个 Start 节点。")).toBeInTheDocument();
  });

  it("loads Catalog tools into the palette and attaches Read File uses, lock, and permissions", async () => {
    const read: ResourceDescriptor = {
      schema_version: "1.0",
      resource_id: "veyra.tool.filesystem.read",
      kind: "tool",
      version: "1.0.0",
      reference: "veyra.tool.filesystem.read@1.0.0",
      name: "Filesystem Read",
      description: "Read a bounded Project path.",
      origin: "builtin",
      content_hash: "d".repeat(64),
      availability: "ready",
      factory_selectable: true,
      runtime_status: "supported",
      required_permissions: { network_hosts: [], tools: ["veyra.tool.filesystem.read"], filesystem_read_roots: ["project"], filesystem_write_roots: [], shell_workspace_only: false },
      tags: ["filesystem"],
      spec: { ui: { category: "filesystem", icon: "file-text", title: "Read File" }, approval_required: false },
    };
    const github: ResourceDescriptor = {
      ...read,
      resource_id: "veyra.tool.github.read",
      reference: "veyra.tool.github.read@1.0.0",
      name: "GitHub Read",
      availability: "unavailable",
      factory_selectable: false,
      runtime_status: "runtime_not_supported",
      required_permissions: { network_hosts: ["api.github.com"], tools: ["veyra.tool.github.read"], filesystem_read_roots: [], filesystem_write_roots: [], shell_workspace_only: false },
      spec: { ui: { category: "git", icon: "github", title: "GitHub Read" } },
    };
    const start: ResourceDescriptor = {
      ...read,
      resource_id: "veyra.component.start",
      kind: "component",
      reference: "veyra.component.start@1.0.0",
      name: "Start",
      required_permissions: { network_hosts: [], tools: [], filesystem_read_roots: [], filesystem_write_roots: [], shell_workspace_only: false },
      spec: { fields: [], output_ports: ["next"], ui: { category: "core", icon: "circle-play", title: "Start" } },
    };
    const listResources = vi.fn(async ({ kind }: { kind?: string } = {}) => ({
      schema_version: "1.0",
      resources: kind === "tool" ? [read, github] : kind === "component" ? [start] : [start, read, github],
      kinds: [],
    }));
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [project] }), getDraft: vi.fn().mockResolvedValue(draft()), listResources } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    renderPage(api);
    expect(await screen.findByRole("button", { name: /Read File/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /GitHub Read/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /Read File/ }));
    expect((await screen.findAllByDisplayValue("veyra.tool.filesystem.read@1.0.0")).length).toBeGreaterThan(1);
    expect(screen.getByDisplayValue("veyra.tool.filesystem.read")).toBeInTheDocument();
  });
});
