import { describe, expect, it } from "vitest";
import type { AgentSource } from "@veyra/api-contracts";
import { graphDiagnostics, sourceWithGraph, toCanvas } from "./graph";

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
    expect(graphDiagnostics({ ...source, nodes: [{ id: "agent", component_type: "Agent" }], transitions: [] })).toEqual(expect.arrayContaining(["Exactly one Start node is required.", "An Output node is required.", "agent is missing required Agent fields."]));
  });
});
