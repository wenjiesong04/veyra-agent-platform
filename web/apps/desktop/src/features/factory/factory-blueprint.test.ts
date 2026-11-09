import { describe, expect, it } from "vitest";
import { blueprintGraph, blueprintPresentation, revisionFactoryGoal } from "./factory-blueprint";
import { layoutExecutionGraph } from "../studio/graph-layout";

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

  it("reads Builder labels and the canvas-only introduction note", () => {
    expect(blueprintPresentation({
      ui_suggestions: {
        labels: { analyze: "需求分析" },
        notes: { note_intro: { x: 0, y: -220, text: "输入与输出说明", width: 420, manual_position: false } },
      },
    })).toEqual({
      labels: { analyze: "需求分析" },
      note: { text: "输入与输出说明", width: 420, color: "amber" },
    });
  });

  it("uses the Studio DAG layout for a Factory Blueprint branch", () => {
    const graph = blueprintGraph({
      nodes: [
        { id: "start", component_type: "Start" },
        { id: "condition", component_type: "Condition" },
        { id: "success", component_type: "Model" },
        { id: "failure", component_type: "HumanApproval" },
        { id: "out", component_type: "Output" },
      ],
      transitions: [
        { from: "start", port: "next", to: "condition" },
        { from: "condition", port: "true", to: "success" },
        { from: "condition", port: "false", to: "failure" },
        { from: "success", port: "next", to: "out" },
        { from: "failure", port: "approved", to: "out" },
      ],
    });
    const positions = layoutExecutionGraph(graph.nodes, graph.transitions);
    expect(positions.success.y).toBeLessThan(positions.failure.y);
    expect(positions.condition.x).toBeLessThan(positions.success.x);
    expect(positions.success.x).toBeLessThan(positions.out.x);
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
