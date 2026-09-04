import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentSource, FactorySession, FactoryStatus } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { FactoryConversation } from "./factory-conversation";
import { writePendingFactoryPrompt } from "../agents/chat/pending-factory-prompt";

const source: AgentSource = {
  schema_version: "1.0",
  agentspec_version: "26.1",
  component_type: "Flow",
  agent_id: "agent-1",
  slug: "research-brief-agent",
  name: "Research Brief Agent",
  description: "Brief",
  inputs: { question: "string" },
  outputs: { brief: "string" },
  nodes: [
    { id: "start", component_type: "Start" },
    { id: "analyze", component_type: "Agent", model_ref: "model.primary", system_prompt: "Write a brief." },
    { id: "output", component_type: "Output", output_name: "brief" },
  ],
  transitions: [
    { from: "start", port: "next", to: "analyze" },
    { from: "analyze", port: "next", to: "output" },
  ],
  extensions: { veyra: { runtime_profile: "guarded-local", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: true, checks: [] } } },
  ui: { positions: {} },
  lock: {},
};

function session(overrides: Partial<FactorySession> = {}): FactorySession {
  return {
    schema_version: "1.0",
    session_id: "session-1",
    project_id: "project-1",
    state: "review",
    ready: true,
    next_prompt: "Review the Blueprint.",
    resource_plan: [{
      reference: "veyra.skill.research-brief@1.0.0",
      kind: "skill",
      availability: "ready",
      runtime_status: "runtime_not_configured",
    }],
    blueprint: {
      schema_version: "1.0",
      goal: "Brief",
      nodes: [
        { id: "start", component_type: "Start" },
        { id: "analyze", component_type: "Agent" },
        { id: "output", component_type: "Output" },
      ],
      transitions: [
        { from: "start", port: "next", to: "analyze" },
        { from: "analyze", port: "next", to: "output" },
      ],
    },
    diagnostics: [],
    missing_capabilities: [],
    run_availability: "requires_configuration",
    executes_drafts: false,
    revision: 2,
    created_at: "2026-08-30T00:00:00Z",
    updated_at: "2026-08-30T00:00:00Z",
    messages: [
      { schema_version: "1.0", message_id: "m1", sequence: 0, role: "user", content: "Write a brief", created_at: "2026-08-30T00:00:00Z" },
      { schema_version: "1.0", message_id: "m2", sequence: 1, role: "assistant", content: "What inputs?", created_at: "2026-08-30T00:00:01Z" },
    ],
    ...overrides,
  };
}

const status: FactoryStatus = {
  schema_version: "1.0",
  configured: true,
  model_id: "kimi-k3",
  model_base_url: "https://api.moonshot.cn/v1",
  model_api_key_env: "MOONSHOT_API_KEY",
  reasoning_effort: "high",
  repair_attempts: 3,
  executes_drafts: false,
};

function apiFor(overrides: Partial<LocalProjectApi> = {}): LocalProjectApi {
  return {
    listProjects: vi.fn(),
    createProject: vi.fn(),
    openProject: vi.fn(),
    getProject: vi.fn(),
    updateProject: vi.fn(),
    deleteProject: vi.fn(),
    updateAgent: vi.fn(),
    deleteAgent: vi.fn(),
    listAgentTemplates: vi.fn(),
    createAgent: vi.fn(),
    importAgent: vi.fn(),
    getDraft: vi.fn().mockResolvedValue({
      schema_version: "1.0",
      draft_id: "draft-1",
      revision: 1,
      etag: "etag-1",
      source_file_hash: "source-hash",
      source,
    }),
    selectDirectory: vi.fn(),
    factoryStatus: vi.fn().mockResolvedValue(status),
    createFactorySession: vi.fn().mockResolvedValue(session({ state: "ready", blueprint: null, resource_plan: [] })),
    addFactoryMessage: vi.fn(),
    generateFactoryBlueprint: vi.fn().mockResolvedValue(session()),
    applyFactoryDraft: vi.fn().mockResolvedValue({
      schema_version: "1.0",
      session: session({ state: "completed" }),
      agent: {
        schema_version: "1.0",
        project_id: "project-1",
        agent_id: "agent-1",
        slug: "research-brief-agent",
        name: "Research Brief Agent",
        description: "Brief",
        source_path: "agents/research-brief-agent/agent.vagent.yaml",
        source_file_hash: "file-hash",
      },
    }),
    createResourceDraft: vi.fn().mockResolvedValue({
      schema_version: "1.0",
      executable: false,
      resource: { resource_id: "draft-tool", availability: "quarantined" },
    }),
    ...overrides,
  } as LocalProjectApi;
}

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

