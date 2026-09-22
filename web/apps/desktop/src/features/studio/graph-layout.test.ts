import { describe, expect, it } from "vitest";
import { estimatedNodeSize, layoutExecutionGraph, type LayoutEdge, type LayoutNode } from "./graph-layout";

function assertNoOverlap(nodes: LayoutNode[], positions: Record<string, { x: number; y: number }>) {
  for (let left = 0; left < nodes.length; left += 1) {
    for (let right = left + 1; right < nodes.length; right += 1) {
      const a = nodes[left]!;
      const b = nodes[right]!;
      const aPosition = positions[a.id]!;
      const bPosition = positions[b.id]!;
      const aSize = estimatedNodeSize(a.component_type);
      const bSize = estimatedNodeSize(b.component_type);
      const separated = aPosition.x + aSize.width <= bPosition.x
        || bPosition.x + bSize.width <= aPosition.x
        || aPosition.y + aSize.height <= bPosition.y
        || bPosition.y + bSize.height <= aPosition.y;
      expect(separated, `${a.id} overlaps ${b.id}`).toBe(true);
    }
  }
}

describe("layoutExecutionGraph", () => {
  it("lays out a simple three-node chain left to right", () => {
    const nodes = [
      { id: "out", component_type: "Output" },
      { id: "model", component_type: "Model" },
      { id: "start", component_type: "Start" },
    ];
    const positions = layoutExecutionGraph(nodes, [
      { from: "start", to: "model", port: "next" },
      { from: "model", to: "out", port: "next" },
    ]);
    expect(positions.start.x).toBeLessThan(positions.model.x);
    expect(positions.model.x).toBeLessThan(positions.out.x);
  });

  it("keeps true/success paths above false/rejection paths and centers a merge", () => {
    const nodes = [
      { id: "start", component_type: "Start" },
      { id: "condition", component_type: "Condition" },
      { id: "true_work", component_type: "Tool" },
      { id: "false_work", component_type: "HumanApproval" },
      { id: "merge", component_type: "Transform" },
      { id: "out", component_type: "Output" },
    ];
    const edges: LayoutEdge[] = [
      { from: "start", to: "condition", port: "next" },
      { from: "condition", to: "true_work", port: "true" },
      { from: "condition", to: "false_work", port: "false" },
      { from: "true_work", to: "merge", port: "next" },
      { from: "false_work", to: "merge", port: "approved" },
      { from: "merge", to: "out", port: "next" },
    ];
    const positions = layoutExecutionGraph(nodes, edges);
    expect(positions.true_work.y).toBeLessThan(positions.false_work.y);
    const branchCenter = (positions.true_work.y + estimatedNodeSize("Tool").height / 2
      + positions.false_work.y + estimatedNodeSize("HumanApproval").height / 2) / 2;
    expect(Math.abs(positions.merge.y + estimatedNodeSize("Transform").height / 2 - branchCenter)).toBeLessThan(100);
    expect(positions.condition.x).toBeLessThan(positions.true_work.x);
    expect(positions.true_work.x).toBeLessThan(positions.merge.x);
    assertNoOverlap(nodes, positions);
  });

  it("keeps approval and estimated custom-component boxes readable", () => {
    expect(estimatedNodeSize("CustomComponent").width).toBeGreaterThan(estimatedNodeSize("Model").width);
    expect(estimatedNodeSize("HumanApproval").height).toBeGreaterThan(estimatedNodeSize("Model").height);
    const nodes = [
      { id: "start", component_type: "Start" },
      { id: "custom", component_type: "CustomComponent" },
      { id: "approval", component_type: "HumanApproval" },
      { id: "out", component_type: "Output" },
    ];
    const positions = layoutExecutionGraph(nodes, [
      { from: "start", to: "custom" },
      { from: "custom", to: "approval" },
      { from: "approval", to: "out", port: "approved" },
    ]);
    assertNoOverlap(nodes, positions);
  });

  it("is deterministic and places six-to-eight and twelve-to-fifteen node DAGs without overlap", () => {
    for (const count of [7, 14]) {
      const nodes = Array.from({ length: count }, (_, index) => ({
        id: `node_${String(index).padStart(2, "0")}`,
        component_type: index === 0 ? "Start" : index === count - 1 ? "Output" : index === 3 ? "Condition" : "Model",
      }));
      const edges: LayoutEdge[] = [];
      for (let index = 0; index < count - 1; index += 1) {
        edges.push({ from: nodes[index]!.id, to: nodes[index + 1]!.id, port: index === 3 ? "true" : "next" });
      }
      if (count > 8) {
        edges.splice(4, 1, { from: nodes[3]!.id, to: nodes[5]!.id, port: "false" });
      }
      const first = layoutExecutionGraph(nodes, edges);
      expect(layoutExecutionGraph(nodes, edges)).toEqual(first);
      assertNoOverlap(nodes, first);
    }
  });

  it("preserves explicitly stored coordinates while filling missing ones", () => {
    const nodes = [
      { id: "start", component_type: "Start" },
      { id: "model", component_type: "Model" },
      { id: "out", component_type: "Output" },
    ];
    const positions = layoutExecutionGraph(nodes, [
      { from: "start", to: "model" },
      { from: "model", to: "out" },
    ], { start: { x: 600, y: 360 } });
    expect(positions.start).toEqual({ x: 600, y: 360 });
    expect(positions.model.x).toBeLessThan(positions.out.x);
  });
});
