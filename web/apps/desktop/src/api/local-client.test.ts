import { describe, expect, it, vi } from "vitest";
import type { ProjectSummaryResponse, ProviderCapabilityProfile, ResourceDescriptor } from "@veyra/api-contracts";
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

function capabilityProfile(overrides: Partial<ProviderCapabilityProfile> = {}): ProviderCapabilityProfile {
  return {
    schema_version: "1.0",
    provider_id: "moonshot",
    provider_family: "moonshot",
    model: "kimi-k3",
    endpoint_kind: "chat_completions",
    base_url_fingerprint: "fingerprint",
    structured_output: "json_schema",
    schema_flavor: "moonshot_mfjs",
    schema_profile: "mfjs",
    strict_json_schema: true,
    json_object_fallback: true,
    reasoning_effort: true,
    supports_reasoning_effort: true,
    strict_json_schema_support: "unknown",
    json_object_support: "unknown",
    source: "static_known",
    status: "unknown",
    checked_at: null,
    probe_version: "semantic-plan-ok-v1",
    probed: false,
    error_class: null,
    summary: {
      provider: "Moonshot",
      model: "kimi-k3",
      structured_output: "Strict JSON Schema",
      schema_profile: "MFJS",
      json_object_fallback: "Supported",
      status: "Unknown",
      checked_at: "",
      error_class: "",
    },
    ...overrides,
  };
}

