import { describe, expect, it } from "vitest";
import { Position } from "@xyflow/react";
import { flowEdgeGeometry } from "./canvas-edge";
import { estimatedNodeSize, fitViewCandidates, labeledNodeSize, layoutExecutionGraph, nodeSize, type LayoutEdge, type LayoutNode } from "./graph-layout";

function assertNoOverlap(nodes: LayoutNode[], positions: Record<string, { x: number; y: number }>) {
  for (let left = 0; left < nodes.length; left += 1) {
    for (let right = left + 1; right < nodes.length; right += 1) {
      const a = nodes[left]!;
      const b = nodes[right]!;
      const aPosition = positions[a.id]!;
      const bPosition = positions[b.id]!;
      const aSize = nodeSize(a);
      const bSize = nodeSize(b);
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

  it("reserves the explicit width of a long label before the next column", () => {
    const nodes = [
      { id: "start", component_type: "Start" },
      { id: "long", component_type: "Condition", width: 280, height: 108 },
      { id: "out", component_type: "Output" },
    ];
    const positions = layoutExecutionGraph(nodes, [
      { from: "start", to: "long" },
      { from: "long", to: "out" },
    ]);
    expect(positions.long.x).toBeGreaterThanOrEqual(positions.start.x + estimatedNodeSize("Start").width);
    expect(positions.out.x).toBeGreaterThanOrEqual(positions.long.x + 280);
    assertNoOverlap(nodes, positions);
  });
});

describe("fitViewCandidates", () => {
  it("fits capability nodes without letting a canvas note shrink them", () => {
    const note = { id: "goal", data: { note: { text: "A long request note" } } };
    const intro = { id: "note_intro", data: { note: { text: "The generated purpose note" } } };
    const model = { id: "model", data: { flow: { component_type: "Model" } } };
    expect(fitViewCandidates([note, model])).toEqual([model]);
    expect(fitViewCandidates([note])).toEqual([note]);
    expect(fitViewCandidates([intro, model], true)).toEqual([model, intro]);
  });
});

function pathCoordinates(path: string): number[] {
  return [...path.matchAll(/-?\d+(?:\.\d+)?/g)].map((match) => Number(match[0]));
}

function assertOrthogonal(path: string) {
  const commands = [...path.matchAll(/([MLQ])\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)(?:\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?))?/g)];
  let previous: { x: number; y: number } | null = null;
  for (const match of commands) {
    if (match[1] === "Q") {
      previous = { x: Number(match[4]), y: Number(match[5]) };
      continue;
    }
    const current = { x: Number(match[2]), y: Number(match[3]) };
    if (previous && match[1] === "L") {
      expect(previous.x === current.x || previous.y === current.y).toBe(true);
    }
    previous = current;
  }
}

describe("labeledNodeSize", () => {
  it("keeps short titles compact and wraps long titles instead of stretching", () => {
    const short = labeledNodeSize("输入", "start", 1);
    const wrapped = labeledNodeSize("用户上传想要包装的物品图片或文字描述并说明场合预算", "analyze_item", 1);
    expect(short.width).toBeLessThanOrEqual(200);
    expect(wrapped.width).toBeLessThanOrEqual(200);
    expect(wrapped.height).toBeGreaterThan(short.height);
    expect(wrapped.width).toBeGreaterThanOrEqual(short.width);
  });
});

describe("review edge routing", () => {
  it("keeps a near-horizontal hop orthogonal instead of diagonal", () => {
    const edge = flowEdgeGeometry(120, 80, 340, 88, Position.Right, Position.Left);
    expect(edge.path).not.toBe("M 120 80 L 340 88");
    assertOrthogonal(edge.path);
    expect(edge.path).toMatch(/ Q /);
  });

  it("routes a skip connection below the row and keeps the label on that path", () => {
    const edge = flowEdgeGeometry(120, 80, 900, 86, Position.Right, Position.Left, "rejected");
    expect(edge.path).not.toBe("M 120 80 L 900 86");
    assertOrthogonal(edge.path);
    expect(edge.path).toMatch(/ Q /);
    const values = pathCoordinates(edge.path);
    const ys = values.filter((_, index) => index % 2 === 1);
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(80);
    expect(Math.max(...ys)).toBeGreaterThan(80 + 120);
    expect(edge.labelY).toBe(Math.max(...ys));
    expect(edge.labelX).toBeGreaterThan(120);
    expect(edge.labelX).toBeLessThan(900);
  });

  it("staggers rejected skips below next skips so the highways do not overlap", () => {
    const next = flowEdgeGeometry(120, 80, 900, 86, Position.Right, Position.Left, "next");
    const rejected = flowEdgeGeometry(120, 80, 900, 86, Position.Right, Position.Left, "rejected");
    expect(rejected.labelY).toBeGreaterThan(next.labelY);
  });

  it("keeps a forward branch inside the column gap with rounded corners", () => {
    const edge = flowEdgeGeometry(300, 90, 540, 230, Position.Right, Position.Left);
    assertOrthogonal(edge.path);
    expect(edge.path).toMatch(/ Q /);
    const values = pathCoordinates(edge.path);
    const ys = values.filter((_, index) => index % 2 === 1);
    expect(Math.min(...ys)).toBeGreaterThan(90 - 12);
    expect(Math.max(...ys)).toBeLessThan(230 + 12);
  });
});