describe("FactoryConversation", () => {
  it("collects a requirement, generates a Blueprint, and creates a Draft without running", async () => {
    const api = apiFor();
    const user = userEvent.setup();
    render(<ThemeProvider><FactoryConversation api={api} projectId="project-1" locale="en" /></ThemeProvider>);

    expect(await screen.findByText("Veyra Agent is configured for Draft generation only.")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox"), "Write a research brief");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(api.createFactorySession).toHaveBeenCalledWith("project-1", { goal: "Write a research brief" });
    expect(await screen.findByLabelText("Assembly canvas")).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "Generate Blueprint" }));
    expect(api.generateFactoryBlueprint).toHaveBeenCalledWith("project-1", "session-1");
    expect(await screen.findByText("veyra.skill.research-brief@1.0.0")).toBeInTheDocument();
    expect(api.runAgent).toBeUndefined();

    await user.click(screen.getByRole("button", { name: "Create Draft" }));
    expect(api.applyFactoryDraft).toHaveBeenCalledWith("project-1", "session-1", { confirm: true });
    expect(await screen.findByRole("link", { name: "Open Studio" })).toHaveAttribute("href", "#/projects/project-1/agents/agent-1/design");
    expect(api.runAgent).toBeUndefined();
  });

  it("test-runs the created Draft only after the user starts it", async () => {
    const run = {
      schema_version: "1.0" as const,
      run_id: "run-1",
      project_id: "project-1",
      agent_id: "agent-1",
      version_id: "version-1",
      status: "verified" as const,
      result: { brief: "Done" },
      error: null,
      created_at: "2026-08-30T00:00:00Z",
      finished_at: "2026-08-30T00:00:01Z",
    };
    const runAgent = vi.fn().mockResolvedValue(run);
    const api = apiFor({
      runAgent,
      getAgentRun: vi.fn().mockResolvedValue(run),
    });
    const user = userEvent.setup();
    render(<ThemeProvider><FactoryConversation api={api} projectId="project-1" locale="en" /></ThemeProvider>);
    await user.type(await screen.findByRole("textbox", { name: "Message" }), "Write a research brief");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await user.click(await screen.findByRole("button", { name: "Generate Blueprint" }));
    await user.click(await screen.findByRole("button", { name: "Create Draft" }));
    expect(runAgent).not.toHaveBeenCalled();
    await user.type(await screen.findByLabelText("Test-run input"), "What happened?");
    await user.click(screen.getByRole("button", { name: "Start test run" }));
    await waitFor(() => expect(runAgent).toHaveBeenCalledWith("project-1", "agent-1", { inputs: { question: "What happened?" } }));
    expect(await screen.findByText(/"brief": "Done"/)).toBeInTheDocument();
  });

  it("applies a revision Draft as a child of the focused Agent", async () => {
    const api = apiFor({
      createFactorySession: vi.fn().mockResolvedValue(session()),
    });
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <FactoryConversation
          api={api}
          projectId="project-1"
          locale="en"
          focusAgent={{ agentId: "parent-1", name: "Reviewer", description: "Reviews a request." }}
        />
      </ThemeProvider>,
    );

    expect(await screen.findByRole("heading", { name: "What do you want to achieve in Reviewer?", level: 2 })).toBeInTheDocument();
    await user.type(screen.getByRole("textbox"), "Add an approval step");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(api.createFactorySession).toHaveBeenCalledWith("project-1", {
      goal: expect.stringContaining("parent-1"),
    });
    const goal = (api.createFactorySession as ReturnType<typeof vi.fn>).mock.calls[0][1].goal as string;
    expect(goal).toContain("Add an approval step");
    expect(goal).toContain("Reviewer");

    await user.click(await screen.findByRole("button", { name: "Create Draft" }));
    expect(api.applyFactoryDraft).toHaveBeenCalledWith("project-1", "session-1", {
      confirm: true,
      parent_agent_id: "parent-1",
    });
  });

  it("quarantines missing capabilities instead of executing generated tools", async () => {
    const missing = session({
      state: "missing_capability",
      missing_capabilities: [{
        kind: "tool",
        reference: "veyra.tool.github.read@1.0.0",
        reason: "not selectable",
        proposal: { action: "quarantined_resource_draft", executable: false },
      }],
    });
    const api = apiFor({
      createFactorySession: vi.fn().mockResolvedValue(missing),
      generateFactoryBlueprint: vi.fn().mockResolvedValue(missing),
    });
    const user = userEvent.setup();
    render(<ThemeProvider><FactoryConversation api={api} projectId="project-1" locale="en" /></ThemeProvider>);
    await user.type(screen.getByRole("textbox"), "Triage GitHub issues");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("veyra.tool.github.read@1.0.0: not selectable")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create quarantined drafts" }));
    expect(api.createResourceDraft).toHaveBeenCalledWith({
      confirm: true,
      kind: "tool",
      requested_reference: "veyra.tool.github.read@1.0.0",
    });
    expect(await screen.findByText(/Wrote quarantined catalog drafts/)).toBeInTheDocument();
    expect(api.runAgent).toBeUndefined();
  });

  it("starts from a pending landing prompt", async () => {
    writePendingFactoryPrompt("Pending brief from landing");
    const api = apiFor();
    render(<ThemeProvider><FactoryConversation api={api} projectId="project-1" locale="en" /></ThemeProvider>);
    await waitFor(() => expect(api.createFactorySession).toHaveBeenCalledWith("project-1", { goal: "Pending brief from landing" }));
  });
});
