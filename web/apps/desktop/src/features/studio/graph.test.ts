import { describe, expect, it } from "vitest";
import type { AgentSource, ResourceDescriptor } from "@veyra/api-contracts";
import { graphDiagnostics, isAgentSourceCandidate, sourceWithGraph, toCanvas } from "./graph";

const source: AgentSource = { schema_version: "1.0", agentspec_version: "26.1", component_type: "Flow", agent_id: "agent-1", slug: "review", name: "Review", description: "", inputs: {}, outputs: {}, nodes: [{ id: "start", component_type: "Start" }, { id: "out", component_type: "Output", output_name: "result" }], transitions: [{ from: "start", port: "next", to: "out" }], extensions: { veyra: { runtime_profile: "guarded", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: true, checks: [] } } }, ui: { positions: { start: { x: 1, y: 2 }, out: { x: 3, y: 4 } } }, lock: {} };

describe("Studio graph adapter", () => {
  it("round-trips positions and exact transition port handles", () => {
    const graph = toCanvas(source);
    const moved = graph.nodes.map((node) => node.id === "start" ? { ...node, position: { x: 44.5, y: 55.5 } } : node);
    const next = sourceWithGraph(source, moved, graph.edges);
    expect(next.ui.positions.start).toEqual({ x: 45, y: 56 });
    expect(next.transitions).toEqual([{ from: "start", port: "next", to: "out" }]);
  });

  it("blocks persistence for incomplete local graphs", () => {
    expect(graphDiagnostics({ ...source, nodes: [{ id: "agent", component_type: "Agent" }], transitions: [] })).toEqual(expect.arrayContaining([
      { code: "start_count" }, { code: "output_missing" }, { code: "node_fields_missing", params: { nodeId: "agent", componentType: "Agent" } },
    ]));
  });

  it("serializes a connection from a newly added canvas node and removes a deleted edge", () => {
    const graph = toCanvas(source);
    const agent = { id: "agent", type: "agentNode", position: { x: 100, y: 100 }, data: { flow: { id: "agent", component_type: "Agent" as const, model_ref: "model.primary", system_prompt: "Review" } } };
    const withConnection = sourceWithGraph(source, [...graph.nodes, agent], [...graph.edges, { id: "agent:next:out", source: "agent", target: "out", sourceHandle: "next" }]);
    expect(withConnection.nodes).toContainEqual(agent.data.flow);
    expect(withConnection.transitions).toContainEqual({ from: "agent", port: "next", to: "out" });
    expect(sourceWithGraph(withConnection, toCanvas(withConnection).nodes, []).transitions).toEqual([]);
  });

  it("rejects structurally incomplete parsed source before graph diagnostics can read it", () => {
    expect(isAgentSourceCandidate({ schema_version: "1.0", nodes: [] })).toBe(false);
    expect(isAgentSourceCandidate({ ...source, extensions: { veyra: { runtime_profile: "guarded" } } })).toBe(false);
    expect(isAgentSourceCandidate(source)).toBe(true);
  });

  it("blocks saving a write tool until a HumanApproval node exists", () => {
    const write: ResourceDescriptor = {
      schema_version: "1.0",
      resource_id: "veyra.tool.filesystem.write",
      kind: "tool",
      version: "1.0.0",
      reference: "veyra.tool.filesystem.write@1.0.0",
      name: "Filesystem Write",
      description: "Write",
      origin: "builtin",
      content_hash: "c".repeat(64),
      availability: "ready",
      factory_selectable: true,
      runtime_status: "supported",
      required_permissions: { network_hosts: [], tools: ["veyra.tool.filesystem.write"], filesystem_read_roots: [], filesystem_write_roots: ["project"], shell_workspace_only: false },
      tags: [],
      spec: { approval_required: true },
    };
    const graph = {
      ...source,
      nodes: [
        { id: "start", component_type: "Start" as const },
        { id: "write", component_type: "Tool" as const, uses: write.reference },
        { id: "out", component_type: "Output" as const, output_name: "result" },
      ],
      outputs: { result: "string" },
      extensions: { veyra: { runtime_profile: "guarded", secret_refs: [], permissions: { network_hosts: [], tools: ["veyra.tool.filesystem.write"] }, verification: { required: false, checks: [] } } },
      lock: { [write.reference]: write.content_hash },
      ui: { positions: { start: { x: 0, y: 0 }, write: { x: 1, y: 0 }, out: { x: 2, y: 0 } } },
    };
    expect(graphDiagnostics(graph, [write])).toEqual(expect.arrayContaining([
      { code: "write_requires_approval", params: { nodeId: "write" } },
    ]));
  });
});
