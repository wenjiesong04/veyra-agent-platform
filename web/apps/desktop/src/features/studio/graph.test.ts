import { describe, expect, it } from "vitest";
import type { AgentSource, AgentVersionSnapshot, ResourceDescriptor, WorkflowSource } from "@veyra/api-contracts";
import { agentCallRef } from "./agent-call";
import { attachFlowNodeOnEdge, autoLayoutCanvasNodes, defaultSpliceEdgeId, FLOW_NODE_ID_RE, flowNodeOutgoingPort, graphDiagnostics, insertFlowNodeOnEdge, isAgentSourceCandidate, isLoopAgent, isWorkflowSourceCandidate, newFlowNodeId, portHandleTop, repairInvalidNodeIds, shouldSplicePaletteItem, sourceWithGraph, toCanvas } from "./graph";

const source: AgentSource = { schema_version: "1.0", agentspec_version: "26.1", component_type: "Flow", agent_id: "agent-1", slug: "review", name: "Review", description: "", inputs: {}, outputs: {}, nodes: [{ id: "start", component_type: "Start" }, { id: "out", component_type: "Output", output_name: "result" }], transitions: [{ from: "start", port: "next", to: "out" }], extensions: { veyra: { runtime_profile: "guarded", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: true, checks: [] } } }, ui: { positions: { start: { x: 1, y: 2 }, out: { x: 3, y: 4 } } }, lock: {} };

const stopWorkflow: WorkflowSource = {
  schema_version: "1.0", component_type: "Workflow", workflow_id: "01900000-0000-7000-8000-000000000080",
  slug: "reviewed-delivery", name: "Reviewed delivery", description: "Deliver only after approval.",
  inputs: { result: "string" }, outputs: { result: "string" },
  nodes: [
    { id: "start", component_type: "Start" },
    { id: "confirm", component_type: "HumanApproval", prompt: "Deliver this reviewed report?" },
    { id: "out", component_type: "Output", output_name: "result" },
    { id: "stop", component_type: "Stop" },
  ],
  transitions: [
    { from: "start", port: "next", to: "confirm" },
    { from: "confirm", port: "approved", to: "out" },
    { from: "confirm", port: "rejected", to: "stop" },
  ],
  extensions: { veyra: { permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } },
  ui: { positions: { start: { x: 0, y: 0 }, confirm: { x: 200, y: 0 }, out: { x: 400, y: 0 }, stop: { x: 400, y: 160 } } },
  lock: {},
};

