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
