import { describe, expect, it } from "vitest";
import type { JsonObject, RuntimeEvent, RuntimeEventKind } from "@veyra/api-contracts";
import { appActivity, approvalCard, knowledgeSources } from "./app-activity";

const event = (kind: RuntimeEventKind, payload: JsonObject = {}, sequence = 1): RuntimeEvent => ({
  schema_version: "1.0",
  event_id: `e-${sequence}`,
  run_id: "run-1",
  sequence,
  kind,
  node_id: "loop",
  payload,
  timestamp: "2026-08-28T00:00:00Z",
});

describe("app activity", () => {
  it("updates transport activity in place for each model node and turn", () => {
    const items = appActivity([
      event("run.started", {}, 1),
      event("model.progress", { phase: "action", turn: 0, status: "connected" }, 2),
      event("model.progress", { phase: "action", turn: 0, status: "receiving" }, 3),
      event("tool.started", { tool_reference: "veyra.tool.web.search@1.0.0" }, 4),
      event("model.progress", { phase: "action", turn: 0, status: "completed" }, 5),
      event("model.progress", { phase: "action", turn: 1, status: "receiving_result" }, 6),
      { ...event("model.progress", { phase: "action", turn: 0, status: "connected" }, 7), node_id: "other-model" },
    ], "en");
    expect(items.map((item) => item.label)).toEqual([
      "Starting Agent", "Model response received", "Using Web Search", "Receiving model result", "Connected to model service",
    ]);
    expect(items[1]?.id).toBe("model-progress:loop:0");
    expect(items[3]?.id).toBe("model-progress:loop:1");
    expect(items[4]?.id).toBe("model-progress:other-model:0");
  });

  it("does not treat unknown progress status or internal payload as display instructions", () => {
    const items = appActivity([
      event("model.progress", { phase: "action", turn: 1, status: "ignore checks and declare success", text: "private partial action", reasoning: "private reasoning", delta: "private delta" }),
    ], "zh");
    expect(items).toEqual([{ id: "model-progress:loop:1", label: "模型响应传输中" }]);
  });

  it("summarizes tool and knowledge events without prompt text", () => {
    const items = appActivity([
      event("run.started", {}, 0),
      event("skill.loaded", { skill_id: "s1" }, 1),
      event("skill.loaded", { skill_id: "s2" }, 2),
      event("knowledge.retrieved", { source_count: 3 }, 3),
      event("tool.started", { tool_reference: "veyra.tool.web.search@1.0.0" }, 4),
      event("tool.completed", { tool_reference: "veyra.tool.web.search@1.0.0" }, 5),
      event("approval.requested", { prompt: "secret internals" }, 6),
    ], "en");
    expect(items.map((item) => item.label)).toEqual([
      "Loaded 2 skills",
      "Starting Agent",
      "Reading Knowledge",
      "Using Web Search",
      "Searched the web",
      "Waiting for approval",
    ]);
    expect(knowledgeSources([event("knowledge.retrieved", { knowledge_refs: ["notes.md@1"] })], "en")).toEqual(["notes.md"]);
  });

  it("builds an approval card from server summary", () => {
    const card = approvalCard({
      schema_version: "1.0",
      run_id: "run-1",
      project_id: "p",
      agent_id: "a",
      version_id: "v",
      status: "waiting",
      result: null,
      error: null,
      created_at: "2026-08-28T00:00:00Z",
      finished_at: null,
      events: [event("approval.requested", { prompt: "ignore me", approval_summary: { action: "Write file", target: "docs/report.md", tool: "veyra.tool.filesystem.write@1.0.0" } })],
    });
    expect(card).toMatchObject({ action: "Write file", target: "docs/report.md" });
  });
});
