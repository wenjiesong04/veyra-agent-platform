import { describe, expect, it } from "vitest";
import type { AgentSource, ResourceDescriptor } from "@veyra/api-contracts";
import { attachFlowNodeOnEdge, defaultSpliceEdgeId, FLOW_NODE_ID_RE, graphDiagnostics, insertFlowNodeOnEdge, isAgentSourceCandidate, newFlowNodeId, portHandleTop, repairInvalidNodeIds, shouldSplicePaletteItem, sourceWithGraph, toCanvas } from "./graph";

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

  it("round-trips catalog bindings without turning them into Flow nodes", () => {
    const bound = {
      ...source,
      extensions: { veyra: { ...source.extensions.veyra, skill_refs: ["veyra.skill.research-brief@1.0.0"] } },
      lock: { "veyra.skill.research-brief@1.0.0": "a".repeat(64) },
      ui: { positions: source.ui.positions, bindings: { bind_skill: { kind: "skill" as const, reference: "veyra.skill.research-brief@1.0.0", x: 40, y: 80 } } },
    };
    const graph = toCanvas(bound);
    expect(graph.nodes.some((node) => node.id === "bind_skill" && node.type === "bindingNode")).toBe(true);
    const next = sourceWithGraph(bound, graph.nodes.map((node) => node.id === "bind_skill" ? { ...node, position: { x: 99.4, y: 12.6 } } : node), graph.edges);
    expect(next.nodes.map((node) => node.id)).toEqual(["start", "out"]);
    expect(next.ui.bindings?.bind_skill).toEqual({ kind: "skill", reference: "veyra.skill.research-brief@1.0.0", x: 99, y: 13 });
    expect(next.extensions.veyra.skill_refs).toEqual(["veyra.skill.research-brief@1.0.0"]);
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

  it("prunes unused Workflow AgentCall locks when the node is removed", () => {
    const ref = "01900000-0000-7000-8000-000000000001@1.0.0";
    const workflow = {
      schema_version: "1.0" as const,
      component_type: "Workflow" as const,
      workflow_id: "01900000-0000-7000-8000-000000000002",
      slug: "path",
      name: "Path",
      description: "A blank Workflow that orchestrates Agents.",
      inputs: { prompt: "string" },
      outputs: { result: "string" },
      nodes: [
        { id: "start", component_type: "Start" as const },
        { id: "call", component_type: "AgentCall" as const, agent_ref: ref },
        { id: "out", component_type: "Output" as const, output_name: "result" },
      ],
      transitions: [
        { from: "start", port: "next" as const, to: "call" },
        { from: "call", port: "next" as const, to: "out" },
      ],
      extensions: { veyra: { permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } },
      ui: { positions: { start: { x: 0, y: 0 }, call: { x: 1, y: 0 }, out: { x: 2, y: 0 } } },
      lock: { [ref]: "a".repeat(64) },
    };
    const graph = toCanvas(workflow);
    const withoutCall = sourceWithGraph(workflow, graph.nodes.filter((node) => node.id !== "call"), graph.edges.filter((edge) => edge.source !== "call" && edge.target !== "call"));
    expect(withoutCall.lock).toEqual({});
  });

  it("treats Model like Agent and AgentCall like a required agent_ref", () => {
    expect(graphDiagnostics({
      ...source,
      nodes: [{ id: "model", component_type: "Model" }],
      transitions: [],
    })).toEqual(expect.arrayContaining([
      { code: "node_fields_missing", params: { nodeId: "model", componentType: "Model" } },
    ]));
    const callProblems = graphDiagnostics({
      ...source,
      nodes: [{ id: "call", component_type: "AgentCall" }],
      transitions: [],
    });
    expect(callProblems).toEqual(expect.arrayContaining([
      { code: "agent_ref_invalid", params: { nodeId: "call" } },
    ]));
    expect(callProblems.some((item) => item.code === "node_fields_missing" && item.params?.nodeId === "call")).toBe(false);
    expect(callProblems.some((item) => item.code === "agent_lock_mismatch" && item.params?.nodeId === "call")).toBe(false);
  });

  it("shows semantic labels on canvas nodes and drops labels for deleted nodes", () => {
    const labelled = {
      ...source,
      ui: { positions: source.ui.positions, labels: { start: "入口", out: "结果", missing: "gone" } },
    };
    const graph = toCanvas(labelled);
    expect(graph.nodes.find((node) => node.id === "start")?.data.title).toBe("入口");
    const next = sourceWithGraph(labelled, graph.nodes, graph.edges);
    expect(next.ui.labels).toEqual({ start: "入口", out: "结果" });
  });

  it("keeps a default canvas note above the flow and valid after deletion", () => {
    const noted = {
      ...source,
      ui: { positions: { start: { x: 0, y: 80 }, out: { x: 240, y: 80 } }, notes: { note_intro: { x: 0, y: -220, text: "说明", color: "amber" as const, width: 280 } } },
    };
    const graph = toCanvas(noted);
    const note = graph.nodes.find((node) => node.id === "note_intro");
    const flowY = Math.min(...graph.nodes.filter((node) => node.data.flow).map((node) => node.position.y));
    expect(note?.position.y).toBeLessThan(flowY);
    const withoutNote = sourceWithGraph(noted, graph.nodes.filter((node) => node.id !== "note_intro"), graph.edges);
    expect(withoutNote.ui.notes).toBeUndefined();
    expect(withoutNote.nodes.map((node) => node.id)).toEqual(["start", "out"]);
  });

  it("round-trips canvas notes without turning them into Flow nodes", () => {
    const noted = {
      ...source,
      ui: { positions: source.ui.positions, notes: { note_intro: { x: 12, y: 24, text: "Hello", color: "violet" as const, width: 240 } } },
    };
    const graph = toCanvas(noted);
    expect(graph.nodes.some((node) => node.id === "note_intro" && node.type === "noteNode")).toBe(true);
    const next = sourceWithGraph(noted, graph.nodes.map((node) => node.id === "note_intro" ? { ...node, position: { x: 40.4, y: 80.6 }, data: { ...node.data, note: { text: "Moved", color: "teal" as const, width: 240 } } } : node), graph.edges);
    expect(next.nodes.map((node) => node.id)).toEqual(["start", "out"]);
    expect(next.ui.notes?.note_intro).toEqual({ x: 40, y: 81, text: "Moved", color: "teal", width: 240 });
  });

  it("inserts a Flow node by splitting an existing edge", () => {
    const graph = toCanvas(source);
    const inserted = insertFlowNodeOnEdge(graph.nodes, graph.edges, "start:next:out", { id: "call", type: "agentNode", position: { x: 0, y: 0 }, data: { flow: { id: "call", component_type: "AgentCall" } } }, "next");
    expect(inserted).not.toBeNull();
    expect(inserted?.edges.map((edge) => edge.id)).toEqual(["start:next:call", "call:next:out"]);
    expect(inserted?.nodes.find((node) => node.id === "call")?.position).toEqual({ x: 2, y: 3 });
    const next = sourceWithGraph(source, inserted!.nodes, inserted!.edges);
    expect(next.nodes.map((node) => node.id)).toEqual(["start", "out", "call"]);
    expect(next.transitions).toEqual([{ from: "start", port: "next", to: "call" }, { from: "call", port: "next", to: "out" }]);
  });

  it("centers a single outgoing port and fans multiple ports around mid-height", () => {
    expect(portHandleTop(0, 1)).toBe(50);
    expect(portHandleTop(0, 0)).toBe(50);
    expect(portHandleTop(0, 2)).toBe(36);
    expect(portHandleTop(1, 2)).toBe(64);
  });

  it("picks the unique edge into Output as the default splice target", () => {
    const blank = toCanvas(source);
    expect(defaultSpliceEdgeId(blank.nodes, blank.edges)).toBe("start:next:out");
    const inserted = insertFlowNodeOnEdge(blank.nodes, blank.edges, "start:next:out", { id: "call", type: "agentNode", position: { x: 0, y: 0 }, data: { flow: { id: "call", component_type: "AgentCall" } } }, "next");
    expect(defaultSpliceEdgeId(inserted!.nodes, inserted!.edges)).toBe("call:next:out");
  });

  it("splices single-exit Agent components onto the flow but not Start, Output, or branches", () => {
    expect(shouldSplicePaletteItem("Model", "component")).toBe(true);
    expect(shouldSplicePaletteItem("Tool", "tool")).toBe(true);
    expect(shouldSplicePaletteItem("Start", "component")).toBe(false);
    expect(shouldSplicePaletteItem("Output", "component")).toBe(false);
    expect(shouldSplicePaletteItem("HumanApproval", "component")).toBe(false);
    expect(shouldSplicePaletteItem("Start", "note")).toBe(false);
  });

  it("attaches an existing disconnected node onto the default splice edge", () => {
    const graph = toCanvas(source);
    const disconnected = [...graph.nodes, { id: "call", type: "agentNode", position: { x: 40, y: 80 }, data: { flow: { id: "call", component_type: "AgentCall" as const } } }];
    const attached = attachFlowNodeOnEdge(disconnected, graph.edges, "start:next:out", "call", "next");
    expect(attached?.edges.map((edge) => edge.id)).toEqual(["start:next:call", "call:next:out"]);
    expect(attached?.nodes.filter((node) => node.id === "call")).toHaveLength(1);
  });

  it("generates Flow node ids without hyphens so they pass the contract", () => {
    expect(newFlowNodeId("AgentCall")).toMatch(FLOW_NODE_ID_RE);
    expect(newFlowNodeId("AgentCall")).not.toContain("-");
  });

  it("rewrites hyphenated canvas ids into contract-safe node ids", () => {
    const broken = {
      ...source,
      nodes: [...source.nodes, { id: "agentcall-7cb9c027", component_type: "AgentCall" as const, output_mapping: { result: "agentcall-7cb9c027_result" } }],
      transitions: [...source.transitions, { from: "agentcall-7cb9c027" as const, port: "next" as const, to: "out" }],
      ui: { positions: { ...source.ui.positions, "agentcall-7cb9c027": { x: 8, y: 8 } } },
    };
    const repaired = repairInvalidNodeIds(broken);
    expect(repaired.nodes.map((node) => node.id)).toEqual(["start", "out", "agentcall_7cb9c027"]);
    expect(repaired.transitions).toContainEqual({ from: "agentcall_7cb9c027", port: "next", to: "out" });
    expect(repaired.ui.positions.agentcall_7cb9c027).toEqual({ x: 8, y: 8 });
    expect(repaired.nodes.find((node) => node.id === "agentcall_7cb9c027")?.output_mapping).toEqual({ result: "agentcall_7cb9c027_result" });
  });
});
