import { describe, expect, it } from "vitest";
import { blueprintGraph, revisionFactoryGoal } from "./factory-blueprint";

describe("blueprintGraph", () => {
  it("reads nodes and transitions from a Factory Blueprint object", () => {
    const graph = blueprintGraph({
      schema_version: "1.0",
      nodes: [
        { id: "start", component_type: "Start" },
        { id: "analyze", component_type: "Agent" },
        "skip",
      ],
      transitions: [
        { from: "start", port: "next", to: "analyze" },
        { from: "analyze", to: "output" },
      ],
    });
    expect(graph.nodes).toEqual([
      { id: "start", component_type: "Start" },
      { id: "analyze", component_type: "Agent" },
    ]);
    expect(graph.transitions).toEqual([
      { from: "start", port: "next", to: "analyze" },
      { from: "analyze", port: "next", to: "output" },
    ]);
  });

  it("returns empty collections when the Blueprint is missing", () => {
    expect(blueprintGraph(null)).toEqual({ nodes: [], transitions: [] });
  });
});

describe("revisionFactoryGoal", () => {
  it("keeps the user request and names the parent Agent", () => {
    const goal = revisionFactoryGoal({
      agentName: "Reviewer",
      agentId: "agent-1",
      description: "Reviews a request.",
      prompt: "Add an approval before writing files.",
      locale: "en",
    });
    expect(goal).toContain("Reviewer");
    expect(goal).toContain("agent-1");
    expect(goal).toContain("Add an approval before writing files.");
    expect(goal).toContain("child of this Agent");
  });
});
