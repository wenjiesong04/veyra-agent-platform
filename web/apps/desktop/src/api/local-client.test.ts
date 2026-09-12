import { describe, expect, it, vi } from "vitest";
import type { ProjectSummaryResponse, ResourceDescriptor } from "@veyra/api-contracts";
import { LocalApiClient } from "./local-client";

function summary(overrides: Partial<ProjectSummaryResponse> = {}) {
  return {
    schema_version: "1.0",
    project_id: "project-1",
    root_path: "/tmp/project-1",
    name: "Project One",
    description: "",
    pinned: false,
    pinned_at: null,
    indexed_at: "2026-08-28T00:00:00Z",
    manifest_hash: "manifest-hash",
    default_agent_id: null,
    agent_count: 0,
    agents: [],
    ...overrides,
  } satisfies ProjectSummaryResponse;
}

function response(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("LocalApiClient Project requests", () => {
  it("lists and validates real Project summaries", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({ schema_version: "1.0", projects: [summary({ agents: [{ agent_id: "agent-1", slug: "reviewer", name: "Reviewer", description: "", pinned: false, source_path: "agents/reviewer/agent.vagent.yaml", source_file_hash: "file-hash" }], agent_count: 1 })] }));
    const client = new LocalApiClient({ fetcher });

    await expect(client.listProjects()).resolves.toEqual({ schema_version: "1.0", projects: [summary({ agents: [{ agent_id: "agent-1", slug: "reviewer", name: "Reviewer", description: "", pinned: false, source_path: "agents/reviewer/agent.vagent.yaml", source_file_hash: "file-hash" }], agent_count: 1 })] });
    expect(fetcher).toHaveBeenCalledWith("/api/v1/projects", expect.objectContaining({ method: "GET", credentials: "include" }));
  });

  it("sends a create name and description while opening continues to send an existing root path", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response(summary({ project_id: "created", name: "Created" }), 201))
      .mockResolvedValueOnce(response(summary({ project_id: "opened", name: "Opened" })));
    const client = new LocalApiClient({ fetcher });

    await client.createProject({ name: "Created", description: "A created Project" });
    await client.openProject({ root_path: "/tmp/existing" });

    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/projects");
    expect(JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))).toEqual({ name: "Created", description: "A created Project" });
    expect(fetcher.mock.calls[1]?.[0]).toBe("/api/v1/projects/open");
    expect(JSON.parse(String(fetcher.mock.calls[1]?.[1]?.body))).toEqual({ root_path: "/tmp/existing" });
  });

  it("uses the deliberate desktop intent header for the native directory picker", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({ schema_version: "1.0", status: "selected", root_path: "/tmp/selected" }));
    const client = new LocalApiClient({ fetcher });

    await expect(client.selectDirectory()).resolves.toEqual({ schema_version: "1.0", status: "selected", root_path: "/tmp/selected" });
    expect(fetcher).toHaveBeenCalledWith("/api/v1/system/select-directory", expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({ "X-Veyra-Desktop-Intent": "select-directory" }),
    }));
    expect(JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))).toEqual({});
  });

  it("uses a native archive picker and imports from the selected path", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({ schema_version: "1.0", status: "selected", path: "/tmp/team.vproject.zip" }))
      .mockResolvedValueOnce(response(summary({ project_id: "imported", name: "Imported" }), 201));
    const client = new LocalApiClient({ fetcher });

    await expect(client.selectArchive()).resolves.toEqual({ schema_version: "1.0", status: "selected", path: "/tmp/team.vproject.zip" });
    await client.importProjectFromPath({ path: "/tmp/team.vproject.zip" });

    expect(fetcher).toHaveBeenNthCalledWith(1, "/api/v1/system/select-archive", expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({ "X-Veyra-Desktop-Intent": "select-archive" }),
    }));
    expect(fetcher.mock.calls[1]?.[0]).toBe("/api/v1/projects/import-path");
    expect(JSON.parse(String(fetcher.mock.calls[1]?.[1]?.body))).toEqual({ path: "/tmp/team.vproject.zip" });
  });

  it("parses the Project Resource Library contract and mutates bindings", async () => {
    const descriptor = {
      schema_version: "1.0",
      resource_id: "veyra.filesystem.read",
      kind: "tool",
      version: "1.0.0",
      reference: "veyra.filesystem.read@1.0.0",
      name: "Filesystem Read",
      description: "Read a bounded Project path.",
      origin: "builtin",
      content_hash: "a".repeat(64),
      availability: "ready",
      factory_selectable: true,
      runtime_status: "supported",
      required_permissions: { network_hosts: [], tools: [], filesystem_read_roots: ["$PROJECT"], filesystem_write_roots: [], shell_workspace_only: false },
      tags: ["filesystem"],
      spec: {},
      scope: "project",
      binding_source: "manual",
      bound_content_hash: "a".repeat(64),
      used_by: [],
    };
    const payload = { schema_version: "1.0", project_id: "project-1", resources: [descriptor], missing_references: [], project_count: 1, used_count: 0, unbound_count: 0, builtin_count: 9 };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response(payload))
      .mockResolvedValueOnce(response(payload, 201))
      .mockResolvedValueOnce(response(payload));
    const client = new LocalApiClient({ fetcher });

    await expect(client.listProjectResources("project-1")).resolves.toMatchObject({ project_count: 1, resources: [{ reference: descriptor.reference, scope: "project" }] });
    await client.addProjectResource("project-1", { reference: descriptor.reference });
    await client.removeProjectResource("project-1", "veyra.filesystem.read", "1.0.0");
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/projects/project-1/resources");
    expect(fetcher.mock.calls[1]?.[0]).toBe("/api/v1/projects/project-1/resources");
    expect(fetcher.mock.calls[2]?.[0]).toBe("/api/v1/projects/project-1/resources/veyra.filesystem.read/versions/1.0.0");
  });

  it("reveals an indexed Project folder through the desktop intent header", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({ schema_version: "1.0", status: "revealed", root_path: "/tmp/Inside" }));
    const client = new LocalApiClient({ fetcher });

    await expect(client.revealProject("project-1")).resolves.toEqual({
      schema_version: "1.0",
      status: "revealed",
      root_path: "/tmp/Inside",
    });
    expect(fetcher).toHaveBeenCalledWith("/api/v1/system/reveal-project", expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({ "X-Veyra-Desktop-Intent": "reveal-project" }),
    }));
    expect(JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))).toEqual({ project_id: "project-1" });
  });

  it("uses JSON create/template bodies and multipart file import without local Agent parsing", async () => {
    const created = { schema_version: "1.0", project_id: "project-1", agent_id: "agent-1", slug: "reviewer", name: "Reviewer", description: "Reviews", source_path: "agents/reviewer/agent.vagent.yaml", source_file_hash: "file-hash" };
    const fetcher = vi.fn().mockResolvedValueOnce(response(created, 201)).mockResolvedValueOnce(response(created, 201));
    const client = new LocalApiClient({ fetcher });
    const file = new File(["schema_version: '1.0'"], "reviewer.vagent.yaml", { type: "application/x-yaml" });

    await client.createAgent("project-1", { mode: "template", template_id: "review", name: "Review override" });
    await client.importAgent("project-1", { file, description: "Imported" });

    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/projects/project-1/agents");
    expect(JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))).toEqual({ mode: "template", template_id: "review", name: "Review override" });
    expect(fetcher.mock.calls[1]?.[0]).toBe("/api/v1/projects/project-1/agents/import");
    expect(fetcher.mock.calls[1]?.[1]?.body).toBeInstanceOf(FormData);
    const body = fetcher.mock.calls[1]?.[1]?.body as FormData;
    expect(body.get("file")).toBe(file);
    expect(body.get("description")).toBe("Imported");
  });

  it("analyzes and applies an external Agent through the typed import contract", async () => {
    const created = { schema_version: "1.0", project_id: "project-1", agent_id: "agent-1", slug: "research-helper", name: "Research Helper", description: "Imported", source_path: "agents/research-helper/agent.vagent.yaml", source_file_hash: "file-hash" };
    const source = { schema_version: "1.0", agentspec_version: "26.1", component_type: "Flow", agent_id: "generated-agent", slug: "research-helper", name: "Research Helper", description: "Imported", inputs: { request: "string" }, outputs: { result: "string" }, nodes: [], transitions: [], extensions: { veyra: { runtime_profile: "veyra-runtime-profile/1", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } }, ui: { positions: {} }, lock: { "veyra.runtime.profile@1.0.0": "0".repeat(64) } };
    const capability = { kind: "instructions", original: "instructions", status: "supported", reason: "Mapped to the model prompt", included: true };
    const warning = { code: "workflow_requires_review", message: "External workflow was preserved for review" };
    const base = {
      schema_version: "agent.import.v1",
      import_id: "01900000-0000-7000-8000-000000000001",
      state: "analyzed",
      source_kind: "yaml",
      source_name: "agent.yaml",
      source_path: "agent.yaml",
      detected_format: "generic_yaml",
      compatibility: 0.75,
      preview: { name: "Research Helper", description: "Imported", instructions: "Summarize.", model: { model_id: "gpt-5" }, inputs: { request: "string" }, outputs: { result: "string" }, tools: [], skills: [], knowledge_files: [], workflow_present: true },
      ir: { schema_version: "agent.import.ir.v1", detected_format: "generic_yaml", source_path: "agent.yaml", name: "Research Helper", description: "Imported", instructions: "Summarize.", model: { model_id: "gpt-5" }, inputs: { request: "string" }, outputs: { result: "string" }, tools: [], skills: [], knowledge_files: [], workflow_present: true },
      capabilities: [capability],
      warnings: [warning],
      compatibility_report: { schema_version: "agent.import.compatibility.v1", score: 0.75, capabilities: [capability], warnings: [warning] },
      generated_source: source,
      manifest: { schema_version: "agent.import.manifest.v1", import_id: "01900000-0000-7000-8000-000000000001", source_kind: "yaml", source_name: "agent.yaml", source_path: "agent.yaml", source_files: ["agent.yaml"], compatibility: 0.75 },
    };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response(base, 201))
      .mockResolvedValueOnce(response({ schema_version: "agent.import.v1", import: { ...base, state: "applied", applied_agent: created }, agent: created }, 200));
    const client = new LocalApiClient({ fetcher });
    const file = new File(["name: Research Helper"], "agent.yaml", { type: "application/yaml" });

    await expect(client.analyzeAgentImportFile(file)).resolves.toMatchObject({ import_id: base.import_id, compatibility_report: { score: 0.75 } });
    await expect(client.applyAgentImport(base.import_id, { project_id: "project-1", confirm: true })).resolves.toMatchObject({ agent: created });
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/agent-imports/file");
    expect(fetcher.mock.calls[0]?.[1]?.body).toBeInstanceOf(FormData);
    expect(fetcher.mock.calls[1]?.[0]).toBe(`/api/v1/agent-imports/${base.import_id}/apply`);
    expect(JSON.parse(String(fetcher.mock.calls[1]?.[1]?.body))).toEqual({ project_id: "project-1", confirm: true });
  });

  it("downloads a Project zip through the existing export route", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response("PK", { status: 200, headers: { "Content-Type": "application/zip" } }))
      .mockResolvedValueOnce(response(summary({ project_id: "imported", name: "Imported" }), 201));
    const client = new LocalApiClient({ fetcher });
    const file = new File(["PK"], "team.vproject.zip", { type: "application/zip" });

    await expect(client.exportProject("project-1")).resolves.toBeInstanceOf(Blob);
    await client.importProject(file);

    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/projects/project-1/export");
    expect(fetcher.mock.calls[0]?.[1]).toEqual(expect.objectContaining({ method: "GET" }));
    expect(fetcher.mock.calls[1]?.[0]).toBe("/api/v1/projects/import");
    expect(fetcher.mock.calls[1]?.[1]?.body).toBeInstanceOf(FormData);
  });

  it("surfaces typed sidecar errors instead of falling back to fixture data", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({ schema_version: "1.0", code: "project_unavailable", message: "Project root cannot be read", request_id: "request-1" }, 503));
    const client = new LocalApiClient({ fetcher });

    await expect(client.listProjects()).rejects.toMatchObject({
      status: 503,
      code: "project_unavailable",
      requestId: "request-1",
      message: "Project root cannot be read",
    });
  });

  it("maps plain 500 bodies and FastAPI detail errors into readable client errors", async () => {
    const plain = vi.fn().mockResolvedValue(new Response("Internal Server Error", { status: 500, headers: { "Content-Type": "text/plain" } }));
    await expect(new LocalApiClient({ fetcher: plain }).listProjects()).rejects.toMatchObject({
      status: 500,
      code: "local_internal_error",
      message: "The local service failed while handling this request. Restart the desktop sidecar and retry.",
    });

    const fastapi = vi.fn().mockResolvedValue(response({ detail: "Not Found" }, 404));
    await expect(new LocalApiClient({ fetcher: fastapi }).getProject("missing")).rejects.toMatchObject({
      status: 404,
      code: "http_error",
      message: "Not Found",
    });
  });

  it("parses the component registry and starts a durable Agent run", async () => {
    const run = {
      schema_version: "1.0",
      run_id: "run-1",
      project_id: "project-1",
      agent_id: "agent-1",
      version_id: "version-1",
      status: "unverified",
      result: { result: "Hello Ada" },
      error: null,
      created_at: "2026-08-28T10:00:00Z",
      finished_at: "2026-08-28T10:00:01Z",
    };
    const event = {
      schema_version: "1.0",
      event_id: "event-1",
      run_id: "run-1",
      sequence: 1,
      kind: "run.created",
      node_id: null,
      payload: {},
      timestamp: "2026-08-28T10:00:00Z",
    };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({
        schema_version: "1.0",
        components: [{ type: "Transform", fields: ["mapping"], output_ports: ["next"], runtime_status: "supported" }],
      }))
      .mockResolvedValueOnce(response(run))
      .mockResolvedValueOnce(response({ ...run, events: [event] }));
    const client = new LocalApiClient({ fetcher });

    await expect(client.listComponents()).resolves.toMatchObject({
      components: [{ type: "Transform", runtime_status: "supported" }],
    });
    const started = await client.runAgent(
      "project-1",
      "agent-1",
      { inputs: { name: "Ada" } },
      { idempotencyKey: "019c0000-0000-7000-8000-000000000001" },
    );
    await expect(client.getAgentRun("project-1", "agent-1", started.run_id)).resolves.toMatchObject({
      run_id: "run-1",
      events: [{ kind: "run.created" }],
    });

    expect(fetcher.mock.calls[1]?.[0]).toBe("/api/v1/projects/project-1/agents/agent-1/run");
    expect(fetcher.mock.calls[1]?.[1]?.headers).toMatchObject({
      "Idempotency-Key": "019c0000-0000-7000-8000-000000000001",
    });
    expect(JSON.parse(String(fetcher.mock.calls[1]?.[1]?.body))).toEqual({ inputs: { name: "Ada" } });
  });

  it("posts a durable run command with an idempotency key", async () => {
    const run = {
      schema_version: "1.0",
      run_id: "run-1",
      project_id: "project-1",
      agent_id: "agent-1",
      version_id: "version-1",
      status: "unverified",
      result: { written: true },
      error: null,
      created_at: "2026-08-28T10:00:00Z",
      finished_at: "2026-08-28T10:00:02Z",
    };
    const fetcher = vi.fn().mockResolvedValueOnce(response(run));
    const client = new LocalApiClient({ fetcher });

    await expect(client.commandAgentRun(
      "project-1",
      "agent-1",
      "run-1",
      { command: "approve" },
      { idempotencyKey: "019c0000-0000-7000-8000-000000000002" },
    )).resolves.toMatchObject({ run_id: "run-1", status: "unverified" });
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/projects/project-1/agents/agent-1/runs/run-1/commands");
    expect(fetcher.mock.calls[0]?.[1]?.headers).toMatchObject({
      "Idempotency-Key": "019c0000-0000-7000-8000-000000000002",
    });
    expect(JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))).toEqual({ command: "approve" });
  });

  it("opens a replayable run event stream", async () => {
    const event = {
      schema_version: "1.0",
      event_id: "event-1",
      run_id: "run-1",
      sequence: 1,
      kind: "run.created",
      node_id: null,
      payload: {},
      timestamp: "2026-08-28T10:00:00Z",
    };
    const listeners: Record<string, (event: MessageEvent) => void> = {};
    let created: { url: string; closed: boolean } | undefined;
    class FakeEventSource {
      url: string;
      closed = false;
      onerror: ((event: Event) => void) | null = null;
      constructor(url: string) {
        this.url = url;
        created = this;
      }
      addEventListener(type: string, handler: (event: MessageEvent) => void) {
        listeners[type] = handler;
      }
      close() {
        this.closed = true;
      }
    }
    vi.stubGlobal("EventSource", FakeEventSource);
    const client = new LocalApiClient({ fetcher: vi.fn() });
    const onEvent = vi.fn();
    const onDone = vi.fn();
    const stop = client.watchAgentRunEvents("project-1", "agent-1", "run-1", { onEvent, onDone }, { after: 2 });
    expect(created?.url).toBe("/api/v1/projects/project-1/agents/agent-1/runs/run-1/events?after=2");
    expect(listeners.runtime).toBeDefined();
    listeners.runtime({ data: JSON.stringify(event) } as MessageEvent);
    listeners.done({ data: JSON.stringify({ status: "unverified" }) } as MessageEvent);
    expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({ kind: "run.created", sequence: 1 }));
    expect(onDone).toHaveBeenCalledWith("unverified");
    stop();
    vi.unstubAllGlobals();
  });

  it("lists filtered Resource Catalog entries and reads an immutable detail", async () => {
    const resource = {
      schema_version: "1.0",
      resource_id: "veyra.skill.research-brief",
      kind: "skill",
      version: "1.0.0",
      reference: "veyra.skill.research-brief@1.0.0",
      name: "Research Brief",
      description: "Structure a bounded research brief.",
      origin: "builtin",
      content_hash: "a".repeat(64),
      availability: "ready",
      factory_selectable: true,
      runtime_status: "runtime_not_configured",
      required_permissions: { network_hosts: [], tools: [], filesystem_read_roots: [], filesystem_write_roots: [], shell_workspace_only: false },
      tags: ["research", "instruction"],
      spec: { instruction: "State scope and evidence." },
    } satisfies ResourceDescriptor;
    const kinds = ["component", "tool", "mcp_tool", "skill", "policy", "template"].map((kind) => ({ kind, count: kind === "skill" ? 1 : 0 }));
    const fetcher = vi.fn().mockResolvedValueOnce(response({ schema_version: "1.0", resources: [resource], kinds })).mockResolvedValueOnce(response(resource));
    const client = new LocalApiClient({ fetcher });

    await expect(client.listResources({ kind: "skill" })).resolves.toMatchObject({ resources: [resource] });
    await expect(client.getResource(resource.resource_id, resource.version)).resolves.toEqual(resource);
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/resources?kind=skill");
    expect(fetcher.mock.calls[1]?.[0]).toBe("/api/v1/resources/veyra.skill.research-brief/versions/1.0.0");
  });

  it("parses Factory status and apply-draft responses without treating generation as a run", async () => {
    const session = {
      schema_version: "1.0",
      session_id: "session-1",
      project_id: "project-1",
      state: "completed",
      ready: true,
      next_prompt: "Open Studio",
      resource_plan: [{ reference: "veyra.skill.research-brief@1.0.0", kind: "skill", availability: "ready", runtime_status: "runtime_not_configured" }],
      blueprint: { schema_version: "1.0", goal: "Brief" },
      diagnostics: [],
      missing_capabilities: [],
      run_availability: "requires_configuration",
      executes_drafts: false,
      revision: 3,
      created_at: "2026-08-30T00:00:00Z",
      updated_at: "2026-08-30T00:00:00Z",
      messages: [{ schema_version: "1.0", message_id: "m1", sequence: 0, role: "user", content: "Write a brief", created_at: "2026-08-30T00:00:00Z" }],
    };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({
        schema_version: "1.0", configured: true, model_id: "kimi-k3", model_base_url: "https://api.moonshot.cn/v1",
        model_api_key_env: "MOONSHOT_API_KEY", reasoning_effort: "high", repair_attempts: 3, executes_drafts: false,
      }))
      .mockResolvedValueOnce(response({
        schema_version: "1.0",
        session,
        agent: { schema_version: "1.0", project_id: "project-1", agent_id: "agent-1", slug: "brief", name: "Brief", description: "", source_path: "agents/brief/agent.vagent.yaml", source_file_hash: "file-hash" },
      }));
    const client = new LocalApiClient({ fetcher });

    await expect(client.factoryStatus()).resolves.toMatchObject({ model_id: "kimi-k3", executes_drafts: false, configured: true });
    await expect(client.applyFactoryDraft("project-1", "session-1", { confirm: true })).resolves.toMatchObject({
      session: { state: "completed", executes_drafts: false },
      agent: { agent_id: "agent-1" },
    });
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/factory/status");
    expect(fetcher.mock.calls[1]?.[0]).toBe("/api/v1/projects/project-1/factory/sessions/session-1/apply-draft");
    expect(JSON.parse(String(fetcher.mock.calls[1]?.[1]?.body))).toEqual({ confirm: true });
  });

  it("parses Runtime status without treating a host key as a user-owned Agent secret", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({
      schema_version: "1.0",
      configured: true,
      model_id: "kimi-k3",
      model_base_url: "https://api.moonshot.cn/v1",
      model_api_key_env: "MOONSHOT_API_KEY",
      reasoning_effort: "high",
      allow_process_environment_key: true,
      user_provided_only: false,
    }));
    const client = new LocalApiClient({ fetcher });

    await expect(client.runtimeStatus()).resolves.toMatchObject({
      model_id: "kimi-k3",
      configured: true,
      user_provided_only: false,
    });
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/runtime/status");
  });

  it("sends commit compare-and-swap headers and revision body", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({
      schema_version: "1.0", version_id: "version-1", agent_id: "agent-1", source_hash: "source", behavior_hash: "behavior", lock_hash: "lock", file_hash: "file",
    }));
    const client = new LocalApiClient({ fetcher });

    await client.commit("project-1", "agent-1", {
      expectedRevision: 7,
      etag: '"draft-7"',
      idempotencyKey: "019c0000-0000-7000-8000-000000000002",
    });

    expect(fetcher).toHaveBeenCalledWith("/api/v1/projects/project-1/agents/agent-1/commit", expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({ "If-Match": '"draft-7"', "Idempotency-Key": "019c0000-0000-7000-8000-000000000002" }),
    }));
    expect(JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))).toEqual({ expected_revision: 7 });
  });

  it("parses Agent pin and recoverable delete responses", async () => {
    const agent = { agent_id: "agent-1", slug: "reviewer", name: "Reviewer", description: "", pinned: true, source_path: "agents/reviewer/agent.vagent.yaml", source_file_hash: "file-hash" };
    const updated = summary({ default_agent_id: "agent-1", agent_count: 1, agents: [agent] });
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response(updated))
      .mockResolvedValueOnce(response({ schema_version: "1.0", project_id: "project-1", agent_id: "agent-1", disposition: "trashed", removed_at: "2026-08-28T00:00:00Z", project: summary() }));
    const client = new LocalApiClient({ fetcher });

    await expect(client.updateAgent("project-1", "agent-1", { pinned: true })).resolves.toEqual(updated);
    await expect(client.deleteAgent("project-1", "agent-1")).resolves.toMatchObject({ agent_id: "agent-1", disposition: "trashed", project: summary() });
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/projects/project-1/agents/agent-1");
    expect(fetcher.mock.calls[0]?.[1]).toMatchObject({ method: "PATCH" });
    expect(JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))).toEqual({ pinned: true });
    expect(fetcher.mock.calls[1]?.[1]).toMatchObject({ method: "DELETE" });
  });

  it("parses a recoverable Workflow delete response", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({
      schema_version: "1.0",
      project_id: "project-1",
      workflow_id: "wf-1",
      disposition: "trashed",
      removed_at: "2026-08-28T00:00:00Z",
      project: summary(),
    }));
    const client = new LocalApiClient({ fetcher });
    await expect(client.deleteWorkflow("project-1", "wf-1")).resolves.toMatchObject({ workflow_id: "wf-1", disposition: "trashed", project: summary() });
    expect(fetcher).toHaveBeenCalledWith("/api/v1/projects/project-1/workflows/wf-1", expect.objectContaining({ method: "DELETE" }));
  });
});