describe("Studio graph adapter", () => {
  it("round-trips positions and exact transition port handles", () => {
    const graph = toCanvas(source);
    const moved = graph.nodes.map((node) => node.id === "start" ? { ...node, position: { x: 44.5, y: 55.5 } } : node);
    const next = sourceWithGraph(source, moved, graph.edges);
    expect(next.ui.positions.start).toEqual({ x: 45, y: 56 });
    expect(next.transitions).toEqual([{ from: "start", port: "next", to: "out" }]);
  });

  it("imports and round-trips an explicit rejected-to-Stop Workflow without inventing an output", () => {
    const parsed: unknown = JSON.parse(JSON.stringify(stopWorkflow));
    expect(isWorkflowSourceCandidate(parsed)).toBe(true);
    expect(graphDiagnostics(stopWorkflow)).toEqual([]);
    const graph = toCanvas(stopWorkflow);
    expect(graph.nodes.find((node) => node.id === "stop")?.data.flow).toEqual({ id: "stop", component_type: "Stop" });
    expect(graph.edges.filter((edge) => edge.source === "stop")).toEqual([]);
    const moved = graph.nodes.map((node) => node.id === "stop" ? { ...node, position: { x: 520.4, y: 180.8 } } : node);
    const next = sourceWithGraph(stopWorkflow, moved, graph.edges);
    expect(next.nodes).toEqual(stopWorkflow.nodes);
    expect(next.transitions).toEqual(stopWorkflow.transitions);
    expect(next.ui.positions.stop).toEqual({ x: 520, y: 181 });
    expect(next.outputs).toEqual({ result: "string" });
    expect(next.extensions).toEqual(stopWorkflow.extensions);
    expect(graphDiagnostics(next)).toEqual([]);
  });

  it.each(["graph", "loop"] as const)("rejects Stop in an Agent %s even when the source parses", (executionKind) => {
    const agent: AgentSource = {
      ...source,
      inputs: stopWorkflow.inputs,
      outputs: stopWorkflow.outputs,
      nodes: stopWorkflow.nodes,
      transitions: stopWorkflow.transitions,
      extensions: { veyra: { ...source.extensions.veyra, execution_kind: executionKind, verification: { required: false, checks: [] } } },
    };
    expect(graphDiagnostics(agent)).toContainEqual({
      code: "node_context_invalid", params: { nodeId: "stop", componentType: "Stop", context: "Flow" },
    });
  });

  it("keeps Stop terminal instead of splicing it into a continuing edge", () => {
    expect(flowNodeOutgoingPort("Stop")).toBeNull();
    expect(shouldSplicePaletteItem("Stop", "component")).toBe(false);
    const invalid: WorkflowSource = {
      ...stopWorkflow,
      transitions: [...stopWorkflow.transitions, { from: "stop", port: "next", to: "out" }],
    };
    expect(graphDiagnostics(invalid)).toEqual(expect.arrayContaining([
      { code: "transition_invalid_port", params: { port: "next", nodeId: "stop" } },
      { code: "node_ports_incomplete", params: { nodeId: "stop" } },
    ]));
    const graph = toCanvas(invalid);
    expect(sourceWithGraph(invalid, graph.nodes, graph.edges).transitions).toEqual(stopWorkflow.transitions);
  });

  it("blocks persistence for incomplete local graphs", () => {
    expect(graphDiagnostics({ ...source, nodes: [{ id: "agent", component_type: "Agent" }], transitions: [] })).toEqual(expect.arrayContaining([
      { code: "start_count" }, { code: "output_missing" }, { code: "node_fields_missing", params: { nodeId: "agent", componentType: "Agent" } },
    ]));
  });

  it("requires Custom Component nodes to carry an exact pinned version lock", () => {
    const reference = "custom-component-1@1.0.0";
    const graph = {
      ...source,
      nodes: [
        { id: "start", component_type: "Start" as const },
        { id: "custom", component_type: "CustomComponent" as const, uses: reference },
        { id: "out", component_type: "Output" as const, output_name: "result" },
      ],
      transitions: [
        { from: "start", port: "next" as const, to: "custom" },
        { from: "custom", port: "next" as const, to: "out" },
      ],
      lock: {},
    };
    expect(graphDiagnostics(graph)).toContainEqual({ code: "custom_component_not_locked", params: { nodeId: "custom" } });
    expect(graphDiagnostics({ ...graph, lock: { [reference]: "a".repeat(64) } })).not.toContainEqual({ code: "custom_component_not_locked", params: { nodeId: "custom" } });
    expect(isAgentSourceCandidate(graph)).toBe(true);
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

  it("accepts compact artifact types and rich typed field descriptors", () => {
    expect(isAgentSourceCandidate({ ...source, inputs: { photo: "image" }, outputs: { caption: "string" } })).toBe(true);
    expect(isAgentSourceCandidate({
      ...source,
      inputs: { photo: { type: "artifact", artifact_kind: "image", multiple: true } },
      outputs: { caption: { type: "string", required: true } },
    })).toBe(true);
    expect(isAgentSourceCandidate({ ...source, inputs: { photo: "blob" }, outputs: { caption: "string" } })).toBe(false);
    expect(isAgentSourceCandidate({ ...source, extensions: { veyra: { ...source.extensions.veyra, interaction_mode: "chat" } } })).toBe(true);
    expect(isAgentSourceCandidate({ ...source, extensions: { veyra: { ...source.extensions.veyra, interaction_mode: "voice" } } })).toBe(false);
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

  it("renders a loop Agent as a capability map instead of a Start-Output DAG", () => {
    const loop: AgentSource = {
      ...source,
      name: "Translation Agent",
      outputs: { translation: "string" },
      nodes: [
        { id: "start", component_type: "Start" },
        { id: "model", component_type: "Model", model_ref: "model.primary", system_prompt: "Translate." },
        { id: "output", component_type: "Output", output_name: "translation" },
      ],
      transitions: [
        { from: "start", port: "next", to: "model" },
        { from: "model", port: "next", to: "output" },
      ],
      extensions: { veyra: { ...source.extensions.veyra, execution_kind: "loop", instructions: "Translate.", max_turns: 8 } },
      ui: {
        positions: { start: { x: 0, y: 80 }, model: { x: 240, y: 80 }, output: { x: 480, y: 80 } },
        bindings: { bind_tool1: { kind: "tool", reference: "veyra.tool.web.search@1.0.0", x: 480, y: 130 } },
      },
      lock: { "veyra.tool.web.search@1.0.0": "a".repeat(64) },
    };
    expect(isLoopAgent(loop)).toBe(true);
    const graph = toCanvas(loop);
    expect(graph.nodes.some((node) => node.data.flow?.component_type === "Start")).toBe(false);
    expect(graph.nodes.some((node) => node.data.flow?.component_type === "Output")).toBe(false);
    expect(graph.nodes.some((node) => node.data.flow?.component_type === "Model")).toBe(true);
    expect(graph.nodes.some((node) => node.id === "bind_tool1")).toBe(true);
    const next = sourceWithGraph(loop, graph.nodes, graph.edges);
    expect(next.nodes.map((node) => node.id)).toEqual(["start", "model", "output"]);
    expect(next.transitions).toEqual(loop.transitions);
    expect(graphDiagnostics(loop)).toEqual([]);
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

  it("centers the default canvas note above the graph and keeps it optional", () => {
    const noted = {
      ...source,
      ui: { positions: { start: { x: 0, y: 80 }, out: { x: 600, y: 80 } }, notes: { note_intro: { x: 0, y: -220, text: "说明", color: "amber" as const, width: 420 } } },
    };
    const graph = toCanvas(noted);
    const note = graph.nodes.find((node) => node.id === "note_intro");
    const flowNodes = graph.nodes.filter((node) => node.data.flow);
    const flowY = Math.min(...flowNodes.map((node) => node.position.y));
    const graphLeft = Math.min(...flowNodes.map((node) => node.position.x));
    const graphRight = Math.max(...flowNodes.map((node) => node.position.x + Number(node.style?.width)));
    expect(note?.position.y).toBeLessThan(flowY);
    expect(note?.position.x).toBe(Math.round((graphLeft + graphRight - 420) / 2));
    expect(note?.data.note?.manual_position).toBe(false);
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
    const next = sourceWithGraph(noted, graph.nodes.map((node) => node.id === "note_intro" ? { ...node, position: { x: 40.4, y: 80.6 }, data: { ...node.data, note: { text: "Moved", color: "teal" as const, width: 240, manual_position: true } } } : node), graph.edges);
    expect(next.nodes.map((node) => node.id)).toEqual(["start", "out"]);
    expect(next.ui.notes?.note_intro).toEqual({ x: 40, y: 81, text: "Moved", color: "teal", width: 240, manual_position: true });
    expect(toCanvas(next).nodes.find((node) => node.id === "note_intro")?.position).toEqual({ x: 40, y: 81 });
  });

  it("preserves legacy custom default-note coordinates as a manual placement", () => {
    const noted = {
      ...source,
      ui: { positions: source.ui.positions, notes: { note_intro: { x: 840, y: -30, text: "User placed", width: 320 } } },
    };
    expect(toCanvas(noted).nodes.find((node) => node.id === "note_intro")).toMatchObject({
      position: { x: 840, y: -30 },
      data: { note: { manual_position: true } },
    });
  });

  it("auto-layouts execution nodes while preserving a manually placed default note", () => {
    const noted = {
      ...source,
      ui: {
        positions: source.ui.positions,
        notes: { note_intro: { x: 730, y: -90, text: "Keep here", width: 420, manual_position: true } },
      },
    };
    const initial = toCanvas(noted);
    const next = autoLayoutCanvasNodes(initial.nodes, initial.edges);
    expect(next.find((node) => node.id === "start")?.position.x).toBe(0);
    expect(next.find((node) => node.id === "out")?.position.x).toBeGreaterThan(0);
    expect(next.find((node) => node.id === "note_intro")?.position).toEqual({ x: 730, y: -90 });
    expect(sourceWithGraph(noted, next, initial.edges).ui.notes?.note_intro).toMatchObject({
      x: 730,
      y: -90,
      manual_position: true,
    });
  });

  it("uses the same default-note layout behavior for Workflow canvases", () => {
    const workflow: WorkflowSource = {
      schema_version: "1.0",
      component_type: "Workflow",
      workflow_id: "01900000-0000-7000-8000-000000000099",
      slug: "review-path",
      name: "Review path",
      description: "",
      inputs: {},
      outputs: { result: "string" },
      nodes: [
        { id: "start", component_type: "Start" },
        { id: "call", component_type: "AgentCall", agent_ref: "01900000-0000-7000-8000-000000000098@1.0.0" },
        { id: "out", component_type: "Output", output_name: "result" },
      ],
      transitions: [
        { from: "start", port: "next", to: "call" },
        { from: "call", port: "next", to: "out" },
      ],
      extensions: { veyra: { permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } },
      ui: { positions: {}, notes: { note_intro: { x: 0, y: -220, text: "Workflow note", width: 420, manual_position: false } } },
      lock: {},
    };
    const graph = toCanvas(workflow);
    const note = graph.nodes.find((node) => node.id === "note_intro");
    const flow = graph.nodes.filter((node) => node.data.flow);
    const minY = Math.min(...flow.map((node) => node.position.y));
    expect(note?.position.y).toBeLessThan(minY);
    const saved = sourceWithGraph(workflow, graph.nodes, graph.edges);
    expect(saved.ui.notes?.note_intro).toMatchObject({ manual_position: false, width: 420 });
  });

  it("accepts Agent output slugs with hyphens in Workflow call mappings", () => {
    const version: AgentVersionSnapshot = {
      agent_id: "01900000-0000-7000-8000-000000000098",
      version_id: "01900000-0000-7000-8000-000000000099",
      source_hash: "a".repeat(64), behavior_hash: "b".repeat(64), created_at: "2026-09-06T00:00:00Z",
      source: { ...source, agent_id: "01900000-0000-7000-8000-000000000098", inputs: { image: "image" }, outputs: { "model-known": "boolean", result: "string" } },
    };
    const ref = agentCallRef(version);
    const workflow: WorkflowSource = {
      schema_version: "1.0", component_type: "Workflow", workflow_id: "01900000-0000-7000-8000-000000000090",
      slug: "package-design", name: "Package design", description: "", inputs: { image: "image" }, outputs: { result: "string" },
      nodes: [
        { id: "start", component_type: "Start" },
        { id: "identify", component_type: "AgentCall", agent_ref: ref, input_mapping: { image: "image" }, output_mapping: { "model-known": "model_known", result: "result" } },
        { id: "out", component_type: "Output", output_name: "result" },
      ],
      transitions: [{ from: "start", port: "next", to: "identify" }, { from: "identify", port: "next", to: "out" }],
      extensions: { veyra: { permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } },
      ui: { positions: {} }, lock: { [ref]: version.source_hash },
    };
    expect(graphDiagnostics(workflow, [], [version])).not.toContainEqual({ code: "agent_mapping_invalid", params: { nodeId: "identify" } });
    const invalid = { ...workflow, nodes: workflow.nodes.map((node) => node.id === "identify" ? { ...node, output_mapping: { "model-known": "model-known", result: "result" } } : node) };
    expect(graphDiagnostics(invalid, [], [version])).toContainEqual({ code: "agent_mapping_invalid", params: { nodeId: "identify" } });
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
    expect(portHandleTop(0, 1)).toBe("50%");
    expect(portHandleTop(0, 0)).toBe("50%");
    expect(portHandleTop(0, 2)).toBe("calc(50% - 9px)");
    expect(portHandleTop(1, 2)).toBe("calc(50% + 9px)");
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
