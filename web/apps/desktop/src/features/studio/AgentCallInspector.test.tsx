import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { AgentVersionSnapshot, FlowNode, ProjectAgentRecord } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { AgentCallInspector } from "./AgentCallInspector";

const agent: ProjectAgentRecord = {
  agent_id: "01900000-0000-7000-8000-000000000001",
  slug: "translation",
  name: "translation",
  description: "",
  pinned: false,
  source_path: "agents/translation/agent.vagent.yaml",
  source_file_hash: "file",
};

const version: AgentVersionSnapshot = {
  agent_id: agent.agent_id,
  version_id: "01900000-0000-7000-8000-000000000011",
  source_hash: "a".repeat(64),
  behavior_hash: "b".repeat(64),
  created_at: "2026-09-06T00:00:00Z",
  source: {
    schema_version: "1.0", agentspec_version: "26.1", component_type: "Flow", agent_id: agent.agent_id, slug: "translation", name: "translation", description: "",
    inputs: { prompt: "string" }, outputs: { result: "string" }, nodes: [], transitions: [],
    extensions: { veyra: { runtime_profile: "veyra-runtime-profile/1", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } },
    ui: { positions: {} }, lock: {},
  },
};

const node: FlowNode = { id: "call", component_type: "AgentCall" };

describe("AgentCallInspector", () => {
  it("binds the latest committed version when an Agent is selected", async () => {
    const onBind = vi.fn();
    const api = {
      listAgentVersions: vi.fn().mockResolvedValue({ schema_version: "1.0", versions: [version] }),
    } as unknown as LocalProjectApi;
    render(
      <ThemeProvider storageKey="agent-call-inspector-theme">
        <AgentCallInspector node={node} agents={[agent]} api={api} projectId="project-1" zh initialAgentId={agent.agent_id} onBind={onBind} onMapping={vi.fn()} />
      </ThemeProvider>,
    );
    await waitFor(() => expect(onBind).toHaveBeenCalledWith(version));
  });

  it("sends the user to commit a version instead of pretending a draft can be called", async () => {
    const onOpenAgent = vi.fn();
    const api = {
      listAgentVersions: vi.fn().mockResolvedValue({ schema_version: "1.0", versions: [] }),
    } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    render(
      <ThemeProvider storageKey="agent-call-inspector-theme">
        <AgentCallInspector node={node} agents={[agent]} api={api} projectId="project-1" zh initialAgentId={agent.agent_id} onBind={vi.fn()} onMapping={vi.fn()} onOpenAgent={onOpenAgent} />
      </ThemeProvider>,
    );
    await user.click(await screen.findByRole("button", { name: "去提交版本" }));
    expect(onOpenAgent).toHaveBeenCalledWith(agent.agent_id);
    expect(screen.getByText(/还没有已提交版本/)).toBeInTheDocument();
  });
});
