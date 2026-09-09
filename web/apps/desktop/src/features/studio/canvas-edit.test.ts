import { describe, expect, it } from "vitest";
import type { AgentSource, WorkflowSource } from "@veyra/api-contracts";
import { copySelection, deleteSelection, loadCanvasClipboard, parseCanvasClipboard, pasteClipboard, selectableCanvasIds, storeCanvasClipboard } from "./canvas-edit";
import { emptyCanvasHistory, recordCanvasChange, redoCanvasChange, undoCanvasChange } from "./canvas-history";
import { canvasShortcut } from "./canvas-shortcuts";

const agent: AgentSource = {
  schema_version: "1.0",
  agentspec_version: "26.1",
  component_type: "Flow",
  agent_id: "agent-1",
  slug: "review",
  name: "Review",
  description: "",
  inputs: {},
  outputs: { result: "string" },
  nodes: [
    { id: "start", component_type: "Start" },
    { id: "model", component_type: "Model", model_ref: "model.primary", system_prompt: "Hi" },
    { id: "out", component_type: "Output", output_name: "result" },
  ],
  transitions: [
    { from: "start", port: "next", to: "model" },
    { from: "model", port: "next", to: "out" },
  ],
  extensions: { veyra: { runtime_profile: "guarded", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } },
  ui: {
    positions: { start: { x: 0, y: 0 }, model: { x: 120, y: 0 }, out: { x: 240, y: 0 } },
    notes: { note_a: { x: 10, y: 80, text: "remember", color: "amber", width: 220 } },
  },
  lock: {},
};

const workflow: WorkflowSource = {
  schema_version: "1.0",
  component_type: "Workflow",
  workflow_id: "wf-1",
  slug: "path",
  name: "Path",
  description: "",
  inputs: { prompt: "string" },
  outputs: { result: "string" },
  nodes: [
    { id: "start", component_type: "Start" },
    { id: "call", component_type: "AgentCall", agent_ref: "agent@version", input_mapping: { request: "prompt" }, output_mapping: { result: "result" } },
    { id: "out", component_type: "Output", output_name: "result" },
  ],
  transitions: [
    { from: "start", port: "next", to: "call" },
    { from: "call", port: "next", to: "out" },
  ],
  extensions: { veyra: { permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } },
  ui: { positions: { start: { x: 0, y: 0 }, call: { x: 160, y: 0 }, out: { x: 320, y: 0 } } },
  lock: { "agent@version": "a".repeat(64) },
};

function key(partial: Partial<KeyboardEvent> & { key: string }): KeyboardEvent {
  return {
    key: partial.key,
    code: partial.code ?? "",
    metaKey: Boolean(partial.metaKey),
    ctrlKey: Boolean(partial.ctrlKey),
    shiftKey: Boolean(partial.shiftKey),
    altKey: Boolean(partial.altKey),
    isComposing: Boolean(partial.isComposing),
    target: partial.target ?? document.body,
  } as KeyboardEvent;
}

describe("canvas shortcuts", () => {
  it("maps undo redo copy paste duplicate and delete, and ignores typing", () => {
    expect(canvasShortcut(key({ key: "z", metaKey: true }))).toBe("undo");
    expect(canvasShortcut(key({ key: "Dead", code: "KeyZ", metaKey: true }))).toBe("undo");
    expect(canvasShortcut(key({ key: "z", ctrlKey: true, shiftKey: true }))).toBe("redo");
    expect(canvasShortcut(key({ key: "y", ctrlKey: true }))).toBe("redo");
    expect(canvasShortcut(key({ key: "c", metaKey: true }))).toBe("copy");
    expect(canvasShortcut(key({ key: "v", metaKey: true }))).toBe("paste");
    expect(canvasShortcut(key({ key: "d", metaKey: true }))).toBe("duplicate");
    expect(canvasShortcut(key({ key: "Backspace" }))).toBe("delete");
    const input = document.createElement("textarea");
    expect(canvasShortcut(key({ key: "z", metaKey: true, target: input }))).toBeNull();
    expect(canvasShortcut(key({ key: "z", metaKey: true, isComposing: true }))).toBeNull();
  });
});

