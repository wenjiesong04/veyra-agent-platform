import { describe, expect, it } from "vitest";
import type { AgentVersionSnapshot, WorkflowSource } from "@veyra/api-contracts";
import { agentCallRef, agentIdFromRef, bindWorkflowAgentCall, latestAgentVersion, repairAgentCallMappings } from "./agent-call";

const agent: AgentVersionSnapshot = {
  agent_id: "01900000-0000-7000-8000-000000000001",
  version_id: "01900000-0000-7000-8000-000000000011",
  source_hash: "a".repeat(64), behavior_hash: "b".repeat(64), created_at: "2026-09-06T00:00:00Z",
  source: { schema_version: "1.0", agentspec_version: "26.1", component_type: "Flow", agent_id: "01900000-0000-7000-8000-000000000001", slug: "reviewer", name: "Reviewer", description: "Review", inputs: { prompt: "string" }, outputs: { result: "string" }, nodes: [], transitions: [], extensions: { veyra: { runtime_profile: "veyra-runtime-profile/1", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } }, ui: { positions: {} }, lock: {} },
};

const source: WorkflowSource = {
  schema_version: "1.0",
  component_type: "Workflow",
  workflow_id: "01900000-0000-7000-8000-000000000002",
  slug: "path",
  name: "Path",
  description: "A blank Workflow that orchestrates Agents.",
  inputs: { prompt: "string" },
  outputs: { result: "string" },
  nodes: [
    { id: "start", component_type: "Start" },
    { id: "call", component_type: "AgentCall" },
    { id: "out", component_type: "Output", output_name: "result" },
  ],
  transitions: [
    { from: "start", port: "next", to: "call" },
    { from: "call", port: "next", to: "out" },
  ],
  extensions: { veyra: { permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } },
  ui: { positions: { start: { x: 0, y: 0 }, call: { x: 1, y: 0 }, out: { x: 2, y: 0 } } },
  lock: {},
};

describe("Workflow AgentCall binding", () => {
  it("writes agent_id@immutable_version_id and locks the version source hash", () => {
    expect(agentCallRef(agent)).toBe(`${agent.agent_id}@${agent.version_id}`);
    expect(agentIdFromRef(`${agent.agent_id}@${agent.version_id}`)).toBe(agent.agent_id);
    const next = bindWorkflowAgentCall(source, "call", agent);
    expect(next.nodes.find((node) => node.id === "call")?.agent_ref).toBe(`${agent.agent_id}@${agent.version_id}`);
    expect(next.lock[`${agent.agent_id}@${agent.version_id}`]).toBe(agent.source_hash);
  });

  it("drops unused AgentCall locks when the target changes", () => {
    const other: AgentVersionSnapshot = { ...agent, version_id: "01900000-0000-7000-8000-000000000099", source_hash: "b".repeat(64) };
    const bound = bindWorkflowAgentCall(source, "call", agent);
    const next = bindWorkflowAgentCall(bound, "call", other);
    expect(Object.keys(next.lock)).toEqual([`${other.agent_id}@${other.version_id}`]);
  });
  it("does not overwrite a different lock for an existing immutable identity", () => {
    const bound = bindWorkflowAgentCall(source, "call", agent);
    expect(() => bindWorkflowAgentCall(bound, "call", { ...agent, source_hash: "c".repeat(64) })).toThrow("existing lock");
    expect(bound.lock[agentCallRef(agent)]).toBe(agent.source_hash);
    expect(agentIdFromRef(`${agent.agent_id}@1.0.0`)).toBeNull();
    expect(latestAgentVersion([
      { ...agent, version_id: "01900000-0000-7000-8000-000000000010", created_at: "2026-09-01T00:00:00Z" },
      agent,
    ])?.version_id).toBe(agent.version_id);
  });

  it("preserves upstream variables, output aliases and unrelated locks when upgrading a version", () => {
    const bound = bindWorkflowAgentCall(source, "call", agent);
    const toolRef = "veyra.tool.math.calculate@1.0.0";
    const mapped: WorkflowSource = {
      ...bound,
      nodes: [
        { id: "upstream", component_type: "AgentCall", output_mapping: { text: "analyze_analysis" } },
        ...bound.nodes.map((node) => node.id === "call" ? { ...node, input_mapping: { prompt: "analyze_analysis" }, output_mapping: { result: "review_final_report" } } : node),
      ],
      lock: { ...bound.lock, [toolRef]: "d".repeat(64) },
    };
    const newer = { ...agent, version_id: "01900000-0000-7000-8000-000000000012", source_hash: "c".repeat(64) };
    const upgraded = bindWorkflowAgentCall(mapped, "call", newer);
    expect(upgraded.nodes.find((node) => node.id === "call")?.input_mapping).toEqual({ prompt: "analyze_analysis" });
    expect(upgraded.nodes.find((node) => node.id === "call")?.output_mapping).toEqual({ result: "review_final_report" });
    expect(upgraded.lock[toolRef]).toBe("d".repeat(64));
    expect(upgraded.lock[agentCallRef(agent)]).toBeUndefined();
    expect(upgraded.lock[agentCallRef(newer)]).toBe(newer.source_hash);
  });

  it("maps a uniquely available Workflow input when the Agent parameter uses a different name", () => {
    const translation: AgentVersionSnapshot = { ...agent, source: { ...agent.source, inputs: { request: "string" } } };
    const next = bindWorkflowAgentCall(source, "call", translation);
    expect(next.nodes.find((node) => node.id === "call")?.input_mapping).toEqual({ request: "prompt" });
    expect(next.nodes.find((node) => node.id === "call")?.output_mapping).toEqual({ result: "result" });
    const broken = { ...next, nodes: next.nodes.map((node) => node.id === "call" ? { ...node, input_mapping: { request: "" } } : node) };
    expect(repairAgentCallMappings(broken).nodes.find((node) => node.id === "call")?.input_mapping).toEqual({ request: "prompt" });
  });
});