function response(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("LocalApiClient Project requests", () => {
  it.each(["resource_unbound", "project_binding_stale", "configuration_required"])("preserves %s Agent dependency evidence", async (status) => {
    const dependency = { reference: "veyra.tool.filesystem.read@1.0.0", kind: "tool", name: "Read File", status, detail: "Check the Project binding", locked_hash: "a".repeat(64), bound_content_hash: "a".repeat(64), content_hash: "b".repeat(64), blocking_reasons: [{ code: "secret_not_configured", message: "Configure host credential." }], used_by: ["read"], bound_by: [] };
    const payload = { schema_version: "1.0", valid: true, source_hash: "source", behavior_hash: "behavior", lock_hash: "lock", file_hash: "file", runtime_ready: false, runtime_ready_scope: "agent_dependencies", dependency_summary: { total: 1, ready: 0, attention: 1 }, dependencies: [dependency] };
    const client = new LocalApiClient({ fetcher: vi.fn().mockResolvedValue(response(payload)) });
    await expect(client.validate("project-1", "agent-1")).resolves.toMatchObject(payload);
  });

  it("accepts a structurally parsed validation failure as a business result", async () => {
    const payload = { schema_version: "1.0", valid: false, source_hash: "source", behavior_hash: "behavior", lock_hash: "lock", file_hash: "file", runtime_ready: false, runtime_ready_scope: "agent_dependencies", dependency_summary: { total: 0, ready: 0, attention: 0 }, dependencies: [] };
    const client = new LocalApiClient({ fetcher: vi.fn().mockResolvedValue(response(payload)) });
    await expect(client.validate("project-1", "agent-1")).resolves.toMatchObject(payload);
  });

  it("still treats a corrupted validation envelope as invalid_response", async () => {
    const client = new LocalApiClient({ fetcher: vi.fn().mockResolvedValue(response({ schema_version: "1.0", valid: "false", source_hash: "source", behavior_hash: "behavior", lock_hash: "lock", file_hash: "file" })) });
    await expect(client.validate("project-1", "agent-1")).rejects.toMatchObject({ code: "invalid_response" });
  });

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
    const missing = { reference: "veyra.skill.missing@1.0.0", content_hash: "b".repeat(64), source: "manual", used_by: [] };
    const payload = { schema_version: "1.0", project_id: "project-1", resources: [descriptor], missing_references: [missing.reference], missing_bindings: [missing], project_count: 2, used_count: 0, unbound_count: 0, builtin_count: 9 };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response(payload))
      .mockResolvedValueOnce(response(payload, 201))
      .mockResolvedValueOnce(response(payload));
    const client = new LocalApiClient({ fetcher });

    await expect(client.listProjectResources("project-1")).resolves.toMatchObject({ project_count: 2, resources: [{ reference: descriptor.reference, scope: "project" }], missing_bindings: [missing] });
    await client.addProjectResource("project-1", { reference: descriptor.reference, content_hash: descriptor.content_hash });
    await client.removeProjectResource("project-1", "veyra.filesystem.read", "1.0.0");
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/projects/project-1/resources");
    expect(fetcher.mock.calls[1]?.[0]).toBe("/api/v1/projects/project-1/resources");
    expect(JSON.parse(String(fetcher.mock.calls[1]?.[1]?.body))).toEqual({ reference: descriptor.reference, content_hash: descriptor.content_hash });
    expect(fetcher.mock.calls[2]?.[0]).toBe("/api/v1/projects/project-1/resources/veyra.filesystem.read/versions/1.0.0");
  });

  it("parses Project-owned Custom Component lifecycles and resource origin", async () => {
    const definition = {
      schema_version: "1.0",
      component_id: "01900000-0000-7000-8000-000000000001",
      project_id: "project-1",
      slug: "invoice-extractor",
      display_name: "Invoice Extractor",
      description: "Extract invoice fields.",
      version: "0.0.0",
      reference: "custom.component.01900000-0000-7000-8000-000000000001@0.0.0",
      content_hash: "a".repeat(64),
      inputs: { text: "string" },
      outputs: { invoice: "object" },
      implementation: { kind: "model_recipe", instruction: "Extract fields", model_ref: "model.primary" },
      metadata: { owner: "finance" },
      dependencies: [],
      required_permissions: { network_hosts: [], tools: [], filesystem_read_roots: [], filesystem_write_roots: [], shell_workspace_only: false },
      readiness: "ready",
      provenance: "manual",
      lifecycle: "draft",
      deprecated: false,
      created_at: "2026-09-22T00:00:00Z",
      updated_at: "2026-09-22T00:00:00Z",
    };
    const resource = {
      schema_version: "1.0",
      resource_id: definition.component_id,
      kind: "component",
      component_class: "composite",
      version: "1.0.0",
      reference: `${definition.component_id}@1.0.0`,
      name: definition.display_name,
      description: definition.description,
      origin: "project",
      content_hash: "b".repeat(64),
      availability: "ready",
      factory_selectable: true,
      runtime_status: "supported",
      required_permissions: definition.required_permissions,
      tags: ["custom-component", "model_recipe"],
      spec: { implementation_kind: "model_recipe" },
      scope: "project",
      binding_status: "current",
      binding_source: "manual",
      bound_content_hash: "b".repeat(64),
      used_by: [],
    };
    const summary = {
      schema_version: "1.0",
      component_id: definition.component_id,
      project_id: "project-1",
      slug: definition.slug,
      display_name: definition.display_name,
      description: definition.description,
      draft: definition,
      latest_version: null,
      versions: [],
    };
    const listPayload = { schema_version: "1.0", project_id: "project-1", components: [summary] };
    const resourcesPayload = { schema_version: "1.0", project_id: "project-1", resources: [resource], missing_references: [], missing_bindings: [], project_count: 1, used_count: 0, unbound_count: 0, builtin_count: 0 };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response(listPayload))
      .mockResolvedValueOnce(response(definition, 201))
      .mockResolvedValueOnce(response(resourcesPayload));
    const client = new LocalApiClient({ fetcher });

    await expect(client.listCustomComponents("project-1")).resolves.toMatchObject({ components: [{ draft: { component_id: definition.component_id, metadata: { owner: "finance" } } }] });
    await expect(client.createCustomComponent("project-1", {
      display_name: definition.display_name,
      description: definition.description,
      inputs: definition.inputs,
      outputs: definition.outputs,
      implementation: definition.implementation,
      metadata: definition.metadata,
    })).resolves.toMatchObject({ reference: definition.reference, lifecycle: "draft" });
    await expect(client.listProjectResources("project-1")).resolves.toMatchObject({ resources: [{ kind: "component", origin: "project", component_class: "composite" }] });
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/projects/project-1/custom-components");
    expect(fetcher.mock.calls[1]?.[1]).toMatchObject({ method: "POST" });
    expect(JSON.parse(String(fetcher.mock.calls[1]?.[1]?.body))).toMatchObject({ display_name: "Invoice Extractor", implementation: { kind: "model_recipe" } });
    expect(fetcher.mock.calls[2]?.[0]).toBe("/api/v1/projects/project-1/resources");
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

  it("reads failed Tool receipts without rejecting the entire run detail", async () => {
    const event = {
      schema_version: "1.0", event_id: "event-1", run_id: "run-1", sequence: 5,
      kind: "tool.failed", node_id: "lookup", timestamp: "2026-08-28T10:00:01Z",
      payload: { input_digest: "a".repeat(64), output_digest: null, schema_validation: { input: "failed", output: "not_checked" } },
    };
    const failed = {
      schema_version: "1.0", run_id: "run-1", project_id: "project-1", agent_id: "agent-1",
      version_id: "version-1", status: "failed", result: null,
      error: { code: "mcp_input_schema_invalid", message: "MCP input validation failed" },
      created_at: "2026-08-28T10:00:00Z", finished_at: "2026-08-28T10:00:01Z", events: [event],
    };
    const fetcher = vi.fn().mockResolvedValue(response(failed));
    const client = new LocalApiClient({ fetcher });
    await expect(client.getAgentRun("project-1", "agent-1", "run-1")).resolves.toEqual(failed);
    fetcher.mockResolvedValue(response({ ...failed, events: [{ ...event, kind: "tool.unknown" }] }));
    await expect(client.getAgentRun("project-1", "agent-1", "run-1")).rejects.toMatchObject({ code: "invalid_response" });
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
    let created: { url: string; closed: boolean; readyState: number; onerror: ((event: Event) => void) | null } | undefined;
    class FakeEventSource {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSED = 2;
      url: string;
      closed = false;
      readyState = FakeEventSource.OPEN;
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
    const onError = vi.fn();
    const stop = client.watchAgentRunEvents("project-1", "agent-1", "run-1", { onEvent, onDone, onError }, { after: 2 });
    expect(created?.url).toBe("/api/v1/projects/project-1/agents/agent-1/runs/run-1/events?after=2");
    expect(listeners.runtime).toBeDefined();
    listeners.runtime({ data: JSON.stringify(event) } as MessageEvent);
    const failed = { ...event, event_id: "event-2", sequence: 3, kind: "tool.failed", node_id: "lookup", payload: { output_digest: null, schema_validation: { input: "failed", output: "not_checked" } } };
    listeners.runtime({ data: JSON.stringify(failed) } as MessageEvent);
    expect(onEvent).toHaveBeenCalledWith(failed);
    expect(onError).not.toHaveBeenCalled();
    created?.onerror?.(new Event("error"));
    expect(created?.closed).toBe(false);
    expect(onError).not.toHaveBeenCalled();
    listeners.done({ data: JSON.stringify({ status: "failed" }) } as MessageEvent);
    expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({ kind: "run.created", sequence: 1 }));
    expect(onDone).toHaveBeenCalledWith("failed");
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
      availability: "requires_configuration",
      factory_selectable: true,
      runtime_status: "runtime_not_configured",
      required_permissions: { network_hosts: [], tools: [], filesystem_read_roots: [], filesystem_write_roots: [], shell_workspace_only: false },
      tags: ["research", "instruction"],
      spec: { instruction: "State scope and evidence." },
      blocking_reasons: [{ code: "model_configuration", message: "Configure Runtime provider." }],
      configuration_requirements: [{ code: "model_configuration", message: "Configure Runtime provider.", satisfied: false }],
      dependencies: [],
      compatibility: { scope: "host", execution: "Requires permissions.", network_verified: false },
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
        capability_profile: capabilityProfile(),
      }))
      .mockResolvedValueOnce(response({
        schema_version: "1.0",
        session,
        agent: { schema_version: "1.0", project_id: "project-1", agent_id: "agent-1", slug: "brief", name: "Brief", description: "", source_path: "agents/brief/agent.vagent.yaml", source_file_hash: "file-hash" },
      }));
    const client = new LocalApiClient({ fetcher });

    await expect(client.factoryStatus()).resolves.toMatchObject({
      model_id: "kimi-k3",
      executes_drafts: false,
      configured: true,
      capability_profile: {
        provider_family: "moonshot",
        structured_output: "json_schema",
        schema_flavor: "moonshot_mfjs",
        probed: false,
      },
    });
    await expect(client.applyFactoryDraft("project-1", "session-1", { confirm: true })).resolves.toMatchObject({
      session: { state: "completed", executes_drafts: false },
      agent: { agent_id: "agent-1" },
    });
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/factory/status");
    expect(fetcher.mock.calls[1]?.[0]).toBe("/api/v1/projects/project-1/factory/sessions/session-1/apply-draft");
    expect(JSON.parse(String(fetcher.mock.calls[1]?.[1]?.body))).toEqual({ confirm: true });
  });

  it("rejects Factory status without a host capability profile", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({
      schema_version: "1.0", configured: true, model_id: "kimi-k3", model_base_url: "https://api.moonshot.cn/v1",
      model_api_key_env: "MOONSHOT_API_KEY", reasoning_effort: "high", repair_attempts: 3, executes_drafts: false,
    }));
    const client = new LocalApiClient({ fetcher });
    await expect(client.factoryStatus()).rejects.toMatchObject({ code: "invalid_response" });
  });

  it("accepts a probed Moonshot json_object fallback profile", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({
      schema_version: "1.0", configured: true, model_id: "kimi-k3", model_base_url: "https://api.moonshot.cn/v1",
      model_api_key_env: "MOONSHOT_API_KEY", reasoning_effort: "high", repair_attempts: 3, executes_drafts: false,
      capability_profile: capabilityProfile({
        structured_output: "json_object",
        schema_flavor: "moonshot_mfjs",
        schema_profile: "mfjs",
        strict_json_schema: false,
        json_object_fallback: false,
        strict_json_schema_support: "unsupported",
        json_object_support: "supported",
        source: "fallback",
        status: "known",
        probed: true,
        checked_at: "2026-09-19T12:00:00Z",
        summary: {
          provider: "Moonshot",
          model: "kimi-k3",
          structured_output: "JSON object",
          schema_profile: "MFJS",
          json_object_fallback: "Not used",
          status: "Known",
          checked_at: "2026-09-19T12:00:00Z",
          error_class: "",
        },
      }),
    }));
    const client = new LocalApiClient({ fetcher });
    await expect(client.factoryStatus()).resolves.toMatchObject({
      capability_profile: {
        source: "fallback",
        json_object_support: "supported",
        summary: { status: "Known", structured_output: "JSON object" },
      },
    });
  });

  it("parses an inconclusive rate-limited capability profile without unsupported", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({
      schema_version: "1.0", configured: true, model_id: "kimi-k3", model_base_url: "https://api.moonshot.cn/v1",
      model_api_key_env: "MOONSHOT_API_KEY", reasoning_effort: "high", repair_attempts: 3, executes_drafts: false,
      capability_profile: capabilityProfile({
        status: "inconclusive",
        error_class: "rate_limited",
        checked_at: "2026-09-19T12:00:00Z",
        summary: {
          provider: "Moonshot",
          model: "kimi-k3",
          structured_output: "Strict JSON Schema",
          schema_profile: "MFJS",
          json_object_fallback: "Supported",
          status: "Inconclusive",
          checked_at: "2026-09-19T12:00:00Z",
          error_class: "rate_limited",
        },
      }),
    }));
    const client = new LocalApiClient({ fetcher });
    await expect(client.factoryStatus()).resolves.toMatchObject({
      capability_profile: {
        status: "inconclusive",
        strict_json_schema: true,
        summary: { status: "Inconclusive", structured_output: "Strict JSON Schema" },
      },
    });
  });

  it("parses an OpenAI-compatible Factory capability profile", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({
      schema_version: "1.0", configured: true, model_id: "gpt-test", model_base_url: "https://llm.example.test/v1",
      model_api_key_env: "EXAMPLE_KEY", reasoning_effort: "high", repair_attempts: 3, executes_drafts: false,
      capability_profile: {
        schema_version: "1.0",
        provider_id: "openai_compatible",
        provider_family: "openai_compatible",
        model: "gpt-test",
        endpoint_kind: "chat_completions",
        base_url_fingerprint: "compat-fingerprint",
        structured_output: "json_object",
        schema_flavor: "none",
        schema_profile: "unknown",
        strict_json_schema: false,
        json_object_fallback: false,
        reasoning_effort: false,
        supports_reasoning_effort: false,
        strict_json_schema_support: "unknown",
        json_object_support: "unknown",
        source: "static_known",
        status: "unknown",
        checked_at: null,
        probe_version: "semantic-plan-ok-v1",
        probed: false,
        error_class: null,
        summary: {
          provider: "OpenAI-compatible",
          model: "gpt-test",
          structured_output: "JSON object",
          schema_profile: "Unknown",
          json_object_fallback: "Not used",
          status: "Unknown",
          checked_at: "",
          error_class: "",
        },
      },
    }));
    const client = new LocalApiClient({ fetcher });
    await expect(client.factoryStatus()).resolves.toMatchObject({
      model_id: "gpt-test",
      capability_profile: {
        provider_family: "openai_compatible",
        structured_output: "json_object",
        schema_flavor: "none",
        probed: false,
      },
    });
  });

  it("posts Builder turns without treating client history as canonical truth", async () => {
    const snapshot = {
      schema_version: "1.0",
      conversation: {
        conversation_id: "conv-1",
        project_id: "project-1",
        title: "Wrap a gift",
        status: "active",
        created_at: "2026-09-18T00:00:00Z",
        updated_at: "2026-09-18T00:00:01Z",
        last_activity_at: "2026-09-18T00:00:01Z",
        last_operation_status: "failed",
      },
      messages: [
        { message_id: "m-user", conversation_id: "conv-1", sequence: 0, role: "user", kind: "user", content: "Wrap a gift", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:00Z" },
      ],
      operations: [
        { operation_id: "op-1", conversation_id: "conv-1", kind: "create_agent", status: "failed", retry_of: null, error_code: "factory_request_invalid", proposal_id: null, run_id: null, factory_session_id: null, created_at: "2026-09-18T00:00:00Z", updated_at: "2026-09-18T00:00:01Z", diagnostic: {}, has_request: true },
      ],
      resolution: null,
      factory_session: null,
    };
    const fetcher = vi.fn().mockResolvedValue(response(snapshot));
    const client = new LocalApiClient({ fetcher });
    await expect(client.submitBuilderTurn("project-1", { content: "Wrap a gift", focus: null, locale: "en" })).resolves.toMatchObject({
      conversation: { conversation_id: "conv-1" },
      operations: [{ status: "failed" }],
    });
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/projects/project-1/builder/turns");
    expect(JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))).toEqual({ content: "Wrap a gift", focus: null, locale: "en" });
  });

  it("parses Builder harness receipts on operations and defaults missing receipts", async () => {
    const snapshot = {
      schema_version: "1.0",
      conversation: {
        conversation_id: "conv-1",
        project_id: "project-1",
        title: "Wrap a gift",
        status: "active",
        created_at: "2026-09-18T00:00:00Z",
        updated_at: "2026-09-18T00:00:01Z",
        last_activity_at: "2026-09-18T00:00:01Z",
        last_operation_status: "waiting",
      },
      messages: [
        { message_id: "m-user", conversation_id: "conv-1", sequence: 0, role: "user", kind: "user", content: "Wrap a gift", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:00Z" },
      ],
      operations: [
        {
          operation_id: "op-1",
          conversation_id: "conv-1",
          kind: "create_agent",
          status: "waiting",
          retry_of: null,
          error_code: null,
          proposal_id: null,
          run_id: null,
          factory_session_id: "session-1",
          created_at: "2026-09-18T00:00:00Z",
          updated_at: "2026-09-18T00:00:01Z",
          diagnostic: {},
          has_request: true,
          receipts: [{
            receipt_id: "receipt-1",
            operation_id: "op-1",
            conversation_id: "conv-1",
            project_id: "project-1",
            invocation_kind: "semantic_plan",
            sequence: 2,
            status: "success",
            started_at: "2026-09-18T00:00:02Z",
            completed_at: "2026-09-18T00:00:10Z",
            harness_mode: "create_agent",
            policy_version: "builder-policy-v1",
            policy_hash: "abc",
            output_contract: "AgentSemanticPlanV1",
            schema_version: "1.0",
            schema_hash: "def",
            structured_mode: "strict_json_schema",
            project_snapshot_hash: "ghi",
            catalog_snapshot_hash: "jkl",
            included_categories: ["project_agents_metadata"],
            excluded_categories: ["knowledge_contents"],
            history_message_count: 1,
            context_size_bytes: 10,
            request_size_bytes: 20,
            provider_id: "moonshot",
            model: "kimi-k3",
            endpoint_kind: "chat_completions",
            provider_profile_status: "known",
            provider_profile_source: "probe",
            schema_profile: "mfjs",
            failure_stage: null,
            error_code: null,
            safe_provider_error_type: null,
            safe_provider_error_param: null,
            provider_request_id: null,
            fallback_from: null,
            fallback_to: null,
          }],
        },
      ],
      resolution: null,
      factory_session: null,
    };
    const fetcher = vi.fn().mockResolvedValue(response(snapshot));
    const client = new LocalApiClient({ fetcher });
    await expect(client.getBuilderConversation("project-1", "conv-1")).resolves.toMatchObject({
      operations: [{ receipts: [{ invocation_kind: "semantic_plan", structured_mode: "strict_json_schema" }] }],
    });
  });

  it("keeps the canonical Builder snapshot when the auxiliary Factory session has a schema mismatch", async () => {
    const snapshot = {
      schema_version: "1.0",
      conversation: {
        conversation_id: "conv-1",
        project_id: "project-1",
        title: "Request Review Agent",
        status: "active",
        created_at: "2026-09-18T00:00:00Z",
        updated_at: "2026-09-18T00:00:01Z",
        last_activity_at: "2026-09-18T00:00:01Z",
        last_operation_status: "waiting",
      },
      messages: [],
      operations: [{
        operation_id: "op-1",
        conversation_id: "conv-1",
        kind: "create_agent",
        status: "waiting",
        retry_of: null,
        error_code: null,
        proposal_id: "proposal-1",
        run_id: null,
        factory_session_id: "session-1",
        created_at: "2026-09-18T00:00:00Z",
        updated_at: "2026-09-18T00:00:01Z",
        diagnostic: {},
        has_request: true,
        receipts: [],
        events: [],
      }],
      resolution: null,
      factory_session: { schema_version: "0.9" },
    };
    const client = new LocalApiClient({ fetcher: vi.fn().mockResolvedValue(response(snapshot)) });

    await expect(client.getBuilderConversation("project-1", "conv-1")).resolves.toMatchObject({
      operations: [{ proposal_id: "proposal-1", status: "waiting" }],
      factory_session: null,
    });
  });

  it("parses Builder run observations and posts explicit test-run commands", async () => {
    const snapshot = {
      schema_version: "1.0",
      conversation: {
        conversation_id: "conv-1",
        project_id: "project-1",
        title: "Test Agent",
        status: "active",
        created_at: "2026-09-20T00:00:00Z",
        updated_at: "2026-09-20T00:00:01Z",
        last_activity_at: "2026-09-20T00:00:01Z",
        last_operation_status: "succeeded",
      },
      messages: [],
      operations: [{
        operation_id: "op-test",
        conversation_id: "conv-1",
        kind: "test_agent",
        target_kind: "agent",
        status: "succeeded",
        retry_of: null,
        error_code: null,
        proposal_id: null,
        run_id: "run-1",
        factory_session_id: null,
        created_at: "2026-09-20T00:00:00Z",
        updated_at: "2026-09-20T00:00:01Z",
        diagnostic: { version_id: "version-1" },
        has_request: false,
        events: [],
        receipts: [],
        run_observation: {
          run_id: "run-1",
          agent_id: "agent-1",
          version_id: "version-1",
          status: "unverified",
          runtime_model_id: "kimi-k3",
          runtime_model_source: "host",
          output_summary: "你好，世界",
          failure_code: null,
          failed_node: null,
          tool_failure: null,
          knowledge_failure: null,
          approval_required: false,
          duration_ms: 12,
          evidence_count: 0,
          classification: "none",
          explanation: "测试成功。",
          repair_proposal_id: null,
          repair_code: null,
          next_action: null,
        },
      }],
      resolution: null,
      factory_session: null,
    };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response(snapshot))
      .mockResolvedValueOnce(response(snapshot))
      .mockResolvedValueOnce(response(snapshot));
    const client = new LocalApiClient({ fetcher });
    await expect(client.startBuilderTestRun("project-1", "conv-1", { agent_id: "agent-1", inputs: { text: "Hello world" }, locale: "zh" })).resolves.toMatchObject({
      operations: [{ kind: "test_agent", run_id: "run-1", run_observation: { runtime_model_id: "kimi-k3", output_summary: "你好，世界" } }],
    });
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/projects/project-1/builder/conversations/conv-1/test-runs");
    await client.commandBuilderTestRun("project-1", "conv-1", "op-test", { command: "stop", locale: "zh" });
    expect(fetcher.mock.calls[1]?.[0]).toBe("/api/v1/projects/project-1/builder/conversations/conv-1/operations/op-test/test-commands");
    await client.proposeBuilderTestRepair("project-1", "conv-1", "op-test", { locale: "zh" });
    expect(fetcher.mock.calls[2]?.[0]).toBe("/api/v1/projects/project-1/builder/conversations/conv-1/operations/op-test/test-repair");
  });

  it("keeps Builder conversation messages when Factory missing-capability payload is invalid", async () => {
    const snapshot = {
      schema_version: "1.0",
      conversation: {
        conversation_id: "conv-1",
        project_id: "project-1",
        title: "Wrap a gift",
        status: "active",
        created_at: "2026-09-18T00:00:00Z",
        updated_at: "2026-09-18T00:00:01Z",
        last_activity_at: "2026-09-18T00:00:01Z",
        last_operation_status: "failed",
      },
      messages: [
        { message_id: "m-user", conversation_id: "conv-1", sequence: 0, role: "user", kind: "user", content: "Wrap a gift", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:00Z" },
      ],
      operations: [
        { operation_id: "op-1", conversation_id: "conv-1", kind: "create_agent", status: "failed", retry_of: null, error_code: "factory_missing_capability", proposal_id: null, run_id: null, factory_session_id: "session-1", created_at: "2026-09-18T00:00:00Z", updated_at: "2026-09-18T00:00:01Z", diagnostic: {}, has_request: true },
      ],
      resolution: null,
      factory_session: {
        schema_version: "1.0",
        session_id: "session-1",
        project_id: "project-1",
        state: "missing_capability",
        ready: true,
        next_prompt: "",
        resource_plan: [],
        blueprint: null,
        diagnostics: [],
        missing_capabilities: [{
          kind: "tool",
          reference: "veyra.tool.filesystem.read",
          reason: "Tool is not bound to this Project",
          proposal: { action: "missing_capability", executable: false },
        }],
        run_availability: "unavailable",
        executes_drafts: false,
        revision: 1,
        created_at: "2026-09-18T00:00:00Z",
        updated_at: "2026-09-18T00:00:01Z",
        messages: [],
      },
    };
    const fetcher = vi.fn().mockResolvedValue(response(snapshot));
    const client = new LocalApiClient({ fetcher });
    await expect(client.submitBuilderTurn("project-1", { content: "Wrap a gift", focus: null, locale: "en" })).resolves.toMatchObject({
      conversation: { conversation_id: "conv-1" },
      messages: [{ kind: "user", content: "Wrap a gift" }],
      factory_session: { state: "missing_capability" },
    });
  });

  it("keeps Builder conversation messages when a missing-capability proposal is executable", async () => {
    const snapshot = {
      schema_version: "1.0",
      conversation: {
        conversation_id: "conv-1",
        project_id: "project-1",
        title: "Wrap a gift",
        status: "active",
        created_at: "2026-09-18T00:00:00Z",
        updated_at: "2026-09-18T00:00:01Z",
        last_activity_at: "2026-09-18T00:00:01Z",
        last_operation_status: "failed",
      },
      messages: [
        { message_id: "m-user", conversation_id: "conv-1", sequence: 0, role: "user", kind: "user", content: "Wrap a gift", operation_id: "op-1", payload: {}, created_at: "2026-09-18T00:00:00Z" },
      ],
      operations: [
        { operation_id: "op-1", conversation_id: "conv-1", kind: "create_agent", status: "failed", retry_of: null, error_code: "factory_missing_capability", proposal_id: null, run_id: null, factory_session_id: "session-1", created_at: "2026-09-18T00:00:00Z", updated_at: "2026-09-18T00:00:01Z", diagnostic: {}, has_request: true },
      ],
      resolution: null,
      factory_session: {
        schema_version: "1.0",
        session_id: "session-1",
        project_id: "project-1",
        state: "missing_capability",
        ready: true,
        next_prompt: "",
        resource_plan: [],
        blueprint: null,
        diagnostics: [],
        missing_capabilities: [{
          kind: "tool",
          reference: "veyra.tool.filesystem.read",
          reason: "Tool is not bound to this Project",
          proposal: { action: "quarantined_resource_draft", executable: true },
        }],
        run_availability: "unavailable",
        executes_drafts: false,
        revision: 1,
        created_at: "2026-09-18T00:00:00Z",
        updated_at: "2026-09-18T00:00:01Z",
        messages: [],
      },
    };
    const fetcher = vi.fn().mockResolvedValue(response(snapshot));
    const client = new LocalApiClient({ fetcher });
    await expect(client.submitBuilderTurn("project-1", { content: "Wrap a gift", focus: null, locale: "en" })).resolves.toMatchObject({
      conversation: { conversation_id: "conv-1" },
      messages: [{ kind: "user", content: "Wrap a gift" }],
      factory_session: null,
    });
  });

  it("drops Runtime runs from Builder Recent activity", async () => {
    const payload = {
      schema_version: "1.0",
      project_id: "dddd",
      items: [
        { kind: "conversation", id: "conv-1", conversation_id: "conv-1", title: "礼物包装 Agent", status: "failed", operation_kind: "create_agent", occurred_at: "2026-09-18T00:00:01Z" },
        { kind: "run", id: "run-1", run_id: "run-1", title: "translation", status: "unverified", run_kind: "agent", occurred_at: "2026-09-12T00:00:00Z", agent_id: "agent-1" },
      ],
    };
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(response(payload)));
    const client = new LocalApiClient({ fetcher });
    await expect(client.listBuilderActivity("dddd")).resolves.toEqual({
      schema_version: "1.0",
      project_id: "dddd",
      items: [
        { kind: "conversation", id: "conv-1", conversation_id: "conv-1", title: "礼物包装 Agent", status: "failed", operation_kind: "create_agent", occurred_at: "2026-09-18T00:00:01Z" },
      ],
    });
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/projects/dddd/builder/activity");
    await expect(client.listBuilderActivity()).resolves.toEqual({
      schema_version: "1.0",
      project_id: "dddd",
      items: [
        { kind: "conversation", id: "conv-1", conversation_id: "conv-1", title: "礼物包装 Agent", status: "failed", operation_kind: "create_agent", occurred_at: "2026-09-18T00:00:01Z" },
      ],
    });
    expect(fetcher.mock.calls[1]?.[0]).toBe("/api/v1/builder/activity");
  });

  it("renames and deletes a Builder conversation", async () => {
    const snapshot = {
      schema_version: "1.0",
      conversation: {
        conversation_id: "conv-1",
        project_id: "project-1",
        title: "日程提醒整理 Agent",
        status: "active",
        created_at: "2026-09-18T00:00:00Z",
        updated_at: "2026-09-20T00:00:00Z",
        last_activity_at: "2026-09-20T00:00:00Z",
        last_operation_status: "succeeded",
      },
      messages: [],
      operations: [],
      resolution: null,
      factory_session: null,
    };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response(snapshot))
      .mockResolvedValueOnce(response({ schema_version: "1.0", conversation_id: "conv-1", deleted: true }));
    const client = new LocalApiClient({ fetcher });
    await expect(client.renameBuilderConversation("project-1", "conv-1", { title: "日程提醒整理 Agent" })).resolves.toMatchObject({
      conversation: { title: "日程提醒整理 Agent" },
    });
    await expect(client.deleteBuilderConversation("project-1", "conv-1")).resolves.toEqual({
      schema_version: "1.0",
      conversation_id: "conv-1",
      deleted: true,
    });
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/projects/project-1/builder/conversations/conv-1");
    expect(fetcher.mock.calls[0]?.[1]).toMatchObject({ method: "PATCH" });
    expect(fetcher.mock.calls[1]?.[1]).toMatchObject({ method: "DELETE" });
  });

  it("lists and mutates workspace Trash with typed item identities", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({
        schema_version: "1.0",
        retention_days: 30,
        items: [{
          kind: "conversation",
          id: "conv-1",
          name: "日程提醒整理 Agent",
          project_id: "project-1",
          project_name: "Project One",
          removed_at: "2026-09-20T00:00:00Z",
          expires_at: "2026-10-20T00:00:00Z",
          restorable: true,
        }],
      }))
      .mockResolvedValueOnce(response({ schema_version: "1.0", kind: "conversation", id: "conv-1", restored: true }))
      .mockResolvedValueOnce(response({ schema_version: "1.0", kind: "conversation", id: "conv-1", deleted: true }));
    const client = new LocalApiClient({ fetcher });
    await expect(client.listWorkspaceTrash()).resolves.toMatchObject({
      retention_days: 30,
      items: [{ kind: "conversation", id: "conv-1", restorable: true }],
    });
    await expect(client.restoreWorkspaceTrash("conversation", "conv-1")).resolves.toMatchObject({ restored: true });
    await expect(client.purgeWorkspaceTrash("conversation", "conv-1")).resolves.toMatchObject({ deleted: true });
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/trash");
    expect(fetcher.mock.calls[1]?.[0]).toBe("/api/v1/trash/conversation/conv-1/restore");
    expect(fetcher.mock.calls[2]?.[0]).toBe("/api/v1/trash/conversation/conv-1/purge");
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

  it("parses Runtime modalities and Project artifact uploads", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({
        schema_version: "1.0",
        configured: true,
        model_id: "kimi-k3",
        model_base_url: "https://api.moonshot.cn/v1",
        model_api_key_env: "MOONSHOT_API_KEY",
        reasoning_effort: "high",
        allow_process_environment_key: true,
        user_provided_only: false,
        modalities: {
          provider: "moonshot",
          model_id: "kimi-k3",
          text_input: "supported",
          image_input: "supported",
          video_input: "unsupported",
          audio_input: "unsupported",
          structured_json_output: "supported",
          source: "static_profile",
        },
      }))
      .mockResolvedValueOnce(response({
        kind: "artifact",
        artifact_id: "art_1",
        project_id: "project-1",
        sha256: "a".repeat(64),
        filename: "product.png",
        media_type: "image/png",
        size_bytes: 12,
        storage_ref: "sha256/aa",
        source_kind: "upload",
        created_at: "2026-09-22T00:00:00Z",
      }, 201));
    const client = new LocalApiClient({ fetcher });
    await expect(client.runtimeStatus()).resolves.toMatchObject({
      modalities: { image_input: "supported", video_input: "unsupported", source: "static_profile" },
    });
    const file = new File(["png"], "product.png", { type: "image/png" });
    await expect(client.uploadArtifact("project-1", file)).resolves.toMatchObject({
      artifact_id: "art_1",
      filename: "product.png",
      kind: "artifact",
    });
    expect(String(fetcher.mock.calls[1]?.[0])).toContain("/api/v1/projects/project-1/artifacts");
  });

  it("accepts account-default Runtime readiness without video_input fields", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({
      schema_version: "1.0",
      project_id: "project-1",
      agent_id: "agent-1",
      ready: true,
      profile_source: "user_default",
      model: {
        required: true,
        configured: true,
        model_id: "kimi-k3",
        model_base_url: "https://api.moonshot.cn/v1",
        model_api_key_env: "MOONSHOT_API_KEY",
        modalities: {
          provider: "moonshot",
          model_id: "kimi-k3",
          text_input: "supported",
          image_input: "supported",
          structured_json_output: "supported",
          source: "static_profile",
        },
      },
      dependency_summary: { total: 0, ready: 0, attention: 0 },
      dependencies: [],
      tool_checks: [],
      checks: [
        { id: "dependencies", ready: true, code: "ready", detail: "ok" },
        { id: "model", ready: true, code: "ready", detail: "ok" },
        { id: "modalities", ready: true, code: "ready", detail: "ok" },
        { id: "tools", ready: true, code: "ready", detail: "ok" },
      ],
    }));
    const client = new LocalApiClient({ fetcher });
    await expect(client.runtimeReadiness("project-1", "agent-1")).resolves.toMatchObject({
      profile_source: "default",
      model: {
        configured: true,
        modalities: { image_input: "supported", video_input: "unsupported", audio_input: "unsupported" },
      },
    });
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
