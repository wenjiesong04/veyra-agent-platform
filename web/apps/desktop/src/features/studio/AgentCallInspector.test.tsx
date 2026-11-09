import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
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
afterEach(cleanup);

describe("AgentCallInspector", () => {
  it("preserves an existing intermediate value when opened and refreshed", async () => {
    const current = { ...node, agent_ref: `${version.agent_id}@${version.version_id}`, input_mapping: { prompt: "analyze_analysis" } };
    const onBind = vi.fn();
    const onMapping = vi.fn();
    const listAgentVersions = vi.fn().mockResolvedValue({ schema_version: "1.0", versions: [version] });
    const api = { listAgentVersions } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    render(<ThemeProvider><AgentCallInspector node={current} agents={[agent]} api={api} projectId="project-1" zh workflowInputs={["rawmaterials"]} onBind={onBind} onMapping={onMapping} /></ThemeProvider>);
    const mapping = await screen.findByRole("combobox", { name: "参数 prompt" });
    expect(mapping).toHaveValue("analyze_analysis");
    await user.click(screen.getByRole("button", { name: "刷新版本" }));
    await waitFor(() => expect(listAgentVersions).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByRole("button", { name: "刷新版本" })).toBeEnabled());
    expect(mapping).toHaveValue("analyze_analysis");
    expect(onMapping).not.toHaveBeenCalled();
    expect(onBind).not.toHaveBeenCalled();
  });

  it("binds a different immutable version only after explicit selection", async () => {
    const newer = { ...version, version_id: "01900000-0000-7000-8000-000000000012", source_hash: "c".repeat(64) };
    const onBind = vi.fn();
    const onMapping = vi.fn();
    const api = { listAgentVersions: vi.fn().mockResolvedValue({ schema_version: "1.0", versions: [version, newer] }) } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    render(<ThemeProvider><AgentCallInspector node={{ ...node, agent_ref: `${version.agent_id}@${version.version_id}` }} agents={[agent]} api={api} projectId="project-1" zh onBind={onBind} onMapping={onMapping} /></ThemeProvider>);
    const selection = await screen.findByRole("combobox", { name: "不可变版本" });
    await waitFor(() => expect(selection).toBeEnabled());
    expect(onBind).not.toHaveBeenCalled();
    await user.selectOptions(selection, newer.version_id);
    expect(onBind).toHaveBeenCalledWith(newer);
    expect(onMapping).not.toHaveBeenCalled();
  });

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
