import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FactorySession, FactoryStatus } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { FactoryConversation } from "./factory-conversation";

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
    blueprint: { schema_version: "1.0", goal: "Brief" },
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
    getDraft: vi.fn(),
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
    ...overrides,
  } as LocalProjectApi;
}

afterEach(() => cleanup());

describe("FactoryConversation", () => {
  it("collects a requirement, generates a Blueprint, and creates a Draft without running", async () => {
    const api = apiFor();
    const user = userEvent.setup();
    render(<ThemeProvider><FactoryConversation api={api} projectId="project-1" locale="en" /></ThemeProvider>);

    expect(await screen.findByText("Kimi K3 is configured for Draft generation only.")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox"), "Write a research brief");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(api.createFactorySession).toHaveBeenCalledWith("project-1", { goal: "Write a research brief" });

    await user.click(await screen.findByRole("button", { name: "Generate Blueprint" }));
    expect(api.generateFactoryBlueprint).toHaveBeenCalledWith("project-1", "session-1");
    expect(await screen.findByText("veyra.skill.research-brief@1.0.0")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Create Draft" }));
    expect(api.applyFactoryDraft).toHaveBeenCalledWith("project-1", "session-1", { confirm: true });
    expect(await screen.findByRole("link", { name: "Open Studio" })).toHaveAttribute("href", "#/projects/project-1/agents/agent-1/design");
    expect(api.runAgent).toBeUndefined();
  });
});