describe("canvas history", () => {
  it("undoes and redoes a recorded source change", () => {
    const next = { ...agent, name: "Changed" };
    let history = recordCanvasChange(emptyCanvasHistory(), agent, next);
    const undone = undoCanvasChange(history, next);
    expect(undone?.source.name).toBe("Review");
    history = undone!.history;
    const redone = redoCanvasChange(history, undone!.source);
    expect(redone?.source.name).toBe("Changed");
    expect(recordCanvasChange(emptyCanvasHistory(), agent, agent).past).toHaveLength(0);
  });
});

describe("canvas copy paste and delete", () => {
  it("copies internal nodes and notes, skips Start/Output, and pastes new ids with offset", () => {
    const clip = copySelection(agent, ["start", "model", "out", "note_a"]);
    expect(clip?.nodes.map((node) => node.id)).toEqual(["model"]);
    expect(clip?.notes?.note_a?.text).toBe("remember");
    expect(clip?.transitions).toEqual([]);
    const pasted = pasteClipboard(agent, clip!, { x: 40, y: 40 });
    expect(pasted).not.toBeNull();
    expect(pasted!.selectedIds).toHaveLength(2);
    expect(pasted!.source.nodes).toHaveLength(4);
    const copyNode = pasted!.source.nodes.find((node) => node.id !== "start" && node.id !== "model" && node.id !== "out");
    expect(copyNode?.component_type).toBe("Model");
    expect(copyNode?.id).not.toBe("model");
    expect(pasted!.source.ui.positions[copyNode!.id]).toEqual({ x: 160, y: 40 });
    expect(Object.keys(pasted!.source.ui.notes ?? {})).toHaveLength(2);
  });

  it("keeps internal edges when copying connected workflow calls", () => {
    const withExtra: WorkflowSource = {
      ...workflow,
      nodes: [
        ...workflow.nodes.slice(0, 2),
        { id: "call2", component_type: "AgentCall", agent_ref: "agent@version", input_mapping: { request: "prompt" }, output_mapping: { result: "temp" } },
        workflow.nodes[2]!,
      ],
      transitions: [
        { from: "start", port: "next", to: "call" },
        { from: "call", port: "next", to: "call2" },
        { from: "call2", port: "next", to: "out" },
      ],
      ui: { positions: { ...workflow.ui.positions, call2: { x: 240, y: 0 } } },
    };
    const clip = copySelection(withExtra, ["call", "call2"]);
    expect(clip?.transitions).toEqual([{ from: "call", port: "next", to: "call2" }]);
    const pasted = pasteClipboard(withExtra, clip!);
    const ids = pasted!.selectedIds;
    expect(ids).toHaveLength(2);
    expect(pasted!.source.transitions.some((edge) => edge.from === ids[0] && edge.to === ids[1])).toBe(true);
  });

  it("does not paste AgentCall nodes onto an Agent canvas", () => {
    const clip = copySelection(workflow, ["call"]);
    expect(pasteClipboard(agent, clip!)).toBeNull();
  });

  it("deletes selected nodes and edges but keeps Start and Output", () => {
    const next = deleteSelection(agent, ["start", "model", "out", "note_a"], ["start:next:model"]);
    expect(next.nodes.map((node) => node.id)).toEqual(["start", "out"]);
    expect(next.ui.notes).toBeUndefined();
    expect(next.transitions).toEqual([]);
  });

  it("deletes an extra Start while keeping the canonical one", () => {
    const duplicate = {
      ...agent,
      nodes: [...agent.nodes, { id: "start_extra", component_type: "Start" as const }],
      ui: { ...agent.ui, positions: { ...agent.ui.positions, start_extra: { x: 40, y: 80 } } },
    };
    const next = deleteSelection(duplicate, ["start_extra"]);
    expect(next.nodes.map((node) => node.id)).toEqual(["start", "model", "out"]);
    expect(deleteSelection(duplicate, ["start"]).nodes.map((node) => node.id)).toContain("start");
  });

  it("round-trips clipboard JSON and remembers an in-memory clip", () => {
    const clip = copySelection(agent, ["model"]);
    expect(parseCanvasClipboard(JSON.stringify(clip))).toEqual(clip);
    expect(parseCanvasClipboard("not-json")).toBeNull();
    storeCanvasClipboard(clip!);
    expect(loadCanvasClipboard()).toEqual(clip);
  });

  it("lists every selectable canvas id", () => {
    expect(selectableCanvasIds(agent)).toEqual(["start", "model", "out", "note_a"]);
  });
});
